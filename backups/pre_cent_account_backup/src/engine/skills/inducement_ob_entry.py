"""
Skill: inducement_ob_entry [VIDEO 1]
Identifies Inducement and Order Block (OB) setups.
Do not buy the first pullback (inducement); it is bait.
Entry: sweep of the inducement low, followed by a bullish close inside the Order Block.
Stop loss: below the Order Block low.
Target: the recent swing highs.
Invalidation: candle close below the Order Block low.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from src.core.contracts import Candle
from src.engine.types import SkillResult, Context, normalize_to_candles


def evaluate(data: Any, ctx: Context) -> SkillResult:
    """
    Evaluates closed candles for an Inducement + Order Block entry setup.
    [VIDEO 1]
    """
    candles: List[Candle] = normalize_to_candles(data)
    if len(candles) < 6:
        return SkillResult(status="FAIL", reasons=["Need at least 6 bars for inducement+OB evaluation"], tag="[VIDEO 1]")

    trend = ctx.trend
    reasons: List[str] = []
    level_prices: Dict[str, float] = {}

    # Bullish setup evaluation (bearish is exact mirror)
    if trend == "BULL" or ctx.parameters.get("force_direction") == "BUY":
        # 1. Locate Order Block: last bearish candle before the impulse push that caused BOS [VIDEO 1]
        ob_candle: Optional[Candle] = None
        ob_idx: Optional[int] = None

        # Look back from bar -5 to find the impulse origin
        for i in range(1, len(candles) - 3):
            c_curr = candles[i]
            c_next = candles[i + 1]
            # Bearish candle followed by strong bullish expansion
            if c_curr.close < c_curr.open and c_next.close > c_next.open and c_next.close > c_curr.high:
                # Check for FVG on impulse if required [ART-09: No break, no gap = just a candle]
                require_fvg = ctx.parameters.get("require_ob_fvg", True)
                min_gap = ctx.pip_size * 0.5
                fvg_present = (i + 2 < len(candles)) and (candles[i + 2].low - c_curr.high >= min_gap)
                if not require_fvg or fvg_present:
                    ob_candle = c_curr
                    ob_idx = i

        if ob_candle is None:
            return SkillResult(status="HOLD", reasons=["No valid Order Block found before impulse push [VIDEO 1]"], tag="[VIDEO 1]")

        ob_top = max(ob_candle.open, ob_candle.high)
        ob_bottom = min(ob_candle.close, ob_candle.low)

        # 2. Locate Inducement: the first minor pullback low formed after the impulse [VIDEO 1]
        inducement_low: Optional[float] = None
        inducement_idx: Optional[int] = None
        highest_high_after_ob = ob_top

        for j in range(ob_idx + 1, len(candles) - 1):
            c = candles[j]
            if c.high > highest_high_after_ob:
                highest_high_after_ob = c.high

            # Look for first pullback dip after reaching a new high
            if j > ob_idx + 2 and candles[j].low < candles[j - 1].low and candles[j].low < candles[j + 1].low:
                if inducement_low is None:
                    inducement_low = candles[j].low
                    inducement_idx = j
                    break

        if inducement_low is None:
            # Fallback: minor trough between OB and latest bars
            mid_slice = candles[ob_idx + 1: -1]
            if mid_slice:
                inducement_low = min(c.low for c in mid_slice)

        if inducement_low is None:
            return SkillResult(status="HOLD", reasons=["No inducement pullback low identified between OB and high [VIDEO 1]"], tag="[VIDEO 1]")

        # 3. Check trigger on recent closed candles [VIDEO 1]
        last = candles[-1]
        penultimate = candles[-2] if len(candles) >= 2 else last

        level_prices["ob_top"] = ob_top
        level_prices["ob_bottom"] = ob_bottom
        level_prices["inducement_low"] = inducement_low
        level_prices["swing_high"] = highest_high_after_ob

        # Rule 4: Invalidation - a close below the block means setup is off [VIDEO 1]
        if last.close < ob_bottom:
            reasons.append(
                f"SETUP INVALIDATED: Closed candle ({last.close:.5f}) below Order Block low ({ob_bottom:.5f}) [VIDEO 1]"
            )
            return SkillResult(
                status="INVALID",
                level_prices=level_prices,
                reasons=reasons,
                confidence=0.0,
                tag="[VIDEO 1]"
            )

        # Rule 2: Wait for sweep of the pullback low, then a bullish close in the block [VIDEO 1]
        # Low swept inducement low and reached into OB zone, with a bullish close inside the zone
        has_swept_inducement = (last.low < inducement_low) or (penultimate.low < inducement_low)
        touches_ob = (last.low <= ob_top) and (last.high >= ob_bottom)
        bullish_close_in_block = last.close > last.open and (ob_bottom <= last.close <= (ob_top + (ctx.atr * 0.2))) # [ASSUMPTION: inside or at boundary]

        if has_swept_inducement and touches_ob and bullish_close_in_block:
            entry_price = last.close
            stop_loss = ob_bottom - (ctx.pip_size * 2) # [VIDEO 1: stop below block]
            take_profit = highest_high_after_ob        # [VIDEO 1: target the highs]

            level_prices["entry"] = entry_price
            level_prices["stop_loss"] = stop_loss
            level_prices["take_profit"] = take_profit

            reasons.append(
                f"TRIGGERED: Inducement swept ({last.low:.5f} < {inducement_low:.5f}), tapped OB [{ob_bottom:.5f} - {ob_top:.5f}], and formed bullish close at {entry_price:.5f}. SL={stop_loss:.5f}, TP={take_profit:.5f} [VIDEO 1]"
            )
            return SkillResult(
                status="TRIGGERED",
                level_prices=level_prices,
                reasons=reasons,
                confidence=1.0,
                tag="[VIDEO 1]",
                metadata={
                    "direction": "BUY",
                    "coach_lesson": "That pullback wasn't your entry. It was bait.",
                    "entry": entry_price,
                    "sl": stop_loss,
                    "tp": take_profit,
                }
            )
        elif not has_swept_inducement:
            reasons.append(
                f"WAITING: First pullback at {inducement_low:.5f} has NOT been swept yet. Do not buy the bait [VIDEO 1]"
            )
            return SkillResult(status="HOLD", level_prices=level_prices, reasons=reasons, confidence=0.5, tag="[VIDEO 1]")
        else:
            reasons.append("Inducement swept; awaiting bullish close inside Order Block [VIDEO 1]")
            return SkillResult(status="HOLD", level_prices=level_prices, reasons=reasons, confidence=0.5, tag="[VIDEO 1]")

    elif trend == "BEAR" or ctx.parameters.get("force_direction") == "SELL":
        # Bearish mirror: Order Block is last bullish candle before drop
        ob_candle = None
        ob_idx = None
        for i in range(1, len(candles) - 3):
            c_curr = candles[i]
            c_next = candles[i + 1]
            if c_curr.close > c_curr.open and c_next.close < c_next.open and c_next.close < c_curr.low:
                require_fvg = ctx.parameters.get("require_ob_fvg", True)
                min_gap = ctx.pip_size * 0.5
                fvg_present = (i + 2 < len(candles)) and (c_curr.low - candles[i + 2].high >= min_gap)
                if not require_fvg or fvg_present:
                    ob_candle = c_curr
                    ob_idx = i

        if ob_candle is None:
            return SkillResult(status="HOLD", reasons=["No valid Bearish Order Block found [VIDEO 1]"], tag="[VIDEO 1]")

        ob_top = max(ob_candle.close, ob_candle.high)
        ob_bottom = min(ob_candle.open, ob_candle.low)

        # Inducement high
        inducement_high = None
        lowest_low_after_ob = ob_bottom
        for j in range(ob_idx + 1, len(candles) - 1):
            c = candles[j]
            if c.low < lowest_low_after_ob:
                lowest_low_after_ob = c.low
            if j > ob_idx + 2 and candles[j].high > candles[j - 1].high and candles[j].high > candles[j + 1].high:
                if inducement_high is None:
                    inducement_high = candles[j].high
                    break

        if inducement_high is None:
            mid_slice = candles[ob_idx + 1: -1]
            if mid_slice:
                inducement_high = max(c.high for c in mid_slice)

        if inducement_high is None:
            return SkillResult(status="HOLD", reasons=["No bearish inducement pullback high identified [VIDEO 1]"], tag="[VIDEO 1]")

        last = candles[-1]
        penultimate = candles[-2] if len(candles) >= 2 else last

        level_prices["ob_top"] = ob_top
        level_prices["ob_bottom"] = ob_bottom
        level_prices["inducement_high"] = inducement_high
        level_prices["swing_low"] = lowest_low_after_ob

        # Invalidation
        if last.close > ob_top:
            reasons.append(f"SETUP INVALIDATED: Closed candle ({last.close:.5f}) above Bearish OB high ({ob_top:.5f}) [VIDEO 1]")
            return SkillResult(status="INVALID", level_prices=level_prices, reasons=reasons, confidence=0.0, tag="[VIDEO 1]")

        has_swept_inducement = (last.high > inducement_high) or (penultimate.high > inducement_high)
        touches_ob = (last.high >= ob_bottom) and (last.low <= ob_top)
        bearish_close_in_block = last.close < last.open and (ob_bottom - (ctx.atr * 0.2) <= last.close <= ob_top)

        if has_swept_inducement and touches_ob and bearish_close_in_block:
            entry_price = last.close
            stop_loss = ob_top + (ctx.pip_size * 2)
            take_profit = lowest_low_after_ob
            level_prices["entry"] = entry_price
            level_prices["stop_loss"] = stop_loss
            level_prices["take_profit"] = take_profit
            reasons.append(
                f"TRIGGERED: Bearish Inducement swept ({last.high:.5f} > {inducement_high:.5f}), tapped OB [{ob_bottom:.5f} - {ob_top:.5f}], and formed bearish close at {entry_price:.5f}. SL={stop_loss:.5f}, TP={take_profit:.5f} [VIDEO 1]"
            )
            return SkillResult(
                status="TRIGGERED",
                level_prices=level_prices,
                reasons=reasons,
                confidence=1.0,
                tag="[VIDEO 1]",
                metadata={"direction": "SELL", "coach_lesson": "That pullback wasn't your entry. It was bait.", "entry": entry_price, "sl": stop_loss, "tp": take_profit}
            )

    return SkillResult(status="HOLD", level_prices=level_prices, reasons=["Waiting for inducement OB setup conditions [VIDEO 1]"], tag="[VIDEO 1]")
