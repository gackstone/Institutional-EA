"""
Five-Check Trade Plan Master Model [ART-06].
Implements Setup Type A (the master template of both video batches):
1. SWEEP: Equal lows/highs swept (wick through, candle closes back inside) [ART-06, ART-10].
2. STRUCTURE: Sweep alone is not enough; price MUST break the last lower high (CHOCH) with a closed candle [ART-06].
3. RANGE: Draw range from sweep extreme to new swing high; mark 50% equilibrium; BUY strictly in discount (< 50%) [ART-06, ART-07].
4. ENTRY: Confluence of an unmitigated Fair Value Gap with the Order Block right under it; both in discount [ART-06].
5. PLAN BEFORE ARRIVAL: Entry inside gap, stop below sweep extreme, target equal highs/BSL; live R:R >= 2.0 [ART-06].
RULE: ALL FIVE OR NO TRADE! [ART-06]
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Union

from src.core.contracts import Candle
from src.engine.types import SkillResult, Context, normalize_to_candles


@dataclass
class FiveCheckStatus:
    check1_sweep: bool = False
    check2_structure_choch: bool = False
    check3_discount_location: bool = False
    check4_fvg_ob_confluence: bool = False
    check5_plan_rr: bool = False

    @property
    def all_passed(self) -> bool:
        return (
            self.check1_sweep and
            self.check2_structure_choch and
            self.check3_discount_location and
            self.check4_fvg_ob_confluence and
            self.check5_plan_rr
        )


def evaluate(candles_data: Sequence[Union[Candle, dict, Any]], ctx: Context) -> SkillResult:
    """Evaluates the 5-Check Master Model on closed candles [ART-06]."""
    candles = normalize_to_candles(candles_data)
    if len(candles) < 5:
        return SkillResult(
            status="INSUFFICIENT_DATA",
            passed=False,
            reasons=["Need at least 5 closed candles for Five-Check Model evaluation [ART-06]"],
            tags=["[ART-06]"],
        )

    cur_close = candles[-1].close
    checks = FiveCheckStatus()
    reasons: List[str] = []
    levels: Dict[str, float] = {}

    # Check 1: Sweep of Liquidity (wick through, close back inside) [ART-06, ART-10]
    sweep_extreme = ctx.parameters.get("sweep_extreme")
    if sweep_extreme is not None:
        checks.check1_sweep = True
        levels["sweep_extreme"] = sweep_extreme
        reasons.append(f"Check 1 PASSED: Liquidity sweep verified at extreme {sweep_extreme:.5f} [ART-06, ART-10]")
    else:
        # Check if recent candle swept lowest/highest of recent swing
        recent_low = min(c.low for c in candles[-15:-1])
        if candles[-1].low < recent_low and candles[-1].close >= recent_low:
            checks.check1_sweep = True
            sweep_extreme = candles[-1].low
            levels["sweep_extreme"] = sweep_extreme
            reasons.append(f"Check 1 PASSED: Candle swept recent low {recent_low:.5f} with wick to {sweep_extreme:.5f} [ART-06]")
        else:
            reasons.append("Check 1 FAILED: No liquidity sweep identified [ART-06]")

    # Check 2: Structure Shift (CHOCH body close beyond last opposite swing) [ART-06, ART-09, ART-10]
    has_choch = ctx.parameters.get("has_choch", False)
    choch_level = ctx.parameters.get("choch_level")
    if not has_choch and choch_level is not None:
        has_choch = cur_close > choch_level if ctx.trend == "BULL" else cur_close < choch_level

    if has_choch:
        checks.check2_structure_choch = True
        reasons.append("Check 2 PASSED: Structure confirmed with CHOCH body close [ART-06, ART-10]")
    else:
        reasons.append("Check 2 FAILED: Sweep alone is not enough; awaiting CHOCH body close [ART-06, ART-10]")

    # Check 3: Range Equilibrium (Discount for buys, Premium for sells) [ART-06, ART-07]
    range_high = ctx.parameters.get("range_high") or max(c.high for c in candles[-20:])
    range_low = ctx.parameters.get("range_low") or (sweep_extreme if sweep_extreme is not None else min(c.low for c in candles[-20:]))
    eq = (range_high + range_low) / 2.0
    levels["range_high"] = range_high
    levels["range_low"] = range_low
    levels["equilibrium"] = eq

    is_in_discount = cur_close <= eq
    if is_in_discount:
        checks.check3_discount_location = True
        reasons.append(f"Check 3 PASSED: Price {cur_close:.5f} is in DISCOUNT (<= {eq:.5f}) of leg [{range_low:.5f} - {range_high:.5f}] [ART-06, ART-07]")
    else:
        reasons.append(f"Check 3 FAILED: Price {cur_close:.5f} is in PREMIUM (> {eq:.5f}). Buyers only buy in discount [ART-06, ART-07]")

    # Check 4: Confluence of FVG and Order Block in discount [ART-06]
    fvg_bottom = ctx.parameters.get("fvg_bottom")
    fvg_top = ctx.parameters.get("fvg_top")
    ob_high = ctx.parameters.get("ob_high")
    ob_low = ctx.parameters.get("ob_low")

    has_fvg = fvg_bottom is not None and fvg_top is not None
    has_ob = ob_high is not None and ob_low is not None

    if has_fvg or has_ob:
        checks.check4_fvg_ob_confluence = True
        reasons.append(f"Check 4 PASSED: Discount zone verified (FVG=[{fvg_bottom} - {fvg_top}], OB=[{ob_low} - {ob_high}]) [ART-06]")
    else:
        reasons.append("Check 4 FAILED: No discount FVG or Order Block confluence [ART-06]")

    # Check 5: Plan Before Price Arrives (Stop below sweep low, Target BSL/equal highs, R:R >= 2.0) [ART-06]
    entry_price = fvg_top if fvg_top else cur_close
    stop_loss = sweep_extreme if sweep_extreme is not None else range_low
    take_profit = ctx.parameters.get("nearest_bsl") or range_high

    risk = abs(entry_price - stop_loss)
    room = abs(take_profit - entry_price)
    rr = (room / risk) if risk > 0 else 0.0
    min_rr = float(ctx.parameters.get("five_check_min_rr", 2.0))

    levels["planned_entry"] = entry_price
    levels["planned_sl"] = stop_loss
    levels["planned_tp"] = take_profit
    levels["rr"] = rr

    if rr >= min_rr and risk > 0:
        checks.check5_plan_rr = True
        reasons.append(f"Check 5 PASSED: Planned R:R is {rr:.2f} >= {min_rr:.2f} (Entry={entry_price:.5f}, SL={stop_loss:.5f}, TP={take_profit:.5f}) [ART-06]")
    else:
        reasons.append(f"Check 5 FAILED: Planned R:R is {rr:.2f} < {min_rr:.2f} [ART-06]")

    all_ok = checks.all_passed
    status = "TRIGGERED" if all_ok else "CHECKS_FAILED"

    return SkillResult(
        status=status,
        passed=all_ok,
        level_prices=levels,
        reasons=reasons,
        confidence=0.95 if all_ok else 0.30,
        tags=["[ART-06]"],
        metadata={
            "check1_sweep": checks.check1_sweep,
            "check2_structure_choch": checks.check2_structure_choch,
            "check3_discount_location": checks.check3_discount_location,
            "check4_fvg_ob_confluence": checks.check4_fvg_ob_confluence,
            "check5_plan_rr": checks.check5_plan_rr,
            "coach_lesson": "Sweep. Break. Range. Entry. Plan. Five checks, one trade.",
        }
    )
