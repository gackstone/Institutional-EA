"""
Phase 8: Controlled Rapid Direction Reversal Engine.
Transitions from BUY to SELL or SELL to BUY when market conditions genuinely change.
Requires:
1. Confirmed opposite directional signal above quality threshold
2. Existing basket exposure & PnL assessment (never closes strong winning trades prematurely on minor noise)
3. Spread and slippage validation
4. Account risk approval
5. Complete closure & reconciliation of previous directional exposure before opening opposite orders
6. Configurable reversal cooldown
Records structured ReversalRecord audit trail.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import time
from typing import Any, Dict, List, Optional

from src.scalper.basket import ScalperBasket
from src.scalper.config import InstrumentScalperConfig
from src.scalper.strategy_gold import StrategySignalEvaluation


@dataclass
class ReversalRecord:
    symbol_key: str
    previous_direction: str
    new_direction: str
    reversal_reason: str
    closed_positions: List[int]
    realized_pnl_usd: float
    remaining_exposure_lots: float
    new_order_details: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


@dataclass
class ReversalEvaluation:
    approved: bool
    reason: str
    previous_direction: str = ""
    new_direction: str = ""


class DirectionReversalEngine:
    """
    Governs controlled directional flipping without holding simultaneous accidental opposing exposure.
    """

    def __init__(self, min_reversal_quality: float = 0.68):
        self.min_reversal_quality = min_reversal_quality
        self.last_reversal_time: Dict[str, float] = {}
        self.reversal_history: List[ReversalRecord] = []

    def evaluate_reversal(
        self,
        symbol_key: str,
        active_basket: Optional[ScalperBasket],
        opposite_signal: StrategySignalEvaluation,
        instrument_config: InstrumentScalperConfig,
        current_spread_points: float,
        estimated_slippage_points: float,
        risk_approved: bool,
        tick_momentum: float = 0.0,
        now_override: Optional[float] = None,
    ) -> ReversalEvaluation:
        sym_k = symbol_key.upper()
        now_ts = now_override if now_override is not None else time.time()

        if active_basket is None or active_basket.position_count == 0:
            return ReversalEvaluation(approved=False, reason="NO_ACTIVE_BASKET_TO_REVERSE")

        prev_dir = active_basket.direction.upper()
        new_dir = opposite_signal.direction.upper()
        if prev_dir == new_dir:
            return ReversalEvaluation(approved=False, reason="SIGNAL_SAME_DIRECTION")

        if not opposite_signal.is_valid or opposite_signal.quality_score < self.min_reversal_quality:
            return ReversalEvaluation(
                approved=False,
                reason=f"UNCONFIRMED_OPPOSITE_SIGNAL: quality {opposite_signal.quality_score:.2f} < {self.min_reversal_quality:.2f}",
                previous_direction=prev_dir,
                new_direction=new_dir,
            )

        # Cooldown check
        last_rev = self.last_reversal_time.get(sym_k, 0.0)
        if now_ts - last_rev < instrument_config.reversal_cooldown_seconds:
            rem = instrument_config.reversal_cooldown_seconds - (now_ts - last_rev)
            return ReversalEvaluation(
                approved=False,
                reason=f"REVERSAL_COOLDOWN_ACTIVE: {rem:.1f}s remaining",
                previous_direction=prev_dir,
                new_direction=new_dir,
            )

        # Do not close strong winning trades prematurely unless momentum has genuinely flipped against the basket
        dir_sign = 1.0 if prev_dir == "BUY" else -1.0
        if active_basket.net_floating_profit >= active_basket.basket_tp_usd * 0.65 and (tick_momentum * dir_sign) > -0.25:
            return ReversalEvaluation(
                approved=False,
                reason="PROTECT_WINNING_BASKET: Strong unrealized profit with intact momentum",
                previous_direction=prev_dir,
                new_direction=new_dir,
            )

        # Spread and slippage validation
        if current_spread_points > instrument_config.spread_max_points:
            return ReversalEvaluation(
                approved=False,
                reason=f"REVERSAL_SPREAD_REJECTED: {current_spread_points:.1f} > {instrument_config.spread_max_points:.1f}",
                previous_direction=prev_dir,
                new_direction=new_dir,
            )

        if estimated_slippage_points > instrument_config.max_slippage:
            return ReversalEvaluation(
                approved=False,
                reason=f"REVERSAL_SLIPPAGE_REJECTED: {estimated_slippage_points:.1f} > {instrument_config.max_slippage:.1f}",
                previous_direction=prev_dir,
                new_direction=new_dir,
            )

        if not risk_approved:
            return ReversalEvaluation(
                approved=False,
                reason="REVERSAL_RISK_NOT_APPROVED",
                previous_direction=prev_dir,
                new_direction=new_dir,
            )

        return ReversalEvaluation(
            approved=True,
            reason=f"CONFIRMED_REVERSAL: {prev_dir}->{new_dir} | {opposite_signal.rationale}",
            previous_direction=prev_dir,
            new_direction=new_dir,
        )

    def record_completed_reversal(
        self,
        symbol_key: str,
        previous_direction: str,
        new_direction: str,
        reason: str,
        closed_positions: List[int],
        realized_pnl_usd: float,
        remaining_exposure_lots: float,
        new_order_details: List[Dict[str, Any]],
        now_override: Optional[float] = None,
    ) -> ReversalRecord:
        sym_k = symbol_key.upper()
        now_ts = now_override if now_override is not None else time.time()
        self.last_reversal_time[sym_k] = now_ts
        rec = ReversalRecord(
            symbol_key=sym_k,
            previous_direction=previous_direction,
            new_direction=new_direction,
            reversal_reason=reason,
            closed_positions=list(closed_positions),
            realized_pnl_usd=round(realized_pnl_usd, 2),
            remaining_exposure_lots=round(remaining_exposure_lots, 4),
            new_order_details=list(new_order_details),
            timestamp=now_ts,
        )
        self.reversal_history.append(rec)
        return rec
