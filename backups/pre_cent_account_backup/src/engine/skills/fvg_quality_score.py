"""
Skill: fvg_quality_score [VIDEO 9]
Scores the structural quality of a Fair Value Gap before trusting it as a Point of Interest (POI).
A gap is only as good as the move that made it.
- Weak (+0): formed inside a range, nothing broken. Reject by default.
- Strong (+2): formed when the move broke previous swing high/low with a candle body close.
- Resting Liquidity Penalty (-1 to -2): if unswept stops rest below/above the gap, price may run through.
Score threshold min_score >= 1.0 required to approve.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from src.core.contracts import Candle
from src.engine.types import SkillResult, Context, normalize_to_candles


def evaluate(data: Any, ctx: Context) -> SkillResult:
    """
    Evaluates FVG quality score across structure breakage and resting liquidity context.
    [VIDEO 9]
    """
    candles: List[Candle] = normalize_to_candles(data)
    if len(candles) < 3:
        return SkillResult(status="FAIL", reasons=["Insufficient candles for FVG scoring"], tag="[VIDEO 9]")

    fvg_top = ctx.parameters.get("fvg_top")
    fvg_bottom = ctx.parameters.get("fvg_bottom")
    fvg_direction = ctx.parameters.get("fvg_direction", "BUY") # "BUY" or "SELL"

    # If not supplied in parameters, detect the most recent FVG in candles
    if fvg_top is None or fvg_bottom is None:
        for i in range(len(candles) - 1, 1, -1):
            c1 = candles[i - 2]
            c3 = candles[i]
            if c3.low > c1.high:
                fvg_bottom = c1.high
                fvg_top = c3.low
                fvg_direction = "BUY"
                break
            elif c1.low > c3.high:
                fvg_top = c1.low
                fvg_bottom = c3.high
                fvg_direction = "SELL"
                break

    if fvg_top is None or fvg_bottom is None:
        return SkillResult(status="HOLD", reasons=["No active FVG zone to score [VIDEO 9]"], tag="[VIDEO 9]")

    atr = ctx.atr or 0.0010
    score = 0.0
    reasons: List[str] = []

    # Question 1: What did the move break? [VIDEO 9]
    # Check if the move breaking into the FVG closed beyond the prior swing high (BOS)
    prior_highs = [c.high for c in candles[:-3]]
    prior_lows = [c.low for c in candles[:-3]]

    caused_bos = False
    if fvg_direction == "BUY" and prior_highs:
        recent_swing_high = max(prior_highs[-10:])
        # Check if the impulse candle closed above recent swing high
        if any(c.close > recent_swing_high for c in candles[-3:]):
            caused_bos = True
            score += float(ctx.parameters.get("fvg_bos_body_close_weight", 2.0)) # [ASSUMPTION: +2]
            reasons.append(f"Strong gap (+2): Move broke previous high {recent_swing_high:.5f} with body close [VIDEO 9]")
    elif fvg_direction == "SELL" and prior_lows:
        recent_swing_low = min(prior_lows[-10:])
        if any(c.close < recent_swing_low for c in candles[-3:]):
            caused_bos = True
            score += float(ctx.parameters.get("fvg_bos_body_close_weight", 2.0)) # [ASSUMPTION: +2]
            reasons.append(f"Strong gap (+2): Move broke previous low {recent_swing_low:.5f} with body close [VIDEO 9]")

    if not caused_bos:
        reasons.append("Weak gap (+0): Formed inside range with no structural break [VIDEO 9]")

    # Question 2: What is still resting below/above it? [VIDEO 9]
    # Check if unswept liquidity sits within N * ATR
    scan_dist = float(ctx.parameters.get("resting_liquidity_distance_atr", 1.5)) * atr # [ASSUMPTION]
    has_resting_liquidity = False

    for pool in ctx.liquidity_pools:
        if not pool.get("swept", False):
            p_price = pool.get("price", 0.0)
            if fvg_direction == "BUY":
                # Unswept sell-side liquidity resting right below the bullish gap
                if (fvg_bottom - scan_dist) <= p_price < fvg_bottom:
                    has_resting_liquidity = True
                    penalty = float(ctx.parameters.get("unswept_liquidity_penalty", -2.0)) # [ASSUMPTION: -2]
                    score += penalty
                    reasons.append(
                        f"Liquidity trap risk ({penalty:+.1f}): Unswept {pool.get('type')} sits at {p_price:.5f} below gap; price may run through [VIDEO 9]"
                    )
            else:
                # Unswept buy-side liquidity resting right above the bearish gap
                if fvg_top < p_price <= (fvg_top + scan_dist):
                    has_resting_liquidity = True
                    penalty = float(ctx.parameters.get("unswept_liquidity_penalty", -2.0))
                    score += penalty
                    reasons.append(
                        f"Liquidity trap risk ({penalty:+.1f}): Unswept {pool.get('type')} sits at {p_price:.5f} above gap; price may run through [VIDEO 9]"
                    )

    min_required_score = float(ctx.parameters.get("fvg_min_score", 1.0)) # [ASSUMPTION]
    status = "PASS" if score >= min_required_score else "FAIL"

    level_prices: Dict[str, float] = {
        "fvg_top": fvg_top,
        "fvg_bottom": fvg_bottom,
        "fvg_score": score,
        "min_score": min_required_score,
    }

    return SkillResult(
        status=status,
        level_prices=level_prices,
        reasons=reasons,
        confidence=max(0.0, min(1.0, score / 2.0)),
        tag="[VIDEO 9]",
        metadata={
            "coach_lesson": "A gap is only as good as the move that made it.",
            "score": score,
            "caused_bos": caused_bos,
            "has_resting_liquidity": has_resting_liquidity,
        }
    )
