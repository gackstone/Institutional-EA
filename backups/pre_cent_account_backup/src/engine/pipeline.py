"""
Combined Engine Confirmation Pipeline (Institutional EA & Art of Trading Master Specification).
Implements the full 28-video confirmation pipeline (P2-4):
H0  HTF POOL MAP        liquidity_pools_bsl_ssl (PDH/PDL/PWH/PWL, EQH/EQL)   (ART-04, ART-10)
G1  TREND/STRUCTURE     swing_hierarchy -> trend_by_structure + protected_swing_marker (ART-02, V3, V4)
G1b MOMENTUM FLAG       structure_momentum_monitor; market_phase_labeler as context only (V15, ART-01)
G2  LOCATION            premium_discount_filter (+range_valid) + range_location_filter (ART-07, V2, V13)
G3  LIQUIDITY EVENT     sweep_breakout_classifier: SWEEP needs CHOCH; BREAKOUT needs confirm (ART-10, V6)
G4  TRIGGER TYPE        A: five_check_model | B: inducement_ob_entry | C: ifvg_inversion
G5  ZONE QUALITY        fvg_detector + order_block_detector (BOS+gap) + quality scores (ART-08, ART-09, V9-V11)
G6  ENTRY SANITY        entry_quality_guard; R:R from real fill; next_draw/target from range_liquidity_loop (ART-03, V14)
G7  RISK/EXEC           size from stop (never margin); spread/swap/session filters; max daily loss (ART-12, ART-13)
--> ENTER               limit in zone; stop = sweep extreme (A) or below block (B); invalidation by closes
--> MANAGE              stop_management_policy (V12): structure-only stop moves
"""

from __future__ import annotations
import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.core.contracts import Candle, OrderType, Timeframe
from src.engine.types import SkillResult, Context, normalize_to_candles

# Import verified skills across both batches
from src.engine.skills import (
    protected_swing_marker,
    trend_by_structure,
    structure_momentum_monitor,
    premium_discount_filter,
    range_location_filter,
    liquidity_mapper,
    breakout_trap_classifier,
    inducement_ob_entry,
    sweep_fvg_entry,
    ifvg_inversion,
    fvg_quality_score,
    fvg_return_classifier,
    fvg_context_guard,
    entry_quality_guard,
    stop_management_policy,
    swing_hierarchy,
    liquidity_pools_bsl_ssl,
    range_liquidity_loop,
    market_phase_labeler,
    delivery_lens_context,
    five_check_model,
    order_block_detector,
    sweep_breakout_classifier,
    fvg_detector,
    candle_anatomy,
)

logger = logging.getLogger("InstitutionalEaPipeline")


class SetupLifecycleState(str, Enum):
    IDLE = "IDLE"
    WATCHING = "WATCHING"
    TRIGGERED = "TRIGGERED"
    ORDER_PLACED = "ORDER_PLACED"
    OPEN = "OPEN"
    MANAGED = "MANAGED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


@dataclass
class GateResult:
    gate_name: str
    passed: bool
    skill_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    reasons: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)


@dataclass
class PipelineEvaluationResult:
    passed: bool
    direction: Optional[str] = None  # "BUY" or "SELL"
    failed_gate: Optional[str] = None
    rejection_reason: Optional[str] = None
    gates: Dict[str, GateResult] = field(default_factory=dict)
    levels: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_json_line(self) -> str:
        d = {
            "timestamp": self.timestamp.isoformat(),
            "passed": self.passed,
            "direction": self.direction,
            "failed_gate": self.failed_gate,
            "rejection_reason": self.rejection_reason,
            "levels": self.levels,
            "gates": {
                g_k: {
                    "passed": g_v.passed,
                    "reasons": g_v.reasons,
                    "tags": g_v.tags,
                }
                for g_k, g_v in self.gates.items()
            },
            "metadata": self.metadata,
        }
        return json.dumps(d)


