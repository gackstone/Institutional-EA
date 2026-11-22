"""
Comprehensive Test Suite for AlgoVistra Strategy Skills & Combined Pipeline.
Tests all 15 video cards with synthetic candle fixtures (bullish and bearish),
plus explicit negative scenarios:
- Wick-only break (V9)
- First close only (V6)
- Close through gap (V5/V10)
- Mid-range entry (V13)
- Late entry / chasing (V14)
- Single big drop holding above protected low (V4)
- Early break-even mistake (V12)
"""

import unittest
from datetime import datetime, timezone, timedelta
from typing import List

from src.core.contracts import Candle
from src.engine.types import Context, SkillResult
from src.engine.pipeline import AlgoVistraEnginePipeline, SetupLifecycleState

# Import skills
from src.engine.skills import (
    protected_swing_marker,
    trend_by_structure,
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
    structure_momentum_monitor,
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


def make_candle(t_sec: int, o: float, h: float, l: float, c: float, complete: bool = True) -> Candle:
    dt = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=15 * t_sec)
    return Candle(time=dt, open=o, high=h, low=l, close=c, complete=complete)


class TestAlgoVistraSkills(unittest.TestCase):

    # --------------------------------------------------------------------------
    # Card 1: Inducement + OB Entry (Video 1)
    # --------------------------------------------------------------------------
    def test_v1_inducement_ob_entry_bullish(self):
        # 1. Bearish OB candle
        # 2. Bullish impulse push breaking highs
        # 3. First pullback low (inducement)
        # 4. Sweep of inducement into OB, bullish close in block
        candles = [
            make_candle(0, 1.1000, 1.1010, 1.0990, 1.1005),
            make_candle(1, 1.1005, 1.1010, 1.0980, 1.0985), # OB candle (1.0980 - 1.1010)
            make_candle(2, 1.0990, 1.1050, 1.0985, 1.1045), # Strong impulse
            make_candle(3, 1.1045, 1.1070, 1.1040, 1.1065), # High 1.1070
            make_candle(4, 1.1065, 1.1068, 1.1020, 1.1030), # Pullback (Inducement low = 1.1020)
            make_candle(5, 1.1030, 1.1055, 1.1025, 1.1050), # Bounce
            make_candle(6, 1.0998, 1.1010, 1.0995, 1.1005), # Sweeps 1.1020 into OB, bullish close at 1.1005
        ]
        ctx = Context(trend="BULL", atr=0.0020, pip_size=0.0001)
        res = inducement_ob_entry.evaluate(candles, ctx)
        self.assertEqual(res.status, "TRIGGERED")
        self.assertEqual(res.tag, "[VIDEO 1]")
        self.assertIn("entry", res.level_prices)
        self.assertLessEqual(res.level_prices["stop_loss"], 1.0985)

    def test_v1_close_below_ob_invalidates(self):
        # Negative case: candle closes below OB low -> setup off [VIDEO 1]
        candles = [
            make_candle(0, 1.1000, 1.1010, 1.0990, 1.1005),
            make_candle(1, 1.1005, 1.1010, 1.0980, 1.0985), # OB low = 1.0980
            make_candle(2, 1.0990, 1.1050, 1.0985, 1.1045),
            make_candle(3, 1.1045, 1.1070, 1.1040, 1.1065),
            make_candle(4, 1.1065, 1.1068, 1.1020, 1.1030),
            make_candle(5, 1.1030, 1.1035, 1.0970, 1.0975), # Closed below OB bottom 1.0980
        ]
        ctx = Context(trend="BULL", atr=0.0020)
        res = inducement_ob_entry.evaluate(candles, ctx)
        self.assertEqual(res.status, "INVALID")

    # --------------------------------------------------------------------------
    # Card 2: Premium / Discount Filter (Video 2)
    # --------------------------------------------------------------------------
    def test_v2_premium_discount_filter(self):
        ctx = Context(trend="BULL", protected_low=1.1000, current_price=1.1040)
        candles = [
            make_candle(0, 1.1000, 1.1010, 1.1000, 1.1010),
            make_candle(1, 1.1010, 1.1100, 1.1005, 1.1090), # Leg: 1.1000 to 1.1100 -> Eq = 1.1050
            make_candle(2, 1.1090, 1.1095, 1.1035, 1.1040),
        ]
        # In discount (1.1040 <= 1.1050) -> PASS
        res = premium_discount_filter.evaluate(candles, ctx)
        self.assertEqual(res.status, "PASS")
        self.assertEqual(res.level_prices["equilibrium"], 1.1050)

        # Negative case: entry in premium for buy
        ctx.current_price = 1.1070
        res_fail = premium_discount_filter.evaluate(candles, ctx)
        self.assertEqual(res_fail.status, "FAIL")

    # --------------------------------------------------------------------------
    # Card 3: Protected Swing Marker (Video 3)
    # --------------------------------------------------------------------------
    def test_v3_protected_swing_marker(self):
        candles = [
            make_candle(0, 1.1000, 1.1020, 1.0990, 1.1015),
            make_candle(1, 1.1015, 1.1050, 1.1010, 1.1040), # Swing high = 1.1050
            make_candle(2, 1.1040, 1.1045, 1.1020, 1.1025),
            make_candle(3, 1.1025, 1.1030, 1.1005, 1.1010), # Dip (Protected Low = 1.1005)
            make_candle(4, 1.1010, 1.1060, 1.1008, 1.1055), # Body close 1.1055 > 1.1050 (BOS)
            make_candle(5, 1.1055, 1.1070, 1.1050, 1.1065),
        ]
        ctx = Context()
        res = protected_swing_marker.evaluate(candles, ctx)
        self.assertEqual(res.status, "PASS")
        self.assertEqual(res.level_prices["protected_low"], 1.1005)
        self.assertEqual(res.level_prices["bos_level"], 1.1050)

    # --------------------------------------------------------------------------
    # Card 4: Trend by Structure (Video 4)
    # --------------------------------------------------------------------------
    def test_v4_single_big_drop_holds_above_protected_low(self):
        # Negative scenario: huge red candle that stops above protected low changes nothing [VIDEO 4]
        ctx = Context(protected_low=1.1000)
        candles = [
            make_candle(0, 1.1000, 1.1050, 1.1000, 1.1040),
            make_candle(1, 1.1040, 1.1090, 1.1035, 1.1085),
            make_candle(2, 1.1085, 1.1088, 1.1015, 1.1020), # Massive drop from 1.1085 to 1.1020, but holds above 1.1000
        ]
        res = trend_by_structure.evaluate(candles, ctx)
        self.assertEqual(res.status, "PASS")
        self.assertEqual(ctx.trend, "BULL") # Trend is NOT flipped by single large candle

    def test_v4_choch_on_close_below_protected_low(self):
        # Candle close below protected low causes CHOCH [VIDEO 4]
        ctx = Context(protected_low=1.1000)
        candles = [
            make_candle(0, 1.1050, 1.1080, 1.1040, 1.1070),
            make_candle(1, 1.1070, 1.1075, 1.0990, 1.0995), # Body close 1.0995 < 1.1000
        ]
        res = trend_by_structure.evaluate(candles, ctx)
        self.assertEqual(ctx.trend, "RANGE/TRANSITION")

    # --------------------------------------------------------------------------
    # Card 5: Liquidity Sweep + FVG Entry (Video 5)
    # --------------------------------------------------------------------------
    def test_v5_sweep_fvg_entry(self):
        candles = [
            make_candle(0, 1.1020, 1.1030, 1.1000, 1.1010), # Prior low = 1.1000
            make_candle(1, 1.1010, 1.1015, 1.0980, 1.1005), # Sweep: low=1.0980, close=1.1005 (back inside)
            make_candle(2, 1.1005, 1.1025, 1.1000, 1.1020), # C1 high = 1.1025
            make_candle(3, 1.1020, 1.1070, 1.1018, 1.1065), # C2 displacement
            make_candle(4, 1.1065, 1.1090, 1.1045, 1.1080), # C3 low = 1.1045 -> FVG: 1.1025 to 1.1045 (mid=1.1035)
            make_candle(5, 1.1080, 1.1085, 1.1030, 1.1040), # Returns to gap, closes at 1.1040 (>= 1.1035 mid)
        ]
        ctx = Context(trend="BULL", pip_size=0.0001)
        res = sweep_fvg_entry.evaluate(candles, ctx)
        self.assertEqual(res.status, "TRIGGERED")
        self.assertLessEqual(res.level_prices["stop_loss"], 1.0980)

    # --------------------------------------------------------------------------
    # Card 6: Breakout vs Trap Classifier (Video 6)
    # --------------------------------------------------------------------------
    def test_v6_breakout_trap_classifier(self):
        ctx = Context()
        ctx.parameters["test_level"] = 1.1050
        ctx.parameters["test_side"] = "HIGH"

        # Negative case: 1 close above level is PENDING [VIDEO 6]
        candles_1_close = [
            make_candle(0, 1.1030, 1.1045, 1.1025, 1.1040),
            make_candle(1, 1.1040, 1.1060, 1.1035, 1.1055), # 1st close above
        ]
        res1 = breakout_trap_classifier.evaluate(candles_1_close, ctx)
        self.assertEqual(res1.status, "PENDING")

        # Breakout confirmed: 2 consecutive closes above level [VIDEO 6]
        candles_2_closes = [
            make_candle(0, 1.1040, 1.1060, 1.1035, 1.1055), # 1st close
            make_candle(1, 1.1055, 1.1068, 1.1051, 1.1062), # 2nd close
        ]
        res2 = breakout_trap_classifier.evaluate(candles_2_closes, ctx)
        self.assertEqual(res2.status, "BREAKOUT_CONFIRMED")

        # Trap case: pierced above, closed back inside [VIDEO 6]
        candles_trap = [
            make_candle(0, 1.1040, 1.1048, 1.1030, 1.1042),
            make_candle(1, 1.1042, 1.1070, 1.1038, 1.1045), # Pierced 1.1070, closed 1.1045 <= 1.1050
        ]
        res3 = breakout_trap_classifier.evaluate(candles_trap, ctx)
        self.assertEqual(res3.status, "TRAP")

    # --------------------------------------------------------------------------
    # Card 7: Liquidity Mapper (Video 7)
    # --------------------------------------------------------------------------
    def test_v7_liquidity_is_context_not_signal(self):
        candles = [
            make_candle(0, 1.1000, 1.1050, 1.0990, 1.1020),
            make_candle(1, 1.1020, 1.1030, 1.1010, 1.1025),
            make_candle(2, 1.1025, 1.1050, 1.1015, 1.1030), # Equal high at 1.1050
            make_candle(3, 1.1030, 1.1040, 1.1020, 1.1035),
            make_candle(4, 1.1035, 1.1042, 1.1028, 1.1038),
        ]
        ctx = Context(atr=0.0020)
        res = liquidity_mapper.evaluate(candles, ctx)
        # Must never return TRIGGERED by itself [VIDEO 7]
        self.assertEqual(res.status, "PASS")
        self.assertTrue(len(ctx.liquidity_pools) > 0)
        self.assertIn("target_bsl", res.level_prices)

    # --------------------------------------------------------------------------
    # Card 8: Inversion FVG (Video 8)
    # --------------------------------------------------------------------------
    def test_v8_ifvg_inversion(self):
        candles = [
            make_candle(0, 1.1000, 1.1020, 1.0995, 1.1015), # C1 high 1.1020
            make_candle(1, 1.1015, 1.1060, 1.1010, 1.1055), # C2
            make_candle(2, 1.1055, 1.1070, 1.1040, 1.1065), # C3 low 1.1040 -> Bull FVG [1.1020 - 1.1040]
            make_candle(3, 1.1065, 1.1070, 1.1010, 1.1015), # Pierces downward, closes 1.1015 < 1.1020 (broken)
            make_candle(4, 1.1015, 1.1030, 1.1010, 1.1018), # Retest into gap, closes 1.1018 <= 1.1020
            make_candle(5, 1.1018, 1.1022, 1.0980, 1.0985), # Confirmation candle drops away
        ]
        ctx = Context(pip_size=0.0001)
        res = ifvg_inversion.evaluate(candles, ctx)
        self.assertEqual(res.status, "TRIGGERED")
        self.assertEqual(res.metadata["direction"], "SELL")

    # --------------------------------------------------------------------------
    # Card 9: FVG Quality Score (Video 9)
    # --------------------------------------------------------------------------
    def test_v9_fvg_quality_score_and_wick_only_break(self):
        ctx = Context(atr=0.0010)
        # Strong FVG: broke previous high with body close
        candles_strong = [
            make_candle(0, 1.1000, 1.1030, 1.0990, 1.1020), # Prev high 1.1030
            make_candle(1, 1.1020, 1.1025, 1.1010, 1.1015),
            make_candle(2, 1.1015, 1.1070, 1.1010, 1.1060), # Body close 1.1060 > 1.1030 (BOS)
            make_candle(3, 1.1060, 1.1080, 1.1045, 1.1075),
        ]
        ctx.parameters = {"fvg_top": 1.1045, "fvg_bottom": 1.1025, "fvg_direction": "BUY"}
        res_strong = fvg_quality_score.evaluate(candles_strong, ctx)
        self.assertEqual(res_strong.status, "PASS")
        self.assertEqual(res_strong.level_prices["fvg_score"], 2.0)

        # Negative scenario: Wick-only break (does not close above) [VIDEO 9]
        candles_wick_only = [
            make_candle(0, 1.1000, 1.1050, 1.0990, 1.1040), # Prev high 1.1050
            make_candle(1, 1.1040, 1.1045, 1.1020, 1.1025),
            make_candle(2, 1.1025, 1.1055, 1.1020, 1.1048), # Wick 1.1055 > 1.1050, but close 1.1048 <= 1.1050 (No BOS!)
            make_candle(3, 1.1048, 1.1060, 1.1040, 1.1050),
        ]
        res_wick = fvg_quality_score.evaluate(candles_wick_only, ctx)
        self.assertEqual(res_wick.status, "FAIL")
        self.assertEqual(res_wick.level_prices["fvg_score"], 0.0)

    # --------------------------------------------------------------------------
    # Card 10: FVG Return Depth vs Close (Video 10)
    # --------------------------------------------------------------------------
    def test_v10_fvg_close_through_gap_broken(self):
        ctx = Context(atr=0.0010)
        ctx.parameters = {"fvg_top": 1.1050, "fvg_bottom": 1.1030, "fvg_direction": "BUY"}
        # Negative scenario: candle body closes through the gap -> BROKEN [VIDEO 10]
        candles_broken = [
            make_candle(0, 1.1060, 1.1070, 1.1055, 1.1065),
            make_candle(1, 1.1065, 1.1068, 1.1025, 1.1028), # Closes at 1.1028 < 1.1030
        ]
        res = fvg_return_classifier.evaluate(candles_broken, ctx)
        self.assertEqual(res.status, "BROKEN")

    # --------------------------------------------------------------------------
    # Card 11: FVG Context Guard (Video 11)
    # --------------------------------------------------------------------------
    def test_v11_fvg_context_guard_rejects_standing_limit(self):
        ctx = Context()
        ctx.parameters = {"proposed_order_type": "BUY_LIMIT", "has_sweep_context": False}
        res = fvg_context_guard.evaluate([], ctx)
        # Must reject blind limit order [VIDEO 11]
        self.assertEqual(res.status, "FAIL")

    # --------------------------------------------------------------------------
    # Card 12: Stop Management & Early BE Scenario (Video 12)
    # --------------------------------------------------------------------------
    def test_v12_early_be_scenario_holds_sl(self):
        # Scenario: in profit, but no new protected structure formed.
        # Video 12 rule: do NOT move to BE just because you're in profit!
        ctx = Context(current_price=1.1050, protected_low=1.0980) # Protected low is still original, below entry
        ctx.parameters = {
            "position_open_price": 1.1000,
            "position_current_sl": 1.0980,
            "position_direction": "BUY",
            "be_move_mode": "structure_only",
        }
        res = stop_management_policy.evaluate([], ctx)
        self.assertEqual(res.status, "HOLD") # Does NOT move to BE prematurely

        # Trail only when a new protected low forms above entry
        ctx.protected_low = 1.1020 # New protected low above entry 1.1000
        res_trail = stop_management_policy.evaluate([], ctx)
        self.assertEqual(res_trail.status, "MODIFY_SL")
        self.assertGreater(res_trail.level_prices["new_sl"], 1.1000)

    # --------------------------------------------------------------------------
    # Card 13: Middle of Range Filter (Video 13)
    # --------------------------------------------------------------------------
    def test_v13_middle_of_range_no_trade(self):
        # Range from 1.1000 to 1.1100. Price at 1.1050 is in the exact 50% middle band.
        ctx = Context(current_price=1.1050, trend="RANGE/TRANSITION")
        candles = [
            make_candle(0, 1.1010, 1.1100, 1.1000, 1.1050),
            make_candle(1, 1.1050, 1.1095, 1.1005, 1.1050),
            make_candle(2, 1.1050, 1.1060, 1.1040, 1.1050),
        ]
        res = range_location_filter.evaluate(candles, ctx)
        self.assertEqual(res.status, "NO_TRADE_MIDDLE")

    # --------------------------------------------------------------------------
    # Card 14: Entry Quality Guard (Video 14)
    # --------------------------------------------------------------------------
    def test_v14_late_entry_poor_rr_and_extension(self):
        ctx = Context()
        # Chased move: entry 1.1080 drifted 30 pips from trigger 1.1050; SL=1.1040 (risk 40), target 1.1100 (room 20) -> RR = 0.5 < 1.5
        ctx.parameters = {
            "entry_price": 1.1080,
            "invalidation_price": 1.1040,
            "target_price": 1.1100,
            "trigger_level": 1.1050,
            "min_rr": 1.5,
        }
        res = entry_quality_guard.evaluate([], ctx)
        self.assertEqual(res.status, "FAIL")
        self.assertLess(res.level_prices["rr"], 1.5)

    # --------------------------------------------------------------------------
    # Card 15: Structure Momentum Monitor (Video 15)
    # --------------------------------------------------------------------------
    def test_v15_weakening_pushes_flag_decaying_momentum(self):
        # Consecutive impulse legs: leg 1 = 45 pips, leg 2 = 15 pips (shrinking)
        candles = [
            make_candle(0, 1.0990, 1.1010, 1.0980, 1.1000),
            make_candle(1, 1.1000, 1.1060, 1.1020, 1.1050),  # SH1: H=1.106
            make_candle(2, 1.1050, 1.1050, 1.1010, 1.1020),  # SL1: L=1.101
            make_candle(3, 1.1020, 1.1055, 1.1040, 1.1050),  # SH2: H=1.1055 (Leg 1: 1.1055 - 1.101 = 45 pips)
            make_candle(4, 1.1040, 1.1035, 1.1030, 1.1032),  # SL2: L=1.103
            make_candle(5, 1.1032, 1.1045, 1.1031, 1.1042),  # SH3: H=1.1045 (Leg 2: 1.1045 - 1.103 = 15 pips)
            make_candle(6, 1.1042, 1.1040, 1.1035, 1.1038),
        ]
        ctx = Context(trend="BULL")
        ctx.parameters = {"swing_lookback": 1, "decaying_legs_count": 1}
        res = structure_momentum_monitor.evaluate(candles, ctx)
        self.assertEqual(res.status, "DECAYING")

    # --------------------------------------------------------------------------
    # Pipeline Integration Test (H0 -> G7 sequential evaluation)
    # --------------------------------------------------------------------------
    def test_pipeline_sequential_evaluation(self):
        pipeline = AlgoVistraEnginePipeline(log_json_path=None)
        candles = [
            make_candle(0, 1.1000, 1.1020, 1.0990, 1.1015),
            make_candle(1, 1.1015, 1.1060, 1.1010, 1.1055), # BOS
            make_candle(2, 1.1055, 1.1070, 1.1030, 1.1040),
            make_candle(3, 1.1040, 1.1045, 1.1020, 1.1030),
        ]
        ctx = Context(symbol="EURUSD", current_price=1.1030)
        res = pipeline.evaluate(candles, ctx)
        self.assertIsInstance(res.passed, bool)
        self.assertIn("H0_HTF_POOL_MAP", res.gates)
        self.assertIn("G1_TREND_STRUCTURE", res.gates)

    # --------------------------------------------------------------------------
    # Part 2 Skills Tests (Art of Trading ART-01 to ART-13)
    # --------------------------------------------------------------------------
    def test_art02_swing_hierarchy_recursive_ranking(self):
        # Build sequence with STH and ITH
        candles = [
            make_candle(0, 1.100, 1.102, 1.099, 1.101),
            make_candle(1, 1.101, 1.105, 1.100, 1.103), # STH 1
            make_candle(2, 1.103, 1.104, 1.101, 1.102),
            make_candle(3, 1.102, 1.108, 1.102, 1.106), # STH 2 (Higher -> ITH candidate)
            make_candle(4, 1.106, 1.105, 1.102, 1.103),
            make_candle(5, 1.103, 1.106, 1.101, 1.104), # STH 3
            make_candle(6, 1.104, 1.103, 1.100, 1.102),
        ]
        ctx = Context()
        res = swing_hierarchy.evaluate(candles, ctx)
        self.assertTrue(res.passed)
        self.assertIn("recent_sth", res.level_prices)

    def test_art08_fvg_detector_formula_and_midpoint(self):
        # 3 candles: c1.high = 1.1020, c2 big up, c3.low = 1.1040 -> gap [1.1020 - 1.1040], mid=1.1030
        candles = [
            make_candle(0, 1.1000, 1.1020, 1.0995, 1.1015),
            make_candle(1, 1.1015, 1.1070, 1.1010, 1.1065),
            make_candle(2, 1.1065, 1.1080, 1.1040, 1.1075),
        ]
        ctx = Context()
        res = fvg_detector.evaluate(candles, ctx)
        self.assertTrue(res.passed)
        self.assertAlmostEqual(res.level_prices["fvg_top"], 1.1040)
        self.assertAlmostEqual(res.level_prices["fvg_bottom"], 1.1020)
        self.assertAlmostEqual(res.level_prices["fvg_midpoint"], 1.1030)

    def test_art09_order_block_requires_bos_and_fvg(self):
        # Case A: OB with BOS and FVG -> Qualified
        candles_valid = [
            make_candle(0, 1.1030, 1.1040, 1.1010, 1.1020), # Prior high = 1.1040
            make_candle(1, 1.1020, 1.1025, 1.0990, 1.0995), # Bearish OB (1.0990 - 1.1025)
            make_candle(2, 1.1000, 1.1060, 1.0995, 1.1055), # Strong impulse breaks 1.1040
            make_candle(3, 1.1055, 1.1080, 1.1040, 1.1075), # c3.low 1.1040 > c1.high 1.1025 -> leaves FVG!
            make_candle(4, 1.1075, 1.1070, 1.1030, 1.1035),
        ]
        ctx = Context()
        res_valid = order_block_detector.evaluate(candles_valid, ctx)
        self.assertTrue(res_valid.passed)
        self.assertEqual(res_valid.status, "QUALIFIED_OB")

        # Case B: Candle without FVG -> "No break, no gap = just a candle" [ART-09]
        candles_no_gap = [
            make_candle(0, 1.1030, 1.1040, 1.1010, 1.1020),
            make_candle(1, 1.1020, 1.1025, 1.0990, 1.0995),
            make_candle(2, 1.1000, 1.1045, 1.0995, 1.1035),
            make_candle(3, 1.1035, 1.1040, 1.1015, 1.1025), # c3.low 1.1015 < c1.high 1.1025 -> NO GAP!
            make_candle(4, 1.1025, 1.1030, 1.1010, 1.1020),
        ]
        res_no_gap = order_block_detector.evaluate(candles_no_gap, ctx)
        self.assertFalse(res_no_gap.passed)
        self.assertEqual(res_no_gap.status, "NO_QUALIFIED_OB")

    def test_art10_sweep_vs_breakout_classifier(self):
        # Test Sweep: wick pierces 1.1050 to 1.1060, but closes back inside at 1.1045
        candles_sweep = [
            make_candle(0, 1.1020, 1.1040, 1.1010, 1.1035),
            make_candle(1, 1.1035, 1.1045, 1.1020, 1.1040),
            make_candle(2, 1.1040, 1.1060, 1.1030, 1.1045), # Pierced 1.1050, closed 1.1045
        ]
        ctx = Context()
        ctx.parameters = {"test_level": 1.1050, "has_choch": True}
        res_sweep = sweep_breakout_classifier.evaluate(candles_sweep, ctx)
        self.assertEqual(res_sweep.status, "SWEEP_CONFIRMED")
        self.assertTrue(res_sweep.passed)

        # Test Breakout Form 1 (2 closes beyond) [VIDEO 6, ART-10]
        candles_bo = [
            make_candle(0, 1.1020, 1.1040, 1.1010, 1.1035),
            make_candle(1, 1.1035, 1.1060, 1.1025, 1.1055), # Close 1 beyond 1.1050
            make_candle(2, 1.1055, 1.1070, 1.1052, 1.1065), # Close 2 beyond 1.1050
        ]
        res_bo = sweep_breakout_classifier.evaluate(candles_bo, ctx)
        self.assertEqual(res_bo.status, "BREAKOUT_CONFIRMED")

    def test_art06_five_check_model_master_template(self):
        ctx = Context(trend="BULL")
        # Setup all 5 conditions:
        ctx.parameters = {
            "sweep_extreme": 1.0980,
            "has_choch": True,
            "range_high": 1.1080,
            "range_low": 1.0980, # Eq = 1.1030. Entry in discount
            "fvg_top": 1.1020,
            "fvg_bottom": 1.1005,
            "ob_high": 1.1000,
            "ob_low": 1.0985,
            "nearest_bsl": 1.1080, # Risk = 1.1020 - 1.0980 = 40; Room = 1.1080 - 1.1020 = 60 -> RR = 1.5
            "five_check_min_rr": 1.5,
        }
        candles = [
            make_candle(0, 1.0990, 1.1010, 1.0980, 1.1005),
            make_candle(1, 1.1005, 1.1060, 1.1000, 1.1055),
            make_candle(2, 1.1055, 1.1080, 1.1040, 1.1070),
            make_candle(3, 1.1070, 1.1060, 1.1015, 1.1020),
            make_candle(4, 1.1020, 1.1025, 1.1010, 1.1018), # in discount
        ]
        res = five_check_model.evaluate(candles, ctx)
        self.assertTrue(res.passed)
        self.assertEqual(res.status, "TRIGGERED")

        # Negative test: Failed Check 3 (price in premium) -> REJECTED
        ctx.parameters["range_high"] = 1.1030
        ctx.parameters["range_low"] = 1.0980 # Eq = 1.1005. Price 1.1018 is in PREMIUM!
        res_prem = five_check_model.evaluate(candles, ctx)
        self.assertFalse(res_prem.passed)
        self.assertEqual(res_prem.status, "CHECKS_FAILED")

    def test_art07_range_invalidation_on_swing_break(self):
        # Bullish leg [1.1000 - 1.1080]. If price closes below 1.1000, range is INVALID!
        candles = [
            make_candle(0, 1.1020, 1.1050, 1.1000, 1.1040),
            make_candle(1, 1.1040, 1.1080, 1.1030, 1.1075),
            make_candle(2, 1.1075, 1.1060, 1.0980, 1.0985), # Close 1.0985 < 1.1000!
        ]
        ctx = Context(trend="BULL")
        ctx.protected_low = 1.1000
        res = premium_discount_filter.evaluate(candles, ctx)
        self.assertFalse(res.passed)
        self.assertEqual(res.status, "INVALID_RANGE")
        self.assertFalse(ctx.parameters["range_valid"])

    def test_art03_range_liquidity_loop_next_draw(self):
        ctx = Context(trend="BULL")
        ctx.parameters = {
            "range_high": 1.1100,
            "range_low": 1.1000,
            "fvg_midpoint": 1.1040,
            "nearest_bsl": 1.1100,
        }
        candles = [
            make_candle(0, 1.1010, 1.1030, 1.1005, 1.1025), # Close 1.1025 < fvg_midpoint 1.1040
        ]
        res = range_liquidity_loop.evaluate(candles, ctx)
        self.assertTrue(res.passed)
        self.assertEqual(ctx.parameters["draw_type"], "IRL_GAP")
        self.assertAlmostEqual(ctx.parameters["next_draw_price"], 1.1040)

    def test_art11_candle_anatomy_and_rejection(self):
        # Long upper wick: open=1.1010, high=1.1080, low=1.1005, close=1.1015
        # Range = 75 pips, upper wick = 65 pips (86.7%) -> Rejection!
        c = make_candle(0, 1.1010, 1.1080, 1.1005, 1.1015)
        ctx = Context()
        res = candle_anatomy.evaluate([c], ctx)
        self.assertTrue(res.passed)
        self.assertTrue(res.metadata["is_rejection"])
        self.assertGreater(res.level_prices["upper_wick_pct"], 50.0)


if __name__ == "__main__":
    unittest.main()
