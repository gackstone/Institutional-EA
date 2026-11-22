"""
Skill: breakout_trap_classifier [VIDEO 6]
Classifies price interaction with key swing levels / range boundaries.
A trap comes back inside. A breakout stays outside.
- PENDING: 1 close beyond level. Breakout entries blocked.
- BREAKOUT_CONFIRMED: 2 consecutive closed candles beyond level.
- TRAP: Candle pierced level but closed back inside. Serves as sweep context for other skills.
All decisions use closed candles only.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from src.core.contracts import Candle
from src.engine.types import SkillResult, Context, normalize_to_candles


def evaluate(data: Any, ctx: Context) -> SkillResult:
    """
    Evaluates closed candles against a reference resistance or support level.
    [VIDEO 6]
    """
    candles: List[Candle] = normalize_to_candles(data)
    if len(candles) < 2:
        return SkillResult(
            status="PENDING",
            reasons=["Need at least 2 closed candles to evaluate breakout vs trap confirmation"],
            tag="[VIDEO 6]"
        )

    # Reference level: high or low being tested
    level = ctx.parameters.get("test_level")
    side = ctx.parameters.get("test_side", "HIGH") # "HIGH" or "LOW"

    if level is None:
        # Default to previous swing high/low if not explicitly specified
        if side == "HIGH":
            level = max((c.high for c in candles[:-2]), default=candles[-2].high)
        else:
            level = min((c.low for c in candles[:-2]), default=candles[-2].low)

    c_penultimate = candles[-2]
    c_last = candles[-1]

    reasons: List[str] = []
    level_prices: Dict[str, float] = {
        "test_level": level,
        "penultimate_close": c_penultimate.close,
        "last_close": c_last.close,
    }

    if side == "HIGH":
        # Testing resistance / high level
        pierced = c_penultimate.high > level or c_last.high > level
        if not pierced:
            return SkillResult(status="PENDING", level_prices=level_prices, reasons=["Level has not been pierced"], tag="[VIDEO 6]")

        # Check for TRAP: pierced above, but closed back inside (<= level) [VIDEO 6]
        if c_last.close <= level and (c_last.high > level or c_penultimate.high > level):
            status = "TRAP"
            confidence = 1.0
            reasons.append(
                f"TRAP confirmed: Price ran above {level:.5f} but closed back inside ({c_last.close:.5f} <= {level:.5f}). Breakout buyers trapped [VIDEO 6]"
            )
        # Check for BREAKOUT_CONFIRMED: two consecutive body closes above level [VIDEO 6]
        elif c_penultimate.close > level and c_last.close > level:
            status = "BREAKOUT_CONFIRMED"
            confidence = 1.0
            reasons.append(
                f"BREAKOUT_CONFIRMED: Two consecutive candles closed above {level:.5f} (c1={c_penultimate.close:.5f}, c2={c_last.close:.5f}). Old high now support [VIDEO 6]"
            )
        # 1 close above level, awaiting second close
        elif c_last.close > level:
            status = "PENDING"
            confidence = 0.5
            reasons.append(
                f"PENDING: Only 1 candle closed above {level:.5f} ({c_last.close:.5f}). Awaiting 2nd close confirmation before approving breakout [VIDEO 6]"
            )
        else:
            status = "PENDING"
            reasons.append(f"Price interacting with {level:.5f}; awaiting closed-candle resolution [VIDEO 6]")

    else:
        # Testing support / low level (bearish mirror)
        pierced = c_penultimate.low < level or c_last.low < level
        if not pierced:
            return SkillResult(status="PENDING", level_prices=level_prices, reasons=["Level has not been pierced"], tag="[VIDEO 6]")

        # Check for TRAP: pierced below, but closed back inside (>= level) [VIDEO 6]
        if c_last.close >= level and (c_last.low < level or c_penultimate.low < level):
            status = "TRAP"
            confidence = 1.0
            reasons.append(
                f"TRAP confirmed: Price ran below {level:.5f} but closed back inside ({c_last.close:.5f} >= {level:.5f}). Breakdown sellers trapped [VIDEO 6]"
            )
        # Check for BREAKOUT_CONFIRMED: two consecutive body closes below level [VIDEO 6]
        elif c_penultimate.close < level and c_last.close < level:
            status = "BREAKOUT_CONFIRMED"
            confidence = 1.0
            reasons.append(
                f"BREAKOUT_CONFIRMED: Two consecutive candles closed below {level:.5f} (c1={c_penultimate.close:.5f}, c2={c_last.close:.5f}). Old low now resistance [VIDEO 6]"
            )
        elif c_last.close < level:
            status = "PENDING"
            confidence = 0.5
            reasons.append(
                f"PENDING: Only 1 candle closed below {level:.5f} ({c_last.close:.5f}). Awaiting 2nd close confirmation before approving breakdown [VIDEO 6]"
            )
        else:
            status = "PENDING"
            reasons.append(f"Price interacting with {level:.5f}; awaiting closed-candle resolution [VIDEO 6]")

    return SkillResult(
        status=status,
        level_prices=level_prices,
        reasons=reasons,
        confidence=confidence,
        tag="[VIDEO 6]",
        metadata={
            "coach_lesson": "A trap comes back inside. A breakout stays outside.",
            "side": side,
            "test_level": level,
        }
    )
