"""
Automated Test Suite for Controlled Self-Improvement Controller & Safety Guards.
Verifies allowlist enforcement, strict rejection of forbidden risk/symbol modifications,
candidate lifecycle progression, and instant configuration rollback.
"""

import tempfile
from pathlib import Path
import pytest

from src.intelligence.contracts import CandidateStatus
from src.intelligence.improvement.allowlist import (
    ParameterAllowlistValidator,
    ALLOWLISTED_PARAMETER_BOUNDS,
)
from src.intelligence.improvement.controller import ControlledSelfImprovementController
from src.intelligence.storage.repository import ATIRepository


@pytest.fixture
def temp_repo():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_ati_ctrl.db"
        yield ATIRepository(db_path)


class TestParameterSafetyAllowlist:
    def test_allowlisted_parameters_accepted(self):
        valid_params = {
            "max_spread_pts": 25.0,
            "min_confluence_score": 70.0,
            "min_risk_reward_ratio": 2.0,
        }
        ok, msg = ParameterAllowlistValidator.validate_candidate_parameters(valid_params)
        assert ok is True
        assert msg == "Valid"

    def test_forbidden_risk_modification_rejected(self):
        forbidden_attempts = [
            {"risk_percentage": 5.0},
            {"max_drawdown_percent": 20.0},
            {"max_account_risk": 10.0},
            {"live_trading_enabled": True},
            {"emergency_stop": False},
            {"approved_symbols": ["EURUSD"]},
            {"whitelist": ["XAUUSD", "EURUSD"]},
        ]
        for bad_param in forbidden_attempts:
            ok, msg = ParameterAllowlistValidator.validate_candidate_parameters(bad_param)
            assert ok is False
            assert "SAFETY VIOLATION" in msg or "not in the explicit ATI adaptation allowlist" in msg

    def test_out_of_bounds_parameters_rejected(self):
        # max_spread_pts valid bounds: (10.0, 50.0)
        ok, msg = ParameterAllowlistValidator.validate_candidate_parameters({"max_spread_pts": 100.0})
        assert ok is False
        assert "outside allowed safe bounds" in msg


class TestImprovementLifecycleAndRollback:
    def test_full_candidate_lifecycle(self, temp_repo):
        base_config = {"max_spread_pts": 40.0, "min_confluence_score": 60.0}
        ctrl = ControlledSelfImprovementController(temp_repo, base_config=base_config)

        # 1. Create candidate
        cand, msg = ctrl.create_candidate(
            candidate_id="CAND_001",
            base_strategy="SMC_SCALPER",
            version="1.1.0",
            parameters={"max_spread_pts": 25.0},
            target_symbols=["XAUUSD"],
            rationale="Audits show spread > 25 pts causes 60% loss rate.",
        )
        assert cand is not None
        assert cand.status == CandidateStatus.DRAFT

        # Manually mark as validated (as if laboratory backtested)
        cand.status = CandidateStatus.OUT_OF_SAMPLE_VALIDATED
        temp_repo.save_candidate(cand)

        # 2. Submit to Shadow Testing
        ok, _ = ctrl.submit_for_shadow_testing("CAND_001")
        assert ok is True
        assert temp_repo.get_candidate("CAND_001").status == CandidateStatus.SHADOW_TESTING

        # 3. Submit for Approval
        ok, _ = ctrl.submit_for_approval("CAND_001")
        assert ok is True
        assert temp_repo.get_candidate("CAND_001").status == CandidateStatus.PENDING_APPROVAL

        # 4. Approve and Deploy with human operator signature
        ok, deploy_msg = ctrl.approve_and_deploy_candidate("CAND_001", operator_signature="Gackstone_Baraka")
        assert ok is True
        assert "Successfully deployed" in deploy_msg
        assert ctrl.active_config["max_spread_pts"] == 25.0
        assert ctrl.config_version == 2
        assert temp_repo.get_candidate("CAND_001").status == CandidateStatus.ACTIVE_DEPLOYED

        # 5. Rollback
        ok, rb_msg = ctrl.rollback_to_previous_configuration(reason="Performance dip in live market")
        assert ok is True
        assert ctrl.active_config["max_spread_pts"] == 40.0  # Restored!
        assert ctrl.config_version == 3
