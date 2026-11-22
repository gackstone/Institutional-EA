"""
Pytest configuration and safety isolation fixtures for the modern Institutional EA architecture.
Ensures that an active operator STOP.flag or scripts/STOP.flag in the repository is NEVER
deleted or modified by tests, while isolating unit-test risk/kill-switch checks to a
temporary flag path unless a test explicitly configures a custom kill_switch_flag_path.
"""

from __future__ import annotations
from pathlib import Path
import pytest

from src.risk.portfolio_risk import PortfolioRiskEngine


@pytest.fixture(autouse=True)
def _isolate_default_kill_switch_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    isolated_flag = str(tmp_path / "isolated_test_STOP.flag")
    orig_init = PortfolioRiskEngine.__init__

    def _patched_init(self, *args, **kwargs):
        orig_init(self, *args, **kwargs)
        if getattr(self, "kill_switch_flag_path", None) in (None, "STOP.flag", "scripts/STOP.flag"):
            self.kill_switch_flag_path = isolated_flag

    monkeypatch.setattr(PortfolioRiskEngine, "__init__", _patched_init)
    yield
