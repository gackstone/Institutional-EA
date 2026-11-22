"""
Phase 4: Smart Dynamic Risk-Based Position Sizing Engine.
Supports:
1. Dynamic Risk-Budget Sizing (`calculate_risk_based_lot`):
   - Configurable risk profiles: CONSERVATIVE (0.10%), STANDARD (0.25%), AGGRESSIVE_DEMO (0.50%)
   - Exact monetary loss calculation using SL distance, tick size, tick value, contract size,
     expected slippage, spread, and commission costs.
   - Consumes remaining basket risk budget and enforces account-wide open risk cap.
   - Rejects trade if broker minimum lot exceeds permitted risk budget.
2. Balance-Step Sizing (`calculate_lot`):
   - Preserved for 100% backward compatibility with v1/v2 test suites.
Strictly prohibits martingale, grid recovery, or loss-chasing escalation.
"""

from __future__ import annotations
from dataclasses import dataclass
import logging
import math
from typing import Optional

from src.scalper.config import InstrumentScalperConfig, LotSizingConfig, RISK_PROFILE_PCT_MAP
from src.scalper.symbol_resolver import ResolvedSymbolSpec

logger = logging.getLogger("SymbolLotSizing")


@dataclass
class SizingCalculationResult:
    lot: float
    raw_lot: float
    is_safe: bool
    rejection_reason: Optional[str] = None
    account_balance: float = 0.0
    account_equity: float = 0.0
    broker_min_lot: float = 0.01
    broker_max_lot: float = 100.0
    broker_lot_step: float = 0.01
    risk_profile: str = "STANDARD"
    risk_budget_usd: float = 0.0
    remaining_basket_risk_usd: float = 0.0
    worst_case_loss_per_lot_usd: float = 0.0
    worst_case_loss_usd: float = 0.0


