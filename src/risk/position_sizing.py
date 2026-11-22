"""
Institutional Position Sizing Engine.
Calculates mathematically precise lot sizing based on account equity,
tick value, contract specifications, and structural stop-loss distances.
Enforces strict volume quantization, minimum reward-to-risk, margin limits,
and Rule R9 (hard-capped at 2.0% risk per trade in code regardless of config; default 1.0%).
"""

from __future__ import annotations
import math
import logging
from dataclasses import dataclass
from typing import Optional

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    mt5 = None
    MT5_AVAILABLE = False

from src.core.contracts import AccountInfo, SymbolInfo, OrderType, calculate_risk_reward
from src.risk.account_tier import AccountTierManager
from src.risk.target_feasibility import TargetFeasibilityEngine, TargetFeasibilityResult

logger = logging.getLogger("PositionSizingEngine")


@dataclass
class PositionSizeResult:
    is_approved: bool
    volume: float
    monetary_risk: float
    risk_percent_actual: float
    sl_points: float
    sl_pips: float
    loss_per_lot: float
    margin_required: float
    reward_to_risk: float = 0.0
    tp_money: float = 0.0
    tier_name: str = "STANDARD"
    target_risk_pct: float = 1.0
    ceiling_risk_pct: float = 2.0
    min_balance_needed: float = 0.0
    raw_lots: float = 0.0
    is_micro_exception: bool = False
    log_line: str = ""
    rejection_reason: Optional[str] = None
    target_price_20usd: Optional[float] = None
    feasibility: Optional[TargetFeasibilityResult] = None
    # Cent account monetary fields
    monetary_risk_native: float = 0.0
    monetary_risk_normalized: float = 0.0
    native_currency: str = "USD"
    normalized_currency: str = "USD"
    is_cent_account: bool = False
    denomination_factor: float = 1.0


