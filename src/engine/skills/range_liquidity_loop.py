"""
External vs Internal Range Liquidity Loop [ART-03].
Implements the institutional liquidity delivery loop:
- External Range Liquidity (ERL): Stops outside the active range (EQH/EQL, PDH/PDL, PWH/PWL).
- Internal Range Liquidity (IRL): Imbalances (FVGs) and minor swings inside the range.
- Delivery Rule: From ERL, price tends to draw back to IRL (rebalance); from IRL, price draws out to ERL (next pool).
- Caveat [ART-03]: A tendency, not a law. Sometimes price skips the gap, sometimes fills it and continues running.
- Exposes next_draw for entry planning (return into IRL gap) and take-profit targets (opposing ERL).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from src.core.contracts import Candle
from src.engine.types import SkillResult, Context, normalize_to_candles


def evaluate(candles_data: Sequence[Union[Candle, dict, Any]], ctx: Context) -> SkillResult:
    """Evaluates ERL vs IRL liquidity loop and resolves the next draw [ART-03]."""
    candles = normalize_to_candles(candles_data)
    if not candles:
        return SkillResult(
            status="INSUFFICIENT_DATA",
            passed=False,
            reasons=["No closed candles available for range liquidity loop evaluation [ART-03]"],
            tags=["[ART-03]"],
        )

    cur_close = candles[-1].close
    range_high = ctx.parameters.get("range_high") or max(c.high for c in candles[-30:])
    range_low = ctx.parameters.get("range_low") or min(c.low for c in candles[-30:])

    # Check for unmitigated IRL gaps inside the active range
    unmitigated_irl_gap: Optional[float] = ctx.parameters.get("fvg_midpoint")
    nearest_bsl: Optional[float] = ctx.parameters.get("nearest_bsl")
    nearest_ssl: Optional[float] = ctx.parameters.get("nearest_ssl")

    # Determine next draw based on position relative to range
    # Bullish trend / setup: if price was at external lows, next draw is internal IRL gap; once mitigated, next draw is ERL high
    draw_type = "ERL"
    next_draw_price = range_high
    reasons: List[str] = []

    if ctx.trend == "BULL":
        if unmitigated_irl_gap and cur_close < unmitigated_irl_gap:
            draw_type = "IRL_GAP"
            next_draw_price = unmitigated_irl_gap
            reasons.append(f"Next draw is Internal Range Liquidity (IRL gap at {unmitigated_irl_gap:.5f}) [ART-03]")
        else:
            draw_type = "ERL_HIGH"
            next_draw_price = nearest_bsl if nearest_bsl else range_high
            reasons.append(f"Internal gap mitigated; next draw is External Range Liquidity (ERL high at {next_draw_price:.5f}) [ART-03]")
    elif ctx.trend == "BEAR":
        if unmitigated_irl_gap and cur_close > unmitigated_irl_gap:
            draw_type = "IRL_GAP"
            next_draw_price = unmitigated_irl_gap
            reasons.append(f"Next draw is Internal Range Liquidity (IRL gap at {unmitigated_irl_gap:.5f}) [ART-03]")
        else:
            draw_type = "ERL_LOW"
            next_draw_price = nearest_ssl if nearest_ssl else range_low
            reasons.append(f"Internal gap mitigated; next draw is External Range Liquidity (ERL low at {next_draw_price:.5f}) [ART-03]")
    else:
        # Range / transition: draw to nearest edge
        dist_to_high = abs(range_high - cur_close)
        dist_to_low = abs(cur_close - range_low)
        if dist_to_high <= dist_to_low:
            draw_type = "ERL_HIGH"
            next_draw_price = range_high
        else:
            draw_type = "ERL_LOW"
            next_draw_price = range_low
        reasons.append(f"In range; next draw is nearest boundary ({draw_type} at {next_draw_price:.5f}) [ART-03]")

    reasons.append("Caveat: From external to internal, from internal to external is a tendency, not a law [ART-03]")

    levels = {
        "range_high": range_high,
        "range_low": range_low,
        "next_draw_price": next_draw_price,
    }
    ctx.parameters["next_draw_price"] = next_draw_price
    ctx.parameters["draw_type"] = draw_type

    return SkillResult(
        status="ACTIVE",
        passed=True,
        level_prices=levels,
        reasons=reasons,
        confidence=0.85,
        tags=["[ART-03]"],
        metadata={
            "draw_type": draw_type,
            "next_draw_price": next_draw_price,
            "coach_lesson": "From external to internal, from internal to external. A tendency, not a law.",
        }
    )
