"""
Central Bot Engine Controller for the Institutional EA Companion Control Centre.
Manages the lifecycle of the single authoritative Python trading engine (scripts/start_bot.py
or packaged mt5_trading_engine.exe) and bridge server (scripts/run_bridge_server.py or
packaged mt5_bridge_server.exe), respecting STOP.flag and state/PAUSE, preventing duplicate
engines, and exposing controlled trade/risk operations.
"""

from __future__ import annotations
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from companion.database.repository import CompanionRepository
from companion.service.configuration.config_service import ConfigurationService
from companion.service.events.event_bus import EventBus
from companion.service.mt5.sync_service import MT5SyncService
from companion.service.security.auth import redact_secrets
from src.core.app_paths import (
    get_state_dir,
    is_pid_alive,
    read_engine_heartbeat,
    read_lock_metadata,
    verify_process_identity,
)
from src.core.config import AppConfig
from src.risk.portfolio_risk import PortfolioRiskEngine


CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


class EngineController:
    def __init__(
        self,
        project_root: str | Path,
        repo: CompanionRepository,
        events: EventBus,
        config_service: ConfigurationService,
        mt5_sync: MT5SyncService,
        python_executable: Optional[Any] = None,
        data_dir: Optional[str | Path] = None,
    ):
        self.project_root = Path(project_root).resolve()
        self.data_dir = Path(data_dir).resolve() if data_dir else self.project_root
        self.repo = repo
        self.events = events
        self.config_service = config_service
        self.mt5_sync = mt5_sync

        explicit_py = (
            str(python_executable)
            if isinstance(python_executable, (str, Path))
            else None
        )
        self.python_exe = self._resolve_python_executable(explicit_py)

        self._lock = threading.RLock()
        self.bridge_proc: Optional[subprocess.Popen] = None
        self.engine_proc: Optional[subprocess.Popen] = None
        self.adopted_engine_pid: Optional[int] = None
        self._user_requested_stop: bool = False
        self._recent_engine_errors: List[str] = []

        self.engine_state: str = "STOPPED"  # STOPPED | STARTING | RUNNING | PAUSED | EMERGENCY_STOP | ERROR
        self.started_at: Optional[str] = None
        self.last_heartbeat: Optional[str] = None
        self.last_signal: Optional[Dict[str, Any]] = None
        self.last_trade: Optional[Dict[str, Any]] = None
        self.last_execution_error: Optional[str] = None

        self.stop_flag_path = self.data_dir / "STOP.flag"
        self.legacy_stop_flag_path = self.project_root / "STOP.flag"
        self.pause_flag_path = self.data_dir / "state" / "PAUSE"
        self.legacy_pause_flag_path = self.project_root / "state" / "PAUSE"

        # Authoritative Risk Engine snapshot (mirrors src/risk/portfolio_risk.py)
        if isinstance(python_executable, PortfolioRiskEngine):
            self.risk_engine = python_executable
        else:
            app_cfg = AppConfig.load_from_dir(str(self.config_service.config_dir))
            self.risk_engine = PortfolioRiskEngine(app_cfg)
        self.risk_engine.kill_switch_flag_path = str(self.stop_flag_path)

    def _resolve_python_executable(self, explicit_py: Optional[str] = None) -> str:
        """Resolves a valid Python interpreter (avoiding frozen sidecars like mt5_control_service.exe)."""
        if explicit_py and "mt5_control_service" not in Path(explicit_py).name.lower():
            return explicit_py

        is_win = os.name == "nt"
        venv_candidates = [
            self.project_root / ".venv" / ("Scripts" if is_win else "bin") / ("python.exe" if is_win else "python"),
            self.project_root.parent / ".venv" / ("Scripts" if is_win else "bin") / ("python.exe" if is_win else "python"),
        ]
        for cand in venv_candidates:
            if cand.exists():
                return str(cand)

        if not getattr(sys, "frozen", False):
            exe_name = Path(sys.executable).name.lower()
            if "python" in exe_name and Path(sys.executable).exists():
                return sys.executable

        found = shutil.which("python") or shutil.which("python3")
        return found or ("python" if is_win else "python3")

    def _resolve_component_command(
        self,
        sidecar_name: str,
        script_rel_path: str,
        extra_args: Optional[List[str]] = None,
    ) -> Optional[List[str]]:
        """
        Resolves either the Python script command (in dev mode) or the standalone frozen
        sidecar binary (in packaged installer mode). Never invokes mt5_control_service.exe as python.
        """
        args = list(extra_args or [])
        is_win = os.name == "nt"
        exe_name = f"{sidecar_name}.exe" if is_win else sidecar_name

        script_candidates = [
            self.project_root / script_rel_path,
            self.project_root.parent / script_rel_path,
        ]
        script_path = next((p for p in script_candidates if p.exists()), None)

        bin_candidates = [
            self.project_root / "bin" / exe_name,
            Path(sys.executable).resolve().parent / exe_name,
            self.project_root / "companion" / "resources" / "bin" / exe_name,
            self.project_root / "resources" / "bin" / exe_name,
        ]
        bin_path = next((p for p in bin_candidates if p.exists()), None)

        is_frozen = bool(getattr(sys, "frozen", False)) or (
            "mt5_control_service" in Path(sys.executable).name.lower()
        )

        # 1. In packaged / frozen mode (or if script isn't shipped in resources/), prefer sidecar binary
        if (is_frozen or script_path is None) and bin_path is not None:
            return [str(bin_path), *args]

        # 2. In development mode with source scripts present, run via resolved Python interpreter
        if script_path is not None and not is_frozen:
            return [self.python_exe, str(script_path), *args]

        # 3. Fallback to binary if present
        if bin_path is not None:
            return [str(bin_path), *args]

        return None

    def _build_child_env(self) -> Dict[str, str]:
        env = os.environ.copy()
        env["PROJECT_ROOT"] = str(self.project_root)
        env["MT5_PROJECT_ROOT"] = str(self.project_root)
        env["MT5_DATA_DIR"] = str(self.data_dir)
        env["MT5_APP_DATA_DIR"] = str(self.data_dir)
        env["INSTITUTIONAL_EA_APP_DATA_DIR"] = str(self.data_dir)
        env["PYTHONPATH"] = str(self.project_root)
        env["PYTHONUNBUFFERED"] = "1"
        return env

    def _state_dirs(self) -> List[Path]:
        dirs: List[Path] = []
        candidates = [self.data_dir / "state", self.project_root / "state"]
        if self.data_dir == self.project_root:
            candidates.append(get_state_dir())
        for d in candidates:
            try:
                resolved = d.resolve()
            except Exception:
                resolved = d
            if resolved not in dirs:
                dirs.append(resolved)
        return dirs

    def _is_stop_flag_present(self) -> bool:
        return (
            self.stop_flag_path.exists()
            or self.legacy_stop_flag_path.exists()
            or self.risk_engine.is_kill_switch_active()
        )

    def _is_pause_flag_present(self) -> bool:
        return self.pause_flag_path.exists() or self.legacy_pause_flag_path.exists()

    def _is_proc_alive(self, proc: Optional[subprocess.Popen]) -> bool:
        return proc is not None and proc.poll() is None

    def _discover_existing_engine_pid(self) -> Optional[int]:
        """Discover an already-running healthy engine PID from child handle, lock metadata, or heartbeat."""
        if self._is_proc_alive(self.engine_proc):
            return self.engine_proc.pid
        if self.adopted_engine_pid and verify_process_identity(self.adopted_engine_pid):
            return self.adopted_engine_pid
        for sdir in self._state_dirs():
            meta = read_lock_metadata("mt5_trading_engine", state_dir=sdir)
            if meta and isinstance(meta.get("pid"), int):
                pid = int(meta["pid"])
                if verify_process_identity(pid):
                    return pid
            hb = read_engine_heartbeat(state_dir=sdir)
            if hb and isinstance(hb.get("pid"), int):
                pid = int(hb["pid"])
                if verify_process_identity(pid):
                    return pid
        self.adopted_engine_pid = None
        return None

    def _get_active_engine_pid(self) -> Optional[int]:
        return self._discover_existing_engine_pid()

    def _refresh_state_flags(self) -> None:
        if self._is_stop_flag_present():
            self.engine_state = "EMERGENCY_STOP"
            return
        if self._get_active_engine_pid() is not None:
            if self._is_pause_flag_present():
                self.engine_state = "PAUSED"
            else:
                self.engine_state = "RUNNING"
        elif self.engine_state not in ("STARTING", "ERROR"):
            self.engine_state = "STOPPED"

    def start_engine(self, dry_run: Optional[bool] = None) -> Dict[str, Any]:
        """Starts the Bridge Server and single Trading Engine process safely and idempotently."""
        with self._lock:
            self.events.log("ENGINE", "INFO", "[START_TRACE] Hop 1: Checking safety locks and MT5 connection readiness.")
            if self._is_stop_flag_present():
                msg = "Cannot start trading engine while STOP.flag kill switch is active. Click Clear Stop first."
                self.engine_state = "EMERGENCY_STOP"
                self.repo.record_error(
                    category="RISK",
                    severity="CRITICAL",
                    component="EngineController",
                    message=msg,
                    trading_affected=True,
                    entries_blocked=True,
                    recommended_recovery="Inspect MT5 terminal, then explicitly clear STOP.flag from Dashboard or Operations.",
                    user_action_required=True,
                )
                return {"success": False, "message": msg, "state": self.engine_state}

            cfg = self.config_service.get_full_config()
            op_mode = str(cfg.get("operating_mode", "DRY_RUN")).upper()
            if op_mode in ("LIVE", "REAL") or cfg.get("settings", {}).get("LIVE_TRADING_ENABLED", False):
                msg = "Safety Lock: Live trading mode is permanently blocked (DEMO ONLY)."
                return {"success": False, "message": msg, "state": self.engine_state}

            snap = self.mt5_sync.get_snapshot()
            if snap.get("connection_status") != "CONNECTED":
                msg = "MT5 not connected. Click Connect MT5 first."
                return {"success": False, "message": msg, "state": self.engine_state}

            use_dry_run = (op_mode in ("DRY_RUN", "OBSERVE")) if dry_run is None else dry_run
            acc = snap.get("account", {})

            if op_mode in ("DEMO_SCALPING", "DEMO_FAST", "DEMO_MANUAL_ASSIST", "BTCUSD_DEMO_SAMPLE_MODE") and not use_dry_run:
                if acc.get("account_number") and not acc.get("demo_verified", False):
                    msg = "Safety Lock: Connected MT5 account is not verified as DEMO. Switch to a DEMO account."
                    return {"success": False, "message": msg, "state": self.engine_state}
                if acc.get("netting_observe_only", False):
                    use_dry_run = True
                    self.events.log("ENGINE", "WARNING", "Netting account detected: forcing OBSERVE/DRY-RUN safety mode.")

            self.events.log("ENGINE", "INFO", "[START_TRACE] Hop 2: Checking for existing active engine instance.")
            existing_pid = self._discover_existing_engine_pid()
            if existing_pid is not None:
                self.adopted_engine_pid = existing_pid
                self._user_requested_stop = False
                self.last_execution_error = None
                self._refresh_state_flags()
                self.events.log("ENGINE", "INFO", f"ENGINE_ALREADY_RUNNING: Adopting healthy engine (PID {existing_pid}).")
                self.events.publish_event("engine_state", self.get_status())
                return {
                    "success": True,
                    "message": f"Trading engine already running (PID {existing_pid}).",
                    "state": self.engine_state,
                    "pid": existing_pid,
                    "adopted": True,
                }

            engine_cmd = self._resolve_component_command(
                "mt5_trading_engine",
                "scripts/start_bot.py",
                ["--dry-run"] if use_dry_run else [],
            )
            if not engine_cmd:
                msg = "Trading engine executable (mt5_trading_engine) or scripts/start_bot.py not found."
                self.engine_state = "ERROR"
                self.last_execution_error = msg
                self.events.log("ENGINE", "ERROR", msg)
                self.events.publish_event("engine_state", self.get_status())
                return {"success": False, "message": msg, "state": self.engine_state}

            self._user_requested_stop = False
            self.last_execution_error = None
            self._recent_engine_errors.clear()
            self.engine_state = "STARTING"
            self.events.publish_event("engine_state", self.get_status())

            # Clear any leftover stop flag file before spawning
            for sdir in self._state_dirs():
                try:
                    (sdir / "engine_stop.flag").unlink(missing_ok=True)
                except Exception:
                    pass

            child_env = self._build_child_env()
            child_cwd = str(self.project_root if self.project_root.exists() else self.data_dir)

            # 1. Start Bridge Server if not already running on port 5556
            self.events.log("ENGINE", "INFO", "[START_TRACE] Hop 3: Verifying ZMQ/TCP Bridge on ports 5555/5556.")
            zmq_now = self.mt5_sync.check_zmq_bridge()
            if not self._is_proc_alive(self.bridge_proc) and not zmq_now.get("port_5556"):
                bridge_cmd = self._resolve_component_command(
                    "mt5_bridge_server",
                    "scripts/run_bridge_server.py",
                )
                if bridge_cmd:
                    try:
                        self.bridge_proc = subprocess.Popen(
                            bridge_cmd,
                            cwd=child_cwd,
                            env=child_env,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            creationflags=CREATE_NO_WINDOW,
                        )
                        self._stream_process_logs("BRIDGE", self.bridge_proc)
                    except Exception as br_exc:
                        self.events.log("BRIDGE", "WARNING", f"Bridge spawn notice: {br_exc}")

            # 2. Start Trading Engine (single instance enforced by start_bot.py)
            self.events.log("ENGINE", "INFO", "[START_TRACE] Hop 4: Spawning Trading Engine process.")
            try:
                self.engine_proc = subprocess.Popen(
                    engine_cmd,
                    cwd=child_cwd,
                    env=child_env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    creationflags=CREATE_NO_WINDOW,
                )
            except Exception as spawn_exc:
                msg = f"Failed to start trading engine process: {spawn_exc}"
                self.engine_state = "ERROR"
                self.last_execution_error = msg
                self.events.log("ENGINE", "ERROR", msg)
                self.events.publish_event("engine_state", self.get_status())
                return {"success": False, "message": msg, "state": self.engine_state}

            self.started_at = datetime.now(timezone.utc).isoformat()
            self.last_heartbeat = self.started_at
            self._stream_process_logs("ENGINE", self.engine_proc)

            # Wait briefly (up to 0.9s) to verify the process did not crash immediately on startup
            verify_deadline = time.time() + 0.9
            while time.time() < verify_deadline:
                if self.engine_proc.poll() is not None:
                    break
                time.sleep(0.1)

            rc = self.engine_proc.poll()
            if rc is not None:
                # Check if it exited 0 because an existing instance already held the single-instance lock
                adopted_pid = self._discover_existing_engine_pid()
                if rc == 0 and adopted_pid is not None:
                    self.adopted_engine_pid = adopted_pid
                    self._refresh_state_flags()
                    self.events.publish_event("engine_state", self.get_status())
                    return {
                        "success": True,
                        "message": f"Trading engine running (adopted PID {adopted_pid}).",
                        "state": self.engine_state,
                        "pid": adopted_pid,
                        "adopted": True,
                    }
                detail = self._recent_engine_errors[-1] if self._recent_engine_errors else f"exit code {rc}"
                msg = f"Trading engine failed to start ({detail}). Check Event Logs."
                self.engine_state = "ERROR"
                self.last_execution_error = msg
                self.events.log("ENGINE", "ERROR", msg)
                self.events.publish_event("engine_state", self.get_status())
                return {"success": False, "message": msg, "state": self.engine_state}

            self.engine_state = "PAUSED" if self._is_pause_flag_present() else "RUNNING"
            self.mt5_sync.check_zmq_bridge()

            self.repo.record_audit(
                actor="operator",
                action="ENGINE_START",
                component="EngineController",
                details=f"Started engine PID={self.engine_proc.pid}, mode={op_mode}, dry_run={use_dry_run}",
            )
            self.events.log(
                "ENGINE",
                "INFO",
                f"Trading Engine started (PID {self.engine_proc.pid}, mode={op_mode}, dry_run={use_dry_run})",
            )
            self.events.publish_event("engine_state", self.get_status())

            start_msg = "Trading engine started."
            if not use_dry_run and acc.get("autotrading_enabled") is False:
                start_msg = (
                    "Trading engine started (Notice: Enable 'Algo Trading' in MT5 toolbar for order execution)."
                )
            return {
                "success": True,
                "message": start_msg,
                "state": self.engine_state,
                "pid": self.engine_proc.pid,
            }

    def _stream_process_logs(self, component: str, proc: subprocess.Popen) -> None:
        def _reader():
            if not proc.stdout:
                return
            saw_duplicate_guard = False
            last_error_line = ""
            try:
                for line in iter(proc.stdout.readline, ""):
                    txt = line.strip()
                    if txt:
                        if "[SINGLE_INSTANCE]" in txt or "ENGINE_DUPLICATE_START_BLOCKED" in txt:
                            saw_duplicate_guard = True
                        sev = (
                            "ERROR"
                            if ("[ERROR]" in txt or "Traceback" in txt or "error:" in txt.lower())
                            else ("WARNING" if "[WARNING]" in txt else "INFO")
                        )
                        safe_txt = redact_secrets(txt)
                        if sev == "ERROR":
                            last_error_line = safe_txt
                            if component == "ENGINE":
                                self._recent_engine_errors.append(safe_txt)
                                if len(self._recent_engine_errors) > 10:
                                    self._recent_engine_errors.pop(0)
                        self.events.log(component, sev, safe_txt)
                        self.last_heartbeat = datetime.now(timezone.utc).isoformat()
            finally:
                try:
                    proc.stdout.close()
                except Exception:
                    pass
            try:
                rc = proc.wait(timeout=2.0)
            except Exception:
                rc = proc.poll()

            if component == "ENGINE" and rc == 0 and saw_duplicate_guard:
                existing_pid = self._discover_existing_engine_pid()
                if existing_pid is not None:
                    self.adopted_engine_pid = existing_pid
                    self._refresh_state_flags()
                    self.events.log(
                        "ENGINE",
                        "INFO",
                        f"ENGINE_DUPLICATE_START_BLOCKED: Adopted active engine PID {existing_pid}.",
                    )
                    self.events.publish_event("engine_state", self.get_status())
                    return

            if rc not in (None, 0) and not self._user_requested_stop:
                err_summary = (
                    f"{component} process exited with code {rc}"
                    + (f" ({last_error_line})" if last_error_line else "")
                )
                self.events.log(component, "ERROR", err_summary)
                if component == "ENGINE":
                    self.engine_state = "ERROR"
                    self.last_execution_error = err_summary
                self.repo.record_error(
                    category="EXECUTION",
                    severity="CRITICAL",
                    component=component,
                    message=err_summary,
                    trading_affected=(component == "ENGINE"),
                    entries_blocked=(component == "ENGINE"),
                    recommended_recovery="Inspect Event Logs and restart the engine cleanly.",
                    user_action_required=False,
                )
                self.events.publish_event("engine_state", self.get_status())

        t = threading.Thread(target=_reader, daemon=True)
        t.start()

    def pause_entries(self) -> Dict[str, Any]:
        with self._lock:
            ts = f"PAUSED_AT={datetime.now(timezone.utc).isoformat()}\n"
            for p_flag in (self.pause_flag_path, self.legacy_pause_flag_path):
                try:
                    p_flag.parent.mkdir(parents=True, exist_ok=True)
                    p_flag.write_text(ts, encoding="utf-8")
                except Exception:
                    pass
            self.risk_engine.pause_trading("Paused by operator via Companion Control Centre")
            self._refresh_state_flags()
            self.repo.record_audit(
                "operator",
                "PAUSE_ENTRIES",
                "EngineController",
                "New entries paused; position protection remains active.",
            )
            self.events.log(
                "ENGINE",
                "WARNING",
                "New trade entries PAUSED. Existing position protection remains active.",
            )
            self.events.publish_event("engine_state", self.get_status())
            return {
                "success": True,
                "message": "New entries paused (position management active).",
                "state": self.engine_state,
            }

    def resume_entries(self) -> Dict[str, Any]:
        with self._lock:
            if self._is_stop_flag_present():
                return {
                    "success": False,
                    "message": "Cannot resume while STOP.flag emergency kill switch is active.",
                    "state": "EMERGENCY_STOP",
                }
            for p_flag in (self.pause_flag_path, self.legacy_pause_flag_path):
                try:
                    if p_flag.exists():
                        p_flag.unlink()
                except Exception:
                    pass
            self.risk_engine.resume_trading()
            self._refresh_state_flags()
            self.repo.record_audit(
                "operator", "RESUME_ENTRIES", "EngineController", "Trade entries resumed."
            )
            self.events.log("ENGINE", "INFO", "Trade entries RESUMED.")
            self.events.publish_event("engine_state", self.get_status())
            return {
                "success": True,
                "message": "Trade entries resumed.",
                "state": self.engine_state,
            }

    def stop_engine(self) -> Dict[str, Any]:
        """Gracefully stops the Trading Engine (spawned or adopted) and Bridge Server."""
        with self._lock:
            self._user_requested_stop = True
            stop_req_ts = f"STOP_REQUESTED={datetime.now(timezone.utc).isoformat()}\n"
            stop_flags = [sdir / "engine_stop.flag" for sdir in self._state_dirs()]
            for sf in stop_flags:
                try:
                    sf.parent.mkdir(parents=True, exist_ok=True)
                    sf.write_text(stop_req_ts, encoding="utf-8")
                except Exception:
                    pass

            active_pid = self._discover_existing_engine_pid()
            if active_pid is not None:
                deadline = time.time() + 4.0
                while time.time() < deadline and is_pid_alive(active_pid):
                    time.sleep(0.2)
                if is_pid_alive(active_pid) and self._is_proc_alive(self.engine_proc):
                    try:
                        self.engine_proc.terminate()
                        self.engine_proc.wait(timeout=3)
                    except Exception:
                        try:
                            self.engine_proc.kill()
                        except Exception:
                            pass
                elif is_pid_alive(active_pid) and os.name == "nt":
                    try:
                        subprocess.run(
                            ["taskkill", "/PID", str(active_pid), "/T", "/F"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            creationflags=CREATE_NO_WINDOW,
                            timeout=5,
                        )
                    except Exception:
                        pass
                self.events.log(
                    "ENGINE",
                    "INFO",
                    f"ENGINE_STOPPED: Engine process (PID {active_pid}) stopped cleanly.",
                )

            if self._is_proc_alive(self.bridge_proc):
                try:
                    self.bridge_proc.terminate()
                    self.bridge_proc.wait(timeout=6)
                except Exception:
                    try:
                        self.bridge_proc.kill()
                    except Exception:
                        pass
                self.events.log("BRIDGE", "INFO", "BRIDGE process stopped cleanly.")

            for sf in stop_flags:
                try:
                    sf.unlink(missing_ok=True)
                except Exception:
                    pass
            self.engine_proc = None
            self.adopted_engine_pid = None
            self.bridge_proc = None
            self.last_execution_error = None
            self.engine_state = (
                "EMERGENCY_STOP" if self._is_stop_flag_present() else "STOPPED"
            )
            self.repo.record_audit(
                "operator", "ENGINE_STOP", "EngineController", "Engine stopped cleanly."
            )
            self.events.publish_event("engine_state", self.get_status())
            return {
                "success": True,
                "message": "Trading engine stopped cleanly.",
                "state": self.engine_state,
            }

    def restart_engine(self) -> Dict[str, Any]:
        self.stop_engine()
        time.sleep(0.5)
        return self.start_engine()

    def emergency_stop(
        self, close_bot_positions: bool = False, confirmed: bool = False
    ) -> Dict[str, Any]:
        """Immediately engages STOP.flag kill switch, pauses risk engine, and optionally closes bot-owned positions if confirmed."""
        with self._lock:
            ts = f"EMERGENCY_STOP={datetime.now(timezone.utc).isoformat()}\n"
            for s_flag in (self.stop_flag_path, self.legacy_stop_flag_path):
                try:
                    s_flag.write_text(ts, encoding="utf-8")
                except Exception:
                    pass
            self.risk_engine.trigger_kill_switch(
                "Emergency Stop triggered from Companion Control Centre"
            )
            self.engine_state = "EMERGENCY_STOP"
            closed_count = 0
            if close_bot_positions and confirmed:
                res = self.close_all_bot_positions(confirmed=True)
                closed_count = res.get("closed_count", 0)

            self.repo.record_audit(
                "operator",
                "EMERGENCY_STOP",
                "EngineController",
                f"STOP.flag engaged; close_bot_positions={close_bot_positions}, closed_count={closed_count}",
            )
            self.events.log(
                "RISK",
                "CRITICAL",
                f"EMERGENCY STOP ENGAGED (STOP.flag written, closed_bot_positions={closed_count}).",
            )
            self.events.publish_event("engine_state", self.get_status())
            return {
                "success": True,
                "message": "Emergency Stop engaged. New order submissions halted.",
                "state": self.engine_state,
                "closed_count": closed_count,
            }

    def clear_emergency_stop(self, confirmed: bool = False) -> Dict[str, Any]:
        if not confirmed:
            return {
                "success": False,
                "message": "Explicit confirmation required to clear STOP.flag.",
            }
        with self._lock:
            for s_flag in (self.stop_flag_path, self.legacy_stop_flag_path):
                try:
                    if s_flag.exists():
                        s_flag.unlink()
                except Exception:
                    pass
            self.risk_engine.clear_kill_switch()
            self.repo.resolve_component_errors(
                "EngineController", "Emergency STOP.flag cleared by operator"
            )
            self._refresh_state_flags()
            self.repo.record_audit(
                "operator",
                "CLEAR_EMERGENCY_STOP",
                "EngineController",
                "STOP.flag cleared.",
            )
            self.events.log("RISK", "INFO", "Emergency STOP.flag cleared by operator.")
            self.events.publish_event("engine_state", self.get_status())
            return {
                "success": True,
                "message": "Emergency stop cleared.",
                "state": self.engine_state,
            }

    def close_all_bot_positions(self, confirmed: bool = False) -> Dict[str, Any]:
        if not confirmed:
            return {
                "success": False,
                "message": "Confirmation required before closing bot-owned positions.",
                "closed_count": 0,
            }
        snap = self.mt5_sync.get_snapshot()
        bot_positions = [
            p for p in snap.get("positions", []) if p.get("ownership") == "BOT"
        ]
        closed = 0
        for p in bot_positions:
            if self.mt5_sync.bridge.is_connected():
                resp = self.mt5_sync.bridge.close_order(ticket=int(p["ticket"]))
                if isinstance(resp, dict) and resp.get("status") == "SUCCESS":
                    closed += 1

        # Reconcile with real MT5 positions before reporting success
        reconciled_snap = self.mt5_sync.sync_all()
        remaining_bot = [
            p
            for p in reconciled_snap.get("positions", [])
            if p.get("ownership") == "BOT"
        ]
        reconciled_ok = len(remaining_bot) == 0
        msg = (
            f"Closed {closed}/{len(bot_positions)} bot position(s) — reconciled with MT5 (0 remaining)."
            if reconciled_ok
            else f"Close All partially completed: {len(remaining_bot)} bot position(s) still open in MT5."
        )
        self.repo.record_audit(
            "operator",
            "CLOSE_ALL_BOT_POSITIONS",
            "EngineController",
            f"Closed {closed}/{len(bot_positions)} bot-owned positions; remaining={len(remaining_bot)}.",
        )
        return {
            "success": reconciled_ok,
            "closed_count": closed,
            "total_bot_positions": len(bot_positions),
            "remaining_bot_positions": len(remaining_bot),
            "reconciled": True,
            "message": msg,
        }

    def modify_position_sl_tp(self, ticket: int, sl: float, tp: float) -> Dict[str, Any]:
        if not self.mt5_sync.bridge.is_connected():
            return {"success": False, "message": "MT5 Bridge not connected."}
        res = self.mt5_sync.bridge.modify_order(
            ticket=int(ticket), sl=float(sl), tp=float(tp)
        )
        ok = isinstance(res, dict) and res.get("status") == "SUCCESS"
        self.repo.record_audit(
            "operator",
            "MODIFY_POSITION",
            "EngineController",
            f"Ticket #{ticket} SL={sl} TP={tp} ok={ok}",
        )
        return {
            "success": ok,
            "message": (res or {}).get("message", "Modify dispatched"),
            "response": res,
        }

    def close_position(self, ticket: int, confirmed: bool = False) -> Dict[str, Any]:
        if not confirmed:
            return {
                "success": False,
                "message": "Explicit confirmation required to close position.",
            }
        snap = self.mt5_sync.get_snapshot()
        target = next(
            (p for p in snap.get("positions", []) if int(p["ticket"]) == int(ticket)),
            None,
        )
        if target and target.get("ownership") in ("MANUAL", "OTHER_EA"):
            self.events.log(
                "ENGINE",
                "WARNING",
                f"Closing non-bot position #{ticket} ({target.get('ownership')}) per explicit user confirmation.",
            )
        if not self.mt5_sync.bridge.is_connected():
            return {"success": False, "message": "MT5 Bridge not connected."}
        res = self.mt5_sync.bridge.close_order(ticket=int(ticket))
        ok = isinstance(res, dict) and res.get("status") == "SUCCESS"
        self.repo.record_audit(
            "operator", "CLOSE_POSITION", "EngineController", f"Closed #{ticket} ok={ok}"
        )
        return {
            "success": ok,
            "message": (res or {}).get("message", "Close dispatched"),
            "response": res,
        }

    def cancel_pending_order(self, ticket: int, confirmed: bool = False) -> Dict[str, Any]:
        if not confirmed:
            return {
                "success": False,
                "message": "Explicit confirmation required to cancel pending order.",
            }
        if not self.mt5_sync.bridge.is_connected():
            return {"success": False, "message": "MT5 Bridge not connected."}
        res = self.mt5_sync.bridge.send_request(
            {"action": "CANCEL_ORDER", "ticket": int(ticket)}
        )
        ok = isinstance(res, dict) and res.get("status") == "SUCCESS"
        self.repo.record_audit(
            "operator",
            "CANCEL_PENDING_ORDER",
            "EngineController",
            f"Cancel #{ticket} ok={ok}",
        )
        return {
            "success": ok,
            "message": (res or {}).get("message", "Cancel dispatched"),
            "response": res,
        }

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            self._refresh_state_flags()
            cfg = self.config_service.get_full_config()
            sched_status = {}
            approved_universe = ["XAUUSD", "BTCUSD"]
            resolved_universe = ["XAUUSD", "BTCUSD"]
            try:
                from src.core.symbol_universe import get_symbol_universe
                from src.core.trading_schedule import get_trading_schedule

                universe = get_symbol_universe()
                schedule = get_trading_schedule()
                sched_status = schedule.get_status()
                approved_universe = universe.get_approved_symbols()
                resolved_universe = universe.get_resolved_symbols()
            except Exception:
                pass

            portfolio_capacity = {}
            try:
                from src.risk.portfolio_capacity import DynamicPortfolioCapacityEngine
                from src.core.contracts import AccountInfo, Position, OrderType

                snap = self.mt5_sync.get_snapshot()
                acc_d = snap.get("account", {})
                pos_list = snap.get("positions", [])
                ord_list = snap.get("orders", [])
                risk_cfg = cfg.get("risk", {})
                cap_eng = DynamicPortfolioCapacityEngine(
                    max_aggregate_open_risk_percent=float(
                        risk_cfg.get("max_aggregate_open_risk_percent", 6.0)
                    ),
                    max_symbol_risk_percent=float(
                        risk_cfg.get("max_symbol_risk_percent", 4.0)
                    ),
                    min_margin_level_percent=float(
                        risk_cfg.get("min_margin_level_percent", 150.0)
                    ),
                    max_margin_utilization_percent=float(
                        risk_cfg.get("max_margin_utilization_percent", 80.0)
                    ),
                )
                acc_obj = AccountInfo(
                    balance=float(acc_d.get("balance", 0.0) or 0.0),
                    equity=float(acc_d.get("equity", 0.0) or 0.0),
                    margin=float(acc_d.get("margin", 0.0) or 0.0),
                    free_margin=float(acc_d.get("free_margin", 0.0) or 0.0),
                )
                pos_objs = [
                    Position(
                        ticket=int(p.get("ticket", 0) or 0),
                        symbol=str(p.get("symbol", "")),
                        order_type=OrderType.BUY
                        if str(p.get("type", "BUY")).upper() == "BUY"
                        else OrderType.SELL,
                        volume=float(p.get("volume", 0.0) or 0.0),
                        open_price=float(p.get("open_price", 0.0) or 0.0),
                        current_price=float(p.get("current_price", 0.0) or 0.0),
                        stop_loss=float(p.get("sl") or p.get("stop_loss") or 0.0),
                        take_profit=float(p.get("tp") or p.get("take_profit") or 0.0),
                        profit=float(p.get("profit", 0.0) or 0.0),
                    )
                    for p in pos_list
                ]
                portfolio_capacity = cap_eng.compute_portfolio_snapshot(
                    account=acc_obj,
                    active_positions=pos_objs,
                    pending_orders_count=len(ord_list),
                )
            except Exception:
                pass

            active_pid = self._get_active_engine_pid()
            bridge_pid = (
                self.bridge_proc.pid if self._is_proc_alive(self.bridge_proc) else None
            )
            op_mode = cfg.get("operating_mode", "DRY_RUN")
            stop_active = self._is_stop_flag_present()
            pause_active = self._is_pause_flag_present()

            return {
                "state": self.engine_state,
                "engine_state": self.engine_state,
                "operating_mode": op_mode,
                "dry_run": op_mode in ("DRY_RUN", "OBSERVE"),
                "live_trading_locked": True,
                "stop_flag_present": stop_active,
                "stop_flag_active": stop_active,
                "pause_flag_present": pause_active,
                "pause_flag_active": pause_active,
                "engine_running": active_pid is not None,
                "bridge_running": bridge_pid is not None,
                "engine_pid": active_pid,
                "bridge_pid": bridge_pid,
                "started_at": self.started_at,
                "last_heartbeat": self.last_heartbeat,
                "last_signal": self.last_signal,
                "last_trade": self.last_trade,
                "last_execution_error": self.last_execution_error,
                "risk_state": self.risk_engine.to_dict(),
                "portfolio_capacity": portfolio_capacity,
                "circuit_breaker_active": self.risk_engine.circuit_breaker_active,
                "circuit_breaker_reason": self.risk_engine.circuit_breaker_reason,
                "approved_universe": approved_universe,
                "resolved_universe": resolved_universe,
                "schedule_mode": sched_status.get("mode", "WEEKDAY_GOLD_MODE"),
                "operating_day": sched_status.get("weekday_name", ""),
                "symbol_priorities": sched_status.get(
                    "priority_order", ["XAUUSD", "BTCUSD"]
                ),
            }

    def get_health(self) -> Dict[str, Any]:
        usage = shutil.disk_usage(self.project_root)
        db_health = self.repo.health_check()
        mt5_snap = self.mt5_sync.get_snapshot()
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "engine": self.get_status(),
            "mt5_connection": mt5_snap["connection_status"],
            "mt5_last_sync": mt5_snap["last_sync_at"],
            "database": db_health,
            "disk_free_gb": round(usage.free / (1024**3), 2),
            "disk_total_gb": round(usage.total / (1024**3), 2),
            "active_errors_count": len(self.repo.get_errors(status="ACTIVE")),
        }
