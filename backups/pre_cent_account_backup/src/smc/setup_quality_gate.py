"""
Setup Quality Gate (Phase 2).

Thin validation layer sitting between candidate detection ("setup detected")
and order execution ("order placed"). Evaluates every candidate signal against
the Canonical SMC Rulebook (R1-R9):

Hard Gates (G1-G8, individually toggleable):
- G1 Structure: HTF (H4/D1) trend is clear (R1) and a body-close BOS in the trade direction exists (R2).
- G2 Zone: Entry is on the correct side of equilibrium (R7): buys in discount (<50%), sells in premium (>50%).
- G3 Sweep: A liquidity sweep with close-back-inside occurred before entry (R4).
- G4 POI Quality: An OrderBlock meeting R5 and/or an FVG meeting R6 exists at entry (OB+FVG gives score bonus).
- G5 LTF Confirmation: LTF CHoCH + BOS confirmed inside the zone, with entry on pullback into POI (no breakout candle chasing) (R2, R3, R8).
- G6 HTF Alignment: Not trading against the HTF (H4/D1) trend (R1, R8).
- G7 Stops/Targets: SL beyond sweep/POI extreme; TP at next liquidity pool; RR >= min_rr (default 2.0) (R4, R8).
- G8 Risk: Risk per trade <= max_risk_pct (hard cap 2.0%); valid SL present (R9).

Soft Factors (adjust score/size multiplier, do not reject):
- OB + FVG spatial confluence
- HTF POI confluence
- Session / Killzone quality
- News proximity
- Volume bias / MTF alignment score

Modes:
- OFF: Gate bypassed (always passes).
- SHADOW: Evaluates and logs full gate diagnostics, never blocks (default).
- ENFORCE: Blocks any candidate with one or more enabled hard-gate failures.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from src.core.contracts import (
    Candle,
    OrderType,
    TrendBias,
    SetupType,
    SignalCandidate,
)
from src.smc.mtf_analyzer import MultiTimeframeContext
from src.smc.structure_confirmation import (
    StructureStateSnapshot,
    ConfirmationState,
    CycleDirection,
)
from src.smc.fvg_ob import FvgObEngine
from src.smc.smc_rulebook import (
    SmcRulebookConfig,
    GateMode,
    NoTradeReason,
)

logger = logging.getLogger("SetupQualityGate")


@dataclass
class QualityGateVerdict:
    """Result returned by SetupQualityGate.evaluate()."""
    passed: bool
    effective_pass: bool  # True in SHADOW/OFF even when passed=False; equals passed in ENFORCE
    mode: GateMode
    score: float
    size_multiplier: float
    hard_fails: List[str] = field(default_factory=list)
    soft_warnings: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    gate_details: Dict[str, bool] = field(default_factory=dict)

    @property
    def blocked(self) -> bool:
        return not self.effective_pass

    @property
    def reason_codes(self) -> List[str]:
        return self.hard_fails

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pass": self.passed,
            "effective_pass": self.effective_pass,
            "mode": self.mode.value,
            "score": round(self.score, 2),
            "size_multiplier": round(self.size_multiplier, 3),
            "hard_fails": list(self.hard_fails),
            "soft_warnings": list(self.soft_warnings),
            "reasons": list(self.reasons),
            "gate_details": dict(self.gate_details),
        }


class SetupQualityGate:
    """
    Evaluates a SignalCandidate against Hard Gates G1-G8 and Soft Factors.
    """

    def __init__(self, config: Optional[SmcRulebookConfig] = None):
        self.config = config or SmcRulebookConfig()

    def evaluate(
        self,
        candidate: SignalCandidate,
        mtf_ctx: Optional[MultiTimeframeContext] = None,
        ltf_candles: Optional[List[Candle]] = None,
        struct_state: Optional[StructureStateSnapshot] = None,
        proposed_risk_pct: Optional[float] = None,
        is_in_killzone: bool = False,
        news_safe: bool = True,
        volume_bias_aligned: Optional[bool] = None,
        mtf: Optional[MultiTimeframeContext] = None,
    ) -> QualityGateVerdict:
        if mtf_ctx is None and mtf is not None:
            mtf_ctx = mtf
        """
        Runs all Hard Gates (G1-G8) and Soft Factors on `candidate`.
        """
        mode = self.config.gate_mode
        if mode == GateMode.OFF:
            return QualityGateVerdict(
                passed=True,
                effective_pass=True,
                mode=mode,
                score=candidate.score,
                size_multiplier=1.0,
                reasons=["Gate mode is OFF"],
            )

        hard_fails: List[str] = []
        soft_warnings: List[str] = []
        reasons: List[str] = list(candidate.reasons) if candidate.reasons else []
        gate_details: Dict[str, bool] = {}

        score = float(candidate.score)
        size_mult = 1.0
        is_buy = candidate.direction == OrderType.BUY

        # ------------------------------------------------------------------
        # G1: Structure (HTF trend clear + BOS in trade direction) (R1, R2)
        # ------------------------------------------------------------------
        g1_ok = True
        if mtf_ctx is not None:
            h4_clear = mtf_ctx.h4.trend != TrendBias.RANGING
            d1_clear = mtf_ctx.d1.trend != TrendBias.RANGING
            if not h4_clear and not d1_clear:
                g1_ok = False
                if self.config.g1_structure_enabled:
                    hard_fails.append(NoTradeReason.UNCLEAR_STRUCTURE)
                else:
                    soft_warnings.append(f"{NoTradeReason.UNCLEAR_STRUCTURE} (G1 disabled)")
            else:
                htf_bos = getattr(mtf_ctx.h4, "has_bos_in_trend", True) or getattr(mtf_ctx.d1, "has_bos_in_trend", True)
                if not htf_bos:
                    g1_ok = False
                    if self.config.g1_structure_enabled:
                        hard_fails.append(NoTradeReason.NO_HTF_BOS)
                    else:
                        soft_warnings.append(f"{NoTradeReason.NO_HTF_BOS} (G1 disabled)")
        gate_details["G1_structure"] = g1_ok

        # ------------------------------------------------------------------
        # G2: Zone (Premium / Discount 50% Equilibrium) (R7)
        # ------------------------------------------------------------------
        g2_ok = True
        if mtf_ctx is not None:
            # Check active swing range on M15/H1/H4
            if is_buy:
                in_discount = (
                    mtf_ctx.m15.is_discount
                    or mtf_ctx.h1.is_discount
                    or mtf_ctx.h4.is_discount
                )
                if not in_discount:
                    g2_ok = False
                    if self.config.g2_zone_enabled:
                        hard_fails.append(NoTradeReason.WRONG_PD_ZONE)
                    else:
                        soft_warnings.append("G2_SHADOW: BUY candidate in Premium (>50% equilibrium)")
                else:
                    reasons.append("G2_PASS: BUY in Discount (<50% equilibrium)")
            else:
                in_premium = (
                    mtf_ctx.m15.is_premium
                    or mtf_ctx.h1.is_premium
                    or mtf_ctx.h4.is_premium
                )
                if not in_premium:
                    g2_ok = False
                    if self.config.g2_zone_enabled:
                        hard_fails.append(NoTradeReason.WRONG_PD_ZONE)
                    else:
                        soft_warnings.append("G2_SHADOW: SELL candidate in Discount (<50% equilibrium)")
                else:
                    reasons.append("G2_PASS: SELL in Premium (>50% equilibrium)")
        gate_details["G2_zone"] = g2_ok

        # ------------------------------------------------------------------
        # G3: Liquidity Sweep with Close-Back-Inside (R4)
        # ------------------------------------------------------------------
        g3_ok = self._check_g3_sweep(candidate, mtf_ctx, ltf_candles)
        if not g3_ok:
            if self.config.g3_sweep_enabled:
                hard_fails.append(NoTradeReason.NO_SWEEP)
            else:
                soft_warnings.append(f"{NoTradeReason.NO_SWEEP} (G3 disabled)")
        else:
            reasons.append("G3_PASS: Liquidity sweep + close-back-inside verified")
        gate_details["G3_sweep"] = g3_ok

        # ------------------------------------------------------------------
        # G4: POI Quality (Valid OB [R5] and/or Valid FVG [R6] at entry)
        # ------------------------------------------------------------------
        g4_ok, has_ob_fvg_bonus = self._check_g4_poi_quality(candidate, ltf_candles)
        if not g4_ok:
            if self.config.g4_poi_quality_enabled:
                hard_fails.append(NoTradeReason.WEAK_OR_MISSING_POI)
            else:
                soft_warnings.append(f"{NoTradeReason.WEAK_OR_MISSING_POI} (G4 disabled)")
        else:
            reasons.append("G4_PASS: Valid displacement OB/FVG POI present")
        if has_ob_fvg_bonus:
            score = min(100.0, score + self.config.ob_fvg_confluence_bonus_pts)
            reasons.append(f"SOFT_BONUS: OB + FVG confluence (+{self.config.ob_fvg_confluence_bonus_pts:.0f})")
        gate_details["G4_poi_quality"] = g4_ok

        # ------------------------------------------------------------------
        # G5: LTF Confirmation & No Breakout-Candle Chasing (R2, R3, R8)
        # ------------------------------------------------------------------
        g5_ok = self._check_g5_ltf_confirmation(candidate, struct_state, ltf_candles)
        if not g5_ok:
            if self.config.g5_ltf_confirm_enabled:
                hard_fails.append(NoTradeReason.NO_LTF_CONFIRMATION)
            else:
                soft_warnings.append(f"{NoTradeReason.NO_LTF_CONFIRMATION} (G5 disabled)")
        else:
            reasons.append("G5_PASS: LTF structure confirmed & entry on pullback")
        gate_details["G5_ltf_confirm"] = g5_ok

        # ------------------------------------------------------------------
        # G6: HTF Alignment (Not trading against H4/D1 trend) (R1, R8)
        # ------------------------------------------------------------------
        g6_ok = True
        if mtf_ctx is not None:
            h4_bull = mtf_ctx.h4.trend in (TrendBias.STRONG_BULLISH, TrendBias.WEAK_BULLISH)
            h4_bear = mtf_ctx.h4.trend in (TrendBias.STRONG_BEARISH, TrendBias.WEAK_BEARISH)
            d1_bull = mtf_ctx.d1.trend in (TrendBias.STRONG_BULLISH, TrendBias.WEAK_BULLISH)
            d1_bear = mtf_ctx.d1.trend in (TrendBias.STRONG_BEARISH, TrendBias.WEAK_BEARISH)

            if is_buy and (h4_bear or (mtf_ctx.h4.trend == TrendBias.RANGING and d1_bear)):
                g6_ok = False
            elif (not is_buy) and (h4_bull or (mtf_ctx.h4.trend == TrendBias.RANGING and d1_bull)):
                g6_ok = False

            if not g6_ok:
                if self.config.g6_htf_alignment_enabled:
                    hard_fails.append(NoTradeReason.HTF_COUNTERTREND)
                else:
                    soft_warnings.append(f"{NoTradeReason.HTF_COUNTERTREND} (G6 disabled)")
            else:
                reasons.append("G6_PASS: Aligned with HTF (H4/D1) trend")
        gate_details["G6_htf_alignment"] = g6_ok

        # ------------------------------------------------------------------
        # G7: Stops & Targets (SL beyond extreme, TP at liquidity, RR >= min_rr) (R8)
        # ------------------------------------------------------------------
        g7_ok, g7_fail_codes = self._check_g7_stops_targets(candidate, mtf_ctx, ltf_candles)
        if not g7_ok:
            if self.config.g7_stops_targets_enabled:
                hard_fails.extend(g7_fail_codes)
            else:
                for code in g7_fail_codes:
                    soft_warnings.append(f"{code} (G7 disabled)")
        else:
            reasons.append(f"G7_PASS: Structural SL/TP valid with RR={candidate.risk_reward:.2f} >= {self.config.min_rr:.2f}")
        gate_details["G7_stops_targets"] = g7_ok

        # ------------------------------------------------------------------
        # G8: Risk Cap (<= 2.0% hard cap) & Mandatory Stop Loss (R9)
        # ------------------------------------------------------------------
        g8_ok = True
        risk_val = proposed_risk_pct if proposed_risk_pct is not None else self.config.default_risk_pct
        has_valid_sl = (
            candidate.stop_loss > 0
            and ((is_buy and candidate.stop_loss < candidate.entry_price) or (not is_buy and candidate.stop_loss > candidate.entry_price))
        )
        if not has_valid_sl:
            g8_ok = False
            if self.config.g8_risk_enabled:
                hard_fails.append(NoTradeReason.MISSING_STOP_LOSS)
            else:
                soft_warnings.append(f"{NoTradeReason.MISSING_STOP_LOSS} (G8 disabled)")

        if risk_val > min(2.0, self.config.max_risk_pct) + 1e-9:
            g8_ok = False
            if self.config.g8_risk_enabled:
                hard_fails.append(NoTradeReason.RISK_ABOVE_CAP)
            else:
                soft_warnings.append(f"{NoTradeReason.RISK_ABOVE_CAP} (G8 disabled)")
        gate_details["G8_risk"] = g8_ok

        # ------------------------------------------------------------------
        # Soft Factors (Adjust score & size_multiplier, never reject)
        # ------------------------------------------------------------------
        if is_in_killzone:
            score = min(100.0, score + 3.0)
            reasons.append("SOFT_FACTOR: Active London/NY Killzone (+3)")
        else:
            soft_warnings.append("SOFT_WARN: Outside primary London/NY Killzone")
            size_mult *= 0.90

        if not news_safe:
            soft_warnings.append("SOFT_WARN: High-impact news proximity")
            size_mult *= 0.75

        if volume_bias_aligned is True:
            score = min(100.0, score + 2.0)
            reasons.append("SOFT_FACTOR: Tick-volume directional bias aligned (+2)")
        elif volume_bias_aligned is False:
            soft_warnings.append("SOFT_WARN: Tick-volume bias opposes trade direction")
            size_mult *= 0.85

        passed = len(hard_fails) == 0
        effective_pass = passed if mode == GateMode.ENFORCE else True

        if not passed:
            log_fn = logger.info if mode == GateMode.SHADOW else logger.warning
            log_fn(
                "[SetupQualityGate][%s] %s %s NO_TRADE_REASONS=%s | soft_warnings=%s",
                mode.value,
                candidate.symbol,
                candidate.direction.value,
                hard_fails,
                soft_warnings,
            )

        return QualityGateVerdict(
            passed=passed,
            effective_pass=effective_pass,
            mode=mode,
            score=score,
            size_multiplier=max(0.25, min(1.25, size_mult)),
            hard_fails=hard_fails,
            soft_warnings=soft_warnings,
            reasons=reasons,
            gate_details=gate_details,
        )

    def _check_g3_sweep(
        self,
        candidate: SignalCandidate,
        mtf_ctx: Optional[MultiTimeframeContext],
        ltf_candles: Optional[List[Candle]],
    ) -> bool:
        """Verifies that a liquidity sweep + close-back-inside occurred (R4)."""
        # 1. Explicit sweep setup types or related levels
        if candidate.setup_type in (
            SetupType.WEEKLY_REVERSAL,
            SetupType.DAILY_REVERSAL,
            SetupType.SESSION_SWEEP,
            SetupType.LIQUIDITY_SWEEP,
            SetupType.TRENDLINE_LIQUIDITY,
        ):
            return True
        if candidate.related_level and "SWEEP" in candidate.related_level.upper():
            return True
        if mtf_ctx is not None and any("SWEEP" in r.interaction.value for r in mtf_ctx.level_interactions):
            return True

        # 2. Check recent LTF candles for a sweep of a prior local swing high/low with close back inside
        if ltf_candles and len(ltf_candles) >= 12:
            prior = ltf_candles[:-4]
            recent = ltf_candles[-4:]
            if prior:
                prior_low = min(c.low for c in prior[-15:])
                prior_high = max(c.high for c in prior[-15:])
                if candidate.direction == OrderType.BUY:
                    if any(c.low < prior_low and c.close > prior_low for c in recent) or (
                        min(c.low for c in recent) < prior_low and recent[-1].close > prior_low
                    ):
                        return True
                else:
                    if any(c.high > prior_high and c.close < prior_high for c in recent) or (
                        max(c.high for c in recent) > prior_high and recent[-1].close < prior_high
                    ):
                        return True
        return False

    def _check_g4_poi_quality(
        self,
        candidate: SignalCandidate,
        ltf_candles: Optional[List[Candle]],
    ) -> tuple[bool, bool]:
        """
        Verifies an R5-valid OB and/or R6-valid FVG exists and checks OB+FVG confluence.
        Returns (g4_ok, has_ob_fvg_bonus).
        """
        has_ob = candidate.ob is not None and not getattr(candidate.ob, "mitigated", False)
        has_fvg = candidate.fvg is not None and not getattr(candidate.fvg, "mitigated", False)
        confluence = FvgObEngine.has_ob_fvg_confluence(candidate.ob, candidate.fvg)
        if has_ob or has_fvg:
            return True, confluence
        return False, False

    def _check_g5_ltf_confirmation(
        self,
        candidate: SignalCandidate,
        struct_state: Optional[StructureStateSnapshot],
        ltf_candles: Optional[List[Candle]],
    ) -> bool:
        """
        Verifies LTF confirmation (R3: no lone CHoCH) and rejects chasing the breakout candle (R2/R8).
        """
        is_buy = candidate.direction == OrderType.BUY

        # 1. Check StructureStateMachine if provided
        if struct_state is not None:
            same_dir = (
                (is_buy and struct_state.direction == CycleDirection.BULLISH)
                or (not is_buy and struct_state.direction == CycleDirection.BEARISH)
            )
            if same_dir and struct_state.state in (
                ConfirmationState.CHOCH_WARNING,
                ConfirmationState.PULLBACK,
                ConfirmationState.FAILED_TRAP,
            ):
                return False

        # 2. Check candidate rejection reasons for unconfirmed CHoCH
        for rej in candidate.rejection_reasons or []:
            if "CHoCH" in rej or "unconfirmed" in rej.lower():
                return False

        # 3. Reject chasing the breakout/displacement candle itself (R2/R8)
        if self.config.reject_breakout_candle_chase and ltf_candles and len(ltf_candles) >= 10:
            last_c = ltf_candles[-1]
            prior_bars = ltf_candles[-10:-1]
            avg_range = sum(c.range for c in prior_bars) / len(prior_bars) if prior_bars else 0.0
            prior_high = max(c.high for c in prior_bars)
            prior_low = min(c.low for c in prior_bars)

            # If the current entry candle is a massive expansion candle closing beyond the 9-bar range extreme
            # without having pulled back into the POI, it is chasing the breakout candle
            if avg_range > 0 and last_c.body >= 1.8 * avg_range:
                if is_buy and last_c.close > prior_high:
                    return False
                if (not is_buy) and last_c.close < prior_low:
                    return False

        return True

    def _check_g7_stops_targets(
        self,
        candidate: SignalCandidate,
        mtf_ctx: Optional[MultiTimeframeContext],
        ltf_candles: Optional[List[Candle]],
    ) -> tuple[bool, List[str]]:
        """
        Verifies:
        1. SL is placed beyond the sweep/POI extreme.
        2. TP is anchored at a structural liquidity pool.
        3. Reward-to-risk RR >= min_rr (default 2.0).
        """
        fails: List[str] = []
        is_buy = candidate.direction == OrderType.BUY

        # 1. RR check
        if candidate.risk_reward < self.config.min_rr - 1e-9:
            fails.append(NoTradeReason.RR_TOO_LOW)

        # 2. SL beyond OB / recent 3-bar sweep extreme check
        if is_buy:
            if candidate.stop_loss >= candidate.entry_price:
                fails.append(NoTradeReason.INVALID_SL_EXTREME)
            elif candidate.ob is not None and candidate.stop_loss > candidate.ob.low:
                fails.append(NoTradeReason.INVALID_SL_EXTREME)
            elif ltf_candles and len(ltf_candles) >= 3:
                recent_low = min(c.low for c in ltf_candles[-3:])
                if candidate.stop_loss > recent_low:
                    fails.append(NoTradeReason.INVALID_SL_EXTREME)
        else:
            if candidate.stop_loss <= candidate.entry_price:
                fails.append(NoTradeReason.INVALID_SL_EXTREME)
            elif candidate.ob is not None and candidate.stop_loss < candidate.ob.high:
                fails.append(NoTradeReason.INVALID_SL_EXTREME)
            elif ltf_candles and len(ltf_candles) >= 3:
                recent_high = max(c.high for c in ltf_candles[-3:])
                if candidate.stop_loss < recent_high:
                    fails.append(NoTradeReason.INVALID_SL_EXTREME)

        # 3. TP structural liquidity check
        if is_buy and candidate.take_profit <= candidate.entry_price:
            fails.append(NoTradeReason.NO_LIQUIDITY_TP)
        elif (not is_buy) and candidate.take_profit >= candidate.entry_price:
            fails.append(NoTradeReason.NO_LIQUIDITY_TP)

        return len(fails) == 0, fails
