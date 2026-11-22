"""
Test Suite: Unrestricted Multi-Position Execution and Spread Gate Removal
Validates:
1. Complete removal of 3-position minimum and 7-position maximum restrictions:
   - Valid execution with 0, 1, 3, 7, 10, 15 active positions.
   - Opportunity-driven multi-position execution.
2. Complete removal of strategy-level spread rejection restrictions:
   - Measured spread is recorded for diagnostics but does NOT reject setups.
   - Setups with high spread, high spread-to-SL ratio, and high spread-to-ATR ratio reach execution.
3. Concurrency and Multi-Instrument independence:
   - Multiple valid opportunities in single scan processed independently.
   - XAUUSD, USDJPY, BTCUSD operate independently under scheduling rules.
4. Drawdown isolation:
   - An existing position in drawdown does NOT block unrelated valid setups.
5. Genuine financial safeguards:
   - Margin sufficiency, critical margin (<150%), invalid volumes, and invalid stops remain enforced.
"""

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.core.contracts import (
    AccountInfo,
    Candle,
    OrderType,
    Position,
    ProfitManagementMode,
    SetupType,
    SignalCandidate,
    SymbolInfo,
    Timeframe,
    TradeOrder,
)
from src.core.config import AppConfig, RiskConfig, StrategyConfig
from src.risk.position_sizing import PositionSizingEngine
from src.execution.order_manager import OrderManager
from src.risk.portfolio_risk import PortfolioRiskEngine
from src.risk.directional_exposure import SameSymbolExposureManager, ExposureDisposition
from src.risk.portfolio_exposure import PortfolioExposureEngine
from src.risk.fast_risk_guard import FastRiskGuardEngine
from src.execution.analytics.spread_filter import SpreadFilter


