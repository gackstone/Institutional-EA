"""
Authenticated Localhost-Only Control API & SSE Event Stream for the Institutional EA Companion.
Binds exclusively to 127.0.0.1 and validates Bearer/X-Companion-Token on every request.
"""

from __future__ import annotations
import json
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from companion.database.repository import CompanionRepository
from companion.service.configuration.config_service import ConfigurationService, ConfigurationValidationError
from companion.service.events.event_bus import EventBus
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
    ):
        self.project_root = Path(project_root)
        self.repo = repo
        self.auth = auth
        self.events = events
        self.config_service = config_service
        self.mt5_sync = mt5_sync
        self.engine = engine
        self.operations = operations
        self.btcusd_sample = btcusd_sample
        self.telegram_notifier = telegram_notifier
        self.ati = ati


def create_request_handler(ctx: ControlServiceContext):
    class CompanionRequestHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            return  # Suppress noisy stdout access logs

        def _send_json(self, status_code: int, data: Any) -> None:
            body = json.dumps(data).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

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

            if path == "/healthz":
                self._send_json(200, {"status": "ok", "service": "institutional-ea-control-service"})
                return

            if not self._is_authorized(query):
                self._send_json(401, {"error": "Unauthorized: invalid or missing session token"})
                return

            if path == "/api/events":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                sub = ctx.events.subscribe()
                try:
                    # Send initial snapshot
                    init_payload = json.dumps({"type": "snapshot", "payload": ctx.engine.get_status()})
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
                ok = ctx.mt5_sync.connect()
                snap = ctx.mt5_sync.sync_all() if ok else ctx.mt5_sync.get_snapshot()
                self._send_json(200, {"success": ok, "snapshot": snap})
            elif path == "/api/mt5/sync":
                snap = ctx.mt5_sync.sync_all(target_symbols=body.get("symbols"))
                self._send_json(200, {"success": True, "snapshot": snap})
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
) -> tuple[ThreadingHTTPServer, ControlServiceContext]:
    bind_host = LocalAuthManager.validate_bind_host(host)
    root = Path(project_root)
    repo = CompanionRepository(db_path or (root / "data" / "companion_control.db"))
    auth = LocalAuthManager(token=token, token_file=root / "state" / "companion_token.txt")
    events = EventBus()
    config_service = ConfigurationService(root / "config", repo)
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
    )
    handler = create_request_handler(ctx)
    server = ThreadingHTTPServer((bind_host, int(port)), handler)
    return server, ctx
