"""
Counterfactual Trade Analysis Engine for ATI.
Evaluates "what if" scenarios on completed positions using historically available evidence.
Strictly separates actual realized results from simulated hypothetical outcomes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.intelligence.contracts import CompletedPositionRecord, utc_now

logger = logging.getLogger("ATI.Counterfactual")


@dataclass
class CounterfactualScenarioResult:
    scenario_name: str
    scenario_description: str
    original_trade_id: int
    actual_realized_profit: float
    simulated_hypothetical_profit: float
    simulated_outcome_difference: float
    simulated_was_skipped: bool = False
    evidence_notes: str = ""
    evaluated_at: datetime = field(default_factory=utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_name": self.scenario_name,
            "scenario_description": self.scenario_description,
            "original_trade_id": self.original_trade_id,
            "actual_realized_profit_usd": round(self.actual_realized_profit, 2),
            "simulated_hypothetical_profit_usd": round(self.simulated_hypothetical_profit, 2),
            "simulated_outcome_difference_usd": round(self.simulated_outcome_difference, 2),
            "simulated_was_skipped": self.simulated_was_skipped,
            "evidence_notes": self.evidence_notes,
            "evaluated_at": self.evaluated_at.isoformat(),
        }


class CounterfactualAnalyzer:
    """
    Simulates alternative execution and risk rules on actual trade history.
    Never presents hypothetical outcomes as actual performance.
    """

    @classmethod
    def evaluate_spread_filter_scenario(
        cls,
        position: CompletedPositionRecord,
        max_allowed_spread_pts: float = 25.0,
    ) -> CounterfactualScenarioResult:
        """Evaluates whether skipping trades during wide spread would have prevented losses."""
        snap = position.features_snapshot or {}
        spread = position.spread_pts or snap.get("spread_pts", 15.0)

        actual_profit = position.normalized_net_profit
        if spread > max_allowed_spread_pts:
            # Trade would have been skipped: net profit = 0.0
            hypothetical = 0.0
            diff = hypothetical - actual_profit
            return CounterfactualScenarioResult(
                scenario_name="STRICT_SPREAD_FILTER",
                scenario_description=f"Skip trades when spread exceeds {max_allowed_spread_pts} pts.",
                original_trade_id=position.position_id,
                actual_realized_profit=actual_profit,
                simulated_hypothetical_profit=hypothetical,
                simulated_outcome_difference=diff,
                simulated_was_skipped=True,
                evidence_notes=f"Trade had spread {spread:.1f} pts. Skipping prevented a net loss of ${abs(actual_profit):.2f}." if actual_profit < 0 else f"Trade had spread {spread:.1f} pts. Skipping missed a gain of ${actual_profit:.2f}.",
            )

        return CounterfactualScenarioResult(
            scenario_name="STRICT_SPREAD_FILTER",
            scenario_description=f"Skip trades when spread exceeds {max_allowed_spread_pts} pts.",
            original_trade_id=position.position_id,
            actual_realized_profit=actual_profit,
            simulated_hypothetical_profit=actual_profit,
            simulated_outcome_difference=0.0,
            simulated_was_skipped=False,
            evidence_notes=f"Trade spread ({spread:.1f} pts) was within threshold. Outcome unchanged.",
        )

    @classmethod
    def evaluate_profit_lock_scenario(
        cls,
        position: CompletedPositionRecord,
        lock_threshold_usd: float = 5.0,
    ) -> CounterfactualScenarioResult:
        """Evaluates what would happen if a break-even/profit floor was locked at target profit."""
        actual_profit = position.normalized_net_profit
        snap = position.features_snapshot or {}
        peak_profit = snap.get("peak_profit_usd", actual_profit)

        if peak_profit >= lock_threshold_usd and actual_profit < 1.0:
            # Trade peaked above threshold but retraced to small profit or loss
            hypothetical = max(1.0, lock_threshold_usd * 0.5)  # Break-even / floor lock
            diff = hypothetical - actual_profit
            return CounterfactualScenarioResult(
                scenario_name="PROFIT_FLOOR_LOCK",
                scenario_description=f"Lock minimum profit once trade reaches ${lock_threshold_usd:.2f}.",
                original_trade_id=position.position_id,
                actual_realized_profit=actual_profit,
                simulated_hypothetical_profit=hypothetical,
                simulated_outcome_difference=diff,
                simulated_was_skipped=False,
                evidence_notes=f"Trade peaked at ${peak_profit:.2f} but closed at ${actual_profit:.2f}. Profit lock would have preserved ~${hypothetical:.2f}.",
            )

        return CounterfactualScenarioResult(
            scenario_name="PROFIT_FLOOR_LOCK",
            scenario_description=f"Lock minimum profit once trade reaches ${lock_threshold_usd:.2f}.",
            original_trade_id=position.position_id,
            actual_realized_profit=actual_profit,
            simulated_hypothetical_profit=actual_profit,
            simulated_outcome_difference=0.0,
            simulated_was_skipped=False,
            evidence_notes="Peak profit did not trigger profit floor condition.",
        )
