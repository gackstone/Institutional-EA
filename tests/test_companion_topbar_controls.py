"""Tests for Part 2 Top Bar Controls in Control Service (mock MT5 & mock engine)."""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from companion.database.repository import CompanionRepository
from companion.service.configuration.config_service import ConfigurationService
from companion.service.events.event_bus import EventBus
from companion.service.mt5.sync_service import MT5SyncService
from companion.service.orchestration.engine_controller import EngineController
from src.risk.portfolio_risk import PortfolioRiskEngine


class FakeMT5:
    def __init__(self, trade_mode: int = 0, positions=None):
        self.trade_mode = trade_mode  # 0 = DEMO, 2 = REAL
        self.initialized = False
        self._positions = list(positions or [])

    def initialize(self, path=None, timeout=5000):
        self.initialized = True
        return True

    def shutdown(self):
        self.initialized = False
        return True

    def terminal_info(self):
        return SimpleNamespace(connected=True, trade_allowed=True) if self.initialized else None

    def account_info(self):
        if not self.initialized:
            return None
        return SimpleNamespace(
            login=50123456,
            balance=10000.0,
            equity=10000.0,
            margin=0.0,
            margin_free=10000.0,
            margin_level=0.0,
            currency="USD",
            leverage=500,
            trade_mode=self.trade_mode,
            margin_mode=2,
            company="JustMarkets-Demo" if self.trade_mode == 0 else "JustMarkets-Live",
        )

    def positions_get(self):
        return list(self._positions)

    def orders_get(self):
        return []

    def symbols_get(self):
        return []

    def symbol_info(self, sym):
        return None

    def symbol_info_tick(self, sym):
        return None


class FakeBridge:
    def __init__(self, fake_mt5: FakeMT5, close_succeeds: bool = True):
        self._connected = True
        self.fake_mt5 = fake_mt5
        self.close_succeeds = close_succeeds

    def is_connected(self):
        return self._connected

    def connect(self):
        self._connected = True
        return True

    def disconnect(self):
        self._connected = False

    def get_account(self):
        return None

    def get_positions(self):
        return []

    def send_request(self, payload):
        return {"status": "SUCCESS", "data": []}

    def close_order(self, ticket: int):
        if self.close_succeeds:
            self.fake_mt5._positions = [p for p in self.fake_mt5._positions if p.ticket != ticket]
            return {"status": "SUCCESS", "ticket": ticket}
        return {"status": "ERROR", "message": "Broker rejected close"}


