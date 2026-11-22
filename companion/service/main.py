"""
Entry point for the Institutional EA Local Control Service.
Runs the authenticated localhost-only HTTP/SSE API and periodic MT5 synchronization loop.
"""

from __future__ import annotations
import argparse
import sys
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from companion.service.api.server import build_control_server


def main() -> int:
    parser = argparse.ArgumentParser(description="Institutional EA Local Control Service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    server, ctx = build_control_server(PROJECT_ROOT, host=args.host, port=args.port, enable_telegram_polling=True)
    ctx.events.log("CONTROL_SERVICE", "INFO", f"Institutional EA Control Service listening on http://{args.host}:{args.port}")

    stop_event = threading.Event()

    def _sync_loop() -> None:
        while not stop_event.is_set():
            try:
                if ctx.mt5_sync.connection_status == "CONNECTED":
                    ctx.mt5_sync.sync_all()
            except Exception as exc:
                ctx.events.log("MT5", "WARNING", f"Background sync error: {exc}")
            stop_event.wait(3.0)

    sync_thread = threading.Thread(target=_sync_loop, daemon=True)
    sync_thread.start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
