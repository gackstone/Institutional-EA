"""
Entry point for the Institutional EA Local Control Service.
Runs the authenticated localhost-only HTTP/SSE API, rotating file logs,
and periodic MT5 auto-connect + synchronization loop.
"""

from __future__ import annotations

import argparse
import logging
from logging.handlers import RotatingFileHandler
import os
import signal
import sys
import threading
from pathlib import Path

from companion.service.security.auth import redact_secrets


def _default_project_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent.parent


PROJECT_ROOT = _default_project_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from companion.service.api.server import build_control_server  # noqa: E402


class _SecretRedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            record.msg = redact_secrets(str(msg))
            record.args = ()
        except Exception:
            pass
        return True


def _configure_logging(data_dir: Path) -> logging.Logger:
    logs_dir = data_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "control_service.log"

    logger = logging.getLogger("institutional_ea.control_service")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%dT%H:%M:%S")
    redact_filter = _SecretRedactingFilter()

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    file_handler.addFilter(redact_filter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)
    stream_handler.addFilter(redact_filter)
    logger.addHandler(stream_handler)
    return logger


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Institutional EA Local Control Service")
    parser.add_argument("--host", default=os.environ.get("MT5_CONTROL_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MT5_CONTROL_PORT", "8765")))
    parser.add_argument(
        "--project-root",
        default=os.environ.get("MT5_PROJECT_ROOT", str(PROJECT_ROOT)),
        help="Path to read-only project/resources root containing config/ and mql5/",
    )
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("MT5_DATA_DIR", ""),
        help="Path to writable application data directory for db, state, logs, and screenshots",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("MT5_COMPANION_TOKEN", ""),
        help="Optional explicit session token (prefer MT5_COMPANION_TOKEN env var)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    resolved_project_root = Path(args.project_root).resolve()
    resolved_data_dir = Path(args.data_dir).resolve() if args.data_dir else resolved_project_root
    logger = _configure_logging(resolved_data_dir)

    logger.info(
        "Starting Institutional EA Control Service (host=%s, port=%s, project_root=%s, data_dir=%s)",
        args.host,
        args.port,
        resolved_project_root,
        resolved_data_dir,
    )

    server, ctx = build_control_server(
        project_root=resolved_project_root,
        host=args.host,
        port=args.port,
        token=args.token or None,
        data_dir=resolved_data_dir,
        enable_telegram_polling=True,
    )
    ctx.events.log("CONTROL_SERVICE", "INFO", f"Institutional EA Control Service listening on http://{args.host}:{args.port}")
    logger.info("Control Service bound and listening on http://%s:%s", args.host, args.port)

    stop_event = threading.Event()

    def _handle_signal(signum: int, _frame: object) -> None:
        logger.info("Received signal %s; initiating clean shutdown", signum)
        stop_event.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handle_signal)
        except Exception:
            pass

    def _sync_loop() -> None:
        # Yield briefly so HTTP /health responds immediately on startup
        stop_event.wait(0.5)
        while not stop_event.is_set():
            try:
                if ctx.mt5_sync.connection_status != "CONNECTED":
                    ok = ctx.mt5_sync.connect()
                    if ok:
                        ctx.mt5_sync.sync_all()
                        logger.info("MT5 auto-connected and synced successfully")
                        stop_event.wait(3.0)
                    else:
                        backoff = ctx.mt5_sync.next_backoff_seconds()
                        stop_event.wait(backoff)
                else:
                    ctx.mt5_sync.sync_all()
                    stop_event.wait(3.0)
            except Exception as exc:
                logger.warning("Background MT5 sync error: %s", exc)
                ctx.events.log("MT5", "WARNING", f"Background sync error: {exc}")
                stop_event.wait(5.0)

    sync_thread = threading.Thread(target=_sync_loop, daemon=True, name="mt5-sync-loop")
    sync_thread.start()

    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        try:
            server.shutdown()
            server.server_close()
        except Exception:
            pass
        logger.info("Institutional EA Control Service stopped cleanly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
