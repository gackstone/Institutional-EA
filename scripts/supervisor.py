#!/usr/bin/env python3
"""
Institutional EA — MT5 Bot & Bridge Supervisor (scripts/supervisor.py)
Autonomous Windows process supervisor for 24/7 institutional trading operations.

Supervises:
  1. python scripts/run_bridge_server.py  (MT5 TCP Socket & IPC Server on ports 5555/5556)
  2. python scripts/start_bot.py          (Institutional Trading Bot Engine & Orchestrator)

Features:
  - MT5 terminal process detection gating (terminal64.exe)
  - Independent child process restart loops with exponential backoff (2s -> 60s)
  - Start order & port readiness (Bridge port 5555/5556 ready -> Bot starts)
  - Single-instance locking (Named Windows Mutex + PID lockfile with stale lock recovery)
  - Hidden background execution (CREATE_NO_WINDOW) with rotating log files (5MB, 5 backups)
  - Periodic health checks (Process alive + Socket connect probe on ports 5555/5556)
  - Clean shutdown handler without zombie processes
  - Optional EA heartbeat file gating without DLL imports (MQL5/Files/institutional_ea_heartbeat.txt)
"""

from __future__ import annotations
import sys
import os
import time
import json
import signal
import socket
import atexit
import ctypes
import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

# Resolve Project Root (guaranteed absolute path, never relying on current dir)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

LOGS_DIR = PROJECT_ROOT / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

SUPERVISOR_LOCK_FILE = LOGS_DIR / "supervisor.lock"
MUTEX_NAME = "Local\\InstitutionalEA_MT5_Supervisor_Mutex"

# Default Configuration Values
DEFAULT_POLL_INTERVAL = 3
DEFAULT_SHUTDOWN_TIMEOUT = 8
DEFAULT_BRIDGE_HOST = "127.0.0.1"
DEFAULT_BRIDGE_PORT = 5555
DEFAULT_IPC_PORT = 5556
DEFAULT_LOG_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
DEFAULT_LOG_BACKUP_COUNT = 5

# Windows Process Creation Flags
CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200


# =============================================================================
# Lightweight Rotating File Logger
# =============================================================================
class RotatingLogWriter:
    """Thread-safe rotating log writer managing 5MB rotating log files."""

    def __init__(self, filename: str | Path, max_bytes: int = DEFAULT_LOG_MAX_BYTES, backup_count: int = DEFAULT_LOG_BACKUP_COUNT):
        self.filename = str(filename)
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self._ensure_parent()

    def _ensure_parent(self):
        os.makedirs(os.path.dirname(self.filename), exist_ok=True)

    def write_line(self, tag: str, message: str, level: str = "INFO"):
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        formatted = f"[{now_str}] [{level}] [{tag}] {message}\n"
        self._rotate_if_needed(len(formatted.encode("utf-8")))

        try:
            with open(self.filename, "a", encoding="utf-8") as f:
                f.write(formatted)
        except Exception as e:
            sys.stderr.write(f"Failed to write to {self.filename}: {e}\n")

    def _rotate_if_needed(self, incoming_bytes: int):
        if not os.path.exists(self.filename):
            return

        try:
            size = os.path.getsize(self.filename)
            if size + incoming_bytes > self.max_bytes:
                for i in range(self.backup_count - 1, 0, -1):
                    sfn = f"{self.filename}.{i}"
                    dfn = f"{self.filename}.{i + 1}"
                    if os.path.exists(sfn):
                        if os.path.exists(dfn):
                            os.remove(dfn)
                        os.rename(sfn, dfn)

                dfn = f"{self.filename}.1"
                if os.path.exists(dfn):
                    os.remove(dfn)
                os.rename(self.filename, dfn)
        except Exception as e:
            sys.stderr.write(f"Log rotation error on {self.filename}: {e}\n")


sup_logger = RotatingLogWriter(LOGS_DIR / "supervisor.log")


