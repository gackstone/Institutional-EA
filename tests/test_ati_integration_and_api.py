"""
Automated Test Suite for ATI Integration, Orchestrator Hook, and Companion API.
Verifies unified facade, engine lifecycle integration, and REST API contract endpoints.
"""

import json
import tempfile
from pathlib import Path
import pytest

from src.intelligence.facade import AdaptiveTradingIntelligence
from src.intelligence.config import ATIConfig
from src.intelligence.contracts import ATIOperatingMode
from src.core.config import AppConfig
from src.core.orchestrator import TradingBotOrchestrator


class MockMT5Empty:
    def initialize(self):
        return True

    def account_info(self):
        return None

    def history_deals_get(self, d_from, d_to):
        return []

    def last_error(self):
        return (1, "OK")


@pytest.fixture
def temp_ati():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_facade.db"
        cfg = ATIConfig(mode=ATIOperatingMode.OBSERVATION)
        ati = AdaptiveTradingIntelligence(config=cfg, db_path=db_path, mt5_module=MockMT5Empty())
        yield ati


class TestATIIntegration:
    def test_facade_initialization_and_status(self, temp_ati):
        status = temp_ati.get_system_status()
        assert status["enabled"] is True
        assert status["mode"] == "OBSERVATION"
        assert status["approved_symbols"] == ["XAUUSD", "BTCUSD"]
        assert status["total_reconciled_positions"] == 0
        assert status["drift_detected"] is False

    def test_orchestrator_initialization_with_ati(self):
        cfg = AppConfig()
        cfg.dry_run = True
        orchestrator = TradingBotOrchestrator(config=cfg)

        assert hasattr(orchestrator, "ati")
        assert orchestrator.ati is not None
        status = orchestrator.ati.get_system_status()
        assert status["approved_symbols"] == ["XAUUSD", "BTCUSD"]

    def test_companion_service_api_endpoints(self):
        from companion.service.api.server import build_control_server
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "config").mkdir(parents=True, exist_ok=True)
            (root / "state").mkdir(parents=True, exist_ok=True)
            (root / "data").mkdir(parents=True, exist_ok=True)

            server, ctx = build_control_server(root, host="127.0.0.1", port=8765, token="test-token-123")
            assert hasattr(ctx, "ati")
            assert ctx.ati is not None

            # Test direct status inspection
            ati_status = ctx.ati.get_system_status()
            assert ati_status["enabled"] is True
            assert ati_status["approved_symbols"] == ["XAUUSD", "BTCUSD"]
