"""
Authenticated Localhost-Only Control API & SSE Event Stream for the Institutional EA Companion.
Binds exclusively to 127.0.0.1 and validates Bearer/X-Companion-Token on every request.
"""

from __future__ import annotations
import base64
import json
import os
import queue
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from companion.database.repository import CompanionRepository
from companion.service.configuration.config_service import ConfigurationService, ConfigurationValidationError
from companion.service.events.event_bus import EventBus
from companion.service.market.drawings_engine import ChartDrawingsService
from companion.service.mt5.ea_deployer import deploy_ea_pipeline, extract_ea_version
from companion.service.mt5.sync_service import MT5SyncService
from companion.service.operations.ps_runner import OperationsRunner
from companion.service.orchestration.engine_controller import EngineController
from companion.service.security.auth import LocalAuthManager
from companion.service.trading.btcusd_sample_service import BTCUSDSampleTradingService
from src.notifications.telegram_config import TelegramConfig
from src.notifications.telegram_service import TelegramCommandHandler, TelegramNotifier
try:
    from src.intelligence.facade import AdaptiveTradingIntelligence
except ImportError:
    AdaptiveTradingIntelligence = None


class ControlServiceContext:
    def __init__(
        self,
        project_root: str | Path,
        repo: CompanionRepository,
        auth: LocalAuthManager,
        events: EventBus,
        config_service: ConfigurationService,
        mt5_sync: MT5SyncService,
        engine: EngineController,
        operations: OperationsRunner,
        btcusd_sample: Optional[BTCUSDSampleTradingService] = None,
        telegram_notifier: Optional[TelegramNotifier] = None,
        ati: Optional[Any] = None,
        data_dir: Optional[str | Path] = None,
        host: str = "127.0.0.1",
        port: int = 8765,
    ):
        self.project_root = Path(project_root)
        self.data_dir = Path(data_dir) if data_dir else self.project_root
        self.host = host
        self.port = int(port)
        self.started_at = time.time()
        self.repo = repo
        self.auth = auth
        self.events = events
        self.config_service = config_service
        self.mt5_sync = mt5_sync
        self.engine = engine
        self.chart_drawings = ChartDrawingsService(self.project_root, mt5_sync, repo)
        self.operations = operations
        self.btcusd_sample = btcusd_sample
        self.telegram_notifier = telegram_notifier
        self.ati = ati

    def run_self_check(self) -> Dict[str, Any]:
        """Runs real end-to-end readiness & health checks for System Health UI."""
        snap = self.mt5_sync.get_snapshot()
        zmq = self.mt5_sync.check_zmq_bridge()
        acc = snap.get("account") or {}
        syms = snap.get("symbols") or {}
        required_syms = ["XAUUSD.m", "USDJPY.m", "BTCUSD.m"]
        present_syms = [s for s in required_syms if s in syms]
        ea_src = self.project_root / "mql5" / "Experts" / "PythonBridgeEA.mq5"
        ea_ver = extract_ea_version(ea_src) if ea_src.exists() else ""
        last_candles = snap.get("last_candle_times") or {}

        checks = [
            {
                "id": "control_service",
                "name": "Control Service",
                "status": "PASS",
                "detail": f"Listening on {self.host}:{self.port} (PID {os.getpid()})",
            },
            {
                "id": "mt5_connection",
                "name": "MT5 Terminal Connection",
                "status": "PASS" if snap.get("connection_status") == "CONNECTED" else "FAIL",
                "detail": (
                    f"Connected to {acc.get('broker', 'MT5')}"
                    if snap.get("connection_status") == "CONNECTED"
                    else (snap.get("last_error") or "MT5 not connected")
                ),
            },
            {
                "id": "demo_mode",
                "name": "DEMO Account Lock",
                "status": "PASS" if acc.get("demo_verified") else ("WARN" if snap.get("connection_status") != "CONNECTED" else "FAIL"),
                "detail": f"Mode: {acc.get('trade_mode', 'UNKNOWN')} (LIVE_TRADING_ENABLED=false)",
            },
            {
                "id": "symbols",
                "name": "Required Symbols (XAUUSD.m, USDJPY.m, BTCUSD.m)",
                "status": "PASS" if len(present_syms) == len(required_syms) else ("WARN" if present_syms else "FAIL"),
                "detail": f"{len(present_syms)}/{len(required_syms)} active: {', '.join(present_syms) or 'none'}",
            },
            {
                "id": "zmq_bridge",
                "name": "ZMQ / TCP Bridge (5555 / 5556)",
                "status": "PASS" if zmq.get("port_5555") else "WARN",
                "detail": f"5555={'LISTENING' if zmq.get('port_5555') else 'IDLE'}, 5556={'LISTENING' if zmq.get('port_5556') else 'IDLE'}",
            },
            {
                "id": "ea_source",
                "name": "PythonBridgeEA Asset",
                "status": "PASS" if ea_src.exists() else "FAIL",
                "detail": f"v{ea_ver or 'unknown'} verified" if ea_src.exists() else "PythonBridgeEA.mq5 missing",
            },
            {
                "id": "candles",
                "name": "Live Candle Feed",
                "status": "PASS" if len(last_candles) > 0 else "WARN",
                "detail": (
                    ", ".join(f"{k}: {v[11:19]}Z" for k, v in last_candles.items())
                    if last_candles
                    else "Awaiting first candle request"
                ),
            },
        ]
        overall = "HEALTHY" if all(c["status"] == "PASS" for c in checks[:4]) else "DEGRADED"
        return {
            "status": overall,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "checks": checks,
            "zmq_bridge": zmq,
            "last_candle_times": last_candles,
        }


