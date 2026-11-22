"""
Phase 3: Rapid Multi-Position Scalping Entry Engine.
Supports 5 configurable entry styles:
A. SINGLE_ENTRY — One position per qualified signal.
B. CONTROLLED_MULTI_ENTRY — Several independently justified positions during a strong directional opportunity.
C. PYRAMID_ENTRY — Add exposure only when existing basket is profitable and additional risk fits inside the original basket risk budget.
D. RE_ENTRY — Enter again after a basket or position closes, only when a fresh signal appears.
E. REVERSAL — Close or reduce old directional exposure and establish opposite-direction exposure after confirmation.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import time
import uuid
from typing import List, Optional

from src.scalper.basket import ScalperBasket
from src.scalper.config import InstrumentScalperConfig
from src.scalper.strategy_gold import StrategySignalEvaluation


class EntryMode(str, Enum):
    SINGLE_ENTRY = "single_entry"
    CONTROLLED_MULTI_ENTRY = "controlled_multi_entry"
    PYRAMID_ENTRY = "pyramid_entry"
    RE_ENTRY = "re_entry"
    REVERSAL = "reversal"


@dataclass
class PlannedOrderEntry:
    entry_id: str
    symbol_key: str
    direction: str
    slot_index: int
    entry_mode: str
    entry_type: str
    reason: str
    quality_score: float
    created_at: float = field(default_factory=time.time)


@dataclass
class EntryPlanDecision:
    allowed: bool
    entry_mode: str
    planned_entries: List[PlannedOrderEntry] = field(default_factory=list)
    requires_reversal_first: bool = False
    rejection_reason: str = ""


class MultiPositionEntryEngine:
    """
    Evaluates signal, active basket state, cooldowns, and fresh-signal requirements
    to generate uniquely identified, justified position entries.
    """

    def __init__(self):
        self._last_entry_time: dict[str, float] = {}
        self._last_closed_tick_seq: dict[str, int] = {}
        self._last_entry_tick_seq: dict[str, int] = {}

    def notify_basket_closed(self, symbol_key: str, tick_seq: int) -> None:
        self._last_closed_tick_seq[symbol_key.upper()] = tick_seq

    def plan_entries(
        self,
        symbol_key: str,
        signal: StrategySignalEvaluation,
        instrument_config: InstrumentScalperConfig,
        active_basket: Optional[ScalperBasket],
        tick_seq: int = 0,
        remaining_basket_risk_usd: float = 100.0,
        risk_per_min_lot_usd: float = 0.50,
        now_override: Optional[float] = None,
    ) -> EntryPlanDecision:
        sym_k = symbol_key.upper()
        now_ts = now_override if now_override is not None else time.time()
        mode = instrument_config.entry_mode.lower()

        if not signal.is_valid:
            return EntryPlanDecision(
                allowed=False,
                entry_mode=mode,
                rejection_reason=signal.rejection_reason or "INVALID_SIGNAL",
            )

        # Prevent opening repeated positions merely because the same tick was re-evaluated
        if tick_seq > 0 and self._last_entry_tick_seq.get(sym_k, -1) == tick_seq:
            return EntryPlanDecision(
                allowed=False,
                entry_mode=mode,
                rejection_reason=f"DUPLICATE_TICK_SEQ_{tick_seq}",
            )

        # Case 1: Active basket already exists on this symbol
        if active_basket is not None and active_basket.position_count > 0:
            # Check for opposite direction -> Reversal candidate
            if active_basket.direction != signal.direction:
                if mode == EntryMode.REVERSAL.value or signal.quality_score >= 0.70:
                    entry_id = f"ENT_{sym_k}_{uuid.uuid4().hex[:8].upper()}"
                    return EntryPlanDecision(
                        allowed=True,
                        entry_mode=EntryMode.REVERSAL.value,
                        requires_reversal_first=True,
                        planned_entries=[
                            PlannedOrderEntry(
                                entry_id=entry_id,
                                symbol_key=sym_k,
                                direction=signal.direction,
                                slot_index=0,
                                entry_mode=EntryMode.REVERSAL.value,
                                entry_type=signal.entry_type,
                                reason=f"REVERSAL: {active_basket.direction}->{signal.direction} ({signal.rationale})",
                                quality_score=signal.quality_score,
                                created_at=now_ts,
                            )
                        ],
                    )
                return EntryPlanDecision(
                    allowed=False,
                    entry_mode=mode,
                    rejection_reason="OPPOSITE_SIGNAL_BELOW_REVERSAL_THRESHOLD",
                )

            # Same direction with active basket -> only PYRAMID_ENTRY allowed if basket is profitable and has capacity
            if mode == EntryMode.PYRAMID_ENTRY.value:
                remaining_slots = instrument_config.max_basket_size - active_basket.position_count
                if remaining_slots <= 0:
                    return EntryPlanDecision(
                        allowed=False,
                        entry_mode=mode,
                        rejection_reason="BASKET_CAPACITY_FULL",
                    )
                if active_basket.net_floating_profit <= 0.0:
                    return EntryPlanDecision(
                        allowed=False,
                        entry_mode=mode,
                        rejection_reason="PYRAMID_REQUIRES_PROFITABLE_BASKET",
                    )
                if remaining_basket_risk_usd < risk_per_min_lot_usd:
                    return EntryPlanDecision(
                        allowed=False,
                        entry_mode=mode,
                        rejection_reason="PYRAMID_RISK_BUDGET_EXHAUSTED",
                    )
                slot_idx = active_basket.position_count
                entry_id = f"ENT_{sym_k}_{uuid.uuid4().hex[:8].upper()}"
                self._last_entry_tick_seq[sym_k] = tick_seq
                self._last_entry_time[sym_k] = now_ts
                return EntryPlanDecision(
                    allowed=True,
                    entry_mode=EntryMode.PYRAMID_ENTRY.value,
                    planned_entries=[
                        PlannedOrderEntry(
                            entry_id=entry_id,
                            symbol_key=sym_k,
                            direction=signal.direction,
                            slot_index=slot_idx,
                            entry_mode=EntryMode.PYRAMID_ENTRY.value,
                            entry_type=signal.entry_type,
                            reason=f"PYRAMID_ADD_SLOT_{slot_idx+1}: Basket PnL +${active_basket.net_floating_profit:.2f} | {signal.rationale}",
                            quality_score=signal.quality_score,
                            created_at=now_ts,
                        )
                    ],
                )

            return EntryPlanDecision(
                allowed=False,
                entry_mode=mode,
                rejection_reason="ACTIVE_BASKET_ALREADY_OPEN",
            )

        # Case 2: No active basket -> New Basket Entry (SINGLE_ENTRY, CONTROLLED_MULTI_ENTRY, or RE_ENTRY)
        last_close_seq = self._last_closed_tick_seq.get(sym_k, -1)
        if mode == EntryMode.RE_ENTRY.value and tick_seq > 0 and last_close_seq == tick_seq:
            return EntryPlanDecision(
                allowed=False,
                entry_mode=mode,
                rejection_reason="RE_ENTRY_REQUIRES_FRESH_TICK_SIGNAL",
            )

        if mode == EntryMode.SINGLE_ENTRY.value:
            count = 1
        else:
            count = max(1, min(instrument_config.basket_size, signal.recommended_positions))

        entries: List[PlannedOrderEntry] = []
        for idx in range(count):
            entry_id = f"ENT_{sym_k}_{uuid.uuid4().hex[:8].upper()}_{idx+1}"
            entries.append(
                PlannedOrderEntry(
                    entry_id=entry_id,
                    symbol_key=sym_k,
                    direction=signal.direction,
                    slot_index=idx,
                    entry_mode=mode,
                    entry_type=signal.entry_type,
                    reason=f"{mode.upper()}[{idx+1}/{count}]: {signal.rationale}",
                    quality_score=signal.quality_score,
                    created_at=now_ts,
                )
            )

        self._last_entry_tick_seq[sym_k] = tick_seq
        self._last_entry_time[sym_k] = now_ts
        return EntryPlanDecision(
            allowed=True,
            entry_mode=mode,
            planned_entries=entries,
        )
