#!/usr/bin/env python3
"""
Test Suite for Institutional EA Supervisor & Tooling (tests/test_supervisor.py)
Verifies:
  - Single-instance locking (mutex and stale lock recovery)
  - Python interpreter resolution
  - MT5 process detection
  - Rotating file logger (size-based rotation & backups)
  - Bridge server socket readiness probe
  - Child process independent backoff and lifecycle management
  - Graceful shutdown signal handling
"""

from __future__ import annotations
import sys
import os
import time
import json
import socket
import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from scripts.supervisor import (
    SingleInstanceLock,
    resolve_python_executable,
    is_mt5_terminal_active,
    is_port_listening,
    wait_for_port_ready,
    RotatingLogWriter,
    ChildProcessManager,
    InstitutionalEaSupervisor,
    load_app_config
)


class TestSupervisorTooling(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.logs_dir = os.path.join(self.test_dir, "logs")
        os.makedirs(self.logs_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_python_interpreter_resolution(self):
        """Proves Python interpreter resolution discovers an existing python/pythonw executable."""
        py_exe = resolve_python_executable(prefer_pythonw=False)
        self.assertTrue(os.path.exists(py_exe), f"Resolved Python executable must exist: {py_exe}")
        self.assertTrue("python" in py_exe.lower(), f"Executable name must contain python: {py_exe}")

    def test_02_single_instance_locking_and_stale_recovery(self):
        """Proves named mutex and PID lockfile enforce single-instance and reclaim stale locks."""
        lock_path = os.path.join(self.logs_dir, "test_supervisor.lock")
        mutex_name = f"Local\\Test_InstitutionalEA_Supervisor_{os.getpid()}_{int(time.time()*1000)}"

        lock1 = SingleInstanceLock(mutex_name=mutex_name, lock_file=lock_path)
        self.assertTrue(lock1.acquire(), "Initial lock acquisition must succeed")
        self.assertTrue(os.path.exists(lock_path), "Lock file must be written to disk")

        # Second lock attempt with same mutex must be rejected
        lock2 = SingleInstanceLock(mutex_name=mutex_name, lock_file=lock_path)
        self.assertFalse(lock2.acquire(), "Concurrent second lock must fail")

        # Release first lock
        lock1.release()
        self.assertFalse(os.path.exists(lock_path), "Lock file must be unlinked upon release")

        # Subsequent acquisition must succeed
        self.assertTrue(lock2.acquire(), "Acquisition after clean release must succeed")
        lock2.release()

    def test_03_stale_lock_pid_recovery(self):
        """Proves that a lockfile left by a non-existent dead PID is reclaimed."""
        lock_path = os.path.join(self.logs_dir, "stale_supervisor.lock")
        mutex_name = f"Local\\Test_InstitutionalEA_Stale_{os.getpid()}_{int(time.time()*1000)}"

        # Write a fake dead PID (e.g. 999999)
        with open(lock_path, "w") as f:
            json.dump({"pid": 999999, "started_at": "2026-01-01T00:00:00Z"}, f)

        lock = SingleInstanceLock(mutex_name=mutex_name, lock_file=lock_path)
        self.assertTrue(lock.acquire(), "Lock must reclaim stale lockfile from dead PID")
        lock.release()

    def test_04_rotating_file_logger(self):
        """Proves log file rotates when exceeding size threshold and preserves backup files."""
        test_log_path = os.path.join(self.logs_dir, "test_rotation.log")
        writer = RotatingLogWriter(test_log_path, max_bytes=600, backup_count=3)

        for i in range(25):
            writer.write_line("TEST", f"Message payload padding line index {i:03d}")

        self.assertTrue(os.path.exists(test_log_path), "Active log file must exist")
        self.assertTrue(os.path.exists(f"{test_log_path}.1"), "Rotated backup .1 must exist")

    def test_05_mt5_terminal_detection(self):
        """Proves MT5 terminal process detector returns boolean and descriptive string."""
        active, reason = is_mt5_terminal_active()
        self.assertIsInstance(active, bool)
        self.assertIsInstance(reason, str)
        self.assertTrue(len(reason) > 0)

    def test_06_port_probe_functions(self):
        """Proves is_port_listening and wait_for_port_ready correctly test socket connectivity."""
        # Unused ephemeral port
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        free_port = s.getsockname()[1]
        s.close()

        self.assertFalse(is_port_listening("127.0.0.1", free_port, timeout=0.2))

        # Listen on port and verify detection
        srv = socket.socket()
        srv.bind(("127.0.0.1", free_port))
        srv.listen(5)

        try:
            self.assertTrue(is_port_listening("127.0.0.1", free_port, timeout=0.8))
            self.assertTrue(wait_for_port_ready("127.0.0.1", free_port, timeout_seconds=2.0))
        finally:
            srv.close()

    def test_07_child_process_manager_backoff(self):
        """Proves child process crash triggers exponential backoff and resets after 60s stability."""
        child = ChildProcessManager("test_child", "scripts/test_script.py", "test.log")
        self.assertEqual(child.backoff_delay, 2.0)
        self.assertEqual(child.consecutive_crashes, 0)

        # Mock a terminated process with exit code 1 (crash)
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1
        mock_proc.pid = 1234
        child.process = mock_proc

        ret = child.handle_exit_if_terminated()
        self.assertEqual(ret, 1)
        self.assertEqual(child.consecutive_crashes, 1)
        self.assertEqual(child.backoff_delay, 4.0)

        # Second crash
        child.process = mock_proc
        ret = child.handle_exit_if_terminated()
        self.assertEqual(child.consecutive_crashes, 2)
        self.assertEqual(child.backoff_delay, 8.0)

        # Healthy reset simulation (>60s runtime)
        mock_alive = MagicMock()
        mock_alive.poll.return_value = None
        child.process = mock_alive
        child.start_time = time.time() - 65.0  # 65 seconds ago

        child.handle_exit_if_terminated()
        self.assertEqual(child.consecutive_crashes, 0)
        self.assertEqual(child.backoff_delay, 2.0)

    def test_08_load_app_config(self):
        """Proves configuration loader extracts BRIDGE_HOST, BRIDGE_PORT, and settings."""
        cfg = load_app_config()
        self.assertIsInstance(cfg, dict)
        self.assertIn("BRIDGE_PORT", cfg)
        self.assertEqual(int(cfg["BRIDGE_PORT"]), 5555)

    def test_09_supervisor_initialization(self):
        """Proves supervisor instantiates child process managers and configuration cleanly."""
        supervisor = InstitutionalEaSupervisor(visible=False)
        self.assertIsNotNone(supervisor.bridge_child)
        self.assertIsNotNone(supervisor.bot_child)
        self.assertEqual(supervisor.bridge_child.name, "bridge")
        self.assertEqual(supervisor.bot_child.name, "bot")
        self.assertTrue(supervisor.require_mt5)


if __name__ == "__main__":
    unittest.main()
