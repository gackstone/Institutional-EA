"""
Automated Test Suite for Strategy Optimization Laboratory & Counterfactual Analysis.
Verifies quantitative metrics, walk-forward out-of-sample validation,
and counterfactual "what if" scenario simulation.
"""

from datetime import datetime, timezone, timedelta
import pytest

from src.intelligence.contracts import (
    CompletedPositionRecord,
    StrategyCandidateRecord,
    CandidateStatus,
)
from src.intelligence.laboratory.evaluator import PerformanceEvaluator
from src.intelligence.laboratory.backtester import StrategyOptimizationLaboratory
from src.intelligence.laboratory.counterfactual import CounterfactualAnalyzer


class TestPerformanceEvaluator:
    def test_metrics_calculation_healthy_series(self):
        # 10 trades: 7 wins of +10, 3 losses of -5
        profits = [10.0, 10.0, -5.0, 10.0, 10.0, -5.0, 10.0, 10.0, -5.0, 10.0]
        metrics = PerformanceEvaluator.calculate_metrics(profits, initial_capital=1000.0)

        assert metrics["trade_count"] == 10
        assert metrics["win_rate_pct"] == 70.0
        assert metrics["profit_factor"] == round(70.0 / 15.0, 2)  # 4.67
        assert metrics["net_profit"] == 55.0
        assert metrics["expectancy"] == 5.5
        assert metrics["sharpe_ratio"] > 0.0
        assert metrics["sortino_ratio"] > 0.0


class TestLaboratoryBacktester:
    def test_candidate_evaluation_with_walk_forward_splits(self):
        now = datetime.now(timezone.utc)
        # Create 30 trades chronologically
        positions = []
        for i in range(30):
            # Wide spread on every 3rd trade causing loss
            is_wide_spread = (i % 3 == 0)
            spread = 45.0 if is_wide_spread else 15.0
            pnl = -20.0 if is_wide_spread else 15.0

            positions.append(
                CompletedPositionRecord(
                    position_id=2000 + i,
                    canonical_symbol="XAUUSD",
                    broker_symbol="XAUUSD",
                    direction="BUY",
                    open_time=now - timedelta(hours=60 - i),
                    close_time=now - timedelta(hours=59 - i),
                    open_price=2600.0,
                    close_price=2600.0,
                    volume=0.10,
                    spread_pts=spread,
                    realized_gross_profit=pnl,
                    realized_net_profit=pnl,
                    features_snapshot={"spread_pts": spread, "confluence_score": 75.0},
                )
            )

        candidate = StrategyCandidateRecord(
            candidate_id="CAND_TIGHT_SPREAD_01",
            base_strategy="SMC_SCALPER",
            version="1.1.0",
            parameters={"max_spread_pts": 25.0},  # Filter out wide spread trades!
            target_symbols=["XAUUSD"],
            target_regimes=["ALL"],
        )

        lab = StrategyOptimizationLaboratory()
        evaluated = lab.evaluate_candidate_on_positions(candidate, positions)

        assert evaluated.status == CandidateStatus.OUT_OF_SAMPLE_VALIDATED
        assert "baseline_comparison" in evaluated.backtest_metrics
        # Net profit delta should be strongly positive because losing wide spread trades were filtered
        assert evaluated.backtest_metrics["baseline_comparison"]["net_profit_delta"] > 0
        assert "profit_factor" in evaluated.out_of_sample_metrics


class TestCounterfactualAnalyzer:
    def test_spread_filter_counterfactual_scenario(self):
        now = datetime.now(timezone.utc)
        losing_pos = CompletedPositionRecord(
            position_id=3001,
            canonical_symbol="XAUUSD",
            broker_symbol="XAUUSD",
            direction="BUY",
            open_time=now - timedelta(minutes=10),
            close_time=now,
            open_price=2650.0,
            close_price=2645.0,
            volume=0.10,
            spread_pts=38.0,
            realized_gross_profit=-50.0,
            realized_net_profit=-52.0,
        )

        result = CounterfactualAnalyzer.evaluate_spread_filter_scenario(losing_pos, max_allowed_spread_pts=25.0)

        assert result.simulated_was_skipped is True
        assert result.actual_realized_profit == -52.0
        assert result.simulated_hypothetical_profit == 0.0
        # Outcome difference: 0 - (-52) = +52
        assert result.simulated_outcome_difference == 52.0
        assert "Skipping prevented a net loss" in result.evidence_notes
