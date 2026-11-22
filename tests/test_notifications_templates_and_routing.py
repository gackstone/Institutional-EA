"""
Comprehensive Unit Tests for the Structured Notification Layer:
- Golden-string / structural template verification for all 28 event types
- HTML escaping & 4096-char safe splitting
- 3-tier routing (LOUD, SILENT, ON_DEMAND)
- Transition-based alerting (OK -> WARNING -> CRITICAL -> RECOVERED), cooldown, repeat merging, escalation
- Quiet hours filtering
- Live trade card edit-in-place + reply_to_message_id threading + fallback on edit failure
- HTTP 429 rate-limit retry_after backoff
- TELEGRAM_CHAT_ID authorization on all commands and inline callback buttons
- Close All two-step confirmation (command and inline keyboard)
- Secret/token/account-number redaction & masking
- Single warm-up progress deduplication + ready notification
- /positions retry & friendly fallback + PersistentBridgeServer provider wiring
"""

import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.core.contracts import DecisionOutcome, DecisionOutcomeType
from src.notifications.events import (
    AlertState,
    NotificationEventType,
    NotificationTier,
    TradeSetupEvent,
    TradeOpenedEvent,
    BreakEvenMovedEvent,
    PartialClosedEvent,
    TargetHitEvent,
    StopLossHitEvent,
    OrderRejectedEvent,
    SetupSkippedEvent,
    SpreadWarningEvent,
    DailyLossWarningEvent,
    DailyLossLimitHitEvent,
    WarmupProgressEvent,
    mask_account_number,
    map_retcode_to_plain_english,
    sanitize_sensitive_text,
)
from src.notifications.router import NotificationRouter
from src.notifications.telegram_config import TelegramConfig
from src.notifications.telegram_service import TelegramCommandHandler, TelegramNotifier
from src.notifications.telegram_transport import TelegramTransport, escape_html
from src.notifications.templates.default_templates import (
    TemplateRenderer,
    build_sample_events,
    split_message_safely,
)