# =============================================================================
# Configuration Loader (.env and settings.json reader)
# =============================================================================
def load_app_config() -> Dict[str, Any]:
    """Reads configuration from root .env and config/settings.json."""
    config: Dict[str, Any] = {}

    # 1. Parse .env
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        config[k.strip()] = v.strip().strip("\"'")
        except Exception as e:
            sup_logger.write_line("CONFIG", f"Error parsing .env: {e}", "WARNING")

    # 2. Parse config/settings.json
    settings_file = PROJECT_ROOT / "config" / "settings.json"
    if settings_file.exists():
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                settings = json.load(f)
                config["BRIDGE_HOST"] = config.get("BRIDGE_HOST", settings.get("bridge_host", DEFAULT_BRIDGE_HOST))
                config["BRIDGE_PORT"] = config.get("BRIDGE_PORT", settings.get("bridge_port", DEFAULT_BRIDGE_PORT))
                config["BRIDGE_SUB_PORT"] = config.get("BRIDGE_SUB_PORT", settings.get("bridge_sub_port", DEFAULT_IPC_PORT))
        except Exception as e:
            sup_logger.write_line("CONFIG", f"Error parsing settings.json: {e}", "WARNING")

    return config


# =============================================================================
# Python Interpreter Resolution
# =============================================================================
def resolve_python_executable(prefer_pythonw: bool = True) -> str:
    """
    Finds the authoritative Python interpreter:
    1. Configured SUPERVISOR_PYTHON_PATH in .env
    2. Virtualenv interpreter (.venv or venv in project root)
    3. Current running sys.executable (switching to pythonw if prefer_pythonw and on Windows)
    """
    cfg = load_app_config()
    custom_python = cfg.get("SUPERVISOR_PYTHON_PATH")
    if custom_python and os.path.exists(custom_python):
        return custom_python

    # Check for local venv in project root
    for venv_name in (".venv", "venv", "env"):
        cand_dir = PROJECT_ROOT / venv_name / "Scripts"
        if prefer_pythonw:
            w_cand = cand_dir / "pythonw.exe"
            if w_cand.exists():
                return str(w_cand)
        c_cand = cand_dir / "python.exe"
        if c_cand.exists():
            return str(c_cand)

    # Fallback to sys.executable
    cur = sys.executable
    if prefer_pythonw and os.name == "nt":
        w_cur = Path(cur).parent / "pythonw.exe"
        if w_cur.exists():
            return str(w_cur)

    return cur


# =============================================================================
# Cross-Process Single-Instance Lock (Named Mutex + Lockfile)
# =============================================================================
class SingleInstanceLock:
    def __init__(self, mutex_name: str = MUTEX_NAME, lock_file: Path | str = SUPERVISOR_LOCK_FILE):
        self.mutex_name = mutex_name
        self.lock_file = Path(lock_file)
        self.mutex_handle = None
        self.is_locked = False

    def acquire(self) -> bool:
        if os.name == "nt":
            try:
                kernel32 = ctypes.windll.kernel32
                ERROR_ALREADY_EXISTS = 183
                handle = kernel32.CreateMutexW(None, False, self.mutex_name)
                last_err = kernel32.GetLastError()
                if last_err == ERROR_ALREADY_EXISTS:
                    if handle:
                        kernel32.CloseHandle(handle)
                    return False
                self.mutex_handle = handle
            except Exception as e:
                sup_logger.write_line("LOCK", f"Mutex creation notice: {e}", "WARNING")

        # PID Lockfile validation
        if self.lock_file.exists():
            try:
                with open(self.lock_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                old_pid = data.get("pid")
                if old_pid and self._is_pid_alive(old_pid):
                    return False
                else:
                    sup_logger.write_line("LOCK", f"Reclaiming stale lockfile from dead PID {old_pid}")
            except Exception:
                pass

        try:
            with open(self.lock_file, "w", encoding="utf-8") as f:
                json.dump({
                    "pid": os.getpid(),
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "python": sys.executable
                }, f, indent=2)
            self.is_locked = True
            return True
        except Exception as e:
            sup_logger.write_line("LOCK", f"Failed to write lockfile: {e}", "ERROR")
            return False

    def release(self):
        if self.mutex_handle and os.name == "nt":
            try:
                ctypes.windll.kernel32.CloseHandle(self.mutex_handle)
            except Exception:
                pass
            self.mutex_handle = None

        if self.is_locked and self.lock_file.exists():
            try:
                self.lock_file.unlink()
            except Exception:
                pass
            self.is_locked = False

    @staticmethod
    def _is_pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        if os.name == "nt":
            try:
                PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
                if h:
                    ctypes.windll.kernel32.CloseHandle(h)
                    return True
                return False
            except Exception:
                return False
        else:
            try:
                os.kill(pid, 0)
                return True
            except OSError:
                return False


# =============================================================================
# MT5 Terminal Detection & Readiness
# =============================================================================
def is_process_running(image_names: Tuple[str, ...]) -> bool:
    """Checks if any process matching image_names is running via tasklist."""
    if os.name != "nt":
        return True

    for name in image_names:
        try:
            cmd = f'tasklist /FI "IMAGENAME eq {name}" /NH /FO CSV'
            out = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL)
            if name.lower() in out.lower():
                return True
        except Exception:
            continue
    return False


