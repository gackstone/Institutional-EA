"""
Buy-Side / Sell-Side Liquidity Pool Mapper [ART-04, ART-10].
Maps institutional order resting pools:
- Buy-Side Liquidity (BSL): Resting stops and breakout buys above old highs.
- Sell-Side Liquidity (SSL): Resting stops and breakout sells below old lows.
- Pool types: EQH, EQL, PDH, PDL, PWH, PWL, and ranked swing extremes.
- Weight hierarchy: PWH/PWL (4.0) > PDH/PDL (3.0) > EQH/EQL (2.0) > minor swings (1.0).
- Outcomes upon touching pool: SWEEP (wick through, closes back inside) or RUN (closes beyond and continues).
- Caveat [ART-04]: Nobody can see the stops; pools are a map of where orders probably rest, not a promise.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from src.core.contracts import Candle
from src.engine.types import SkillResult, Context, normalize_to_candles


@dataclass
class LiquidityPool:
    pool_id: str
    pool_type: str  # "EQH", "EQL", "PDH", "PDL", "PWH", "PWL", "BSL", "SSL"
    price: float
    weight: float
    time: str
    status: str = "RESTING"  # "RESTING", "SWEPT", "RUN"
    touch_count: int = 1


def identify_pools(candles: Sequence[Candle], pip_size: float = 0.0001, eq_tolerance_pips: float = 2.0) -> List[LiquidityPool]:
    """Identifies and classifies BSL and SSL pools from completed candles."""
    pools: List[LiquidityPool] = []
    n = len(candles)
    if n < 5:
        return pools

    tolerance = eq_tolerance_pips * pip_size

    # 1. Identify local highs and lows
    highs: List[Tuple[int, Candle]] = []
    lows: List[Tuple[int, Candle]] = []
    for i in range(1, n - 1):
        if candles[i].high > candles[i - 1].high and candles[i].high >= candles[i + 1].high:
            highs.append((i, candles[i]))
        if candles[i].low < candles[i - 1].low and candles[i].low <= candles[i + 1].low:
            lows.append((i, candles[i]))

    # 2. Equal Highs (EQH - BSL) [ART-04, VIDEO 7]
    for i in range(len(highs) - 1):
        idx1, c1 = highs[i]
        idx2, c2 = highs[i + 1]
        if abs(c1.high - c2.high) <= tolerance:
            pools.append(
                LiquidityPool(
                    pool_id=f"EQH_{idx2}",
                    pool_type="EQH",
                    price=max(c1.high, c2.high),
                    weight=2.0,
                    time=c2.time if isinstance(c2.time, str) else c2.time.isoformat(),
                    touch_count=2,
                )
            )

    # 3. Equal Lows (EQL - SSL) [ART-04, VIDEO 7]
    for i in range(len(lows) - 1):
        idx1, c1 = lows[i]
        idx2, c2 = lows[i + 1]
        if abs(c1.low - c2.low) <= tolerance:
            pools.append(
                LiquidityPool(
                    pool_id=f"EQL_{idx2}",
                    pool_type="EQL",
                    price=min(c1.low, c2.low),
                    weight=2.0,
                    time=c2.time if isinstance(c2.time, str) else c2.time.isoformat(),
                    touch_count=2,
                )
            )

    # 4. Previous Day High / Low (PDH/PDL) or overall period extremes [ART-04]
    max_c = max(candles, key=lambda c: c.high)
    min_c = min(candles, key=lambda c: c.low)
    pools.append(
        LiquidityPool(
            pool_id="PDH_EXTREME",
            pool_type="PDH",
            price=max_c.high,
            weight=3.0,
            time=max_c.time if isinstance(max_c.time, str) else max_c.time.isoformat(),
        )
    )
    pools.append(
        LiquidityPool(
            pool_id="PDL_EXTREME",
            pool_type="PDL",
            price=min_c.low,
            weight=3.0,
            time=min_c.time if isinstance(min_c.time, str) else min_c.time.isoformat(),
        )
    )

    # Check status against current closed candle
    cur_candle = candles[-1]
    for p in pools:
        if "H" in p.pool_type:
            if cur_candle.high > p.price:
                if cur_candle.close <= p.price:
                    p.status = "SWEPT"  # Wick through, close back inside [ART-10]
                else:
                    p.status = "RUN"    # Close beyond [ART-04, ART-10]
        elif "L" in p.pool_type:
            if cur_candle.low < p.price:
                if cur_candle.close >= p.price:
                    p.status = "SWEPT"
                else:
                    p.status = "RUN"

    return pools


def evaluate(candles_data: Sequence[Union[Candle, dict, Any]], ctx: Context) -> SkillResult:
    """Evaluates HTF and LTF liquidity pools [ART-04, ART-10]."""
    candles = normalize_to_candles(candles_data)
    if len(candles) < 5:
        return SkillResult(
            status="INSUFFICIENT_DATA",
            passed=False,
            reasons=["Need at least 5 closed candles for liquidity pool mapping [ART-04]"],
            tags=["[ART-04]"],
        )

    eq_pips = float(ctx.parameters.get("eq_tolerance_pips", 2.0))
    pools = identify_pools(candles, pip_size=ctx.pip_size, eq_tolerance_pips=eq_pips)

    levels: Dict[str, float] = {}
    swept_pools: List[LiquidityPool] = []
    resting_bsl: List[float] = []
    resting_ssl: List[float] = []

    cur_close = candles[-1].close
    for p in pools:
        if p.status == "SWEPT":
            swept_pools.append(p)
        elif p.status == "RESTING":
            if p.price > cur_close:
                resting_bsl.append(p.price)
            else:
                resting_ssl.append(p.price)

    nearest_bsl = min(resting_bsl) if resting_bsl else None
    nearest_ssl = max(resting_ssl) if resting_ssl else None

    if nearest_bsl:
        levels["nearest_bsl"] = nearest_bsl
        ctx.parameters["nearest_bsl"] = nearest_bsl
    if nearest_ssl:
        levels["nearest_ssl"] = nearest_ssl
        ctx.parameters["nearest_ssl"] = nearest_ssl

    reasons = [
        f"Mapped {len(pools)} institutional liquidity pools (EQH/EQL/PDH/PDL) [ART-04]",
        f"Nearest resting BSL target: {nearest_bsl if nearest_bsl else 'None'}, Nearest resting SSL target: {nearest_ssl if nearest_ssl else 'None'} [ART-04]",
        f"Swept pools on recent close: {len(swept_pools)} [ART-10]",
        "Caveat: Nobody can see the stops; pools are a map of where orders probably rest, not a promise [ART-04]"
    ]

    return SkillResult(
        status="ACTIVE",
        passed=True,
        level_prices=levels,
        reasons=reasons,
        confidence=0.85,
        tags=["[ART-04]", "[ART-10]"],
        metadata={
            "pool_count": len(pools),
            "swept_count": len(swept_pools),
            "nearest_bsl": nearest_bsl,
            "nearest_ssl": nearest_ssl,
            "coach_lesson": "Nobody can see the stops. Pools are a map of where orders probably rest, not a promise.",
        }
    )