class SymbolLotSizingEngine:
    def __init__(self, default_config: Optional[LotSizingConfig] = None):
        self.default_config = default_config or LotSizingConfig()

    @staticmethod
    def compute_worst_case_loss_per_lot(
        sl_points: float,
        spec: Optional[ResolvedSymbolSpec] = None,
        expected_slippage_points: float = 10.0,
        spread_points: float = 20.0,
        commission_per_lot_usd: float = 7.0,
    ) -> float:
        """
        Computes exact worst-case monetary loss for 1.00 standard lot including:
        - Stop-loss distance
        - Spread cost
        - Expected slippage
        - Round-turn commission
        """
        pt = spec.point if spec and spec.point > 0 else 0.01
        tick_sz = spec.tick_size if spec and spec.tick_size > 0 else pt
        tick_val = spec.tick_value if spec and spec.tick_value > 0 else 1.0
        contract_sz = spec.contract_size if spec and spec.contract_size > 0 else 100.0

        # Monetary value per point per 1.0 lot:
        # On MT5, if tick_value == 1.0 and tick_size == 0.01, check if contract_size scales it
        # For XAUUSD (100 oz, point=0.01): 1 point ($0.01) on 1.0 lot (100 oz) = $1.00
        # For BTCUSD (1 BTC, point=0.01): 1 point ($0.01) on 1.0 lot (1 BTC) = $0.01
        if spec and "BTC" in spec.canonical.upper():
            value_per_point_1lot = pt * contract_sz * tick_val
        else:
            value_per_point_1lot = (pt / tick_sz) * tick_val * (contract_sz / 100.0 if contract_sz > 0 else 1.0)
            if value_per_point_1lot <= 0:
                value_per_point_1lot = 1.0

        total_adverse_points = max(1.0, sl_points) + max(0.0, spread_points) + max(0.0, expected_slippage_points)
        loss_1lot = (total_adverse_points * value_per_point_1lot) + max(0.0, commission_per_lot_usd)
        return round(max(0.01, loss_1lot), 4)

    def calculate_risk_based_lot(
        self,
        account_equity: float,
        sl_points: float,
        spec: Optional[ResolvedSymbolSpec] = None,
        instrument_config: Optional[InstrumentScalperConfig] = None,
        risk_profile: str = "STANDARD",
        custom_risk_pct: Optional[float] = None,
        planned_positions_in_basket: int = 1,
        already_used_basket_risk_usd: float = 0.0,
        current_account_open_risk_usd: float = 0.0,
        max_account_open_risk_pct: float = 2.0,
        expected_slippage_points: float = 10.0,
        spread_points: float = 20.0,
    ) -> SizingCalculationResult:
        """
        Phase 4 Dynamic Risk-Based Position Sizing:
        - Uses account_equity, risk_profile (CONSERVATIVE=0.10%, STANDARD=0.25%, AGGRESSIVE_DEMO=0.50%),
          stop-loss distance, contract specs, spread, slippage, and commission.
        - Consumes remaining basket risk budget across multiple positions.
        - Enforces account-wide open risk ceiling.
        - Rejects trade if broker min_lot exceeds permitted risk budget.
        """
        if account_equity <= 0:
            return SizingCalculationResult(
                lot=0.0,
                raw_lot=0.0,
                is_safe=False,
                rejection_reason=f"Account equity is zero or negative: ${account_equity:.2f}",
                account_equity=account_equity,
            )

        prof_key = (instrument_config.risk_profile if instrument_config else risk_profile).upper()
        basket_risk_pct = (
            custom_risk_pct
            if custom_risk_pct is not None
            else (
                instrument_config.max_basket_risk_pct
                if instrument_config and instrument_config.max_basket_risk_pct > 0
                else RISK_PROFILE_PCT_MAP.get(prof_key, 0.25)
            )
        )

        total_basket_budget_usd = account_equity * (basket_risk_pct / 100.0)
        remaining_basket_budget_usd = max(0.0, total_basket_budget_usd - max(0.0, already_used_basket_risk_usd))

        max_account_risk_usd = account_equity * (max_account_open_risk_pct / 100.0)
        remaining_account_budget_usd = max(0.0, max_account_risk_usd - max(0.0, current_account_open_risk_usd))

        effective_budget_usd = min(remaining_basket_budget_usd, remaining_account_budget_usd)
        slots = max(1, planned_positions_in_basket)
        per_order_budget_usd = effective_budget_usd / slots

        comm_per_lot = instrument_config.commission_per_lot_usd if instrument_config else 7.0
        loss_per_1lot = self.compute_worst_case_loss_per_lot(
            sl_points=sl_points,
            spec=spec,
            expected_slippage_points=expected_slippage_points,
            spread_points=spread_points,
            commission_per_lot_usd=comm_per_lot,
        )

        b_min = spec.min_lot if spec else (instrument_config.min_lot if instrument_config else 0.01)
        b_max = spec.max_lot if spec else 100.0
        b_step = spec.lot_step if spec and spec.lot_step > 0 else 0.01
        cfg_max = instrument_config.max_lot if instrument_config else self.default_config.max_lot_override
        effective_max = min(b_max, cfg_max)

        min_lot_loss_usd = round(b_min * loss_per_1lot, 4)

        # Reject if minimum lot exceeds remaining basket or account risk budget
        if min_lot_loss_usd > effective_budget_usd + 1e-6:
            return SizingCalculationResult(
                lot=0.0,
                raw_lot=0.0,
                is_safe=False,
                rejection_reason=(
                    f"MIN_LOT_EXCEEDS_PERMITTED_RISK: Min lot {b_min} risks ${min_lot_loss_usd:.2f} > "
                    f"remaining risk budget ${effective_budget_usd:.2f}"
                ),
                account_balance=account_equity,
                account_equity=account_equity,
                broker_min_lot=b_min,
                broker_max_lot=b_max,
                broker_lot_step=b_step,
                risk_profile=prof_key,
                risk_budget_usd=round(total_basket_budget_usd, 4),
                remaining_basket_risk_usd=round(effective_budget_usd, 4),
                worst_case_loss_per_lot_usd=loss_per_1lot,
                worst_case_loss_usd=min_lot_loss_usd,
            )

        raw_lot = per_order_budget_usd / loss_per_1lot
        if raw_lot < b_min:
            # Can still fit 1 min_lot inside effective_budget_usd
            raw_lot = b_min

        clamped = min(effective_max, max(b_min, raw_lot))
        steps_count = math.floor((clamped - b_min + 1e-9) / b_step)
        normalized_lot = round(b_min + steps_count * b_step, 4)
        normalized_lot = max(b_min, min(effective_max, normalized_lot))

        worst_case_loss_usd = round(normalized_lot * loss_per_1lot, 4)
        if worst_case_loss_usd > effective_budget_usd + 1e-6:
            return SizingCalculationResult(
                lot=0.0,
                raw_lot=round(raw_lot, 4),
                is_safe=False,
                rejection_reason=(
                    f"WORST_CASE_LOSS_EXCEEDS_BUDGET: ${worst_case_loss_usd:.2f} > ${effective_budget_usd:.2f}"
                ),
                account_balance=account_equity,
                account_equity=account_equity,
                broker_min_lot=b_min,
                broker_max_lot=b_max,
                broker_lot_step=b_step,
                risk_profile=prof_key,
                risk_budget_usd=round(total_basket_budget_usd, 4),
                remaining_basket_risk_usd=round(effective_budget_usd, 4),
                worst_case_loss_per_lot_usd=loss_per_1lot,
                worst_case_loss_usd=worst_case_loss_usd,
            )

        return SizingCalculationResult(
            lot=normalized_lot,
            raw_lot=round(raw_lot, 4),
            is_safe=True,
            rejection_reason=None,
            account_balance=account_equity,
            account_equity=account_equity,
            broker_min_lot=b_min,
            broker_max_lot=b_max,
            broker_lot_step=b_step,
            risk_profile=prof_key,
            risk_budget_usd=round(total_basket_budget_usd, 4),
            remaining_basket_risk_usd=round(effective_budget_usd - worst_case_loss_usd, 4),
            worst_case_loss_per_lot_usd=loss_per_1lot,
            worst_case_loss_usd=worst_case_loss_usd,
        )

    def calculate_lot(
        self,
        balance: float,
        spec: Optional[ResolvedSymbolSpec] = None,
        max_lot_override: Optional[float] = None,
        instrument_config: Optional[InstrumentScalperConfig] = None,
    ) -> SizingCalculationResult:
        """
        Calculates balance-based volume according to:
        lot = floor(balance / LOT_STEP_BALANCE) * 0.01
        Clamped to broker min/max/step.
        """
        if balance <= 0:
            return SizingCalculationResult(
                lot=0.0,
                raw_lot=0.0,
                is_safe=False,
                rejection_reason=f"Account balance is zero or negative: ${balance:.2f}",
                account_balance=balance,
                account_equity=balance,
            )

        if instrument_config:
            step_bal = instrument_config.lot_step_balance if instrument_config.lot_step_balance > 0 else 50.0
            min_allowed = instrument_config.min_lot
            configured_max = max_lot_override or instrument_config.max_lot
            micro_floor = instrument_config.micro_account_min_lot
            sl_pts = instrument_config.sl_points
            comm = instrument_config.commission_per_lot_usd
        else:
            step_bal = self.default_config.lot_step_balance if self.default_config.lot_step_balance > 0 else 50.0
            min_allowed = self.default_config.min_lot_override
            configured_max = max_lot_override or self.default_config.max_lot_override
            micro_floor = self.default_config.micro_account_min_lot
            sl_pts = 300.0
            comm = 7.0

        b_min = spec.min_lot if spec else 0.01
        b_max = spec.max_lot if spec else 100.0
        b_step = spec.lot_step if spec and spec.lot_step > 0 else 0.01

        multiplier = math.floor(balance / step_bal)
        raw_lot = multiplier * 0.01

        floor_lot = max(min_allowed, b_min, micro_floor)
        candidate_lot = max(floor_lot, raw_lot)

        effective_max = min(configured_max, b_max)
        if candidate_lot > effective_max:
            candidate_lot = effective_max

        steps_count = math.floor((candidate_lot - b_min + 1e-9) / b_step)
        normalized_lot = b_min + (steps_count * b_step)
        normalized_lot = round(normalized_lot, 4)

        if normalized_lot < b_min:
            normalized_lot = b_min
        if normalized_lot > effective_max:
            normalized_lot = effective_max

        loss_1lot = self.compute_worst_case_loss_per_lot(sl_pts, spec=spec, commission_per_lot_usd=comm)
        wc_loss = round(normalized_lot * loss_1lot, 4)

        return SizingCalculationResult(
            lot=normalized_lot,
            raw_lot=round(raw_lot, 4),
            is_safe=True,
            rejection_reason=None,
            account_balance=balance,
            account_equity=balance,
            broker_min_lot=b_min,
            broker_max_lot=b_max,
            broker_lot_step=b_step,
            worst_case_loss_per_lot_usd=loss_1lot,
            worst_case_loss_usd=wc_loss,
        )


# Backward-compatible Gold lot sizing engine alias
class GoldLotSizingEngine(SymbolLotSizingEngine):
    pass