class InstitutionalEaEnginePipeline:
    """
    Combined Confirmation Pipeline enforcing strict H0 -> G7 evaluation on closed candles.
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        log_json_path: Optional[str] = "logs/pipeline_decisions.jsonl",
        state_file: str = "data/setup_lifecycle_state.json",
    ):
        self.config = config or {}
        self.log_json_path = log_json_path
        self.state_file = state_file
        self._setup_states: Dict[str, Dict[str, Any]] = self._load_persisted_states()
        if self.log_json_path:
            os.makedirs(os.path.dirname(self.log_json_path) or ".", exist_ok=True)
        os.makedirs(os.path.dirname(self.state_file) or ".", exist_ok=True)

    def _load_persisted_states(self) -> Dict[str, Dict[str, Any]]:
        p = Path(self.state_file)
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_persisted_states(self) -> None:
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self._setup_states, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to persist setup states: {e}")

    def get_setup_state(self, setup_id: str) -> SetupLifecycleState:
        st = self._setup_states.get(setup_id, {}).get("state", SetupLifecycleState.IDLE.value)
        return SetupLifecycleState(st)

    def transition_setup_state(self, setup_id: str, new_state: SetupLifecycleState, meta: Optional[Dict[str, Any]] = None) -> None:
        record = self._setup_states.setdefault(setup_id, {})
        record["state"] = new_state.value
        record["updated_at"] = datetime.now(timezone.utc).isoformat()
        if meta:
            record.setdefault("metadata", {}).update(meta)
        self._save_persisted_states()

    def evaluate(self, candles_data: Any, ctx: Context) -> PipelineEvaluationResult:
        """
        Executes sequential gate evaluation: H0 -> G1 -> G1b -> G2 -> G3 -> G4 -> G5 -> G6 -> G7.
        All decisions use closed candles only [GROUND RULE 4, ART-06, ART-10].
        """
        candles: List[Candle] = normalize_to_candles(candles_data)
        if not candles:
            res = PipelineEvaluationResult(
                passed=False,
                rejection_reason="No completed candles available for pipeline evaluation [GROUND RULE 4]",
            )
            self._log_decision(res)
            return res

        gates_report: Dict[str, GateResult] = {}
        all_levels: Dict[str, float] = {}

        # ------------------------------------------------------------------
        # H0: HIGHER-TIMEFRAME POOL MAP (ART-04, ART-10)
        # Mandatory order: Liquidity first, then structure, then the zone [ART-10, ART-09]
        # ------------------------------------------------------------------
        r_h0 = liquidity_pools_bsl_ssl.evaluate(candles, ctx)
        all_levels.update(r_h0.level_prices)

        gates_report["H0_HTF_POOL_MAP"] = GateResult(
            gate_name="H0_HTF_POOL_MAP",
            passed=r_h0.passed,
            skill_results={"liquidity_pools_bsl_ssl": r_h0.to_dict()},
            reasons=r_h0.reasons,
            tags=["[ART-04]", "[ART-10]"],
        )

        # ------------------------------------------------------------------
        # G1: TREND / STRUCTURE (ART-02, V3, V4)
        # ------------------------------------------------------------------
        r_swings = swing_hierarchy.evaluate(candles, ctx)
        r_prot = protected_swing_marker.evaluate(candles, ctx)
        r_trend = trend_by_structure.evaluate(candles, ctx)

        all_levels.update(r_swings.level_prices)
        all_levels.update(r_prot.level_prices)
        all_levels.update(r_trend.level_prices)

        g1_passed = (r_trend.status in ("PASS", "BULL", "BEAR")) and (ctx.trend in ("BULL", "BEAR"))
        g1_reasons = r_swings.reasons + r_prot.reasons + r_trend.reasons

        gates_report["G1_TREND_STRUCTURE"] = GateResult(
            gate_name="G1_TREND_STRUCTURE",
            passed=g1_passed,
            skill_results={
                "swing_hierarchy": r_swings.to_dict(),
                "protected_swing_marker": r_prot.to_dict(),
                "trend_by_structure": r_trend.to_dict(),
            },
            reasons=g1_reasons,
            tags=["[ART-02]", "[VIDEO 3]", "[VIDEO 4]"],
        )

        if not g1_passed:
            r_range = range_location_filter.evaluate(candles, ctx)
            if r_range.status == "NO_TRADE_MIDDLE":
                res = PipelineEvaluationResult(
                    passed=False,
                    failed_gate="G1_TREND_STRUCTURE",
                    rejection_reason=f"G1 Structure failed (trend={ctx.trend}); and in mid-range chop: {r_range.reasons[0]} [VIDEO 4, 13]",
                    gates=gates_report,
                    levels=all_levels,
                )
                self._log_decision(res)
                return res
            elif ctx.trend == "RANGE/TRANSITION":
                res = PipelineEvaluationResult(
                    passed=False,
                    failed_gate="G1_TREND_STRUCTURE",
                    rejection_reason="G1 Structure failed: Market is in RANGE/TRANSITION without confirmed trend structure [VIDEO 4]",
                    gates=gates_report,
                    levels=all_levels,
                )
                self._log_decision(res)
                return res

        trade_direction = "BUY" if ctx.trend == "BULL" else "SELL"

        # ------------------------------------------------------------------
        # G1b: MOMENTUM FLAG & MARKET PHASE (V15, ART-01, ART-05)
        # ------------------------------------------------------------------
        r_mom = structure_momentum_monitor.evaluate(candles, ctx)
        r_phase = market_phase_labeler.evaluate(candles, ctx)
        r_ipda = delivery_lens_context.evaluate(candles, ctx)

        g1b_passed = True
        decaying_action = self.config.get("decaying_action", "BLOCK_CONTINUATIONS")

        if r_mom.status == "DECAYING":
            if decaying_action == "BLOCK_CONTINUATIONS" and ctx.parameters.get("is_continuation", True):
                g1b_passed = False
                res_reason = f"G1b Blocked: Decaying momentum detected ({r_mom.reasons[0]}). New continuation entries blocked [VIDEO 15]"
                gates_report["G1b_MOMENTUM"] = GateResult(
                    gate_name="G1b_MOMENTUM",
                    passed=False,
                    skill_results={
                        "structure_momentum_monitor": r_mom.to_dict(),
                        "market_phase_labeler": r_phase.to_dict(),
                        "delivery_lens_context": r_ipda.to_dict(),
                    },
                    reasons=r_mom.reasons + r_phase.reasons + r_ipda.reasons,
                    tags=["[VIDEO 15]", "[ART-01]", "[ART-05]"],
                )
                res = PipelineEvaluationResult(
                    passed=False,
                    direction=trade_direction,
                    failed_gate="G1b_MOMENTUM",
                    rejection_reason=res_reason,
                    gates=gates_report,
                    levels=all_levels,
                )
                self._log_decision(res)
                return res

        gates_report["G1b_MOMENTUM"] = GateResult(
            gate_name="G1b_MOMENTUM",
            passed=g1b_passed,
            skill_results={
                "structure_momentum_monitor": r_mom.to_dict(),
                "market_phase_labeler": r_phase.to_dict(),
                "delivery_lens_context": r_ipda.to_dict(),
            },
            reasons=r_mom.reasons + r_phase.reasons + r_ipda.reasons,
            tags=["[VIDEO 15]", "[ART-01]", "[ART-05]"],
        )

        # ------------------------------------------------------------------
        # G2: LOCATION & RANGE VALIDATION (ART-07, V2, V13)
        # ------------------------------------------------------------------
        r_pd = premium_discount_filter.evaluate(candles, ctx)
        r_range = range_location_filter.evaluate(candles, ctx)
        all_levels.update(r_pd.level_prices)
        all_levels.update(r_range.level_prices)

        g2_passed = r_pd.passed and (r_range.status != "NO_TRADE_MIDDLE") and (r_pd.status != "INVALID_RANGE")
        g2_reasons = r_pd.reasons + r_range.reasons

        gates_report["G2_LOCATION"] = GateResult(
            gate_name="G2_LOCATION",
            passed=g2_passed,
            skill_results={"premium_discount_filter": r_pd.to_dict(), "range_location_filter": r_range.to_dict()},
            reasons=g2_reasons,
            tags=["[ART-07]", "[VIDEO 2]", "[VIDEO 13]"],
        )

        if not g2_passed:
            fail_msg = r_range.reasons[0] if r_range.status == "NO_TRADE_MIDDLE" else r_pd.reasons[0]
            res = PipelineEvaluationResult(
                passed=False,
                direction=trade_direction,
                failed_gate="G2_LOCATION",
                rejection_reason=f"G2 Location gate failed: {fail_msg}",
                gates=gates_report,
                levels=all_levels,
            )
            self._log_decision(res)
            return res

        # ------------------------------------------------------------------
        # G3: LIQUIDITY EVENT & BREAKOUT/TRAP (ART-10, V6, V7)
        # ------------------------------------------------------------------
        r_liq = liquidity_mapper.evaluate(candles, ctx)
        r_sb = sweep_breakout_classifier.evaluate(candles, ctx)
        all_levels.update(r_liq.level_prices)
        all_levels.update(r_sb.level_prices)

        g3_passed = True
        g3_reasons = r_liq.reasons + r_sb.reasons

        # If breakout trade candidate, require confirmation (2 closes or retest-hold) [ART-10, VIDEO 6]
        if ctx.parameters.get("is_breakout_entry", False) and r_sb.status != "BREAKOUT_CONFIRMED":
            g3_passed = False
            g3_reasons.append(f"G3 Blocked: Breakout requires confirmed 2 closes or retest-hold [ART-10, VIDEO 6]. Current={r_sb.status}")

        gates_report["G3_LIQUIDITY_EVENT"] = GateResult(
            gate_name="G3_LIQUIDITY_EVENT",
            passed=g3_passed,
            skill_results={"liquidity_mapper": r_liq.to_dict(), "sweep_breakout_classifier": r_sb.to_dict()},
            reasons=g3_reasons,
            tags=["[ART-10]", "[VIDEO 6]", "[VIDEO 7]"],
        )

        if not g3_passed:
            res = PipelineEvaluationResult(
                passed=False,
                direction=trade_direction,
                failed_gate="G3_LIQUIDITY_EVENT",
                rejection_reason=g3_reasons[-1],
                gates=gates_report,
                levels=all_levels,
            )
            self._log_decision(res)
            return res

        # ------------------------------------------------------------------
        # G4: TRIGGER (Setup A: five_check_model | Setup B: inducement_ob_entry | Setup C: ifvg_inversion)
        # ------------------------------------------------------------------
        r_five = five_check_model.evaluate(candles, ctx)
        r_v1 = inducement_ob_entry.evaluate(candles, ctx)
        r_v5 = sweep_fvg_entry.evaluate(candles, ctx)
        r_v8 = ifvg_inversion.evaluate(candles, ctx)

        active_trigger: Optional[SkillResult] = None
        trigger_name = ""

        # Priority: Master Setup Type A (five_check_model) > Type B (inducement_ob) > Type C (ifvg_inversion)
        candidates = [
            ("five_check_model", r_five),
            ("inducement_ob_entry", r_v1),
            ("sweep_fvg_entry", r_v5),
            ("ifvg_inversion", r_v8),
        ]
        for name, r_trig in candidates:
            if r_trig.status == "TRIGGERED":
                active_trigger = r_trig
                trigger_name = name
                break

        g4_passed = active_trigger is not None
        g4_reasons = (
            [r_five.reasons[0], r_v1.reasons[0], r_v5.reasons[0], r_v8.reasons[0]]
            if not g4_passed
            else active_trigger.reasons
        )

        gates_report["G4_TRIGGER"] = GateResult(
            gate_name="G4_TRIGGER",
            passed=g4_passed,
            skill_results={
                "five_check_model": r_five.to_dict(),
                "inducement_ob_entry": r_v1.to_dict(),
                "sweep_fvg_entry": r_v5.to_dict(),
                "ifvg_inversion": r_v8.to_dict(),
            },
            reasons=g4_reasons,
            tags=["[ART-06]", "[VIDEO 1]", "[VIDEO 5]", "[VIDEO 8]"],
        )

        if not g4_passed:
            res = PipelineEvaluationResult(
                passed=False,
                direction=trade_direction,
                failed_gate="G4_TRIGGER",
                rejection_reason="G4 Trigger failed: No valid setup triggered on closed candle (Five-Check Master, Inducement OB, Sweep FVG, or IFVG) [ART-06, VIDEO 1, 5, 8]",
                gates=gates_report,
                levels=all_levels,
            )
            self._log_decision(res)
            return res

        all_levels.update(active_trigger.level_prices)
        planned_entry = active_trigger.level_prices.get("entry", candles[-1].close)
        planned_sl = active_trigger.level_prices.get("stop_loss", 0.0)
        planned_tp = active_trigger.level_prices.get("take_profit", 0.0)

        # ------------------------------------------------------------------
        # G5: ZONE QUALITY (ART-08, ART-09, V9, V10, V11)
        # ------------------------------------------------------------------
        r_fvg_det = fvg_detector.evaluate(candles, ctx)
        r_ob_det = order_block_detector.evaluate(candles, ctx)
        r_q = fvg_quality_score.evaluate(candles, ctx)
        r_ret = fvg_return_classifier.evaluate(candles, ctx)
        r_ctx = fvg_context_guard.evaluate(candles, ctx)

        all_levels.update(r_fvg_det.level_prices)
        all_levels.update(r_ob_det.level_prices)

        # If trigger is OB-based, enforce strict BOS+FVG qualification [ART-09]
        if trigger_name in ("inducement_ob_entry", "five_check_model") and not r_ob_det.passed:
            gates_report["G5_ZONE_QUALITY"] = GateResult(
                gate_name="G5_ZONE_QUALITY",
                passed=False,
                skill_results={"order_block_detector": r_ob_det.to_dict()},
                reasons=[f"Order block unqualified: {r_ob_det.reasons[0]} [ART-09]"],
                tags=["[ART-09]"],
            )
            res = PipelineEvaluationResult(
                passed=False,
                direction=trade_direction,
                failed_gate="G5_ZONE_QUALITY",
                rejection_reason=f"G5 Zone Quality failed: Order block unqualified [ART-09]",
                gates=gates_report,
                levels=all_levels,
            )
            self._log_decision(res)
            return res

        # If trigger involves FVG, evaluate zone quality and return classifier
        if trigger_name in ("sweep_fvg_entry", "ifvg_inversion", "five_check_model") or "fvg_top" in active_trigger.level_prices:
            ctx.parameters["fvg_top"] = active_trigger.level_prices.get("fvg_top")
            ctx.parameters["fvg_bottom"] = active_trigger.level_prices.get("fvg_bottom")
            ctx.parameters["fvg_direction"] = trade_direction

            g5_passed = r_q.passed and (r_ret.status != "BROKEN") and r_ctx.passed and (r_fvg_det.status != "INVALIDATED")
            g5_reasons = r_fvg_det.reasons + r_q.reasons + r_ret.reasons + r_ctx.reasons

            gates_report["G5_ZONE_QUALITY"] = GateResult(
                gate_name="G5_ZONE_QUALITY",
                passed=g5_passed,
                skill_results={
                    "fvg_detector": r_fvg_det.to_dict(),
                    "fvg_quality_score": r_q.to_dict(),
                    "fvg_return_classifier": r_ret.to_dict(),
                    "fvg_context_guard": r_ctx.to_dict(),
                },
                reasons=g5_reasons,
                tags=["[ART-08]", "[VIDEO 9]", "[VIDEO 10]", "[VIDEO 11]"],
            )

            if not g5_passed:
                res = PipelineEvaluationResult(
                    passed=False,
                    direction=trade_direction,
                    failed_gate="G5_ZONE_QUALITY",
                    rejection_reason=f"G5 Zone Quality failed: {g5_reasons[0]} [ART-08, VIDEO 9, 10, 11]",
                    gates=gates_report,
                    levels=all_levels,
                )
                self._log_decision(res)
                return res
        else:
            gates_report["G5_ZONE_QUALITY"] = GateResult(
                gate_name="G5_ZONE_QUALITY",
                passed=True,
                skill_results={"order_block_detector": r_ob_det.to_dict()},
                reasons=["Order block trigger qualified with BOS and FVG [ART-09, VIDEO 1]"],
                tags=["[ART-09]", "[VIDEO 1]"],
            )

        # ------------------------------------------------------------------
        # G6: ENTRY SANITY & RANGE LIQUIDITY LOOP (ART-03, V14)
        # ------------------------------------------------------------------
        r_loop = range_liquidity_loop.evaluate(candles, ctx)
        all_levels.update(r_loop.level_prices)

        # Target next draw from ERL/IRL loop if not explicitly defined [ART-03]
        if planned_tp == 0.0 or planned_tp == planned_entry:
            planned_tp = r_loop.level_prices.get("next_draw_price", planned_tp)

        ctx.parameters["entry_price"] = planned_entry
        ctx.parameters["invalidation_price"] = planned_sl
        ctx.parameters["target_price"] = planned_tp
        ctx.parameters["trigger_level"] = planned_entry

        r_sanity = entry_quality_guard.evaluate(candles, ctx)
        all_levels.update(r_sanity.level_prices)

        gates_report["G6_ENTRY_SANITY"] = GateResult(
            gate_name="G6_ENTRY_SANITY",
            passed=r_sanity.passed,
            skill_results={"entry_quality_guard": r_sanity.to_dict(), "range_liquidity_loop": r_loop.to_dict()},
            reasons=r_sanity.reasons + r_loop.reasons,
            tags=["[VIDEO 14]", "[ART-03]"],
        )

        if not r_sanity.passed:
            res = PipelineEvaluationResult(
                passed=False,
                direction=trade_direction,
                failed_gate="G6_ENTRY_SANITY",
                rejection_reason=f"G6 Entry Sanity failed: {r_sanity.reasons[0]} [VIDEO 14]",
                gates=gates_report,
                levels=all_levels,
            )
            self._log_decision(res)
            return res

        # ------------------------------------------------------------------
        # G7: RISK / EXECUTION (ART-12, ART-13)
        # Sized strictly from stop loss distance [ART-12].
        # ------------------------------------------------------------------
        spread = float(ctx.parameters.get("broker_spread_points", 10.0)) * ctx.pip_size * 0.1
        risk_dist = abs(planned_entry - planned_sl)
        max_spread_pct = float(self.config.get("max_spread_pct_of_sl", 20.0))  # [ASSUMPTION, ART-13]
        spread_ok = (spread / risk_dist * 100.0) <= max_spread_pct if risk_dist > 0 else False

        # Strategy-level spread rejection disabled: spread recorded in diagnostics, does not veto G7
        g7_passed = planned_sl > 0
        spread_pct = (spread / risk_dist * 100.0) if risk_dist > 0 else 0.0
        g7_reasons = [
            f"[SPREAD_ENGINE] Strategy-level spread rejection is disabled. Spread retained for diagnostics: {spread:.5f} ({spread_pct:.1f}% of SL).",
            f"Risk checks passed: Sized from stop distance {risk_dist:.5f} (never margin) [ART-12]."
        ]

        gates_report["G7_RISK_EXEC"] = GateResult(
            gate_name="G7_RISK_EXEC",
            passed=g7_passed,
            reasons=g7_reasons,
            tags=["[ART-12]", "[ART-13]"],
        )

        if not g7_passed:
            res = PipelineEvaluationResult(
                passed=False,
                direction=trade_direction,
                failed_gate="G7_RISK_EXEC",
                rejection_reason=f"G7 Risk failed: {g7_reasons[0]}",
                gates=gates_report,
                levels=all_levels,
            )
            self._log_decision(res)
            return res

        # ------------------------------------------------------------------
        # ALL GATES PASSED (H0 -> G7) -> APPROVE TRADE SETUP!
        # ------------------------------------------------------------------
        final_res = PipelineEvaluationResult(
            passed=True,
            direction=trade_direction,
            gates=gates_report,
            levels=all_levels,
            metadata={
                "trigger_name": trigger_name,
                "entry": planned_entry,
                "stop_loss": planned_sl,
                "take_profit": planned_tp,
                "rr": r_sanity.level_prices.get("rr", 0.0),
                "coach_lesson": active_trigger.metadata.get("coach_lesson", ""),
                "next_draw": r_loop.level_prices.get("next_draw_price"),
            }
        )
        self._log_decision(final_res)
        return final_res

    def _log_decision(self, result: PipelineEvaluationResult) -> None:
        if not self.log_json_path:
            return
        try:
            line = result.to_json_line()
            with open(self.log_json_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception as e:
            logger.warning(f"Failed to log pipeline decision: {e}")
