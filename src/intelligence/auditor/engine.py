"""
Autonomous Trade Auditor for ATI.
Performs comprehensive post-trade forensics on completed positions.
Investigates Entry Quality, Exit Quality, Execution Quality, and Risk Quality.
Classifies outcomes accurately without simplistic win/loss biases.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.intelligence.contracts import (
    AuditClassification,
    CompletedPositionRecord,
    TradeAuditReport,
    utc_now,
)
from src.intelligence.storage.repository import ATIRepository

logger = logging.getLogger("ATI.Auditor")


class AutonomousTradeAuditor:
    """
    Forensic investigation engine for every completed trading position.
    Produces structured machine-readable reports and clear classifications.
    """

    def __init__(self, repo: Optional[ATIRepository] = None):
        self.repo = repo

    def audit_position(self, pos: CompletedPositionRecord) -> TradeAuditReport:
        """Audits a single completed trading position."""
        detected_issues: List[str] = []
        evidence: Dict[str, Any] = {}
        recommendations: List[str] = []
        suggested_experiments: List[Dict[str, Any]] = []

        is_profit = pos.realized_net_profit > 0
        is_breakeven = abs(pos.realized_net_profit) <= 0.05
        is_loss = pos.realized_net_profit < -0.05

        features = pos.features_snapshot or {}

        # ----------------------------------------------------------------------
        # 1. ENTRY QUALITY EVALUATION
        # ----------------------------------------------------------------------
        entry_quality = 70.0  # Baseline
        spread_pts = pos.spread_pts or features.get("spread_pts", 0.0)
        adx_val = features.get("adx", 25.0)
        atr_val = features.get("atr", 1.0)
        regime_str = features.get("regime", "UNKNOWN")

        if spread_pts > 40.0:
            entry_quality -= 25.0
            detected_issues.append(f"Elevated entry spread: {spread_pts:.1f} pts.")
            recommendations.append("Apply strict spread ceiling filter prior to order dispatch.")
            suggested_experiments.append({
                "type": "SPREAD_FILTER",
                "param": "max_spread_pts",
                "current": spread_pts,
                "candidate": 25.0,
            })

        if adx_val < 15.0:
            entry_quality -= 15.0
            detected_issues.append(f"Low market momentum at entry (ADX={adx_val:.1f}).")
            recommendations.append("Require minimum ADX threshold for breakout signals.")

        # ----------------------------------------------------------------------
        # 2. EXIT QUALITY EVALUATION
        # ----------------------------------------------------------------------
        exit_quality = 70.0
        exit_reason = pos.exit_reason.upper()
        evidence["exit_reason"] = exit_reason

        if exit_reason == "STOP_LOSS":
            if is_loss:
                # Controlled stop loss hit
                exit_quality = 80.0  # Stop loss executed as intended to protect capital
            else:
                # Stop loss hit in profit (trailing stop / break-even)
                exit_quality = 90.0
        elif exit_reason == "TAKE_PROFIT":
            exit_quality = 95.0
        elif exit_reason in ("SYSTEM_CLOSE", "MANUAL_OR_BROKER"):
            if is_loss and pos.duration_seconds < 30:
                exit_quality -= 20.0
                detected_issues.append("Immediate position termination (<30s). Potential panic close or collision.")
            else:
                exit_quality = 75.0

        # Check if exit execution differed significantly
        if pos.slippage_pts > 15.0:
            detected_issues.append(f"High exit slippage observed: {pos.slippage_pts:.1f} pts.")

        # ----------------------------------------------------------------------
        # 3. EXECUTION QUALITY EVALUATION
        # ----------------------------------------------------------------------
        exec_quality = 85.0
        costs_ratio = 0.0
        total_costs = abs(pos.commission) + abs(pos.swap)
        if abs(pos.realized_gross_profit) > 0.01:
            costs_ratio = total_costs / abs(pos.realized_gross_profit)

        evidence["total_costs_usd"] = round(total_costs, 4)
        evidence["costs_ratio"] = round(costs_ratio, 4)

        if total_costs > abs(pos.realized_gross_profit) and pos.realized_gross_profit > 0:
            exec_quality -= 30.0
            detected_issues.append("Broker commissions and swap exceeded gross trade profit (negative cost drag).")
            recommendations.append("Review min lot size and commission tier for this instrument.")

        if pos.slippage_pts > 25.0:
            exec_quality -= 25.0
            detected_issues.append(f"Severe execution slippage ({pos.slippage_pts:.1f} pts).")

        # ----------------------------------------------------------------------
        # 4. RISK QUALITY EVALUATION
        # ----------------------------------------------------------------------
        risk_quality = 90.0
        if pos.initial_sl <= 0.0:
            risk_quality -= 50.0
            detected_issues.append("CRITICAL: Position opened without non-zero initial stop loss!")
            recommendations.append("Enforce R9 mandatory initial stop loss gate.")

        # ----------------------------------------------------------------------
        # 5. SYNTHESIS & CAUSAL CLASSIFICATION
        # ----------------------------------------------------------------------
        confidence = 0.85

        if pos.initial_sl <= 0.0:
            classification = AuditClassification.RISK_POLICY_VIOLATION
            confidence = 0.99
        elif any("Broker commissions and swap exceeded gross trade profit" in issue for issue in detected_issues) or (spread_pts > 40.0):
            classification = AuditClassification.SPREAD_OR_COST_ISSUE
            confidence = 0.90
        elif pos.slippage_pts > 30.0:
            classification = AuditClassification.EXECUTION_FAILURE
            confidence = 0.85
        elif regime_str in ("UNSTABLE_SPREAD", "ABNORMAL_EXECUTION"):
            classification = AuditClassification.MARKET_REGIME_MISMATCH
            confidence = 0.80
        elif is_loss and adx_val < 15.0 and "Low market momentum" in detected_issues:
            classification = AuditClassification.ENTRY_TIMING_FAILURE
            confidence = 0.75
        elif is_loss and exit_reason == "STOP_LOSS" and len(detected_issues) == 0:
            # Expected statistical loss in trading within healthy parameters
            classification = AuditClassification.NORMAL_STATISTICAL_LOSS
            confidence = 0.95
        elif is_loss and len(detected_issues) > 0:
            classification = AuditClassification.STRATEGY_FAILURE
            confidence = 0.70
        elif is_profit and exit_reason == "STOP_LOSS" and pos.realized_net_profit < 1.0:
            classification = AuditClassification.EXIT_OPTIMIZATION_OPPORTUNITY
            confidence = 0.75
            recommendations.append("Investigate dynamic profit floor ratchet to prevent giveback.")
        elif is_profit:
            # Clean profitable execution
            classification = AuditClassification.NORMAL_STATISTICAL_LOSS if not is_profit else AuditClassification.INSUFFICIENT_EVIDENCE
            # Mark clean win
            evidence["audit_verdict"] = "EXECUTION_VALIDATED_PROFITABLE"
            classification = AuditClassification.EXIT_OPTIMIZATION_OPPORTUNITY if pos.partial_closes_count > 0 else AuditClassification.INSUFFICIENT_EVIDENCE
            if not detected_issues:
                evidence["audit_verdict"] = "CLEAN_SYSTEMATIC_WIN"
        else:
            classification = AuditClassification.INSUFFICIENT_EVIDENCE
            confidence = 0.50

        audit_report = TradeAuditReport(
            trade_id=pos.position_id,
            audit_timestamp=utc_now(),
            audit_version="1.0.0",
            classification=classification,
            root_cause_confidence=round(confidence, 2),
            entry_quality_score=round(max(0.0, min(100.0, entry_quality)), 1),
            exit_quality_score=round(max(0.0, min(100.0, exit_quality)), 1),
            execution_quality_score=round(max(0.0, min(100.0, exec_quality)), 1),
            risk_quality_score=round(max(0.0, min(100.0, risk_quality)), 1),
            detected_issues=detected_issues,
            supporting_evidence=evidence,
            recommendations=recommendations,
            suggested_experiments=suggested_experiments,
            status="AUDITED",
        )

        if self.repo:
            self.repo.save_trade_audit(audit_report)

        return audit_report

    def audit_all_unaudited(self, limit: int = 100) -> List[TradeAuditReport]:
        """Scans repository for closed positions lacking audit records and audits them."""
        if not self.repo:
            return []

        positions = self.repo.list_completed_positions(limit=limit)
        audits = []
        for pos in positions:
            existing = self.repo.get_trade_audit(pos.position_id)
            if existing is None:
                aud = self.audit_position(pos)
                audits.append(aud)
        return audits
