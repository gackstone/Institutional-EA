"""
Skill: stop_management_policy [VIDEO 12]
Manages open position Stop Loss during trade lifecycle.
Forbids moving Stop Loss to break even prematurely (+1.0R / +0.5R early BE churn).
The setup didn't fail. The trade management did.
Move your stop when the market gives you a reason, not just because you're finally in profit.
Rules:
- be_move_mode = "structure_only" (default) [VIDEO 12]
- Stop Loss trails ONLY when a new structural level forms that would invalidate the idea if broken
  (e.g., a newly formed protected low above entry after a confirmed BOS) [DERIVED].
- Fixed-R break-even retained only as an optional, off-by-default mode [ASSUMPTION].
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from src.core.contracts import Candle, Position, OrderType
from src.engine.types import SkillResult, Context, normalize_to_candles


def evaluate(data: Any, ctx: Context) -> SkillResult:
    """
    Evaluates whether an open position's Stop Loss should be trailed to a new structural level.
    [VIDEO 12]
    """
    candles: List[Candle] = normalize_to_candles(data)

    open_price = float(ctx.parameters.get("position_open_price", 0.0))
    current_sl = float(ctx.parameters.get("position_current_sl", 0.0))
    direction = ctx.parameters.get("position_direction", "BUY") # "BUY" or "SELL"
    be_mode = ctx.parameters.get("be_move_mode", "structure_only") # [VIDEO 12]
    enable_fixed_r = bool(ctx.parameters.get("enable_fixed_r_be", False)) # [ASSUMPTION: default false]

    reasons: List[str] = []
    level_prices: Dict[str, float] = {
        "open_price": open_price,
        "current_sl": current_sl,
    }

    if open_price <= 0:
        return SkillResult(status="FAIL", reasons=["No open position price provided"], tag="[VIDEO 12]")

    # Check 1: Fixed-R break-even (disabled by default per Video 12)
    if enable_fixed_r and be_mode == "fixed_r":
        r_dist = abs(open_price - current_sl)
        current_price = ctx.current_price or (candles[-1].close if candles else open_price)
        threshold_r = float(ctx.parameters.get("fixed_r_be_threshold", 1.0))
        current_r = (current_price - open_price) / r_dist if direction == "BUY" else (open_price - current_price) / r_dist

        if current_r >= threshold_r:
            new_sl = open_price + (ctx.pip_size * 2) if direction == "BUY" else open_price - (ctx.pip_size * 2)
            level_prices["new_sl"] = new_sl
            reasons.append(
                f"Fixed-R BE triggered at +{current_r:.2f}R (New SL: {new_sl:.5f}) [ASSUMPTION]"
            )
            return SkillResult(status="MODIFY_SL", level_prices=level_prices, reasons=reasons, tag="[ASSUMPTION]")

    # Check 2: Structure-Only trailing policy (Canonical AlgoVistra Video 12)
    # Trail SL ONLY when a new protected swing has formed after a confirmed BOS
    new_protected_low = ctx.protected_low
    new_protected_high = ctx.protected_high

    if direction == "BUY" and new_protected_low is not None:
        # A new protected low has formed above the original/current stop loss
        if new_protected_low > current_sl and new_protected_low > open_price:
            new_sl = new_protected_low - (ctx.pip_size * 2) # [DERIVED]
            level_prices["new_sl"] = new_sl
            reasons.append(
                f"STRUCTURAL SL TRAIL: Confirmed new protected low formed at {new_protected_low:.5f} above entry {open_price:.5f} after BOS. Trail SL to {new_sl:.5f} [VIDEO 12, DERIVED]"
            )
            return SkillResult(
                status="MODIFY_SL",
                level_prices=level_prices,
                reasons=reasons,
                confidence=1.0,
                tag="[VIDEO 12]",
                metadata={
                    "coach_lesson": "Move your stop when the market gives you a reason, not just because you're finally in profit.",
                    "new_sl": new_sl,
                    "structural_anchor": new_protected_low,
                }
            )

    elif direction == "SELL" and new_protected_high is not None:
        if (current_sl <= 0 or new_protected_high < current_sl) and new_protected_high < open_price:
            new_sl = new_protected_high + (ctx.pip_size * 2)
            level_prices["new_sl"] = new_sl
            reasons.append(
                f"STRUCTURAL SL TRAIL: Confirmed new protected high formed at {new_protected_high:.5f} below entry {open_price:.5f} after BOS. Trail SL to {new_sl:.5f} [VIDEO 12, DERIVED]"
            )
            return SkillResult(
                status="MODIFY_SL",
                level_prices=level_prices,
                reasons=reasons,
                confidence=1.0,
                tag="[VIDEO 12]",
                metadata={"coach_lesson": "Move your stop when the market gives you a reason, not just because you're finally in profit.", "new_sl": new_sl, "structural_anchor": new_protected_high}
            )

    reasons.append(
        "HOLD SL: No new structural protected swing formed yet. Retain original stop below structural invalidation; avoid premature BE churn [VIDEO 12]"
    )
    return SkillResult(
        status="HOLD",
        level_prices=level_prices,
        reasons=reasons,
        confidence=1.0,
        tag="[VIDEO 12]",
        metadata={"coach_lesson": "Move your stop when the market gives you a reason, not just because you're finally in profit."}
    )
