"""
Execution Intelligence Subsystem for ATI.
Analyzes broker execution quality: latency, slippage, partial fills, spread anomalies,
broker rejection retcodes, and stop-loss/take-profit modification reliability.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.intelligence.contracts import CompletedPositionRecord, utc_now

logger = logging.getLogger("ATI.Execution")


@dataclass
class ExecutionQualityMetrics:
    total_positions_analyzed: int = 0
    average_slippage_pts: float = 0.0
    max_slippage_pts: float = 0.0
    partial_fills_count: int = 0
    average_costs_usd: float = 0.0
    cost_drag_ratio: float = 0.0  # (commissions + swap) / gross profits
    rejected_orders_count: int = 0
    recurring_broker_issues: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    analyzed_at: datetime = field(default_factory=utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_positions_analyzed": self.total_positions_analyzed,
            "average_slippage_pts": round(self.average_slippage_pts, 2),
            "max_slippage_pts": round(self.max_slippage_pts, 2),
            "partial_fills_count": self.partial_fills_count,
            "average_costs_usd": round(self.average_costs_usd, 4),
            "cost_drag_ratio": round(self.cost_drag_ratio, 4),
            "rejected_orders_count": self.rejected_orders_count,
            "recurring_broker_issues": self.recurring_broker_issues,
            "recommendations": self.recommendations,
            "analyzed_at": self.analyzed_at.isoformat(),
        }


class ExecutionIntelligenceAnalyzer:
    """
    Subsystem for evaluating broker execution quality and detecting execution anomalies.
    """

    def analyze_positions_execution(
        self,
        positions: List[CompletedPositionRecord],
        rejection_events: Optional[List[Dict[str, Any]]] = None,
    ) -> ExecutionQualityMetrics:
        """Evaluates historical execution quality across completed positions."""
        rejection_events = rejection_events or []
        metrics = ExecutionQualityMetrics(total_positions_analyzed=len(positions))

        if not positions and not rejection_events:
            return metrics

        slippages = [p.slippage_pts for p in positions if p.slippage_pts > 0]
        if slippages:
            metrics.average_slippage_pts = float(sum(slippages) / len(slippages))
            metrics.max_slippage_pts = float(max(slippages))

        metrics.partial_fills_count = sum(p.partial_closes_count for p in positions)

        total_costs = sum(abs(p.commission) + abs(p.swap) for p in positions)
        total_gross = sum(p.realized_gross_profit for p in positions if p.realized_gross_profit > 0)

        if positions:
            metrics.average_costs_usd = float(total_costs / len(positions))

        if total_gross > 0:
            metrics.cost_drag_ratio = float(total_costs / total_gross)

        metrics.rejected_orders_count = len(rejection_events)

        # Diagnose recurring issues
        if metrics.average_slippage_pts > 20.0:
            metrics.recurring_broker_issues.append(
                f"Elevated average slippage detected ({metrics.average_slippage_pts:.1f} pts)."
            )
            metrics.recommendations.append("Consider tightening broker deviation tolerance or avoiding news windows.")

        if metrics.cost_drag_ratio > 0.35:
            metrics.recurring_broker_issues.append(
                f"High cost drag ratio ({metrics.cost_drag_ratio*100:.1f}% of gross gains paid in spread/fees)."
            )
            metrics.recommendations.append("Evaluate cent vs standard commission structure or raise minimum take-profit target.")

        if metrics.partial_fills_count > len(positions) * 0.4 and len(positions) >= 5:
            metrics.recurring_broker_issues.append(
                f"Frequent partial fills ({metrics.partial_fills_count} across {len(positions)} trades)."
            )
            metrics.recommendations.append("Verify broker liquidity depth and order filling policy (IOC vs FOK vs RETURN).")

        for rej in rejection_events:
            retcode = rej.get("retcode", 0)
            comment = rej.get("comment", "")
            if retcode in (10014, 10015, 10016):  # Invalid volume, price, or stops
                metrics.recurring_broker_issues.append(f"Broker rejected orders with retcode {retcode} ({comment}).")
                metrics.recommendations.append("Check symbol min volume step and freeze level in broker registry.")
                break

        return metrics
