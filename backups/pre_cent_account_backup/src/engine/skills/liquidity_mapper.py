"""
Skill: liquidity_mapper [VIDEO 7]
Maps major buy-side and sell-side liquidity pools (EQH, EQL, swing extremes).
Liquidity is NOT a signal. It tells you where to watch, not what to do.
Must NEVER emit a trade on its own.
Used strictly for:
(a) Watchlist for liquidity sweep setups (V5)
(b) Take-profit target selection (next liquidity pool)
(c) Risk check under/over Fair Value Gaps (V9)
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from src.core.contracts import Candle
from src.engine.types import SkillResult, Context, normalize_to_candles


def evaluate(data: Any, ctx: Context) -> SkillResult:
    """
    Identifies liquidity pools and updates swept status on closed candles.
    [VIDEO 7]
    """
    candles: List[Candle] = normalize_to_candles(data)
    if len(candles) < 5:
        return SkillResult(status="PASS", reasons=["Insufficient bars for liquidity mapping"], tag="[VIDEO 7]")

    atr = ctx.atr or 0.0010
    eq_tolerance = float(ctx.parameters.get("eqh_tolerance_atr_mult", 0.10)) * atr # [ASSUMPTION]

    # Detect local swing highs and lows
    swing_highs: List[Dict[str, Any]] = []
    swing_lows: List[Dict[str, Any]] = []

    default_k = min(2, max(1, (len(candles) - 2) // 3))
    k = int(ctx.parameters.get("swing_lookback", default_k))
    for i in range(k, len(candles) - k):
        c = candles[i]
        if all(c.high > candles[j].high for j in range(i - k, i)) and \
           all(c.high >= candles[j].high for j in range(i + 1, i + k + 1)):
            swing_highs.append({"index": i, "price": c.high, "time": c.time, "swept": False})

        if all(c.low < candles[j].low for j in range(i - k, i)) and \
           all(c.low <= candles[j].low for j in range(i + 1, i + k + 1)):
            swing_lows.append({"index": i, "price": c.low, "time": c.time, "swept": False})

    # Check for Equal Highs (EQH) and Equal Lows (EQL)
    pools: List[Dict[str, Any]] = []

    # Group EQH
    for i in range(len(swing_highs) - 1):
        sh1 = swing_highs[i]
        sh2 = swing_highs[i + 1]
        if abs(sh1["price"] - sh2["price"]) <= eq_tolerance:
            pools.append({
                "type": "EQH",
                "price": max(sh1["price"], sh2["price"]),
                "time": sh2["time"],
                "side": "BUY_SIDE_LIQUIDITY",
                "swept": False,
            })

    # Group EQL
    for i in range(len(swing_lows) - 1):
        sl1 = swing_lows[i]
        sl2 = swing_lows[i + 1]
        if abs(sl1["price"] - sl2["price"]) <= eq_tolerance:
            pools.append({
                "type": "EQL",
                "price": min(sl1["price"], sl2["price"]),
                "time": sl2["time"],
                "side": "SELL_SIDE_LIQUIDITY",
                "swept": False,
            })

    # Add obvious swing extremes as BSL/SSL pools
    for sh in swing_highs[-3:]:
        pools.append({
            "type": "BSL",
            "price": sh["price"],
            "time": sh["time"],
            "side": "BUY_SIDE_LIQUIDITY",
            "swept": False,
        })
    for sl in swing_lows[-3:]:
        pools.append({
            "type": "SSL",
            "price": sl["price"],
            "time": sl["time"],
            "side": "SELL_SIDE_LIQUIDITY",
            "swept": False,
        })

    # Check swept status against subsequent closed candles
    for p in pools:
        p_price = p["price"]
        p_side = p["side"]
        for c in candles:
            if c.time > p["time"]:
                if p_side == "BUY_SIDE_LIQUIDITY" and c.high > p_price:
                    p["swept"] = True
                elif p_side == "SELL_SIDE_LIQUIDITY" and c.low < p_price:
                    p["swept"] = True

    ctx.liquidity_pools = pools

    # Collect nearest unswept opposing pools for take-profit target selection
    current_price = ctx.current_price or candles[-1].close
    unswept_bsl = [p["price"] for p in pools if p["side"] == "BUY_SIDE_LIQUIDITY" and not p["swept"] and p["price"] > current_price]
    unswept_ssl = [p["price"] for p in pools if p["side"] == "SELL_SIDE_LIQUIDITY" and not p["swept"] and p["price"] < current_price]

    target_high = min(unswept_bsl) if unswept_bsl else max((c.high for c in candles[-20:]), default=current_price + atr * 2)
    target_low = max(unswept_ssl) if unswept_ssl else min((c.low for c in candles[-20:]), default=current_price - atr * 2)

    level_prices: Dict[str, float] = {
        "target_bsl": target_high,
        "target_ssl": target_low,
        "pool_count": float(len(pools)),
    }

    reasons = [
        f"Mapped {len(pools)} liquidity pools (EQH/EQL/BSL/SSL). Context only; not a trigger [VIDEO 7]"
    ]

    return SkillResult(
        status="PASS",
        level_prices=level_prices,
        reasons=reasons,
        confidence=1.0,
        tag="[VIDEO 7]",
        metadata={
            "coach_lesson": "Liquidity is not a signal. It tells you where to watch, not what to do.",
            "pools": pools,
            "target_bsl": target_high,
            "target_ssl": target_low,
        }
    )
