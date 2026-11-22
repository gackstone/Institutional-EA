"""
Unit tests for Phase 2 (SetupQualityGate G1-G8 & modes) and Phase 3 (R9 Risk-Rule Enforcement).
"""

from __future__ import annotations
import unittest
from datetime import datetime, timezone
from typing import List, Optional

from src.core.config import AppConfig
from src.core.contracts import (
    AccountInfo,
    AccountTier,
    Candle,
    ExecutionMode,
    FairValueGap,
    OrderBlock,
    OrderType,
    PlanAmendment,
    SetupType,
    SignalCandidate,
    SymbolInfo,
    Timeframe,
    TradePlan,
    TrendBias,
    WeeklyDailyLevels,
)
from src.execution.bridge_client import BridgeClient
from src.execution.order_manager import OrderManager
from src.execution.persistent_socket import BrokerConstraintValidator
from src.risk.account_tier import AccountTierManager
from src.risk.portfolio_risk import PortfolioRiskEngine
from src.risk.position_sizing import PositionSizingEngine
from src.smc.mtf_analyzer import MultiTimeframeContext, TimeframeAnalysis
from src.smc.setup_quality_gate import SetupQualityGate
from src.smc.smc_rulebook import GateMode, NoTradeReason, SmcRulebookConfig
from src.smc.weekly_daily import InteractionType, LiquidityInteractionResult


def _make_mtf_context(
    h4_bias: TrendBias = TrendBias.STRONG_BULLISH,
    h4_has_bos: bool = True,
    is_discount: bool = True,
    is_premium: bool = False,
    pd_ratio: float = 0.25,
    has_sweep_interaction: bool = True,
) -> MultiTimeframeContext:
    t0 = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)

    def _tf(tf: Timeframe, bias: TrendBias, bos: bool) -> TimeframeAnalysis:
        return TimeframeAnalysis(
            timeframe=tf,
            trend=bias,
            last_close=1.1000,
            swing_high=1.1060,
            swing_low=1.0980,
            is_premium=is_premium,
            is_discount=is_discount,
            pd_ratio=pd_ratio,
            fvg_count=1,
            ob_count=1,
            has_bos_in_trend=bos,
        )

    interactions: List[LiquidityInteractionResult] = []
    if has_sweep_interaction:
        interactions.append(
            LiquidityInteractionResult(
                interaction=InteractionType.PDL_SWEEP,
                level_name="PDL",
                level_price=1.0985,
                direction_bias=OrderType.BUY,
                sweep_distance_pips=5.0,
                confirmed=True,
                description="Bullish sweep & rejection of PDL",
            )
        )

    return MultiTimeframeContext(
        symbol="EURUSD",
        timestamp=t0,
        w1=_tf(Timeframe.W1, h4_bias, h4_has_bos),
        d1=_tf(Timeframe.D1, h4_bias, h4_has_bos),
        h4=_tf(Timeframe.H4, h4_bias, h4_has_bos),
        h1=_tf(Timeframe.H1, h4_bias, h4_has_bos),
        m15=_tf(Timeframe.M15, h4_bias, True),
        overall_bias=h4_bias,
        levels=WeeklyDailyLevels(
            symbol="EURUSD",
            pwh=1.1080,
            pwl=1.0950,
            pwo=1.0970,
            pwc=1.1040,
            pwm=1.1015,
            cwo=1.1040,
            cwh=1.1060,
            cwl=1.0980,
            pdh=1.1050,
            pdl=1.0985,
            pdo=1.0990,
            pdc=1.1020,
            pdm=1.10175,
            cdo=1.1020,
            cdh=1.1030,
            cdl=1.0980,
            timestamp=t0,
        ),
        level_interactions=interactions,
        alignment_score=90.0,
    )


