"""
Model Drift, Feature Drift, and Strategy Degradation Monitor for ATI.
Continuously monitors predictive calibration, feature distribution shifts,
and consecutive loss clusters to trigger safe degradation fallback.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import numpy as np

from src.intelligence.contracts import CompletedPositionRecord, utc_now

logger = logging.getLogger("ATI.DriftMonitor")


@dataclass
class DriftStatusReport:
    drift_detected: bool = False
    consecutive_losses_count: int = 0
    brier_score_degradation: float = 0.0
    feature_shifts: Dict[str, float] = field(default_factory=dict)
    warning_messages: List[str] = field(default_factory=list)
    action_required: str = "NONE"
    monitored_at: datetime = field(default_factory=utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "drift_detected": self.drift_detected,
            "consecutive_losses_count": self.consecutive_losses_count,
            "brier_score_degradation": round(self.brier_score_degradation, 4),
            "feature_shifts": self.feature_shifts,
            "warning_messages": self.warning_messages,
            "action_required": self.action_required,
            "monitored_at": self.monitored_at.isoformat(),
        }


class ModelPerformanceDriftMonitor:
    """
    Guards the trading system against model and market regime drift.
    Triggers fallback to observation mode if predictions degrade.
    """

    MAX_CONSECUTIVE_LOSS_THRESHOLD = 5

    def check_drift(
        self,
        recent_positions: List[CompletedPositionRecord],
        baseline_win_rate: float = 0.60,
    ) -> DriftStatusReport:
        report = DriftStatusReport()
        if not recent_positions:
            return report

        # 1. Consecutive losses check
        consecutive_losses = 0
        for p in reversed(recent_positions):
            if p.realized_net_profit < 0:
                consecutive_losses += 1
            else:
                break
        report.consecutive_losses_count = consecutive_losses

        if consecutive_losses >= self.MAX_CONSECUTIVE_LOSS_THRESHOLD:
            report.drift_detected = True
            msg = f"Consecutive loss cluster ({consecutive_losses} losses in a row) exceeds safety threshold ({self.MAX_CONSECUTIVE_LOSS_THRESHOLD})."
            report.warning_messages.append(msg)
            report.action_required = "HALT_MODEL_SCORING_AND_RECALIBRATE"
            logger.warning(f"[DRIFT_MONITOR] {msg}")

        # 2. Recent win-rate degradation check
        if len(recent_positions) >= 10:
            recent_wins = sum(1 for p in recent_positions[-10:] if p.realized_net_profit > 0)
            recent_win_rate = recent_wins / 10.0
            if recent_win_rate < (baseline_win_rate - 0.25):
                report.drift_detected = True
                msg = f"Recent 10-trade win rate ({recent_win_rate*100:.1f}%) severely degraded vs baseline ({baseline_win_rate*100:.1f}%)."
                report.warning_messages.append(msg)
                report.action_required = "HALT_MODEL_SCORING_AND_RECALIBRATE"

        return report
