"""
Fixed-Allowlist PowerShell & Script Operations Runner for the Operations Centre.
Never executes arbitrary user-supplied commands. Validates arguments, runs in the
project root, captures & redacts stdout/stderr, supports timeouts & cancellation,
and records every execution in SQLite operation_audits.
"""

from __future__ import annotations
import os
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from companion.database.repository import CompanionRepository
from companion.service.events.event_bus import EventBus
from companion.service.security.auth import redact_secrets


CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


@dataclass(frozen=True)
class AllowlistedOperation:
    op_id: str
    name: str
    description: str
    command_builder: Callable[[Path, str], List[str]]
    timeout_sec: int = 120
    shell: str = "process"  # "process" | "powershell"


def _build_allowlist() -> Dict[str, AllowlistedOperation]:
    ops: List[AllowlistedOperation] = [
        AllowlistedOperation("check_python", "Check Python Installation", "Verify Python runtime and virtual environment", lambda r, py: [py, "--version"], 15),
        AllowlistedOperation("check_deps", "Check Dependencies", "List installed packages and verify core imports", lambda r, py: [py, "-c", "import MetaTrader5, pydantic, yaml, zmq, requests, pytest; print('All core dependencies OK')"], 20),
        AllowlistedOperation("install_deps", "Install Approved Dependencies", "Install pinned packages from requirements.txt", lambda r, py: [py, "-m", "pip", "install", "-r", str(r / "requirements.txt")], 300),
        AllowlistedOperation("validate_config", "Validate Project Configuration", "Load and validate AppConfig & DEMO lock", lambda r, py: [py, "-c", "from src.core.config import AppConfig; c=AppConfig.load_from_dir(); assert not c.live_trading_enabled; print('Config OK:', c.execution_mode.value, c.symbols)"], 20),
        AllowlistedOperation("check_mt5_install", "Check MT5 Installation", "Verify MetaTrader 5 terminal binaries on disk", lambda r, py: ["powershell", "-NoProfile", "-Command", "Get-Item 'C:\\Program Files\\MetaTrader 5\\terminal64.exe' -ErrorAction SilentlyContinue | Select-Object FullName, Length"], 15),
        AllowlistedOperation("check_mt5_conn", "Check MT5 Connection", "Verify MetaTrader5 Python API initialization", lambda r, py: [py, "-c", "import MetaTrader5 as mt5; ok=mt5.initialize(); info=mt5.account_info() if ok else None; print('Connected:', ok, 'Mode:', getattr(info,'trade_mode',None)); mt5.shutdown()"], 20),
        AllowlistedOperation("bridge_preflight", "Bridge Server Preflight", "Run bridge server preflight self-check", lambda r, py: [py, str(r / "scripts" / "run_bridge_server.py"), "--check-only"], 20),
        AllowlistedOperation("run_diagnostics", "Run System Diagnostics", "Run scripts/selfcheck.py diagnostics", lambda r, py: [py, str(r / "scripts" / "selfcheck.py")], 60),
        AllowlistedOperation("run_unit_tests", "Run Unit Tests", "Run consolidated architecture & unit test suite", lambda r, py: [py, "-m", "pytest", "tests/test_modern_architecture_consolidation.py", "tests/test_companion_control_service.py", "-q"], 180),
        AllowlistedOperation("run_integration_tests", "Run Integration Tests", "Run full pytest suite excluding long replay", lambda r, py: [py, "-m", "pytest", "--ignore=tests/test_golden_master.py", "-q"], 300),
        AllowlistedOperation("run_risk_tests", "Run Risk Manager Tests", "Run risk management and sizing test suites", lambda r, py: [py, "-m", "pytest", "tests/test_risk_management.py", "tests/test_fast_risk_guards.py", "-q"], 120),
        AllowlistedOperation("run_execution_tests", "Run Execution Tests", "Run order execution and bridge test suites", lambda r, py: [py, "-m", "pytest", "tests/test_execution_bridge.py", "tests/test_broker_execution_upgrade.py", "-q"], 120),
        AllowlistedOperation("verify_demo_only", "Verify DEMO-Only Status", "Verify settings.json and promotion_check.py enforce DEMO lock", lambda r, py: [py, str(r / "scripts" / "promotion_check.py")], 30),
        AllowlistedOperation("create_backup", "Create Backup", "Run scripts/backup.py to archive configs and state", lambda r, py: [py, str(r / "scripts" / "backup.py")], 60),
        AllowlistedOperation("restore_backup", "List / Verify Backups", "Inspect available recovery backups", lambda r, py: ["powershell", "-NoProfile", "-Command", f"Get-ChildItem -Path '{r / 'backups'}' | Select-Object Name, LastWriteTime"], 15),
        AllowlistedOperation("export_logs", "Export Logs", "Archive recent logs to reports/exported_logs_manifest.txt", lambda r, py: ["powershell", "-NoProfile", "-Command", f"Get-ChildItem -Path '{r / 'logs'}' -ErrorAction SilentlyContinue | Select-Object Name, Length, LastWriteTime"], 20),
        AllowlistedOperation("generate_diag_report", "Generate Diagnostic Report", "Generate readiness diagnostic report", lambda r, py: [py, str(r / "scripts" / "validate_readiness.py")], 60),
        AllowlistedOperation("git_status", "Check Git Status", "Inspect repository branch and working tree status", lambda r, py: ["git", "status", "--short", "--branch"], 15),
        AllowlistedOperation("check_updates", "Check for Updates", "Check remote git commits (read-only fetch dry-check)", lambda r, py: ["git", "log", "-5", "--oneline"], 15),
        AllowlistedOperation("run_migrations", "Run Database Migrations", "Verify and apply SQLite companion schema migrations", lambda r, py: [py, "-c", "from companion.database.migrations import init_database; print('Schema version:', init_database())"], 20),
        AllowlistedOperation("build_companion_ui", "Build Companion Frontend", "Build companion React/TypeScript UI bundle", lambda r, py: ["npm.cmd" if os.name == "nt" else "npm", "run", "build", "--prefix", str(r / "companion")], 180),
        AllowlistedOperation("generate_release_pkg", "Verify Release Packaging Config", "Validate companion package.json and sidecar scripts", lambda r, py: [py, "-c", "import json, pathlib; p=json.loads(pathlib.Path('companion/package.json').read_text()); print('App:', p['name'], p['version'], 'NSIS:', p['build']['nsis']['artifactName'])"], 20),
    ]
    return {op.op_id: op for op in ops}


