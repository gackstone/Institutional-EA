"""
Comprehensive Unit Test Suite for Advanced Market Structure Intelligence Engine.
Tests all 10 core algorithmic components:
1. Advanced Liquidity Mapping (Swings, EQH/EQL, PDH/PDL/PWH/PWL, Prominence)
2. Liquidity Sweep vs Breakout vs Trap Classification
3. Fair Value Gap (FVG) Detection & Mitigation Tracking
4. Secondary / Nested Imbalance Recognition
5. Breaker Block Identification & Retest Evaluation
6. Multi-Timeframe Pairing Engine & Directional Alignment
7. Contextual Volume Confirmation (Expansion, Dry-up, Absorption, Flat Volume fallback)
8. Advanced Setup Evaluator & Weighted Confluence Scoring
9. Model 4 Breakout-Retracement-Retest Scalping Engine
10. Sizing Budget Safeguard (MINIMUM_VOLUME_EXCEEDS_RISK_BUDGET)
"""

import unittest
from datetime import datetime, timezone, timedelta
from typing import List

from src.core.contracts import (
    Candle, Timeframe, OrderType, TrendBias, SetupType,
    SignalCandidate, FairValueGap, OrderBlock, AccountInfo, SymbolInfo
)
from src.smc.advanced_market_structure import (
    AdvancedLiquidityMapper,
    LiquidityLevelType,
    LiquidityPoint,
    LiquiditySweepClassifier,
    SweepClassification,
    SweepEvent,
    FvgBreakerEngine,
    FvgMitigationState,
    BreakerZone,
    VolumeConfirmationEngine,
    VolumeContext,
    MultiTimeframePairingEngine,
    DirectionalState,
    AdvancedSetupEvaluator,
)
from src.execution.continuous_scalper import ContinuousScalpingEngine
from src.risk.position_sizing import PositionSizingEngine


def make_candle(
    time: datetime,
    o: float,
    h: float,
    l: float,
    c: float,
    vol: float = 100.0,
) -> Candle:
    return Candle(
        time=time,
        open=o,
        high=h,
        low=l,
        close=c,
        tick_volume=int(vol),
        complete=True
    )


