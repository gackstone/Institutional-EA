"""
Skill: structure_momentum_monitor [VIDEO 15]
Monitors structural momentum across successive impulse legs.
New HH != strong trend.
When successive impulse pushes contract, momentum is DECAYING.
Effects [DERIVED]:
- Reduce confidence / position size or block new continuation breakout entries.
- Do NOT flip trend until CHOCH (body close through protected low).
Caution flag only; not an automatic reversal trigger.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from src.core.contracts import Candle
from src.engine.types import SkillResult, Context, normalize_to_candles


def evaluate(data: Any, ctx: Context) -> SkillResult:
    """
    Measures consecutive impulse leg expansions to detect momentum decay.
    [VIDEO 15]
    """
    candles: List[Candle] = normalize_to_candles(data)
    if len(candles) < 4:
        return SkillResult(status="PASS", reasons=["Insufficient bars for momentum monitoring"], tag="[VIDEO 15]")

    # Identify swing pivots to measure consecutive impulse legs
    k = ctx.parameters.get("swing_lookback", 3)
    pivots: List[Tuple[int, str, float]] = []

    for i in range(k, len(candles) - k):
        c = candles[i]
        is_high = all(c.high > candles[j].high for j in range(i - k, i)) and \
                  all(c.high >= candles[j].high for j in range(i + 1, i + k + 1))
        if is_high:
            pivots.append((i, "HIGH", c.high))

        is_low = all(c.low < candles[j].low for j in range(i - k, i)) and \
                 all(c.low <= candles[j].low for j in range(i + 1, i + k + 1))
        if is_low:
            pivots.append((i, "LOW", c.low))

    pivots.sort(key=lambda x: x[0])

    trend = ctx.trend
    reasons: List[str] = []
    level_prices: Dict[str, float] = {}
    momentum_state = "NORMAL"
    decaying_count_threshold = int(ctx.parameters.get("decaying_legs_count", 2)) # [ASSUMPTION]

    if trend == "BULL" or (not trend and len(pivots) >= 4):
        # Measure bullish impulse legs: from low to subsequent high
        impulse_lengths: List[float] = []
        for i in range(len(pivots) - 1):
            if pivots[i][1] == "LOW" and pivots[i + 1][1] == "HIGH":
                length = pivots[i + 1][2] - pivots[i][2]
                if length > 0:
                    impulse_lengths.append(length)

        level_prices["recent_leg_count"] = float(len(impulse_lengths))
        if len(impulse_lengths) >= 2:
            # Check if last 2-3 legs are shrinking
            recent = impulse_lengths[- (decaying_count_threshold + 1):]
            is_shrinking = all(recent[i] < recent[i - 1] for i in range(1, len(recent)))

            level_prices["last_impulse"] = recent[-1]
            level_prices["prev_impulse"] = recent[-2]

            if is_shrinking:
                momentum_state = "DECAYING"
                reasons.append(
                    f"DECAYING MOMENTUM: Last {len(recent)} successive bullish impulse pushes are shrinking ({', '.join(f'{x:.5f}' for x in recent)}). Trend may end or enter big correction [VIDEO 15]"
                )
                reasons.append("Caution: Trend remains bullish until CHOCH; block new continuation breakouts or scale size down [VIDEO 15, DERIVED]")
                return SkillResult(
                    status="DECAYING",
                    level_prices=level_prices,
                    reasons=reasons,
                    confidence=0.5,
                    tag="[VIDEO 15]",
                    metadata={
                        "coach_lesson": "New higher high doesn't mean strong trend. Look at the size of the push.",
                        "momentum": "DECAYING",
                        "impulse_lengths": recent,
                    }
                )

    elif trend == "BEAR":
        impulse_lengths = []
        for i in range(len(pivots) - 1):
            if pivots[i][1] == "HIGH" and pivots[i + 1][1] == "LOW":
                length = pivots[i][2] - pivots[i + 1][2]
                if length > 0:
                    impulse_lengths.append(length)

        level_prices["recent_leg_count"] = float(len(impulse_lengths))
        if len(impulse_lengths) >= 2:
            recent = impulse_lengths[- (decaying_count_threshold + 1):]
            is_shrinking = all(recent[i] < recent[i - 1] for i in range(1, len(recent)))
            if is_shrinking:
                momentum_state = "DECAYING"
                reasons.append(
                    f"DECAYING MOMENTUM: Last {len(recent)} successive bearish impulse pushes are shrinking. Block continuation breakdowns [VIDEO 15]"
                )
                return SkillResult(
                    status="DECAYING",
                    level_prices=level_prices,
                    reasons=reasons,
                    confidence=0.5,
                    tag="[VIDEO 15]",
                    metadata={
                        "coach_lesson": "New lower low doesn't mean strong trend. Look at the size of the push.",
                        "momentum": "DECAYING",
                        "impulse_lengths": recent,
                    }
                )

    reasons.append("Impulse pushes show healthy expansion; momentum intact [VIDEO 15]")
    return SkillResult(
        status="PASS",
        level_prices=level_prices,
        reasons=reasons,
        confidence=1.0,
        tag="[VIDEO 15]",
        metadata={
            "coach_lesson": "New higher high doesn't mean strong trend. Look at the size of the push.",
            "momentum": "NORMAL"
        }
    )
