"""
Liquidity Sweep vs Breakout Classifier [ART-10].
AMENDS Part 1 Video 6:
- Sweep: Wick trades beyond the level, then closes back inside.
  - Sweep requires a subsequent Change of Character (CHOCH) to confirm structure [ART-10, ART-06].
  - "Not every wick is a sweep. Let structure confirm it." [ART-10]
  - Risk line: Stop placed beyond the sweep wick extreme. Invalidation occurs on close beyond extreme.
- Breakout: Two accepted confirmation forms [ART-10, VIDEO 6]:
  1. Two consecutive candle closes beyond the level (stays outside).
  2. One close beyond + retest of the broken level that holds as new support/resistance.
- TRAP Reversal: A TRAP (wick through, close back inside) followed by a CHOCH provides valid reversal context.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Sequence, Union

from src.core.contracts import Candle
from src.engine.types import SkillResult, Context, normalize_to_candles


def evaluate(candles_data: Sequence[Union[Candle, dict, Any]], ctx: Context) -> SkillResult:
    """Classifies pool touch as SWEEP, BREAKOUT, or TRAP [ART-10]."""
    candles = normalize_to_candles(candles_data)
    if len(candles) < 3:
        return SkillResult(
            status="INSUFFICIENT_DATA",
            passed=False,
            reasons=["Need at least 3 closed candles for sweep/breakout classification [ART-10]"],
            tags=["[ART-10]"],
        )

    test_level = ctx.parameters.get("test_level")
    if test_level is None:
        # Default to highest or lowest level of lookback
        test_level = max(c.high for c in candles[-15:-2]) if ctx.trend == "BULL" else min(c.low for c in candles[-15:-2])

    last_candle = candles[-1]
    penultimate_candle = candles[-2]
    levels = {
        "test_level": test_level,
        "penultimate_close": penultimate_candle.close,
        "last_close": last_candle.close,
    }

    # 1. Bullish breakout / sweep evaluation (at resistance / swing high)
    if ctx.trend == "BULL" or last_candle.high >= test_level:
        # Check for Sweep: wick pierced test_level, but candle closed back below [ART-10]
        if last_candle.high > test_level and last_candle.close <= test_level:
            levels["sweep_extreme"] = last_candle.high
            has_choch = ctx.parameters.get("has_choch", False)
            status = "SWEEP_CONFIRMED" if has_choch else "SWEEP_CANDIDATE"
            reasons = [
                f"SWEEP detected: Candle wicked to {last_candle.high:.5f} but closed back inside at {last_candle.close:.5f} <= {test_level:.5f} [ART-10]",
                "Structure confirmation: " + ("CHOCH confirmed! Ready for entry plan [ART-06]" if has_choch else "Awaiting CHOCH close; a sweep alone is not enough [ART-06, ART-10]"),
                f"Risk line: Wick extreme {last_candle.high:.5f}. Close beyond extreme invalidates setup [ART-10]"
            ]
            return SkillResult(
                status=status,
                passed=has_choch,
                level_prices=levels,
                reasons=reasons,
                confidence=0.88 if has_choch else 0.50,
                tags=["[ART-10]", "[ART-06]"],
                metadata={
                    "is_sweep": True,
                    "sweep_extreme": last_candle.high,
                    "coach_lesson": "Liquidity shows where price may go; structure shows what it did there.",
                }
            )

        # Check for Breakout Confirmation (Form 1: two closes beyond) [VIDEO 6, ART-10]
        if penultimate_candle.close > test_level and last_candle.close > test_level:
            reasons = [
                f"BREAKOUT_CONFIRMED (Form 1): Two consecutive closes beyond level ({penultimate_candle.close:.5f}, {last_candle.close:.5f} > {test_level:.5f}) [VIDEO 6, ART-10]",
                "Level has become confirmed support [VIDEO 6]"
            ]
            return SkillResult(
                status="BREAKOUT_CONFIRMED",
                passed=True,
                level_prices=levels,
                reasons=reasons,
                confidence=0.90,
                tags=["[VIDEO 6]", "[ART-10]"],
            )

        # Check for Breakout Confirmation (Form 2: close beyond + retest & hold) [ART-10]
        if penultimate_candle.close > test_level and last_candle.low <= test_level and last_candle.close > test_level:
            reasons = [
                f"BREAKOUT_CONFIRMED (Form 2): Close beyond with retest and hold ({last_candle.low:.5f} tested {test_level:.5f}, closed at {last_candle.close:.5f}) [ART-10]",
                "Retest held successfully as support [ART-10]"
            ]
            return SkillResult(
                status="BREAKOUT_CONFIRMED",
                passed=True,
                level_prices=levels,
                reasons=reasons,
                confidence=0.88,
                tags=["[ART-10]"],
            )

        # First close beyond: PENDING [VIDEO 6]
        if last_candle.close > test_level and penultimate_candle.close <= test_level:
            return SkillResult(
                status="BREAKOUT_PENDING",
                passed=False,
                level_prices=levels,
                reasons=[f"BREAKOUT_PENDING: Only 1 close beyond {test_level:.5f}. Must wait for second close or retest hold [VIDEO 6, ART-10]"],
                tags=["[VIDEO 6]", "[ART-10]"],
            )

    # 2. Bearish breakout / sweep evaluation (at support / swing low)
    if last_candle.low <= test_level:
        if last_candle.low < test_level and last_candle.close >= test_level:
            levels["sweep_extreme"] = last_candle.low
            has_choch = ctx.parameters.get("has_choch", False)
            status = "SWEEP_CONFIRMED" if has_choch else "SWEEP_CANDIDATE"
            reasons = [
                f"SWEEP detected: Candle wicked to {last_candle.low:.5f} but closed back inside at {last_candle.close:.5f} >= {test_level:.5f} [ART-10]",
                "Structure confirmation: " + ("CHOCH confirmed! Ready for entry plan [ART-06]" if has_choch else "Awaiting CHOCH close; a sweep alone is not enough [ART-06, ART-10]"),
                f"Risk line: Wick extreme {last_candle.low:.5f}. Close beyond extreme invalidates setup [ART-10]"
            ]
            return SkillResult(
                status=status,
                passed=has_choch,
                level_prices=levels,
                reasons=reasons,
                confidence=0.88 if has_choch else 0.50,
                tags=["[ART-10]", "[ART-06]"],
                metadata={
                    "is_sweep": True,
                    "sweep_extreme": last_candle.low,
                    "coach_lesson": "Liquidity shows where price may go; structure shows what it did there.",
                }
            )

        if penultimate_candle.close < test_level and last_candle.close < test_level:
            return SkillResult(
                status="BREAKOUT_CONFIRMED",
                passed=True,
                level_prices=levels,
                reasons=[f"Bearish BREAKOUT_CONFIRMED: Two consecutive closes below {test_level:.5f} [VIDEO 6, ART-10]"],
                tags=["[VIDEO 6]", "[ART-10]"],
            )

    return SkillResult(
        status="NO_EVENT",
        passed=False,
        level_prices=levels,
        reasons=[f"Level {test_level:.5f} has not experienced a sweep or breakout on closed candle [ART-10]"],
        tags=["[ART-10]"],
    )
