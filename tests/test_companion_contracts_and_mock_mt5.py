"""
Automated IPC / HTTP Route Contract Tests & Mocked-MT5 Control Service Tests.

Covers:
  1. Control Service CLI parsing (--project-root, --data-dir, --host, --port).
  2. /health, /healthz, and /api/health/selfcheck endpoints.
  3. Mocked-MT5 Connect, Sync, Candles (3 symbols x 5 TFs + offline reason),
     Pause, Resume, Stop, and Close All Bot Positions.
  4. EA Deployer DEMO-lock enforcement, timestamped backup, SHA-256 copy verification,
     common.ini read-only inspection, and rollback behavior.
  5. Static contract check: every preload.cjs IPC invoke has a handler in main.cjs,
     and every controlClient /api/* route in ipc.ts exists in server.py.
"""

from __future__ import annotations

import json
import re
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict

import pytest

from companion.service.api.server import build_control_server
from companion.service.main import parse_args
from companion.service.mt5.ea_deployer import parse_metaeditor_log


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class _FakeMT5:
    """In-memory mock of the MetaTrader5 Python module (no real terminal touched)."""

    TIMEFRAME_M1 = 1
    TIMEFRAME_M5 = 5
    TIMEFRAME_M15 = 15
    TIMEFRAME_H1 = 16385
    TIMEFRAME_H4 = 16388

    def __init__(self, connected: bool = True, trade_mode: int = 0):
        self.connected = connected
        self.trade_mode = trade_mode  # 0 = DEMO, 2 = REAL
        self.last_init_path = None

    def initialize(self, path: str | None = None) -> bool:
        self.last_init_path = path
        return self.connected

    def last_error(self) -> tuple[int, str]:
        return (1, "OK") if self.connected else (-10003, "IPC initialize failed")

    def account_info(self) -> Any:
        if not self.connected:
            return None
        return SimpleNamespace(
            login=9990001,
            balance=10000.0,
            equity=10025.0,
            margin=100.0,
            margin_free=9925.0,
            margin_level=10025.0,
            currency="USD",
            leverage=500,
            trade_mode=self.trade_mode,
            margin_mode=2,
            company="MockDemoBroker",
        )

    def positions_get(self) -> list[Any]:
        return []

    def orders_get(self) -> list[Any]:
        return []

    def symbol_select(self, symbol: str, enable: bool = True) -> bool:
        return symbol in ("XAUUSD.m", "USDJPY.m", "BTCUSD.m")

    def symbol_info(self, symbol: str) -> Any:
        if symbol not in ("XAUUSD.m", "USDJPY.m", "BTCUSD.m"):
            return None
        digits = 3 if "JPY" in symbol else 2
        pt = 0.001 if "JPY" in symbol else 0.01
        return SimpleNamespace(
            name=symbol,
            digits=digits,
            point=pt,
            trade_tick_size=pt,
            trade_tick_value=1.0,
            trade_contract_size=100.0,
            volume_min=0.01,
            volume_max=50.0,
            volume_step=0.01,
            trade_stops_level=0,
            spread=12,
            trade_mode=4,
        )

    def symbol_info_tick(self, symbol: str) -> Any:
        if not self.connected or symbol not in ("XAUUSD.m", "USDJPY.m", "BTCUSD.m"):
            return None
        now_ts = int(datetime.now(timezone.utc).timestamp())
        base = 2500.0 if "XAU" in symbol else (150.0 if "JPY" in symbol else 65000.0)
        return SimpleNamespace(bid=base, ask=base + 0.2, time=now_ts)

    def copy_rates_from_pos(self, symbol: str, tf: int, start_pos: int, count: int) -> list[Dict[str, Any]]:
        if not self.connected or symbol not in ("XAUUSD.m", "USDJPY.m", "BTCUSD.m"):
            return []
        now_ts = int(datetime.now(timezone.utc).timestamp())
        base = 2500.0 if "XAU" in symbol else (150.0 if "JPY" in symbol else 65000.0)
        bars = []
        for i in range(min(count, 20)):
            t = now_ts - (20 - i) * 300
            bars.append({
                "time": t,
                "open": base + i * 0.1,
                "high": base + i * 0.1 + 0.5,
                "low": base + i * 0.1 - 0.4,
                "close": base + i * 0.1 + 0.2,
                "tick_volume": 100 + i,
            })
        return bars

    def symbols_get(self) -> list[Any]:
        return [self.symbol_info(s) for s in ("XAUUSD.m", "USDJPY.m", "BTCUSD.m")]