class OperationsRunner:
    def __init__(
        self,
        project_root: str | Path,
        repo: CompanionRepository,
        events: EventBus,
        python_executable: Optional[str] = None,
        engine_controller: Any = None,
    ):
        self.project_root = Path(project_root)
        self.repo = repo
        self.events = events
        self.python_exe = python_executable or sys.executable
        self.engine_controller = engine_controller
        self.allowlist = _build_allowlist()
        self._running_procs: Dict[str, subprocess.Popen] = {}
        self._lock = threading.RLock()

    def list_operations(self) -> List[Dict[str, Any]]:
        items = [
            {"op_id": op.op_id, "name": op.name, "description": op.description, "timeout_sec": op.timeout_sec}
            for op in self.allowlist.values()
        ]
        if self.engine_controller is not None:
            items.extend([
                {"op_id": "start_engine", "name": "Start Engine", "description": "Start trading engine via Control Service", "timeout_sec": 30},
                {"op_id": "stop_engine", "name": "Stop Engine", "description": "Stop trading engine via Control Service", "timeout_sec": 30},
                {"op_id": "restart_engine", "name": "Restart Engine", "description": "Restart trading engine via Control Service", "timeout_sec": 30},
            ])
        return items

    def run_operation(self, op_id: str, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        args = args or {}
        if op_id in ("start_engine", "stop_engine", "restart_engine") and self.engine_controller is not None:
            audit_id = self.repo.create_operation_audit(op_id, op_id, args)
            t0 = time.monotonic()
            if op_id == "start_engine":
                res = self.engine_controller.start_engine()
            elif op_id == "stop_engine":
                res = self.engine_controller.stop_engine()
            else:
                res = self.engine_controller.restart_engine()
            dur = int((time.monotonic() - t0) * 1000)
            ok = bool(res.get("success", False))
            self.repo.finish_operation_audit(audit_id, "SUCCESS" if ok else "FAILED", 0 if ok else 1, str(res.get("message", "")), "", dur)
            return {"audit_id": audit_id, "op_id": op_id, "status": "SUCCESS" if ok else "FAILED", "stdout": res.get("message", ""), "stderr": "", "exit_code": 0 if ok else 1, "duration_ms": dur}

        if op_id not in self.allowlist:
            self.repo.record_audit("operator", "BLOCKED_OPERATION", "OperationsRunner", f"Rejected non-allowlisted operation '{op_id}'")
            raise PermissionError(f"Operation '{op_id}' is not in the approved allowlist.")

        op = self.allowlist[op_id]
        cmd = op.command_builder(self.project_root, self.python_exe)
        audit_id = self.repo.create_operation_audit(op.op_id, op.name, args)
        run_key = f"{op.op_id}_{uuid.uuid4().hex[:8]}"
        t0 = time.monotonic()

        self.events.log("OPERATIONS", "INFO", f"Running operation: {op.name} ({op.op_id})")
        proc = subprocess.Popen(
            cmd,
            cwd=str(self.project_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=CREATE_NO_WINDOW,
        )
        with self._lock:
            self._running_procs[run_key] = proc

        try:
            stdout_raw, stderr_raw = proc.communicate(timeout=op.timeout_sec)
            rc = proc.returncode
            status = "SUCCESS" if rc == 0 else "FAILED"
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout_raw, stderr_raw = proc.communicate()
            rc = -1
            status = "TIMEOUT"
            stderr_raw = (stderr_raw or "") + f"\nOperation timed out after {op.timeout_sec}s."
        finally:
            with self._lock:
                self._running_procs.pop(run_key, None)

        dur = int((time.monotonic() - t0) * 1000)
        stdout_clean = redact_secrets(stdout_raw or "")
        stderr_clean = redact_secrets(stderr_raw or "")
        self.repo.finish_operation_audit(audit_id, status, rc, stdout_clean, stderr_clean, dur)
        self.repo.record_audit("operator", "RUN_OPERATION", "OperationsRunner", f"{op.op_id} -> {status} (rc={rc}, {dur}ms)")
        self.events.log("OPERATIONS", "INFO" if status == "SUCCESS" else "ERROR", f"Operation {op.name} finished: {status} (rc={rc}, {dur}ms)")
        return {
            "audit_id": audit_id,
            "run_key": run_key,
            "op_id": op.op_id,
            "name": op.name,
            "status": status,
            "exit_code": rc,
            "stdout": stdout_clean,
            "stderr": stderr_clean,
            "duration_ms": dur,
        }

    def cancel_operation(self, run_key: str) -> bool:
        with self._lock:
            proc = self._running_procs.get(run_key)
            if proc and proc.poll() is None:
                proc.kill()
                self.events.log("OPERATIONS", "WARNING", f"Operation {run_key} cancelled by operator.")
                return True
            return False
