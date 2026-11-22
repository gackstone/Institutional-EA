"""
Skill: sweep_fvg_entry [VIDEO 5]
Identifies Liquidity Sweep + Fair Value Gap (FVG) entry setups.
State machine: LIQ_IDENTIFIED -> SWEPT -> DISPLACEMENT_FVG -> RETURN_TO_FVG -> GAP_HOLDS -> ENTRY.
Do not chase the displacement.
Entry: closed candle test holding the gap.
Hard stop: strictly beyond the sweep extreme.
Target: resting highs above (next liquidity).
Invalidation: candle close through the gap.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from src.core.contracts import Candle
from src.engine.types import SkillResult, Context, normalize_to_candles


def evaluate(data: Any, ctx: Context) -> SkillResult:
    """
    Evaluates closed candles for a Liquidity Sweep + FVG entry setup.
    [VIDEO 5]
    """
    candles: List[Candle] = normalize_to_candles(data)
    if len(candles) < 5:
        return SkillResult(status="FAIL", reasons=["Need at least 5 bars for sweep+FVG evaluation"], tag="[VIDEO 5]")

    direction = ctx.parameters.get("force_direction")
    if not direction:
        direction = "BUY" if ctx.trend == "BULL" else ("SELL" if ctx.trend == "BEAR" else "BUY")

    reasons: List[str] = []
    level_prices: Dict[str, float] = {}

    if direction == "BUY":
        # 1. Identify swept level: prior obvious swing low that was pierced by wick then closed back inside [VIDEO 5]
        sweep_level: Optional[float] = None
        sweep_extreme: Optional[float] = None
        sweep_idx: Optional[int] = None

        for i in range(1, len(candles) - 3):
            # Prior reference low before bar i
            prior_low = min(c.low for c in candles[max(0, i - 10): i])
            c = candles[i]
            # Wick below prior low, body closed back inside (above or equal to prior low)
            if c.low < prior_low and c.close >= prior_low:
                sweep_level = prior_low
                sweep_extreme = c.low
                sweep_idx = i
                break

        if sweep_level is None or sweep_idx is None:
            return SkillResult(status="HOLD", reasons=["No liquidity sweep with close-back-inside found [VIDEO 5]"], tag="[VIDEO 5]")

        # 2. Check for displacement + FVG after the sweep [VIDEO 5]
        # FVG: candle 1 high < candle 3 low, requiring noticeable imbalance
        fvg_top: Optional[float] = None
        fvg_bottom: Optional[float] = None
        fvg_idx: Optional[int] = None
        min_gap = max(ctx.pip_size * 1.5, (ctx.atr or 0.0010) * 0.25)

        best_gap = 0.0
        for j in range(sweep_idx + 2, len(candles) - 1):
            c1 = candles[j - 2]
            c3 = candles[j]
            gap = c3.low - c1.high
            if gap >= min_gap and gap > best_gap:
                best_gap = gap
                fvg_bottom = c1.high
                fvg_top = c3.low
                fvg_idx = j

        if fvg_top is None or fvg_bottom is None:
            return SkillResult(status="HOLD", reasons=["Sweep found, but no displacement FVG created after it [VIDEO 5]"], tag="[VIDEO 5]")

        # 2b. Structure confirmation check [ART-06, ART-10]
        # "A sweep alone is not enough. Let structure confirm it."
        require_choch = ctx.parameters.get("require_structure_confirmation", True)
        if require_choch and sweep_idx > 0:
            prior_high = max(c.high for c in candles[max(0, sweep_idx - 5): sweep_idx])
            has_structure_break = any(candles[k].close > prior_high for k in range(sweep_idx + 1, len(candles)))
            if not has_structure_break:
                return SkillResult(
                    status="HOLD",
                    reasons=[f"Sweep at {sweep_level:.5f} found, but awaiting structure confirmation (CHOCH close above {prior_high:.5f}). A sweep alone is not enough [ART-06, ART-10]"],
                    tag="[ART-06, ART-10]"
                )

        fvg_mid = (fvg_top + fvg_bottom) / 2.0
        level_prices["sweep_level"] = sweep_level
        level_prices["sweep_extreme"] = sweep_extreme
        level_prices["fvg_top"] = fvg_top
        level_prices["fvg_bottom"] = fvg_bottom
        level_prices["fvg_mid"] = fvg_mid

        # 3. Check for return to FVG and evaluate the closed candle [VIDEO 5]
        last = candles[-1]

        # Invalidation check: closed candle through the gap (< fvg_bottom) [VIDEO 5, 10]
        if last.close < fvg_bottom:
            reasons.append(
                f"SETUP INVALIDATED: Closed candle ({last.close:.5f}) pierced through FVG bottom ({fvg_bottom:.5f}). Buyers gone [VIDEO 5]"
            )
            return SkillResult(status="INVALID", level_prices=level_prices, reasons=reasons, confidence=0.0, tag="[VIDEO 5]")

        # Gap holds check: candle dipped into the gap (low <= fvg_top) and closed inside or above the gap (close >= fvg_bottom) [VIDEO 5]
        dipped_into_gap = last.low <= fvg_top and last.high >= fvg_bottom
        gap_holds = dipped_into_gap and (last.close >= fvg_mid or (last.close >= fvg_bottom and last.close > last.open))

        if gap_holds:
            entry_price = last.close
            stop_loss = sweep_extreme - (ctx.pip_size * 2) # [VIDEO 5: stop strictly below sweep extreme]
            target_highs = max(c.high for c in candles[sweep_idx:]) # [VIDEO 5: target the highs where next liquidity sits]
            take_profit = max(target_highs, entry_price + (entry_price - stop_loss) * 1.5)

            level_prices["entry"] = entry_price
            level_prices["stop_loss"] = stop_loss
            level_prices["take_profit"] = take_profit

            reasons.append(
                f"TRIGGERED: Sweep of {sweep_level:.5f} (extreme {sweep_extreme:.5f}), FVG [{fvg_bottom:.5f} - {fvg_top:.5f}] held on close at {entry_price:.5f}. SL={stop_loss:.5f}, TP={take_profit:.5f} [VIDEO 5]"
            )
            return SkillResult(
                status="TRIGGERED",
                level_prices=level_prices,
                reasons=reasons,
                confidence=1.0,
                tag="[VIDEO 5]",
                metadata={
                    "direction": "BUY",
                    "coach_lesson": "The sweep shows who stepped in, the gap shows where to join them.",
                    "entry": entry_price,
                    "sl": stop_loss,
                    "tp": take_profit,
                }
            )
        else:
            reasons.append("Sweep + FVG mapped; awaiting return and closed candle confirming gap holds [VIDEO 5]")
            return SkillResult(status="HOLD", level_prices=level_prices, reasons=reasons, confidence=0.5, tag="[VIDEO 5]")

    else:
        # Bearish mirror
        sweep_level = None
        sweep_extreme = None
        sweep_idx = None
        for i in range(1, len(candles) - 3):
            prior_high = max(c.high for c in candles[max(0, i - 10): i])
            c = candles[i]
            if c.high > prior_high and c.close <= prior_high:
                sweep_level = prior_high
                sweep_extreme = c.high
                sweep_idx = i
                break

        if sweep_level is None or sweep_idx is None:
            return SkillResult(status="HOLD", reasons=["No bearish liquidity sweep found [VIDEO 5]"], tag="[VIDEO 5]")

        fvg_top = None
        fvg_bottom = None
        min_gap = max(ctx.pip_size * 1.5, (ctx.atr or 0.0010) * 0.25)
        best_gap = 0.0
        for j in range(sweep_idx + 2, len(candles) - 1):
            c1 = candles[j - 2]
            c3 = candles[j]
            gap = c1.low - c3.high
            if gap >= min_gap and gap > best_gap:
                best_gap = gap
                fvg_top = c1.low
                fvg_bottom = c3.high

        if fvg_top is None or fvg_bottom is None:
            return SkillResult(status="HOLD", reasons=["No bearish displacement FVG created after sweep [VIDEO 5]"], tag="[VIDEO 5]")

        # 2b. Structure confirmation check [ART-06, ART-10]
        require_choch = ctx.parameters.get("require_structure_confirmation", True)
        if require_choch and sweep_idx > 0:
            prior_low = min(c.low for c in candles[max(0, sweep_idx - 5): sweep_idx])
            has_structure_break = any(candles[k].close < prior_low for k in range(sweep_idx + 1, len(candles)))
            if not has_structure_break:
                return SkillResult(
                    status="HOLD",
                    reasons=[f"Bearish sweep at {sweep_level:.5f} found, but awaiting structure confirmation (CHOCH close below {prior_low:.5f}). A sweep alone is not enough [ART-06, ART-10]"],
                    tag="[ART-06, ART-10]"
                )

        fvg_mid = (fvg_top + fvg_bottom) / 2.0
        level_prices["sweep_level"] = sweep_level
        level_prices["sweep_extreme"] = sweep_extreme
        level_prices["fvg_top"] = fvg_top
        level_prices["fvg_bottom"] = fvg_bottom

        last = candles[-1]
        if last.close > fvg_top:
            reasons.append(f"SETUP INVALIDATED: Closed candle ({last.close:.5f}) pierced through bearish FVG top ({fvg_top:.5f}) [VIDEO 5]")
            return SkillResult(status="INVALID", level_prices=level_prices, reasons=reasons, confidence=0.0, tag="[VIDEO 5]")

        dipped_into_gap = last.high >= fvg_bottom and last.low <= fvg_top
        gap_holds = dipped_into_gap and (last.close <= fvg_mid or (last.close <= fvg_top and last.close < last.open))

        if gap_holds:
            entry_price = last.close
            stop_loss = sweep_extreme + (ctx.pip_size * 2)
            target_lows = min(c.low for c in candles[sweep_idx:])
            take_profit = min(target_lows, entry_price - (stop_loss - entry_price) * 1.5)

            level_prices["entry"] = entry_price
            level_prices["stop_loss"] = stop_loss
            level_prices["take_profit"] = take_profit

            reasons.append(
                f"TRIGGERED: Bearish Sweep of {sweep_level:.5f} (extreme {sweep_extreme:.5f}), FVG [{fvg_bottom:.5f} - {fvg_top:.5f}] held on close at {entry_price:.5f}. SL={stop_loss:.5f}, TP={take_profit:.5f} [VIDEO 5]"
            )
            return SkillResult(
                status="TRIGGERED",
                level_prices=level_prices,
                reasons=reasons,
                confidence=1.0,
                tag="[VIDEO 5]",
                metadata={"direction": "SELL", "coach_lesson": "The sweep shows who stepped in, the gap shows where to join them.", "entry": entry_price, "sl": stop_loss, "tp": take_profit}
            )

    return SkillResult(status="HOLD", level_prices=level_prices, reasons=["Waiting for sweep FVG setup conditions [VIDEO 5]"], tag="[VIDEO 5]")
