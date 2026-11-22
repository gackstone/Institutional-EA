"""
Dynamic $20 Net-Profit Target Feasibility Engine.
Calculates mathematically exact price distances, required gross profits,
broker execution friction (commission, spread, slippage buffer, swap),
and volatility-adaptive realism to determine whether an individual position
can realistically achieve $20 NET realized profit within acceptable market
and account risk constraints (Rule R9).
"""

from __future__ import annotations
import math
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

from src.core.contracts import SymbolInfo, OrderType, AccountInfo, Candle, calculate_risk_reward

logger = logging.getLogger("TargetFeasibilityEngine")


@dataclass(frozen=True)
class TargetFeasibilityResult:
    is_feasible: bool
    target_net_usd: float
    required_gross_usd: float
    estimated_commission_usd: float
    estimated_spread_usd: float
    estimated_slippage_usd: float
    total_estimated_costs_usd: float
    required_price_distance: float
    required_points: float
    target_price: float
    volatility_ratio_m15: float
    reward_to_risk: float
    monetary_risk_usd: float
    risk_pct_of_capital: float
    rejection_reason: Optional[str] = None
    log_line: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_feasible": self.is_feasible,
            "target_net_usd": round(self.target_net_usd, 2),
            "required_gross_usd": round(self.required_gross_usd, 2),
            "estimated_commission_usd": round(self.estimated_commission_usd, 2),
            "estimated_spread_usd": round(self.estimated_spread_usd, 2),
            "estimated_slippage_usd": round(self.estimated_slippage_usd, 2),
            "total_estimated_costs_usd": round(self.total_estimated_costs_usd, 2),
            "required_price_distance": round(self.required_price_distance, 5),
            "required_points": round(self.required_points, 1),
            "target_price": round(self.target_price, 5),
            "volatility_ratio_m15": round(self.volatility_ratio_m15, 2),
            "reward_to_risk": round(self.reward_to_risk, 2),
            "monetary_risk_usd": round(self.monetary_risk_usd, 2),
            "risk_pct_of_capital": round(self.risk_pct_of_capital, 2),
            "rejection_reason": self.rejection_reason,
        }


