"""
Four Phases of a Move [ART-01].
Tracks the institutional 4-phase cycle:
1. CONSOLIDATION: Sideways price action, orders building on both sides.
2. EXPANSION: Fast breakout from consolidation with large candles.
3. RETRACEMENT: Pullback into the expansion move (often into the FVG it left).
4. REVERSAL: Liquidity taken at high/low, followed by change of character (CHOCH) into a new range.
Caveat [ART-01]: Easy to label afterward; live, a pullback and a reversal can look the same.
Descriptive and lagging only: NEVER use market phase as a standalone entry or exit trigger!
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Sequence, Union

from src.core.contracts import Candle
from src.engine.types import SkillResult, Context, normalize_to_candles


def evaluate(candles_data: Sequence[Union[Candle, dict, Any]], ctx: Context) -> SkillResult:
    """Classifies the current 4-phase state using closed candles [ART-01]."""
    candles = normalize_to_candles(candles_data)
    if len(candles) < 10:
        return SkillResult(
            status="INSUFFICIENT_DATA",
            passed=False,
            reasons=["Need at least 10 closed candles for market phase labeling [ART-01]"],
            tags=["[ART-01]"],
        )

    recent = candles[-10:]
    ranges = [c.high - c.low for c in recent]
    mean_range = sum(ranges) / len(ranges)
    cur_range = recent[-1].high - recent[-1].low

    # Heuristic classification for logging and coach explanation
    phase = "CONSOLIDATION"
    confidence = 0.70

    if cur_range > 1.8 * mean_range:
        phase = "EXPANSION"
    elif ctx.trend in ("BULL", "BEAR") and (recent[-1].close < recent[-2].close if ctx.trend == "BULL" else recent[-1].close > recent[-2].close):
        phase = "RETRACEMENT"
    elif ctx.parameters.get("has_choch", False):
        phase = "REVERSAL"

    reasons = [
        f"Market Phase labeled as {phase} (confidence {confidence:.0%}) [ART-01]",
        "Context only: Retracement into a gap serves as a cue to watch the FVG [ART-01]",
        "Caveat: Easy to label afterward; live, a pullback and a reversal look identical [ART-01]",
        "Guard: Phase is never used as a standalone entry or exit trigger [ART-01]"
    ]

    return SkillResult(
        status=phase,
        passed=True,
        level_prices={"mean_candle_range": mean_range},
        reasons=reasons,
        confidence=confidence,
        tags=["[ART-01]"],
        metadata={
            "phase": phase,
            "coach_lesson": "Easy to label afterward. Live, a pullback and a reversal look the same.",
        }
    )
