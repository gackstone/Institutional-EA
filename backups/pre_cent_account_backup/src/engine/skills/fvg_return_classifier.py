"""
Skill: fvg_return_classifier [VIDEO 10]
Classifies the nature of return into a Fair Value Gap based on closed candles.
Depth is not the signal; watch the close.
- TAP: Price touches edge of gap but does not close inside.
- HELD: Candle wicks into gap but closes back above the 50% midpoint (bullish) or below 50% (bearish).
- CONFIRMED: Next candle pushes away strongly with displacement body.
- BROKEN: A candle closes through the gap. The idea is broken immediately.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from src.core.contracts import Candle
from src.engine.types import SkillResult, Context, normalize_to_candles


def evaluate(data: Any, ctx: Context) -> SkillResult:
    """
    Classifies FVG return behavior on completed candles.
    [VIDEO 10]
    """
    candles: List[Candle] = normalize_to_candles(data)
    if len(candles) < 2:
        return SkillResult(status="FAIL", reasons=["Need at least 2 closed candles to evaluate FVG return"], tag="[VIDEO 10]")

    fvg_top = ctx.parameters.get("fvg_top")
    fvg_bottom = ctx.parameters.get("fvg_bottom")
    fvg_direction = ctx.parameters.get("fvg_direction", "BUY")

    if fvg_top is None or fvg_bottom is None:
        return SkillResult(status="HOLD", reasons=["No FVG boundaries specified for return classification"], tag="[VIDEO 10]")

    fvg_mid = (fvg_top + fvg_bottom) / 2.0
    atr = ctx.atr or 0.0010
    strong_push_threshold = float(ctx.parameters.get("strong_push_atr_multiplier", 1.0)) * atr # [ASSUMPTION]

    last = candles[-1]
    prev = candles[-2]
    reasons: List[str] = []
    level_prices: Dict[str, float] = {
        "fvg_top": fvg_top,
        "fvg_bottom": fvg_bottom,
        "fvg_mid": fvg_mid,
        "last_close": last.close,
    }

    if fvg_direction == "BUY":
        # 1. BROKEN: Candle closes through bottom of gap [VIDEO 10]
        if last.close < fvg_bottom:
            status = "BROKEN"
            reasons.append(
                f"BROKEN: Candle closed through FVG ({last.close:.5f} < {fvg_bottom:.5f}). Setup is dead [VIDEO 10]"
            )
            return SkillResult(status=status, level_prices=level_prices, reasons=reasons, confidence=0.0, tag="[VIDEO 10]")

        # 2. CONFIRMED: Previous candle held, and last candle pushed away strongly with bullish body [VIDEO 10]
        prev_held = prev.low <= fvg_top and prev.close >= fvg_mid
        is_strong_push = last.is_bullish and (last.body >= strong_push_threshold) # [ASSUMPTION]
        if prev_held and is_strong_push and last.close > prev.high:
            status = "CONFIRMED"
            reasons.append(
                f"CONFIRMED: Gap held on prev bar ({prev.close:.5f} >= {fvg_mid:.5f}), followed by strong push away ({last.body:.5f} >= {strong_push_threshold:.5f}) [VIDEO 10]"
            )
            return SkillResult(status=status, level_prices=level_prices, reasons=reasons, confidence=1.0, tag="[VIDEO 10]")

        # 3. HELD: Candle wicked into gap and closed back above 50% midpoint [VIDEO 10]
        if last.low <= fvg_top and last.close >= fvg_mid:
            status = "HELD"
            reasons.append(
                f"HELD: Candle wicked into gap (low={last.low:.5f}) and closed back above 50% midpoint ({last.close:.5f} >= {fvg_mid:.5f}) [VIDEO 10]"
            )
            return SkillResult(status=status, level_prices=level_prices, reasons=reasons, confidence=0.8, tag="[VIDEO 10]")

        # 4. TAP: Touched top edge but did not penetrate deeply
        if last.low <= fvg_top and last.close > fvg_top:
            status = "TAP"
            reasons.append(f"TAP: Price touched FVG top edge ({last.low:.5f}) but closed outside [VIDEO 10]")
            return SkillResult(status=status, level_prices=level_prices, reasons=reasons, confidence=0.5, tag="[VIDEO 10]")

    else:
        # Bearish mirror
        if last.close > fvg_top:
            status = "BROKEN"
            reasons.append(
                f"BROKEN: Candle closed through Bearish FVG ({last.close:.5f} > {fvg_top:.5f}). Setup is dead [VIDEO 10]"
            )
            return SkillResult(status=status, level_prices=level_prices, reasons=reasons, confidence=0.0, tag="[VIDEO 10]")

        prev_held = prev.high >= fvg_bottom and prev.close <= fvg_mid
        is_strong_push = last.is_bearish and (last.body >= strong_push_threshold)
        if prev_held and is_strong_push and last.close < prev.low:
            status = "CONFIRMED"
            reasons.append(
                f"CONFIRMED: Gap held on prev bar, followed by strong downward push away [VIDEO 10]"
            )
            return SkillResult(status=status, level_prices=level_prices, reasons=reasons, confidence=1.0, tag="[VIDEO 10]")

        if last.high >= fvg_bottom and last.close <= fvg_mid:
            status = "HELD"
            reasons.append(
                f"HELD: Candle wicked into gap and closed back below 50% midpoint [VIDEO 10]"
            )
            return SkillResult(status=status, level_prices=level_prices, reasons=reasons, confidence=0.8, tag="[VIDEO 10]")

        if last.high >= fvg_bottom and last.close < fvg_bottom:
            status = "TAP"
            reasons.append("TAP: Price touched FVG bottom edge but closed outside [VIDEO 10]")
            return SkillResult(status=status, level_prices=level_prices, reasons=reasons, confidence=0.5, tag="[VIDEO 10]")

    return SkillResult(status="HOLD", level_prices=level_prices, reasons=["Price has not interacted with FVG [VIDEO 10]"], tag="[VIDEO 10]")
