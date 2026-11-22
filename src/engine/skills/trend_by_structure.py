"""
Skill: trend_by_structure [VIDEO 4]
Evaluates market structure using completed closed candles.
Trend = structure, not the last candle.
Uptrend: HH + HL intact, no body close below protected low.
Downtrend: LH + LL intact, no body close above protected high.
Large single-candle drops/spikes that hold above protected levels do NOT flip the trend.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from src.core.contracts import Candle
from src.engine.types import SkillResult, Context, normalize_to_candles


def evaluate(data: Any, ctx: Context) -> SkillResult:
    """
    Evaluates closed candles against protected swing levels.
    [VIDEO 4]
    """
    candles: List[Candle] = normalize_to_candles(data)
    if not candles:
        return SkillResult(
            status="FAIL",
            reasons=["No closed candles provided for trend evaluation"],
            confidence=0.0,
            tag="[VIDEO 4]"
        )

    last_candle = candles[-1]
    reasons: List[str] = []
    trend = "RANGE/TRANSITION"
    confidence = 0.5

    protected_low = ctx.protected_low
    protected_high = ctx.protected_high

    # Evaluate against protected levels using closed candle prices only [VIDEO 4]
    if protected_low is not None and protected_high is None:
        # Candidate uptrend: verify if any candle has closed below protected_low
        has_broken_protected_low = any(c.close < protected_low for c in candles[-20:])
        if not has_broken_protected_low:
            trend = "BULL"
            confidence = 1.0
            reasons.append(
                f"Bullish trend intact: higher highs formed and all closed candles hold above protected low {protected_low:.5f} [VIDEO 4]"
            )
        else:
            trend = "RANGE/TRANSITION"
            reasons.append(
                f"Candle closed below protected low {protected_low:.5f}; uptrend in trouble / CHOCH occurred [VIDEO 4, 15]"
            )

    elif protected_high is not None and protected_low is None:
        # Candidate downtrend: verify if any candle has closed above protected_high
        has_broken_protected_high = any(c.close > protected_high for c in candles[-20:])
        if not has_broken_protected_high:
            trend = "BEAR"
            confidence = 1.0
            reasons.append(
                f"Bearish trend intact: lower lows formed and all closed candles hold below protected high {protected_high:.5f} [VIDEO 4]"
            )
        else:
            trend = "RANGE/TRANSITION"
            reasons.append(
                f"Candle closed above protected high {protected_high:.5f}; downtrend in trouble / CHOCH occurred [VIDEO 4, 15]"
            )

    elif protected_low is not None and protected_high is not None:
        # Both exist: check which structural break is more recent
        low_broken = any(c.close < protected_low for c in candles[-10:])
        high_broken = any(c.close > protected_high for c in candles[-10:])
        if not low_broken and high_broken:
            trend = "BULL"
            confidence = 1.0
            reasons.append(f"Bullish structure dominant: protected low {protected_low:.5f} holding [VIDEO 4]")
        elif not high_broken and low_broken:
            trend = "BEAR"
            confidence = 1.0
            reasons.append(f"Bearish structure dominant: protected high {protected_high:.5f} holding [VIDEO 4]")
        else:
            trend = "RANGE/TRANSITION"
            reasons.append("Conflicting structural breaks; market in transition [VIDEO 4]")
    else:
        # Fallback to simple swing progression if protected swings not yet marked
        if len(candles) >= 10:
            half = len(candles) // 2
            first_half_low = min(c.low for c in candles[:half])
            second_half_low = min(c.low for c in candles[half:])
            first_half_high = max(c.high for c in candles[:half])
            second_half_high = max(c.high for c in candles[half:])
            if second_half_high > first_half_high and second_half_low > first_half_low:
                trend = "BULL"
                confidence = 0.7
                reasons.append("HH + HL progression observed over window [VIDEO 4]")
            elif second_half_high < first_half_high and second_half_low < first_half_low:
                trend = "BEAR"
                confidence = 0.7
                reasons.append("LH + LL progression observed over window [VIDEO 4]")
            else:
                trend = "RANGE/TRANSITION"
                reasons.append("Mixed structure; range or consolidation [VIDEO 4]")

    ctx.trend = trend
    status = "PASS" if trend in ("BULL", "BEAR") else "HOLD"

    return SkillResult(
        status=status,
        level_prices={
            "current_close": last_candle.close,
            "protected_low": protected_low or 0.0,
            "protected_high": protected_high or 0.0,
        },
        reasons=reasons,
        confidence=confidence,
        tag="[VIDEO 4]",
        metadata={
            "coach_lesson": "Don't judge the trend by the last candle. Judge it by the last low.",
            "trend": trend,
            "last_close": last_candle.close,
        }
    )