def is_mt5_terminal_active(custom_path: Optional[str] = None) -> Tuple[bool, str]:
    """
    Checks if MetaTrader 5 terminal is running on the Windows host.
    Matches terminal64.exe (standard 64-bit MT5) and terminal.exe (legacy 32-bit).
    """
    if custom_path and os.path.exists(custom_path):
        exe_name = os.path.basename(custom_path)
        if is_process_running((exe_name,)):
            return True, f"Configured terminal running ({exe_name})"

    if is_process_running(("terminal64.exe", "terminal.exe")):
        return True, "MetaTrader 5 process active (terminal64.exe)"

    return False, "MetaTrader 5 terminal is closed"


# =============================================================================
# Optional EA Heartbeat Gating (Deliverable 3)
# =============================================================================
def check_ea_heartbeat_fresh(heartbeat_path: Optional[str], max_age_seconds: int = 30) -> Tuple[bool, str]:
    """
    Checks if an Expert Advisor heartbeat file is updated within max_age_seconds.
    Zero DLL imports needed: EA writes timestamp into MQL5/Files/institutional_ea_heartbeat.txt
    """
    if not heartbeat_path:
        appdata = os.environ.get("APPDATA", "")
        terminal_base = os.path.join(appdata, "MetaQuotes", "Terminal")
        if os.path.exists(terminal_base):
            for d in os.listdir(terminal_base):
                cand = os.path.join(terminal_base, d, "MQL5", "Files", "institutional_ea_heartbeat.txt")
                if os.path.exists(cand):
                    heartbeat_path = cand
                    break

    if not heartbeat_path or not os.path.exists(heartbeat_path):
        return False, "EA heartbeat file not found"

    try:
        mtime = os.path.getmtime(heartbeat_path)
        age = time.time() - mtime
        if age <= max_age_seconds:
            return True, f"EA heartbeat fresh ({int(age)}s ago)"
        else:
            return False, f"EA heartbeat stale ({int(age)}s > {max_age_seconds}s limit)"
    except Exception as e:
        return False, f"Failed to read EA heartbeat: {e}"


# =============================================================================
# TCP Port Probe (Bridge Port Readiness)
# =============================================================================
def is_port_listening(host: str, port: int, timeout: float = 1.0) -> bool:
    """Tests if a TCP port accepts socket connections."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def wait_for_port_ready(host: str, port: int, timeout_seconds: float = 15.0) -> bool:
    """Waits until host:port accepts connections or timeout expires."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if is_port_listening(host, port, timeout=0.8):
            return True
        time.sleep(0.5)
    return False