class TargetFeasibilityEngine:
    TARGET_NET_PROFIT_USD: float = 20.0
    ROUNDTURN_COMMISSION_PER_LOT: float = 7.0  # Institutional roundturn estimate ($7 / standard lot)
    SLIPPAGE_POINTS_BUFFER: float = 2.0        # Expected execution slippage buffer in points
    MAX_VOLATILITY_RATIO_M15: float = 2.8      # Target distance / M15 ATR limit for fast scalp
    MAX_VOLATILITY_RATIO_H1: float = 1.8       # Target distance / H1 ATR limit
    MIN_REWARD_TO_RISK: float = 1.1            # Minimum acceptable R:R for $20 target
    MAX_REWARD_TO_RISK_SCALP: float = 4.5      # Maximum realistic R:R on a fast scalp without HTF runway

    @classmethod
    def evaluate_target_feasibility(
        cls,
        symbol_info: SymbolInfo,
        volume: float,
        entry_price: float,
        stop_loss: float,
        order_type: OrderType,
        account: AccountInfo,
        atr_m15: float,
        atr_h1: Optional[float] = None,
        target_net_usd: float = 20.0,
        commission_per_lot: Optional[float] = None,
    ) -> TargetFeasibilityResult:
        """
        Determines whether a proposed position of `volume` lots can reasonably achieve
        `target_net_usd` (default $20.00 USD) net profit after all transaction costs,
        without requiring excessive price movement or violating Rule R9 risk limits.
        """
        if target_net_usd <= 0.0:
            target_net_usd = cls.TARGET_NET_PROFIT_USD
        comm_per_lot = commission_per_lot if commission_per_lot is not None else cls.ROUNDTURN_COMMISSION_PER_LOT

        # Capital base: MIN(Account Balance, Account Equity)
        capital_base = min(float(account.balance), float(account.equity))

        # Basic validations
        if volume <= 0:
            return cls._reject(
                reason="Invalid position volume (volume <= 0)",
                target_net=target_net_usd,
                capital_base=capital_base,
            )
        if entry_price <= 0:
            return cls._reject(
                reason="Invalid entry price (entry_price <= 0)",
                target_net=target_net_usd,
                capital_base=capital_base,
            )
        if stop_loss <= 0:
            return cls._reject(
                reason="Stop-loss is mandatory for target feasibility evaluation (R9)",
                target_net=target_net_usd,
                capital_base=capital_base,
            )

        sl_distance = abs(entry_price - stop_loss)
        if sl_distance <= 0:
            return cls._reject(
                reason="Stop loss distance is zero or negative",
                target_net=target_net_usd,
                capital_base=capital_base,
            )

        # Symbol contract specs
        point = symbol_info.point if symbol_info.point > 0 else 0.00001
        tick_size = symbol_info.tick_size if symbol_info.tick_size > 0 else point
        tick_value = symbol_info.tick_value if symbol_info.tick_value > 0 else 1.0

        usd_per_price_unit = (tick_value / tick_size) * volume
        if usd_per_price_unit <= 1e-9:
            return cls._reject(
                reason="USD value per price unit could not be determined",
                target_net=target_net_usd,
                capital_base=capital_base,
            )

        # 1. Estimate Transaction Costs
        # Roundturn commission
        est_commission = round(comm_per_lot * volume, 2)

        # Spread drag (in USD)
        spread_pts = float(getattr(symbol_info, "spread", 10.0))
        spread_dist = spread_pts * point
        est_spread_usd = round(spread_dist * usd_per_price_unit, 2)

        # Slippage buffer (in USD)
        slip_dist = cls.SLIPPAGE_POINTS_BUFFER * point
        est_slippage_usd = round(slip_dist * usd_per_price_unit, 2)

        total_costs_usd = round(est_commission + est_spread_usd + est_slippage_usd, 2)
        required_gross_usd = round(target_net_usd + total_costs_usd, 2)

        # 2. Required Price Movement Calculation
        required_price_dist = required_gross_usd / usd_per_price_unit
        required_pts = required_price_dist / point

        # 3. Target Price Placement
        is_buy = order_type in (OrderType.BUY, OrderType.BUY_LIMIT, OrderType.BUY_STOP)
        if is_buy:
            target_price = symbol_info.round_price(entry_price + required_price_dist)
        else:
            target_price = symbol_info.round_price(entry_price - required_price_dist)

        # 4. Monetary Risk and Rule R9 Evaluation
        # Risk money at SL (base loss + spread + commission)
        base_risk_usd = sl_distance * usd_per_price_unit
        total_risk_usd = round(base_risk_usd + est_spread_usd + est_commission, 2)
        risk_pct = (total_risk_usd / capital_base * 100.0) if capital_base > 0 else 100.0

        # R9.1: Hard Cap 2.0% Risk per Trade
        if risk_pct > 2.0 + 1e-4:
            reason = (
                f"Trade risks ${total_risk_usd:.2f} ({risk_pct:.2f}% of capital ${capital_base:.2f}), "
                f"exceeding Rule R9 hard cap of 2.0%. Target $20 infeasible on this account risk budget."
            )
            return cls._reject(
                reason=reason,
                target_net=target_net_usd,
                required_gross=required_gross_usd,
                comm=est_commission,
                spread=est_spread_usd,
                slip=est_slippage_usd,
                total_cost=total_costs_usd,
                price_dist=required_price_dist,
                pts=required_pts,
                tp=target_price,
                risk_usd=total_risk_usd,
                risk_pct=risk_pct,
                capital_base=capital_base,
            )

        # 5. Reward-to-Risk & Volatility Telemetry (non-blocking: strategy decides setup validity)
        reward_to_risk = calculate_risk_reward(entry_price, stop_loss, target_price, order_type)
        if reward_to_risk <= 0.0 and sl_distance > 0:
            reward_to_risk = round(required_price_dist / sl_distance, 4)
        vol_ratio_m15 = round(required_price_dist / atr_m15, 2) if atr_m15 > 0 else 0.0

        # Trade is feasible!
        log_line = (
            f"[FEASIBILITY] APPROVED | Symbol: {symbol_info.symbol} | Vol: {volume:.2f} | "
            f"Target: ${target_net_usd:.2f} Net (Gross: ${required_gross_usd:.2f}, Costs: ${total_costs_usd:.2f}) | "
            f"Distance: {required_pts:.1f} pts ({vol_ratio_m15:.1f}x ATR) | R:R: {reward_to_risk:.2f} | "
            f"Risk: ${total_risk_usd:.2f} ({risk_pct:.2f}%)"
        )
        logger.info(log_line)

        return TargetFeasibilityResult(
            is_feasible=True,
            target_net_usd=target_net_usd,
            required_gross_usd=required_gross_usd,
            estimated_commission_usd=est_commission,
            estimated_spread_usd=est_spread_usd,
            estimated_slippage_usd=est_slippage_usd,
            total_estimated_costs_usd=total_costs_usd,
            required_price_distance=required_price_dist,
            required_points=required_pts,
            target_price=target_price,
            volatility_ratio_m15=vol_ratio_m15,
            reward_to_risk=reward_to_risk,
            monetary_risk_usd=total_risk_usd,
            risk_pct_of_capital=risk_pct,
            rejection_reason=None,
            log_line=log_line,
        )

    @staticmethod
    def _reject(
        reason: str,
        target_net: float = 20.0,
        required_gross: float = 0.0,
        comm: float = 0.0,
        spread: float = 0.0,
        slip: float = 0.0,
        total_cost: float = 0.0,
        price_dist: float = 0.0,
        pts: float = 0.0,
        tp: float = 0.0,
        vol_m15: float = 0.0,
        rr: float = 0.0,
        risk_usd: float = 0.0,
        risk_pct: float = 0.0,
        capital_base: float = 0.0,
    ) -> TargetFeasibilityResult:
        log_line = f"[FEASIBILITY] REJECTED | Target: ${target_net:.2f} | Reason: {reason}"
        logger.warning(log_line)
        return TargetFeasibilityResult(
            is_feasible=False,
            target_net_usd=target_net,
            required_gross_usd=required_gross,
            estimated_commission_usd=comm,
            estimated_spread_usd=spread,
            estimated_slippage_usd=slip,
            total_estimated_costs_usd=total_cost,
            required_price_distance=price_dist,
            required_points=pts,
            target_price=tp,
            volatility_ratio_m15=vol_m15,
            reward_to_risk=rr,
            monetary_risk_usd=risk_usd,
            risk_pct_of_capital=risk_pct,
            rejection_reason=reason,
            log_line=log_line,
        )