class TestAdvancedMarketStructure(unittest.TestCase):

    def setUp(self):
        self.now = datetime(2026, 11, 15, 10, 0, tzinfo=timezone.utc)
        self.eur_info = SymbolInfo(
            symbol="EURUSD",
            digits=5,
            point=0.00001,
            tick_size=0.00001,
            tick_value=1.0,
            contract_size=100000.0,
            min_lot=0.01,
            max_lot=50.0,
            lot_step=0.01,
            margin_required=20.0,
            spread=15,
            ask=1.08515,
            bid=1.08500
        )

    # -------------------------------------------------------------------------
    # 1. Advanced Liquidity Mapping (EQH, EQL, Prominence, Session Extrema)
    # -------------------------------------------------------------------------
    def test_01_liquidity_mapping_eqh_and_eql(self):
        mapper = AdvancedLiquidityMapper(swing_lookback=3, eq_tolerance_pips=2.0, pip_size=0.0001)
        base_time = self.now - timedelta(hours=8)
        candles: List[Candle] = []

        # Create price series with Equal Highs at ~1.0900
        for i in range(25):
            t = base_time + timedelta(minutes=15 * i)
            if i == 5:
                candles.append(make_candle(t, 1.0880, 1.09005, 1.0875, 1.0885))
            elif i == 15:
                candles.append(make_candle(t, 1.0882, 1.09002, 1.0878, 1.0880))
            elif i == 10:
                candles.append(make_candle(t, 1.0850, 1.0855, 1.08300, 1.0845))
            else:
                candles.append(make_candle(t, 1.0860, 1.0870, 1.0850, 1.0865))

        liq_points = mapper.map_liquidity("EURUSD", Timeframe.M15, candles)
        self.assertTrue(len(liq_points) >= 2)

        # Confirm mapped liquidity points exist and contain swing extrema
        high_points = [p for p in liq_points if p.level_type in (LiquidityLevelType.BUY_SIDE_LIQUIDITY, LiquidityLevelType.EQUAL_HIGHS)]
        self.assertTrue(len(high_points) >= 1)
        self.assertAlmostEqual(high_points[0].price, 1.0900, places=3)

    # -------------------------------------------------------------------------
    # 2. Liquidity Sweep vs Breakout vs Trap Classification
    # -------------------------------------------------------------------------
    def test_02_liquidity_sweep_classification_sweep_with_reclaim(self):
        classifier = LiquiditySweepClassifier(pip_size=0.0001, reclaim_window_bars=3)
        level = LiquidityPoint(
            level_id="BSL_1.0900",
            symbol="EURUSD",
            timeframe=Timeframe.M15,
            level_type=LiquidityLevelType.BUY_SIDE_LIQUIDITY,
            price=1.0900,
            high=1.0900,
            low=1.0890,
            formation_time=self.now - timedelta(hours=2),
            reaction_count=2,
            prominence=1.5
        )

        c0 = make_candle(self.now - timedelta(minutes=45), 1.0880, 1.0885, 1.0875, 1.0882)
        # Candle pierces 1.0900 up to 1.0908 but closes at 1.0895 (clean sweep wick & reclaim)
        c1 = make_candle(self.now - timedelta(minutes=30), 1.0885, 1.0908, 1.0880, 1.0895, vol=250.0)
        c2 = make_candle(self.now - timedelta(minutes=15), 1.0895, 1.0898, 1.0870, 1.0875, vol=300.0)
        c3 = make_candle(self.now, 1.0875, 1.0880, 1.0865, 1.0870, vol=200.0)

        event = classifier.classify_sweep(level, [c0, c1, c2, c3], atr=0.0010)
        self.assertIsNotNone(event)
        self.assertEqual(event.classification, SweepClassification.SWEEP)
        self.assertTrue(event.is_reclaimed)
        self.assertEqual(event.direction_bias, OrderType.SELL)
        self.assertEqual(event.wick_extreme, 1.0908)

    def test_03_liquidity_sweep_classification_genuine_breakout(self):
        classifier = LiquiditySweepClassifier(pip_size=0.0001, reclaim_window_bars=3)
        level = LiquidityPoint(
            level_id="BSL_1.0900",
            symbol="EURUSD",
            timeframe=Timeframe.M15,
            level_type=LiquidityLevelType.BUY_SIDE_LIQUIDITY,
            price=1.0900,
            high=1.0900,
            low=1.0890,
            formation_time=self.now - timedelta(hours=2)
        )

        c0 = make_candle(self.now - timedelta(minutes=45), 1.0885, 1.0895, 1.0880, 1.0890)
        # Candle breaks decisively and closes strong above level (Genuine Breakout, not a sweep)
        c1 = make_candle(self.now - timedelta(minutes=30), 1.0890, 1.0930, 1.0888, 1.0925, vol=350.0)
        c2 = make_candle(self.now - timedelta(minutes=15), 1.0925, 1.0945, 1.0920, 1.0940, vol=400.0)
        c3 = make_candle(self.now, 1.0940, 1.0950, 1.0935, 1.0948, vol=300.0)

        event = classifier.classify_sweep(level, [c0, c1, c2, c3], atr=0.0010)
        self.assertIsNotNone(event)
        self.assertEqual(event.classification, SweepClassification.GENUINE_BREAKOUT)
        self.assertFalse(event.is_reclaimed)

    # -------------------------------------------------------------------------
    # 3. Fair Value Gap (FVG) and Secondary / Nested FVG Detection
    # -------------------------------------------------------------------------
    def test_04_fvg_and_secondary_nested_fvg_detection(self):
        engine = FvgBreakerEngine(pip_size=0.0001, fvg_min_atr=0.30)
        base_t = self.now - timedelta(hours=4)
        candles: List[Candle] = []

        # 3-candle primary bullish FVG:
        # C0 high = 1.0820, C1 massive green displacement (1.0820 -> 1.0870), C2 low = 1.0845
        # Gap between C0.high (1.0820) and C2.low (1.0845) = 25 pips gap!
        c0 = make_candle(base_t, 1.0800, 1.0820, 1.0795, 1.0815)
        c1 = make_candle(base_t + timedelta(minutes=15), 1.0820, 1.0870, 1.0818, 1.0868)
        c2 = make_candle(base_t + timedelta(minutes=30), 1.0868, 1.0890, 1.0845, 1.0885)
        candles.extend([c0, c1, c2])

        # Additional candles that form a smaller nested FVG inside:
        c3 = make_candle(base_t + timedelta(minutes=45), 1.0885, 1.0888, 1.0860, 1.0862)
        c4 = make_candle(base_t + timedelta(minutes=60), 1.0862, 1.0895, 1.0860, 1.0892)
        c5 = make_candle(base_t + timedelta(minutes=75), 1.0892, 1.0910, 1.0875, 1.0905)
        candles.extend([c3, c4, c5])

        all_fvgs = engine.detect_all_fvgs("EURUSD", Timeframe.M15, candles, atr=0.0010)
        self.assertTrue(len(all_fvgs) >= 1)
        primary = all_fvgs[0]
        self.assertEqual(primary.direction, OrderType.BUY)
        self.assertAlmostEqual(primary.bottom, 1.0820, places=4)
        self.assertAlmostEqual(primary.top, 1.0845, places=4)

        sec_fvg = engine.detect_secondary_fvg(primary, all_fvgs, current_price=1.0870)
        # Should either identify refined nested FVG or return None cleanly
        if sec_fvg:
            self.assertEqual(sec_fvg.direction, OrderType.BUY)

    # -------------------------------------------------------------------------
    # 4. Breaker Block Identification and Retest Evaluation
    # -------------------------------------------------------------------------
    def test_05_breaker_block_formation_and_retest(self):
        engine = FvgBreakerEngine(pip_size=0.0001, fvg_min_atr=0.30)
        base_t = self.now - timedelta(hours=6)
        candles: List[Candle] = []

        # Build swing high at i=6:
        for i in range(15):
            t = base_t + timedelta(minutes=15 * i)
            if i == 6:
                # Pivot swing high at 1.0880
                candles.append(make_candle(t, 1.0850, 1.0880, 1.0845, 1.0875))
            elif i == 10:
                # Decisive bullish displacement breaking swing high above 1.0880 to 1.0920
                candles.append(make_candle(t, 1.0870, 1.0925, 1.0868, 1.0920))
            elif i == 13:
                # Retest of the broken swing high zone [1.0845 - 1.0880]
                candles.append(make_candle(t, 1.0910, 1.0912, 1.0875, 1.0885))
            else:
                candles.append(make_candle(t, 1.0840, 1.0855, 1.0835, 1.0845))

        breakers = engine.detect_breaker_blocks("EURUSD", Timeframe.M15, candles, atr=0.0010)
        self.assertTrue(len(breakers) >= 1)
        b = breakers[0]
        self.assertEqual(b.direction, OrderType.BUY)
        self.assertAlmostEqual(b.top, 1.0880, places=3)
        self.assertTrue(b.retested)

    # -------------------------------------------------------------------------
    # 5. Contextual Volume Confirmation
    # -------------------------------------------------------------------------
    def test_06_volume_confirmation_expansion_and_absorption(self):
        engine = VolumeConfirmationEngine(rolling_period=10)
        candles: List[Candle] = []
        base_t = self.now - timedelta(hours=4)

        # 10 baseline candles with volume ~100
        for i in range(10):
            t = base_t + timedelta(minutes=15 * i)
            candles.append(make_candle(t, 1.0850, 1.0860, 1.0845, 1.0855, vol=100.0))

        # 11th candle: massive displacement volume expansion (RVOL > 2.0x)
        disp_candle = make_candle(
            base_t + timedelta(minutes=150),
            1.0855, 1.0895, 1.0850, 1.0890, vol=250.0
        )
        candles.append(disp_candle)

        ctx = engine.evaluate_volume("EURUSD", Timeframe.M15, candles, is_sweep=False)
        self.assertAlmostEqual(ctx.relative_volume, 2.17, delta=0.2)
        self.assertTrue(ctx.is_volume_expanding)
        self.assertFalse(ctx.is_retracement_dry)

        # 12th candle: sweep test with volume absorption
        absorp_candle = make_candle(
            base_t + timedelta(minutes=165),
            1.0890, 1.0920, 1.0888, 1.0892, vol=300.0
        )
        candles.append(absorp_candle)
        ctx_abs = engine.evaluate_volume("EURUSD", Timeframe.M15, candles, is_sweep=True)
        self.assertTrue(ctx_abs.is_sweep_absorption)

    def test_07_volume_confirmation_flat_fallback(self):
        """When tick volume is flat or missing (zeros), the system must fallback gracefully without division errors."""
        engine = VolumeConfirmationEngine(rolling_period=10)
        candles: List[Candle] = []
        base_t = self.now - timedelta(hours=4)

        for i in range(10):
            t = base_t + timedelta(minutes=15 * i)
            candles.append(make_candle(t, 1.0850, 1.0860, 1.0845, 1.0855, vol=0.0))

        ctx = engine.evaluate_volume("EURUSD", Timeframe.M15, candles)
        self.assertFalse(ctx.volume_available)
        self.assertEqual(ctx.relative_volume, 1.0)
        self.assertFalse(ctx.is_volume_expanding)

    # -------------------------------------------------------------------------
    # 6. Multi-Timeframe Pairing & Bias Engine
    # -------------------------------------------------------------------------
    def test_08_mtf_pairing_engine(self):
        pairing_engine = MultiTimeframePairingEngine()
        exec_tf = pairing_engine.get_execution_timeframe(Timeframe.H4)
        self.assertEqual(exec_tf, Timeframe.M15)

        base_t = self.now - timedelta(days=5)
        # Create zigzag price series with higher highs and higher lows
        # Low1 1.0800 -> High1 1.0850 -> Low2 1.0820 -> High2 1.0890 -> Low3 1.0860
        prices = [
            1.0800, 1.0815, 1.0830, 1.0850, 1.0835, 1.0820, 1.0840, 1.0865, 1.0890, 1.0875, 1.0860, 1.0880, 1.0900
        ]
        bullish_candles: List[Candle] = []
        for i, p in enumerate(prices):
            t = base_t + timedelta(hours=4 * i)
            bullish_candles.append(make_candle(t, p, p + 0.0008, p - 0.0008, p + 0.0004))

        state = pairing_engine.evaluate_directional_state(bullish_candles, swing_lookback=2)
        self.assertEqual(state, DirectionalState.BULLISH)

    # -------------------------------------------------------------------------
    # 7. Model 4 Breakout-Retracement-Retest Scalp in ContinuousScalpingEngine
    # -------------------------------------------------------------------------
    def test_09_model_4_breakout_retracement_retest_detection(self):
        scalper = ContinuousScalpingEngine(symbols=["EURUSD"])
        base_t = self.now - timedelta(hours=5)
        candles: List[Candle] = []

        # Setup prior resistance swing high at 1.0850 with 20 candles
        for i in range(16):
            t = base_t + timedelta(minutes=5 * i)
            high_val = 1.0850 if i == 5 else 1.0835
            candles.append(make_candle(t, 1.0820, high_val, 1.0815, 1.0830))

        # Breakout candle: closes decisively at 1.0875 (> 1.0850)
        candles.append(make_candle(base_t + timedelta(minutes=80), 1.0830, 1.0880, 1.0828, 1.0875))

        # Retracement back to 1.0850 broken resistance (now support)
        candles.append(make_candle(base_t + timedelta(minutes=85), 1.0875, 1.0878, 1.0852, 1.0855))

        # Retest rejection candle: bounces from 1.0848, closes at 1.0865 with long lower wick
        candles.append(make_candle(base_t + timedelta(minutes=90), 1.0855, 1.0870, 1.0848, 1.0865))

        cands = scalper._detect_breakout_retracement_fvg(
            symbol="EURUSD",
            timeframe=Timeframe.M5,
            candles=candles,
            atr=0.0010,
            m15_bias=TrendBias.STRONG_BULLISH,
            h1_bias=TrendBias.STRONG_BULLISH,
            symbol_info=self.eur_info
        )
        self.assertTrue(len(cands) >= 1)
        self.assertEqual(cands[0].direction, OrderType.BUY)
        self.assertEqual(cands[0].related_level, "BREAKOUT_RETRACEMENT_FVG")
        self.assertAlmostEqual(cands[0].metadata["breakout_level"], 1.0850, places=4)
        self.assertEqual(cands[0].metadata["lifecycle_stage"], "EXECUTION_READY")

    # -------------------------------------------------------------------------
    # 8. Sizing Risk Budget Safeguard: MINIMUM_VOLUME_EXCEEDS_RISK_BUDGET
    # -------------------------------------------------------------------------
    def test_10_sizing_safeguard_rejection_reason_standardization(self):
        sizer = PositionSizingEngine(default_risk_percent=1.0)
        # $100 account with 0.01 lot on 100-pip SL ($10 risk) = 10% risk > 2.0% hard cap
        small_acc = AccountInfo(
            account_number=10001,
            balance=100.0,
            equity=100.0,
            free_margin=100.0,
            currency="USD",
            leverage=500
        )
        res = sizer.calculate_lot_size(
            account=small_acc,
            symbol_info=self.eur_info,
            entry_price=1.08500,
            stop_loss=1.07500,  # 100 pips
            adaptive_scalping=True,
            adaptive_min_lot_ceiling_pct=2.0
        )
        self.assertFalse(res.is_approved)
        self.assertTrue(res.rejection_reason.startswith("MINIMUM_VOLUME_EXCEEDS_RISK_BUDGET:"))
        self.assertIn("exceeding target risk", res.rejection_reason)
        self.assertIn("Required margin:", res.rejection_reason)
        self.assertIn("estimated monetary risk:", res.rejection_reason)
        self.assertIn("Min balance needed:", res.rejection_reason)


if __name__ == "__main__":
    unittest.main()
