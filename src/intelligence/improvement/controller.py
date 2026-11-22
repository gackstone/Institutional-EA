"""
Controlled Self-Improvement Controller for ATI.
Enforces the strict candidate promotion lifecycle:
OBSERVE -> AUDIT -> IDENTIFY -> CANDIDATE -> BACKTEST -> VALIDATE -> SHADOW -> APPROVE -> DEPLOY -> ROLLBACK.
Guarantees versioned configuration history, auditability, and immediate rollback.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.intelligence.contracts import (
    CandidateStatus,
    StrategyCandidateRecord,
    utc_now,
)
from src.intelligence.improvement.allowlist import ParameterAllowlistValidator
from src.intelligence.storage.repository import ATIRepository

logger = logging.getLogger("ATI.ImprovementController")


class ControlledSelfImprovementController:
    """
    Orchestrates the lifecycle of candidate strategy parameters.
    Prevents unvalidated promotion and provides instant configuration rollback.
    """

    def __init__(self, repo: ATIRepository, base_config: Optional[Dict[str, Any]] = None):
        self.repo = repo
        self.active_config = dict(base_config or {})
        self.config_version = 1
        self._init_baseline_snapshot()

    def _init_baseline_snapshot(self) -> None:
        """Initializes baseline configuration version in repository."""
        checksum = ParameterAllowlistValidator.compute_config_checksum(self.active_config)
        self.repo.save_active_config(
            version=self.config_version,
            config_json=json.dumps(self.active_config),
            checksum=checksum,
            promoted_by="SYSTEM_INIT",
        )

    def create_candidate(
        self,
        candidate_id: str,
        base_strategy: str,
        version: str,
        parameters: Dict[str, Any],
        target_symbols: List[str],
        rationale: str,
        author: str = "ATI_LABORATORY",
    ) -> Tuple[Optional[StrategyCandidateRecord], str]:
        """Creates a candidate record after strictly validating parameters against the allowlist."""
        # 1. Allowlist Validation
        is_valid, reason = ParameterAllowlistValidator.validate_candidate_parameters(parameters)
        if not is_valid:
            logger.warning(f"[IMPROVEMENT] Candidate creation rejected: {reason}")
            return None, reason

        checksum = ParameterAllowlistValidator.compute_config_checksum(parameters)

        candidate = StrategyCandidateRecord(
            candidate_id=candidate_id,
            base_strategy=base_strategy,
            version=version,
            parameters=parameters,
            target_symbols=target_symbols,
            target_regimes=["ALL"],
            creation_timestamp=utc_now(),
            status=CandidateStatus.DRAFT,
            rationale=rationale,
            checksum=checksum,
            author=author,
        )

        self.repo.save_candidate(candidate)
        logger.info(f"[IMPROVEMENT] Created candidate {candidate_id} (checksum: {checksum[:8]}).")
        return candidate, "Candidate created successfully in DRAFT state."

    def submit_for_shadow_testing(self, candidate_id: str) -> Tuple[bool, str]:
        """Transitions candidate to SHADOW_TESTING state if walk-forward validated."""
        cand = self.repo.get_candidate(candidate_id)
        if not cand:
            return False, f"Candidate {candidate_id} not found."

        if cand.status not in (CandidateStatus.OUT_OF_SAMPLE_VALIDATED, CandidateStatus.WALK_FORWARD_VALIDATED):
            return False, f"Candidate must be validated prior to shadow testing (current status: {cand.status.value})."

        cand.status = CandidateStatus.SHADOW_TESTING
        self.repo.save_candidate(cand)
        logger.info(f"[IMPROVEMENT] Candidate {candidate_id} submitted to SHADOW_TESTING.")
        return True, "Candidate promoted to SHADOW_TESTING."

    def submit_for_approval(self, candidate_id: str) -> Tuple[bool, str]:
        """Transitions candidate to PENDING_APPROVAL after shadow test evidence is gathered."""
        cand = self.repo.get_candidate(candidate_id)
        if not cand:
            return False, f"Candidate {candidate_id} not found."

        if cand.status != CandidateStatus.SHADOW_TESTING:
            return False, f"Candidate must complete shadow testing before approval (current: {cand.status.value})."

        cand.status = CandidateStatus.PENDING_APPROVAL
        self.repo.save_candidate(cand)
        logger.info(f"[IMPROVEMENT] Candidate {candidate_id} moved to PENDING_APPROVAL.")
        return True, "Candidate awaiting authorized human operator approval."

    def approve_and_deploy_candidate(
        self,
        candidate_id: str,
        operator_signature: str,
    ) -> Tuple[bool, str]:
        """
        Applies validated candidate parameters to active configuration.
        Creates immutable rollback snapshot first.
        """
        cand = self.repo.get_candidate(candidate_id)
        if not cand:
            return False, f"Candidate {candidate_id} not found."

        if cand.status != CandidateStatus.PENDING_APPROVAL:
            return False, f"Candidate {candidate_id} is not in PENDING_APPROVAL state."

        # Safety Re-verification
        is_valid, reason = ParameterAllowlistValidator.validate_candidate_parameters(cand.parameters)
        if not is_valid:
            cand.status = CandidateStatus.REJECTED
            cand.promotion_notes = f"Failed final security check: {reason}"
            self.repo.save_candidate(cand)
            return False, f"Final safety check failed: {reason}"

        # 1. Take Rollback Snapshot of current active configuration
        self.repo.record_rollback_snapshot(
            version=self.config_version,
            config_json=json.dumps(self.active_config),
            reason=f"Pre-promotion snapshot before deploying {candidate_id}",
        )

        # 2. Merge candidate parameters into active configuration
        self.active_config.update(cand.parameters)
        self.config_version += 1
        new_checksum = ParameterAllowlistValidator.compute_config_checksum(self.active_config)

        # 3. Save new active configuration in database
        self.repo.save_active_config(
            version=self.config_version,
            config_json=json.dumps(self.active_config),
            checksum=new_checksum,
            promoted_by=operator_signature,
        )

        # 4. Update candidate status
        cand.status = CandidateStatus.ACTIVE_DEPLOYED
        cand.approved_by = operator_signature
        cand.approved_at = utc_now()
        cand.promotion_notes = f"Approved and deployed by {operator_signature} to version {self.config_version}."
        self.repo.save_candidate(cand)

        logger.info(f"[IMPROVEMENT] Deployed candidate {candidate_id} to configuration v{self.config_version}.")
        return True, f"Successfully deployed {candidate_id} to active configuration v{self.config_version}."

    def rollback_to_previous_configuration(self, reason: str = "Operator rollback") -> Tuple[bool, str]:
        """Rolls back the active configuration to the latest pre-promotion snapshot."""
        snapshot = self.repo.get_latest_rollback_snapshot()
        if not snapshot:
            return False, "No rollback snapshot available in database."

        try:
            restored_config = json.loads(snapshot["config_json"])
            self.active_config = restored_config
            self.config_version += 1
            checksum = ParameterAllowlistValidator.compute_config_checksum(self.active_config)

            self.repo.save_active_config(
                version=self.config_version,
                config_json=json.dumps(self.active_config),
                checksum=checksum,
                promoted_by="ROLLBACK_CONTROLLER",
            )
            logger.warning(f"[IMPROVEMENT] Rolled back active configuration to v{self.config_version}: {reason}")
            return True, f"Successfully rolled back configuration to snapshot (new v{self.config_version})."
        except Exception as exc:
            return False, f"Failed to restore rollback snapshot: {exc}"