class TestNotificationTemplatesAndRouting(unittest.TestCase):
    def setUp(self):
        self.fixed_dt = datetime(2026, 11, 3, 14, 30, 0, tzinfo=timezone.utc)
        self.renderer = TemplateRenderer(
            tz_offset_hours=3.0,
            tz_label="UTC+3",
            account_number=1000000001,
        )

    # ------------------------------------------------------------------
    # 1. All 28 Event Templates & Golden Structure
    # ------------------------------------------------------------------
    def test_all_33_sample_event_templates_render_cleanly(self):
        samples = build_sample_events()
        self.assertEqual(len(samples), 33)
        seen_types = set()
        for evt in samples:
            seen_types.add(evt.event_type)
            rendered = self.renderer.render(evt)
            self.assertTrue(rendered.startswith("🧪 <b>[SAMPLE]</b> "))
            self.assertIn("2026-11-03 14:30:00 UTC", rendered)
            self.assertIn("17:30:00 UTC+3", rendered)
            self.assertIn("****0001", rendered)
            self.assertNotIn("1000000001", rendered)
            self.assertLessEqual(len(rendered), 4096)
            self.assertNotIn("Traceback", rendered)

        self.assertEqual(len(seen_types), len(NotificationEventType))

    def test_golden_snapshot_trade_setup_and_stop_loss(self):
        setup_evt = TradeSetupEvent(
            timestamp=self.fixed_dt,
            symbol="XAUUSD",
            direction="BUY",
            entry_price=2650.50,
            stop_loss=2645.50,
            take_profit=2662.50,
            sl_distance_pips=50.0,
            tp_distance_pips=120.0,
            distance_unit="pips",
            rr_ratio=2.40,
            lots=0.10,
            risk_usd=50.0,
            risk_pct=0.50,
            session="London / NY Overlap",
            htf_bias="BULLISH",
            reason="Confirmed BOS + Bullish FVG retest",
            confidence_score=88.0,
            digits=2,
        )
        text = self.renderer.render(setup_evt)
        self.assertIn("🟢 <b>BUY SIGNAL | XAUUSD</b>", text)
        self.assertIn("<b>Entry:</b> <code>2650.50</code>", text)
        self.assertIn("<b>SL:</b> <code>2645.50</code>", text)
        self.assertIn("<b>TP:</b> <code>2662.50</code>", text)
        self.assertIn("<b>R:R:</b> <code>1:2.4</code>", text)
        self.assertIn("<b>Lot:</b> <code>0.10</code> | <b>Risk:</b> <code>0.50%</code>", text)

        sl_evt = StopLossHitEvent(
            timestamp=self.fixed_dt,
            symbol="XAUUSD",
            direction="BUY",
            ticket=501024,
            close_price=2645.50,
            loss_usd=-50.0,
            loss_r=-1.0,
            duration_str="18m 12s",
            daily_loss_used_pct=1.20,
            daily_loss_cap_pct=4.00,
            digits=2,
        )
        sl_text = self.renderer.render(sl_evt)
        self.assertIn("🛑 <b>TRADE CLOSED | LOSS | XAUUSD</b>", sl_text)
        self.assertIn("-$50.00", sl_text)
        self.assertIn("-1.00R", sl_text)

    def test_plain_english_retcode_mapping(self):
        self.assertIn("Market is closed", map_retcode_to_plain_english(10018))
        self.assertIn("Insufficient free margin", map_retcode_to_plain_english(10019))
        evt = OrderRejectedEvent(
            timestamp=self.fixed_dt,
            symbol="EURUSD",
            direction="SELL",
            retcode=10018,
            bot_action="Will retry when session opens",
        )
        rendered = self.renderer.render(evt)
        self.assertIn("Market is closed", rendered)
        self.assertNotIn("10018", rendered)

    # ------------------------------------------------------------------
    # 2. HTML Escaping & 4096-char Splitting
    # ------------------------------------------------------------------
    def test_html_escaping_and_safe_4096_splitting(self):
        malicious = "<script>alert('xss & hack')</script>"
        escaped = escape_html(malicious)
        self.assertNotIn("<script>", escaped)
        self.assertIn("&lt;script&gt;", escaped)
        self.assertIn("&amp;", escaped)

        long_lines = [f"Line {i}: " + ("X" * 80) for i in range(100)]
        long_msg = "\n".join(long_lines)
        self.assertGreater(len(long_msg), 8000)
        chunks = split_message_safely(long_msg, max_chars=4096)
        self.assertGreaterEqual(len(chunks), 3)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 4096)

    # ------------------------------------------------------------------
    # 3. 3-Tier Routing & Transition Alerting & Cooldown/Repeat Merge
    # ------------------------------------------------------------------
    def test_three_tier_routing_loud_silent_ondemand(self):
        transport = MagicMock()
        transport.send_message_ex.return_value = (True, 101, "")
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = os.path.join(tmpdir, "notifications.json")
            router = NotificationRouter(
                renderer=self.renderer,
                transport=transport,
                chat_id="8649330717",
                config_path=cfg_path,
            )

            # 1. ON_DEMAND (SetupSkipped) -> never sent to transport
            skip_evt = SetupSkippedEvent(
                timestamp=self.fixed_dt,
                symbol="EURUSD",
                reason="Spread above cap",
            )
            self.assertEqual(skip_evt.get_tier(), NotificationTier.ON_DEMAND)
            ok_skip, _, _ = router.route_and_dispatch(skip_evt)
            self.assertFalse(ok_skip)
            transport.send_message_ex.assert_not_called()

            # 2. SILENT (SessionOpen) -> sent with disable_notification=True
            from src.notifications.events import SessionOpenEvent
            sess_evt = SessionOpenEvent(
                timestamp=self.fixed_dt,
                session_name="London",
                window_utc="06:00–12:00 UTC",
            )
            self.assertEqual(sess_evt.get_tier(), NotificationTier.SILENT)
            ok_sess, _, _ = router.route_and_dispatch(sess_evt)
            self.assertTrue(ok_sess)
            transport.send_message_ex.assert_called_once()
            self.assertTrue(transport.send_message_ex.call_args.kwargs.get("disable_notification"))

            # 3. LOUD (DailyLossLimitHit) -> sent with disable_notification=False
            transport.reset_mock()
            crit_evt = DailyLossLimitHitEvent(
                timestamp=self.fixed_dt,
                daily_loss_usd=-400.0,
                daily_loss_used_pct=4.0,
                daily_loss_cap_pct=4.0,
            )
            ok_crit, _, _ = router.route_and_dispatch(crit_evt)
            self.assertTrue(ok_crit)
            transport.send_message_ex.assert_called_once()
            self.assertFalse(transport.send_message_ex.call_args.kwargs.get("disable_notification"))

    def test_state_transition_cooldown_and_escalation(self):
        transport = MagicMock()
        transport.send_message_ex.return_value = (True, 202, "")
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = os.path.join(tmpdir, "notifications.json")
            router = NotificationRouter(
                renderer=self.renderer,
                transport=transport,
                chat_id="8649330717",
                config_path=cfg_path,
            )

            # First WARNING -> dispatched
            w1 = SpreadWarningEvent(
                timestamp=self.fixed_dt,
                symbol="XAUUSD",
                current_spread_pts=45.0,
                normal_spread_pts=18.0,
            )
            ok1, _, _ = router.route_and_dispatch(w1, now_ts=1000.0)
            self.assertTrue(ok1)
            self.assertEqual(transport.send_message_ex.call_count, 1)

            # Second identical WARNING within 600s cooldown -> suppressed & counted
            w2 = SpreadWarningEvent(
                timestamp=self.fixed_dt,
                symbol="XAUUSD",
                current_spread_pts=46.0,
                normal_spread_pts=18.0,
            )
            ok2, _, _ = router.route_and_dispatch(w2, now_ts=1100.0)
            self.assertFalse(ok2)
            self.assertEqual(router.suppressed_alerts_count, 1)

            # Direct state transition OK -> WARNING -> CRITICAL -> RECOVERED
            ok_c, repeats_c, eff_c = router.evaluate_state_transition(
                key="spread:XAUUSD",
                new_state=AlertState.CRITICAL,
                summary="80.0 pts",
                now_ts=1150.0,
            )
            self.assertTrue(ok_c)
            self.assertEqual(eff_c, AlertState.CRITICAL)

            ok_r, repeats_r, eff_r = router.evaluate_state_transition(
                key="spread:XAUUSD",
                new_state=AlertState.RECOVERED,
                summary="18.0 pts",
                now_ts=1200.0,
            )
            self.assertTrue(ok_r)
            self.assertEqual(eff_r, AlertState.RECOVERED)

    # ------------------------------------------------------------------
    # 4. Quiet Hours Filtering
    # ------------------------------------------------------------------
    def test_quiet_hours_silences_non_critical_allows_critical(self):
        transport = MagicMock()
        transport.send_message_ex.return_value = (True, 303, "")
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = os.path.join(tmpdir, "notifications.json")
            router = NotificationRouter(
                renderer=self.renderer,
                transport=transport,
                chat_id="8649330717",
                config_path=cfg_path,
            )
            router.set_quiet_for_hours(2.0)
            self.assertTrue(router.is_quiet_hours())

            # Non-critical warning is silenced during quiet hours
            warn_evt = DailyLossWarningEvent(
                timestamp=self.fixed_dt,
                daily_loss_usd=-300.0,
                daily_loss_used_pct=3.0,
                daily_loss_cap_pct=4.0,
                remaining_budget_usd=100.0,
            )
            ok_w, _, _ = router.route_and_dispatch(warn_evt)
            self.assertFalse(ok_w)
            transport.send_message_ex.assert_not_called()

            # Critical DailyLossLimitHit still fires during quiet hours
            crit_evt = DailyLossLimitHitEvent(
                timestamp=self.fixed_dt,
                daily_loss_usd=-400.0,
                daily_loss_used_pct=4.0,
                daily_loss_cap_pct=4.0,
            )
            ok_c, _, _ = router.route_and_dispatch(crit_evt)
            self.assertTrue(ok_c)
            transport.send_message_ex.assert_called_once()

    # ------------------------------------------------------------------
    # 5. Live Trade Card Edit-In-Place, Threading & Fallback
    # ------------------------------------------------------------------
    def test_live_trade_card_edit_in_place_and_fallback_when_deleted(self):
        transport = MagicMock()
        transport.send_message_ex.side_effect = [
            (True, 555, ""),
            (True, 556, ""),
            (True, 557, ""),
            (True, 558, ""),
            (True, 559, ""),
        ]
        transport.edit_message_text.return_value = (True, False, "")

        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = os.path.join(tmpdir, "notifications.json")
            router = NotificationRouter(
                renderer=self.renderer,
                transport=transport,
                chat_id="8649330717",
                config_path=cfg_path,
            )

            # Step 1: TradeSetup posts initial card (message_id=555)
            setup = TradeSetupEvent(
                timestamp=self.fixed_dt,
                symbol="XAUUSD",
                direction="BUY",
                entry_price=2650.0,
                stop_loss=2645.0,
                take_profit=2660.0,
                rr_ratio=2.0,
                lots=0.10,
                risk_usd=50.0,
                risk_pct=0.5,
                trade_id="PLAN-1",
            )
            router.route_and_dispatch(setup)
            self.assertEqual(router._trade_threads_by_id["PLAN-1"].card_message_id, 555)

            # Step 2: TradeOpened edits card 555 in place AND sends threaded reply
            opened = TradeOpenedEvent(
                timestamp=self.fixed_dt,
                symbol="XAUUSD",
                direction="BUY",
                ticket=9001,
                fill_price=2650.1,
                requested_price=2650.0,
                lots=0.10,
                stop_loss=2645.0,
                take_profit=2660.0,
                risk_usd=50.0,
                risk_pct=0.5,
                trade_id="PLAN-1",
            )
            router.route_and_dispatch(opened)
            transport.edit_message_text.assert_called_once()
            self.assertEqual(transport.edit_message_text.call_args.kwargs.get("message_id"), 555)
            self.assertEqual(router._trade_threads_by_ticket[9001].card_message_id, 555)

            # Step 3: Simulate user deleting card 555 -> edit_message_text returns (False, True, "message to edit not found")
            transport.edit_message_text.return_value = (False, True, "Bad Request: message to edit not found")
            be_evt = BreakEvenMovedEvent(
                timestamp=self.fixed_dt,
                symbol="XAUUSD",
                direction="BUY",
                ticket=9001,
                entry_price=2650.0,
                new_sl=2650.2,
                locked_r=0.05,
            )
            router.route_and_dispatch(be_evt)
            # Fallback must have posted a new card (message_id=557) and updated card_message_id
            self.assertEqual(router._trade_threads_by_ticket[9001].card_message_id, 557)

            # Step 4: TargetHit sends loud close message replying to setup_message_id=555
            transport.edit_message_text.return_value = (True, False, "")
            tp_evt = TargetHitEvent(
                timestamp=self.fixed_dt,
                symbol="XAUUSD",
                direction="BUY",
                ticket=9001,
                close_price=2660.0,
                pnl_usd=100.0,
                pnl_r=2.0,
                duration_str="25m",
            )
            router.route_and_dispatch(tp_evt)
            last_send_kwargs = transport.send_message_ex.call_args.kwargs
            self.assertEqual(last_send_kwargs.get("reply_to_message_id"), 555)
            self.assertFalse(last_send_kwargs.get("disable_notification"))

    # ------------------------------------------------------------------
    # 6. HTTP 429 Rate-Limit Retry Backoff
    # ------------------------------------------------------------------
    def test_http_429_rate_limit_backoff_in_transport(self):
        cfg = TelegramConfig(env_path="nonexistent.env")
        cfg.bot_token = "123456:TEST"
        cfg.chat_id = "8649330717"
        cfg.enabled = True
        transport = TelegramTransport(cfg)

        calls = []

        class FakeSSLSocket:
            def __init__(self, status_line: str, body: str):
                self._raw = (
                    f"{status_line}\r\n"
                    f"Content-Length: {len(body.encode('utf-8'))}\r\n"
                    f"Connection: close\r\n\r\n"
                    f"{body}"
                ).encode("utf-8")
                self._offset = 0

            def sendall(self, data):
                pass

            def recv(self, bufsize):
                if self._offset >= len(self._raw):
                    return b""
                chunk = self._raw[self._offset : self._offset + bufsize]
                self._offset += len(chunk)
                return chunk

            def close(self):
                pass

        def fake_open_ssl_socket(timeout=10.0):
            calls.append(1)
            if len(calls) == 1:
                return FakeSSLSocket(
                    "HTTP/1.1 429 Too Many Requests",
                    '{"ok": false, "error_code": 429, "parameters": {"retry_after": 0}}',
                )
            return FakeSSLSocket(
                "HTTP/1.1 200 OK",
                '{"ok": true, "result": {"message_id": 777}}',
            )

        with patch.object(transport, "_open_ssl_socket", side_effect=fake_open_ssl_socket):
            ok, msg_id, _ = transport.send_message_ex("8649330717", "Test 429 retry")
            self.assertTrue(ok)
            self.assertEqual(msg_id, 777)
            self.assertEqual(len(calls), 2)

    # ------------------------------------------------------------------
    # 7. Command & Inline Callback Authorization + CloseAll 2-Step
    # ------------------------------------------------------------------
    def test_inline_callback_authorization_and_closeall_two_step(self):
        cfg = TelegramConfig(env_path="nonexistent.env")
        cfg.bot_token = "123456:TEST"
        cfg.chat_id = "8649330717"
        cfg.enabled = True

        notifier = TelegramNotifier(cfg, account_number=1000000001)
        notifier.stop()

        mock_closeall = MagicMock(return_value=3)
        mock_pause = MagicMock(return_value=True)
        handler = TelegramCommandHandler(
            config=cfg,
            notifier=notifier,
            closeall_handler=mock_closeall,
            pause_handler=mock_pause,
        )
        handler.stop()
        handler.transport.answer_callback_query = MagicMock(return_value=True)
        handler._reply = MagicMock()
        handler._reply_with_markup = MagicMock()

        # 1. Unauthorized callback query from intruder -> blocked
        intruder_cb = {
            "id": "cb_1",
            "data": "cmd_closeall_confirm",
            "from": {"first_name": "Attacker"},
            "message": {"chat": {"id": "99999999"}},
        }
        handler._process_callback_query(intruder_cb)
        mock_closeall.assert_not_called()

        # 2. Authorized Close All step 1 (prompt) -> shows confirmation buttons, does not close yet
        auth_prompt_cb = {
            "id": "cb_2",
            "data": "cmd_closeall_prompt",
            "from": {"first_name": "Operator"},
            "message": {"chat": {"id": "8649330717"}},
        }
        handler._process_callback_query(auth_prompt_cb)
        mock_closeall.assert_not_called()
        handler._reply_with_markup.assert_called_once()
        self.assertIsNotNone(handler._pending_confirmation)

        # 3. Authorized Close All step 2 (confirm) -> executes closeall_handler
        auth_confirm_cb = {
            "id": "cb_3",
            "data": "cmd_closeall_confirm",
            "from": {"first_name": "Operator"},
            "message": {"chat": {"id": "8649330717"}},
        }
        handler._process_callback_query(auth_confirm_cb)
        mock_closeall.assert_called_once()
        self.assertIsNone(handler._pending_confirmation)

    # ------------------------------------------------------------------
    # 8. No Secrets / Tokens / Full Account Numbers
    # ------------------------------------------------------------------
    def test_no_secrets_tokens_or_full_account_numbers_in_messages(self):
        self.assertEqual(mask_account_number(1000000001), "****0001")
        fake_tok = "1234567890:" + "AAH" + ("x" * 28)
        raw_secret = f"Token {fake_tok} and login 1000000001"
        sanitized = sanitize_sensitive_text(raw_secret)
        self.assertNotIn(fake_tok, sanitized)
        self.assertNotIn("1000000001", sanitized)
        self.assertIn("[REDACTED_TOKEN]", sanitized)
        self.assertIn("****0001", sanitized)

    # ------------------------------------------------------------------
    # 9. Single Warm-Up Progress Message & Ready Notification (No Repeats)
    # ------------------------------------------------------------------
    def test_warmup_progress_deduplication_and_ready_transition(self):
        cfg = TelegramConfig(env_path="nonexistent.env")
        cfg.bot_token = "123456:TEST"
        cfg.chat_id = "8649330717"
        cfg.enabled = True
        notifier = TelegramNotifier(cfg)
        notifier.stop()
        notifier.policy._cfg['routine_status_alerts_enabled'] = True
        sent_messages = []
        notifier.send_message = lambda text, **kw: sent_messages.append(text)

        # Outcome 1: EURUSD have 0, required 20 -> sends 1st warmup progress
        o1 = DecisionOutcome(
            symbol="EURUSD",
            bar_time=self.fixed_dt,
            outcome_type=DecisionOutcomeType.NO_SETUP,
            details="Insufficient M15 candle history (have 0, required 20)",
        )
        notifier.notify_decision_outcome(o1)
        self.assertEqual(len(sent_messages), 1)
        self.assertIn("WARMING UP HISTORY", sent_messages[0])
        self.assertIn("0/20 bars", sent_messages[0])

        # Outcome 2: Next bar still have 0, required 20 -> NO repeat warmup message!
        o2 = DecisionOutcome(
            symbol="EURUSD",
            bar_time=self.fixed_dt.replace(minute=45),
            outcome_type=DecisionOutcomeType.NO_SETUP,
            details="Insufficient M15 candle history (have 0, required 20)",
        )
        notifier.notify_decision_outcome(o2)
        self.assertEqual(len(sent_messages), 1)

        # Outcome 3: EURUSD reaches 20/20 bars and evaluates normal NO_SETUP -> sends 1 READY message, suppresses NO_SETUP
        o3 = DecisionOutcome(
            symbol="EURUSD",
            bar_time=self.fixed_dt.replace(hour=15, minute=0),
            outcome_type=DecisionOutcomeType.NO_SETUP,
            details="No sweep or displacement on closed bar",
        )
        notifier.notify_decision_outcome(o3)
        self.assertEqual(len(sent_messages), 2)
        self.assertIn("HISTORY READY — EURUSD", sent_messages[1])

    # ------------------------------------------------------------------
    # 10. /positions Retry & Friendly Fallback + /health Suppressed Count
    # ------------------------------------------------------------------
    def test_positions_retry_fallback_and_health_command(self):
        cfg = TelegramConfig(env_path="nonexistent.env")
        cfg.bot_token = "123456:TEST"
        cfg.chat_id = "8649330717"
        cfg.enabled = True
        notifier = TelegramNotifier(cfg)
        notifier.stop()

        call_count = {"n": 0}

        def flaky_positions_provider():
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("Socket timeout")
            return [
                {
                    "ticket": 701,
                    "symbol": "XAUUSD",
                    "type": "BUY",
                    "volume": 0.10,
                    "open_price": 2650.0,
                    "sl": 2645.0,
                    "tp": 2660.0,
                    "profit": 35.50,
                    "initial_risk_amount": 50.0,
                }
            ]

        handler = TelegramCommandHandler(
            config=cfg,
            notifier=notifier,
            positions_provider=flaky_positions_provider,
            status_provider=lambda: {"bridge_connected": True, "state": "RUNNING"},
        )
        handler.stop()
        replies = []
        handler._reply = lambda msg: replies.append(msg)

        handler._handle_positions()
        self.assertEqual(len(replies), 2)
        self.assertIn("retrying", replies[0])
        self.assertIn("#701", replies[1])
        self.assertIn("35.50", replies[1])

        # Verify /status does NOT contain Suppressed Alert Duplicates, and /health DOES
        replies.clear()
        handler._handle_status()
        self.assertNotIn("Suppressed Alert Duplicates", replies[0])

        replies.clear()
        handler._handle_health()
        self.assertIn("Suppressed Alert Duplicates", replies[0])



    def test_message_size_constraint_and_html_escaping_on_new_templates(self):
        from src.notifications.events import SetupBlockedEvent, SetupDetectedEvent
        malicious_input = "<script>alert('xss & attack')</script>"
        evt_blocked = SetupBlockedEvent(
            timestamp=self.fixed_dt,
            symbol="XAUUSD",
            rejection_code=malicious_input,
            filter_name=malicious_input,
            metric_value=malicious_input,
        )
        msg = self.renderer.render(evt_blocked)
        self.assertLessEqual(len(msg), 4096)
        self.assertNotIn("<script>", msg)
        self.assertIn("&lt;script&gt;", msg)
        self.assertIn("&amp;", msg)

        # Huge confluences list test
        huge_confluences = [f"Confluence #{i}: " + ("A" * 100) for i in range(50)]
        evt_detected = SetupDetectedEvent(
            timestamp=self.fixed_dt,
            symbol="XAUUSD",
            confluences=huge_confluences,
        )
        msg_det = self.renderer.render(evt_detected)
        self.assertNotIn("<script>", msg_det)

    def test_new_events_tier_prioritization_and_deduplication(self):
        from src.notifications.events import (
            SetupBlockedEvent,
            SetupDetectedEvent,
            LiquidityAlertEvent,
            BotStatusEvent,
            CalibrationAlertEvent,
            NotificationTier,
        )
        evt_blocked = SetupBlockedEvent()
        self.assertEqual(evt_blocked.get_tier(), NotificationTier.ON_DEMAND)

        evt_detected = SetupDetectedEvent()
        self.assertEqual(evt_detected.get_tier(), NotificationTier.SILENT)

        evt_liq = LiquidityAlertEvent()
        self.assertEqual(evt_liq.get_tier(), NotificationTier.SILENT)

        evt_status = BotStatusEvent()
        self.assertEqual(evt_status.get_tier(), NotificationTier.SILENT)

        evt_calib = CalibrationAlertEvent()
        self.assertEqual(evt_calib.get_tier(), NotificationTier.SILENT)

    def test_delivery_failure_non_blocking_handling(self):
        cfg = TelegramConfig(env_path="nonexistent.env")
        cfg.bot_token = "123456:TEST"
        cfg.chat_id = "8649330717"
        cfg.enabled = True
        notifier = TelegramNotifier(cfg)
        notifier.stop()  # Keep worker stopped to test queue behavior

        # Verify queue accepts messages without throwing exceptions
        notifier.send_message("Test message")
        self.assertEqual(notifier._msg_queue.qsize(), 1)

        from src.notifications.events import SetupDetectedEvent
        evt = SetupDetectedEvent()
        transport = MagicMock()
        transport.send_message_ex.return_value = (False, None, "Connection reset by peer")
        router = NotificationRouter(
            renderer=self.renderer,
            transport=transport,
            chat_id="8649330717",
        )
        dispatched, msg_id, rendered = router.route_and_dispatch(evt)
        transport.send_message_ex.assert_called_once()
        self.assertTrue(dispatched)
        self.assertIn("SETUP DETECTED", rendered)


