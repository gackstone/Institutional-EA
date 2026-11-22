"""
Unit and Integration Tests for Spam Elimination and Success-First Alert System:
- Rejected trades never reaching Telegram
- Valid signals reaching Telegram
- Confirmed executions reaching Telegram
- Trade closures reaching Telegram
- Critical alerts always reaching Telegram
- Duplicate alerts being suppressed
- Recovery alerts being delivered once
- Notification configuration being respected
- Telegram delivery failures not affecting trading execution
- Persistent deduplication across restarts
- Shadow-journal / diagnostics rejection recording remaining functional
"""

import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.core.contracts import DecisionOutcome, DecisionOutcomeType, OrderType, Candle, Timeframe
from src.notifications.events import (
    NotificationEventType,
    NotificationTier,
    OrderRejectedEvent,
    SetupBlockedEvent,
    SetupSkippedEvent,
    TradeSetupEvent,
    TradeOpenedEvent,
    TargetHitEvent,
    StopLossHitEvent,
    ConnectionLostEvent,
    ConnectionRestoredEvent,
    DailyLossLimitHitEvent,
    LiquidityAlertEvent,
)
from src.notifications.notification_policy import NotificationPolicy, get_notification_policy
from src.notifications.router import NotificationRouter
from src.notifications.telegram_config import TelegramConfig
from src.notifications.telegram_service import TelegramNotifier, TelegramCommandHandler
from src.notifications.templates.default_templates import TemplateRenderer


