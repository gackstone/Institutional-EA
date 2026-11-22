"""
Comprehensive Verification Test Suite for Master System Upgrade:
- Two-Phase Broker Execution & Position Verification
- Elimination of Premature / False Telegram "TRADE EXECUTED" Alerts
- Unconfirmed Execution Detection & Alerting
- Partial Fill Detection & Management
- Post-Fill Stop-Loss Verification and Protective Modification
- Authoritative Persistent Transaction Ledger & Duplicate Prevention
- Manual Trade Discovery & Protection Notifications
- Connection State Monitoring & Lifecycle Callbacks
"""

import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.core.contracts import (
    AccountInfo, OrderType, Position, SignalCandidate, SetupType,
    ExecutionMode, SymbolInfo, Timeframe
)
from src.core.config import AppConfig
from src.execution.bridge_client import BridgeClient
from src.execution.order_manager import OrderManager, PreTradeCheckResult
from src.execution.transaction_manager import TransactionManager, TransactionRecord
from src.monitoring.alerts_telegram import TelegramAlertManager
from src.notifications.telegram_config import TelegramConfig


def make_candidate(sig_id: str, symbol: str = "EURUSD", direction: OrderType = OrderType.BUY, entry: float = 1.10000, sl: float = 1.09500, tp: float = 1.11000) -> SignalCandidate:
    return SignalCandidate(
        id=sig_id,
        symbol=symbol,
        timeframe=Timeframe.M15,
        direction=direction,
        setup_type=SetupType.LIQUIDITY_SWEEP,
        entry_price=entry,
        stop_loss=sl,
        take_profit=tp,
        risk_reward=2.0,
        score=85.0,
        timestamp=datetime.now(timezone.utc),
        status="APPROVED",
    )


