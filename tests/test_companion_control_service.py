"""
Comprehensive test suite for the Institutional EA Companion Local Control Service,
SQLite persistence, security/auth, config versioning, MT5 sync & reconciliation,
engine lifecycle, allowlisted PowerShell operations, and HTTP Control API.
"""

from __future__ import annotations

import json
import shutil
import threading
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest

from companion.database import CompanionRepository, init_database
from companion.service.api.server import build_control_server
from companion.service.configuration.config_service import (
    ConfigurationService,
    ConfigurationValidationError,
)
from companion.service.events.event_bus import EventBus
from companion.service.mt5.sync_service import MT5SyncService
from companion.service.operations.ps_runner import OperationsRunner
from companion.service.orchestration.engine_controller import EngineController
from companion.service.security.auth import LocalAuthManager, redact_secrets


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _copy_config_dir(tmp_path: Path) -> Path:
    cfg_dst = tmp_path / "config"
    shutil.copytree(PROJECT_ROOT / "config", cfg_dst)
    return cfg_dst


def _no_bridge():
    return SimpleNamespace(connect=lambda: False, is_connected=lambda: False)


class _FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_REAL = 2
    ACCOUNT_MARGIN_MODE_HEDGING = 2
    ACCOUNT_MARGIN_MODE_NETTING = 1
    POSITION_TYPE_BUY = 0
    POSITION_TYPE_SELL = 1

    def __init__(self, trade_mode: int = 0, margin_mode: int = 2):
        self.trade_mode = trade_mode
        self.margin_mode = margin_mode
        self.initialized = False

    def initialize(self) -> bool:
        self.initialized = True
        return True

    def shutdown(self) -> None:
        self.initialized = False

    def account_info(self):
        return SimpleNamespace(
            login=999001,
            company="JustMarkets-Demo",
            currency="USD",
            balance=10000.0,
            equity=10025.0,
            margin=120.0,
            margin_free=9905.0,
            margin_level=8354.16,
            leverage=500,
            trade_mode=self.trade_mode,
            margin_mode=self.margin_mode,
        )

    def positions_get(self):
        return [
            SimpleNamespace(
                ticket=1001,
                symbol="XAUUSD",
                type=0,
                volume=0.02,
                price_open=2650.0,
                price_current=2652.0,
                sl=0.0,  # Unprotected bot position!
                tp=2656.0,
                profit=4.0,
                magic=100101,
                comment="Institutional EA",
            ),
            SimpleNamespace(
                ticket=1002,
                symbol="BTCUSD",
                type=1,
                volume=0.01,
                price_open=95000.0,
                price_current=94900.0,
                sl=95500.0,
                tp=94000.0,
                profit=1.0,
                magic=0,
                comment="manual trade",
            ),
            SimpleNamespace(
                ticket=1003,
                symbol="XAUUSD",
                type=0,
                volume=0.01,
                price_open=2648.0,
                price_current=2652.0,
                sl=2640.0,
                tp=2660.0,
                profit=4.0,
                magic=888888,
                comment="other EA",
            ),
        ]

    def orders_get(self):
        return []

    def symbol_info(self, symbol: str):
        if symbol in ("XAUUSD", "BTCUSD"):
            return SimpleNamespace(
                name=symbol,
                digits=2,
                point=0.01,
                trade_tick_size=0.01,
                trade_tick_value=1.0,
                volume_min=0.01,
                volume_max=100.0,
                volume_step=0.01,
                trade_stops_level=10,
                spread=25,
                bid=2652.0 if symbol == "XAUUSD" else 94900.0,
                ask=2652.25 if symbol == "XAUUSD" else 94925.0,
            )
        return None


def test_sqlite_migrations_and_error_lifecycle(tmp_path: Path):
    db_path = tmp_path / "companion.db"
    version = init_database(db_path)
    assert version >= 1

    repo = CompanionRepository(db_path)
    health = repo.health_check()
    assert health["healthy"] is True
    assert health["schema_version"] == version

    err_id = repo.record_error(
        category="MT5",
        severity="WARNING",
        component="TestSuite",
        message="Simulated disconnect",
        trading_affected=False,
        entries_blocked=False,
        recommended_recovery="Reconnect MT5",
        user_action_required=True,
    )
    active = repo.get_errors(status="ACTIVE")
    assert len(active) == 1
    assert active[0]["id"] == err_id

    assert repo.resolve_error(err_id, "Verified recovery") is True
    assert repo.get_errors(status="ACTIVE") == []
    resolved = repo.get_errors(status="RESOLVED")
    assert len(resolved) == 1
    assert resolved[0]["resolution_note"] == "Verified recovery"


