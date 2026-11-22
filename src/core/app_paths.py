"""
Centralized, Windows-compatible Application Paths and Runtime Data Directory Management.
Ensures zero writes to Program Files or installation directory.
Works seamlessly across development, PyInstaller-packaged sidecars, and Electron.
"""

from __future__ import annotations
from datetime import datetime, timezone
import json
import os
import subprocess
import sys
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import tempfile
from typing import Optional, Dict, Any, Tuple


def get_base_app_data_dir() -> Path:
    """
    Returns the root writable application data directory:
    Windows: %LOCALAPPDATA%\\ArcadeFX\\MT5-OO1 Companion
    macOS / Linux: ~/.arcadefx/mt5-oo1-companion
    """
    override = os.environ.get("ARCADEFX_APP_DATA_DIR") or os.environ.get("MT5_APP_DATA_DIR")
    if override:
        try:
            p = Path(override).resolve()
            p.mkdir(parents=True, exist_ok=True)
            return p
        except Exception:
            pass

    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            base = Path(local_app_data) / "ArcadeFX" / "MT5-OO1 Companion"
        else:
            base = Path.home() / "AppData" / "Local" / "ArcadeFX" / "MT5-OO1 Companion"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "ArcadeFX" / "MT5-OO1 Companion"
    else:
        base = Path.home() / ".arcadefx" / "mt5-oo1-companion"

    try:
        base.mkdir(parents=True, exist_ok=True)
        return base
    except Exception as e:
        # Fallback to temp directory if user directory is inaccessible
        fallback = Path(tempfile.gettempdir()) / "ArcadeFX_MT5Companion"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


BASE_DIR = get_base_app_data_dir()


def get_logs_dir() -> Path:
    d = BASE_DIR / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_state_dir() -> Path:
    d = BASE_DIR / "state"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_credentials_dir() -> Path:
    d = BASE_DIR / "credentials"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_cache_dir() -> Path:
    d = BASE_DIR / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_runtime_dir() -> Path:
    d = BASE_DIR / "runtime"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_backups_dir() -> Path:
    d = BASE_DIR / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ensure_all_dirs() -> Dict[str, Path]:
    """Ensures that all standard subdirectories exist and are writable."""
    return {
        "base": BASE_DIR,
        "logs": get_logs_dir(),
        "state": get_state_dir(),
        "credentials": get_credentials_dir(),
        "cache": get_cache_dir(),
        "runtime": get_runtime_dir(),
        "backups": get_backups_dir(),
    }


def get_primary_credentials_file() -> Path:
    """Returns the primary credentials file location in %LOCALAPPDATA%."""
    return get_credentials_dir() / "credentials.json"


def get_legacy_credentials_files() -> list[Path]:
    """Returns possible legacy credentials paths for migration."""
    return [
        Path.home() / ".arcadefx_agent" / "credentials.enc.json",
        Path.home() / ".arcadefx_agent" / "credentials.json",
        Path.home() / ".mt5_companion" / "credentials.json",
        BASE_DIR / "credentials.enc.json"
    ]


def setup_service_logger(
    service_name: str,
    log_filename: str,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 14
) -> logging.Logger:
    """
    Creates or configures a standard rotating file logger writing to the safe logs directory.
    """
    logger = logging.getLogger(service_name)
    logger.setLevel(logging.INFO)

    # Avoid duplicate handlers if already configured
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "[%(asctime)s.%(msecs)03d] [%(name)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console stdout handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # Safe rotating file handler
    try:
        log_file = get_logs_dir() / log_filename
        fh = RotatingFileHandler(
            str(log_file),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8"
        )
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    except Exception as e:
        # Non-fatal if file logging fails; console handler remains active
        logger.warning(f"Could not initialize rotating file log at {log_filename}: {e}")

    return logger


def is_pid_alive(pid: int) -> bool:
    """Check whether a process with the given PID is currently running."""
    if not pid or pid <= 0:
        return False
    if sys.platform.startswith("win"):
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
            if not handle:
                return False
            try:
                exit_code = ctypes.c_ulong()
                if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return exit_code.value == STILL_ACTIVE
                return True
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return False
    else:
        try:
            os.kill(int(pid), 0)
            return True
        except OSError:
            return False