class PositionSizingEngine:
    HARD_MAX_RISK_PCT: float = 2.0
    DEFAULT_RISK_PCT: float = 0.25

    def __init__(
        self,
        default_risk_percent: float = 0.25,
        max_risk_percent_per_trade: float = 2.0,
        min_rr: float = 2.0,
        reduced_history_factor: float = 0.5,
        max_margin_percent_of_free: float = 50.0,
        max_lot_cap: Optional[float] = None,
        tier_manager: Optional[AccountTierManager] = None
    ):
        # R9 hard cap enforced in constructor
        self.default_risk_percent = min(self.HARD_MAX_RISK_PCT, default_risk_percent)
        self.max_risk_percent_per_trade = min(self.HARD_MAX_RISK_PCT, max_risk_percent_per_trade)
        self.min_rr = min_rr
        self.reduced_history_factor = reduced_history_factor
        self.max_margin_percent_of_free = max_margin_percent_of_free
        self.max_lot_cap = max_lot_cap  # None = governed dynamically by broker symbol_info.max_lot & margin
        self.tier_manager = tier_manager or AccountTierManager()

    def calculate_lot_size(
        self,
        account: AccountInfo,
        symbol_info: SymbolInfo,
        entry_price: float,
        stop_loss: float,
        take_profit: Optional[float] = None,
        risk_percent: Optional[float] = None,
        is_reduced_history: bool = False,
        sizing_reference: str = "CONSERVATIVE",
        order_type: Optional[OrderType] = None,
        adaptive_scalping: bool = False,
        adaptive_min_lot_ceiling_pct: float = 2.0,
        min_rr_override: Optional[float] = None,
        kelly_risk_pct: Optional[float] = None,
        volatility_scale: Optional[float] = None,
        atr_m15: Optional[float] = None,
        atr_h1: Optional[float] = None,
        target_net_usd: float = 20.0,
    ) -> PositionSizeResult:
        """
        Single Shared Position Sizing Algorithm used by every order path, enforcing R9:
        - Hard-cap risk per trade at 2.0% in code regardless of config; default 1.0%.
        - Reject any order without a valid stop loss.
        """
        self.tier_manager.reload_config()

        # R9 hard cap in code regardless of caller/config input
        adaptive_min_lot_ceiling_pct = min(self.HARD_MAX_RISK_PCT, adaptive_min_lot_ceiling_pct)
        if risk_percent is not None:
            risk_percent = min(self.HARD_MAX_RISK_PCT, risk_percent)

        # 1. Evaluate account facts and cent account detection
        capital_base = min(account.balance, account.equity)
        is_cent = bool(getattr(account, "is_cent_account", False))
        denom_factor = float(getattr(account, "denomination_factor", 100.0 if is_cent else 1.0))
        native_curr = getattr(account, "raw_currency", getattr(account, "currency", "USD"))
        raw_bal = getattr(account, "raw_balance", capital_base)
        norm_capital = capital_base / denom_factor if is_cent else capital_base
        unit_str = f"{raw_bal:,.2f} {native_curr} (${norm_capital:.2f} USD)" if is_cent else f"{account.currency} (${capital_base:.2f})"
        effective_order_type = order_type if order_type is not None else (OrderType.BUY if entry_price > stop_loss else OrderType.SELL)

        # Evaluate Account Tier
        tier_def, changed, tier_msg = self.tier_manager.evaluate_account(account)
        tier_name = tier_def.name
        if is_reduced_history:
            effective_cap = min(
                self.HARD_MAX_RISK_PCT,
                self.max_risk_percent_per_trade,
                tier_def.absolute_ceiling_pct if tier_def.absolute_ceiling_pct > 0 else self.max_risk_percent_per_trade,
            )
            ceiling_pct = min(self.HARD_MAX_RISK_PCT, effective_cap * self.reduced_history_factor)
            requested_risk = risk_percent if risk_percent is not None else min(self.DEFAULT_RISK_PCT, tier_def.target_risk_pct)
            target_pct = min(self.HARD_MAX_RISK_PCT, requested_risk, ceiling_pct)
        else:
            ceiling_pct = min(self.HARD_MAX_RISK_PCT, tier_def.absolute_ceiling_pct)
            target_pct = (
                min(self.DEFAULT_RISK_PCT, tier_def.target_risk_pct)
                if risk_percent is None
                else min(self.HARD_MAX_RISK_PCT, risk_percent, ceiling_pct)
            )

        # Advanced Quantitative Modulation (Phase 3: Kelly Sizing & Volatility Targeting)
        if kelly_risk_pct is not None and kelly_risk_pct > 0.0:
            target_pct = min(target_pct, kelly_risk_pct, ceiling_pct)
        if volatility_scale is not None and volatility_scale > 0.0:
            vol_mult = min(1.0, max(0.2, float(volatility_scale)))
            target_pct = min(self.HARD_MAX_RISK_PCT, target_pct * vol_mult)

        # Hard Floor Guard: < $5.00 disables trading immediately
        norm_capital = capital_base / denom_factor if is_cent else capital_base
        if norm_capital < 5.0 or tier_name == "BELOW_FLOOR":
            rej = f"Account capital ${norm_capital:.2f} is below the $5.00 floor ({tier_name}). Trading disabled."
            log_line = (
                f"[SIZING] REJECTED | Bal: {unit_str} | Tier: {tier_name} | "
                f"TargetRisk: {target_pct:.2f}% | RawLots: 0.00 | FinalLots: 0.00 | Reason: {rej}"
            )
            logger.warning(log_line)
            return PositionSizeResult(
                is_approved=False,
                volume=0.0,
                monetary_risk=0.0,
                risk_percent_actual=0.0,
                sl_points=0.0,
                sl_pips=0.0,
                loss_per_lot=0.0,
                margin_required=0.0,
                tier_name=tier_name,
                target_risk_pct=target_pct,
                ceiling_risk_pct=ceiling_pct,
                min_balance_needed=5.0,
                raw_lots=0.0,
                log_line=log_line,
                rejection_reason=rej
            )

        # 2. Risk Money Calculation (strictly in native account units)
        risk_money = capital_base * (target_pct / 100.0)

        # 3. Structural SL presence & distance check (R9.2)
        sl_distance = abs(entry_price - stop_loss) if stop_loss > 0 else 0.0
        if stop_loss <= 0 or sl_distance <= 0:
            rej = "Stop loss is mandatory and distance must be strictly greater than zero (R9)."
            log_line = f"[SIZING] REJECTED | Bal: {unit_str} | Tier: {tier_name} | Reason: {rej}"
            logger.warning(log_line)
            return PositionSizeResult(
                is_approved=False,
                volume=0.0,
                monetary_risk=0.0,
                risk_percent_actual=0.0,
                sl_points=0.0,
                sl_pips=0.0,
                loss_per_lot=0.0,
                margin_required=0.0,
                tier_name=tier_name,
                target_risk_pct=target_pct,
                ceiling_risk_pct=ceiling_pct,
                min_balance_needed=0.0,
                raw_lots=0.0,
                log_line=log_line,
                rejection_reason=rej
            )

        tick_size = symbol_info.tick_size if symbol_info.tick_size > 0 else symbol_info.point
        tick_value = symbol_info.tick_value if symbol_info.tick_value > 0 else 1.0

        # Structural loss per lot calculation (verified via OrderCalcProfit)
        base_loss_per_lot_native = 0.0
        if MT5_AVAILABLE and mt5.terminal_info() is not None:
            try:
                mt5_order_type = mt5.ORDER_TYPE_BUY if (entry_price > stop_loss) else mt5.ORDER_TYPE_SELL
                if order_type is not None:
                    if order_type in [OrderType.BUY, OrderType.BUY_LIMIT, OrderType.BUY_STOP]:
                        mt5_order_type = mt5.ORDER_TYPE_BUY
                    else:
                        mt5_order_type = mt5.ORDER_TYPE_SELL
                profit_calc = mt5.order_calc_profit(mt5_order_type, symbol_info.symbol, 1.0, entry_price, stop_loss)
                if profit_calc is not None and profit_calc != 0.0:
                    base_loss_per_lot_native = abs(float(profit_calc))
            except Exception:
                pass

        if base_loss_per_lot_native <= 0.0:
            num_ticks = sl_distance / tick_size
            base_loss_per_lot_native = num_ticks * tick_value

        if base_loss_per_lot_native <= 0:
            rej = "Calculated loss per lot is non-positive."
            log_line = f"[SIZING] REJECTED | Bal: {unit_str} | Tier: {tier_name} | Reason: {rej}"
            logger.warning(log_line)
            return PositionSizeResult(
                is_approved=False,
                volume=0.0,
                monetary_risk=0.0,
                risk_percent_actual=0.0,
                sl_points=0.0,
                sl_pips=0.0,
                loss_per_lot=0.0,
                margin_required=0.0,
                tier_name=tier_name,
                target_risk_pct=target_pct,
                ceiling_risk_pct=ceiling_pct,
                raw_lots=0.0,
                log_line=log_line,
                rejection_reason=rej,
                is_cent_account=is_cent,
                denomination_factor=denom_factor,
                native_currency=native_curr,
            )

        # Spread & Commission Cost Estimation per lot (native units)
        spread_pts = symbol_info.spread if symbol_info.spread > 0 else 1.0
        spread_cost_per_lot_native = (spread_pts * symbol_info.point / tick_size) * tick_value
        commission_per_lot_native = 7.0 if is_cent else 7.0
        total_loss_per_lot_native = base_loss_per_lot_native + spread_cost_per_lot_native + commission_per_lot_native
        total_loss_per_lot_normalized = total_loss_per_lot_native / denom_factor if is_cent else total_loss_per_lot_native
        total_loss_per_lot = total_loss_per_lot_native

        # 4. Raw lots calculation from structural loss (strictly native / native)
        raw_volume = risk_money / total_loss_per_lot_native

        # Lot caps: governed dynamically by broker symbol_info.max_lot (arbitrary balance/static caps removed)
        effective_max_lot = symbol_info.max_lot
        if self.max_lot_cap is not None and self.max_lot_cap > 0:
            effective_max_lot = min(symbol_info.max_lot, self.max_lot_cap)

        # 5. Volume quantization (never round up; conform to broker lot_step precision)
        step = symbol_info.lot_step if symbol_info.lot_step > 0 else 0.01
        step_str = f"{step:.8f}".rstrip("0")
        step_decimals = len(step_str.split(".")[1]) if "." in step_str else 2
        steps_count = math.floor(round(raw_volume / step, 6))
        quantized_volume = round(steps_count * step, step_decimals)

        # 6. Check against minimum lot - Strictly enforce risk budget without upward rounding/overrides
        min_lot = symbol_info.min_lot if symbol_info.min_lot > 0 else 0.01
        min_lot_loss_native = min_lot * total_loss_per_lot_native
        min_lot_loss_normalized = min_lot_loss_native / denom_factor if is_cent else min_lot_loss_native
        min_lot_risk_pct = (min_lot_loss_native / capital_base) * 100.0
        min_balance_needed = (min_lot_loss_native / (target_pct / 100.0)) / denom_factor if (is_cent and target_pct > 0) else (min_lot_loss_native / (target_pct / 100.0) if target_pct > 0 else 0.0)

        is_micro_exception = False

        if quantized_volume >= min_lot:
            final_volume = min(quantized_volume, effective_max_lot)
        else:
            # Per directive: Never round volume up to min_lot or grant micro-lot upward overrides.
            margin_req = (min_lot * symbol_info.margin_required) if getattr(symbol_info, "margin_required", 0) > 0 else 0.0
            min_loss_str = f"{min_lot_loss_native:,.2f} {native_curr} (${min_lot_loss_normalized:.2f} USD)" if is_cent else f"${min_lot_loss_normalized:.2f}"
            reason = (
                f"MIN_VOLUME_EXCEEDS_RISK_BUDGET (MINIMUM_VOLUME_EXCEEDS_RISK_BUDGET): Min lot {min_lot:.2f} risks {min_loss_str} "
                f"({min_lot_risk_pct:.2f}% of capital {capital_base:.2f} {native_curr}), exceeding target risk ({target_pct:.2f}%). "
                f"Required margin: {margin_req:.2f} {native_curr}, estimated monetary risk: {min_lot_loss_native:.2f} {native_curr}. "
                f"Required raw lot: {raw_volume:.4f}. Min balance needed: ${min_balance_needed:.2f}."
            )
            log_line = (
                f"[SIZING] SKIPPED | Bal: {unit_str} | Tier: {tier_name} | "
                f"TargetRisk: {target_pct:.2f}% | Loss/Lot: {total_loss_per_lot_native:.2f} {native_curr} | "
                f"RawLots: {raw_volume:.4f} | FinalLots: 0.00 | RealRisk: {min_lot_risk_pct:.2f}% ({min_loss_str}) | "
                f"Reason: {reason}"
            )
            logger.info(log_line)
            return PositionSizeResult(
                is_approved=False,
                volume=0.0,
                monetary_risk=min_lot_loss_native,
                monetary_risk_native=min_lot_loss_native,
                monetary_risk_normalized=min_lot_loss_normalized,
                risk_percent_actual=min_lot_risk_pct,
                sl_points=sl_distance / symbol_info.point,
                sl_pips=sl_distance / (symbol_info.point * 10),
                loss_per_lot=total_loss_per_lot_native,
                margin_required=0.0,
                tier_name=tier_name,
                target_risk_pct=target_pct,
                ceiling_risk_pct=ceiling_pct,
                min_balance_needed=round(min_balance_needed, 2),
                raw_lots=round(raw_volume, 4),
                is_micro_exception=False,
                log_line=log_line,
                rejection_reason=reason,
                is_cent_account=is_cent,
                denomination_factor=denom_factor,
                native_currency=native_curr,
            )

        actual_loss_money_native = final_volume * base_loss_per_lot_native
        actual_loss_money_normalized = actual_loss_money_native / denom_factor if is_cent else actual_loss_money_native
        actual_loss_money = actual_loss_money_native
        actual_risk_pct = (actual_loss_money_native / capital_base) * 100.0
        actual_monetary_risk_native = actual_loss_money_native + (final_volume * (spread_cost_per_lot_native + commission_per_lot_native))
        actual_monetary_risk_normalized = actual_monetary_risk_native / denom_factor if is_cent else actual_monetary_risk_native
        actual_monetary_risk = actual_monetary_risk_native

        # Hard Ceiling Guard Check (R9: never exceed 2.0%)
        hard_ceiling = min(self.HARD_MAX_RISK_PCT, ceiling_pct)
        if actual_risk_pct > hard_ceiling + 1e-9:
            rej = f"Calculated risk {actual_risk_pct:.2f}% exceeds R9 hard risk ceiling {hard_ceiling:.2f}%"
            log_line = f"[SIZING] REJECTED | Bal: {unit_str} | Tier: {tier_name} | Reason: {rej}"
            logger.warning(log_line)
            return PositionSizeResult(
                is_approved=False,
                volume=0.0,
                monetary_risk=actual_monetary_risk_native,
                monetary_risk_native=actual_monetary_risk_native,
                monetary_risk_normalized=actual_monetary_risk_normalized,
                risk_percent_actual=actual_risk_pct,
                sl_points=sl_distance / symbol_info.point,
                sl_pips=sl_distance / (symbol_info.point * 10),
                loss_per_lot=total_loss_per_lot_native,
                margin_required=0.0,
                tier_name=tier_name,
                target_risk_pct=target_pct,
                ceiling_risk_pct=hard_ceiling,
                min_balance_needed=round(min_balance_needed, 2),
                raw_lots=round(raw_volume, 4),
                log_line=log_line,
                rejection_reason=rej,
                is_cent_account=is_cent,
                denomination_factor=denom_factor,
                native_currency=native_curr,
            )

        # 7. Reward to Risk check
        rr = 0.0
        total_tp_money = 0.0
        if take_profit is not None and take_profit > 0.0:
            tp_dist = abs(take_profit - entry_price)
            tp_ticks = tp_dist / tick_size
            gain_per_lot_native = tp_ticks * tick_value
            if is_cent and getattr(symbol_info, "currency_profit", "USD") == "USD":
                gain_per_lot_native *= denom_factor
            gross_tp_native = final_volume * gain_per_lot_native
            gross_tp_normalized = gross_tp_native / denom_factor if is_cent else gross_tp_native
            cost_native = final_volume * (spread_cost_per_lot_native + commission_per_lot_native)
            total_tp_money_native = max(0.0, gross_tp_native - cost_native)
            total_tp_money = total_tp_money_native / denom_factor if is_cent else total_tp_money_native
            rr = calculate_risk_reward(entry_price, stop_loss, take_profit, effective_order_type)
            if rr <= 0.0 and actual_monetary_risk_native > 0:
                rr = round(total_tp_money_native / actual_monetary_risk_native, 4)

            tier_min_rr = min_rr_override if min_rr_override is not None else float(getattr(tier_def, "min_reward_to_risk", 1.5))
            if rr < tier_min_rr - 0.01:
                rej = f"Reward:Risk ratio {rr:.2f} is below minimum {tier_min_rr:.1f} (SL: -{actual_monetary_risk_native:.2f} {native_curr}, TP: +{total_tp_money_native:.2f} {native_curr})"
                log_line = f"[SIZING] REJECTED | Bal: {unit_str} | Tier: {tier_name} | Reason: {rej}"
                return PositionSizeResult(
                    is_approved=False,
                    volume=final_volume,
                    monetary_risk=round(actual_monetary_risk_native, 2),
                    monetary_risk_native=round(actual_monetary_risk_native, 2),
                    monetary_risk_normalized=round(actual_monetary_risk_normalized, 2),
                    risk_percent_actual=round(actual_risk_pct, 3),
                    sl_points=round(sl_distance / symbol_info.point, 1),
                    sl_pips=round(sl_distance / (symbol_info.point * 10), 1),
                    loss_per_lot=round(total_loss_per_lot_native, 2),
                    margin_required=0.0,
                    reward_to_risk=round(rr, 2),
                    tp_money=round(total_tp_money, 2),
                    tier_name=tier_name,
                    target_risk_pct=target_pct,
                    ceiling_risk_pct=hard_ceiling,
                    min_balance_needed=round(min_balance_needed, 2),
                    raw_lots=round(raw_volume, 4),
                    log_line=log_line,
                    rejection_reason=rej,
                    is_cent_account=is_cent,
                    denomination_factor=denom_factor,
                    native_currency=native_curr,
                )

        # 8. Margin check
        estimated_margin = 0.0
        if MT5_AVAILABLE and mt5.terminal_info() is not None:
            try:
                calc_m = mt5.order_calc_margin(mt5_order_type, symbol_info.symbol, final_volume, entry_price)
                if calc_m is not None and calc_m > 0:
                    estimated_margin = float(calc_m)
            except Exception:
                pass

        if estimated_margin <= 0.0:
            if getattr(symbol_info, "margin_required", 0) > 0:
                margin_per_lot = symbol_info.margin_required
            else:
                contract_size = float(getattr(symbol_info, "contract_size", 100000.0) or 100000.0)
                price = entry_price if entry_price > 0 else 1.0
                leverage = float(getattr(account, "leverage", 100.0) or 100.0)
                if leverage <= 0:
                    leverage = 100.0
                margin_per_lot = (contract_size * price) / leverage
                if is_cent:
                    margin_per_lot = margin_per_lot * denom_factor
            estimated_margin = final_volume * margin_per_lot

        tier_margin_pct = tier_def.max_margin_percent_of_free
        max_free_margin = account.free_margin * (tier_margin_pct / 100.0)

        if estimated_margin > max_free_margin and max_free_margin > 0:
            # Margin-aware volume reduction in valid broker volume-step increments
            step = symbol_info.lot_step if symbol_info.lot_step > 0 else 0.01
            margin_per_unit = estimated_margin / final_volume if final_volume > 0 else 0.0
            reduced_vol = final_volume

            while (reduced_vol - step >= min_lot - 1e-9) and ((reduced_vol * margin_per_unit) > max_free_margin):
                reduced_vol = round(reduced_vol - step, 4)

            if (reduced_vol * margin_per_unit) <= max_free_margin + 1e-4 and reduced_vol >= min_lot - 1e-9:
                logger.info(
                    f"[SIZING] Margin-Aware Volume Adjustment: Reduced volume from {final_volume:.2f} to {reduced_vol:.2f} "
                    f"to fit margin budget ({reduced_vol * margin_per_unit:.2f} <= {max_free_margin:.2f} {native_curr})."
                )
                final_volume = reduced_vol
                estimated_margin = round(final_volume * margin_per_unit, 2)
                actual_loss_money_native = final_volume * base_loss_per_lot_native
                actual_loss_money_normalized = actual_loss_money_native / denom_factor if is_cent else actual_loss_money_native
                actual_risk_pct = (actual_loss_money_native / capital_base) * 100.0
                actual_monetary_risk_native = actual_loss_money_native + (final_volume * (spread_cost_per_lot_native + commission_per_lot_native))
                actual_monetary_risk_normalized = actual_monetary_risk_native / denom_factor if is_cent else actual_monetary_risk_native
            else:
                rej = f"INSUFFICIENT_MARGIN: Required margin {estimated_margin:.2f} {native_curr} exceeds {tier_margin_pct:.0f}% of free margin ({max_free_margin:.2f} / {account.free_margin:.2f} {native_curr})"
                log_line = f"[SIZING] REJECTED | Bal: {unit_str} | Tier: {tier_name} | Reason: {rej}"
                return PositionSizeResult(
                    is_approved=False,
                    volume=final_volume,
                    monetary_risk=round(actual_monetary_risk_native, 2),
                    monetary_risk_native=round(actual_monetary_risk_native, 2),
                    monetary_risk_normalized=round(actual_monetary_risk_normalized, 2),
                    risk_percent_actual=round(actual_risk_pct, 3),
                    sl_points=round(sl_distance / symbol_info.point, 1),
                    sl_pips=round(sl_distance / (symbol_info.point * 10), 1),
                    loss_per_lot=round(total_loss_per_lot_native, 2),
                    margin_required=round(estimated_margin, 2),
                    reward_to_risk=round(rr, 2),
                    tp_money=round(total_tp_money, 2),
                    tier_name=tier_name,
                    target_risk_pct=target_pct,
                    ceiling_risk_pct=hard_ceiling,
                    min_balance_needed=round(min_balance_needed, 2),
                    raw_lots=round(raw_volume, 4),
                    is_micro_exception=is_micro_exception,
                    log_line=log_line,
                    rejection_reason=rej,
                    is_cent_account=is_cent,
                    denomination_factor=denom_factor,
                    native_currency=native_curr,
                )

        # 9. Feasibility of $20 Net Profit Objective
        target_feasibility = None
        target_price_20 = None
        effective_order_type = order_type
        if effective_order_type is None:
            effective_order_type = OrderType.BUY if entry_price > stop_loss else OrderType.SELL

        eff_atr_m15 = atr_m15 if (atr_m15 is not None and atr_m15 > 0) else 0.0
        target_feasibility = TargetFeasibilityEngine.evaluate_target_feasibility(
            symbol_info=symbol_info,
            volume=final_volume,
            entry_price=entry_price,
            stop_loss=stop_loss,
            order_type=effective_order_type,
            account=account,
            atr_m15=eff_atr_m15,
            atr_h1=atr_h1,
            target_net_usd=target_net_usd,
        )
        if target_feasibility and target_feasibility.is_feasible:
            target_price_20 = target_feasibility.target_price

        # 10. Sizing Approval and Structured Audit Log Line
        log_line = (
            f"[SIZING] APPROVED | Bal: {unit_str} | Tier: {tier_name} | "
            f"TargetRisk: {target_pct:.2f}% | Loss/Lot: {total_loss_per_lot_native:.2f} {native_curr} | "
            f"RawLots: {raw_volume:.4f} | FinalLots: {final_volume:.2f} | "
            f"RealRisk: {actual_risk_pct:.2f}% ({actual_monetary_risk_native:,.2f} {native_curr}) | "
            f"MarginReq: {estimated_margin:.2f} {native_curr} | RR: {rr:.2f} | "
            f"$20_Feasible: {target_feasibility.is_feasible if target_feasibility else 'N/A'}"
        )
        logger.info(log_line)

        return PositionSizeResult(
            is_approved=True,
            volume=final_volume,
            monetary_risk=round(actual_monetary_risk_native, 2),
            monetary_risk_native=round(actual_monetary_risk_native, 2),
            monetary_risk_normalized=round(actual_monetary_risk_normalized, 2),
            risk_percent_actual=round(actual_risk_pct, 3),
            sl_points=round(sl_distance / symbol_info.point, 1),
            sl_pips=round(sl_distance / (symbol_info.point * 10), 1),
            loss_per_lot=round(total_loss_per_lot_native, 2),
            margin_required=round(estimated_margin, 2),
            reward_to_risk=round(rr, 2),
            tp_money=round(total_tp_money, 2),
            tier_name=tier_name,
            target_risk_pct=target_pct,
            ceiling_risk_pct=hard_ceiling,
            min_balance_needed=round(min_balance_needed, 2),
            raw_lots=round(raw_volume, 4),
            is_micro_exception=is_micro_exception,
            log_line=log_line,
            rejection_reason=None,
            target_price_20usd=target_price_20,
            feasibility=target_feasibility,
            is_cent_account=is_cent,
            denomination_factor=denom_factor,
            native_currency=native_curr,
        )