def test_local_auth_manager_and_secret_redaction(tmp_path: Path):
    with pytest.raises(ValueError):
        LocalAuthManager.validate_bind_host("0.0.0.0")
    assert LocalAuthManager.validate_bind_host("127.0.0.1") == "127.0.0.1"

    token_file = tmp_path / "token.txt"
    auth = LocalAuthManager(token="secret-token-123", token_file=token_file)
    assert token_file.read_text(encoding="utf-8") == "secret-token-123"

    assert auth.verify_request({"Authorization": "Bearer secret-token-123"}) is True
    assert auth.verify_request({"X-Companion-Token": "secret-token-123"}) is True
    assert auth.verify_request({}, query_token="secret-token-123") is True
    assert auth.verify_request({"Authorization": "Bearer wrong"}) is False
    assert auth.verify_request({"Authorization": "Bearer secret-token-123", "Origin": "https://evil.example"}) is False

    masked = redact_secrets("TELEGRAM_BOT_TOKEN=123456:ABCdef MT5_PASSWORD=mysecretpass")
    assert "123456:ABCdef" not in masked
    assert "mysecretpass" not in masked
    assert "***REDACTED***" in masked


def test_config_service_demo_lock_and_rollback(tmp_path: Path):
    cfg_dir = _copy_config_dir(tmp_path)
    repo = CompanionRepository(tmp_path / "db.sqlite")
    cfg_svc = ConfigurationService(cfg_dir, repo)

    # Attempt to enable live trading -> rejected
    with pytest.raises(ConfigurationValidationError):
        cfg_svc.apply_update(
            {"settings": {"LIVE_TRADING_ENABLED": True}},
            change_summary="Unsafe attempt",
        )

    # Attempt invalid operating mode -> rejected
    with pytest.raises(ConfigurationValidationError):
        cfg_svc.apply_update(
            {"operating_mode": "LIVE_REAL_MONEY"},
            change_summary="Invalid mode",
        )

    # Valid update with restart-required change
    res = cfg_svc.apply_update(
        {"operating_mode": "DEMO_FAST", "settings": {"magic_number": 200202}},
        change_summary="Switch to DEMO_FAST",
    )
    assert res["version"] >= 2
    assert res["requires_restart"] is True
    assert "magic_number" in res["changed_keys"][0] or any("magic_number" in k for k in res["changed_keys"])

    history = cfg_svc.get_history()
    assert len(history) >= 2
    v1_ver = history[-1]["version"]

    rb = cfg_svc.rollback_to_version(v1_ver)
    assert rb["version"] > res["version"]
    assert cfg_svc.get_full_config()["settings"].get("magic_number") != 200202


def test_mt5_sync_service_demo_check_and_reconciliation(tmp_path: Path):
    repo = CompanionRepository(tmp_path / "db.sqlite")
    events = EventBus()

    # 1. Real/Live account must be flagged non-DEMO
    live_mt5 = _FakeMT5(trade_mode=_FakeMT5.ACCOUNT_TRADE_MODE_REAL)
    sync_live = MT5SyncService(repo, events, mt5_module=live_mt5, bridge_client=_no_bridge())
    assert sync_live.connect() is True
    snap_live = sync_live.sync_all()
    assert snap_live["account"]["demo_verified"] is False
    active_errors = repo.get_errors(status="ACTIVE")
    assert any("DEMO" in e["message"] or "Non-DEMO" in e["message"] for e in active_errors)

    # 2. Demo account connects & reconciles BOT / MANUAL / OTHER_EA positions
    demo_mt5 = _FakeMT5(trade_mode=_FakeMT5.ACCOUNT_TRADE_MODE_DEMO, margin_mode=_FakeMT5.ACCOUNT_MARGIN_MODE_NETTING)
    sync = MT5SyncService(repo, events, bot_magic=100101, mt5_module=demo_mt5, bridge_client=_no_bridge())
    assert sync.connect() is True

    snap = sync.sync_all(["XAUUSD", "BTCUSD"])
    assert snap["account"]["demo_verified"] is True
    assert snap["account"]["netting_observe_only"] is True
    rep = snap["reconciliation"]
    assert rep["bot_owned_count"] == 1
    assert rep["manual_count"] == 1
    assert rep["other_ea_count"] == 1
    assert 1001 in rep["unprotected_bot_tickets"]


