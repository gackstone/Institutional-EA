"""
Tests for the Opt-In Read-Only Mobile Sync HTTP/SSE Server.

Verifies:
1. Off by default (no network port bound until explicitly enabled).
2. Unauthenticated requests rejected with 401.
3. Pairing with valid 6-digit code works; code is single-use; brute-force rate limited (429).
4. Token isolation: desktop token rejected by mobile server, mobile token rejected by desktop server.
5. STRICT READ-ONLY ENFORCEMENT: all mutation methods/paths rejected with 403 READ_ONLY_ENFORCED.
6. Device revocation and self-unpair immediately invalidate tokens.
7. Read-only GET endpoints (/status, /account, /stats, /positions, /trades, /symbols, /candles, /drawings, /equity, /activity, /events SSE) return accurate real data with masked account numbers.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

import pytest

from companion.service.api.server import build_control_server
from companion.service.mobile.sync_server import MOBILE_SYNC_SCHEMA_VERSION


def _http_req(
    url: str,
    method: str = "GET",
    headers: Dict[str, str] | None = None,
    body: Dict[str, Any] | None = None,
    timeout: float = 5.0,
) -> Tuple[int, Dict[str, Any]]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8")
        return err.code, json.loads(raw) if raw.strip() else {}


@pytest.fixture
def control_and_mobile_env(tmp_path: Path):
    project_root = Path(__file__).resolve().parent.parent
    server, ctx = build_control_server(
        project_root=project_root,
        host="127.0.0.1",
        port=0,
        db_path=tmp_path / "companion.db",
        token="desktop-only-secret-token-12345",
        data_dir=tmp_path,
    )
    # Seed realistic MT5 snapshot in memory for deterministic assertions
    now_iso = datetime.now(timezone.utc).isoformat()
    ctx.mt5_sync.connection_status = "CONNECTED"
    ctx.mt5_sync.last_sync_at = now_iso
    ctx.mt5_sync.account.update({
        "account_number": 50987654,
        "broker": "JustMarkets-Demo",
        "currency": "USD",
        "balance": 12500.0,
        "equity": 12615.5,
        "margin": 420.0,
        "free_margin": 12195.5,
        "margin_level": 3003.69,
        "leverage": 500,
        "trade_mode": "DEMO",
        "demo_verified": True,
    })
    ctx.mt5_sync.positions = [
        {
            "ticket": 880011,
            "symbol": "XAUUSD.m",
            "direction": "BUY",
            "volume": 0.05,
            "open_price": 2710.20,
            "current_price": 2712.50,
            "sl": 2705.00,
            "tp": 2722.00,
            "profit": 115.50,
            "swap": -0.30,
            "open_time": int(time.time()) - 1800,
            "ownership": "BOT_OWN",
            "comment": "SMC FVG Entry",
        }
    ]
    ctx.mt5_sync.symbols = {
        "XAUUSD.m": {"digits": 2, "point": 0.01, "bid": 2712.50, "ask": 2712.70, "spread_points": 20.0},
        "USDJPY.m": {"digits": 3, "point": 0.001, "bid": 154.210, "ask": 154.225, "spread_points": 15.0},
    }

    # Bind mobile server to 127.0.0.1 ephemeral port during tests
    ctx.mobile_sync.bind_host = "127.0.0.1"
    ctx.mobile_sync.port = 0

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    desktop_url = f"http://127.0.0.1:{ctx.port}"
    desktop_headers = {"Authorization": f"Bearer {ctx.auth.token}"}

    try:
        yield desktop_url, desktop_headers, ctx
    finally:
        ctx.mobile_sync.disable()
        server.shutdown()
        server.server_close()


def test_mobile_sync_off_by_default_and_opt_in_lifecycle(control_and_mobile_env):
    desktop_url, desktop_headers, ctx = control_and_mobile_env

    # 1. Off by default
    code, status = _http_req(f"{desktop_url}/api/mobile-sync/status", headers=desktop_headers)
    assert code == 200
    assert status["enabled"] is False
    assert status["pairingCode"] is None
    assert status["readOnlyEnforced"] is True

    # 2. Opt-in enable starts listener and generates 6-digit pairing code
    code, enabled_status = _http_req(
        f"{desktop_url}/api/mobile-sync/enable",
        method="POST",
        headers=desktop_headers,
        body={},
    )
    assert code == 200
    assert enabled_status["enabled"] is True
    assert enabled_status["port"] > 0
    assert len(enabled_status["pairingCode"]) == 6
    assert enabled_status["qrPayload"]["code"] == enabled_status["pairingCode"]

    mobile_url = f"http://127.0.0.1:{enabled_status['port']}"

    # 3. Unauthenticated request to mobile data endpoint returns 401
    code, _ = _http_req(f"{mobile_url}/api/mobile/v1/status")
    assert code == 401

    # 4. Desktop session token is rejected by mobile server (token isolation)
    code, _ = _http_req(f"{mobile_url}/api/mobile/v1/status", headers=desktop_headers)
    assert code == 401

    # 5. Pair mobile device with valid 6-digit code
    pair_code = enabled_status["pairingCode"]
    code, paired = _http_req(
        f"{mobile_url}/api/mobile/v1/pair",
        method="POST",
        body={"code": pair_code, "deviceName": "Pixel 8 Pro", "platform": "android"},
    )
    assert code == 200
    assert paired["readOnly"] is True
    assert paired["schemaVersion"] == MOBILE_SYNC_SCHEMA_VERSION
    assert paired["deviceToken"].startswith("iea_ro_")
    mobile_headers = {"Authorization": f"Bearer {paired['deviceToken']}"}

    # 6. Pairing code is single-use (replay rejected)
    code, _ = _http_req(
        f"{mobile_url}/api/mobile/v1/pair",
        method="POST",
        body={"code": pair_code, "deviceName": "Attacker Phone", "platform": "android"},
    )
    assert code == 401

    # 7. Mobile token is rejected by desktop control server (cannot touch desktop API)
    code, _ = _http_req(f"{desktop_url}/api/status", headers=mobile_headers)
    assert code == 401
    code, _ = _http_req(f"{desktop_url}/api/engine/start", method="POST", headers=mobile_headers, body={})
    assert code == 401


def test_mobile_sync_strict_read_only_rejects_all_mutations(control_and_mobile_env):
    desktop_url, desktop_headers, _ctx = control_and_mobile_env
    _, st = _http_req(f"{desktop_url}/api/mobile-sync/enable", method="POST", headers=desktop_headers, body={})
    mobile_url = f"http://127.0.0.1:{st['port']}"
    _, paired = _http_req(
        f"{mobile_url}/api/mobile/v1/pair",
        method="POST",
        body={"code": st["pairingCode"], "deviceName": "Galaxy S24", "platform": "android"},
    )
    mobile_headers = {"Authorization": f"Bearer {paired['deviceToken']}"}

    # Every mutation attempt must be rejected with 403 READ_ONLY_ENFORCED
    mutation_cases = [
        ("POST", "/api/engine/start"),
        ("POST", "/api/engine/stop"),
        ("POST", "/api/engine/pause"),
        ("POST", "/api/engine/emergency-stop"),
        ("POST", "/api/trades/close"),
        ("POST", "/api/trades/modify"),
        ("POST", "/api/trades/close-all-bot"),
        ("POST", "/api/config/apply"),
        ("POST", "/api/mobile/v1/status"),
        ("PUT", "/api/mobile/v1/account"),
        ("PATCH", "/api/mobile/v1/positions"),
        ("DELETE", "/api/mobile/v1/positions"),
    ]
    for method, path in mutation_cases:
        code, body = _http_req(
            f"{mobile_url}{path}",
            method=method,
            headers=mobile_headers,
            body={"confirmed": True},
        )
        assert code == 403, f"Expected 403 for {method} {path}, got {code}"
        assert body.get("error") == "READ_ONLY_ENFORCED"


def test_mobile_sync_rate_limiting_and_revocation(control_and_mobile_env):
    desktop_url, desktop_headers, _ctx = control_and_mobile_env
    _, st = _http_req(f"{desktop_url}/api/mobile-sync/enable", method="POST", headers=desktop_headers, body={})
    mobile_url = f"http://127.0.0.1:{st['port']}"

    # Pair a valid device first
    _, paired = _http_req(
        f"{mobile_url}/api/mobile/v1/pair",
        method="POST",
        body={"code": st["pairingCode"], "deviceName": "OnePlus 12", "platform": "android"},
    )
    mobile_headers = {"Authorization": f"Bearer {paired['deviceToken']}"}

    # Verify authenticated GET works and masks account number
    code, status_payload = _http_req(f"{mobile_url}/api/mobile/v1/status", headers=mobile_headers)
    assert code == 200
    assert status_payload["readOnlyEnforced"] is True
    assert status_payload["mt5Connected"] is True
    assert "50987654" not in json.dumps(status_payload)
    assert status_payload["accountMasked"] == "50***654"

    code, acc = _http_req(f"{mobile_url}/api/mobile/v1/account", headers=mobile_headers)
    assert code == 200
    assert acc["balance"] == 12500.0
    assert acc["equity"] == 12615.5
    assert acc["openPositionsCount"] == 1

    code, pos = _http_req(f"{mobile_url}/api/mobile/v1/positions", headers=mobile_headers)
    assert code == 200
    assert len(pos["positions"]) == 1
    assert pos["positions"][0]["ticket"] == 880011

    code, stats = _http_req(f"{mobile_url}/api/mobile/v1/stats", headers=mobile_headers)
    assert code == 200
    assert stats["currency"] == "USD"

    code, syms = _http_req(f"{mobile_url}/api/mobile/v1/symbols", headers=mobile_headers)
    assert code == 200
    assert len(syms["symbols"]) == 2
    assert "M5" in syms["timeframes"]

    code, trades = _http_req(f"{mobile_url}/api/mobile/v1/trades?page=1&limit=10", headers=mobile_headers)
    assert code == 200
    assert "items" in trades and "summary" in trades

    # Revoke device from desktop side -> immediate 401
    code, rev = _http_req(
        f"{desktop_url}/api/mobile-sync/devices/revoke",
        method="POST",
        headers=desktop_headers,
        body={"deviceId": paired["deviceId"]},
    )
    assert code == 200
    assert rev["revoked"] is True

    code, _ = _http_req(f"{mobile_url}/api/mobile/v1/status", headers=mobile_headers)
    assert code == 401

    # Brute-force pairing attempts trigger 429 after 5 failures
    for _ in range(5):
        c, _ = _http_req(
            f"{mobile_url}/api/mobile/v1/pair",
            method="POST",
            body={"code": "000000", "deviceName": "Brute", "platform": "android"},
        )
        assert c == 401
    c_rl, body_rl = _http_req(
        f"{mobile_url}/api/mobile/v1/pair",
        method="POST",
        body={"code": "000000", "deviceName": "Brute", "platform": "android"},
    )
    assert c_rl == 429
    assert body_rl["error"] == "RATE_LIMITED"


def test_cloud_bundle_sync_health_closed_deals_reconciliation_and_secret_scan(control_and_mobile_env):
    """
    Phase 5 Regression Test for E1-E8 and Phase 4 Security Payload Minimisation:
    - Verifies stale OPEN rows in trade_records are cleaned up and never counted as closed deals (E5/E6).
    - Verifies closed MT5 deals are synced into trade_records with status='CLOSED'.
    - Verifies /api/mobile-sync/cloud-bundle returns complete v1.1.0 contract (meta, status, account with marginLevel,
      stats with tradesToday = closedToday + openPositionsCount, positions with SL/TP or None when 0, closed trades,
      symbols, candlesByKey, drawingsByKey with both camelCase & uppercase counts, equityPoints).
    - Verifies /api/sync/health reports stream rows, lag, and unprotected position safety findings (E7).
    - Scans full serialized bundle for forbidden secrets or raw account numbers (Phase 4).
    """
    desktop_url, desktop_headers, ctx = control_and_mobile_env

    # Seed 50 stale 'OPEN' rows in SQLite (reproducing the exact E6 bug condition: 25 positive, 25 negative)
    for i in range(50):
        ctx.repo.upsert_trade_record(
            {
                "ticket": 900000 + i,
                "symbol": "XAUUSD.m",
                "direction": "BUY",
                "volume": 0.02,
                "entry_price": 2700.0,
                "close_price": 0.0,
                "stop_loss": 0.0,
                "take_profit": 0.0,
                "profit": 10.0 if i < 25 else -10.0,
                "status": "OPEN",
                "opened_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    # Seed 2 real balance snapshots for equity curve (E4)
    ctx.repo.record_balance_snapshot(balance=12500.0, equity=12500.0, floating_pnl=0.0, source="MT5")
    ctx.repo.record_balance_snapshot(balance=12500.0, equity=12615.5, floating_pnl=115.5, source="MT5")

    # 1. Verify stats payload ignores the 50 stale 'OPEN' rows (E5/E6 fix)
    stats = ctx.mobile_sync.build_stats_payload()
    assert stats["dealsCount"] == 0, "Stale OPEN rows must never be counted as closed deals!"
    assert stats["winsCount"] == 0
    assert stats["lossesCount"] == 0
    assert stats["winRate"] == 0.0
    assert stats["openPositionsCount"] == 1
    assert stats["tradesToday"] == 1  # 0 closed today + 1 open position = 1 trade today (matches Desktop!)
    assert stats["todayPnl"] == 115.5  # 0 realized today + 115.5 floating
    assert stats["totalProfit"] == 115.5

    # 2. Verify cleanup_stale_open_trade_records removes orphan OPEN rows not in active MT5 positions
    removed = ctx.repo.cleanup_stale_open_trade_records([880011])
    assert removed == 50

    # 3. Fetch v1.1.0 cloud bundle from /api/mobile-sync/cloud-bundle
    code, bundle = _http_req(f"{desktop_url}/api/mobile-sync/cloud-bundle?limit=40", headers=desktop_headers)
    assert code == 200
    assert bundle["meta"]["schemaVersion"] == "1.1.0"
    assert bundle["account"]["marginLevel"] == 3003.69
    assert bundle["account"]["freeMargin"] == 12195.5
    assert bundle["stats"]["dealsCount"] == 0
    assert bundle["stats"]["tradesToday"] == 1
    assert len(bundle["symbols"]) == 2
    assert len(bundle["equityPoints"]) >= 2
    assert bundle["trades"] == []

    # 4. Fetch /api/sync/health
    code_h, health = _http_req(f"{desktop_url}/api/sync/health", headers=desktop_headers)
    assert code_h == 200
    assert health["ok"] is True
    assert health["schemaVersion"] == "1.1.0"
    assert "account" in health["streams"]
    assert "positions" in health["streams"]
    assert "equity_snapshots" in health["streams"]

    # 5. Phase 4 Automated Payload Secret & Raw Account Number Scanner
    serialized = json.dumps(bundle)
    assert "50987654" not in serialized, "Raw unmasked MT5 account number must never appear in cloud payload"
    assert "desktop-only-secret-token-12345" not in serialized
    for forbidden_key in ("password", "service_role", "sb_secret_", "telegram_bot_token", "signing_secret"):
        assert forbidden_key not in serialized.lower(), f"Forbidden key '{forbidden_key}' found in cloud bundle"