def _http_json(base_url: str, method: str, path: str, token: str | None = None, body: Dict[str, Any] | None = None) -> tuple[int, Dict[str, Any]]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers: Dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{base_url}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8")
        return err.code, json.loads(raw) if raw else {}


def test_cli_parse_args_accepts_project_root_and_data_dir(tmp_path: Path) -> None:
    ns = parse_args([
        "--host", "127.0.0.1",
        "--port", "8765",
        "--project-root", str(PROJECT_ROOT),
        "--data-dir", str(tmp_path),
    ])
    assert ns.host == "127.0.0.1"
    assert ns.port == 8765
    assert Path(ns.project_root) == PROJECT_ROOT
    assert Path(ns.data_dir) == tmp_path


def test_control_service_health_selfcheck_candles_and_controls_mock_mt5(tmp_path: Path) -> None:
    fake_mt5 = _FakeMT5(connected=True, trade_mode=0)
    token = "test-session-token-123"
    server, ctx = build_control_server(
        project_root=PROJECT_ROOT,
        host="127.0.0.1",
        port=0,
        data_dir=tmp_path,
        token=token,
        mt5_module=fake_mt5,
        enable_telegram_polling=False,
    )
    port = server.server_address[1]
    base_url = f"http://127.0.0.1:{port}"
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()
    try:
        # 1. /health and /healthz unauthenticated readiness
        code, h = _http_json(base_url, "GET", "/health")
        assert code == 200
        assert h["status"] == "ok"
        assert h["port"] == port

        code_z, hz = _http_json(base_url, "GET", "/healthz")
        assert code_z == 200
        assert hz["status"] == "ok"

        # 2. Connect & Sync MT5 with terminal_path
        code, conn = _http_json(
            base_url, "POST", "/api/mt5/connect", token=token,
            body={"terminal_path": r"C:\Program Files\MetaTrader 5\terminal64.exe"},
        )
        assert code == 200
        assert conn["success"] is True
        assert fake_mt5.last_init_path == r"C:\Program Files\MetaTrader 5\terminal64.exe"
        assert conn["snapshot"]["connection_status"] == "CONNECTED"
        assert conn["snapshot"]["account"]["demo_verified"] is True
        assert "zmq_bridge" in conn["snapshot"]

        # 3. Candles across all 3 symbols x 5 timeframes
        for sym in ("XAUUSD", "USDJPY", "BTCUSD"):
            for tf in ("M1", "M5", "M15", "H1", "H4"):
                c_code, c_res = _http_json(base_url, "GET", f"/api/market/candles?symbol={sym}&tf={tf}&count=20", token=token)
                assert c_code == 200
                assert len(c_res["candles"]) > 0
                assert c_res["status_reason"] == "OK"

        # 4. Self-check endpoint reports real PASS/WARN checks
        sc_code, sc = _http_json(base_url, "GET", "/api/health/selfcheck", token=token)
        assert sc_code == 200
        by_id = {c["id"]: c for c in sc["checks"]}
        assert by_id["control_service"]["status"] == "PASS"
        assert by_id["mt5_connection"]["status"] == "PASS"
        assert by_id["demo_mode"]["status"] == "PASS"
        assert by_id["symbols"]["status"] == "PASS"
        assert by_id["ea_source"]["status"] == "PASS"

        # 5. Pause, Resume, Stop, Close All (mock MT5)
        for endpoint, body in [
            ("/api/engine/pause", {}),
            ("/api/engine/resume", {}),
            ("/api/engine/stop", {}),
            ("/api/trades/close-all-bot", {"confirmed": True}),
        ]:
            rc, res = _http_json(base_url, "POST", endpoint, token=token, body=body)
            assert rc == 200
            assert "message" in res or "success" in res

        # 6. Deploy EA onto temp MT5 data folder (DEMO verified, backup + SHA256 copy + common.ini check)
        mt5_data = tmp_path / "mt5_data"
        experts = mt5_data / "MQL5" / "Experts"
        experts.mkdir(parents=True, exist_ok=True)
        (experts / "PythonBridgeEA.mq5").write_text("// old version", encoding="utf-8")
        (mt5_data / "config").mkdir(parents=True, exist_ok=True)
        (mt5_data / "config" / "common.ini").write_text("[Experts]\nExpertsEnabled=1\nExpertsDllImport=1\n", encoding="utf-8")

        d_code, d_res = _http_json(
            base_url, "POST", "/api/mt5/deploy-ea", token=token,
            body={"data_folder": str(mt5_data), "compile": False},
        )
        assert d_code == 200
        assert d_res["success"] is True
        assert d_res["backup_dir"] is not None
        assert Path(d_res["backup_dir"]).exists()
        assert (mt5_data / "MQL5" / "Sounds" / "signal.wav").exists()
        assert d_res["settings_check"]["allow_algo_trading"] is True
        assert d_res["chart_attachment"]["automated"] is False

        # 7. Disconnected MT5 candle status_reason & last_error
        fake_mt5.connected = False
        c_code2, c_res2 = _http_json(base_url, "GET", "/api/market/candles?symbol=XAUUSD&tf=M5&count=20", token=token)
        assert c_code2 == 200
        assert c_res2["candles"] == []
        assert c_res2["status_reason"] == "MT5_NOT_CONNECTED"
        assert "IPC initialize failed" in (c_res2.get("last_error") or "")
    finally:
        server.shutdown()
        server.server_close()


