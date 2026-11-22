"""
Skill: entry_quality_guard [VIDEO 14]
Enforces entry quality and anti-chasing guardrails from real fill price.
Right direction, bad entry.
Never chase an extended move.
Calculates live metrics from actual fill price:
- risk = |entry - invalidation|
- room = |target - entry|
- rr = room / risk
Rejects order if:
- rr < min_rr (default 1.5) [ASSUMPTION]
- entry is extended > max_extension (1.0 * planned risk) from the trigger level [ASSUMPTION]
Strictly forbids widening the stop loss to make R:R fit.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from src.core.contracts import Candle
from src.engine.types import SkillResult, Context, normalize_to_candles


def evaluate(data: Any, ctx: Context) -> SkillResult:
    """
    Evaluates order execution sanity from actual entry price.
    [VIDEO 14]
    """
    candles: List[Candle] = normalize_to_candles(data)

    entry_price = float(ctx.parameters.get("entry_price") or ctx.current_price or (candles[-1].close if candles else 0.0))
    invalidation = float(ctx.parameters.get("invalidation_price") or 0.0)
    target = float(ctx.parameters.get("target_price") or 0.0)
    trigger_level = float(ctx.parameters.get("trigger_level") or entry_price)

    min_rr = float(ctx.parameters.get("min_rr", 1.5)) # [ASSUMPTION]
    max_extension_factor = float(ctx.parameters.get("max_extension_factor", 1.0)) # [ASSUMPTION]

    reasons: List[str] = []
    level_prices: Dict[str, float] = {
        "entry_price": entry_price,
        "invalidation_price": invalidation,
        "target_price": target,
        "trigger_level": trigger_level,
    }

    if invalidation <= 0:
        reasons.append("REJECTED: No valid invalidation / stop loss price provided [VIDEO 14]")
        return SkillResult(status="FAIL", level_prices=level_prices, reasons=reasons, confidence=0.0, tag="[VIDEO 14]")

    risk = abs(entry_price - invalidation)
    if risk <= 0:
        reasons.append("REJECTED: Risk distance is zero [VIDEO 14]")
        return SkillResult(status="FAIL", level_prices=level_prices, reasons=reasons, confidence=0.0, tag="[VIDEO 14]")

    room = abs(target - entry_price) if target > 0 else 0.0
    rr = room / risk if risk > 0 else 0.0

    level_prices["risk"] = risk
    level_prices["room"] = room
    level_prices["rr"] = rr

    # Check 1: Late entry / extension check [VIDEO 14]
    drift = abs(entry_price - trigger_level)
    max_allowed_extension = risk * max_extension_factor
    level_prices["drift"] = drift
    level_prices["max_allowed_extension"] = max_allowed_extension

    if drift > max_allowed_extension:
        reasons.append(
            f"REJECTED (Chasing): Entry has moved up/down {drift:.5f} away from trigger level {trigger_level:.5f} (> max extension {max_allowed_extension:.5f}). Don't chase the move [VIDEO 14]"
        )
        return SkillResult(
            status="FAIL",
            level_prices=level_prices,
            reasons=reasons,
            confidence=0.0,
            tag="[VIDEO 14]",
            metadata={"coach_lesson": "Right direction, bad entry. Don't chase the move; wait for a new setup or let it go."}
        )

    # Check 2: Minimum Reward-to-Risk check from actual fill price [VIDEO 14]
    if rr < min_rr:
        reasons.append(
            f"REJECTED (Poor R:R): Live Reward-to-Risk {rr:.2f} is below minimum {min_rr:.2f} (risk={risk:.5f}, room={room:.5f}). Never widen stop loss to force R:R [VIDEO 14]"
        )
        return SkillResult(
            status="FAIL",
            level_prices=level_prices,
            reasons=reasons,
            confidence=0.0,
            tag="[VIDEO 14]",
            metadata={"coach_lesson": "Right direction, bad entry. Don't chase the move; wait for a new setup or let it go."}
        )

    reasons.append(
        f"APPROVED: Entry sanity passed. Risk={risk:.5f}, Room={room:.5f}, Live R:R={rr:.2f} >= {min_rr:.2f} [VIDEO 14]"
    )
    return SkillResult(
        status="PASS",
        level_prices=level_prices,
        reasons=reasons,
        confidence=1.0,
        tag="[VIDEO 14]",
        metadata={
            "coach_lesson": "Right direction, bad entry. Don't chase the move; wait for a new setup or let it go.",
            "rr": rr,
            "risk": risk,
            "room": room,
        }
    )
