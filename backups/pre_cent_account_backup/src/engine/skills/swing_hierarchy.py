"""
Swing Hierarchy Engine [ART-02].
Implements 3-tier recursive fractal swing ranking:
- Rank 1: Short-Term High / Low (STH / STL): candle with lower high (or higher low) on each side (n=1).
- Rank 2: Intermediate-Term High / Low (ITH / ITL): an STH with lower STH on each side.
- Rank 3: Long-Term High / Low (LTH / LTL): an ITH with lower ITH on each side.
Confirmation Lag: Each rank requires the subsequent swing to confirm it (the bigger the high, the later you know).
Zero Repainting: Swings are confirmed only after the confirmation candle closes.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from src.core.contracts import Candle
from src.engine.types import SkillResult, Context, normalize_to_candles


@dataclass
class SwingPoint:
    index: int
    time: str
    price: float
    swing_type: str  # "STH", "STL", "ITH", "ITL", "LTH", "LTL"
    rank: int        # 1, 2, or 3
    confirmed_index: int
    confirmed_time: str


def identify_swings(candles: Sequence[Candle]) -> Tuple[List[SwingPoint], List[SwingPoint]]:
    """
    Computes confirmed recursive swing highs and swing lows.
    Returns: (swing_highs, swing_lows)
    """
    n = len(candles)
    if n < 3:
        return [], []

    # 1. Rank 1: STH and STL (n=1 on each side) [ART-02]
    sth_list: List[SwingPoint] = []
    stl_list: List[SwingPoint] = []

    for i in range(1, n - 1):
        prev_c = candles[i - 1]
        cur_c = candles[i]
        next_c = candles[i + 1]

        # Short-Term High: higher high than candle before and candle after
        if cur_c.high > prev_c.high and cur_c.high >= next_c.high:
            sth_list.append(
                SwingPoint(
                    index=i,
                    time=cur_c.time if isinstance(cur_c.time, str) else cur_c.time.isoformat(),
                    price=cur_c.high,
                    swing_type="STH",
                    rank=1,
                    confirmed_index=i + 1,
                    confirmed_time=next_c.time if isinstance(next_c.time, str) else next_c.time.isoformat(),
                )
            )

        # Short-Term Low: lower low than candle before and candle after
        if cur_c.low < prev_c.low and cur_c.low <= next_c.low:
            stl_list.append(
                SwingPoint(
                    index=i,
                    time=cur_c.time if isinstance(cur_c.time, str) else cur_c.time.isoformat(),
                    price=cur_c.low,
                    swing_type="STL",
                    rank=1,
                    confirmed_index=i + 1,
                    confirmed_time=next_c.time if isinstance(next_c.time, str) else next_c.time.isoformat(),
                )
            )

    # 2. Rank 2: ITH and ITL (lower STH/higher STL on each side) [ART-02]
    ith_list: List[SwingPoint] = []
    itl_list: List[SwingPoint] = []

    if len(sth_list) >= 3:
        for j in range(1, len(sth_list) - 1):
            prev_sth = sth_list[j - 1]
            cur_sth = sth_list[j]
            next_sth = sth_list[j + 1]
            if cur_sth.price > prev_sth.price and cur_sth.price >= next_sth.price:
                ith_list.append(
                    SwingPoint(
                        index=cur_sth.index,
                        time=cur_sth.time,
                        price=cur_sth.price,
                        swing_type="ITH",
                        rank=2,
                        confirmed_index=next_sth.confirmed_index,
                        confirmed_time=next_sth.confirmed_time,
                    )
                )

    if len(stl_list) >= 3:
        for j in range(1, len(stl_list) - 1):
            prev_stl = stl_list[j - 1]
            cur_stl = stl_list[j]
            next_stl = stl_list[j + 1]
            if cur_stl.price < prev_stl.price and cur_stl.price <= next_stl.price:
                itl_list.append(
                    SwingPoint(
                        index=cur_stl.index,
                        time=cur_stl.time,
                        price=cur_stl.price,
                        swing_type="ITL",
                        rank=2,
                        confirmed_index=next_stl.confirmed_index,
                        confirmed_time=next_stl.confirmed_time,
                    )
                )

    # 3. Rank 3: LTH and LTL (lower ITH/higher ITL on each side) [ART-02]
    lth_list: List[SwingPoint] = []
    ltl_list: List[SwingPoint] = []

    if len(ith_list) >= 3:
        for k in range(1, len(ith_list) - 1):
            prev_ith = ith_list[k - 1]
            cur_ith = ith_list[k]
            next_ith = ith_list[k + 1]
            if cur_ith.price > prev_ith.price and cur_ith.price >= next_ith.price:
                lth_list.append(
                    SwingPoint(
                        index=cur_ith.index,
                        time=cur_ith.time,
                        price=cur_ith.price,
                        swing_type="LTH",
                        rank=3,
                        confirmed_index=next_ith.confirmed_index,
                        confirmed_time=next_ith.confirmed_time,
                    )
                )

    if len(itl_list) >= 3:
        for k in range(1, len(itl_list) - 1):
            prev_itl = itl_list[k - 1]
            cur_itl = itl_list[k]
            next_itl = itl_list[k + 1]
            if cur_itl.price < prev_itl.price and cur_itl.price <= next_itl.price:
                ltl_list.append(
                    SwingPoint(
                        index=cur_itl.index,
                        time=cur_itl.time,
                        price=cur_itl.price,
                        swing_type="LTL",
                        rank=3,
                        confirmed_index=next_itl.confirmed_index,
                        confirmed_time=next_itl.confirmed_time,
                    )
                )

    # Combine ranked swings
    all_highs = sorted(sth_list + ith_list + lth_list, key=lambda s: s.index)
    all_lows = sorted(stl_list + itl_list + ltl_list, key=lambda s: s.index)
    return all_highs, all_lows


def evaluate(candles_data: Sequence[Union[Candle, dict, Any]], ctx: Context) -> SkillResult:
    """
    Evaluates swing hierarchy across closed candles [GROUND RULE 4, ART-02].
    Populates ctx.protected_swing_low and ctx.protected_swing_high using ITH/ITL swings [ART-02, ASSUMPTION].
    """
    candles = normalize_to_candles(candles_data)
    if len(candles) < 3:
        return SkillResult(
            status="INSUFFICIENT_DATA",
            passed=False,
            reasons=["Need at least 3 closed candles for swing identification [ART-02]"],
            tags=["[ART-02]"],
        )

    highs, lows = identify_swings(candles)
    levels: Dict[str, float] = {}

    recent_sth = next((s for s in reversed(highs) if s.rank == 1), None)
    recent_stl = next((s for s in reversed(lows) if s.rank == 1), None)
    recent_ith = next((s for s in reversed(highs) if s.rank >= 2), None)
    recent_itl = next((s for s in reversed(lows) if s.rank >= 2), None)
    recent_lth = next((s for s in reversed(highs) if s.rank == 3), None)
    recent_ltl = next((s for s in reversed(lows) if s.rank == 3), None)

    if recent_sth:
        levels["recent_sth"] = recent_sth.price
    if recent_stl:
        levels["recent_stl"] = recent_stl.price
    if recent_ith:
        levels["recent_ith"] = recent_ith.price
        ctx.parameters["ith_level"] = recent_ith.price
    if recent_itl:
        levels["recent_itl"] = recent_itl.price
        ctx.parameters["itl_level"] = recent_itl.price
    if recent_lth:
        levels["recent_lth"] = recent_lth.price
    if recent_ltl:
        levels["recent_ltl"] = recent_ltl.price

    # Anchor intermediate swing to context if available [ART-02, ASSUMPTION]
    if recent_itl and ctx.protected_swing_low is None:
        ctx.protected_swing_low = recent_itl.price
    if recent_ith and ctx.protected_swing_high is None:
        ctx.protected_swing_high = recent_ith.price

    reasons = [
        f"Ranked Swings confirmed: {len(highs)} highs (STH/ITH/LTH), {len(lows)} lows (STL/ITL/LTL) [ART-02]",
        f"Latest STH: {recent_sth.price if recent_sth else 'None'}, Latest STL: {recent_stl.price if recent_stl else 'None'} [ART-02]",
        f"Latest ITH: {recent_ith.price if recent_ith else 'None'}, Latest ITL: {recent_itl.price if recent_itl else 'None'} [ART-02]"
    ]

    return SkillResult(
        status="CONFIRMED",
        passed=True,
        level_prices=levels,
        reasons=reasons,
        confidence=0.90,
        tags=["[ART-02]"],
        metadata={
            "sth_count": sum(1 for s in highs if s.rank == 1),
            "ith_count": sum(1 for s in highs if s.rank == 2),
            "lth_count": sum(1 for s in highs if s.rank == 3),
            "stl_count": sum(1 for s in lows if s.rank == 1),
            "itl_count": sum(1 for s in lows if s.rank == 2),
            "ltl_count": sum(1 for s in lows if s.rank == 3),
            "coach_lesson": "Most highs and lows don't matter. The bigger the high, the later you know.",
        }
    )