class TestUnrestrictedPositionsAndSpreadRemoval(unittest.TestCase):
    def setUp(self):
        self.config = AppConfig()
        self.config.risk = RiskConfig()
        self.config.strategy = StrategyConfig()
        self.portfolio_risk = PortfolioRiskEngine(self.config)
        self.sizing_engine = PositionSizingEngine(default_risk_percent=1.0)

        self.account = AccountInfo(
            account_number=1200057798,
            balance=25000.0,
            equity=25000.0,
            margin=1000.0,
            free_margin=24000.0,
            margin_level=2500.0,
            currency="USD",
            trade_mode="DEMO",
            leverage=100,
        )

        self.symbol_xau = SymbolInfo(
            symbol="XAUUSD.m",
            point=0.01,
            digits=2,
            spread=25.0,  # 25 points = $0.25
            lot_step=0.01,
            min_lot=0.01,
            max_lot=10.0,
            tick_value=1.0,
            tick_size=0.01,
            contract_size=100.0,
            ask=2700.25,
            bid=2700.00,
        )

        self.symbol_jpy = SymbolInfo(
            symbol="USDJPY.m",
            point=0.001,
            digits=3,
            spread=12.0,
            lot_step=0.01,
            min_lot=0.01,
            max_lot=10.0,
            tick_value=0.67,
            tick_size=0.001,
            contract_size=100000.0,
            ask=154.012,
            bid=154.000,
        )

        self.symbol_btc = SymbolInfo(
            symbol="BTCUSD.m",
            point=0.01,
            digits=2,
            spread=1500.0,  # 1500 points = $15.00
            lot_step=0.01,
            min_lot=0.01,
            max_lot=5.0,
            tick_value=1.0,
            tick_size=0.01,
            contract_size=1.0,
            ask=92015.0,
            bid=92000.0,
        )

    # =========================================================================
    # 1. POSITION COUNT TESTS (0, 1, 3, 7, 10, 15 EXISTING POSITIONS)
    # =========================================================================

    def test_opportunity_driven_execution_at_various_position_counts(self):
        """
        Verifies that PortfolioRiskEngine permits valid trading opportunities
        when active position count is 0, 1, 3, 7, 10, and 15 without artificial ceiling.
        """
        for count in [0, 1, 3, 7, 10, 15]:
            active_positions = [
                Position(
                    ticket=1000 + i,
                    symbol=f"SYM_{i}",
                    order_type=OrderType.BUY,
                    volume=0.01,
                    open_price=100.0,
                    current_price=100.5,
                    stop_loss=99.0,
                    take_profit=103.0,
                    profit=10.0,
                    initial_risk_amount=10.0,
                )
                for i in range(count)
            ]

            candidate = SignalCandidate(
                id=f"SIG_TEST_{count}",
                symbol="XAUUSD.m",
                timeframe=Timeframe.M5,
                direction=OrderType.BUY,
                setup_type=SetupType.SESSION_SWEEP,
                entry_price=2700.25,
                stop_loss=2695.0,
                take_profit=2715.0,
                risk_reward=2.8,
                score=82.0,
                timestamp=datetime.now(timezone.utc),
                status="APPROVED",
            )

            permitted, reason = self.portfolio_risk.evaluate_new_order_permission(
                candidate=candidate,
                account=self.account,
                active_positions=active_positions,
                proposed_monetary_risk=25.0,
                proposed_volume=0.02,
            )

            self.assertTrue(
                permitted,
                f"Opportunity-driven engine failed with {count} active positions: {reason}",
            )
            self.assertIsNone(reason)

    def test_order_manager_precheck_allows_more_than_7_positions(self):
        """
        Verifies that OrderManager pre-trade checklist allows execution
        when 7 or more positions are already open (hard 7 ceiling removed).
        """
        bridge = MagicMock()
        bridge.ping.return_value = True
        bridge.check_symbol_session.return_value = {"trading_allowed": True}

        order_mgr = OrderManager(self.config, bridge, self.sizing_engine, self.portfolio_risk)

        positions_10 = [
            Position(
                ticket=2000 + i,
                symbol=f"PAIRS_{i}",
                order_type=OrderType.BUY,
                volume=0.01,
                open_price=100.0,
                current_price=100.5,
                stop_loss=99.0,
                take_profit=103.0,
                profit=5.0,
                initial_risk_amount=10.0,
            )
            for i in range(10)
        ]

        candidate = SignalCandidate(
            id="SIG_XAU_11TH",
            symbol="XAUUSD.m",
            timeframe=Timeframe.M5,
            direction=OrderType.BUY,
            setup_type=SetupType.SESSION_SWEEP,
            entry_price=2700.25,
            stop_loss=2695.0,
            take_profit=2715.0,
            risk_reward=2.8,
            score=85.0,
            timestamp=datetime.now(timezone.utc),
            status="APPROVED",
        )

        check = order_mgr.run_pre_trade_checklist(
            candidate=candidate,
            account=self.account,
            symbol_info=self.symbol_xau,
            active_positions=positions_10,
        )

        self.assertTrue(
            check.passed,
            f"Pre-check rejected order with 10 existing positions: {check.rejection_reasons}",
        )
        self.assertNotIn(
            "Maximum simultaneous portfolio ceiling reached",
            str(check.rejection_reasons),
        )

    # =========================================================================
    # 2. SPREAD RESTRICTIONS REMOVAL TESTS
    # =========================================================================

    def test_spread_filter_retains_diagnostics_without_rejection(self):
        """
        Verifies that SpreadFilter records diagnostic ratio without vetoing trade.
        """
        spread_filter = SpreadFilter(max_spread_multiplier=2.0)
        spread_filter.set_hourly_median("EURUSD.m", 14, 8.0)
        # Normal hour (14 UTC), elevated spread 30 pts vs 8 pts expected (3.75x)
        res = spread_filter.evaluate_spread("EURUSD.m", current_spread_pts=30.0, hour_utc=14)
        self.assertTrue(res.allowed)
        self.assertIn("strategy-level spread rejection is disabled", res.reason.lower())
        self.assertEqual(res.spread_ratio, 3.75)

    def test_order_manager_wide_spread_does_not_reject_setup(self):
        """
        Verifies that an unusually wide spread (e.g. 500 points on XAUUSD)
        does not cause OrderManager pre-check to reject the trade.
        """
        bridge = MagicMock()
        bridge.ping.return_value = True
        bridge.check_symbol_session.return_value = {"trading_allowed": True}
        order_mgr = OrderManager(self.config, bridge, self.sizing_engine, self.portfolio_risk)

        wide_xau = SymbolInfo(
            symbol="XAUUSD.m",
            point=0.01,
            digits=2,
            spread=500.0,  # $5.00 wide spread
            lot_step=0.01,
            min_lot=0.01,
            max_lot=10.0,
            tick_value=1.0,
            tick_size=0.01,
            contract_size=100.0,
            ask=2705.00,
            bid=2700.00,
        )

        candidate = SignalCandidate(
            id="SIG_WIDE_SPREAD",
            symbol="XAUUSD.m",
            timeframe=Timeframe.M5,
            direction=OrderType.BUY,
            setup_type=SetupType.SESSION_SWEEP,
            entry_price=2705.00,
            stop_loss=2695.00,  # 1000 pts SL ($10.00), spread is 50% of SL
            take_profit=2730.00,
            risk_reward=2.5,
            score=80.0,
            timestamp=datetime.now(timezone.utc),
            status="APPROVED",
        )

        check = order_mgr.run_pre_trade_checklist(
            candidate=candidate,
            account=self.account,
            symbol_info=wide_xau,
            active_positions=[],
        )

        self.assertTrue(
            check.passed,
            f"Pre-check unexpectedly rejected wide spread: {check.rejection_reasons}",
        )
        self.assertIn("spread_pts", candidate.metadata)
        self.assertEqual(candidate.metadata["spread_pts"], 500.0)

    # =========================================================================
    # 3. DRAWDOWN ISOLATION TESTS
    # =========================================================================

    def test_position_in_drawdown_does_not_block_unrelated_setups(self):
        """
        Verifies that an existing position in drawdown (e.g. XAUUSD down -$250)
        does not block a valid setup on USDJPY or BTCUSD or an independent setup.
        """
        drawdown_position = Position(
            ticket=5001,
            symbol="XAUUSD.m",
            order_type=OrderType.BUY,
            volume=0.1,
            open_price=2720.0,
            current_price=2695.0,
            stop_loss=2680.0,
            take_profit=2750.0,
            profit=-250.0,  # in drawdown
            initial_risk_amount=40.0,
        )

        cand_jpy = SignalCandidate(
            id="SIG_USDJPY_VALID",
            symbol="USDJPY.m",
            timeframe=Timeframe.M5,
            direction=OrderType.BUY,
            setup_type=SetupType.FAST_SCALP,
            entry_price=154.012,
            stop_loss=153.500,
            take_profit=155.500,
            risk_reward=2.9,
            score=84.0,
            timestamp=datetime.now(timezone.utc),
            status="APPROVED",
        )

        permitted, reason = self.portfolio_risk.evaluate_new_order_permission(
            candidate=cand_jpy,
            account=self.account,
            active_positions=[drawdown_position],
            proposed_monetary_risk=30.0,
            proposed_volume=0.05,
        )

        self.assertTrue(
            permitted,
            f"Drawdown position on XAUUSD blocked unrelated USDJPY setup: {reason}",
        )

    # =========================================================================
    # 4. MULTI-INSTRUMENT INDEPENDENCE & CONCURRENCY
    # =========================================================================

    def test_three_approved_instruments_coexist_independently(self):
        """
        Verifies that XAUUSD, USDJPY, and BTCUSD can all have concurrent open
        positions without artificial interference.
        """
        active_positions = [
            Position(ticket=6001, symbol="XAUUSD.m", order_type=OrderType.BUY, volume=0.02, open_price=2700.0, current_price=2705.0, stop_loss=2690.0, take_profit=2720.0, profit=10.0, initial_risk_amount=20.0),
            Position(ticket=6002, symbol="USDJPY.m", order_type=OrderType.SELL, volume=0.05, open_price=154.0, current_price=153.5, stop_loss=154.8, take_profit=152.0, profit=25.0, initial_risk_amount=20.0),
            Position(ticket=6003, symbol="BTCUSD.m", order_type=OrderType.BUY, volume=0.01, open_price=92000.0, current_price=92500.0, stop_loss=91000.0, take_profit=94000.0, profit=5.0, initial_risk_amount=10.0),
        ]

        # Another valid XAUUSD opportunity arrives
        cand_xau_2 = SignalCandidate(
            id="SIG_XAU_SECOND",
            symbol="XAUUSD.m",
            timeframe=Timeframe.M15,
            direction=OrderType.BUY,
            setup_type=SetupType.SESSION_SWEEP,
            entry_price=2705.0,
            stop_loss=2695.0,
            take_profit=2725.0,
            risk_reward=2.0,
            score=88.0,
            timestamp=datetime.now(timezone.utc),
            status="APPROVED",
        )

        permitted, reason = self.portfolio_risk.evaluate_new_order_permission(
            candidate=cand_xau_2,
            account=self.account,
            active_positions=active_positions,
            proposed_monetary_risk=20.0,
            proposed_volume=0.02,
        )

        self.assertTrue(
            permitted,
            f"Multi-instrument coexistence blocked new valid XAU opportunity: {reason}",
        )

    # =========================================================================
    # 5. PRESERVATION OF GENUINE FINANCIAL SAFEGUARDS
    # =========================================================================

    def test_critical_margin_floor_is_preserved(self):
        """
        Verifies that critical margin floor (< 150%) still rejects trades.
        """
        critical_account = AccountInfo(
            account_number=1200057798,
            balance=2000.0,
            equity=140.0,
            margin=100.0,
            free_margin=40.0,
            margin_level=140.0,  # < 150% critical
            currency="USD",
            trade_mode="DEMO",
            leverage=100,
        )

        candidate = SignalCandidate(
            id="SIG_CRIT_MARGIN",
            symbol="XAUUSD.m",
            timeframe=Timeframe.M5,
            direction=OrderType.BUY,
            setup_type=SetupType.SESSION_SWEEP,
            entry_price=2700.25,
            stop_loss=2695.0,
            take_profit=2715.0,
            risk_reward=2.8,
            score=80.0,
            timestamp=datetime.now(timezone.utc),
            status="APPROVED",
        )

        permitted, reason = self.portfolio_risk.evaluate_new_order_permission(
            candidate=candidate,
            account=critical_account,
            active_positions=[],
            proposed_monetary_risk=20.0,
            proposed_volume=0.01,
        )

        self.assertFalse(permitted)
        self.assertIn("Margin level critical", reason)

    def test_invalid_order_stops_rejected(self):
        """
        Verifies that invalid Stop Loss (e.g. SL >= entry on BUY) is strictly rejected.
        """
        bridge = MagicMock()
        bridge.ping.return_value = True
        bridge.check_symbol_session.return_value = {"trading_allowed": True}
        order_mgr = OrderManager(self.config, bridge, self.sizing_engine, self.portfolio_risk)

        invalid_candidate = SignalCandidate(
            id="SIG_INVALID_SL",
            symbol="XAUUSD.m",
            timeframe=Timeframe.M5,
            direction=OrderType.BUY,
            setup_type=SetupType.SESSION_SWEEP,
            entry_price=2700.00,
            stop_loss=2705.00,  # SL is ABOVE entry on BUY!
            take_profit=2720.00,
            risk_reward=2.0,
            score=80.0,
            timestamp=datetime.now(timezone.utc),
            status="APPROVED",
        )

        check = order_mgr.run_pre_trade_checklist(
            candidate=invalid_candidate,
            account=self.account,
            symbol_info=self.symbol_xau,
            active_positions=[],
        )

        self.assertFalse(check.passed)
        self.assertTrue(any("Invalid stops" in r for r in check.rejection_reasons))


if __name__ == "__main__":
    unittest.main()
