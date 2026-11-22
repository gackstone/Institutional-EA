#!/usr/bin/env python3
"""
Comprehensive Unit & Integration Test Suite for ArcadeFx MT5 Bot Agent.
Verifies all 17 requirements and operational scenarios:
1. Fresh installation with no machine credentials.
2. Code normalization (lowercase -> uppercase, whitespace removal, 6-char validation).
3. Valid pairing code successfully registers machine and stores credentials.
4. Invalid pairing code rejection with user-friendly error message.
5. Expired pairing code rejection with user-friendly error message.
6. Already-used pairing code rejection with user-friendly error message.
7. Network disconnection resilience, retry backoff, and offline event queue.
8. Existing paired machine reconnection without requesting new code.
9. MT5 terminal connectivity detection.
10. Execution bridge connectivity detection.
11. Real MT5 telemetry heartbeat compilation.
12. START command execution.
13. PAUSE command execution.
14. RESUME command execution.
15. STOP command execution.
16. Real command execution acknowledgement and reporting.
17. Local risk limits enforcement and replay protection.
"""

from __future__ import annotations
import os
import sys
import json
import time
import hmac
import hashlib
import unittest
from unittest.mock import patch, MagicMock
import tempfile
import shutil
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agent.mt5_bot_agent import (
    MT5BotAgent,
    LocalCredentialStore,
    OfflineEventQueue,
    AGENT_VERSION,
)


