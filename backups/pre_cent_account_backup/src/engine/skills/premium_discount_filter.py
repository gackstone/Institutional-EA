"""
Skill: premium_discount_filter [VIDEO 2]
Evaluates trade candidate entry location relative to 50% equilibrium of the protected leg.
Bullish: entry <= 50% equilibrium (Discount).
Bearish: entry >= 50% equilibrium (Premium).
A missed trade costs nothing.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from src.core.contracts import Candle
from src.engine.types import SkillResult, Context, normalize_to_candles


def evaluate(data: Any, ctx: Context) -> SkillResult:
    """
    Evaluates whether the candidate entry price sits in the correct half of the protected leg.
    [VIDEO 2]
    """
    candles: List[Candle] = normalize_to_candles(data)
    if not candles:
        return SkillResult(status="FAIL", reasons=["No candles provided"], tag="[VIDEO 2]")

    current_price = ctx.current_price or candles[-1].close
    trend = ctx.trend
    protected_low = ctx.protected_low
    protected_high = ctx.protected_high

    reasons: List[str] = []
    level_prices: Dict[str, float] = {}

    # Determine the impulse leg boundaries
    if trend == "BULL":
        # Bullish leg: from protected low to highest high since that low
        p_low = protected_low if protected_low is not None else min(c.low for c in candles[-20:])
        highs_after = [c.high for c in candles if c.low >= p_low or c.time >= (ctx.bos_time or candles[0].time)]
        p_high = max(highs_after) if highs_after else max(c.high for c in candles[-20:])

        leg_range = p_high - p_low
        equilibrium = p_low + 0.50 * leg_range
        ctx.active_leg = (p_low, p_high)
        ctx.equilibrium = equilibrium

        level_prices["leg_low"] = p_low
        level_prices["leg_high"] = p_high
        level_prices["equilibrium"] = equilibrium
        level_prices["entry_price"] = current_price

        # Range invalidation check [ART-07]
        if candles[-1].close < p_low:
            ctx.parameters["range_valid"] = False
            return SkillResult(
                status="INVALID_RANGE",
                level_prices=level_prices,
                reasons=[f"Range invalidation: Closed candle ({candles[-1].close:.5f}) broke below swing low ({p_low:.5f}). Discount wasn't cheap after all; step aside and draw new range [ART-07]"],
                confidence=0.0,
                tag="[ART-07]",
                metadata={"range_valid": False}
            )

        ctx.parameters["range_valid"] = True
        if current_price <= equilibrium:
            status = "PASS"
            confidence = 1.0
            reasons.append(
                f"Location approved: BUY price {current_price:.5f} is in DISCOUNT (<= 50% equilibrium {equilibrium:.5f}) of leg [{p_low:.5f} - {p_high:.5f}] [VIDEO 2, ART-07]"
            )
        else:
            status = "FAIL"
            confidence = 0.0
            reasons.append(
                f"Location rejected: BUY price {current_price:.5f} is in PREMIUM (> 50% equilibrium {equilibrium:.5f}); wait for discount [VIDEO 2, ART-07]"
            )

    elif trend == "BEAR":
        # Bearish leg: from protected high to lowest low since that high
        p_high = protected_high if protected_high is not None else max(c.high for c in candles[-20:])
        lows_after = [c.low for c in candles if c.high <= p_high or c.time >= (ctx.bos_time or candles[0].time)]
        p_low = min(lows_after) if lows_after else min(c.low for c in candles[-20:])

        leg_range = p_high - p_low
        equilibrium = p_low + 0.50 * leg_range
        ctx.active_leg = (p_high, p_low)
        ctx.equilibrium = equilibrium

        level_prices["leg_high"] = p_high
        level_prices["leg_low"] = p_low
        level_prices["equilibrium"] = equilibrium
        level_prices["entry_price"] = current_price

        # Range invalidation check [ART-07]
        if candles[-1].close > p_high:
            ctx.parameters["range_valid"] = False
            return SkillResult(
                status="INVALID_RANGE",
                level_prices=level_prices,
                reasons=[f"Range invalidation: Closed candle ({candles[-1].close:.5f}) broke above swing high ({p_high:.5f}). Premium wasn't expensive after all; step aside and draw new range [ART-07]"],
                confidence=0.0,
                tag="[ART-07]",
                metadata={"range_valid": False}
            )

        ctx.parameters["range_valid"] = True
        if current_price >= equilibrium:
            status = "PASS"
            confidence = 1.0
            reasons.append(
                f"Location approved: SELL price {current_price:.5f} is in PREMIUM (>= 50% equilibrium {equilibrium:.5f}) of leg [{p_high:.5f} - {p_low:.5f}] [VIDEO 2, ART-07]"
            )
        else:
            status = "FAIL"
            confidence = 0.0
            reasons.append(
                f"Location rejected: SELL price {current_price:.5f} is in DISCOUNT (< 50% equilibrium {equilibrium:.5f}); wait for premium [VIDEO 2, ART-07]"
            )
    else:
        status = "FAIL"
        confidence = 0.0
        reasons.append("Cannot evaluate Premium/Discount: trend is RANGE/TRANSITION [VIDEO 2, 4]")

    return SkillResult(
        status=status,
        level_prices=level_prices,
        reasons=reasons,
        confidence=confidence,
        tag="[VIDEO 2]",
        metadata={
            "coach_lesson": "Two traders, same trend, same stop, same target. Where they bought decides the quality.",
            "equilibrium": ctx.equilibrium,
        }
    )