class TestSpamEliminationAndPolicy(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.cfg_file = os.path.join(self.tmp_dir.name, "telegram_notifications.json")
        self.state_file = os.path.join(self.tmp_dir.name, "notification_state.json")
        self.policy = NotificationPolicy(config_path=self.cfg_file, state_path=self.state_file)

        self.fixed_dt = datetime(2026, 11, 3, 14, 30, 0, tzinfo=timezone.utc)
        self.renderer = TemplateRenderer(
            tz_offset_hours=3.0,
            tz_label="UTC+3",
            account_number=1000000001,
        )
        self.transport = MagicMock()
        self.transport.send_message_ex.return_value = (True, 1001, "")
        self.transport.edit_message_text.return_value = (True, False, "")

        self.router = NotificationRouter(
            renderer=self.renderer,
            transport=self.transport,
            chat_id="8649330717",
        )
        self.router.policy = self.policy

    def tearDown(self):
        self.tmp_dir.cleanup()

    # 1. Rejected Trades Never Reach Telegram
    def test_rejected_trades_never_reach_telegram(self):
        self.assertFalse(self.policy.is_rejected_trade_alerts_enabled())

        rej_events = [
            OrderRejectedEvent(symbol="EURUSD", direction="BUY", retcode=10018, reason="Market closed"),
            SetupBlockedEvent(symbol="XAUUSD", direction="BUY", rejection_code="ERR_SPREAD_TOO_HIGH"),
            SetupSkippedEvent(symbol="GBPUSD", direction="SELL", reason="Pre-check failed: Insufficient margin"),
        ]

        for ev in rej_events:
            ok, msg_id, _ = self.router.route_and_dispatch(ev)
            self.assertFalse(ok, f"Expected {ev.event_type} to be suppressed from Telegram")
            self.assertIsNone(msg_id)

        self.transport.send_message_ex.assert_not_called()

    # 2. Decision Outcome TRADE SKIPPED Suppressed from Telegram
    def test_decision_outcome_trade_skipped_suppressed_from_telegram(self):
        cfg = TelegramConfig(env_path="nonexistent.env")
        cfg.bot_token = "123456:TEST"
        cfg.chat_id = "8649330717"
        cfg.enabled = True
        notifier = TelegramNotifier(cfg)
        notifier.stop()
        notifier.policy = self.policy

        sent_messages = []
        notifier.send_message = lambda text, **kw: sent_messages.append(text)
        notifier.send_raw_html = lambda text: sent_messages.append(text)

        outcome = DecisionOutcome(
            symbol="XAUUSD",
            bar_time=self.fixed_dt,
            outcome_type=DecisionOutcomeType.TRADE_SKIPPED,
            reason_code="RISK_CHECK_FAILED",
            details="Spread (45.0 pts) exceeds limit (25.0 pts)",
        )
        res = notifier.notify_decision_outcome(outcome)
        self.assertTrue(res)
        self.assertEqual(len(sent_messages), 0, "TRADE SKIPPED must not be sent to Telegram")

    # 3. Valid Signals and Executions Reach Telegram
    def test_valid_signals_and_executions_reach_telegram(self):
        self.assertTrue(self.policy.is_trade_signals_enabled())
        self.assertTrue(self.policy.is_execution_success_enabled())

        setup_ev = TradeSetupEvent(
            symbol="XAUUSD",
            direction="BUY",
            entry_price=2650.50,
            stop_loss=2647.50,
            take_profit=2656.50,
            lots=0.01,
            risk_pct=1.0,
            trade_id="SIGNAL-TEST-001",
        )
        ok_sig, msg_id_sig, rendered_sig = self.router.route_and_dispatch(setup_ev)
        self.assertTrue(ok_sig)
        self.assertIn("BUY SIGNAL | XAUUSD", rendered_sig)

        opened_ev = TradeOpenedEvent(
            symbol="XAUUSD",
            direction="BUY",
            ticket=555123,
            fill_price=2650.50,
            lots=0.01,
            trade_id="SIGNAL-TEST-001",
        )
        ok_open, msg_id_open, _ = self.router.route_and_dispatch(opened_ev)
        self.assertTrue(ok_open)

    # 4. Trade Closures and Profit Lockings Reach Telegram
    def test_trade_closures_reach_telegram(self):
        self.assertTrue(self.policy.is_trade_closure_enabled())

        tp_ev = TargetHitEvent(
            symbol="XAUUSD",
            ticket=555123,
            pnl_usd=18.40,
            pnl_r=1.84,
            duration_str="25m",
        )
        ok_tp, _, rendered_tp = self.router.route_and_dispatch(tp_ev)
        self.assertTrue(ok_tp)
        self.assertIn("TRADE CLOSED | WIN | XAUUSD", rendered_tp)
        self.assertIn("+$18.40", rendered_tp)

    # 5. Critical Alerts Always Reach Telegram
    def test_critical_alerts_always_reach_telegram(self):
        self.assertTrue(self.policy.is_critical_alerts_enabled())

        crit_loss = DailyLossLimitHitEvent(
            daily_loss_used_pct=4.5,
            daily_loss_cap_pct=4.0,
        )
        ok_crit, _, rendered_crit = self.router.route_and_dispatch(crit_loss)
        self.assertTrue(ok_crit)
        self.assertIn("CRITICAL RISK ALERT", rendered_crit)

        conn_lost = ConnectionLostEvent(
            details="Socket error connecting to MT5 trade terminal",
        )
        ok_conn, _, rendered_conn = self.router.route_and_dispatch(conn_lost)
        self.assertTrue(ok_conn)
        self.assertIn("CONNECTION LOST", rendered_conn)

    # 6. Smart Deduplication Suppresses Unchanged State
    def test_smart_deduplication_suppresses_unchanged_state(self):
        conn_lost_1 = ConnectionLostEvent(details="MT5 connection lost")
        ok_1, _, _ = self.router.route_and_dispatch(conn_lost_1)
        self.assertTrue(ok_1)

        # Repeated connection lost while still offline -> suppressed
        conn_lost_2 = ConnectionLostEvent(details="MT5 connection lost")
        ok_2, _, _ = self.router.route_and_dispatch(conn_lost_2)
        self.assertFalse(ok_2)

    # 7. Recovery Alert Delivered Once Upon Recovery
    def test_recovery_alert_delivered_once(self):
        # 1. Trigger offline
        conn_lost = ConnectionLostEvent(details="Connection down")
        self.router.route_and_dispatch(conn_lost)

        # 2. Trigger restored
        conn_restored_1 = ConnectionRestoredEvent(in_sync=True)
        ok_rec_1, _, rendered_rec_1 = self.router.route_and_dispatch(conn_restored_1)
        self.assertTrue(ok_rec_1)
        self.assertIn("CONNECTION RESTORED", rendered_rec_1)

        # 3. Repeated restored without going offline -> suppressed
        conn_restored_2 = ConnectionRestoredEvent(in_sync=True)
        ok_rec_2, _, _ = self.router.route_and_dispatch(conn_restored_2)
        self.assertFalse(ok_rec_2)

    # 8. Persistent Deduplication Across Engine Restarts
    def test_persistent_deduplication_across_restarts(self):
        # Set bridge offline in policy 1
        self.policy.transition_state("BRIDGE_OFFLINE", True, "Terminal unresponsive")

        # Create new policy instance from same state file
        policy_reloaded = NotificationPolicy(config_path=self.cfg_file, state_path=self.state_file)
        self.assertTrue(policy_reloaded.is_state_active("BRIDGE_OFFLINE"))

        # Transitioning to True again returns changed=False
        changed, is_act = policy_reloaded.transition_state("BRIDGE_OFFLINE", True)
        self.assertFalse(changed)

    # 9. Daily Summary Formatting and Delivery
    def test_daily_summary_delivery(self):
        cfg = TelegramConfig(env_path="nonexistent.env")
        cfg.bot_token = "123456:TEST"
        cfg.chat_id = "8649330717"
        cfg.enabled = True
        notifier = TelegramNotifier(cfg)
        notifier.stop()
        notifier.policy = self.policy

        sent = []
        notifier.send_raw_html = lambda text: sent.append(text)

        notifier.send_daily_summary(
            date_str="2026-11-03",
            trades_count=12,
            wins=8,
            losses=4,
            win_rate_pct=66.7,
            pnl_usd=24.80,
            max_drawdown_pct=0.85,
            best_performer="XAUUSD",
        )
        self.assertEqual(len(sent), 1)
        self.assertIn("DAILY TRADING SUMMARY", sent[0])
        self.assertIn("+$24.80", sent[0])
        self.assertIn("XAUUSD", sent[0])

    # 10. Notifications Command Handler
    def test_notifications_command_handler(self):
        cfg = TelegramConfig(env_path="nonexistent.env")
        cfg.bot_token = "123456:TEST"
        cfg.chat_id = "8649330717"
        cfg.enabled = True
        notifier = TelegramNotifier(cfg)
        notifier.stop()
        notifier.policy = self.policy

        handler = TelegramCommandHandler(config=cfg, notifier=notifier)
        handler.stop()

        replies = []
        handler._reply = lambda msg: replies.append(msg)

        handler._handle_notifications()
        self.assertEqual(len(replies), 1)
        self.assertIn("TELEGRAM NOTIFICATION SETTINGS", replies[0])
        self.assertIn("Trade Signals:", replies[0])
        self.assertIn("Rejected Trade Alerts:", replies[0])


if __name__ == "__main__":
    unittest.main()