def get_process_image_path(pid: int) -> str:
    """Return the executable path for a running PID on Windows/POSIX, or empty string."""
    if not pid or pid <= 0:
        return ""
    if sys.platform.startswith("win"):
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
            if not handle:
                return ""
            try:
                buf_len = ctypes.c_ulong(1024)
                buf = ctypes.create_unicode_buffer(1024)
                if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(buf_len)):
                    return buf.value
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            pass
    else:
        try:
            proc_exe = Path(f"/proc/{int(pid)}/exe")
            if proc_exe.exists():
                return str(proc_exe.resolve())
        except Exception:
            pass
    return ""


def verify_process_identity(
    pid: int,
    expected_tokens: Tuple[str, ...] = ("mt5_trading_engine", "start_bot", "python"),
) -> bool:
    """Verify PID is alive and its executable/image matches expected identity tokens."""
    if not is_pid_alive(pid):
        return False
    img = get_process_image_path(pid).lower()
    if not img:
        # Process is alive but image path couldn't be queried; fall back to alive check
        return True
    return any(tok.lower() in img for tok in expected_tokens)


class SingleInstanceLock:
    """
    Robust single-instance process lock for Windows and POSIX.
    Uses non-blocking OS file locking (msvcrt on Windows, fcntl on POSIX)
    plus an unlocked companion .pid.json metadata file for safe external inspection.
    Automatically releases on process exit or crash.
    """
    def __init__(self, lock_name: str, state_dir: Optional[Path] = None):
        self.lock_name = lock_name
        self._state_dir = Path(state_dir) if state_dir is not None else get_state_dir()
        self.lock_file = self._state_dir / f"{lock_name}.lock"
        self.meta_file = self._state_dir / f"{lock_name}.pid.json"
        self._fh = None

    def acquire(self) -> bool:
        self._state_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._fh = open(self.lock_file, "a+")
            if sys.platform.startswith("win"):
                import msvcrt
                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._fh.seek(0)
            self._fh.truncate()
            self._fh.write(str(os.getpid()))
            self._fh.flush()

            # Write unlocked metadata file so external monitors can read PID & identity safely
            meta = {
                "lock_name": self.lock_name,
                "pid": os.getpid(),
                "exe": sys.executable,
                "argv": sys.argv[:4],
                "started_at": datetime.now(timezone.utc).isoformat(),
            }
            tmp_meta = self._state_dir / f".{self.lock_name}.pid.json.tmp"
            tmp_meta.write_text(json.dumps(meta, indent=2), encoding="utf-8")
            os.replace(tmp_meta, self.meta_file)
            return True
        except Exception:
            if self._fh:
                try:
                    self._fh.close()
                except Exception:
                    pass
                self._fh = None
            return False

    def release(self):
        if self._fh:
            try:
                if sys.platform.startswith("win"):
                    import msvcrt
                    self._fh.seek(0)
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
                self._fh.close()
            except Exception:
                pass
            self._fh = None
            try:
                self.lock_file.unlink(missing_ok=True)
            except Exception:
                pass
            try:
                self.meta_file.unlink(missing_ok=True)
            except Exception:
                pass


def read_lock_metadata(lock_name: str, state_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Read unlocked lock metadata (.pid.json) if present and valid."""
    sd = Path(state_dir) if state_dir is not None else get_state_dir()
    meta_file = sd / f"{lock_name}.pid.json"
    if not meta_file.exists():
        return None
    try:
        data = json.loads(meta_file.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def write_engine_heartbeat(payload: Dict[str, Any], state_dir: Optional[Path] = None) -> None:
    """Atomically write engine heartbeat JSON for supervisor/Companion health verification."""
    sd = Path(state_dir) if state_dir is not None else get_state_dir()
    sd.mkdir(parents=True, exist_ok=True)
    hb_file = sd / "engine_heartbeat.json"
    tmp_file = sd / ".engine_heartbeat.json.tmp"
    try:
        tmp_file.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp_file, hb_file)
    except Exception:
        pass


def read_engine_heartbeat(state_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Read engine heartbeat JSON if present."""
    sd = Path(state_dir) if state_dir is not None else get_state_dir()
    hb_file = sd / "engine_heartbeat.json"
    if not hb_file.exists():
        return None
    try:
        data = json.loads(hb_file.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def clear_engine_heartbeat(state_dir: Optional[Path] = None) -> None:
    """Remove engine heartbeat file on clean shutdown."""
    sd = Path(state_dir) if state_dir is not None else get_state_dir()
    hb_file = sd / "engine_heartbeat.json"
    try:
        hb_file.unlink(missing_ok=True)
    except Exception:
        pass

