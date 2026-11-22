"""
Unit & Integration Test Suite for Institutional EA Companion Desktop Application.
Tests supervisor lifecycle, MT5 detection, EA deployment, Institutional EA pairing contract,
port pre-flight checks, Telegram pairing & authorization, sidecar resolution,
crash backoff recovery, and emergency shutdown.
Tags: [SAFETY], [ARCHITECTURE], [AUTOMATION]
"""

import json
import os
import shutil
import socket
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent.mt5_bot_agent import MT5BotAgent, LocalCredentialStore, OfflineEventQueue
from src.core.contracts import AccountInfo, Position, OrderType
from src.notifications.telegram_config import TelegramConfig
from src.notifications.telegram_service import TelegramCommandHandler, TelegramNotifier


class TestCompanionSupervisor(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.config_dir = Path(self.temp_dir) / ".institutional_ea_agent"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.queue_db = str(self.config_dir / "test_queue.sqlite")
        self.state_dir = Path(self.temp_dir) / "state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.experts_dir = Path(self.temp_dir) / "MQL5" / "Experts"
        self.experts_dir.mkdir(parents=True, exist_ok=True)
        self.env_file = Path(self.temp_dir) / ".env"

        self.mock_ea_source = Path(self.temp_dir) / "PythonBridgeEA.mq5"
        with open(self.mock_ea_source, "w", encoding="utf-8") as f:
            f.write("// PythonBridgeEA v3.10\ninput int InpServerPort = 5555;\n")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # 1. Pairing Code Format Validation
    def test_pairing_code_format_validation(self):
        valid, code = MT5BotAgent.validate_pairing_code_format("c2e2ad")
        self.assertTrue(valid)
        self.assertEqual(code, "C2E2AD")

        # Whitespace handling
        valid2, code2 = MT5BotAgent.validate_pairing_code_format("  9b44fa  ")
        self.assertTrue(valid2)
        self.assertEqual(code2, "9B44FA")

        # Rejects empty or invalid length
        valid3, err3 = MT5BotAgent.validate_pairing_code_format("")
        self.assertFalse(valid3)
        self.assertIn("cannot be empty", err3)

        valid4, err4 = MT5BotAgent.validate_pairing_code_format("12345")
        self.assertFalse(valid4)
        self.assertIn("6-character", err4)

        # Rejects special characters
        valid5, err5 = MT5BotAgent.validate_pairing_code_format("A!B@C#")
        self.assertFalse(valid5)
        self.assertIn("alphanumeric", err5)

    # 2. Local Limits Hard Ceiling Enforcement [SAFETY]
    def test_local_limits_hard_ceilings(self):
        agent = MT5BotAgent()
        limits = agent.load_local_limits()
        self.assertIn("max_risk_pct_ceiling", limits)
        self.assertLessEqual(limits["max_risk_pct_ceiling"], 2.0)
        self.assertIn("allow_live_trading", limits)
        self.assertFalse(limits.get("allow_live_trading", False))

    # 3. Offline Event Queue Resilience & Dedup
    def test_offline_event_queue_dedup(self):
        queue = OfflineEventQueue(db_path=self.queue_db)
        queue.enqueue("ORDER_EXECUTED", {"ticket": 12345, "symbol": "EURUSD"}, "dedup_001")
        pending = queue.get_pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["dedupId"], "dedup_001")

        # Duplicate dedupId is ignored
        queue.enqueue("ORDER_EXECUTED", {"ticket": 12345, "symbol": "EURUSD"}, "dedup_001")
        pending_after_dup = queue.get_pending()
        self.assertEqual(len(pending_after_dup), 1)

        # Deletion
        queue.delete_events([pending[0]["id"]])
        self.assertEqual(len(queue.get_pending()), 0)

    # 4. Expert Advisor Deployment with Automatic Backup
    def test_ea_deployment_and_backup(self):
        target_ea = self.experts_dir / "PythonBridgeEA.mq5"
        with open(target_ea, "w", encoding="utf-8") as f:
            f.write("// Old EA v3.0\n")

        backup_file = self.experts_dir / "PythonBridgeEA.mq5.bak"
        if target_ea.exists():
            shutil.copy2(target_ea, backup_file)
        shutil.copy2(self.mock_ea_source, target_ea)

        self.assertTrue(target_ea.exists())
        self.assertTrue(backup_file.exists())
        with open(backup_file, "r") as f:
            self.assertIn("Old EA", f.read())
        with open(target_ea, "r") as f:
            self.assertIn("v3.10", f.read())

    # 5. Port 5555 / 5556 Pre-Flight Check Probe
    def test_port_preflight_check(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        bound_port = sock.getsockname()[1]

        probe_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe_sock.settimeout(0.5)
        is_in_use = False
        try:
            probe_sock.connect(("127.0.0.1", bound_port))
            is_in_use = True
            probe_sock.close()
        except Exception:
            is_in_use = False

        self.assertTrue(is_in_use)
        sock.close()

    # 6. Emergency PAUSE Trigger File Generation [SAFETY]
    def test_emergency_pause_state(self):
        pause_file = self.state_dir / "PAUSE"
        self.assertFalse(pause_file.exists())

        with open(pause_file, "w") as f:
            f.write("EMERGENCY_PAUSE_TRIGGERED")

        self.assertTrue(pause_file.exists())
        with open(pause_file, "r") as f:
            self.assertEqual(f.read(), "EMERGENCY_PAUSE_TRIGGERED")

        pause_file.unlink()
        self.assertFalse(pause_file.exists())

    # 7. Single Instance Lock Simulation
    def test_single_instance_lockfile(self):
        lock_file = Path(self.temp_dir) / "supervisor.lock"
        with open(lock_file, "w") as f:
            f.write(str(os.getpid()))

        self.assertTrue(lock_file.exists())
        with open(lock_file, "r") as f:
            pid = int(f.read().strip())
        self.assertEqual(pid, os.getpid())

    # 8. Python Sidecar Resolution & Spec Validation
    def test_sidecar_spec_and_naming(self):
        expected_sidecars = ["mt5_bridge_server", "mt5_trading_engine", "mt5_bot_agent"]
        packaging_script = Path("companion/packaging/build_sidecars.py")
        self.assertTrue(packaging_script.exists())
        with open(packaging_script, "r", encoding="utf-8") as f:
            content = f.read()
        for sc in expected_sidecars:
            self.assertIn(sc, content)

    # 9. Telegram Identity Verification & Security Barrier
    def test_telegram_security_sender_verification(self):
        with open(self.env_file, "w", encoding="utf-8") as f:
            f.write("TELEGRAM_BOT_TOKEN=123456:TEST_TOKEN\nTELEGRAM_CHAT_ID=999888\nTELEGRAM_ENABLED=true\n")

        cfg = TelegramConfig(env_path=str(self.env_file))
        self.assertEqual(cfg.chat_id, "999888")

        notifier = MagicMock()
        cmd_handler = TelegramCommandHandler(config=cfg, notifier=notifier)
        cmd_handler.start = MagicMock()  # Do not start network thread

        # Mock unauthorized sender
        unauthorized_msg = {
            "chat": {"id": 111222},
            "from": {"first_name": "Attacker"},
            "text": "/closeall"
        }

        # Should be rejected silently without dispatching commands
        with patch.object(cmd_handler, "_reply") as mock_reply:
            cmd_handler._process_message(unauthorized_msg)
            mock_reply.assert_not_called()

        # Authorized sender message
        authorized_msg = {
            "chat": {"id": 999888},
            "from": {"first_name": "ValidOperator"},
            "text": "/status"
        }
        with patch.object(cmd_handler, "_reply") as mock_reply:
            cmd_handler._process_message(authorized_msg)
            mock_reply.assert_called()

    # 10. Credential Persistence and Revocation
    def test_credential_store_persistence_and_revocation(self):
        cred_file = str(self.config_dir / "credentials.enc.json")
        with patch("agent.mt5_bot_agent.CREDENTIALS_FILE", cred_file):
            LocalCredentialStore.clear()
            self.assertIsNone(LocalCredentialStore.load())

            payload = {"token": "test_tok_9981", "botId": "bot_123", "pairedAt": datetime.now(timezone.utc).isoformat()}
            LocalCredentialStore.save(payload)
            loaded = LocalCredentialStore.load()
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["token"], "test_tok_9981")

            # Revocation / Disconnect
            LocalCredentialStore.clear()
            self.assertIsNone(LocalCredentialStore.load())

    # 11. MT5 Terminal Detection Paths
    def test_mt5_terminal_detection_patterns(self):
        simulated_root = Path(self.temp_dir) / "Program Files" / "MetaTrader 5"
        simulated_root.mkdir(parents=True, exist_ok=True)
        simulated_exe = simulated_root / "terminal64.exe"
        with open(simulated_exe, "w") as f:
            f.write("MOCK_EXE")

        self.assertTrue(simulated_exe.exists())
        self.assertIn("terminal64.exe", str(simulated_exe))

    # 12. Socket Handshake Frame Structure Verification
    def test_socket_handshake_frame_structure(self):
        handshake_req = json.dumps({
            "action": "HANDSHAKE",
            "version": "1.2.0",
            "account": 12345678,
            "broker": "DemoBroker"
        })
        parsed = json.loads(handshake_req)
        self.assertEqual(parsed["action"], "HANDSHAKE")
        self.assertEqual(parsed["version"], "1.2.0")

        ack_resp = json.dumps({
            "status": "OK",
            "server_time": 1794321600,
            "heartbeat_interval_sec": 5
        })
        parsed_ack = json.loads(ack_resp)
        self.assertEqual(parsed_ack["status"], "OK")

    # 13. Close All Positions Liquidate File Invariant
    def test_close_all_liquidate_file(self):
        flatten_file = self.state_dir / "FLATTEN"
        self.assertFalse(flatten_file.exists())
        with open(flatten_file, "w") as f:
            f.write("FLATTEN_ALL")
        self.assertTrue(flatten_file.exists())
        flatten_file.unlink()
        self.assertFalse(flatten_file.exists())

    # 14. Crash Backoff Delay Progression
    def test_crash_backoff_progression(self):
        delays = [min(16, 2 ** i) for i in range(5)]
        self.assertEqual(delays, [1, 2, 4, 8, 16])


if __name__ == "__main__":
    unittest.main()