# =============================================================================
# Child Process Specification & Health Tracker
# =============================================================================
class ChildProcessManager:
    """Manages an individual supervised child process with independent backoff."""

    def __init__(self, name: str, script_relpath: str, log_filename: str):
        self.name = name
        self.script_path = str(PROJECT_ROOT / script_relpath)
        self.log_file = str(LOGS_DIR / log_filename)
        self.log_writer = RotatingLogWriter(self.log_file)

        self.process: Optional[subprocess.Popen] = None
        self.start_time: float = 0.0
        self.backoff_delay: float = 2.0
        self.consecutive_crashes: int = 0
        self.next_allowed_start: float = 0.0
        self.last_exit_code: Optional[int] = None
        self.unresponsive_probes: int = 0

    def is_alive(self) -> bool:
        if self.process is None:
            return False
        return self.process.poll() is None

    def start(self, python_exe: str, visible: bool = False) -> bool:
        now = time.time()
        if now < self.next_allowed_start:
            wait_rem = int(self.next_allowed_start - now)
            sup_logger.write_line(self.name, f"Restart deferred by rate-limit backoff ({wait_rem}s remaining)", "INFO")
            return False

        if not os.path.exists(self.script_path):
            sup_logger.write_line(self.name, f"Script file not found: {self.script_path}", "ERROR")
            self.next_allowed_start = now + 30.0
            return False

        sup_logger.write_line(self.name, f"Starting {self.name} child process using {python_exe}...")
        self.log_writer.write_line("SUPERVISOR", f"Launching {self.name} child process...")

        creationflags = 0
        if os.name == "nt":
            creationflags = CREATE_NEW_PROCESS_GROUP
            if not visible:
                creationflags |= CREATE_NO_WINDOW

        try:
            log_fp = open(self.log_file, "a", encoding="utf-8")
            cmd = [python_exe, "-u", self.script_path]
            child_env = os.environ.copy()
            child_env["PYTHONUNBUFFERED"] = "1"

            self.process = subprocess.Popen(
                cmd,
                cwd=str(PROJECT_ROOT),
                env=child_env,
                stdout=log_fp,
                stderr=subprocess.STDOUT,
                creationflags=creationflags
            )
            try:
                log_fp.close()
            except Exception:
                pass

            self.start_time = now
            self.unresponsive_probes = 0
            sup_logger.write_line(self.name, f"Process started successfully (PID: {self.process.pid})")
            return True
        except Exception as e:
            sup_logger.write_line(self.name, f"Failed to spawn process: {e}", "ERROR")
            self.consecutive_crashes += 1
            self.backoff_delay = min(60.0, self.backoff_delay * 2.0)
            self.next_allowed_start = now + self.backoff_delay
            return False

    def stop_gracefully(self, timeout_seconds: float = DEFAULT_SHUTDOWN_TIMEOUT):
        if not self.is_alive() or self.process is None:
            self.process = None
            return

        pid = self.process.pid
        sup_logger.write_line(self.name, f"Stopping PID {pid} gracefully (timeout {timeout_seconds}s)...")

        try:
            if os.name == "nt":
                try:
                    self.process.send_signal(signal.CTRL_BREAK_EVENT)
                    self.process.wait(timeout=max(2.0, timeout_seconds / 2.0))
                    sup_logger.write_line(self.name, f"PID {pid} exited gracefully via CTRL_BREAK_EVENT.")
                    return
                except (subprocess.TimeoutExpired, OSError):
                    pass

            self.process.terminate()
            self.process.wait(timeout=max(2.0, timeout_seconds / 2.0))
            sup_logger.write_line(self.name, f"PID {pid} exited gracefully.")
        except subprocess.TimeoutExpired:
            sup_logger.write_line(self.name, f"PID {pid} did not exit in {timeout_seconds}s. Forcefully terminating...", "WARNING")
            try:
                self.process.kill()
                self.process.wait(timeout=3)
            except Exception:
                pass
        except Exception as e:
            sup_logger.write_line(self.name, f"Error stopping PID {pid}: {e}", "WARNING")
        finally:
            self.process = None

    def handle_exit_if_terminated(self) -> Optional[int]:
        """Checks if process has died, logs exit code, and recalculates backoff."""
        if self.process is None:
            return None

        ret = self.process.poll()
        if ret is None:
            if time.time() - self.start_time >= 60.0 and self.consecutive_crashes > 0:
                sup_logger.write_line(self.name, f"Child sustained healthy execution for >60s. Resetting crash backoff to 2s.")
                self.consecutive_crashes = 0
                self.backoff_delay = 2.0
            return None

        now = time.time()
        self.last_exit_code = ret
        pid = self.process.pid
        self.process = None

        if ret == 0:
            sup_logger.write_line(self.name, f"Child PID {pid} exited cleanly (code 0).")
            self.next_allowed_start = now + 5.0
        else:
            self.consecutive_crashes += 1
            sup_logger.write_line(
                self.name,
                f"Child PID {pid} crashed with exit code {ret} (Crash count: {self.consecutive_crashes}). Backing off for {int(self.backoff_delay)}s.",
                "ERROR"
            )
            self.next_allowed_start = now + self.backoff_delay
            self.backoff_delay = min(60.0, self.backoff_delay * 2.0)

        return ret