def _make_candidate(
    direction: OrderType = OrderType.BUY,
    setup_type: SetupType = SetupType.DAILY_REVERSAL,
    entry: float = 1.1000,
    sl: float = 1.0978,
    tp: float = 1.1050,
    rr: float = 2.27,
    include_poi: bool = True,
    related_level: Optional[str] = "PDL_SWEEP",
) -> SignalCandidate:
    t0 = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)
    fvg = (
        FairValueGap(
            id="FVG_1",
            symbol="EURUSD",
            timeframe=Timeframe.M15,
            direction=direction,
            top=1.1005,
            bottom=1.0995,
            midpoint=1.1000,
            formation_time=t0,
        )
        if include_poi
        else None
    )
    ob = (
        OrderBlock(
            id="OB_1",
            symbol="EURUSD",
            timeframe=Timeframe.M15,
            direction=direction,
            high=1.1002,
            low=1.0990,
            open_price=1.1001,
            close_price=1.0991,
            formation_time=t0,
        )
        if include_poi
        else None
    )
    return SignalCandidate(
        id="TEST_SIG_001",
        symbol="EURUSD",
        timeframe=Timeframe.M15,
        direction=direction,
        setup_type=setup_type,
        entry_price=entry,
        stop_loss=sl,
        take_profit=tp,
        risk_reward=rr,
        score=85.0,
        timestamp=t0,
        status="APPROVED",
        reasons=[
            "W1/D1/H4 aligned bullish",
            "Price in H1 Discount Zone",
            "Bullish liquidity sweep of PDL at 1.0985",
            "M15 Bullish BOS confirmed by candle close",
            "Entry at unmitigated Bullish FVG + Bullish OB",
        ],
        fvg=fvg,
        ob=ob,
        related_level=related_level,
    )