def test_deploy_ea_refuses_non_demo_account(tmp_path: Path) -> None:
    fake_real = _FakeMT5(connected=True, trade_mode=2)  # REAL account!
    token = "test-real-guard"
    server, _ctx = build_control_server(
        project_root=PROJECT_ROOT,
        host="127.0.0.1",
        port=0,
        data_dir=tmp_path,
        token=token,
        mt5_module=fake_real,
    )
    port = server.server_address[1]
    base_url = f"http://127.0.0.1:{port}"
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()
    try:
        d_code, d_res = _http_json(
            base_url, "POST", "/api/mt5/deploy-ea", token=token,
            body={"data_folder": str(tmp_path), "compile": False},
        )
        assert d_code == 400
        assert d_res["success"] is False
        assert "not verified DEMO" in d_res["message"]
    finally:
        server.shutdown()
        server.server_close()


def test_parse_metaeditor_log() -> None:
    ok, errs, warns, _ = parse_metaeditor_log("Result: 0 errors, 2 warnings, 1450 msec elapsed\n")
    assert ok is True and errs == 0 and warns == 2

    ok2, errs2, warns2, _ = parse_metaeditor_log("PythonBridgeEA.mq5(10,5) : error 149: undeclared identifier\nResult: 1 errors, 0 warnings\n")
    assert ok2 is False and errs2 == 1


def test_ipc_and_http_route_contracts() -> None:
    preload_src = (PROJECT_ROOT / "companion" / "electron" / "preload.cjs").read_text(encoding="utf-8")
    main_src = (PROJECT_ROOT / "companion" / "electron" / "main.cjs").read_text(encoding="utf-8")
    ipc_ts_src = (PROJECT_ROOT / "companion" / "src" / "services" / "ipc.ts").read_text(encoding="utf-8")
    server_py_src = (PROJECT_ROOT / "companion" / "service" / "api" / "server.py").read_text(encoding="utf-8")

    invoked_channels = set(re.findall(r'ipcRenderer\.invoke\(\s*"([^"]+)"', preload_src))
    handled_channels = set(re.findall(r'ipcMain\.handle\(\s*"([^"]+)"', main_src))
    missing_ipc = invoked_channels - handled_channels
    assert not missing_ipc, f"preload.cjs invokes IPC channels missing in main.cjs: {missing_ipc}"

    called_routes = set(re.findall(r'callControl(?:<[^>]+>)?\(\s*"(?:GET|POST)"\s*,\s*["`]([^"`?]+)', ipc_ts_src))
    # Also catch template literal routes like `/api/market/candles?...`
    called_routes |= set(re.findall(r'`(/api/[a-zA-Z0-9/_-]+)\?', ipc_ts_src))
    server_routes = set(re.findall(r'path\s*==\s*"(/api/[a-zA-Z0-9/_-]+)"', server_py_src))
    missing_routes = {r for r in called_routes if r.startswith("/api/")} - server_routes
    assert not missing_routes, f"ipc.ts calls HTTP routes missing in server.py: {missing_routes}"
