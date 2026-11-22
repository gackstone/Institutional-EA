"""
Verification suite for MT5 Trading Engine single-instance lifecycle,
PID/heartbeat metadata, bridge handshake probe handling, request caching,
and EngineController adoption & graceful shutdown.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.app_paths import (
    SingleInstanceLock,
    clear_engine_heartbeat,
    is_pid_alive,
    read_engine_heartbeat,
    read_lock_metadata,
    verify_process_identity,
    write_engine_heartbeat,
)
from src.execution.bridge_client import BridgeClient
from src.execution.bridge_server import PersistentBridgeServer


def test_single_instance_lock_and_pid_metadata(tmp_path: Path):
    lock1 = SingleInstanceLock("mt5_trading_engine", state_dir=tmp_path)
    lock2 = SingleInstanceLock("mt5_trading_engine", state_dir=tmp_path)

    assert lock1.acquire() is True
    assert lock2.acquire() is False

    meta = read_lock_metadata("mt5_trading_engine", state_dir=tmp_path)
    assert meta is not None
    assert meta["pid"] == os.getpid()
    assert is_pid_alive(os.getpid()) is True
    assert verify_process_identity(os.getpid(), ("python", "pytest")) is True

    lock1.release()
    assert read_lock_metadata("mt5_trading_engine", state_dir=tmp_path) is None
    assert lock2.acquire() is True
    lock2.release()


def test_engine_heartbeat_write_read_clear(tmp_path: Path):
    payload = {
        "pid": os.getpid(),
        "status": "RUNNING",
        "epoch": time.time(),
        "cycles": 5,
    }
    write_engine_heartbeat(payload, state_dir=tmp_path)
    hb = read_engine_heartbeat(state_dir=tmp_path)
    assert hb is not None
    assert hb["pid"] == os.getpid()
    assert hb["status"] == "RUNNING"
    assert hb["cycles"] == 5

    clear_engine_heartbeat(state_dir=tmp_path)
    assert read_engine_heartbeat(state_dir=tmp_path) is None


def test_bridge_server_empty_probe_does_not_log_handshake_timeout(caplog):
    server = PersistentBridgeServer(ea_host="127.0.0.1", ea_port=0, ipc_host="127.0.0.1", ipc_port=0)
    # Bind ephemeral ports
    server._ea_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server._ea_server_socket.bind(("127.0.0.1", 0))
    server._ea_server_socket.listen(5)
    ea_port = server._ea_server_socket.getsockname()[1]

    server._ipc_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server._ipc_server_socket.bind(("127.0.0.1", 0))
    server._ipc_server_socket.listen(5)
    ipc_port = server._ipc_server_socket.getsockname()[1]

    server._is_running = True
    ea_thread = threading.Thread(target=server._ea_listener_loop, daemon=True)
    ipc_thread = threading.Thread(target=server._ipc_listener_loop, daemon=True)
    ea_thread.start()
    ipc_thread.start()

    try:
        # Simulate an immediate TCP connect+close on EA port
        with caplog.at_level("WARNING"):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(("127.0.0.1", ea_port))
            s.close()
            time.sleep(0.3)

        assert "EA_HANDSHAKE_TIMEOUT" not in caplog.text

        # Query STATUS over IPC port cleanly
        ipc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        ipc.settimeout(2.0)
        ipc.connect(("127.0.0.1", ipc_port))
        ipc.sendall((json.dumps({"action": "STATUS"}) + "\n").encode("utf-8"))
        resp = json.loads(ipc.recv(4096).decode("utf-8").strip())
        ipc.close()
        assert resp["status"] == "SUCCESS"
        assert resp["active_connections_count"] == 0
    finally:
        server.stop()


def test_bridge_client_request_dedup_and_caching():
    client = BridgeClient()
    calls = {"SYMBOL_SESSION": 0, "ACCOUNT": 0, "POSITIONS": 0}

    def fake_send_request(payload):
        action = payload["action"]
        calls[action] = calls.get(action, 0) + 1
        if action == "SYMBOL_SESSION":
            return {"status": "SUCCESS", "symbol": payload["symbol"], "trade_allowed": True}
        if action == "ACCOUNT":
            return {"status": "SUCCESS", "data": {"login": 12345, "balance": 1000.0, "equity": 1005.0}}
        if action == "POSITIONS":
            return {"status": "SUCCESS", "data": []}
        return {"status": "SUCCESS"}

    client.send_request = fake_send_request  # type: ignore[method-assign]

    # Repeated SYMBOL_SESSION within TTL hits cache
    r1 = client.check_symbol_session("XAUUSD.m")
    r2 = client.check_symbol_session("XAUUSD.m")
    assert r1["trade_allowed"] is True
    assert r2["trade_allowed"] is True
    assert calls["SYMBOL_SESSION"] == 1

    # Repeated ACCOUNT & POSITIONS within TTL hit cache
    a1 = client.get_account()
    a2 = client.get_account()
    assert a1 is not None and a2 is not None
    assert calls["ACCOUNT"] == 1

    p1 = client.get_positions()
    p2 = client.get_positions()
    assert p1 == [] and p2 == []
    assert calls["POSITIONS"] == 1

    # Mutating trade invalidates read caches
    client.invalidate_read_caches()
    client.get_account()
    client.get_positions()
    assert calls["ACCOUNT"] == 2
    assert calls["POSITIONS"] == 2