class TestSetupQualityGateAndRisk(unittest.TestCase):
    def test_gate_passes_high_quality_r8_setup(self) -> None:
        cfg = SmcRulebookConfig(gate_mode=GateMode.ENFORCE)
        gate = SetupQualityGate(cfg)
        mtf = _make_mtf_context()
        cand = _make_candidate()
        verdict = gate.evaluate(cand, mtf=mtf, proposed_risk_pct=1.0, is_in_killzone=True)
        self.assertTrue(verdict.passed)
        self.assertFalse(verdict.blocked)
        self.assertEqual(len(verdict.hard_fails), 0)
        self.assertGreater(verdict.score, cand.score)  # Soft bonus from OB+FVG + Killzone

    def test_gate_g1_g2_g3_g4_g7_g8_individual_rejections(self) -> None:
        cfg = SmcRulebookConfig(gate_mode=GateMode.ENFORCE)
        gate = SetupQualityGate(cfg)

        # G1: Ranging HTF structure -> reject
        mtf_ranging = _make_mtf_context(h4_bias=TrendBias.RANGING, h4_has_bos=False)
        v1 = gate.evaluate(_make_candidate(), mtf=mtf_ranging, proposed_risk_pct=1.0)
        self.assertFalse(v1.passed)
        self.assertIn(NoTradeReason.UNCLEAR_STRUCTURE, v1.reason_codes)

        # G2: BUY in PREMIUM zone -> reject when G2 enabled, pass when G2 toggled off
        mtf_premium = _make_mtf_context(is_discount=False, is_premium=True, pd_ratio=0.75)
        v2 = gate.evaluate(_make_candidate(), mtf=mtf_premium, proposed_risk_pct=1.0)
        self.assertFalse(v2.passed)
        self.assertIn(NoTradeReason.WRONG_PD_ZONE, v2.reason_codes)

        cfg_no_g2 = SmcRulebookConfig(gate_mode=GateMode.ENFORCE, g2_zone_enabled=False)
        v2_ablation = SetupQualityGate(cfg_no_g2).evaluate(_make_candidate(), mtf=mtf_premium, proposed_risk_pct=1.0)
        self.assertNotIn(NoTradeReason.WRONG_PD_ZONE, v2_ablation.reason_codes)

        # G3: No sweep interaction and non-sweep setup -> reject
        mtf_no_sweep = _make_mtf_context(has_sweep_interaction=False)
        cand_no_sweep = _make_candidate(setup_type=SetupType.M15_SMC_OTE, related_level=None)
        v3 = gate.evaluate(cand_no_sweep, mtf=mtf_no_sweep, proposed_risk_pct=1.0)
        self.assertFalse(v3.passed)
        self.assertIn(NoTradeReason.NO_SWEEP, v3.reason_codes)

        # G4: Missing POI (no OB and no FVG) -> reject
        cand_no_poi = _make_candidate(include_poi=False)
        v4 = gate.evaluate(cand_no_poi, mtf=_make_mtf_context(), proposed_risk_pct=1.0)
        self.assertFalse(v4.passed)
        self.assertIn(NoTradeReason.WEAK_OR_MISSING_POI, v4.reason_codes)

        # G7: SL not beyond OB low (1.0995 > 1.0990 OB low) or RR < 2.0 -> reject
        cand_bad_sl = _make_candidate(sl=1.0995, rr=1.5)
        v7 = gate.evaluate(cand_bad_sl, mtf=_make_mtf_context(), proposed_risk_pct=1.0)
        self.assertFalse(v7.passed)
        self.assertIn(NoTradeReason.INVALID_SL_EXTREME, v7.reason_codes)
        self.assertIn(NoTradeReason.RR_TOO_LOW, v7.reason_codes)

        # G8: Risk > 2.0% or missing SL -> reject
        v8 = gate.evaluate(_make_candidate(), mtf=_make_mtf_context(), proposed_risk_pct=2.5)
        self.assertFalse(v8.passed)
        self.assertIn(NoTradeReason.RISK_ABOVE_CAP, v8.reason_codes)

    def test_gate_modes_off_shadow_enforce(self) -> None:
        mtf_ranging = _make_mtf_context(h4_bias=TrendBias.RANGING, h4_has_bos=False)
        cand = _make_candidate()

        # SHADOW mode evaluates and records failures but never blocks
        shadow_gate = SetupQualityGate(SmcRulebookConfig(gate_mode=GateMode.SHADOW))
        v_shadow = shadow_gate.evaluate(cand, mtf=mtf_ranging, proposed_risk_pct=1.0)
        self.assertFalse(v_shadow.passed)
        self.assertFalse(v_shadow.blocked)

        # OFF mode always passes and never blocks
        off_gate = SetupQualityGate(SmcRulebookConfig(gate_mode=GateMode.OFF))
        v_off = off_gate.evaluate(cand, mtf=mtf_ranging, proposed_risk_pct=1.0)
        self.assertTrue(v_off.passed)
        self.assertFalse(v_off.blocked)

        # ENFORCE mode blocks failing candidates
        enforce_gate = SetupQualityGate(SmcRulebookConfig(gate_mode=GateMode.ENFORCE))
        v_enforce = enforce_gate.evaluate(cand, mtf=mtf_ranging, proposed_risk_pct=1.0)
        self.assertFalse(v_enforce.passed)
        self.assertTrue(v_enforce.blocked)

    def test_r9_hard_risk_cap_and_missing_sl_rejection(self) -> None:
        # 1. AccountTierManager caps absolute_ceiling_pct at 2.0% even if JSON has 5.0%
        tier_mgr = AccountTierManager()
        for tier_name, spec in tier_mgr.tiers.items():
            if tier_name != AccountTier.BELOW_FLOOR.value:
                self.assertLessEqual(spec.absolute_ceiling_pct, AccountTierManager.HARD_MAX_RISK_PCT)
                self.assertLessEqual(spec.target_risk_pct, 1.0)

        # 2. PositionSizingEngine clamps default_risk_percent to <= 2.0% and rejects missing SL
        sizer = PositionSizingEngine(default_risk_percent=5.0)
        self.assertLessEqual(sizer.default_risk_percent, 2.0)

        acct = AccountInfo(balance=10000.0, equity=10000.0, free_margin=10000.0)
        sym = SymbolInfo(
            symbol="EURUSD",
            point=0.00001,
            digits=5,
            min_lot=0.01,
            max_lot=100.0,
            lot_step=0.01,
            contract_size=100000.0,
            tick_value=1.0,
            tick_size=0.00001,
            bid=1.1000,
            ask=1.1001,
            spread=10.0,
        )
        no_sl_res = sizer.calculate_lot_size(acct, sym, entry_price=1.1000, stop_loss=0.0, risk_percent=1.0)
        self.assertFalse(no_sl_res.is_approved)
        self.assertIn("R9", no_sl_res.rejection_reason)

        # Even if caller passes risk_percent=5.0, actual risk never exceeds 2.0%
        capped_res = sizer.calculate_lot_size(acct, sym, entry_price=1.1000, stop_loss=1.0980, risk_percent=5.0)
        self.assertTrue(capped_res.is_approved)
        self.assertLessEqual(capped_res.risk_percent_actual, 2.0)

        # 3. BridgeClient rejects execute_trade with stop_loss <= 0
        bridge = BridgeClient()
        res = bridge.execute_trade(symbol="EURUSD", order_type=OrderType.BUY, volume=0.1, stop_loss=0.0, take_profit=1.1100)
        self.assertEqual(res.get("status"), "ERROR")
        self.assertIn("R9.2", res.get("message", ""))

    def test_r9_never_widen_stop_loss_guard(self) -> None:
        # 1. OrderManager.validate_sl_modification
        ok_be, _ = OrderManager.validate_sl_modification(OrderType.BUY, current_sl=1.0980, new_sl=1.1000)
        self.assertTrue(ok_be)

        bad_widen_buy, msg_buy = OrderManager.validate_sl_modification(OrderType.BUY, current_sl=1.0980, new_sl=1.0970)
        self.assertFalse(bad_widen_buy)
        self.assertIn("R9.3", msg_buy)

        bad_widen_sell, msg_sell = OrderManager.validate_sl_modification(OrderType.SELL, current_sl=1.1020, new_sl=1.1035)
        self.assertFalse(bad_widen_sell)
        self.assertIn("R9.3", msg_sell)

        ok_trail_sell, _ = OrderManager.validate_sl_modification(OrderType.SELL, current_sl=1.1020, new_sl=1.1005)
        self.assertTrue(ok_trail_sell)

        # 2. OrderManager.apply_plan_amendment rejects widening amendment
        cfg = AppConfig.load_from_dir()
        cfg.execution_mode = ExecutionMode.SIMULATION
        om = OrderManager(cfg, BridgeClient(), PositionSizingEngine(1.0), PortfolioRiskEngine(cfg.risk))
        plan = TradePlan(
            plan_id="PLAN_1",
            symbol="EURUSD",
            direction=OrderType.BUY,
            entry_price=1.1000,
            stop_loss=1.0980,
            take_profit=1.1050,
            lots=0.10,
            risk_percent=1.0,
            reward_to_risk=2.5,
            structure_state="BOS_CONFIRMED",
            timestamp=datetime.now(timezone.utc),
        )
        om._active_trade_plans[101] = plan

        widen_amendment = PlanAmendment(
            amendment_type="MANUAL_WIDEN",
            old_sl=1.0980,
            new_sl=1.0965,
            old_tp=1.1050,
            new_tp=1.1050,
            reason="Attempted stop widening",
            timestamp=datetime.now(timezone.utc),
        )
        self.assertIsNone(om.apply_plan_amendment(101, widen_amendment))
        self.assertAlmostEqual(om.get_trade_plan(101).stop_loss, 1.0980)

        tighten_amendment = PlanAmendment(
            amendment_type="BREAKEVEN",
            old_sl=1.0980,
            new_sl=1.1001,
            old_tp=1.1050,
            new_tp=1.1050,
            reason="Lock breakeven",
            timestamp=datetime.now(timezone.utc),
        )
        updated = om.apply_plan_amendment(101, tighten_amendment)
        self.assertIsNotNone(updated)
        self.assertAlmostEqual(updated.stop_loss, 1.1001)

        # 3. BrokerConstraintValidator.validate_modification_constraints rejects SL widening
        ok_mod, mod_msg = BrokerConstraintValidator.validate_modification_constraints(
            direction=OrderType.BUY,
            current_price=1.1005,
            current_sl=1.0980,
            current_tp=1.1050,
            new_sl=1.0970,
            new_tp=1.1050,
            symbol_info=SymbolInfo(symbol="EURUSD", point=0.00001),
        )
        self.assertFalse(ok_mod)
        self.assertIn("R9", mod_msg)


if __name__ == "__main__":
    unittest.main()
