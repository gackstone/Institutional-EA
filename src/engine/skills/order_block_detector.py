"""
Order Block Detector [ART-09].
AMENDS Part 1 Video 1 order block qualification:
- Definition: The last opposite candle before a strong move that breaks structure.
- Strict Qualification [ART-09]: The impulse move MUST break structure (body-close BOS)
  AND leave an unmitigated Fair Value Gap (imbalance).
- "No break, no gap = just a candle." [ART-09]
- Sequence: Sweep liquidity -> CHOCH -> Pullback into Order Block.
- Invalidation: Price closes through the order block zone -> setup cancelled [ART-09].
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Union

from src.core.contracts import Candle
from src.engine.types import SkillResult, Context, normalize_to_candles


@dataclass
class QualifiedOrderBlock:
    direction: str  # "BULL" (last down candle) or "BEAR" (last up candle)
    high: float
    low: float
    ob_index: int
    ob_time: str
    bos_level: float
    has_fvg: bool
    retested: bool = False
    invalidated: bool = False


def detect_qualified_ob(candles: Sequence[Candle], min_gap: float = 0.0001) -> Optional[QualifiedOrderBlock]:
    """
    Detects qualified Order Block requiring BOTH body-close BOS and an FVG [ART-09].
    """
    n = len(candles)
    if n < 4:
        return None

    # Scan backwards from penultimate candle
    for i in range(n - 3, 0, -1):
        c_ob = candles[i]
        c_impulse1 = candles[i + 1]
        c_impulse2 = candles[i + 2]

        # Bullish OB Candidate: last down candle before strong up push [ART-09]
        if c_ob.close < c_ob.open:
            # 1. Must cause body close above prior local high (BOS)
            prior_high = max(c.high for c in candles[max(0, i - 10):i]) if i > 0 else c_ob.high
            has_bos = any(c.close > prior_high for c in candles[i + 1:])

            # 2. Must leave an FVG on the impulse move (c_ob.high < c_impulse2.low) [ART-09, ART-08]
            has_fvg = (c_impulse2.low - c_ob.high) >= min_gap

            if has_bos and has_fvg:
                return QualifiedOrderBlock(
                    direction="BULL",
                    high=c_ob.high,
                    low=c_ob.low,
                    ob_index=i,
                    ob_time=c_ob.time if isinstance(c_ob.time, str) else c_ob.time.isoformat(),
                    bos_level=prior_high,
                    has_fvg=True,
                )

        # Bearish OB Candidate: last up candle before strong down push [ART-09]
        elif c_ob.close > c_ob.open:
            prior_low = min(c.low for c in candles[max(0, i - 10):i]) if i > 0 else c_ob.low
            has_bos = any(c.close < prior_low for c in candles[i + 1:])
            has_fvg = (c_ob.low - c_impulse2.high) >= min_gap

            if has_bos and has_fvg:
                return QualifiedOrderBlock(
                    direction="BEAR",
                    high=c_ob.high,
                    low=c_ob.low,
                    ob_index=i,
                    ob_time=c_ob.time if isinstance(c_ob.time, str) else c_ob.time.isoformat(),
                    bos_level=prior_low,
                    has_fvg=True,
                )

    return None


def evaluate(candles_data: Sequence[Union[Candle, dict, Any]], ctx: Context) -> SkillResult:
    """Evaluates Order Block qualification on closed candles [ART-09]."""
    candles = normalize_to_candles(candles_data)
    if len(candles) < 4:
        return SkillResult(
            status="INSUFFICIENT_DATA",
            passed=False,
            reasons=["Need at least 4 closed candles to evaluate Order Block qualification [ART-09]"],
            tags=["[ART-09]"],
        )

    min_gap = ctx.pip_size * 0.5
    ob = detect_qualified_ob(candles, min_gap=min_gap)
    if not ob:
        return SkillResult(
            status="NO_QUALIFIED_OB",
            passed=False,
            reasons=["No qualified Order Block found. No break, no gap = just a candle [ART-09]"],
            tags=["[ART-09]"],
        )

    cur_close = candles[-1].close
    levels = {
        "ob_high": ob.high,
        "ob_low": ob.low,
        "bos_level": ob.bos_level,
    }
    ctx.parameters["ob_high"] = ob.high
    ctx.parameters["ob_low"] = ob.low

    # Invalidation: price closed through the order block [ART-09]
    if ob.direction == "BULL" and cur_close < ob.low:
        return SkillResult(
            status="INVALIDATED",
            passed=False,
            level_prices=levels,
            reasons=[f"Bullish Order Block invalidated: Candle closed below block low ({cur_close:.5f} < {ob.low:.5f}) [ART-09]"],
            tags=["[ART-09]"],
        )
    elif ob.direction == "BEAR" and cur_close > ob.high:
        return SkillResult(
            status="INVALIDATED",
            passed=False,
            level_prices=levels,
            reasons=[f"Bearish Order Block invalidated: Candle closed above block high ({cur_close:.5f} > {ob.high:.5f}) [ART-09]"],
            tags=["[ART-09]"],
        )

    reasons = [
        f"Qualified {ob.direction} Order Block: [{ob.low:.5f} - {ob.high:.5f}] at {ob.ob_time} [ART-09]",
        f"Impulse confirmed: Caused body-close BOS beyond {ob.bos_level:.5f} AND created Fair Value Gap [ART-09]",
        "Order Block zone holds valid on closed candles [ART-09]"
    ]

    return SkillResult(
        status="QUALIFIED_OB",
        passed=True,
        level_prices=levels,
        reasons=reasons,
        confidence=0.92,
        tags=["[ART-09]"],
        metadata={
            "direction": ob.direction,
            "ob_high": ob.high,
            "ob_low": ob.low,
            "coach_lesson": "No break, no gap = just a candle. Liquidity first, then structure, then the zone.",
        }
    )
