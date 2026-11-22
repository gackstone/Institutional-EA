"""
Fair Value Gap (FVG) Detector [ART-08].
Implements canonical 3-candle non-overlapping gap detection:
- Bullish FVG: high[candle 1] < low[candle 3], gap zone = [high[c1], low[c3]].
- Bearish FVG: low[candle 1] > high[candle 3], gap zone = [high[c3], low[c1]].
- Midpoint: 50% equilibrium level of the gap zone (often reached before turning).
- Invalidation: A completed candle closing through the gap invalidates the setup [ART-08, VIDEO 10].
- Context: Strong when liquidity was swept first and gap formed on structure break; weak inside range [ART-08, VIDEO 9].
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Union

from src.core.contracts import Candle
from src.engine.types import SkillResult, Context, normalize_to_candles


@dataclass
class DetectedFVG:
    direction: str  # "BULL" or "BEAR"
    top: float
    bottom: float
    midpoint: float
    size: float
    formation_index: int
    formation_time: str
    mitigated: bool = False
    invalidated: bool = False


def find_fvgs(candles: Sequence[Candle], min_gap: float = 0.0001) -> List[DetectedFVG]:
    """Finds all non-overlapping 3-candle fair value gaps in closed candle sequence."""
    fvgs: List[DetectedFVG] = []
    n = len(candles)
    if n < 3:
        return fvgs

    for i in range(2, n):
        c1 = candles[i - 2]
        c2 = candles[i - 1]
        c3 = candles[i]

        # Bullish FVG: c1.high < c3.low [ART-08]
        if c3.low > c1.high and (c3.low - c1.high) >= min_gap:
            top = c3.low
            bottom = c1.high
            mid = round((top + bottom) / 2.0, 5)
            fvgs.append(
                DetectedFVG(
                    direction="BULL",
                    top=top,
                    bottom=bottom,
                    midpoint=mid,
                    size=top - bottom,
                    formation_index=i - 1,
                    formation_time=c2.time if isinstance(c2.time, str) else c2.time.isoformat(),
                )
            )

        # Bearish FVG: c1.low > c3.high [ART-08]
        elif c1.low > c3.high and (c1.low - c3.high) >= min_gap:
            top = c1.low
            bottom = c3.high
            mid = round((top + bottom) / 2.0, 5)
            fvgs.append(
                DetectedFVG(
                    direction="BEAR",
                    top=top,
                    bottom=bottom,
                    midpoint=mid,
                    size=top - bottom,
                    formation_index=i - 1,
                    formation_time=c2.time if isinstance(c2.time, str) else c2.time.isoformat(),
                )
            )

    return fvgs


def evaluate(candles_data: Sequence[Union[Candle, dict, Any]], ctx: Context) -> SkillResult:
    """Evaluates the latest unmitigated Fair Value Gap on closed candles [ART-08]."""
    candles = normalize_to_candles(candles_data)
    if len(candles) < 3:
        return SkillResult(
            status="INSUFFICIENT_DATA",
            passed=False,
            reasons=["Need at least 3 closed candles for FVG detection [ART-08]"],
            tags=["[ART-08]"],
        )

    min_gap = ctx.pip_size * 0.5
    all_fvgs = find_fvgs(candles, min_gap=min_gap)
    if not all_fvgs:
        return SkillResult(
            status="NO_GAP",
            passed=False,
            reasons=["No 3-candle non-overlapping imbalance detected [ART-08]"],
            tags=["[ART-08]"],
        )

    latest_fvg = all_fvgs[-1]
    cur_close = candles[-1].close
    levels = {
        "fvg_top": latest_fvg.top,
        "fvg_bottom": latest_fvg.bottom,
        "fvg_midpoint": latest_fvg.midpoint,
        "fvg_size": latest_fvg.size,
    }
    ctx.parameters["fvg_top"] = latest_fvg.top
    ctx.parameters["fvg_bottom"] = latest_fvg.bottom
    ctx.parameters["fvg_midpoint"] = latest_fvg.midpoint

    # Check for invalidation by closed candle [ART-08, VIDEO 10]
    if latest_fvg.direction == "BULL" and cur_close < latest_fvg.bottom:
        return SkillResult(
            status="INVALIDATED",
            passed=False,
            level_prices=levels,
            reasons=[f"Bullish FVG invalidated: Candle closed below gap bottom ({cur_close:.5f} < {latest_fvg.bottom:.5f}) [ART-08]"],
            tags=["[ART-08]"],
        )
    elif latest_fvg.direction == "BEAR" and cur_close > latest_fvg.top:
        return SkillResult(
            status="INVALIDATED",
            passed=False,
            level_prices=levels,
            reasons=[f"Bearish FVG invalidated: Candle closed above gap top ({cur_close:.5f} > {latest_fvg.top:.5f}) [ART-08]"],
            tags=["[ART-08]"],
        )

    reasons = [
        f"Detected {latest_fvg.direction} FVG: [{latest_fvg.bottom:.5f} - {latest_fvg.top:.5f}], midpoint=50% at {latest_fvg.midpoint:.5f} [ART-08]",
        "Gap valid; closed candle has not penetrated through far boundary [ART-08]"
    ]

    return SkillResult(
        status="ACTIVE_GAP",
        passed=True,
        level_prices=levels,
        reasons=reasons,
        confidence=0.90,
        tags=["[ART-08]"],
        metadata={
            "direction": latest_fvg.direction,
            "midpoint": latest_fvg.midpoint,
            "coach_lesson": "Not every gap matters. Context decides.",
        }
    )