def create_request_handler(ctx: ControlServiceContext):
    class CompanionRequestHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            return  # Suppress noisy stdout access logs

        def _send_json(self, status_code: int, data: Any) -> None:
            body = json.dumps(data).encode("utf-8")
            try:
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                pass

        def _read_json_body(self) -> Dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0:
                return {}
            raw = self.rfile.read(length).decode("utf-8")
            return json.loads(raw) if raw.strip() else {}

        def _is_authorized(self, query: Dict[str, list[str]]) -> bool:
            q_tok = query.get("token", [None])[0]
            return ctx.auth.verify_request(self.headers, query_token=q_tok)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)

            if path in ("/healthz", "/health"):
                self._send_json(200, {
                    "status": "ok",
                    "service": "institutional-ea-control-service",
                    "host": ctx.host,
                    "port": ctx.port,
                    "pid": os.getpid(),
                    "uptime_sec": round(time.time() - ctx.started_at, 2),
                    "mt5_status": ctx.mt5_sync.connection_status,
                })
                return

            if not self._is_authorized(query):
                self._send_json(401, {"error": "Unauthorized: invalid or missing session token"})
                return

            if path == "/api/events":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                sub = ctx.events.subscribe()
                try:
                    # Send initial full snapshot matching /api/status schema
                    init_payload = json.dumps({
                        "type": "snapshot",
                        "payload": {
                            "engine": ctx.engine.get_status(),
                            "mt5": ctx.mt5_sync.get_snapshot(),
                            "health": ctx.engine.get_health(),
                        },
                    })
                    self.wfile.write(f"data: {init_payload}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    while True:
                        try:
                            ev = sub.get(timeout=15.0)
                            self.wfile.write(f"data: {json.dumps(ev)}\n\n".encode("utf-8"))
                            self.wfile.flush()
                        except queue.Empty:
                            self.wfile.write(b": keepalive\n\n")
                            self.wfile.flush()
                except Exception:
                    pass
                finally:
                    ctx.events.unsubscribe(sub)
                return

            if path == "/api/status":
                self._send_json(200, {
                    "engine": ctx.engine.get_status(),
                    "mt5": ctx.mt5_sync.get_snapshot(),
                    "health": ctx.engine.get_health(),
                })
            elif path == "/api/engine/status":
                self._send_json(200, ctx.engine.get_status())
            elif path == "/api/health":
                self._send_json(200, ctx.engine.get_health())
            elif path == "/api/health/selfcheck":
                self._send_json(200, ctx.run_self_check())
            elif path == "/api/mt5/snapshot":
                self._send_json(200, ctx.mt5_sync.get_snapshot())
            elif path == "/api/mt5/detect":
                self._send_json(200, ctx.mt5_sync.detect_terminal())
            elif path == "/api/config":
                self._send_json(200, ctx.config_service.get_full_config())
            elif path == "/api/config/history":
                self._send_json(200, {"versions": ctx.config_service.get_history()})
            elif path == "/api/operations":
                self._send_json(200, {
                    "operations": ctx.operations.list_operations(),
                    "audits": ctx.repo.get_operation_audits(),
                })
            elif path == "/api/errors":
                status_filter = query.get("status", [None])[0]
                self._send_json(200, {"errors": ctx.repo.get_errors(status=status_filter)})
            elif path == "/api/logs":
                limit = int(query.get("limit", ["200"])[0])
                self._send_json(200, {
                    "logs": ctx.events.get_logs(
                        limit=limit,
                        severity=query.get("severity", [None])[0],
                        instrument=query.get("instrument", [None])[0],
                        component=query.get("component", [None])[0],
                        ticket=int(query["ticket"][0]) if "ticket" in query else None,
                        correlation_id=query.get("correlation_id", [None])[0],
                    )
                })
            elif path == "/api/trades/history":
                self._send_json(200, {"trades": ctx.repo.get_trade_records(limit=250)})
            elif path == "/api/market/candles":
                sym = query.get("symbol", ["XAUUSD"])[0]
                tf = query.get("tf", ["M5"])[0]
                count = int(query.get("count", ["120"])[0])
                from_iso = query.get("from", [None])[0]
                to_iso = query.get("to", [None])[0]
                self._send_json(200, ctx.mt5_sync.get_candles(sym, tf, count, from_iso, to_iso))
            elif path == "/api/chart/drawings":
                sym = query.get("symbol", ["XAUUSD"])[0]
                tf = query.get("tf", ["M5"])[0]
                count = int(query.get("count", ["160"])[0])
                self._send_json(200, ctx.chart_drawings.get_drawings(sym, tf, count))
            elif path == "/api/analytics/equity":
                self._send_json(200, {
                    "snapshots": ctx.repo.get_balance_snapshots(limit=500),
                    "trades": ctx.repo.get_trade_records(limit=500),
                    "source": "BOT+MT5",
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                })
            elif path == "/api/signals":
                self._send_json(200, {
                    "signals": ctx.repo.get_signals(limit=150),
                    "decisions": ctx.repo.get_risk_decisions(limit=150),
                    "source": "BOT",
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                })
            elif path == "/api/trades/replay":
                ticket = int(query.get("ticket", ["0"])[0])
                tf = query.get("tf", ["M5"])[0]
                all_trades = ctx.repo.get_trade_records(limit=500)
                trade = next((t for t in all_trades if int(t.get("ticket", 0)) == ticket), None)
                if not trade:
                    self._send_json(404, {"error": f"Trade #{ticket} not found in real trade history"})
                else:
                    events = ctx.repo.get_execution_events_for_ticket(ticket)
                    shots = ctx.repo.get_trade_screenshots(ticket=ticket)
                    opened_iso = trade.get("opened_at")
                    closed_iso = trade.get("closed_at") or datetime.now(timezone.utc).isoformat()
                    try:
                        s_dt = datetime.fromisoformat(str(opened_iso).replace("Z", "+00:00")) - timedelta(minutes=90)
                        e_dt = datetime.fromisoformat(str(closed_iso).replace("Z", "+00:00")) + timedelta(minutes=60)
                        candles_res = ctx.mt5_sync.get_candles(
                            str(trade.get("symbol", "XAUUSD")),
                            tf,
                            count=200,
                            start_iso=s_dt.isoformat(),
                            end_iso=e_dt.isoformat(),
                        )
                    except Exception:
                        candles_res = {"candles": [], "source": "MT5"}
                    self._send_json(200, {
                        "trade": trade,
                        "events": events,
                        "screenshots": shots,
                        "candles": candles_res.get("candles", []),
                        "source": "MT5+BOT",
                    })
            elif path == "/api/trades/screenshots":
                ticket_q = query.get("ticket", [None])[0]
                t_int = int(ticket_q) if ticket_q is not None else None
                self._send_json(200, {"screenshots": ctx.repo.get_trade_screenshots(ticket=t_int)})
            elif path == "/api/trades/screenshots/file":
                name = str(query.get("name", [""])[0])
                if not re.fullmatch(r"[A-Za-z0-9._-]+\.png", name):
                    self._send_json(400, {"error": "Invalid screenshot filename"})
                else:
                    fpath = (ctx.data_dir / "data" / "screenshots" / name).resolve()
                    shots_root = (ctx.data_dir / "data" / "screenshots").resolve()
                    if not str(fpath).startswith(str(shots_root)) or not fpath.exists():
                        self._send_json(404, {"error": "Screenshot not found"})
                    else:
                        raw_png = fpath.read_bytes()
                        self.send_response(200)
                        self.send_header("Content-Type", "image/png")
                        self.send_header("Content-Length", str(len(raw_png)))
                        self.send_header("Cache-Control", "no-store")
                        self.end_headers()
                        self.wfile.write(raw_png)
            elif path == "/api/alerts":
                self._send_json(200, {
                    "alerts": ctx.repo.get_alerts(limit=150),
                    "settings": ctx.repo.get_alert_settings(),
                    "source": "BOT",
                })
            elif path == "/api/alerts/settings":
                self._send_json(200, ctx.repo.get_alert_settings())
            elif path == "/api/risk/decisions":
                self._send_json(200, {
                    "decisions": ctx.repo.get_risk_decisions(limit=150),
                    "risk_state": ctx.engine.risk_engine.to_dict(),
                })
            elif path == "/api/audit":
                self._send_json(200, {
                    "audits": ctx.repo.get_audit_logs(limit=150),
                    "connections": ctx.repo.get_connection_history(limit=50),
                })
            elif path == "/api/btcusd/status":
                self._send_json(200, ctx.btcusd_sample.get_status() if ctx.btcusd_sample else {"enabled": False, "state": "UNAVAILABLE"})
            elif path == "/api/ati/status":
                self._send_json(200, ctx.ati.get_system_status() if ctx.ati else {"enabled": False, "mode": "DISABLED"})
            elif path == "/api/ati/audits":
                self._send_json(200, {"audits": [a.to_dict() for a in ctx.ati.repo.list_trade_audits(limit=100)]} if ctx.ati else {"audits": []})
            elif path == "/api/ati/candidates":
                self._send_json(200, {"candidates": [c.to_dict() for c in ctx.ati.repo.list_candidates()]} if ctx.ati else {"candidates": []})
            elif path == "/api/ati/execution":
                self._send_json(200, ctx.ati.get_execution_metrics().to_dict() if ctx.ati else {})
            elif path == "/api/ati/reports/daily":
                self._send_json(200, ctx.ati.reporter.generate_daily_report() if ctx.ati else {})
            elif path == "/api/ati/reports/weekly":
                self._send_json(200, ctx.ati.reporter.generate_weekly_report() if ctx.ati else {})
            else:
                self._send_json(404, {"error": f"Unknown endpoint: {path}"})

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)

            if not self._is_authorized(query):
                self._send_json(401, {"error": "Unauthorized: invalid or missing session token"})
                return

            try:
                body = self._read_json_body()
            except Exception as exc:
                self._send_json(400, {"error": f"Invalid JSON body: {exc}"})
                return

            if path == "/api/engine/start":
                self._send_json(200, ctx.engine.start_engine(dry_run=body.get("dry_run")))
            elif path == "/api/engine/stop":
                self._send_json(200, ctx.engine.stop_engine())
            elif path == "/api/engine/restart":
                self._send_json(200, ctx.engine.restart_engine())
            elif path == "/api/engine/pause":
                self._send_json(200, ctx.engine.pause_entries())
            elif path == "/api/engine/resume":
                self._send_json(200, ctx.engine.resume_entries())
            elif path == "/api/engine/emergency-stop":
                self._send_json(200, ctx.engine.emergency_stop(
                    close_bot_positions=bool(body.get("close_bot_positions", False)),
                    confirmed=bool(body.get("confirmed", False)),
                ))
            elif path == "/api/engine/clear-emergency-stop":
                self._send_json(200, ctx.engine.clear_emergency_stop(confirmed=bool(body.get("confirmed", False))))
            elif path == "/api/mt5/connect":
                term_path = body.get("terminal_path")
                ok = ctx.mt5_sync.connect(terminal_path=term_path)
                snap = ctx.mt5_sync.sync_all(terminal_path=term_path) if ok else ctx.mt5_sync.get_snapshot()
                self._send_json(200, {"success": ok, "error": ctx.mt5_sync.last_error, "snapshot": snap})
            elif path == "/api/mt5/disconnect":
                eng_status = ctx.engine.get_status()
                eng_state = eng_status.get("engine_state") or eng_status.get("state") or "STOPPED"
                if eng_state in ("RUNNING", "PAUSED", "STARTING"):
                    self._send_json(200, {
                        "success": False,
                        "error": "Stop the engine before disconnecting MT5.",
                        "snapshot": ctx.mt5_sync.get_snapshot(),
                    })
                else:
                    snap = ctx.mt5_sync.disconnect()
                    self._send_json(200, {"success": True, "error": None, "snapshot": snap})
            elif path == "/api/mt5/sync":
                term_path = body.get("terminal_path")
                snap = ctx.mt5_sync.sync_all(target_symbols=body.get("symbols"), terminal_path=term_path)
                ok = snap.get("connection_status") == "CONNECTED"
                self._send_json(200, {"success": ok, "error": snap.get("last_error"), "snapshot": snap})
            elif path == "/api/mt5/deploy-ea":
                res = deploy_ea_pipeline(
                    project_root=ctx.project_root,
                    mt5_sync=ctx.mt5_sync,
                    executable_path=body.get("executable_path"),
                    data_folder=body.get("data_folder"),
                    experts_dir=body.get("experts_dir"),
                    compile_ea=bool(body.get("compile", True)),
                )
                self._send_json(200 if res.get("success") else 400, res)
            elif path == "/api/trades/modify":
                self._send_json(200, ctx.engine.modify_position_sl_tp(
                    ticket=int(body["ticket"]),
                    sl=float(body["sl"]),
                    tp=float(body["tp"]),
                ))
            elif path == "/api/trades/close":
                self._send_json(200, ctx.engine.close_position(
                    ticket=int(body["ticket"]),
                    confirmed=bool(body.get("confirmed", False)),
                ))
            elif path == "/api/trades/close-all-bot":
                self._send_json(200, ctx.engine.close_all_bot_positions(confirmed=bool(body.get("confirmed", False))))
            elif path == "/api/orders/cancel":
                self._send_json(200, ctx.engine.cancel_pending_order(
                    ticket=int(body["ticket"]),
                    confirmed=bool(body.get("confirmed", False)),
                ))
            elif path == "/api/config/preview":
                self._send_json(200, ctx.config_service.preview_changes(body))
            elif path == "/api/config/apply":
                try:
                    res = ctx.config_service.apply_update(
                        body.get("patch", body),
                        change_summary=str(body.get("change_summary", "Companion UI update")),
                        author=str(body.get("author", "operator")),
                    )
                    self._send_json(200, {"success": True, **res})
                except ConfigurationValidationError as exc:
                    self._send_json(400, {"success": False, "error": str(exc)})
            elif path == "/api/config/rollback":
                try:
                    res = ctx.config_service.rollback_to_version(int(body["version"]))
                    self._send_json(200, {"success": True, **res})
                except ConfigurationValidationError as exc:
                    self._send_json(400, {"success": False, "error": str(exc)})
            elif path == "/api/operations/run":
                try:
                    res = ctx.operations.run_operation(str(body["op_id"]), args=body.get("args"))
                    self._send_json(200, {"success": res["status"] == "SUCCESS", "result": res})
                except PermissionError as exc:
                    self._send_json(403, {"success": False, "error": str(exc)})
            elif path == "/api/operations/cancel":
                ok = ctx.operations.cancel_operation(str(body.get("run_key", "")))
                self._send_json(200, {"success": ok})
            elif path == "/api/errors/resolve":
                ok = ctx.repo.resolve_error(int(body["error_id"]), resolution_note=str(body.get("note", "Resolved by operator")))
                self._send_json(200, {"success": ok})
            elif path == "/api/logs/clear":
                ctx.events.clear_logs()
                self._send_json(200, {"success": True})
            elif path == "/api/btcusd/enable":
                self._send_json(200, ctx.btcusd_sample.enable())
            elif path == "/api/btcusd/disable":
                self._send_json(200, ctx.btcusd_sample.disable())
            elif path == "/api/btcusd/start":
                self._send_json(200, ctx.btcusd_sample.start())
            elif path == "/api/btcusd/stop":
                self._send_json(200, ctx.btcusd_sample.stop())
            elif path == "/api/btcusd/pause":
                self._send_json(200, ctx.btcusd_sample.pause())
            elif path == "/api/btcusd/resume":
                self._send_json(200, ctx.btcusd_sample.resume())
            elif path == "/api/btcusd/manual-test-order":
                self._send_json(200, ctx.btcusd_sample.place_manual_test_order(str(body.get("direction", ""))))
            elif path == "/api/telegram/test":
                if not ctx.telegram_notifier:
                    self._send_json(200, {"success": False, "message": "Telegram notifier not initialized"})
                else:
                    ok, msg = ctx.telegram_notifier.verify_connection()
                    if ok and body.get("send_message", True):
                        ctx.telegram_notifier.send_raw_html(
                            "🧪 <b>Institutional EA TELEGRAM TEST</b>\n\nConnection verified from Companion Control Centre (DEMO mode)."
                        )
                    self._send_json(200, {"success": ok, "message": msg})
            elif path == "/api/trades/screenshots":
                ticket = int(body.get("ticket", 0))
                symbol = re.sub(r"[^A-Za-z0-9._-]", "", str(body.get("symbol", "UNK")))
                stage = re.sub(r"[^A-Za-z0-9_-]", "", str(body.get("stage", "CAPTURE"))).upper()
                data_url = str(body.get("data_url", ""))
                if not data_url.startswith("data:image/png;base64,") or ticket <= 0:
                    self._send_json(400, {"success": False, "error": "Invalid ticket or PNG data_url"})
                else:
                    try:
                        b64_part = data_url.split(",", 1)[1]
                        png_bytes = base64.b64decode(b64_part)
                        shots_dir = ctx.data_dir / "data" / "screenshots"
                        shots_dir.mkdir(parents=True, exist_ok=True)
                        ts_tag = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                        fname = f"trade_{ticket}_{symbol}_{stage}_{ts_tag}.png"
                        (shots_dir / fname).write_bytes(png_bytes)
                        ctx.repo.record_trade_screenshot(ticket, symbol, stage, fname)
                        self._send_json(200, {"success": True, "filename": fname})
                    except Exception as exc:
                        self._send_json(400, {"success": False, "error": str(exc)})
            elif path == "/api/alerts/settings":
                saved = ctx.repo.save_alert_settings(body)
                self._send_json(200, {"success": True, "settings": saved})
            elif path == "/api/alerts/test":
                msg_text = "Alert Centre test notification (DEMO mode, real event pipeline active)."
                tg_status = "SKIPPED"
                if ctx.telegram_notifier:
                    ok, _ = ctx.telegram_notifier.verify_connection()
                    if ok:
                        ctx.telegram_notifier.send_raw_html(f"🔔 <b>Institutional EA Alert Test</b>\n{msg_text}")
                        tg_status = "DELIVERED"
                    else:
                        tg_status = "FAILED"
                alert_id = ctx.repo.record_alert(
                    alert_type="signal",
                    severity="INFO",
                    message=msg_text,
                    symbol="SYSTEM",
                    telegram_status=tg_status,
                )
                self._send_json(200, {"success": True, "alert_id": alert_id, "telegram_status": tg_status})
            elif path == "/api/ati/sync":
                res = ctx.ati.sync_broker_history() if ctx.ati else {"status": "UNAVAILABLE"}
                self._send_json(200, res)
            elif path == "/api/ati/audit-all":
                auds = ctx.ati.audit_all_pending() if ctx.ati else []
                self._send_json(200, {"audited_count": len(auds)})
            elif path == "/api/ati/train":
                res = ctx.ati.train_models() if ctx.ati else {"status": "UNAVAILABLE"}
                self._send_json(200, res)
            elif path == "/api/ati/approve":
                if not ctx.ati:
                    self._send_json(400, {"success": False, "error": "ATI unavailable"})
                else:
                    cand_id = str(body.get("candidate_id", ""))
                    operator = str(body.get("operator", "operator"))
                    ok, msg = ctx.ati.approve_candidate(cand_id, operator)
                    self._send_json(200 if ok else 400, {"success": ok, "message": msg})
            elif path == "/api/ati/rollback":
                if not ctx.ati:
                    self._send_json(400, {"success": False, "error": "ATI unavailable"})
                else:
                    reason = str(body.get("reason", "Operator requested rollback"))
                    ok, msg = ctx.ati.rollback_config(reason)
                    self._send_json(200 if ok else 400, {"success": ok, "message": msg})
            else:
                self._send_json(404, {"error": f"Unknown endpoint: {path}"})

    return CompanionRequestHandler


