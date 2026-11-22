"""
Automated Test Suite for ATI Autonomous Trade Auditor.
Verifies forensic investigation of Entry, Exit, Execution, and Risk quality.
Ensures correct classifications: NORMAL_STATISTICAL_LOSS, SPREAD_OR_COST_ISSUE,
EXECUTION_FAILURE, RISK_POLICY_VIOLATION, EXIT_OPTIMIZATION_OPPORTUNITY.
"""

from datetime import datetime, timezone, timedelta
import pytest

from src.intelligence.contracts import CompletedPositionRecord, AuditClassification
from src.intelligence.auditor.engine import AutonomousTradeAuditor


class TestAutonomousTradeAuditor:
    def test_normal_statistical_loss_classification(self):
        now = datetime.now(timezone.utc)
        pos = CompletedPositionRecord(
            position_id=101,
            canonical_symbol="XAUUSD",
            broker_symbol="XAUUSD",
            direction="BUY",
            open_time=now - timedelta(minutes=20),
            close_time=now,
            open_price=2650.0,
            close_price=2645.0,
            volume=0.10,
            initial_sl=2645.0,
            initial_tp=2665.0,
            realized_gross_profit=-50.0,
            realized_net_profit=-52.0,
            commission=-2.0,
            swap=0.0,
            exit_reason="STOP_LOSS",
            features_snapshot={"adx": 28.0, "atr": 2.5, "spread_pts": 12.0},
        )

        auditor = AutonomousTradeAuditor()
        report = auditor.audit_position(pos)

        assert report.classification == AuditClassification.NORMAL_STATISTICAL_LOSS
        assert report.root_cause_confidence >= 0.80
        assert report.risk_quality_score >= 80.0
        assert len(report.detected_issues) == 0

    def test_risk_policy_violation_missing_stop_loss(self):
        now = datetime.now(timezone.utc)
        pos = CompletedPositionRecord(
            position_id=102,
            canonical_symbol="BTCUSD",
            broker_symbol="BTCUSD",
            direction="BUY",
            open_time=now - timedelta(minutes=10),
            close_time=now,
            open_price=90000.0,
            close_price=89500.0,
            volume=0.05,
            initial_sl=0.0,  # CRITICAL: Missing SL
            realized_gross_profit=-25.0,
            realized_net_profit=-26.0,
            exit_reason="SYSTEM_CLOSE",
        )

        auditor = AutonomousTradeAuditor()
        report = auditor.audit_position(pos)

        assert report.classification == AuditClassification.RISK_POLICY_VIOLATION
        assert report.root_cause_confidence == 0.99
        assert any("CRITICAL: Position opened without non-zero initial stop loss" in issue for issue in report.detected_issues)

    def test_spread_and_cost_drag_classification(self):
        now = datetime.now(timezone.utc)
        pos = CompletedPositionRecord(
            position_id=103,
            canonical_symbol="USDJPY",
            broker_symbol="USDJPY",
            direction="SELL",
            open_time=now - timedelta(minutes=5),
            close_time=now,
            open_price=154.50,
            close_price=154.48,
            volume=0.10,
            initial_sl=154.70,
            realized_gross_profit=1.20,
            realized_net_profit=-1.80,  # Negative due to commission and spread
            commission=-3.00,
            exit_reason="SYSTEM_CLOSE",
            features_snapshot={"spread_pts": 48.0},
        )

        auditor = AutonomousTradeAuditor()
        report = auditor.audit_position(pos)

        assert report.classification == AuditClassification.SPREAD_OR_COST_ISSUE
        assert report.execution_quality_score < 70.0
        assert any("Broker commissions and swap exceeded gross trade profit" in issue for issue in report.detected_issues)

    def test_execution_failure_excessive_slippage(self):
        now = datetime.now(timezone.utc)
        pos = CompletedPositionRecord(
            position_id=104,
            canonical_symbol="XAUUSD",
            broker_symbol="XAUUSD",
            direction="BUY",
            open_time=now - timedelta(minutes=15),
            close_time=now,
            open_price=2600.0,
            close_price=2595.0,
            volume=0.10,
            initial_sl=2598.0,
            slippage_pts=35.0,  # Extreme slippage
            realized_gross_profit=-50.0,
            realized_net_profit=-52.0,
            exit_reason="STOP_LOSS",
        )

        auditor = AutonomousTradeAuditor()
        report = auditor.audit_position(pos)

        assert report.classification == AuditClassification.EXECUTION_FAILURE
        assert any("Severe execution slippage" in issue for issue in report.detected_issues)

    def test_audit_report_to_dict_format(self):
        now = datetime.now(timezone.utc)
        pos = CompletedPositionRecord(
            position_id=105,
            canonical_symbol="BTCUSD",
            broker_symbol="BTCUSD",
            direction="BUY",
            open_time=now - timedelta(minutes=30),
            close_time=now,
            open_price=90000.0,
            close_price=91000.0,
            volume=0.10,
            initial_sl=89500.0,
            initial_tp=91000.0,
            realized_gross_profit=100.0,
            realized_net_profit=98.0,
            exit_reason="TAKE_PROFIT",
        )

        auditor = AutonomousTradeAuditor()
        report = auditor.audit_position(pos)
        d = report.to_dict()

        assert d["trade_id"] == 105
        assert "classification" in d
        assert "entry_quality_score" in d
        assert "exit_quality_score" in d
        assert "risk_quality_score" in d
        assert isinstance(d["audit_timestamp"], str)
