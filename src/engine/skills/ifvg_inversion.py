"""
Skill: ifvg_inversion [VIDEO 8]
Identifies Inversion Fair Value Gap (IFVG) setups.
A close through an FVG does not kill it; old support becomes resistance.
Trigger: confirmation candle dropping away after inversion retest close.
Invalidation: candle closes back above/inside the gap (trap).
Stop loss: beyond far edge of gap [ASSUMPTION].
Target: next opposing liquidity [ASSUMPTION].
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from src.core.contracts import Candle
from src.engine.types import SkillResult, Context, normalize_to_candles


def evaluate(data: Any, ctx: Context) -> SkillResult:
    """
    Evaluates closed candles for an Inversion FVG setup.
    [VIDEO 8]
    """
    candles: List[Candle] = normalize_to_candles(data)
    if len(candles) < 5:
        return SkillResult(status="FAIL", reasons=["Need at least 5 bars for IFVG evaluation"], tag="[VIDEO 8]")

    reasons: List[str] = []
    level_prices: Dict[str, float] = {}

    # Example shown in Video 8: Bullish FVG broken downward -> flips to Bearish IFVG resistance
    # Look back for an FVG that was subsequently broken by a closed candle
    fvg_top: Optional[float] = None
    fvg_bottom: Optional[float] = None
    break_idx: Optional[int] = None

    for i in range(2, len(candles) - 2):
        c1 = candles[i - 2]
        c3 = candles[i]
        # Bullish FVG
        if c3.low > c1.high:
            b_top = c3.low
            b_bottom = c1.high
            # Check if broken by candle close below b_bottom
            for k in range(i + 1, len(candles) - 1):
                if candles[k].close < b_bottom:
                    fvg_top = b_top
                    fvg_bottom = b_bottom
                    break_idx = k
                    break
        if break_idx is not None:
            break

    if fvg_top is None or fvg_bottom is None or break_idx is None:
        return SkillResult(status="HOLD", reasons=["No broken FVG identified for inversion retest [VIDEO 8]"], tag="[VIDEO 8]")

    level_prices["ifvg_top"] = fvg_top
    level_prices["ifvg_bottom"] = fvg_bottom

    # Evaluate candles after the break for retest into the gap zone
    retest_candle: Optional[Candle] = None
    retest_idx: Optional[int] = None
    for m in range(break_idx + 1, len(candles) - 1):
        c = candles[m]
        # Pushes into gap (high >= fvg_bottom) but closes back below it (close <= fvg_bottom) [VIDEO 8]
        if c.high >= fvg_bottom and c.close <= fvg_bottom:
            retest_candle = c
            retest_idx = m
            break

    if retest_candle is None:
        return SkillResult(status="HOLD", level_prices=level_prices, reasons=["Awaiting price retest into broken gap zone [VIDEO 8]"], tag="[VIDEO 8]")

    # Confirmation candle: candle following retest drops away (bearish close) [VIDEO 8]
    confirmation_candle = candles[-1]

    # Invalidation check: candle closes back above the gap -> trap, buyers back in control [VIDEO 8]
    if confirmation_candle.close > fvg_bottom:
        reasons.append(
            f"INVERSION TRAP: Candle closed back above gap ({confirmation_candle.close:.5f} > {fvg_bottom:.5f}). Break was a trap [VIDEO 8]"
        )
        return SkillResult(status="TRAP", level_prices=level_prices, reasons=reasons, confidence=0.0, tag="[VIDEO 8]")

    # Confirmation: drops away with bearish close [VIDEO 8]
    if confirmation_candle.close < retest_candle.close and confirmation_candle.close < confirmation_candle.open:
        entry_price = confirmation_candle.close
        stop_loss = fvg_top + (ctx.pip_size * 2) # [ASSUMPTION: stop above far edge of gap]
        # Target: next opposing sell-side liquidity or recent swing low [ASSUMPTION]
        target = min((c.low for c in candles[break_idx:]), default=entry_price - (stop_loss - entry_price) * 1.5)
        level_prices["entry"] = entry_price
        level_prices["stop_loss"] = stop_loss
        level_prices["take_profit"] = target

        reasons.append(
            f"TRIGGERED: IFVG inversion confirmed. Gap [{fvg_bottom:.5f} - {fvg_top:.5f}] retested and held as resistance; confirmation candle dropped away to {entry_price:.5f}. SL={stop_loss:.5f}, TP={target:.5f} [VIDEO 8]"
        )
        return SkillResult(
            status="TRIGGERED",
            level_prices=level_prices,
            reasons=reasons,
            confidence=1.0,
            tag="[VIDEO 8]",
            metadata={
                "direction": "SELL",
                "coach_lesson": "Same zone, same return. The close decides. A failed FVG isn't finished, it just changed sides.",
                "entry": entry_price,
                "sl": stop_loss,
                "tp": target,
            }
        )
    else:
        reasons.append("Retest into inverted FVG observed; awaiting confirmation candle dropping away [VIDEO 8]")
        return SkillResult(status="HOLD", level_prices=level_prices, reasons=reasons, confidence=0.5, tag="[VIDEO 8]")
