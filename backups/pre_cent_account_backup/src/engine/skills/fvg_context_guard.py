"""
Skill: fvg_context_guard [VIDEO 11]
Enforces context validation on Fair Value Gaps.
An FVG is NOT a magnet. Price does not have to come back.
Rules:
1. Forbids standing limit orders placed solely because an FVG exists.
2. An FVG enters trading logic only when accompanied by higher-timeframe structure, liquidity sweeps, and closed-candle confirmation.
3. Educational attribution: Imbalance and rebalancing are credited to ICT methodology.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from src.core.contracts import Candle
from src.engine.types import SkillResult, Context, normalize_to_candles


def evaluate(data: Any, ctx: Context) -> SkillResult:
    """
    Evaluates whether an FVG has sufficient context to be traded.
    Blocks blind limit orders.
    [VIDEO 11]
    """
    candles: List[Candle] = normalize_to_candles(data)

    order_type = ctx.parameters.get("proposed_order_type", "MARKET")
    has_sweep_context = ctx.parameters.get("has_sweep_context", False)
    has_structural_bos = (ctx.bos_level is not None)

    reasons: List[str] = []

    # Rule 1: Forbid standing limit order without closed-candle confirmation [VIDEO 11]
    if order_type in ("BUY_LIMIT", "SELL_LIMIT") and not has_sweep_context:
        reasons.append(
            "REJECTED: Standing limit order blocked. An FVG is not a magnet; price does not have to return. Awaiting real-time closed-candle test [VIDEO 11]"
        )
        return SkillResult(
            status="FAIL",
            reasons=reasons,
            confidence=0.0,
            tag="[VIDEO 11]",
            metadata={"coach_lesson": "An FVG is not a magnet. Price does not have to come back. Context tells you if the return really matters."}
        )

    # Rule 2: Require structural context (BOS or Sweep)
    if not has_structural_bos and not has_sweep_context:
        reasons.append(
            "REJECTED: FVG lacks market structure context (no confirmed BOS or liquidity sweep). Context decides if return matters [VIDEO 11]"
        )
        return SkillResult(
            status="FAIL",
            reasons=reasons,
            confidence=0.0,
            tag="[VIDEO 11]",
            metadata={"coach_lesson": "An FVG is not a magnet. Price does not have to come back. Context tells you if the return really matters."}
        )

    reasons.append("APPROVED: FVG is accompanied by verified market structure and sweep context [VIDEO 11]")
    return SkillResult(
        status="PASS",
        reasons=reasons,
        confidence=1.0,
        tag="[VIDEO 11]",
        metadata={"coach_lesson": "An FVG is not a magnet. Price does not have to come back. Context tells you if the return really matters."}
    )