class TestBrokerExecutionUpgrade(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ledger_file = os.path.join(self.temp_dir.name, "test_transactions.json")
        self.tx_mgr = TransactionManager(ledger_file=self.ledger_file)

        self.config = AppConfig()
        self.config.magic_number = 100101
        self.config.execution_mode = ExecutionMode.DEMO

        self.mock_bridge = MagicMock(spec=BridgeClient)
        self.mock_sizing = MagicMock()
        self.mock_portfolio_risk = MagicMock()

        self.order_manager = OrderManager(
            config=self.config,
            bridge=self.mock_bridge,
            sizing_engine=self.mock_sizing,
            portfolio_risk=self.mock_portfolio_risk,
            transaction_manager=self.tx_mgr,
        )

        self.account = AccountInfo(
            account_number=123456,
            balance=10000.0,
            equity=10000.0,
            margin=0.0,
            free_margin=10000.0,
            margin_level=0.0,
            currency="USD",
            leverage=100,
            trade_mode="DEMO",
            trading_enabled=True,
        )

        self.symbol_info = SymbolInfo(
            symbol="EURUSD",
            digits=5,
            point=0.00001,
            tick_size=0.00001,
            tick_value=1.0,
            contract_size=100000.0,
            min_lot=0.01,
            max_lot=100.0,
            lot_step=0.01,
            margin_required=1000.0,
            spread=10.0,
            ask=1.10010,
            bid=1.10000,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_two_phase_broker_verification_success(self):
        """
        Verify that MT5 retcode 10009 only records acceptance,
        and full TRADE EXECUTED status is only established after polling broker positions.
        """
        candidate = make_candidate("SIG_EURUSD_001", direction=OrderType.BUY)

        prevalidated = PreTradeCheckResult(
            passed=True,
            calculated_volume=0.10,
            monetary_risk=50.0,
        )

        # MT5 accepts order (phase 1)
        self.mock_bridge.execute_trade.return_value = {
            "status": "SUCCESS",
            "ticket": 88001,
            "retcode": 10009,
            "price": 1.10020,
        }

        # Polling positions returns confirmed broker position (phase 2)
        confirmed_pos = Position(
            ticket=88001,
            symbol="EURUSD",
            order_type=OrderType.BUY,
            volume=0.10,
            open_price=1.10025,
            current_price=1.10030,
            stop_loss=1.09500,
            take_profit=1.11000,
            profit=5.0,
            magic=100101,
        )
        self.mock_bridge.get_positions.return_value = [confirmed_pos]

        order = self.order_manager.execute_signal(
            candidate=candidate,
            account=self.account,
            symbol_info=self.symbol_info,
            active_positions=[],
            prevalidated=prevalidated,
        )

        self.assertIsNotNone(order)
        self.assertEqual(order.status, "FILLED")
        self.assertEqual(order.ticket, 88001)
        self.assertEqual(order.entry_price, 1.10025)
        self.assertEqual(order.volume, 0.10)
        self.assertEqual(order.stop_loss, 1.09500)

        # Ledger check
        tx = self.tx_mgr.get_transaction_by_signal_id("SIG_EURUSD_001")
        self.assertIsNotNone(tx)
        self.assertEqual(tx.execution_status, "FILLED")
        self.assertEqual(tx.position_ticket, 88001)
        self.assertEqual(tx.actual_fill_price, 1.10025)

    def test_unconfirmed_execution_when_position_missing(self):
        """
        Verify that if MT5 returns retcode 10009 but polling positions and pending orders
        fails to confirm the position, status is UNCONFIRMED, never falsely FILLED.
        """
        candidate = make_candidate("SIG_EURUSD_002", direction=OrderType.BUY)

        prevalidated = PreTradeCheckResult(
            passed=True,
            calculated_volume=0.10,
            monetary_risk=50.0,
        )

        # Order accepted
        self.mock_bridge.execute_trade.return_value = {
            "status": "SUCCESS",
            "ticket": 88002,
            "retcode": 10009,
        }

        # Polling positions returns empty list (position never appeared)
        self.mock_bridge.get_positions.return_value = []
        # Polling pending orders also returns empty
        self.mock_bridge.send_request.return_value = {"status": "SUCCESS", "data": []}

        order = self.order_manager.execute_signal(
            candidate=candidate,
            account=self.account,
            symbol_info=self.symbol_info,
            active_positions=[],
            prevalidated=prevalidated,
        )

        self.assertIsNotNone(order)
        self.assertEqual(order.status, "UNCONFIRMED")
        self.assertEqual(candidate.status, "UNCONFIRMED")
        self.assertIn("no broker position or pending order verified", order.error)

        # Ledger check
        tx = self.tx_mgr.get_transaction_by_signal_id("SIG_EURUSD_002")
        self.assertIsNotNone(tx)
        self.assertEqual(tx.execution_status, "UNCONFIRMED")

    def test_partial_fill_detection(self):
        """
        Verify that when actual volume < requested volume, status is PARTIALLY_FILLED.
        """
        candidate = make_candidate("SIG_EURUSD_003", direction=OrderType.SELL, sl=1.10500, tp=1.09000)

        prevalidated = PreTradeCheckResult(
            passed=True,
            calculated_volume=0.10,
            monetary_risk=50.0,
        )

        self.mock_bridge.execute_trade.return_value = {
            "status": "SUCCESS",
            "ticket": 88003,
            "retcode": 10009,
        }

        # Broker filled 0.04 lots instead of 0.10
        partial_pos = Position(
            ticket=88003,
            symbol="EURUSD",
            order_type=OrderType.SELL,
            volume=0.04,
            open_price=1.09990,
            current_price=1.09990,
            stop_loss=1.10500,
            take_profit=1.09000,
            profit=0.0,
            magic=100101,
        )
        self.mock_bridge.get_positions.return_value = [partial_pos]

        order = self.order_manager.execute_signal(
            candidate=candidate,
            account=self.account,
            symbol_info=self.symbol_info,
            active_positions=[],
            prevalidated=prevalidated,
        )

        self.assertIsNotNone(order)
        self.assertEqual(order.status, "PARTIALLY_FILLED")
        self.assertEqual(order.volume, 0.04)

        # Ledger check
        tx = self.tx_mgr.get_transaction_by_signal_id("SIG_EURUSD_003")
        self.assertIsNotNone(tx)
        self.assertEqual(tx.execution_status, "PARTIALLY_FILLED")
        self.assertEqual(tx.executed_volume, 0.04)

    def test_missing_sl_triggers_immediate_protective_modification(self):
        """
        Verify that if broker stripped SL upon market fill, immediate modification is triggered.
        """
        candidate = make_candidate("SIG_EURUSD_004", direction=OrderType.BUY)

        prevalidated = PreTradeCheckResult(
            passed=True,
            calculated_volume=0.05,
            monetary_risk=25.0,
        )

        self.mock_bridge.execute_trade.return_value = {
            "status": "SUCCESS",
            "ticket": 88004,
            "retcode": 10009,
        }

        # Position opens with sl=0.0
        stripped_pos = Position(
            ticket=88004,
            symbol="EURUSD",
            order_type=OrderType.BUY,
            volume=0.05,
            open_price=1.10010,
            current_price=1.10010,
            stop_loss=0.0,
            take_profit=0.0,
            profit=0.0,
            magic=100101,
        )
        self.mock_bridge.get_positions.return_value = [stripped_pos]
        self.mock_bridge.modify_order.return_value = {"status": "SUCCESS"}

        order = self.order_manager.execute_signal(
            candidate=candidate,
            account=self.account,
            symbol_info=self.symbol_info,
            active_positions=[],
            prevalidated=prevalidated,
        )

        self.assertIsNotNone(order)
        self.assertEqual(order.status, "FILLED")
        self.assertEqual(order.stop_loss, 1.09500)
        self.mock_bridge.modify_order.assert_called_with(ticket=88004, sl=1.09500, tp=1.11000)

    def test_failed_sl_protection_closes_unprotected_position(self):
        """
        Verify that if broker strips SL and modification fails, the position is immediately closed.
        """
        candidate = make_candidate("SIG_EURUSD_005", direction=OrderType.BUY)

        prevalidated = PreTradeCheckResult(
            passed=True,
            calculated_volume=0.05,
            monetary_risk=25.0,
        )

        self.mock_bridge.execute_trade.return_value = {
            "status": "SUCCESS",
            "ticket": 88005,
            "retcode": 10009,
        }

        stripped_pos = Position(
            ticket=88005,
            symbol="EURUSD",
            order_type=OrderType.BUY,
            volume=0.05,
            open_price=1.10010,
            current_price=1.10010,
            stop_loss=0.0,
            take_profit=0.0,
            profit=0.0,
            magic=100101,
        )
        self.mock_bridge.get_positions.return_value = [stripped_pos]
        self.mock_bridge.modify_order.return_value = {"status": "ERROR", "message": "Broker modify rejected"}

        order = self.order_manager.execute_signal(
            candidate=candidate,
            account=self.account,
            symbol_info=self.symbol_info,
            active_positions=[],
            prevalidated=prevalidated,
        )

        self.assertIsNotNone(order)
        self.assertEqual(order.status, "REJECTED")
        self.mock_bridge.close_position.assert_called_with(88005)

    def test_duplicate_signal_prevention_via_transaction_manager(self):
        """
        Verify that duplicate signal execution is strictly prevented by TransactionManager.
        """
        self.tx_mgr.record_submission(
            signal_id="SIG_DUP_001",
            symbol="EURUSD",
            direction="BUY",
            volume=0.05,
            price=1.10000,
            sl=1.09500,
            tp=1.11000,
            request_id="REQ_DUP_001",
        )

        candidate = make_candidate("SIG_DUP_001", direction=OrderType.BUY)

        order = self.order_manager.execute_signal(
            candidate=candidate,
            account=self.account,
            symbol_info=self.symbol_info,
            active_positions=[],
        )

        self.assertIsNone(order)
        self.assertEqual(candidate.status, "REJECTED")
        self.assertIn("Duplicate signal execution prevented", candidate.rejection_reasons)
        self.mock_bridge.execute_trade.assert_not_called()

    def test_connection_state_callbacks(self):
        """
        Verify BridgeClient connection state callbacks trigger on loss and recovery.
        """
        bridge = BridgeClient()
        lost_calls = []
        restored_calls = []

        bridge.set_connection_callbacks(
            on_lost=lambda d: lost_calls.append(d),
            on_restored=lambda d: restored_calls.append(d),
        )

        # Simulate state transitions
        bridge._update_connection_state(True, "EA Connected")
        self.assertEqual(len(restored_calls), 1)
        self.assertIn("EA Connected", restored_calls[0])

        bridge._update_connection_state(False, "Socket Drop")
        self.assertEqual(len(lost_calls), 1)
        self.assertIn("Socket Drop", lost_calls[0])

        # No transition if state doesn't change
        bridge._update_connection_state(False, "Still disconnected")
        self.assertEqual(len(lost_calls), 1)

    def test_telegram_alert_dispatch_formatting(self):
        """
        Verify that TelegramAlertManager dispatches all verified lifecycle events cleanly.
        """
        mock_notifier = MagicMock()
        alert_mgr = TelegramAlertManager()
        alert_mgr.notifier = mock_notifier
        alert_mgr.enabled = True

        # 1. Order Accepted
        alert_mgr.alert_order_accepted("EURUSD", "BUY", 0.10, 1.10000, 88100, "REQ_123")
        mock_notifier.notify_order_accepted.assert_called_with(
            symbol="EURUSD",
            direction="BUY",
            volume=0.10,
            price=1.10000,
            ticket=88100,
            request_id="REQ_123"
        )

        # 2. Trade Executed (Broker Verified)
        alert_mgr.alert_trade_executed(
            ticket=88100,
            symbol="EURUSD",
            direction="BUY",
            volume=0.10,
            price=1.10020,
            sl=1.09500,
            tp=1.11000,
            execution_status="FILLED",
            account_number=123456
        )
        mock_notifier.notify_trade_executed.assert_called_with(
            symbol="EURUSD",
            direction="BUY",
            ticket=88100,
            price=1.10020,
            volume=0.10,
            sl=1.09500,
            tp=1.11000,
            execution_status="FILLED",
            account_number=123456,
            timestamp=None
        )

        # 3. Order Partially Filled
        alert_mgr.alert_order_partially_filled(
            symbol="EURUSD",
            direction="BUY",
            ticket=88100,
            filled_volume=0.04,
            remaining_volume=0.06,
            price=1.10020
        )
        mock_notifier.notify_order_partially_filled.assert_called_with(
            symbol="EURUSD",
            direction="BUY",
            ticket=88100,
            filled_volume=0.04,
            remaining_volume=0.06,
            price=1.10020
        )

        # 4. Execution Unconfirmed
        alert_mgr.alert_execution_unconfirmed(
            symbol="EURUSD",
            direction="BUY",
            ticket=88100,
            request_id="REQ_123",
            reason="No position verified at broker"
        )
        mock_notifier.notify_execution_unconfirmed.assert_called_with(
            symbol="EURUSD",
            direction="BUY",
            ticket=88100,
            request_id="REQ_123",
            reason="No position verified at broker"
        )

        # 5. Manual Trade Detected & Protected
        alert_mgr.alert_manual_trade_detected("XAUUSD", 99050, "BUY", 0.50, 2050.50, 0.0, 0.0)
        mock_notifier.notify_manual_trade_detected.assert_called_with(
            symbol="XAUUSD",
            ticket=99050,
            direction="BUY",
            volume=0.50,
            price=2050.50,
            sl=0.0,
            tp=0.0
        )

        alert_mgr.alert_manual_trade_protected("XAUUSD", 99050, 2045.00, 2065.00, "M15 OB Structure")
        mock_notifier.notify_manual_trade_protected.assert_called_with(
            symbol="XAUUSD",
            ticket=99050,
            sl=2045.00,
            tp=2065.00,
            reason="M15 OB Structure"
        )

        # 6. Connection Lost and Restored
        alert_mgr.alert_connection_lost("Socket error")
        mock_notifier.notify_bridge_status.assert_called_with("DISCONNECTED", "Socket error")

        alert_mgr.alert_connection_restored("Re-established")
        mock_notifier.notify_bridge_status.assert_called_with("CONNECTED", "Re-established")


if __name__ == "__main__":
    unittest.main()
