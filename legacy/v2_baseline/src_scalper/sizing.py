"""
Dynamic Balance-Based Lot Sizing for Dual-Market Scalping.
Calculates volume strictly from current account balance and broker specifications:
lot = floor(balance / LOT_STEP_BALANCE) * 0.01,
clamped to broker minimum, maximum, and volume step.
Supports instrument-specific parameters for GOLD and BTCUSD.
Martingale, progressive loss recovery, and averaging down are strictly prohibited.
"""

from __future__ import annotations
import math
import logging
from dataclasses import dataclass
from typing import Optional

from src.scalper.config import LotSizingConfig, InstrumentScalperConfig
from src.scalper.symbol_resolver import ResolvedSymbolSpec

logger = logging.getLogger("SymbolLotSizing")


@dataclass
class SizingCalculationResult:
    lot: float
    raw_lot: float
    is_safe: bool
    rejection_reason: Optional[str] = None
    account_balance: float = 0.0
    broker_min_lot: float = 0.01
    broker_max_lot: float = 100.0
    broker_lot_step: float = 0.01


class SymbolLotSizingEngine:
    def __init__(self, default_config: Optional[LotSizingConfig] = None):
        self.default_config = default_config or LotSizingConfig()

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
            )

        if instrument_config:
            step_bal = instrument_config.lot_step_balance if instrument_config.lot_step_balance > 0 else 50.0
            min_allowed = instrument_config.min_lot
            configured_max = max_lot_override or instrument_config.max_lot
            micro_floor = instrument_config.micro_account_min_lot
        else:
            step_bal = self.default_config.lot_step_balance if self.default_config.lot_step_balance > 0 else 50.0
            min_allowed = self.default_config.min_lot_override
            configured_max = max_lot_override or self.default_config.max_lot_override
            micro_floor = self.default_config.micro_account_min_lot

        # Broker specs
        b_min = spec.min_lot if spec else 0.01
        b_max = spec.max_lot if spec else 100.0
        b_step = spec.lot_step if spec and spec.lot_step > 0 else 0.01

        # Base formula: floor(balance / LOT_STEP_BALANCE) * 0.01
        multiplier = math.floor(balance / step_bal)
        raw_lot = multiplier * 0.01

        # Apply floor: micro accounts get minimum lot floor
        floor_lot = max(min_allowed, b_min, micro_floor)
        candidate_lot = max(floor_lot, raw_lot)

        # Upper ceiling clamp
        effective_max = min(configured_max, b_max)
        if candidate_lot > effective_max:
            candidate_lot = effective_max

        # Broker step normalization (downward quantization to avoid over-sizing)
        steps_count = math.floor((candidate_lot - b_min + 1e-9) / b_step)
        normalized_lot = b_min + (steps_count * b_step)
        normalized_lot = round(normalized_lot, 4)

        # Final safety bounds check
        if normalized_lot < b_min:
            normalized_lot = b_min
        if normalized_lot > effective_max:
            normalized_lot = effective_max

        return SizingCalculationResult(
            lot=normalized_lot,
            raw_lot=raw_lot,
            is_safe=True,
            account_balance=balance,
            broker_min_lot=b_min,
            broker_max_lot=b_max,
            broker_lot_step=b_step,
        )


# Backward-compatible Gold sizing alias
class GoldLotSizingEngine(SymbolLotSizingEngine):
    pass
