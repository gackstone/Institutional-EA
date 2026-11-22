"""
Performance and Robustness Metrics Evaluator for ATI Laboratory.
Calculates institutional metrics: Expectancy, Profit Factor, Max Drawdown,
Sharpe, Sortino, Recovery Factor, and Average Holding Time.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List
import numpy as np


class PerformanceEvaluator:
    """Calculates quantitative performance metrics for backtest and live trade sequences."""

    @classmethod
    def calculate_metrics(
        cls,
        profits: List[float],
        durations_sec: Optional[List[float]] = None,
        initial_capital: float = 10000.0,
    ) -> Dict[str, Any]:
        if not profits:
            return {
                "trade_count": 0,
                "net_profit": 0.0,
                "profit_factor": 0.0,
                "win_rate_pct": 0.0,
                "expectancy": 0.0,
                "max_drawdown_amount": 0.0,
                "max_drawdown_pct": 0.0,
                "sharpe_ratio": 0.0,
                "sortino_ratio": 0.0,
                "recovery_factor": 0.0,
                "avg_holding_time_sec": 0.0,
            }

        arr = np.array(profits, dtype=np.float64)
        wins = arr[arr > 0]
        losses = arr[arr < 0]

        total_trades = len(arr)
        win_count = len(wins)
        loss_count = len(losses)

        gross_profit = float(np.sum(wins)) if win_count > 0 else 0.0
        gross_loss = abs(float(np.sum(losses))) if loss_count > 0 else 0.0
        net_profit = float(np.sum(arr))

        win_rate = (win_count / total_trades) * 100.0 if total_trades > 0 else 0.0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)
        expectancy = float(np.mean(arr)) if total_trades > 0 else 0.0

        # Drawdown calculation
        equity_curve = initial_capital + np.cumsum(arr)
        peak = np.maximum.accumulate(equity_curve)
        drawdowns = peak - equity_curve
        max_dd_amount = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0
        max_dd_pct = float(np.max(drawdowns / peak)) * 100.0 if len(drawdowns) > 0 and np.max(peak) > 0 else 0.0

        # Sharpe & Sortino (per-trade)
        std_pnl = float(np.std(arr))
        sharpe = (float(np.mean(arr)) / std_pnl) if std_pnl > 1e-6 else 0.0

        downside_diff = np.minimum(0.0, arr)
        downside_dev = float(np.sqrt(np.mean(downside_diff ** 2)))
        sortino = (float(np.mean(arr)) / downside_dev) if downside_dev > 1e-6 else sharpe

        recovery_factor = (net_profit / max_dd_amount) if max_dd_amount > 0 else (99.0 if net_profit > 0 else 0.0)
        avg_holding = float(np.mean(durations_sec)) if durations_sec and len(durations_sec) > 0 else 0.0

        return {
            "trade_count": total_trades,
            "net_profit": round(net_profit, 2),
            "profit_factor": round(profit_factor, 2),
            "win_rate_pct": round(win_rate, 1),
            "expectancy": round(expectancy, 4),
            "max_drawdown_amount": round(max_dd_amount, 2),
            "max_drawdown_pct": round(max_dd_pct, 2),
            "sharpe_ratio": round(sharpe, 3),
            "sortino_ratio": round(sortino, 3),
            "recovery_factor": round(recovery_factor, 2),
            "avg_holding_time_sec": round(avg_holding, 1),
        }