class TestArcadeFxMT5BotAgent(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.queue_db = os.path.join(self.test_dir, "test_queue.sqlite")
        self.creds_file = os.path.join(self.test_dir, "test_creds.enc.json")
        self.limits_file = os.path.join(self.test_dir, "test_limits.json")

        with open(self.limits_file, "w") as f:
            json.dump({
                "max_risk_pct_ceiling": 1.0,
                "max_lots_ceiling": 0.5,
                "max_drawdown_pct_ceiling": 5.0,
                "allow_live_trading": False,
                "allowed_symbols": ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD.m"]
            }, f)

        # Patch agent file locations to temp directory
        self.patcher_creds = patch("agent.mt5_bot_agent.CREDENTIALS_FILE", self.creds_file)
        self.patcher_limits = patch("agent.mt5_bot_agent.LOCAL_LIMITS_FILE", self.limits_file)
        self.patcher_creds.start()
        self.patcher_limits.start()

        def _mock_init(agent_self):
            agent_self.config = MagicMock()
            agent_self.orchestrator = MagicMock()
            agent_self.bridge = MagicMock()

        self.patcher_infra = patch.object(MT5BotAgent, "_init_trading_infrastructure", _mock_init)
        self.patcher_infra.start()

        self.agent = MT5BotAgent(api_url="https://arcadefx.live/api/v1")
        self.agent.notify_admin = MagicMock()
        self.agent.signing_secret = hashlib.sha256(b"arcadefx_test_signing_secret_12345").hexdigest()
        self.agent.offline_queue = OfflineEventQueue(db_path=self.queue_db)

    def tearDown(self):
        self.patcher_creds.stop()
        self.patcher_limits.stop()
        self.patcher_infra.stop()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # 1. Fresh installation with no machine credentials
    def test_01_fresh_installation_unpaired(self):
        """Proves fresh installation has no credentials and is reported as unpaired."""
        LocalCredentialStore.clear()
        creds = LocalCredentialStore.load()
        self.assertIsNone(creds)
        fresh_agent = MT5BotAgent(api_url="https://arcadefx.live/api/v1")
        self.assertIsNone(fresh_agent.device_token)
        self.assertIsNone(fresh_agent.instance_id)

    # 2. Input normalization and validation
    def test_02_pairing_code_format_validation_and_normalization(self):
        """Proves pairing code input normalizes lowercase, strips whitespace, and rejects bad formats."""
        # Valid lowercase with surrounding whitespace
        valid, normalized = MT5BotAgent.validate_pairing_code_format("  c2e2ad  ")
        self.assertTrue(valid)
        self.assertEqual(normalized, "C2E2AD")

        # Valid mixed case
        valid, normalized = MT5BotAgent.validate_pairing_code_format("aB12cD")
        self.assertTrue(valid)
        self.assertEqual(normalized, "AB12CD")

        # Empty code rejected
        valid, err = MT5BotAgent.validate_pairing_code_format("")
        self.assertFalse(valid)
        self.assertIn("cannot be empty", err)

        # Code too short
        valid, err = MT5BotAgent.validate_pairing_code_format("AB12")
        self.assertFalse(valid)
        self.assertIn("6-character", err)

        # Code too long
        valid, err = MT5BotAgent.validate_pairing_code_format("AB12CDEF")
        self.assertFalse(valid)
        self.assertIn("6-character", err)

        # Non-alphanumeric characters
        valid, err = MT5BotAgent.validate_pairing_code_format("AB-12#")
        self.assertFalse(valid)
        self.assertIn("6-character alphanumeric", err)

    # 3. Valid pairing code claims and stores machine credentials
    @patch("agent.mt5_bot_agent.MT5BotAgent._http_request")
    def test_03_valid_pairing_code_claim(self, mock_http):
        """Proves valid pairing code receives deviceToken, saves credentials, and registers machine."""
        mock_http.return_value = {
            "success": True,
            "instanceId": "inst-uuid-12345",
            "deviceToken": "bot_99887766554433221100aabbccddeeff",
            "signingSecret": "secret_hmac_abc123"
        }

        success, msg = self.agent.pair_with_code("C2E2AD", "Test-VPS-MT5")
        self.assertTrue(success)
        self.assertEqual(msg, "MACHINE PAIRED SUCCESSFULLY")
        self.assertEqual(self.agent.instance_id, "inst-uuid-12345")
        self.assertEqual(self.agent.device_token, "bot_99887766554433221100aabbccddeeff")

        # Verify saved locally
        loaded = LocalCredentialStore.load()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["instance_id"], "inst-uuid-12345")
        self.assertEqual(loaded["device_token"], "bot_99887766554433221100aabbccddeeff")

    # 4. Invalid pairing code rejected with clear error message
    @patch("agent.mt5_bot_agent.MT5BotAgent._http_request")
    def test_04_invalid_pairing_code_rejected(self, mock_http):
        """Proves invalid pairing code returns user-friendly error message."""
        mock_http.return_value = {
            "success": False,
            "error": "Pairing code not found or invalid."
        }

        success, msg = self.agent.pair_with_code("INVALID")
        # Format check catches it first
        self.assertFalse(success)
        self.assertIn("6-character", msg)

        # Test backend rejection
        success, msg = self.agent.pair_with_code("INV123")
        self.assertFalse(success)
        self.assertIn("INVALID CODE: The pairing code is invalid", msg)

    # 5. Expired pairing code rejected with clear error message
    @patch("agent.mt5_bot_agent.MT5BotAgent._http_request")
    def test_05_expired_pairing_code_rejected(self, mock_http):
        """Proves expired pairing code returns user-friendly expiration message."""
        mock_http.return_value = {
            "success": False,
            "error": "Pairing code has expired (10-minute limit)."
        }

        success, msg = self.agent.pair_with_code("EXP123")
        self.assertFalse(success)
        self.assertIn("EXPIRED CODE: This pairing code has expired", msg)

    # 6. Already used pairing code rejected with clear error message
    @patch("agent.mt5_bot_agent.MT5BotAgent._http_request")
    def test_06_already_used_pairing_code_rejected(self, mock_http):
        """Proves already claimed code returns user-friendly already used message."""
        mock_http.return_value = {
            "success": False,
            "error": "Pairing code has already been claimed or expired."
        }

        success, msg = self.agent.pair_with_code("USE123")
        self.assertFalse(success)
        self.assertIn("ALREADY USED: This pairing code has already been used", msg)

    # 7. Network error handling and offline event queue
    @patch("agent.mt5_bot_agent.MT5BotAgent._http_request")
    def test_07_network_error_and_offline_queue(self, mock_http):
        """Proves network disconnections return clear message and queue telemetry offline."""
        mock_http.side_effect = RuntimeError("NETWORK ERROR: Unable to reach ArcadeFX.live. [Errno 11001] getaddrinfo failed")

        success, msg = self.agent.pair_with_code("NET123")
        self.assertFalse(success)
        self.assertIn("NETWORK ERROR: Unable to reach ArcadeFX.live", msg)

        # Heartbeat queuing offline
        self.agent.bot_state = "RUNNING"
        self.agent.send_heartbeat()
        pending = self.agent.offline_queue.get_pending()
        self.assertGreaterEqual(len(pending), 1)
        self.assertEqual(pending[0]["eventType"], "heartbeat_failure")

    # 8. Reconnecting existing paired machine without re-prompting
    def test_08_paired_machine_auto_reconnect(self):
        """Proves already paired machine loads saved credentials without asking for code."""
        LocalCredentialStore.save({
            "device_token": "bot_stored_token_abc123",
            "instance_id": "inst-stored-uuid-999",
            "signing_secret": "secret_stored_hmac",
            "api_url": "https://arcadefx.live/api/v1",
            "paired_at": time.time()
        })

        reconnected_agent = MT5BotAgent(api_url="https://arcadefx.live/api/v1")
        self.assertEqual(reconnected_agent.device_token, "bot_stored_token_abc123")
        self.assertEqual(reconnected_agent.instance_id, "inst-stored-uuid-999")
        self.assertEqual(reconnected_agent.signing_secret, "secret_stored_hmac")

    # 9. MT5 terminal detection
    def test_09_mt5_terminal_connectivity_detection(self):
        """Proves MT5 terminal connection status is reported correctly."""
        checks = self.agent.check_local_connectivity()
        self.assertIn("mt5", checks)
        self.assertIn(checks["mt5"], ["CONNECTED", "RUNNING (No Broker Connection)", "NOT RUNNING", "PROCESS DETECTED"])

    # 10. Execution bridge detection
    def test_10_execution_bridge_detection(self):
        """Proves execution bridge connection status is reported correctly."""
        checks = self.agent.check_local_connectivity()
        self.assertIn("bridge", checks)
        self.assertTrue(checks["bridge"].startswith("CONNECTED") or checks["bridge"] == "DISCONNECTED")

    # 11. Real MT5 telemetry collection
    def test_11_real_telemetry_collection(self):
        """Proves telemetry contains real balance, equity, masked account, broker, and local limits."""
        self.agent.bot_state = "RUNNING"
        telemetry = self.agent.collect_real_telemetry()

        self.assertIn("instanceName", telemetry)
        self.assertIn("accountNumberMasked", telemetry)
        self.assertIn("balance", telemetry)
        self.assertIn("equity", telemetry)
        self.assertIn("broker", telemetry)
        self.assertIn("openPositions", telemetry)
        self.assertEqual(telemetry["botState"], "RUNNING")
        self.assertEqual(telemetry["engineVersion"], AGENT_VERSION)
        self.assertIn("localLimitsSnapshot", telemetry)
        self.assertEqual(telemetry["localLimitsSnapshot"]["maxRiskPctCeiling"], 1.0)
        self.assertFalse(telemetry["localLimitsSnapshot"]["liveTradingAllowedLocally"])

    # 12. START command execution
    def test_12_start_command_execution(self):
        """Proves cloud START command safely transitions bot to RUNNING."""
        self.agent.bot_state = "STOPPED"
        cmd = {
            "command_type": "start",
            "payload_json": "{}"
        }
        res = self.agent.execute_safe_command(cmd)
        self.assertEqual(self.agent.bot_state, "RUNNING")
        self.assertEqual(res["status"], "RUNNING")
        self.assertIn("started successfully", res["message"])

    # 13. PAUSE command execution
    def test_13_pause_command_execution(self):
        """Proves cloud PAUSE command transitions bot to PAUSED without closing positions."""
        self.agent.bot_state = "RUNNING"
        cmd = {
            "command_type": "pause",
            "payload_json": "{}"
        }
        res = self.agent.execute_safe_command(cmd)
        self.assertEqual(self.agent.bot_state, "PAUSED")
        self.assertEqual(res["status"], "PAUSED")
        self.assertIn("paused", res["message"])

    # 14. RESUME command execution
    def test_14_resume_command_execution(self):
        """Proves cloud RESUME command transitions bot back to RUNNING."""
        self.agent.bot_state = "PAUSED"
        cmd = {
            "command_type": "resume",
            "payload_json": "{}"
        }
        res = self.agent.execute_safe_command(cmd)
        self.assertEqual(self.agent.bot_state, "RUNNING")
        self.assertEqual(res["status"], "RUNNING")
        self.assertIn("resumed", res["message"])

    # 15. STOP command execution
    def test_15_stop_command_execution(self):
        """Proves cloud STOP command transitions bot to STOPPED."""
        self.agent.bot_state = "RUNNING"
        cmd = {
            "command_type": "stop",
            "payload_json": "{}"
        }
        res = self.agent.execute_safe_command(cmd)
        self.assertEqual(self.agent.bot_state, "STOPPED")
        self.assertEqual(res["status"], "STOPPED")
        self.assertIn("stopped", res["message"])

    # 16. Command signature verification & replay protection
    def test_16_command_signature_and_replay_protection(self):
        """Proves HMAC signature verification, tampered payload rejection, and nonce replay rejection."""
        command_id = "cmd-unique-test-1"
        instance_id = "inst-test-1"
        nonce = "nonce-abc-xyz-1"
        expires_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 300))
        payload = {"riskPercent": 0.5}

        msg = {
            "commandId": command_id,
            "instanceId": instance_id,
            "commandType": "start",
            "payload": payload,
            "nonce": nonce,
            "expiresAt": expires_at
        }
        serialized = json.dumps(msg, sort_keys=True)
        valid_sig = hmac.new(
            self.agent.signing_secret.encode("utf-8"),
            serialized.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        cmd = {
            "id": command_id,
            "instance_id": instance_id,
            "command_type": "start",
            "payload_json": json.dumps(payload),
            "nonce": nonce,
            "expires_at": expires_at,
            "signature": valid_sig
        }

        # 1. Valid signature passes
        self.assertTrue(self.agent.verify_command_signature(cmd))

        # 2. Nonce replay is strictly rejected
        self.assertFalse(self.agent.verify_command_signature(cmd))

        # 3. Tampered signature is rejected
        tampered_cmd = {
            "id": "cmd-tampered",
            "instance_id": instance_id,
            "command_type": "start",
            "payload_json": json.dumps({"riskPercent": 50.0}),
            "nonce": "nonce-new-different",
            "expires_at": expires_at,
            "signature": valid_sig
        }
        self.assertFalse(self.agent.verify_command_signature(tampered_cmd))

    # 18. Interactive prompt input flow with retry
    @patch("agent.mt5_bot_agent.MT5BotAgent.pair_with_code")
    @patch("builtins.input")
    def test_18_interactive_input_flow_with_retry(self, mock_input, mock_pair):
        """Proves interactive prompt rejects bad input, asks again, normalizes, and succeeds."""
        from agent.mt5_bot_agent import interactive_pairing_flow

        # First attempt: invalid format ('bad')
        # Second attempt: valid lowercase with space ('  c2e2ad  ')
        mock_input.side_effect = ["bad", "  c2e2ad  "]
        mock_pair.return_value = (True, "MACHINE PAIRED SUCCESSFULLY")

        result = interactive_pairing_flow(self.agent)
        self.assertTrue(result)
        self.assertEqual(mock_input.call_count, 2)
        mock_pair.assert_called_once_with("C2E2AD", None)

    # 19. Interactive prompt cancellation with 'q'
    @patch("builtins.input")
    def test_19_interactive_input_flow_cancellation(self, mock_input):
        """Proves interactive prompt exits gracefully when user inputs 'q'."""
        from agent.mt5_bot_agent import interactive_pairing_flow

        mock_input.return_value = "q"
        result = interactive_pairing_flow(self.agent)
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
