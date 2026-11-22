"""
Automated Test Suite for ATI AI Pattern Recognition and Learning Engine.
Verifies temporal train/validation split, feature matrix generation,
calibrated logistic classifier, and drift detection.
"""

from datetime import datetime, timezone, timedelta
import numpy as np
import pytest

from src.intelligence.contracts import CompletedPositionRecord
from src.intelligence.learning.feature_extractor import HistoricalFeatureExtractor
from src.intelligence.learning.model_engine import (
    CalibratedLogisticClassifier,
    AIPatternLearningEngine,
)
from src.intelligence.monitoring.drift_monitor import ModelPerformanceDriftMonitor


class TestFeatureExtractorAndModel:
    def test_feature_vector_structure(self):
        now = datetime.now(timezone.utc)
        feat_dict = HistoricalFeatureExtractor.extract_features_from_context(
            entry_time=now,
            direction="BUY",
            spread_pts=18.0,
            rsi=62.0,
            adx=31.0,
            atr=1.8,
            momentum_pct=0.45,
            session_name="LONDON",
        )

        assert feat_dict["spread_pts"] == 18.0
        assert feat_dict["rsi"] == 62.0
        assert feat_dict["adx"] == 31.0
        assert feat_dict["session_is_london"] == 1.0
        assert feat_dict["direction_is_buy"] == 1.0

    def test_insufficient_sample_size_observation_mode(self):
        engine = AIPatternLearningEngine(random_seed=42)
        X = np.random.randn(8, len(HistoricalFeatureExtractor.FEATURE_NAMES))
        y = np.random.randint(0, 2, size=8)

        report = engine.train_temporal(X, y, HistoricalFeatureExtractor.FEATURE_NAMES)
        assert report.status == "OBSERVATION_ONLY_INSUFFICIENT_DATA"
        assert report.sample_size == 8

        # In observation mode, win probability estimate defaults safely to neutral 0.50
        prob = engine.estimate_win_probability(X[0])
        assert prob == 0.50

    def test_temporal_training_and_calibration(self):
        engine = AIPatternLearningEngine(random_seed=42)
        np.random.seed(42)

        # 40 historical samples
        n = 40
        X = np.random.randn(n, len(HistoricalFeatureExtractor.FEATURE_NAMES))
        # Create clear signal: positive values in column 1 (adx) correlate with win
        y = (X[:, 1] > 0).astype(int)

        report = engine.train_temporal(X, y, HistoricalFeatureExtractor.FEATURE_NAMES)
        assert report.status == "TRAINED"
        assert report.sample_size == 40
        assert report.validation_accuracy >= 0.60
        assert report.brier_score <= 0.30
        assert "adx" in report.feature_importance

        # High ADX should have higher win probability
        test_high_adx = np.zeros((len(HistoricalFeatureExtractor.FEATURE_NAMES),))
        test_high_adx[1] = 2.5
        p_high = engine.estimate_win_probability(test_high_adx)

        test_low_adx = np.zeros((len(HistoricalFeatureExtractor.FEATURE_NAMES),))
        test_low_adx[1] = -2.5
        p_low = engine.estimate_win_probability(test_low_adx)

        assert p_high > p_low


class TestDriftMonitor:
    def test_consecutive_losses_triggers_drift_halt(self):
        now = datetime.now(timezone.utc)
        # Create 6 consecutive losing trades
        positions = []
        for i in range(6):
            positions.append(
                CompletedPositionRecord(
                    position_id=1000 + i,
                    canonical_symbol="XAUUSD",
                    broker_symbol="XAUUSD",
                    direction="BUY",
                    open_time=now - timedelta(minutes=60 - i * 10),
                    close_time=now - timedelta(minutes=50 - i * 10),
                    open_price=2600.0,
                    close_price=2595.0,
                    volume=0.10,
                    realized_gross_profit=-50.0,
                    realized_net_profit=-52.0,
                )
            )

        monitor = ModelPerformanceDriftMonitor()
        report = monitor.check_drift(positions)

        assert report.drift_detected is True
        assert report.consecutive_losses_count == 6
        assert report.action_required == "HALT_MODEL_SCORING_AND_RECALIBRATE"
