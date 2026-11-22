"""
IPDA Delivery Lens Context [ART-05].
Provides an institutional perspective on price action:
- Moves are labeled as either SEEKING_LIQUIDITY (reaching for resting stops above old highs/below old lows)
  or REBALANCING (trading into an existing Fair Value Gap).
- Loop: Take liquidity outside the range, rebalance inside it, reach for the next pool.
- Caveat [ART-05]: Nobody outside can prove an algorithm exists; you do not have to believe it to use the lens.
- Guard: Lens only for logs and coach explanations; NEVER a mechanical entry rule!
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Sequence, Union

from src.core.contracts import Candle
from src.engine.types import SkillResult, Context, normalize_to_candles


def evaluate(candles_data: Sequence[Union[Candle, dict, Any]], ctx: Context) -> SkillResult:
    """Labels market delivery state as SEEKING_LIQUIDITY or REBALANCING [ART-05]."""
    candles = normalize_to_candles(candles_data)
    if not candles:
        return SkillResult(
            status="INSUFFICIENT_DATA",
            passed=False,
            reasons=["No closed candles available for IPDA lens labeling [ART-05]"],
            tags=["[ART-05]"],
        )

    cur_close = candles[-1].close
    fvg_mid = ctx.parameters.get("fvg_midpoint")
    nearest_bsl = ctx.parameters.get("nearest_bsl")
    nearest_ssl = ctx.parameters.get("nearest_ssl")

    mode = "SEEKING_LIQUIDITY"
    target_price = cur_close

    if fvg_mid and abs(cur_close - fvg_mid) < (abs(cur_close - (nearest_bsl or cur_close))):
        mode = "REBALANCING"
        target_price = fvg_mid
    else:
        target_price = nearest_bsl if ctx.trend == "BULL" else (nearest_ssl or cur_close)

    reasons = [
        f"Delivery Lens: Price is currently {mode} (target {target_price:.5f}) [ART-05]",
        "Lens only: Used for trade journaling, telemetry, and coach dialogue [ART-05]",
        "Caveat: Nobody outside can prove an algorithm exists. Not presented as established fact [ART-05]"
    ]

    return SkillResult(
        status=mode,
        passed=True,
        level_prices={"delivery_target": target_price},
        reasons=reasons,
        confidence=0.80,
        tags=["[ART-05]"],
        metadata={
            "delivery_mode": mode,
            "coach_lesson": "Ask what price is reaching for.",
        }
    )
