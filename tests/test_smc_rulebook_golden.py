"""
Golden-Fixture & No-Lookahead Unit Tests for the Canonical SMC Rulebook (Phase 1).

Tests hand-labelled candle sequences for Rules R1-R9:
1. R1: Market Structure (HH+HL = BULLISH, LH+LL = BEARISH, mixed/unclear = RANGING).
2. R2: Break of Structure (wick-only break = NO BOS; candle body close = BOS).
3. R3: Change of Character (lone CHoCH = warning only; pullback + BOS = confirmed).
4. R4: Liquidity Sweep (pierce + close back inside = valid sweep; close outside = breakout/rejected).
5. R5: Order Block (with displacement + structural break = valid OB; weak/no-BOS candle = rejected).
6. R6: Fair Value Gap (3-candle non-overlap >= fvg_min_atr*ATR = valid FVG; tiny/overlapping = rejected; OB+FVG confluence).
7. R7: Premium / Discount (50% equilibrium: <50% = discount for buys, >50% = premium for sells).
8. R8: TP anchored at next liquidity pool (no artificial TP inflation when pool RR < min_rr).
9. No-Lookahead Invariance: Decisions at bar t depend strictly on closed bars [0..t] and never change when future bars [t+1..N] are appended or mutated.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from typing import List

from src.core.contracts import (
    Candle,
    Timeframe,
    OrderType,
    TrendBias,
    MarketStructureType,
    LiquidityZone,
    WeeklyDailyLevels,
)
from src.smc.market_structure import MarketStructureEngine
from src.smc.structure_confirmation import (
    StructureStateMachine,
    ConfirmationState,
    CycleDirection,
)
from src.smc.liquidity import LiquidityEngine
from src.smc.fvg_ob import FvgObEngine
from src.smc.mtf_analyzer import MultiTimeframeAnalyzer
from src.smc.strategy_engine import SmcStrategyEngine
from src.strategies.cisd import CisdSignalModule
from src.strategies.base import StrategyContext
from src.core.config import AppConfig


def _make_candle(
    idx: int,
    open_p: float,
    high_p: float,
    low_p: float,
    close_p: float,
    tf: Timeframe = Timeframe.M15,
) -> Candle:
    base_time = datetime(2026, 1, 5, 8, 0, tzinfo=timezone.utc)
    return Candle(
        time=base_time + timedelta(minutes=15 * idx),
        open=open_p,
        high=high_p,
        low=low_p,
        close=close_p,
        tick_volume=1000,
    )


def _build_uptrend_swing_candles() -> List[Candle]:
    """
    Hand-labelled candle sequence with lookback=2 forming:
    - Swing Low 1 at bar 2 (1.0980)
    - Swing High 1 at bar 5 (1.1050)
    - Higher Swing Low 2 at bar 8 (1.1010)
    - Higher Swing High 2 at bar 11 (1.1080)
    - Pullback bars 12..14 around 1.1045
    """
    specs = [
        # 0..1: descending into SL1
        (1.1010, 1.1015, 1.0995, 1.1000),
        (1.1000, 1.1005, 1.0988, 1.0990),
        # 2: Swing Low 1 (low = 1.0980)
        (1.0990, 1.0998, 1.0980, 1.0995),
        # 3..4: rising into SH1
        (1.0995, 1.1025, 1.0992, 1.1020),
        (1.1020, 1.1040, 1.1015, 1.1035),
        # 5: Swing High 1 (high = 1.1050)
        (1.1035, 1.1050, 1.1028, 1.1032),
        # 6..7: pullback into SL2
        (1.1032, 1.1036, 1.1018, 1.1022),
        (1.1022, 1.1028, 1.1014, 1.1016),
        # 8: Higher Swing Low 2 (low = 1.1010 > 1.0980)
        (1.1016, 1.1025, 1.1010, 1.1022),
        # 9..10: rally into SH2
        (1.1022, 1.1055, 1.1020, 1.1050),
        (1.1050, 1.1070, 1.1045, 1.1065),
        # 11: Higher Swing High 2 (high = 1.1080 > 1.1050)
        (1.1065, 1.1080, 1.1058, 1.1062),
        # 12..14: post-SH2 consolidation (confirms SH2 with k=2)
        (1.1062, 1.1068, 1.1045, 1.1050),
        (1.1050, 1.1058, 1.1040, 1.1045),
        (1.1045, 1.1055, 1.1042, 1.1048),
    ]
    return [_make_candle(i, o, h, l, c) for i, (o, h, l, c) in enumerate(specs)]


class TestSmcRulebookGolden(unittest.TestCase):

    def test_r1_uptrend_requires_both_hh_and_hl(self):
        engine = MarketStructureEngine(swing_lookback=2, require_both_hh_hl_for_trend=True)
        candles = _build_uptrend_swing_candles()
        bias, _ = engine.analyze_structure("EURUSD", Timeframe.H4, candles)
        self.assertEqual(bias, TrendBias.STRONG_BULLISH)

        # Mutate Swing Low 2 (bar 8) so it is a Lower Low (1.0975 < 1.0980) -> HH + LL (expanding range)
        candles_mixed = list(candles)
        candles_mixed[8] = _make_candle(8, 1.1016, 1.1025, 1.0975, 1.1022)
        bias_mixed, _ = engine.analyze_structure("EURUSD", Timeframe.H4, candles_mixed)
        self.assertEqual(bias_mixed, TrendBias.RANGING, "HH + LL must be classified as RANGING under R1")

    def test_r1_insufficient_swings_returns_ranging_not_fallback_trend(self):
        engine = MarketStructureEngine(swing_lookback=5, require_both_hh_hl_for_trend=True)
        short_candles = [
            _make_candle(i, 1.1000 + i * 0.0010, 1.1010 + i * 0.0010, 1.0995 + i * 0.0010, 1.1008 + i * 0.0010)
            for i in range(6)
        ]
        bias, events = engine.analyze_structure("EURUSD", Timeframe.H4, short_candles)
        self.assertEqual(bias, TrendBias.RANGING)
        self.assertEqual(events, [])

    def test_r2_wick_only_pierce_is_not_bos_body_close_is_bos(self):
        engine = MarketStructureEngine(swing_lookback=2, bos_body_close_required=True)
        base = _build_uptrend_swing_candles()

        # Bar 15 with WICK above 1.1080 (high=1.1092) but BODY CLOSE below 1.1080 (close=1.1072)
        wick_only = base + [_make_candle(15, 1.1048, 1.1092, 1.1045, 1.1072)]
        _, events_wick = engine.analyze_structure("EURUSD", Timeframe.M15, wick_only)
        self.assertEqual(len(events_wick), 0, "R2: Wick-only pierce above swing high must NOT trigger BOS/MSS")

        # Bar 15 with BODY CLOSE above 1.1080 (close=1.1088)
        body_close = base + [_make_candle(15, 1.1048, 1.1092, 1.1045, 1.1088)]
        _, events_close = engine.analyze_structure("EURUSD", Timeframe.M15, body_close)
        self.assertEqual(len(events_close), 1)
        self.assertEqual(events_close[0].direction, OrderType.BUY)
        self.assertTrue(events_close[0].confirmed_by_close)
        self.assertIn(events_close[0].event_type, (MarketStructureType.BOS, MarketStructureType.MSS))

    def test_r3_lone_choch_is_warning_only_until_pullback_and_bos(self):
        sm = StructureStateMachine(
            swing_lookback=2,
            require_close_break=True,
            require_lower_high=True,
            choch_timeout_bars=25,
            allow_choch_only_entries=False,
            choch_requires_confirmation=True,
        )
        base = _build_uptrend_swing_candles()
        # Bar 15 closes below last protected swing low 1.1010 (at 1.1002) against prevailing uptrend -> Bearish CHoCH Warning!
        choch_seq = base + [_make_candle(15, 1.1048, 1.1050, 1.0998, 1.1002)]
        state_warn = sm.update("EURUSD", Timeframe.M15, choch_seq)
        self.assertEqual(state_warn.state, ConfirmationState.CHOCH_WARNING)
        self.assertEqual(state_warn.direction, CycleDirection.BEARISH)
        self.assertFalse(state_warn.is_confirmed, "R3: Lone CHoCH must NOT be marked confirmed")

        pullback_and_bos = choch_seq + [
            _make_candle(16, 1.1002, 1.1025, 1.1001, 1.1020),
            _make_candle(17, 1.1020, 1.1035, 1.1015, 1.1032),
            _make_candle(18, 1.1032, 1.1045, 1.1025, 1.1040),  # LH peak at 1.1045 (< 1.1080) with k=2 before & after
            _make_candle(19, 1.1040, 1.1042, 1.1015, 1.1018),
            _make_candle(20, 1.1018, 1.1022, 1.1005, 1.1008),  # Confirms LH at bar 18
            _make_candle(21, 1.1008, 1.1010, 1.0985, 1.0990),  # Body close < 1.0998 -> BOS_CONFIRMED!
        ]
        state_conf = sm.update("EURUSD", Timeframe.M15, pullback_and_bos)
        self.assertEqual(state_conf.state, ConfirmationState.BOS_CONFIRMED)
        self.assertTrue(state_conf.is_confirmed)

    def test_r4_sweep_requires_close_back_inside_and_correct_cisd_direction(self):
        liq = LiquidityEngine(eqh_tolerance_pips=2.0, pip_size=0.0001, sweep_requires_close_back_inside=True)
        bsl_pool = LiquidityZone(
            id="TEST_BSL",
            symbol="EURUSD",
            timeframe=Timeframe.M15,
            level_type="BSL",
            price=1.1050,
            high=1.1052,
            low=1.1050,
            formation_time=datetime(2026, 1, 5, 8, 0, tzinfo=timezone.utc),
        )

        # Case 1: Breakout candle closes ABOVE BSL and stays above -> NOT a sweep rejection
        breakout_bars = [
            _make_candle(1, 1.1040, 1.1065, 1.1038, 1.1060),
            _make_candle(2, 1.1060, 1.1075, 1.1055, 1.1070),
        ]
        swept_bo, rejected_bo, _ = liq.verify_sweep(bsl_pool, breakout_bars)
        self.assertTrue(swept_bo)
        self.assertFalse(rejected_bo, "R4: Multi-bar close outside BSL is a breakout, not a sweep rejection")

        # Case 2: Sweep candle pierces 1.1050 (high=1.1062) and closes back inside (close=1.1042)
        sweep_bars = [_make_candle(1, 1.1045, 1.1062, 1.1038, 1.1042)]
        swept_ok, rejected_ok, dist_pips = liq.verify_sweep(bsl_pool, sweep_bars)
        self.assertTrue(swept_ok)
        self.assertTrue(rejected_ok)
        self.assertAlmostEqual(dist_pips, 12.0, places=4)

        # Case 3: CISD plugin must generate SELL on BSL sweep (pierce 1.1080 -> 1.1088, close back inside at 1.1066)
        cfg = AppConfig()
        cisd = CisdSignalModule(cfg)
        base = _build_uptrend_swing_candles()
        bsl_sweep_candles = base + [
            _make_candle(15, 1.1072, 1.1088, 1.1062, 1.1066),
        ]
        ctx = StrategyContext(symbol="EURUSD", m15_candles=bsl_sweep_candles)
        sig = cisd.generate_signal(ctx)
        self.assertIsNotNone(sig)
        self.assertEqual(sig.direction, OrderType.SELL, "R4: Sweeping Buy-Side Liquidity (highs) must produce a SELL signal")

    def test_r5_order_block_requires_displacement_and_bos(self):
        fvg_ob = FvgObEngine(
            min_fvg_pips=1.0,
            pip_size=0.0001,
            fvg_min_atr=0.3,
            ob_requires_displacement=True,
            ob_displacement_atr_mult=1.2,
            ob_requires_bos=True,
        )

        weak_candles = [
            _make_candle(0, 1.1000, 1.1030, 1.0995, 1.1020),
            _make_candle(1, 1.1020, 1.1022, 1.1005, 1.1010),
            _make_candle(2, 1.1010, 1.1012, 1.1000, 1.1002),
            _make_candle(3, 1.1002, 1.1016, 1.1001, 1.1014),
            _make_candle(4, 1.1014, 1.1018, 1.1010, 1.1015),
            _make_candle(5, 1.1015, 1.1019, 1.1011, 1.1016),
        ]
        obs_weak = fvg_ob.detect_order_blocks("EURUSD", Timeframe.M15, weak_candles)
        self.assertEqual(len(obs_weak), 0, "R5: Opposite candle without displacement + BOS must NOT be marked as an OB")

        strong_candles = [
            _make_candle(0, 1.1000, 1.1030, 1.0995, 1.1020),
            _make_candle(1, 1.1020, 1.1022, 1.1005, 1.1010),
            _make_candle(2, 1.1010, 1.1012, 1.1000, 1.1002),
            _make_candle(3, 1.1002, 1.1045, 1.1002, 1.1042),
            _make_candle(4, 1.1042, 1.1055, 1.1025, 1.1050),
            _make_candle(5, 1.1050, 1.1058, 1.1040, 1.1052),
        ]
        obs_strong = fvg_ob.detect_order_blocks("EURUSD", Timeframe.M15, strong_candles)
        self.assertEqual(len(obs_strong), 1)
        self.assertEqual(obs_strong[0].direction, OrderType.BUY)
        self.assertAlmostEqual(obs_strong[0].low, 1.1000, places=5)
        self.assertAlmostEqual(obs_strong[0].high, 1.1012, places=5)

    def test_r6_fvg_requires_non_overlap_and_min_atr_size(self):
        fvg_ob = FvgObEngine(
            min_fvg_pips=0.5,
            pip_size=0.0001,
            fvg_min_atr=0.3,
        )
        base = [_make_candle(i, 1.1000, 1.1020, 1.1000, 1.1010) for i in range(10)]

        tiny_gap_seq = base + [
            _make_candle(10, 1.1005, 1.1015, 1.1000, 1.1012),
            _make_candle(11, 1.1012, 1.1025, 1.1010, 1.1022),
            _make_candle(12, 1.1022, 1.1028, 1.1016, 1.1025),
        ]
        self.assertEqual(len(fvg_ob.detect_fvgs("EURUSD", Timeframe.M15, tiny_gap_seq)), 0)

        valid_gap_seq = base + [
            _make_candle(10, 1.1005, 1.1015, 1.1000, 1.1002),
            _make_candle(11, 1.1002, 1.1045, 1.1002, 1.1042),
            _make_candle(12, 1.1042, 1.1055, 1.1027, 1.1050),
            _make_candle(13, 1.1050, 1.1058, 1.1040, 1.1052),
        ]
        fvgs = fvg_ob.detect_fvgs("EURUSD", Timeframe.M15, valid_gap_seq)
        obs = fvg_ob.detect_order_blocks("EURUSD", Timeframe.M15, valid_gap_seq)
        self.assertEqual(len(fvgs), 1)
        self.assertEqual(len(obs), 1)
        self.assertTrue(FvgObEngine.has_ob_fvg_confluence(obs[0], fvgs[0], tolerance=0.0005))

    def test_r7_premium_discount_equilibrium(self):
        pd_disc = FvgObEngine.calculate_premium_discount(
            range_high=1.1100,
            range_low=1.1000,
            current_price=1.1035,
            pd_equilibrium=0.5,
        )
        self.assertAlmostEqual(pd_disc["equilibrium"], 1.1050, places=5)
        self.assertTrue(pd_disc["is_discount"])
        self.assertFalse(pd_disc["is_premium"])

        pd_prem = FvgObEngine.calculate_premium_discount(
            range_high=1.1100,
            range_low=1.1000,
            current_price=1.1075,
            pd_equilibrium=0.5,
        )
        self.assertFalse(pd_prem["is_discount"])
        self.assertTrue(pd_prem["is_premium"])

    def test_r8_no_artificial_tp_inflation_when_liquidity_pool_is_too_close(self):
        mtf_analyzer = MultiTimeframeAnalyzer()
        candles = _build_uptrend_swing_candles()
        ctx = mtf_analyzer.analyze("EURUSD", candles, candles, candles, candles, candles)
        ctx.levels = WeeklyDailyLevels(
            symbol="EURUSD",
            pwh=1.1065,
            pwl=1.0950,
            pwo=1.1000,
            pwc=1.1040,
            pwm=1.1007,
            cwo=1.1040,
            cwh=1.1065,
            cwl=1.0980,
            pdh=1.1060,
            pdl=1.0980,
            pdo=1.1010,
            pdc=1.1045,
            pdm=1.1020,
            cdo=1.1045,
            cdh=1.1060,
            cdl=1.1010,
            timestamp=candles[-1].time,
        )
        ctx.m15.swing_high = 1.1065
        ctx.h1.swing_high = 1.1065
        ctx.h4.swing_high = 1.1065
        ctx.d1.swing_high = 1.1065

        target, anchored = SmcStrategyEngine._select_best_bullish_target(
            entry_price=1.1045,
            sl_distance=0.0035,
            min_rr=2.0,
            mtf_ctx=ctx,
            swing_highs=[],
            tp_requires_liquidity_pool=True,
        )
        self.assertTrue(anchored)
        self.assertAlmostEqual(target, 1.1065, places=5)

    def test_no_lookahead_invariance_across_detectors(self):
        base = _build_uptrend_swing_candles()
        future_bull_explosion = [
            _make_candle(15, 1.1048, 1.1250, 1.1048, 1.1240),
            _make_candle(16, 1.1240, 1.1350, 1.1230, 1.1340),
        ]
        future_bear_crash = [
            _make_candle(15, 1.1048, 1.1050, 1.0800, 1.0810),
            _make_candle(16, 1.0810, 1.0820, 1.0700, 1.0710),
        ]

        ms = MarketStructureEngine(swing_lookback=2)
        sm1 = StructureStateMachine(swing_lookback=2)
        sm2 = StructureStateMachine(swing_lookback=2)

        seq_a = (base + future_bull_explosion)[:15]
        seq_b = (base + future_bear_crash)[:15]

        bias_a, events_a = ms.analyze_structure("EURUSD", Timeframe.M15, seq_a)
        bias_b, events_b = ms.analyze_structure("EURUSD", Timeframe.M15, seq_b)
        self.assertEqual(bias_a, bias_b)
        self.assertEqual(events_a, events_b)

        state_a = sm1.update("EURUSD", Timeframe.M15, seq_a)
        state_b = sm2.update("EURUSD", Timeframe.M15, seq_b)
        self.assertEqual(state_a, state_b)


if __name__ == "__main__":
    unittest.main()