def build_control_server(
    project_root: str | Path,
    host: str = "127.0.0.1",
    port: int = 8765,
    db_path: Optional[str | Path] = None,
    token: Optional[str] = None,
    mt5_module: Any = None,
    enable_telegram_polling: bool = False,
    data_dir: Optional[str | Path] = None,
) -> tuple[ThreadingHTTPServer, ControlServiceContext]:
    bind_host = LocalAuthManager.validate_bind_host(host)
    root = Path(project_root)
    writable_root = Path(data_dir) if data_dir else root
    repo = CompanionRepository(db_path or (writable_root / "data" / "companion_control.db"))
    auth = LocalAuthManager(token=token, token_file=writable_root / "state" / "companion_token.txt")
    events = EventBus()
    cfg_dir = writable_root / "config" if (writable_root / "config" / "settings.json").exists() else (root / "config")
    config_service = ConfigurationService(cfg_dir, repo)
    cfg = config_service.get_full_config()
    settings = cfg.get("settings", {})
    mt5_sync = MT5SyncService(
        repo=repo,
        events=events,
        bridge_host=str(settings.get("bridge_host", "127.0.0.1")),
        bridge_port=int(settings.get("bridge_port", 5555)),
        bot_magic=int(settings.get("magic_number", 100101)),
        mt5_module=mt5_module,
    )
    engine = EngineController(
        project_root=root,
        repo=repo,
        events=events,
        config_service=config_service,
        mt5_sync=mt5_sync,
        data_dir=writable_root,
    )
    operations = OperationsRunner(
        project_root=root,
        repo=repo,
        events=events,
        engine_controller=engine,
    )
    tg_cfg = TelegramConfig()
    tg_notifier = TelegramNotifier(config=tg_cfg)
    tg_commands = TelegramCommandHandler(config=tg_cfg, notifier=tg_notifier) if enable_telegram_polling else None
    btcusd_sample = BTCUSDSampleTradingService(
        project_root=root,
        repo=repo,
        events=events,
        config_service=config_service,
        mt5_sync=mt5_sync,
        engine=engine,
        telegram_notifier=tg_notifier,
        telegram_commands=tg_commands,
    )
    ati_instance = None
    if AdaptiveTradingIntelligence:
        try:
            ati_instance = AdaptiveTradingIntelligence(mt5_module=mt5_module)
        except Exception:
            ati_instance = None

    ctx = ControlServiceContext(
        project_root=root,
        repo=repo,
        auth=auth,
        events=events,
        config_service=config_service,
        mt5_sync=mt5_sync,
        engine=engine,
        operations=operations,
        btcusd_sample=btcusd_sample,
        telegram_notifier=tg_notifier,
        ati=ati_instance,
        data_dir=writable_root,
        host=bind_host,
        port=int(port),
    )
    handler = create_request_handler(ctx)
    server = ThreadingHTTPServer((bind_host, int(port)), handler)
    ctx.port = int(server.server_address[1])
    return server, ctx
