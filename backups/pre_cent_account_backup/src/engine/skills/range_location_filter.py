"""
Skill: range_location_filter [VIDEO 13]
Filters out trade entries in the middle of a consolidation or range.
Middle of range = no clear edge, choppy, room against you either way.
Outputs NO_TRADE_MIDDLE when price is in the 40%-60% band of a detected range.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from src.core.contracts import Candle
from src.engine.types import SkillResult, Context, normalize_to_candles


def evaluate(data: Any, ctx: Context) -> SkillResult:
    """
    Evaluates whether price is situated in the hazardous middle band of a range.
    [VIDEO 13]
    """
    candles: List[Candle] = normalize_to_candles(data)
    if len(candles) < 3:
        return SkillResult(status="PASS", reasons=["Insufficient bars for range filter; passing"], tag="[VIDEO 13]")

    current_price = ctx.current_price or candles[-1].close
    lookback = ctx.parameters.get("range_lookback_bars", 30)
    window = candles[-min(len(candles), lookback):]

    range_high = max(c.high for c in window)
    range_low = min(c.low for c in window)
    span = range_high - range_low

    if span <= 0:
        return SkillResult(status="PASS", tag="[VIDEO 13]")

    # Check for range touches (support and resistance touches >= 2 each) [ASSUMPTION]
    tolerance = 0.15 * span
    high_touches = sum(1 for c in window if abs(c.high - range_high) <= tolerance)
    low_touches = sum(1 for c in window if abs(c.low - range_low) <= tolerance)
    is_established_range = (high_touches >= 2 and low_touches >= 2) or (ctx.trend == "RANGE/TRANSITION")

    reasons: List[str] = []
    level_prices: Dict[str, float] = {
        "range_high": range_high,
        "range_low": range_low,
        "range_span": span,
        "current_price": current_price,
    }

    if is_established_range:
        # Relative position within the range [0.0 = low, 1.0 = high]
        pos = (current_price - range_low) / span
        level_prices["relative_position"] = pos

        band_low = float(ctx.parameters.get("range_middle_band_low", 0.40))   # [ASSUMPTION]
        band_high = float(ctx.parameters.get("range_middle_band_high", 0.60)) # [ASSUMPTION]

        if band_low <= pos <= band_high:
            reasons.append(
                f"NO_TRADE_MIDDLE: Price {current_price:.5f} is in the middle band ({pos*100:.1f}%) of range [{range_low:.5f} - {range_high:.5f}]. Far from edges, no edge [VIDEO 13]"
            )
            return SkillResult(
                status="NO_TRADE_MIDDLE",
                level_prices=level_prices,
                reasons=reasons,
                confidence=0.0,
                tag="[VIDEO 13]",
                metadata={
                    "coach_lesson": "Don't force a decision. Movement is not location. Sometimes the best location is somewhere else.",
                    "relative_position": pos,
                }
            )
        else:
            reasons.append(
                f"Range edge location: Price {current_price:.5f} is near range boundary ({pos*100:.1f}%) with clear invalidation [VIDEO 13]"
            )
            return SkillResult(
                status="PASS",
                level_prices=level_prices,
                reasons=reasons,
                confidence=1.0,
                tag="[VIDEO 13]",
                metadata={"relative_position": pos}
            )

    return SkillResult(
        status="PASS",
        level_prices=level_prices,
        reasons=["Market is trending or no established range detected [VIDEO 13]"],
        confidence=1.0,
        tag="[VIDEO 13]"
    )