class TestNewNotificationTemplates(unittest.TestCase):
    def setUp(self):
        self.fixed_dt = datetime(2026, 11, 3, 14, 30, 0, tzinfo=timezone.utc)
        self.renderer = TemplateRenderer(
            tz_offset_hours=3.0,
            tz_label="UTC+3",
            account_number=1000000001,
        )

    def test_trade_signal_template(self):
        evt = TradeSetupEvent(
            timestamp=self.fixed_dt,
            symbol="XAUUSD",
            direction="BUY",
            entry_price=2650.50,
            stop_loss=2647.50,
            take_profit=2656.50,
            rr_ratio=2.0,
            lots=0.01,
            risk_pct=1.0,
            reason="ICT FVG + OB",
            htf_bias="Bullish",
            confidence_score=85.0,
        )
        msg = self.renderer.render(evt)
        self.assertIn("🟢 <b>BUY SIGNAL | XAUUSD</b>", msg)
        self.assertIn("<b>Entry:</b> <code>2650.50</code>", msg)
        self.assertIn("<b>SL:</b> <code>2647.50</code>", msg)
        self.assertIn("<b>TP:</b> <code>2656.50</code>", msg)
        self.assertIn("<b>R:R:</b> <code>1:2.0</code>", msg)
        self.assertIn("<b>Lot:</b> <code>0.01</code> | <b>Risk:</b> <code>1.00%</code>", msg)
        self.assertIn("<b>Setup:</b> ICT FVG + OB", msg)
        self.assertIn("<b>Bias:</b> Bullish", msg)
        self.assertIn("<b>Confidence:</b> <code>85%</code>", msg)
        self.assertLessEqual(len(msg), 4096)

    def test_trade_executed_template(self):
        evt = TradeOpenedEvent(
            timestamp=self.fixed_dt,
            symbol="XAUUSD",
            direction="BUY",
            ticket=123456,
            fill_price=2650.50,
            lots=0.01,
            stop_loss=2647.50,
            take_profit=2656.50,
            slippage_points=0.3,
        )
        msg = self.renderer.render(evt)
        self.assertIn("🔵 <b>TRADE EXECUTED | BUY XAUUSD</b>", msg)
        self.assertIn("<b>Ticket:</b> <code>#123456</code>", msg)
        self.assertIn("<b>Price:</b> <code>2650.50</code>", msg)
        self.assertIn("<b>Lot:</b> <code>0.01</code>", msg)
        self.assertIn("<b>SL:</b> <code>2647.50</code> | <b>TP:</b> <code>2656.50</code>", msg)
        self.assertIn("<b>Execution:</b> OK (Deviation: <code>0.3 pts</code>)", msg)
        self.assertLessEqual(len(msg), 4096)

    def test_setup_detected_template(self):
        from src.notifications.events import SetupDetectedEvent
        evt = SetupDetectedEvent(
            timestamp=self.fixed_dt,
            symbol="XAUUSD",
            direction="Bullish",
            timeframe="M15",
            setup_type="ICT FVG + OB",
            confluences=["H1 Liquidity Sweep", "Displacement"],
        )
        msg = self.renderer.render(evt)
        self.assertIn("🟡 <b>SETUP DETECTED | XAUUSD</b>", msg)
        self.assertIn("<b>Bias:</b> Bullish | <b>Timeframe:</b> M15", msg)
        self.assertIn("<b>Model:</b> ICT FVG + OB", msg)
        self.assertIn("<b>Confluence:</b> H1 Liquidity Sweep + Displacement", msg)
        self.assertIn("<b>Status:</b> Monitoring for Confirmation", msg)

    def test_setup_blocked_template(self):
        from src.notifications.events import SetupBlockedEvent
        evt = SetupBlockedEvent(
            timestamp=self.fixed_dt,
            symbol="XAUUSD",
            rejection_code="ERR_SPREAD_TOO_HIGH",
            filter_name="Liquidity Guard",
            metric_value="4.2 pips > 2.5 pips max",
        )
        msg = self.renderer.render(evt)
        self.assertIn("🔴 <b>SETUP BLOCKED | XAUUSD</b>", msg)
        self.assertIn("<b>Reason:</b> Spread exceeds maximum threshold", msg)
        self.assertIn("<b>Detail:</b> 4.2 pips &gt; 2.5 pips max", msg)
        self.assertIn("<b>Filter:</b> Liquidity Guard", msg)

    def test_critical_risk_alert_template(self):
        evt = DailyLossLimitHitEvent(
            timestamp=self.fixed_dt,
            daily_loss_used_pct=2.8,
            daily_loss_cap_pct=3.0,
        )
        msg = self.renderer.render(evt)
        self.assertIn("🚨 <b>CRITICAL RISK ALERT</b>", msg)
        self.assertIn("<b>Equity Loss:</b> <code>2.80%</code>", msg)
        self.assertIn("<b>Daily Limit:</b> <code>3.00%</code>", msg)
        self.assertIn("<b>Action:</b> Trading Paused", msg)

    def test_warning_template(self):
        evt = SpreadWarningEvent(
            timestamp=self.fixed_dt,
            symbol="XAUUSD",
            current_spread_pts=24.0,
            normal_spread_pts=20.0,
        )
        msg = self.renderer.render(evt)
        self.assertIn("⚠️ <b>WARNING | XAUUSD</b>", msg)
        self.assertIn("High Spread", msg)
        self.assertIn("Trading paused for XAUUSD", msg)

    def test_liquidity_alert_template(self):
        from src.notifications.events import LiquidityAlertEvent
        evt = LiquidityAlertEvent(
            timestamp=self.fixed_dt,
            symbol="XAUUSD",
            state="NORMAL",
            spread_pts=24.0,
            spread_pct=1.2,
            action_taken="Trading active",
            details="Markets healthy. Trading active.",
        )
        msg = self.renderer.render(evt)
        self.assertIn("🔵 <b>MARKET INFO | XAUUSD</b>", msg)
        self.assertIn("Liquidity:</b> <code>NORMAL</code> ✅", msg)
        self.assertIn("Markets healthy. Trading active.", msg)

    def test_trade_closed_win_template(self):
        evt = TargetHitEvent(
            timestamp=self.fixed_dt,
            symbol="XAUUSD",
            ticket=123456,
            pnl_usd=18.40,
            pnl_r=1.84,
            duration_str="42m",
        )
        msg = self.renderer.render(evt)
        self.assertIn("🏆 <b>TRADE CLOSED | WIN | XAUUSD</b>", msg)
        self.assertIn("<b>Ticket:</b> <code>#123456</code>", msg)
        self.assertIn("+$18.40", msg)
        self.assertIn("+1.84R", msg)
        self.assertIn("Profit Locked</b> ✅", msg)

    def test_bot_status_template(self):
        from src.notifications.events import BotStatusEvent
        evt = BotStatusEvent(
            timestamp=self.fixed_dt,
            state="Active",
            uptime="24h 12m",
            open_positions=1,
            daily_pnl=125.40,
            daily_pnl_pct=1.25,
            current_drawdown_pct=0.45,
            active_session="London",
            symbols_monitored=["XAUUSD", "EURUSD"],
        )
        msg = self.renderer.render(evt)
        self.assertIn("🔄 <b>BOT STATUS | ACTIVE</b>", msg)
        self.assertIn("24h 12m", msg)
        self.assertIn("+$125.40", msg)
        self.assertIn("+1.25%", msg)
        self.assertIn("0.45%", msg)
        self.assertIn("XAUUSD, EURUSD", msg)

    def test_calibration_update_template(self):
        from src.notifications.events import CalibrationAlertEvent
        evt = CalibrationAlertEvent(
            timestamp=self.fixed_dt,
            param_name="Risk Per Trade",
            old_value="1.0%",
            new_value="0.75%",
            reason="Challenger Model CH-042 Superiority",
            challenger_id="CH-042",
            win_rate=68.5,
            profit_factor=2.10,
        )
        msg = self.renderer.render(evt)
        self.assertIn("🧠 <b>CALIBRATION UPDATE</b>", msg)
        self.assertIn("Risk Per Trade", msg)
        self.assertIn("1.0% ➔ 0.75%", msg)
        self.assertIn("CH-042", msg)
        self.assertIn("68.5%", msg)
        self.assertIn("2.10", msg)


if __name__ == "__main__":
    unittest.main()
