"""
Standalone Persistent Bridge Server Runner with Built-in Process Watchdog,
Environment Variable Loading, and Rotating File Logging.
"""

from __future__ import annotations
import os
import sys
import time
import socket
import logging
from logging.handlers import RotatingFileHandler
import threading
import signal
from pathlib import Path

# Clean shutdown signal handler for supervisor
def _handle_term(signum, frame):
    raise KeyboardInterrupt

try:
    signal.signal(signal.SIGTERM, _handle_term)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _handle_term)
except Exception:
    pass

# Ensure project root is in sys.path
if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", Path(sys.executable).resolve().parent))
    if hasattr(sys, "_MEIPASS"):
        sys.path.insert(0, str(sys._MEIPASS))
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env file safely
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k not in os.environ:
                        os.environ[k] = v
    except Exception as e:
        print(f"Warning: Failed to parse .env: {e}")

# Initialize safe writable directories (never write to Program Files)
try:
    from src.core.app_paths import get_logs_dir, setup_service_logger
    LOGS_DIR = get_logs_dir()
    log_file = LOGS_DIR / "bridge_service.log"
    logger = setup_service_logger("BridgeRunner", "bridge_service.log")
except Exception as e:
    import tempfile
    LOGS_DIR = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "ArcadeFX" / "MT5-OO1 Companion" / "logs"
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOGS_DIR / "bridge_service.log"
    logger = logging.getLogger("BridgeRunner")
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "[%(asctime)s.%(msecs)03d] [BridgeRunner] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    try:
        fh = RotatingFileHandler(str(log_file), maxBytes=10*1024*1024, backupCount=14, encoding="utf-8")
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    except Exception:
        pass

from src.execution.bridge_server import PersistentBridgeServer


class WatchdogManager:
    """Monitors the bridge server process. If main loop hangs for > 60s, triggers exit for restart."""
    def __init__(self, timeout_sec: float = 60.0):
        self.timeout_sec = timeout_sec
        self.last_heartbeat = time.time()
        self.is_running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True, name="BridgeWatchdog")
        self.thread.start()

    def beat(self):
        self.last_heartbeat = time.time()

    def _monitor_loop(self):
        while self.is_running:
            time.sleep(5.0)
            elapsed = time.time() - self.last_heartbeat
            if elapsed > self.timeout_sec:
                logger.critical(
                    f"[WATCHDOG_HANG_DETECTED] Bridge server main loop hung for {elapsed:.1f}s "
                    f"(> {self.timeout_sec}s threshold). Forcing process exit to trigger automatic service restart."
                )
                try:
                    sys.stderr.flush()
                    sys.stdout.flush()
                except Exception:
                    pass
                os._exit(42)  # Non-zero exit code triggers service/scheduler restart


def probe_existing_bridge(ipc_port: int = 5556) -> Optional[Dict[str, Any]]:
    """Probes whether a healthy bridge server is already running on IPC port."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1.5)
    try:
        s.connect(("127.0.0.1", ipc_port))
        s.sendall(b'{"action": "STATUS"}\n')
        rx = b""
        start_t = time.time()
        while time.time() - start_t < 2.0:
            chunk = s.recv(4096)
            if not chunk:
                break
            rx += chunk
            if b"\n" in rx:
                line = rx.split(b"\n", 1)[0].decode("utf-8", errors="ignore").strip()
                if line:
                    data = json.loads(line)
                    if data.get("status") == "SUCCESS":
                        return data
                break
    except Exception:
        pass
    finally:
        try:
            s.close()
        except Exception:
            pass
    return None


def run_startup_selfcheck(server_port: int = 5555, ipc_port: int = 5556) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Pre-flight check:
    Returns (is_free_to_bind, existing_bridge_status).
    """
    logger.info("Executing startup pre-flight check...")
    # First, test if an existing bridge is responsive on IPC port
    existing = probe_existing_bridge(ipc_port)
    if existing:
        active_cnt = existing.get("active_connections_count", 0)
        logger.info(
            f"[PREFLIGHT_PASS] Healthy MT5 Bridge Server already active and responsive on ports {server_port}/{ipc_port} "
            f"(active EA connections: {active_cnt}). Reusing existing bridge instance."
        )
        return False, existing

    # Check port 5555
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1.0)
    try:
        s.connect(("127.0.0.1", server_port))
        logger.warning(f"[PREFLIGHT_CONFLICT] Port {server_port} is occupied by another process, but IPC port {ipc_port} did not answer with valid bridge status!")
        s.close()
        return False, None
    except (ConnectionRefusedError, socket.timeout):
        logger.info(f"[PREFLIGHT_PASS] Port {server_port} is clear and ready.")
        return True, None
    except Exception as e:
        logger.info(f"[PREFLIGHT_NOTE] Port check notice: {e}")
        return True, None
    finally:
        try:
            s.close()
        except Exception:
            pass


def main():
    check_only = "--check-only" in sys.argv
    logger.info("=" * 70)
    logger.info("Initializing Persistent Bridge Server Daemon (Service Mode)...")
    logger.info(f"Working Directory: {PROJECT_ROOT}")
    logger.info(f"Python Executable: {sys.executable}")
    logger.info(f"Logging to: {log_file} (10MB rotation, keep 14 files)")
    logger.info("=" * 70)

    if check_only:
        can_bind, existing = run_startup_selfcheck(5555, 5556)
        logger.info(f"[CHECK_ONLY] Preflight result: can_bind={can_bind}, existing_healthy={existing is not None}")
        return 0

    # Initialize Watchdog
    watchdog = WatchdogManager(timeout_sec=60.0)

    restart_count = 0
    server: Optional[PersistentBridgeServer] = None

    while True:
        try:
            watchdog.beat()
            can_bind, existing = run_startup_selfcheck(5555, 5556)

            if existing:
                # Existing healthy bridge is already running. Monitor it safely.
                logger.info("Attached standby monitor to active Bridge Server. Monitoring health without port conflict...")
                while True:
                    watchdog.beat()
                    time.sleep(3.0)
                    probe = probe_existing_bridge(5556)
                    if not probe:
                        logger.warning("Active Bridge Server on 5556 stopped responding. Initiating local bridge takeover...")
                        break
                continue

            if not can_bind:
                # Unrecognized process occupying port 5555
                logger.warning("Port 5555 is occupied by an unrecognized process. Waiting for port release...")
                for _ in range(5):
                    watchdog.beat()
                    time.sleep(2.0)
                continue

            server = PersistentBridgeServer(ea_port=5555, ipc_port=5556)
            server.start()
            logger.info("Bridge Server successfully started on Ports 5555 (EA) and 5556 (IPC).")
            restart_count = 0

            # Health loop with watchdog beat
            while True:
                watchdog.beat()
                time.sleep(2.0)

        except KeyboardInterrupt:
            logger.info("Termination signal received. Shutting down gracefully...")
            if server:
                try:
                    server.stop()
                except Exception:
                    pass
            break
        except Exception as e:
            restart_count += 1
            delay = min(30, 5 + restart_count * 2)
            logger.error(f"Bridge server encountered error: {e}. Auto-restarting (#{restart_count}) in {delay}s...")
            if server:
                try:
                    server.stop()
                except Exception:
                    pass
            # Beat watchdog while backing off to prevent hang crash
            start_wait = time.time()
            while time.time() - start_wait < delay:
                watchdog.beat()
                time.sleep(2.0)


if __name__ == "__main__":
    main()