class TestTopBarControlsService(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "config").mkdir(parents=True, exist_ok=True)
        (self.root / "state").mkdir(parents=True, exist_ok=True)
        self.repo = CompanionRepository(self.root / "test.db")
        self.events = EventBus()
        self.cfg = ConfigurationService(self.root / "config", self.repo)
        self.risk = PortfolioRiskEngine()

    def tearDown(self):
        self.tmp.cleanup()

    def test_connect_refuses_non_demo_account(self):
        real_mt5 = FakeMT5(trade_mode=2)  # REAL
        sync = MT5SyncService(self.repo, self.events, mt5_module=real_mt5)
        ok = sync.connect()
        self.assertFalse(ok)
        self.assertEqual(sync.connection_status, "DISCONNECTED")
        self.assertIn("DEMO Lock", sync.last_error or "")

    def test_connect_demo_and_disconnect_sets_manual_flag(self):
        demo_mt5 = FakeMT5(trade_mode=0)
        sync = MT5SyncService(self.repo, self.events, mt5_module=demo_mt5)
        self.assertTrue(sync.connect())
        self.assertEqual(sync.connection_status, "CONNECTED")
        self.assertFalse(sync.is_manually_disconnected())

        snap = sync.disconnect()
        self.assertEqual(snap["connection_status"], "DISCONNECTED")
        self.assertTrue(sync.is_manually_disconnected())

    def test_start_engine_blocked_when_mt5_disconnected(self):
        demo_mt5 = FakeMT5(trade_mode=0)
        sync = MT5SyncService(self.repo, self.events, mt5_module=demo_mt5)
        ctrl = EngineController(self.root, self.repo, self.events, self.cfg, sync, self.risk)
        res = ctrl.start_engine()
        self.assertFalse(res["success"])
        self.assertIn("Connect MT5 first", res["message"])

    def test_status_exposes_canonical_fields_and_pause_resume_lifecycle(self):
        demo_mt5 = FakeMT5(trade_mode=0)
        sync = MT5SyncService(self.repo, self.events, mt5_module=demo_mt5)
        ctrl = EngineController(self.root, self.repo, self.events, self.cfg, sync, self.risk)
        st = ctrl.get_status()
        self.assertIn("engine_state", st)
        self.assertIn("stop_flag_active", st)
        self.assertIn("pause_flag_active", st)
        self.assertTrue(st["live_trading_locked"])

        p = ctrl.pause_entries()
        self.assertTrue(p["success"])
        self.assertTrue(ctrl.get_status()["pause_flag_active"])

        r = ctrl.resume_entries()
        self.assertTrue(r["success"])
        self.assertFalse(ctrl.get_status()["pause_flag_active"])

    def test_close_all_reconciles_with_mt5_success_and_failure(self):
        pos = SimpleNamespace(
            ticket=9001,
            symbol="XAUUSD.m",
            type=0,
            volume=0.02,
            price_open=2650.0,
            price_current=2655.0,
            sl=2640.0,
            tp=2670.0,
            profit=10.0,
            commission=0.0,
            swap=0.0,
            magic=100101,
            comment="BOT",
            time=1760000000,
        )
        # Success path: position disappears on reconciliation
        mt5_ok = FakeMT5(trade_mode=0, positions=[pos])
        bridge_ok = FakeBridge(mt5_ok, close_succeeds=True)
        sync_ok = MT5SyncService(self.repo, self.events, mt5_module=mt5_ok, bridge_client=bridge_ok)
        sync_ok.connect()
        sync_ok.sync_all()
        self.assertEqual(len(sync_ok.positions), 1)
        self.assertEqual(sync_ok.positions[0]["sl"], 2640.0)
        self.assertEqual(sync_ok.positions[0]["tp"], 2670.0)
        self.assertEqual(sync_ok.positions[0]["open_timestamp"], 1760000000)

        ctrl_ok = EngineController(self.root, self.repo, self.events, self.cfg, sync_ok, self.risk)
        res_ok = ctrl_ok.close_all_bot_positions(confirmed=True)
        self.assertTrue(res_ok["success"])
        self.assertTrue(res_ok["reconciled"])
        self.assertEqual(res_ok["remaining_bot_positions"], 0)

        # Failure path: position still remains after reconciliation -> success=False
        mt5_fail = FakeMT5(trade_mode=0, positions=[pos])
        bridge_fail = FakeBridge(mt5_fail, close_succeeds=False)
        sync_fail = MT5SyncService(self.repo, self.events, mt5_module=mt5_fail, bridge_client=bridge_fail)
        sync_fail.connect()
        sync_fail.sync_all()
        ctrl_fail = EngineController(self.root, self.repo, self.events, self.cfg, sync_fail, self.risk)
        res_fail = ctrl_fail.close_all_bot_positions(confirmed=True)
        self.assertFalse(res_fail["success"])
        self.assertTrue(res_fail["reconciled"])
        self.assertEqual(res_fail["remaining_bot_positions"], 1)

    def test_start_pause_resume_stop_state_machine_and_packaged_sidecar_resolution(self):
        demo_mt5 = FakeMT5(trade_mode=0)
        sync = MT5SyncService(self.repo, self.events, mt5_module=demo_mt5)
        sync.connect()
        sync.sync_all()

        # 1. Create a fake long-lived scripts/start_bot.py to test real process spawn -> pause -> resume -> stop
        scripts_dir = self.root / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        fake_bot = scripts_dir / "start_bot.py"
        fake_bot.write_text(
            "import os, pathlib, time, sys\n"
            "print('[INFO] Fake engine booted')\n"
            "sys.stdout.flush()\n"
            "sf = pathlib.Path(os.environ.get('MT5_DATA_DIR', '.')) / 'state' / 'engine_stop.flag'\n"
            "for _ in range(100):\n"
            "    if sf.exists(): break\n"
            "    time.sleep(0.05)\n",
            encoding="utf-8",
        )

        ctrl = EngineController(
            self.root,
            self.repo,
            self.events,
            self.cfg,
            sync,
            python_executable=sys.executable,
            data_dir=self.root,
        )
        try:
            start_res = ctrl.start_engine(dry_run=True)
            self.assertTrue(start_res["success"], start_res)
            self.assertEqual(start_res["state"], "RUNNING")
            self.assertIsNotNone(start_res.get("pid"))

            # Idempotent second start adopts the running engine PID without spawning a duplicate
            second_start = ctrl.start_engine(dry_run=True)
            self.assertTrue(second_start["success"])
            self.assertTrue(second_start.get("adopted"))
            self.assertEqual(second_start["pid"], start_res["pid"])

            # Pause transitions state to PAUSED while engine remains running
            pause_res = ctrl.pause_entries()
            self.assertTrue(pause_res["success"])
            self.assertEqual(pause_res["state"], "PAUSED")
            self.assertEqual(ctrl.get_status()["engine_state"], "PAUSED")

            # Resume transitions state back to RUNNING
            resume_res = ctrl.resume_entries()
            self.assertTrue(resume_res["success"])
            self.assertEqual(resume_res["state"], "RUNNING")
            self.assertEqual(ctrl.get_status()["engine_state"], "RUNNING")

            # Stop terminates the engine and transitions state to STOPPED
            stop_res = ctrl.stop_engine()
            self.assertTrue(stop_res["success"])
            self.assertEqual(stop_res["state"], "STOPPED")
            self.assertEqual(ctrl.get_status()["engine_state"], "STOPPED")
        finally:
            ctrl.stop_engine()

    def test_start_engine_detects_early_crash_and_sets_error_state(self):
        demo_mt5 = FakeMT5(trade_mode=0)
        sync = MT5SyncService(self.repo, self.events, mt5_module=demo_mt5)
        sync.connect()
        sync.sync_all()

        scripts_dir = self.root / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        fake_bot = scripts_dir / "start_bot.py"
        fake_bot.write_text(
            "import sys\nprint('[ERROR] Simulated startup crash')\nsys.stdout.flush()\nsys.exit(2)\n",
            encoding="utf-8",
        )

        ctrl = EngineController(
            self.root,
            self.repo,
            self.events,
            self.cfg,
            sync,
            python_executable=sys.executable,
            data_dir=self.root,
        )
        res = ctrl.start_engine(dry_run=True)
        self.assertFalse(res["success"])
        self.assertEqual(res["state"], "ERROR")
        self.assertEqual(ctrl.get_status()["engine_state"], "ERROR")
        self.assertIsNotNone(ctrl.get_status()["last_execution_error"])


if __name__ == "__main__":
    unittest.main()
