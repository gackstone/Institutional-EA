"""
Unified Facade for the MT5-001 Adaptive Trading Intelligence (ATI) Subsystem.
Coordinates Historian, Auditor, Learning, Regime, Execution, Laboratory,
Self-Improvement Controller, and Reporting into a coherent, thread-safe interface.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.intelligence.contracts import (
    ATIOperatingMode,
    AuditClassification,
    CompletedPositionRecord,
    TradeAuditReport,
    MarketRegimeSnapshot,
    StrategyCandidateRecord,
    CandidateStatus,
    utc_now,
)
from src.intelligence.config import ATIConfig
from src.intelligence.storage.repository import ATIRepository, DEFAULT_ATI_DB_PATH
from src.intelligence.historian.collector import MT5TradeHistorian
from src.intelligence.historian.normalization import AccountBrokerNormalizer
from src.intelligence.historian.reconciler import PositionLifecycleReconciler
from src.intelligence.auditor.engine import AutonomousTradeAuditor
from src.intelligence.learning.feature_extractor import HistoricalFeatureExtractor
from src.intelligence.learning.model_engine import AIPatternLearningEngine
from src.intelligence.regime.detector import MarketRegimeDetector
from src.intelligence.execution.analyzer import ExecutionIntelligenceAnalyzer, ExecutionQualityMetrics
from src.intelligence.laboratory.backtester import StrategyOptimizationLaboratory
from src.intelligence.laboratory.counterfactual import CounterfactualAnalyzer
from src.intelligence.improvement.controller import ControlledSelfImprovementController
from src.intelligence.monitoring.drift_monitor import ModelPerformanceDriftMonitor
from src.intelligence.monitoring.reporter import AutomatedIntelligenceReporter

logger = logging.getLogger("ATI.Engine")


class AdaptiveTradingIntelligence:
    """
    Central Coordinator for the Adaptive Trading Intelligence subsystem.
    Thread-safe, non-blocking, and cleanly isolated from the live execution loop.
    ATI NEVER independently executes live orders.
    """

    def __init__(
        self,
        config: Optional[ATIConfig] = None,
        db_path: Optional[str | Path] = None,
        mt5_module: Any = None,
    ):
        self.config = config or ATIConfig()
        self.config.validate()

        effective_db = db_path or self.config.database_path or DEFAULT_ATI_DB_PATH
        self.repo = ATIRepository(effective_db)

        self.normalizer = AccountBrokerNormalizer()
        self.reconciler = PositionLifecycleReconciler(self.normalizer)
        self.historian = MT5TradeHistorian(self.repo, self.normalizer, self.reconciler, mt5_module=mt5_module)
        self.auditor = AutonomousTradeAuditor(self.repo)
        self.learning_engine = AIPatternLearningEngine()
        self.regime_detector = MarketRegimeDetector(self.repo)
        self.execution_analyzer = ExecutionIntelligenceAnalyzer()
        self.laboratory = StrategyOptimizationLaboratory()
        self.counterfactual = CounterfactualAnalyzer()
        self.improvement_controller = ControlledSelfImprovementController(self.repo)
        self.drift_monitor = ModelPerformanceDriftMonitor()
        self.reporter = AutomatedIntelligenceReporter(self.repo)

        logger.info(
            f"[ATI] Initialized in mode '{self.config.mode.value}' | Database: {effective_db} | "
            f"Approved Symbols: {self.config.approved_symbols}"
        )

    # --------------------------------------------------------------------------
    # Historian & Ingestion
    # --------------------------------------------------------------------------
    def sync_broker_history(
        self,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Pulls deal history from MT5 and reconciles closed positions."""
        res = self.historian.sync_history(from_date=from_date, to_date=to_date)
        if self.config.trade_auditing and res.get("status") == "SUCCESS":
            self.auditor.audit_all_unaudited()
        return res

    # --------------------------------------------------------------------------
    # Auditing
    # --------------------------------------------------------------------------
    def audit_trade(self, position_id: int) -> Optional[TradeAuditReport]:
        """Audits a specific completed position by ID."""
        pos = self.repo.get_completed_position(position_id)
        if not pos:
            return None
        return self.auditor.audit_position(pos)

    def audit_all_pending(self, limit: int = 100) -> List[TradeAuditReport]:
        return self.auditor.audit_all_unaudited(limit=limit)

    # --------------------------------------------------------------------------
    # Learning & Pattern Recognition
    # --------------------------------------------------------------------------
    def train_models(self) -> Dict[str, Any]:
        """Trains temporal predictive models on reconciled completed positions."""
        positions = self.repo.list_completed_positions(limit=1000)
        X, y, feature_names = HistoricalFeatureExtractor.build_matrix_from_positions(positions)
        eval_report = self.learning_engine.train_temporal(X, y, feature_names)
        return {
            "model_version": eval_report.model_version,
            "sample_size": eval_report.sample_size,
            "validation_accuracy": eval_report.validation_accuracy,
            "brier_score": eval_report.brier_score,
            "status": eval_report.status,
            "recurring_loss_patterns": eval_report.recurring_loss_patterns,
            "feature_importance": eval_report.feature_importance,
        }

    # --------------------------------------------------------------------------
    # Execution Analytics
    # --------------------------------------------------------------------------
    def get_execution_metrics(self) -> ExecutionQualityMetrics:
        positions = self.repo.list_completed_positions(limit=500)
        return self.execution_analyzer.analyze_positions_execution(positions)

    # --------------------------------------------------------------------------
    # Self-Improvement & Laboratory
    # --------------------------------------------------------------------------
    def run_candidate_experiment(
        self,
        candidate_id: str,
        parameters: Dict[str, Any],
        rationale: str,
        target_symbols: Optional[List[str]] = None,
    ) -> Tuple[Optional[StrategyCandidateRecord], str]:
        """Registers a candidate improvement and evaluates it in the laboratory."""
        syms = target_symbols or list(self.config.approved_symbols)
        cand, msg = self.improvement_controller.create_candidate(
            candidate_id=candidate_id,
            base_strategy="SMC_SCALPER",
            version="1.1.0",
            parameters=parameters,
            target_symbols=syms,
            rationale=rationale,
        )
        if not cand:
            return None, msg

        # Run historical backtest & walk-forward validation
        positions = self.repo.list_completed_positions(limit=1000)
        cand = self.laboratory.evaluate_candidate_on_positions(cand, positions)
        self.repo.save_candidate(cand)
        return cand, f"Candidate evaluated: {cand.status.value}"

    def approve_candidate(self, candidate_id: str, operator: str) -> Tuple[bool, str]:
        """Applies human approval to a candidate that passed shadow testing."""
        return self.improvement_controller.approve_and_deploy_candidate(candidate_id, operator)

    def rollback_config(self, reason: str = "Operator requested rollback") -> Tuple[bool, str]:
        """Reverts active adaptive configuration to previous snapshot."""
        return self.improvement_controller.rollback_to_previous_configuration(reason)

    # --------------------------------------------------------------------------
    # System Status & Reporting
    # --------------------------------------------------------------------------
    def get_system_status(self) -> Dict[str, Any]:
        """Comprehensive snapshot of ATI operating state."""
        positions = self.repo.list_completed_positions(limit=10)
        audits = self.repo.list_trade_audits(limit=10)
        cands = self.repo.list_candidates()
        drift_report = self.drift_monitor.check_drift(positions)

        # Calculate quick summary
        all_pos = self.repo.list_completed_positions(limit=500)
        wins = sum(1 for p in all_pos if p.realized_net_profit > 0)
        losses = sum(1 for p in all_pos if p.realized_net_profit < 0)
        net_profit = sum(p.normalized_net_profit for p in all_pos)

        return {
            "enabled": self.config.enabled,
            "mode": self.config.mode.value,
            "approved_symbols": self.config.approved_symbols,
            "total_reconciled_positions": len(all_pos),
            "winning_positions": wins,
            "losing_positions": losses,
            "win_rate_pct": round((wins / len(all_pos) * 100.0) if all_pos else 0.0, 1),
            "net_realized_profit_usd": round(net_profit, 2),
            "total_audited_trades": len(audits),
            "active_candidates_count": len(cands),
            "drift_detected": drift_report.drift_detected,
            "model_status": self.learning_engine.latest_report.status if self.learning_engine.latest_report else "UNINITIALIZED",
            "timestamp": utc_now().isoformat(),
        }