def test_engine_controller_stop_flag_and_pause_resume(tmp_path: Path):
    cfg_dir = _copy_config_dir(tmp_path)
    repo = CompanionRepository(tmp_path / "db.sqlite")
    events = EventBus()
    cfg_svc = ConfigurationService(cfg_dir, repo)
    mt5_sync = MT5SyncService(repo, events, mt5_module=_FakeMT5(), bridge_client=_no_bridge())
    controller = EngineController(tmp_path, repo, events, cfg_svc, mt5_sync)

    # Emergency stop creates STOP.flag and blocks start_engine
    em = controller.emergency_stop()
    assert em["success"] is True
    assert (tmp_path / "STOP.flag").exists()

    blocked = controller.start_engine()
    assert blocked["success"] is False
    assert blocked["state"] == "EMERGENCY_STOP"

    cleared = controller.clear_emergency_stop(confirmed=True)
    assert cleared["success"] is True
    assert not (tmp_path / "STOP.flag").exists()

    paused = controller.pause_entries()
    assert paused["success"] is True
    assert (tmp_path / "state" / "PAUSE").exists()

    resumed = controller.resume_entries()
    assert resumed["success"] is True
    assert not (tmp_path / "state" / "PAUSE").exists()


def test_operations_runner_allowlist_and_execution(tmp_path: Path):
    repo = CompanionRepository(tmp_path / "db.sqlite")
    events = EventBus()
    runner = OperationsRunner(PROJECT_ROOT, repo, events)

    # Unknown operation rejected with PermissionError
    with pytest.raises(PermissionError):
        runner.run_operation("rm_rf_arbitrary")

    # Allowlisted operation runs
    good = runner.run_operation("check_python")
    assert good["status"] == "SUCCESS"
    assert good["exit_code"] == 0
    assert "Python" in good["stdout"]


def test_control_http_server_auth_and_endpoints(tmp_path: Path):
    _copy_config_dir(tmp_path)
    server, ctx = build_control_server(
        project_root=tmp_path,
        host="127.0.0.1",
        port=0,
        db_path=tmp_path / "control.db",
        token="test-http-token",
        mt5_module=_FakeMT5(),
    )
    ctx.mt5_sync.bridge = _no_bridge()
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    try:
        # 1. /healthz works unauthenticated
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=5) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["status"] == "ok"

        # 2. /api/status without token returns 401
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=5)
        assert exc.value.code == 401

        # 3. /api/status with Bearer token succeeds
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/status",
            headers={"Authorization": "Bearer test-http-token"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            status_data = json.loads(resp.read().decode("utf-8"))
            assert "engine" in status_data and "mt5" in status_data and "health" in status_data

        # 4. POST /api/mt5/connect succeeds via fake MT5
        conn_req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/mt5/connect",
            data=b"{}",
            method="POST",
            headers={"Authorization": "Bearer test-http-token", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(conn_req, timeout=5) as resp:
            conn_data = json.loads(resp.read().decode("utf-8"))
            assert conn_data["success"] is True
            assert conn_data["snapshot"]["account"]["demo_verified"] is True

        # 5. POST /api/config/apply with LIVE_TRADING_ENABLED=True returns 400
        bad_cfg_req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/config/apply",
            data=json.dumps({"patch": {"settings": {"LIVE_TRADING_ENABLED": True}}}).encode("utf-8"),
            method="POST",
            headers={"Authorization": "Bearer test-http-token", "Content-Type": "application/json"},
        )
        with pytest.raises(urllib.error.HTTPError) as bad_cfg_exc:
            urllib.request.urlopen(bad_cfg_req, timeout=5)
        assert bad_cfg_exc.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