# =============================================================================
# Main Supervisor Engine
# =============================================================================
class InstitutionalEaSupervisor:
    def __init__(self, visible: bool = False):
        self.visible = visible
        self.config = load_app_config()
        self.require_mt5 = str(self.config.get("SUPERVISOR_REQUIRE_MT5", "true")).lower() in ("true", "1", "yes")
        self.require_ea = str(self.config.get("SUPERVISOR_REQUIRE_EA_HEARTBEAT", "false")).lower() in ("true", "1", "yes")
        self.ea_heartbeat_path = self.config.get("EA_HEARTBEAT_PATH")
        self.mt5_custom_path = self.config.get("MT5_TERMINAL_PATH")
        self.poll_interval = int(self.config.get("SUPERVISOR_POLL_INTERVAL", str(DEFAULT_POLL_INTERVAL)))
        self.bridge_host = str(self.config.get("BRIDGE_HOST", DEFAULT_BRIDGE_HOST))
        self.bridge_port = int(self.config.get("BRIDGE_PORT", str(DEFAULT_BRIDGE_PORT)))
        self.ipc_port = int(self.config.get("BRIDGE_SUB_PORT", str(DEFAULT_IPC_PORT)))

        self.python_exe = resolve_python_executable(prefer_pythonw=not self.visible)
        self.lock = SingleInstanceLock()
        self.running = True

        self.bridge_child = ChildProcessManager("bridge", "scripts/run_bridge_server.py", "bridge.log")
        self.bot_child = ChildProcessManager("bot", "scripts/start_bot.py", "bot.log")

    def _kill_orphaned_children(self):
        """Terminates any orphan bot or bridge scripts from a previously crashed supervisor."""
        if os.name != "nt":
            return

        sup_logger.write_line("SUPERVISOR", "Scanning for orphaned python bridge or bot processes...")

        # 1. Check if bridge port is held by an old process
        for check_port in (self.bridge_port, self.ipc_port):
            if is_port_listening(self.bridge_host, check_port, timeout=0.5):
                sup_logger.write_line("CLEANUP", f"Port {check_port} is already active. Checking for orphan owner...", "WARNING")
                try:
                    cmd = f'netstat -ano | findstr :{check_port}'
                    out = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL)
                    for line in out.splitlines():
                        parts = line.strip().split()
                        if len(parts) >= 5 and "LISTENING" in parts:
                            pid = int(parts[-1])
                            if pid != os.getpid():
                                subprocess.run(f"taskkill /PID {pid} /F", shell=True, capture_output=True)
                                sup_logger.write_line("CLEANUP", f"Terminated orphan holding port {check_port} (PID: {pid})")
                except Exception as e:
                    sup_logger.write_line("CLEANUP", f"Port cleanup notice: {e}", "DEBUG")

        # 2. Check for leftover orphan python children running start_bot.py or run_bridge_server.py
        try:
            ps_cmd = (
                f'powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \\"Name like \'python%\'\\" | '
                f'Where-Object {{ ($_.CommandLine -like \'*start_bot.py*\' -or $_.CommandLine -like \'*run_bridge_server.py*\') '
                f'-and $_.ProcessId -ne {os.getpid()} }} | '
                f'ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force; Write-Output $_.ProcessId }}"'
            )
            out = subprocess.check_output(ps_cmd, shell=True, text=True, stderr=subprocess.DEVNULL)
            for line in out.splitlines():
                line = line.strip()
                if line.isdigit():
                    sup_logger.write_line("CLEANUP", f"Cleaned up stale orphan process PID {line}")
        except Exception as e:
            sup_logger.write_line("CLEANUP", f"Orphan scan notice: {e}", "DEBUG")

    def handle_shutdown(self, signum=None, frame=None):
        if not self.running:
            return
        self.running = False
        sig_str = f"signal {signum}" if signum is not None else "shutdown request"
        sup_logger.write_line("SUPERVISOR", f"Supervisor shutting down on {sig_str}...")

        # Gracefully stop child processes in reverse dependency order
        self.bot_child.stop_gracefully()
        self.bridge_child.stop_gracefully()

        self.lock.release()
        sup_logger.write_line("SUPERVISOR", "All child processes terminated. Supervisor exit 0.")
        sys.exit(0)

    def register_signals(self):
        try:
            signal.signal(signal.SIGINT, self.handle_shutdown)
            signal.signal(signal.SIGTERM, self.handle_shutdown)
            if hasattr(signal, "SIGBREAK"):
                signal.signal(signal.SIGBREAK, self.handle_shutdown)
        except Exception as e:
            sup_logger.write_line("SUPERVISOR", f"Signal registration warning: {e}", "WARNING")

        if os.name == "nt":
            try:
                HandlerRoutine = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)

                def _console_ctrl_handler(ctrl_type):
                    sup_logger.write_line("SUPERVISOR", f"Windows Console Event received (Code: {ctrl_type}). Shutting down...")
                    self.handle_shutdown(signum=ctrl_type)
                    return True

                self._ctrl_handler_ref = HandlerRoutine(_console_ctrl_handler)
                ctypes.windll.kernel32.SetConsoleCtrlHandler(self._ctrl_handler_ref, True)
            except Exception as e:
                sup_logger.write_line("SUPERVISOR", f"Console handler warning: {e}", "DEBUG")

        atexit.register(self.handle_shutdown)

    def check_health(self):
        """Performs periodic health probe on children."""
        # Probe Bridge process and socket port
        if self.bridge_child.is_alive():
            if not is_port_listening(self.bridge_host, self.bridge_port, timeout=1.0) and not is_port_listening(self.bridge_host, self.ipc_port, timeout=1.0):
                self.bridge_child.unresponsive_probes += 1
                if self.bridge_child.unresponsive_probes >= 5:
                    sup_logger.write_line("HEALTH", f"Bridge process is alive but ports {self.bridge_port}/{self.ipc_port} are unresponsive. Restarting...", "WARNING")
                    self.bridge_child.stop_gracefully()
            else:
                self.bridge_child.unresponsive_probes = 0

    def run(self):
        if not self.lock.acquire():
            sup_logger.write_line("LOCK", "Another supervisor instance is already running. Exiting.", "WARNING")
            print("Another Institutional EA supervisor instance is already active.", file=sys.stderr)
            sys.exit(0)

        self.register_signals()
        sup_logger.write_line("SUPERVISOR", f"Institutional EA Supervisor started (PID: {os.getpid()})")
        sup_logger.write_line("SUPERVISOR", f"Python Interpreter: {self.python_exe}")
        sup_logger.write_line("SUPERVISOR", f"MT5 Gating Required: {self.require_mt5} | EA Heartbeat Required: {self.require_ea}")

        self._kill_orphaned_children()

        while self.running:
            try:
                # 1. Determine if conditions permit running (MT5 gating & optional EA gating)
                should_run = True
                status_reason = "Conditions met"

                if self.require_mt5:
                    mt5_ok, mt5_reason = is_mt5_terminal_active(self.mt5_custom_path)
                    if not mt5_ok:
                        should_run = False
                        status_reason = mt5_reason

                if should_run and self.require_ea:
                    ea_ok, ea_reason = check_ea_heartbeat_fresh(self.ea_heartbeat_path)
                    if not ea_ok:
                        should_run = False
                        status_reason = ea_reason

                # 2. Reconcile desired state with actual child processes
                if not should_run:
                    if self.bot_child.is_alive():
                        sup_logger.write_line("GATING", f"{status_reason}. Stopping Bot Engine...")
                        self.bot_child.stop_gracefully()

                    if self.bridge_child.is_alive():
                        sup_logger.write_line("GATING", f"{status_reason}. Stopping Bridge Server...")
                        self.bridge_child.stop_gracefully()

                else:
                    # Poll for child exits & backoff
                    self.bridge_child.handle_exit_if_terminated()
                    self.bot_child.handle_exit_if_terminated()

                    # Start Order: 1. Bridge Server first
                    if not self.bridge_child.is_alive():
                        self.bridge_child.start(self.python_exe, self.visible)
                        if self.bridge_child.is_alive():
                            sup_logger.write_line("SUPERVISOR", f"Waiting for bridge ports {self.bridge_port}/{self.ipc_port} to accept connections...")
                            port_ok = wait_for_port_ready(self.bridge_host, self.bridge_port, timeout_seconds=15.0) or wait_for_port_ready(self.bridge_host, self.ipc_port, timeout_seconds=2.0)
                            if port_ok:
                                sup_logger.write_line("SUPERVISOR", f"Bridge ports are ready.")
                            else:
                                sup_logger.write_line("SUPERVISOR", f"Bridge port readiness timed out. Will probe in next loop.", "WARNING")

                    # Start Order: 2. Bot Engine starts once Bridge is ready
                    if self.bridge_child.is_alive() and not self.bot_child.is_alive():
                        if is_port_listening(self.bridge_host, self.bridge_port, timeout=0.8) or is_port_listening(self.bridge_host, self.ipc_port, timeout=0.8):
                            self.bot_child.start(self.python_exe, self.visible)

                    # 3. Perform periodic health check on running children
                    self.check_health()

                time.sleep(self.poll_interval)

            except SystemExit:
                break
            except Exception as e:
                sup_logger.write_line("SUPERVISOR", f"Unhandled loop exception: {e}", "ERROR")
                time.sleep(5)

        self.handle_shutdown()


def main():
    parser = argparse.ArgumentParser(description="Institutional EA MT5 Bot & Bridge Supervisor")
    parser.add_argument("--visible", action="store_true", help="Launch children with visible terminal consoles (debug mode)")
    args = parser.parse_args()

    supervisor = InstitutionalEaSupervisor(visible=args.visible)
    supervisor.run()


if __name__ == "__main__":
    main()
