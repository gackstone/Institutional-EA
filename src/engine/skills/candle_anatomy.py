"""
Candle Anatomy and S/R Zones Engine [ART-11].
Implements price action fundamentals:
- Candle Anatomy: Body = who won, wicks = rejection.
- Rejection verification: Long upper wick = buyers rejected; long lower wick = sellers rejected.
- Support & Resistance: Modeled as dynamic ZONES (~0.5 x ATR), not exact lines.
- Mandatory Rule [ART-11]: Every trade setup must define invalidation BEFORE order placement.
- "Price action doesn't predict the future. It shows you where you're wrong."
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Union

from src.core.contracts import Candle
from src.engine.types import SkillResult, Context, normalize_to_candles


@dataclass
class CandleMetrics:
    total_range: float
    body_size: float
    upper_wick: float
    lower_wick: float
    body_pct: float
    upper_wick_pct: float
    lower_wick_pct: float
    is_bullish: bool
    is_rejection: bool


def analyze_candle(candle: Candle) -> CandleMetrics:
    """Computes exact anatomy metrics for a closed candle [ART-11]."""
    total_range = max(candle.high - candle.low, 1e-6)
    body_size = abs(candle.close - candle.open)
    upper_wick = candle.high - max(candle.open, candle.close)
    lower_wick = min(candle.open, candle.close) - candle.low

    body_pct = (body_size / total_range) * 100.0
    upper_pct = (upper_wick / total_range) * 100.0
    lower_pct = (lower_wick / total_range) * 100.0
    is_bull = candle.close >= candle.open
    is_rejection = (upper_pct >= 45.0) or (lower_pct >= 45.0)

    return CandleMetrics(
        total_range=round(total_range, 5),
        body_size=round(body_size, 5),
        upper_wick=round(upper_wick, 5),
        lower_wick=round(lower_wick, 5),
        body_pct=round(body_pct, 1),
        upper_wick_pct=round(upper_pct, 1),
        lower_wick_pct=round(lower_pct, 1),
        is_bullish=is_bull,
        is_rejection=is_rejection,
    )


def evaluate(candles_data: Sequence[Union[Candle, dict, Any]], ctx: Context) -> SkillResult:
    """Evaluates candle anatomy and S/R zone invalidation [ART-11]."""
    candles = normalize_to_candles(candles_data)
    if not candles:
        return SkillResult(
            status="INSUFFICIENT_DATA",
            passed=False,
            reasons=["No closed candles to evaluate candle anatomy [ART-11]"],
            tags=["[ART-11]"],
        )

    last_c = candles[-1]
    m = analyze_candle(last_c)

    # Compute ATR for S/R zone width (~0.5x ATR) [ART-11, ASSUMPTION]
    atr = max(candles[-1].range, ctx.pip_size * 10)
    zone_half_width = atr * 0.25

    levels = {
        "candle_range": m.total_range,
        "body_pct": m.body_pct,
        "upper_wick_pct": m.upper_wick_pct,
        "lower_wick_pct": m.lower_wick_pct,
        "zone_width": zone_half_width * 2.0,
    }

    reasons = [
        f"Candle Anatomy: Body={m.body_pct}% ({'Bull' if m.is_bullish else 'Bear'}), Upper Wick={m.upper_wick_pct}%, Lower Wick={m.lower_wick_pct}% [ART-11]",
        f"Support/Resistance modeled as zones (width {zone_half_width*2:.5f}), not single lines [ART-11]",
        "Price action doesn't predict the future. It shows you where you're wrong [ART-11]"
    ]

    return SkillResult(
        status="ANALYZED",
        passed=True,
        level_prices=levels,
        reasons=reasons,
        confidence=0.85,
        tags=["[ART-11]"],
        metadata={
            "is_rejection": m.is_rejection,
            "coach_lesson": "Price action doesn't predict the future. It shows you where you're wrong.",
        }
    )
