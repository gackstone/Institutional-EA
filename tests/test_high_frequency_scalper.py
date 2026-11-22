"""
Comprehensive Unit and Integration Test Suite:
High-Frequency, Multi-Position Scalping Engine with Layering and Basket Management.
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, List
import unittest
from unittest.mock import MagicMock, patch

from src.core.contracts import (
    AccountInfo,
    Candle,
    OrderType,
    Position,
    PositionManagementState,
    ProfitManagementMode,
    SetupType,
    SignalCandidate,
    SymbolInfo,
    Timeframe,
    TrendBias,
)
from src.core.config import AppConfig, RiskConfig
from src.execution.continuous_scalper import (
    ContinuousScalpingEngine,
    PositionLayerType,
    PositionLayeringEngine,
    TickEvent,
    TickMomentumTracker,
)
from src.risk.trade_management import (
    BasketAction,
    BasketProfitManager,
    TradeManagementEngine,
)
from src.core.orchestrator import TradingBotOrchestrator


class TestTickMomentumTracker(unittest.TestCase):
    def setUp(self):
        self.tracker = TickMomentumTracker(max_ticks=50)

    def test_velocity_and_acceleration_positive(self):
        t0 = datetime(2026, 11, 17, 12, 0, 0, tzinfo=timezone.utc)
        # Record 10 rising ticks
        for i in range(10):
            t = t0 + timedelta(milliseconds=i * 200)
            price = 2600.0 + (i * 0.5)
            self.tracker.record_tick(
                TickEvent(symbol="XAUUSD", bid=price, ask=price + 0.2, timestamp=t)
            )

        vel = self.tracker.compute_velocity("XAUUSD", window_ticks=5)
        acc = self.tracker.compute_acceleration("XAUUSD")
        self.assertGreater(vel, 0.0)
        self.assertIsInstance(acc, float)

    def test_micro_breakout_detection_buy(self):
        t0 = datetime(2026, 11, 17, 12, 0, 0, tzinfo=timezone.utc)
        # 14 ticks oscillating around 2600.0
        for i in range(14):
            t = t0 + timedelta(milliseconds=i * 200)
            p = 2600.0 + (0.1 if i % 2 == 0 else -0.1)
            self.tracker.record_tick(
                TickEvent(symbol="XAUUSD", bid=p, ask=p + 0.2, timestamp=t)
            )

        # 15th tick surges past range
        t_break = t0 + timedelta(milliseconds=14 * 200)
        self.tracker.record_tick(
            TickEvent(symbol="XAUUSD", bid=2602.0, ask=2602.2, timestamp=t_break)
        )

        res = self.tracker.detect_micro_breakout("XAUUSD", point=0.01)
        self.assertIsNotNone(res)
        direction, level = res
        self.assertEqual(direction, OrderType.BUY)
        self.assertLess(level, 2602.0)

    def test_micro_pullback_detection_buy(self):
        t0 = datetime(2026, 11, 17, 12, 0, 0, tzinfo=timezone.utc)
        # Establish high at 2610.0
        for i in range(5):
            t = t0 + timedelta(milliseconds=i * 200)
            p = 2608.0 + (i * 0.5)
            self.tracker.record_tick(
                TickEvent(symbol="XAUUSD", bid=p, ask=p + 0.2, timestamp=t)
            )

        # Pullback dip to 2607.0
        t_dip = t0 + timedelta(milliseconds=5 * 200)
        self.tracker.record_tick(
            TickEvent(symbol="XAUUSD", bid=2607.0, ask=2607.2, timestamp=t_dip)
        )

        # Turn-up tick to 2607.5
        t_turn = t0 + timedelta(milliseconds=6 * 200)
        self.tracker.record_tick(
            TickEvent(symbol="XAUUSD", bid=2607.5, ask=2607.7, timestamp=t_turn)
        )

        is_pullback = self.tracker.detect_micro_pullback("XAUUSD", OrderType.BUY, atr=2.0)
        self.assertTrue(is_pullback)


class TestPositionLayeringEngine(unittest.TestCase):
    def setUp(self):
        self.engine = PositionLayeringEngine(min_spacing_atr_mult=0.35)

    def test_initial_entry(self):
        allowed, ltype, reason = self.engine.evaluate_layering(
            symbol="XAUUSD",
            direction=OrderType.BUY,
            current_price=2600.0,
            atr=2.0,
            point=0.01,
            active_positions=[],
        )
        self.assertTrue(allowed)
        self.assertEqual(ltype, PositionLayerType.INITIAL)

    def test_confirmation_entry(self):
        pos1 = Position(
            ticket=101,
            symbol="XAUUSD",
            order_type=OrderType.BUY,
            volume=0.02,
            open_price=2600.0,
            current_price=2601.5,
            stop_loss=2598.0,
            take_profit=2605.0,
            profit=30.0,
            open_time=datetime.now(timezone.utc) - timedelta(seconds=20),
        )
        # Current price moved up by 1.50 (above 0.35 * 2.0 = 0.70 spacing)
        allowed, ltype, reason = self.engine.evaluate_layering(
            symbol="XAUUSD",
            direction=OrderType.BUY,
            current_price=2601.5,
            atr=2.0,
            point=0.01,
            active_positions=[pos1],
        )
        self.assertTrue(allowed)
        self.assertEqual(ltype, PositionLayerType.CONFIRMATION)

    def test_continuation_entry(self):
        pos1 = Position(
            ticket=101,
            symbol="XAUUSD",
            order_type=OrderType.BUY,
            volume=0.02,
            open_price=2600.0,
            current_price=2603.0,
            stop_loss=2598.0,
            take_profit=2608.0,
            profit=60.0,
            open_time=datetime.now(timezone.utc) - timedelta(seconds=40),
        )
        pos2 = Position(
            ticket=102,
            symbol="XAUUSD",
            order_type=OrderType.BUY,
            volume=0.02,
            open_price=2601.5,
            current_price=2603.0,
            stop_loss=2599.5,
            take_profit=2608.0,
            profit=30.0,
            open_time=datetime.now(timezone.utc) - timedelta(seconds=20),
        )
        # Current price pushed to 2603.0
        allowed, ltype, reason = self.engine.evaluate_layering(
            symbol="XAUUSD",
            direction=OrderType.BUY,
            current_price=2603.0,
            atr=2.0,
            point=0.01,
            active_positions=[pos1, pos2],
        )
        self.assertTrue(allowed)
        self.assertEqual(ltype, PositionLayerType.CONTINUATION)

    def test_pullback_entry(self):
        pos1 = Position(
            ticket=101,
            symbol="XAUUSD",
            order_type=OrderType.BUY,
            volume=0.02,
            open_price=2602.0,
            current_price=2600.5,
            stop_loss=2598.0,
            take_profit=2608.0,
            profit=-30.0,
            open_time=datetime.now(timezone.utc) - timedelta(seconds=20),
        )
        # Price retraced to 2600.5 (above SL 2598.0 + 0.35*2.0 = 2598.70)
        allowed, ltype, reason = self.engine.evaluate_layering(
            symbol="XAUUSD",
            direction=OrderType.BUY,
            current_price=2600.5,
            atr=2.0,
            point=0.01,
            active_positions=[pos1],
        )
        self.assertTrue(allowed)
        self.assertEqual(ltype, PositionLayerType.PULLBACK)

    def test_anti_stacking_spacing_rejection(self):
        pos1 = Position(
            ticket=101,
            symbol="XAUUSD",
            order_type=OrderType.BUY,
            volume=0.02,
            open_price=2600.0,
            current_price=2600.05,
            stop_loss=2598.0,
            take_profit=2605.0,
            profit=1.0,
            open_time=datetime.now(timezone.utc),
        )
        # Price is only 0.05 away, spacing requires >= 0.70
        allowed, ltype, reason = self.engine.evaluate_layering(
            symbol="XAUUSD",
            direction=OrderType.BUY,
            current_price=2600.05,
            atr=2.0,
            point=0.01,
            active_positions=[pos1],
        )
        self.assertFalse(allowed)
        self.assertIn("narrow", reason.lower())

    def test_opposing_direction_rejection(self):
        pos1 = Position(
            ticket=101,
            symbol="XAUUSD",
            order_type=OrderType.SELL,
            volume=0.02,
            open_price=2600.0,
            current_price=2600.0,
            stop_loss=2602.0,
            take_profit=2595.0,
            profit=0.0,
        )
        allowed, ltype, reason = self.engine.evaluate_layering(
            symbol="XAUUSD",
            direction=OrderType.BUY,
            current_price=2605.0,
            atr=2.0,
            point=0.01,
            active_positions=[pos1],
        )
        self.assertFalse(allowed)
        self.assertIn("opposing", reason.lower())


class TestBasketProfitManager(unittest.TestCase):
    def setUp(self):
        self.cfg = RiskConfig(
            basket_profit_target_usd=20.0,
            basket_trailing_enabled=True,
            basket_trailing_floor_usd=10.0,
        )
        self.basket_mgr = BasketProfitManager(config=self.cfg)
        self.sym_info_map = {
            "XAUUSD": SymbolInfo(symbol="XAUUSD", point=0.01, tick_size=0.01, tick_value=1.0, spread=10.0)
        }

    def test_basket_target_reached_triggers_close(self):
        # 3 layered positions on XAUUSD: profit = $12, $7, $5 => total = $24 (net after costs > $20)
        pos1 = Position(ticket=1, symbol="XAUUSD", order_type=OrderType.BUY, volume=0.02, open_price=2600.0, current_price=2606.0, stop_loss=2598.0, take_profit=2610.0, profit=12.0, commission=-0.14)
        pos2 = Position(ticket=2, symbol="XAUUSD", order_type=OrderType.BUY, volume=0.02, open_price=2602.5, current_price=2606.0, stop_loss=2600.0, take_profit=2610.0, profit=7.0, commission=-0.14)
        pos3 = Position(ticket=3, symbol="XAUUSD", order_type=OrderType.BUY, volume=0.02, open_price=2603.5, current_price=2606.0, stop_loss=2601.0, take_profit=2610.0, profit=5.0, commission=-0.14)

        actions = self.basket_mgr.evaluate_baskets(
            active_positions=[pos1, pos2, pos3],
            symbol_info_map=self.sym_info_map,
            target_basket_net_profit_usd=20.0,
        )
        self.assertEqual(len(actions), 1)
        b_act = actions[0]
        self.assertEqual(b_act.action_type, "CLOSE_BASKET")
        self.assertEqual(b_act.symbol, "XAUUSD")
        self.assertEqual(set(b_act.tickets), {1, 2, 3})
        self.assertGreaterEqual(b_act.basket_net_profit_usd, 20.0)

    def test_basket_trailing_protection_triggered(self):
        # First round: basket peak reaches $18
        pos1 = Position(ticket=1, symbol="XAUUSD", order_type=OrderType.BUY, volume=0.02, open_price=2600.0, current_price=2609.0, stop_loss=2598.0, take_profit=2615.0, profit=18.5, commission=-0.14)
        self.basket_mgr.evaluate_baskets(
            active_positions=[pos1],
            symbol_info_map=self.sym_info_map,
            target_basket_net_profit_usd=25.0,
            basket_trailing_enabled=True,
            basket_trailing_floor_usd=10.0,
        )
        self.assertAlmostEqual(self.basket_mgr.get_peak_profit("XAUUSD_BUY"), 18.12, places=2)

        # Second round: price gives back profit, dropping net to $11.0 (below 72% of $18.22 = $13.12)
        pos1.profit = 11.5
        actions = self.basket_mgr.evaluate_baskets(
            active_positions=[pos1],
            symbol_info_map=self.sym_info_map,
            target_basket_net_profit_usd=25.0,
            basket_trailing_enabled=True,
            basket_trailing_floor_usd=10.0,
        )
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].action_type, "TRAILING_BASKET_EXIT")
        self.assertIn("trailing", actions[0].reason.lower())


class TestIndividualPositionProfitExit(unittest.TestCase):
    def setUp(self):
        self.cfg = RiskConfig(
            target_net_profit_usd=20.0,
            individual_profit_target_usd=10.0,
        )
        self.trade_mgr = TradeManagementEngine(config=self.cfg)
        self.sym_info = SymbolInfo(symbol="XAUUSD", point=0.01, tick_size=0.01, tick_value=1.0, spread=5.0)

    def test_individual_position_closes_at_configured_target(self):
        pos = Position(
            ticket=555,
            symbol="XAUUSD",
            order_type=OrderType.BUY,
            volume=0.02,
            open_price=2600.0,
            current_price=2605.5,
            stop_loss=2598.0,
            take_profit=2615.0,
            profit=11.0,
            commission=-0.14,
            profit_mode=ProfitManagementMode.QUICK_SCALP,
        )
        candles = [
            Candle(time=datetime.now(timezone.utc), open=2600.0, high=2606.0, low=2599.5, close=2605.5, tick_volume=100)
        ]
        actions = self.trade_mgr.evaluate_position(
            position=pos,
            symbol_info=self.sym_info,
            recent_candles=candles,
            scalp_mode=True,
        )
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].action_type, "FULL_CLOSE")
        self.assertIn("Individual profit target reached", actions[0].reason)


class TestTickDrivenExecution(unittest.TestCase):
    def setUp(self):
        self.engine = ContinuousScalpingEngine(symbols=["XAUUSD"], min_confluence_score=0.0, min_rr=0.0)
        self.sym_info = SymbolInfo(symbol="XAUUSD", point=0.01, tick_size=0.01, tick_value=1.0, spread=10.0)

    def test_scan_tick_opportunity_generates_valid_candidate(self):
        # 10 ticks building upward momentum
        t0 = datetime(2026, 11, 17, 12, 0, 0, tzinfo=timezone.utc)
        for i in range(10):
            t = t0 + timedelta(milliseconds=i * 200)
            p = 2600.0 + (i * 0.4)
            tick = {
                "bid": p,
                "ask": p + 0.2,
                "spread_points": 20.0,
                "timestamp": t,
                "available": True,
            }
            cand = self.engine.scan_tick_opportunity(
                symbol="XAUUSD",
                tick=tick,
                candles_by_tf={
                    Timeframe.M1: [Candle(time=t0, open=2595.0, high=2604.0, low=2594.0, close=p, tick_volume=50)] * 10
                },
                active_positions=[],
                symbol_info=self.sym_info,
            )

        self.assertIsNotNone(cand)
        self.assertEqual(cand.symbol, "XAUUSD")
        self.assertEqual(cand.direction, OrderType.BUY)
        self.assertEqual(cand.metadata.get("layer_type"), "INITIAL")
        self.assertTrue(cand.metadata.get("tick_driven"))


if __name__ == "__main__":
    unittest.main()
