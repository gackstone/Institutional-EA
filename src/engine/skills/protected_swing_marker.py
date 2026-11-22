"""
Skill: protected_swing_marker [VIDEO 3]
Identifies the true protected structural low (bullish) or high (bearish).
Filters out minor fractal noise; only marks the swing that started the move that broke structure.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from src.core.contracts import Candle
from src.engine.types import SkillResult, Context, normalize_to_candles


def evaluate(data: Any, ctx: Context) -> SkillResult:
    """
    Evaluates completed candles to locate the active protected swing.
    Bullish: The swing low that started the impulse that closed above the prior swing high.
    Bearish: The swing high that started the impulse that closed below the prior swing low.
    [VIDEO 3]
    """
    candles: List[Candle] = normalize_to_candles(data)
    if len(candles) < 5:
        return SkillResult(
            status="FAIL",
            reasons=["Insufficient closed candles for protected swing identification"],
            confidence=0.0,
            tag="[VIDEO 3]",
        )

    # 1. Identify local swing pivots using lookback window
    default_k = min(3, max(1, (len(candles) - 2) // 3))
    k = int(ctx.parameters.get("swing_lookback", default_k))
    pivots: List[Tuple[int, str, float, Candle]] = [] # (index, "HIGH"|"LOW", price, candle)

    for i in range(k, len(candles) - k):
        c = candles[i]
        is_high = all(c.high > candles[j].high for j in range(i - k, i)) and \
                  all(c.high >= candles[j].high for j in range(i + 1, i + k + 1))
        if is_high:
            pivots.append((i, "HIGH", c.high, c))

        is_low = all(c.low < candles[j].low for j in range(i - k, i)) and \
                 all(c.low <= candles[j].low for j in range(i + 1, i + k + 1))
        if is_low:
            pivots.append((i, "LOW", c.low, c))

    # Sort pivots by index
    pivots.sort(key=lambda x: x[0])

    protected_low: Optional[float] = None
    protected_high: Optional[float] = None
    bos_level: Optional[float] = None
    bos_time: Optional[datetime] = None
    reasons: List[str] = []

    # 2. Find confirmed body-close BOS events to determine protected low / high
    # Bullish: price closes above a previous swing high. The lowest low between that swing high and the BOS is the protected low [VIDEO 3]
    high_pivots = [p for p in pivots if p[1] == "HIGH"]
    low_pivots = [p for p in pivots if p[1] == "LOW"]

    # Bullish scan: check recent high pivots broken by candle body close
    for h_idx, _, h_price, h_candle in reversed(high_pivots):
        # Look for subsequent candle body close above h_price
        for c_idx in range(h_idx + 1, len(candles)):
            c = candles[c_idx]
            if c.close > h_price:
                # BOS confirmed! [VIDEO 3, 4]
                # Find the swing low that started this move (lowest low between h_idx and c_idx)
                leg_lows = [candles[j].low for j in range(h_idx, c_idx + 1)]
                if leg_lows:
                    min_leg_low = min(leg_lows)
                    protected_low = min_leg_low
                    bos_level = h_price
                    bos_time = c.time
                    reasons.append(
                        f"Protected Low marked at {protected_low:.5f} preceding BOS above {bos_level:.5f} at {bos_time.isoformat()} [VIDEO 3]"
                    )
                    break
        if protected_low is not None:
            break

    # Bearish scan: check recent low pivots broken by candle body close
    for l_idx, _, l_price, l_candle in reversed(low_pivots):
        for c_idx in range(l_idx + 1, len(candles)):
            c = candles[c_idx]
            if c.close < l_price:
                # Bearish BOS confirmed!
                leg_highs = [candles[j].high for j in range(l_idx, c_idx + 1)]
                if leg_highs:
                    max_leg_high = max(leg_highs)
                    protected_high = max_leg_high
                    bos_level = l_price
                    bos_time = c.time
                    reasons.append(
                        f"Protected High marked at {protected_high:.5f} preceding BOS below {bos_level:.5f} at {bos_time.isoformat()} [VIDEO 3]"
                    )
                    break
        if protected_high is not None:
            break

    # Update context
    if protected_low is not None:
        ctx.protected_low = protected_low
        ctx.bos_level = bos_level
        ctx.bos_time = bos_time
    if protected_high is not None:
        ctx.protected_high = protected_high

    levels: Dict[str, float] = {}
    if protected_low is not None:
        levels["protected_low"] = protected_low
    if protected_high is not None:
        levels["protected_high"] = protected_high
    if bos_level is not None:
        levels["bos_level"] = bos_level

    status = "PASS" if (protected_low is not None or protected_high is not None) else "HOLD"
    if not reasons:
        reasons.append("No confirmed body-close BOS found; protected swings undefined [VIDEO 3]")

    return SkillResult(
        status=status,
        level_prices=levels,
        reasons=reasons,
        confidence=1.0 if status == "PASS" else 0.5,
        tag="[VIDEO 3]",
        metadata={
            "coach_lesson": "Mark the low that broke something.",
            "protected_low": protected_low,
            "protected_high": protected_high,
            "bos_level": bos_level,
            "bos_time": bos_time.isoformat() if bos_time else None,
        }
    )
