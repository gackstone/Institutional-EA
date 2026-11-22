"""
Manual Position Strategy Assessor.
Leverages the 28 transferred strategy skills (protected swings, five check model,
momentum monitoring, stop management policy) to evaluate manual positions.
Tags: [VIDEO 1], [VIDEO 3], [VIDEO 4], [VIDEO 12], [VIDEO 15], [ART-12], [SAFETY]
"""

from __future__ import annotations
import logging
from typing import List, Optional, Tuple, Dict, Any

from src.core.contracts import Candle, OrderType, Position, SymbolInfo
from src.engine.types import Context, SkillResult
from src.manual_mgmt.contracts import (
    AdoptionAssessment,
    ManualPositionRecord,
    PositionClass,
    ManagementMode,
    ManualMgmtConfig
)
from src.engine.skills import (
    trend_by_structure,
    protected_swing_marker,
    swing_hierarchy,
    five_check_model,
    entry_quality_guard,
    structure_momentum_monitor,
    stop_management_policy,
)

logger = logging.getLogger("ManualPositionAssessor")


class ManualPositionAssessor:
    def __init__(self, config: Optional[ManualMgmtConfig] = None):
        self.config = config or ManualMgmtConfig()

    @staticmethod
    def calculate_atr(candles: List[Candle], period: int = 14) -> float:
        if len(candles) < 2:
            return 0.0010
        tr_list = []
        for i in range(1, min(len(candles), period + 1)):
            c = candles[-i]
            prev = candles[-i - 1]
            tr = max(c.high - c.low, abs(c.high - prev.close), abs(c.low - prev.close))
            tr_list.append(tr)
        return sum(tr_list) / len(tr_list) if tr_list else 0.0010

    def assess(
        self,
        pos: Position,
        record: ManualPositionRecord,
        candles_m15: List[Candle],
        candles_m5: Optional[List[Candle]] = None,
        symbol_info: Optional[SymbolInfo] = None
    ) -> AdoptionAssessment:
        """
        Evaluates a manual position using closed candles only [VIDEO 6, 10, 15].
        Produces structured recommendations for SL placement, TP placement, Break-Even,
        Trailing, Add-ons, or Strategy-Based Closure.
        """
        ticket = int(pos.ticket)
        symbol = pos.symbol
        is_buy = pos.order_type == OrderType.BUY
        current_px = float(pos.current_price)
        open_px = float(pos.open_price)
        current_sl = float(pos.stop_loss)
        current_tp = float(pos.take_profit)
        pt = symbol_info.point if symbol_info and symbol_info.point > 0 else 0.00001
        atr = self.calculate_atr(candles_m15)
        buffer = max(self.config.break_even_buffer_points * pt, 1.5 * pt)

        skills_used = []

        # ---------------------------------------------------------------------
        # 1. Check for Missing Stop Loss (Naked Position) [SAFETY]
        # ---------------------------------------------------------------------
        if current_sl <= 0.0 and self.config.auto_sl_enabled:
            skills_used.append("protected_swing_marker")
            ctx = Context(trend="BULL" if is_buy else "BEAR", atr=atr)
            res_prot = protected_swing_marker.evaluate(candles_m15, ctx)
            rec_sl = 0.0
            if is_buy:
                prot_low = res_prot.metadata.get("protected_low") or res_prot.level_prices.get("protected_low")
                if prot_low and prot_low < open_px:
                    rec_sl = prot_low - (0.5 * atr)
                else:
                    # Fallback to recent candle lows or ATR
                    lowest_low = min(c.low for c in candles_m15[-5:]) if len(candles_m15) >= 5 else (open_px - 1.5 * atr)
                    rec_sl = min(lowest_low - (0.2 * atr), open_px - (1.0 * atr))
            else:
                prot_high = res_prot.metadata.get("protected_high") or res_prot.level_prices.get("protected_high")
                if prot_high and prot_high > open_px:
                    rec_sl = prot_high + (0.5 * atr)
                else:
                    highest_high = max(c.high for c in candles_m15[-5:]) if len(candles_m15) >= 5 else (open_px + 1.5 * atr)
                    rec_sl = max(highest_high + (0.2 * atr), open_px + (1.0 * atr))

            if symbol_info:
                rec_sl = symbol_info.round_price(rec_sl)

            # Check if Take Profit should also be calculated
            rec_tp: Optional[float] = None
            if self.config.auto_tp_enabled and current_tp <= 0.0:
                skills_used.append("take_profit_calculator")
                risk_dist = abs(open_px - rec_sl) if abs(open_px - rec_sl) > 0 else (1.5 * atr)
                raw_tp = (open_px + risk_dist * self.config.tp_target_r) if is_buy else (open_px - risk_dist * self.config.tp_target_r)
                if symbol_info:
                    raw_tp = symbol_info.round_price(raw_tp)
                rec_tp = raw_tp

            return AdoptionAssessment(
                ticket=ticket,
                symbol=symbol,
                direction=pos.order_type,
                classification=PositionClass.MANUAL,
                action="SET_SL",
                recommended_sl=rec_sl,
                recommended_tp=rec_tp,
                reason="Position lacks stop loss. Calculated structure protection [VIDEO 3, SAFETY].",
                skills_used=skills_used
            )

        # ---------------------------------------------------------------------
        # 2. Check for Missing Take Profit (when SL is already present)
        # ---------------------------------------------------------------------
        if current_sl > 0.0 and current_tp <= 0.0 and self.config.auto_tp_enabled:
            skills_used.append("take_profit_calculator")
            initial_sl = record.initial_sl if record.initial_sl > 0 else current_sl
            risk_dist = abs(open_px - initial_sl) if abs(open_px - initial_sl) > 0 else (1.5 * atr)
            raw_tp = (open_px + risk_dist * self.config.tp_target_r) if is_buy else (open_px - risk_dist * self.config.tp_target_r)
            if symbol_info:
                raw_tp = symbol_info.round_price(raw_tp)

            tp_valid = (raw_tp > current_px) if is_buy else (raw_tp < current_px)
            if tp_valid:
                return AdoptionAssessment(
                    ticket=ticket,
                    symbol=symbol,
                    direction=pos.order_type,
                    classification=PositionClass.MANUAL,
                    action="SET_TP",
                    recommended_sl=current_sl,
                    recommended_tp=raw_tp,
                    reason=f"Position lacks Take Profit. Applied {self.config.tp_target_r:.1f}R target [SAFETY].",
                    skills_used=skills_used
                )

        # ---------------------------------------------------------------------
        # 3. Compute Risk Metrics (Initial R and Current R)
        # ---------------------------------------------------------------------
        initial_sl = record.initial_sl if record.initial_sl > 0 else current_sl
        risk_dist = abs(open_px - initial_sl) if abs(open_px - initial_sl) > 0 else (1.5 * atr)
        cur_profit_dist = (current_px - open_px) if is_buy else (open_px - current_px)
        cur_r = cur_profit_dist / risk_dist if risk_dist > 0 else 0.0

        # ---------------------------------------------------------------------
        # 4. Strategy Exit / Invalidation Check [Requirement 8]
        # ---------------------------------------------------------------------
        if self.config.auto_exit_enabled and len(candles_m15) >= 10:
            skills_used.append("trend_by_structure")
            ctx_trend = Context(atr=atr)
            trend_res = trend_by_structure.evaluate(candles_m15, ctx_trend)
            trend_val = str(trend_res.metadata.get("trend") or ("BULLISH" if trend_res.status == "PASS" else "BEARISH")).upper()

            # Market structure reversal against open position
            reversal_detected = False
            reversal_detail = ""
            if is_buy and "BEAR" in trend_val:
                # Closed below recent swing low
                recent_lows = [c.low for c in candles_m15[-5:-1]]
                if recent_lows and candles_m15[-1].close < min(recent_lows):
                    reversal_detected = True
                    reversal_detail = "Confirmed BEARISH structure breakdown below recent pivot"
            elif not is_buy and "BULL" in trend_val:
                # Closed above recent swing high
                recent_highs = [c.high for c in candles_m15[-5:-1]]
                if recent_highs and candles_m15[-1].close > max(recent_highs):
                    reversal_detected = True
                    reversal_detail = "Confirmed BULLISH structure breakout above recent pivot"

            if reversal_detected:
                return AdoptionAssessment(
                    ticket=ticket,
                    symbol=symbol,
                    direction=pos.order_type,
                    classification=PositionClass.MANUAL,
                    action="CLOSE",
                    close_volume=pos.volume,
                    reason=f"Strategy exit triggered: {reversal_detail} [Requirement 8].",
                    skills_used=skills_used,
                    risk_r_current=cur_r
                )

        # ---------------------------------------------------------------------
        # 5. Break-Even Evaluation [VIDEO 12]
        # ---------------------------------------------------------------------
        if self.config.break_even_enabled and cur_r >= self.config.break_even_activation_r and not record.break_even_applied:
            skills_used.append("stop_management_policy")
            be_sl = (open_px + buffer) if is_buy else (open_px - buffer)
            if symbol_info:
                be_sl = symbol_info.round_price(be_sl)

            # Check tighten-only condition
            is_tightening = (be_sl > current_sl) if is_buy else (be_sl < current_sl)
            if is_tightening:
                return AdoptionAssessment(
                    ticket=ticket,
                    symbol=symbol,
                    direction=pos.order_type,
                    classification=PositionClass.MANUAL,
                    action="BREAK_EVEN",
                    recommended_sl=be_sl,
                    reason=f"Position reached +{cur_r:.2f}R. Moving SL to cost-covering Break-Even [VIDEO 12].",
                    skills_used=skills_used,
                    risk_r_current=cur_r
                )

        # ---------------------------------------------------------------------
        # 6. Trailing Stop Evaluation [VIDEO 12, VIDEO 15, Requirement 7]
        # ---------------------------------------------------------------------
        if self.config.trailing_stop_enabled and cur_r >= self.config.trailing_stop_activation_r:
            skills_used.extend(["swing_hierarchy", "structure_momentum_monitor"])
            recent_candles = candles_m5 if candles_m5 and len(candles_m5) >= 10 else candles_m15
            ctx_trail = Context(trend="BULL" if is_buy else "BEAR", atr=atr)
            res_mom = structure_momentum_monitor.evaluate(recent_candles, ctx_trail)

            trail_sl = current_sl

            if self.config.trailing_method == "ATR":
                # ATR-based trailing
                atr_dist = self.config.trailing_atr_multiplier * atr
                candidate_trail = (current_px - atr_dist) if is_buy else (current_px + atr_dist)
                if (is_buy and candidate_trail > current_sl and candidate_trail < current_px) or \
                   (not is_buy and candidate_trail < current_sl and candidate_trail > current_px):
                    trail_sl = candidate_trail
            elif self.config.trailing_method == "FIXED":
                # Fixed point distance trailing
                fixed_dist = self.config.trailing_fixed_points * pt
                candidate_trail = (current_px - fixed_dist) if is_buy else (current_px + fixed_dist)
                if (is_buy and candidate_trail > current_sl and candidate_trail < current_px) or \
                   (not is_buy and candidate_trail < current_sl and candidate_trail > current_px):
                    trail_sl = candidate_trail
            else:
                # Default: STRUCTURE-based trailing behind confirmed pivots
                if is_buy:
                    lows = [c.low for c in recent_candles[-6:-1]]
                    candidate_pivot = min(lows) if lows else (current_px - 1.0 * atr)
                    candidate_trail = candidate_pivot - (0.2 * atr)
                    if candidate_trail > current_sl and candidate_trail < current_px:
                        trail_sl = candidate_trail
                else:
                    highs = [c.high for c in recent_candles[-6:-1]]
                    candidate_pivot = max(highs) if highs else (current_px + 1.0 * atr)
                    candidate_trail = candidate_pivot + (0.2 * atr)
                    if candidate_trail < current_sl and candidate_trail > current_px:
                        trail_sl = candidate_trail

            if symbol_info:
                trail_sl = symbol_info.round_price(trail_sl)

            is_valid_trail = (trail_sl > current_sl) if is_buy else (trail_sl < current_sl)
            if is_valid_trail and abs(trail_sl - current_sl) >= (5.0 * pt):
                warning_text = ""
                if res_mom.metadata.get("exhaustion_warning"):
                    warning_text = " (Momentum exhaustion detected [VIDEO 15])"

                return AdoptionAssessment(
                    ticket=ticket,
                    symbol=symbol,
                    direction=pos.order_type,
                    classification=PositionClass.MANUAL,
                    action="TRAIL_SL",
                    recommended_sl=trail_sl,
                    reason=f"Advancing trailing stop ({self.config.trailing_method}) to {trail_sl:.5f} at +{cur_r:.2f}R{warning_text}.",
                    skills_used=skills_used,
                    risk_r_current=cur_r
                )

        # ---------------------------------------------------------------------
        # 7. Add-On (Pyramid) Opportunity Check [FULL Mode Only, Winners Only]
        # ---------------------------------------------------------------------
        if (
            record.assigned_mode == ManagementMode.FULL.value
            and record.add_ons_count < self.config.max_addons_per_position
            and cur_r >= self.config.min_addon_rr_in_profit
            and record.break_even_applied
        ):
            skills_used.append("trend_by_structure")
            ctx_trend = Context(atr=atr)
            trend_res = trend_by_structure.evaluate(candles_m15, ctx_trend)
            trend_val = trend_res.metadata.get("trend") or ("BULLISH" if trend_res.status == "PASS" else "BEARISH")
            bullish_ok = is_buy and "BULL" in str(trend_val).upper()
            bearish_ok = not is_buy and "BEAR" in str(trend_val).upper()

            if bullish_ok or bearish_ok:
                skills_used.append("five_check_model")
                addon_vol = round(float(pos.volume) * 0.5, 2)
                if symbol_info:
                    addon_vol = symbol_info.normalize_volume_down(addon_vol)

                if addon_vol >= (symbol_info.min_lot if symbol_info else 0.01):
                    return AdoptionAssessment(
                        ticket=ticket,
                        symbol=symbol,
                        direction=pos.order_type,
                        classification=PositionClass.MANUAL,
                        action="ADD_ON",
                        add_on_volume=addon_vol,
                        reason=f"Confirmed structural continuation trend while original trade at +{cur_r:.2f}R with BE secured [SAFETY].",
                        skills_used=skills_used,
                        risk_r_current=cur_r
                    )

        # ---------------------------------------------------------------------
        # 8. Default: Monitor & Maintain
        # ---------------------------------------------------------------------
        return AdoptionAssessment(
            ticket=ticket,
            symbol=symbol,
            direction=pos.order_type,
            classification=PositionClass.MANUAL,
            action="NONE",
            reason=f"Position healthy at +{cur_r:.2f}R. No structural stop amendment required.",
            skills_used=skills_used,
            risk_r_current=cur_r
        )
