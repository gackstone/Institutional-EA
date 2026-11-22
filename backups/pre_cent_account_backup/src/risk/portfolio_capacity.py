"""
Dynamic Portfolio Capacity Engine.
Replaces fixed position-count ceilings (e.g., 3-max / 7-max) with continuous,
risk-budget and margin-aware portfolio capacity evaluation.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.core.contracts import AccountInfo, OrderType, Position, SignalCandidate, SymbolInfo
from src.core.symbol_universe import get_symbol_universe


@dataclass
class PortfolioCapacityResult:
    allowed: bool
    rejection_code: Optional[str] = None
    rejection_reason: Optional[str] = None
    setup_id: str = ""
    symbol: str = ""
    canonical_symbol: str = ""
    direction: str = ""
    timestamp: str = ""
    equity: float = 0.0
    free_margin: float = 0.0
    margin_required: float = 0.0
    projected_margin_level_pct: float = 0.0
    projected_margin_utilization_pct: float = 0.0
    aggregate_risk_budget_usd: float = 0.0
    open_risk_usd: float = 0.0
    pending_risk_usd: float = 0.0
    proposed_risk_usd: float = 0.0
    remaining_risk_capacity_usd: float = 0.0
    symbol_risk_budget_usd: float = 0.0
    symbol_open_risk_usd: float = 0.0
    remaining_symbol_capacity_usd: float = 0.0
    open_positions_total: int = 0
    open_positions_on_symbol: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "rejection_code": self.rejection_code,
            "rejection_reason": self.rejection_reason,
            "setup_id": self.setup_id,
            "symbol": self.symbol,
            "canonical_symbol": self.canonical_symbol,
            "direction": self.direction,
            "timestamp": self.timestamp,
            "equity": round(self.equity, 2),
            "free_margin": round(self.free_margin, 2),
            "margin_required": round(self.margin_required, 2),
            "projected_margin_level_pct": round(self.projected_margin_level_pct, 2),
            "projected_margin_utilization_pct": round(self.projected_margin_utilization_pct, 2),
            "aggregate_risk_budget_usd": round(self.aggregate_risk_budget_usd, 2),
            "open_risk_usd": round(self.open_risk_usd, 2),
            "pending_risk_usd": round(self.pending_risk_usd, 2),
            "proposed_risk_usd": round(self.proposed_risk_usd, 2),
            "remaining_risk_capacity_usd": round(self.remaining_risk_capacity_usd, 2),
            "symbol_risk_budget_usd": round(self.symbol_risk_budget_usd, 2),
            "symbol_open_risk_usd": round(self.symbol_open_risk_usd, 2),
            "remaining_symbol_capacity_usd": round(self.remaining_symbol_capacity_usd, 2),
            "open_positions_total": self.open_positions_total,
            "open_positions_on_symbol": self.open_positions_on_symbol,
        }


class DynamicPortfolioCapacityEngine:
    """
    Evaluates whether a new setup fits within remaining portfolio risk,
    per-instrument exposure budget, and broker margin constraints.
    Never uses an arbitrary position-count ceiling as a proxy for risk.
    """

    def __init__(
        self,
        max_aggregate_open_risk_percent: float = 6.0,
        max_symbol_risk_percent: float = 4.0,
        min_margin_level_percent: float = 150.0,
        max_margin_utilization_percent: float = 80.0,
    ):
        self.max_aggregate_open_risk_percent = float(max_aggregate_open_risk_percent)
        self.max_symbol_risk_percent = float(max_symbol_risk_percent)
        self.min_margin_level_percent = float(min_margin_level_percent)
        self.max_margin_utilization_percent = float(max_margin_utilization_percent)

    @staticmethod
    def _canonical(symbol: str) -> str:
        universe = get_symbol_universe()
        return universe.get_canonical_symbol(symbol) or str(symbol).upper()

    @staticmethod
    def _estimate_position_risk_usd(pos: Position) -> float:
        init_risk = float(getattr(pos, "initial_risk_amount", 0.0) or 0.0)
        if init_risk > 0.0:
            return init_risk
        sl = float(getattr(pos, "stop_loss", 0.0) or 0.0)
        op = float(getattr(pos, "open_price", 0.0) or 0.0)
        vol = float(getattr(pos, "volume", 0.0) or 0.0)
        if sl > 0.0 and op > 0.0 and vol > 0.0:
            return abs(op - sl) * vol
        return 0.0

    def evaluate_capacity(
        self,
        candidate: SignalCandidate,
        account: AccountInfo,
        active_positions: List[Position],
        proposed_monetary_risk: float,
        margin_required: float = 0.0,
        pending_orders_risk_usd: float = 0.0,
    ) -> PortfolioCapacityResult:
        now_iso = datetime.now(timezone.utc).isoformat()
        canon = self._canonical(candidate.symbol)
        equity = float(getattr(account, "equity", 0.0) or getattr(account, "balance", 0.0) or 0.0)
        free_margin = float(getattr(account, "free_margin", 0.0) or 0.0)
        used_margin = float(getattr(account, "margin", 0.0) or 0.0)

        open_risk_usd = sum(self._estimate_position_risk_usd(p) for p in active_positions)
        sym_positions = [p for p in active_positions if self._canonical(p.symbol) == canon]
        symbol_open_risk_usd = sum(self._estimate_position_risk_usd(p) for p in sym_positions)

        agg_budget_usd = equity * (self.max_aggregate_open_risk_percent / 100.0) if equity > 0 else 0.0
        sym_budget_usd = equity * (self.max_symbol_risk_percent / 100.0) if equity > 0 else 0.0

        remaining_agg_usd = max(0.0, agg_budget_usd - (open_risk_usd + pending_orders_risk_usd))
        remaining_sym_usd = max(0.0, sym_budget_usd - symbol_open_risk_usd)

        projected_margin = used_margin + max(0.0, margin_required)
        projected_margin_level = (equity / projected_margin * 100.0) if (projected_margin > 0 and equity > 0) else 9999.0
        projected_margin_util = (projected_margin / equity * 100.0) if equity > 0 else 0.0

        base_res = PortfolioCapacityResult(
            allowed=True,
            setup_id=candidate.id,
            symbol=candidate.symbol,
            canonical_symbol=canon,
            direction=candidate.direction.value,
            timestamp=now_iso,
            equity=equity,
            free_margin=free_margin,
            margin_required=margin_required,
            projected_margin_level_pct=projected_margin_level,
            projected_margin_utilization_pct=projected_margin_util,
            aggregate_risk_budget_usd=agg_budget_usd,
            open_risk_usd=open_risk_usd,
            pending_risk_usd=pending_orders_risk_usd,
            proposed_risk_usd=proposed_monetary_risk,
            remaining_risk_capacity_usd=remaining_agg_usd,
            symbol_risk_budget_usd=sym_budget_usd,
            symbol_open_risk_usd=symbol_open_risk_usd,
            remaining_symbol_capacity_usd=remaining_sym_usd,
            open_positions_total=len(active_positions),
            open_positions_on_symbol=len(sym_positions),
        )

        # 1. Free margin sufficiency
        if margin_required > free_margin:
            base_res.allowed = False
            base_res.rejection_code = "INSUFFICIENT_MARGIN"
            base_res.rejection_reason = (
                f"Insufficient free margin: required ${margin_required:.2f} > available ${free_margin:.2f}."
            )
            return base_res

        # 2. Projected margin level & utilization
        if projected_margin > 0 and projected_margin_level < self.min_margin_level_percent:
            base_res.allowed = False
            base_res.rejection_code = "MARGIN_LEVEL_CRITICAL"
            base_res.rejection_reason = (
                f"Projected margin level ({projected_margin_level:.1f}%) below minimum "
                f"({self.min_margin_level_percent:.1f}%)."
            )
            return base_res

        if equity > 0 and projected_margin_util > self.max_margin_utilization_percent:
            base_res.allowed = False
            base_res.rejection_code = "MARGIN_UTILIZATION_EXCEEDED"
            base_res.rejection_reason = (
                f"Projected margin utilization ({projected_margin_util:.1f}%) exceeds cap "
                f"({self.max_margin_utilization_percent:.1f}%)."
            )
            return base_res

        # 3. Aggregate portfolio risk budget
        if equity > 0 and (open_risk_usd + pending_orders_risk_usd + proposed_monetary_risk) > agg_budget_usd + 1e-6:
            base_res.allowed = False
            base_res.rejection_code = "RISK_BUDGET_EXHAUSTED"
            base_res.rejection_reason = (
                f"Aggregate portfolio risk budget exhausted: open (${open_risk_usd:.2f}) + pending (${pending_orders_risk_usd:.2f}) "
                f"+ proposed (${proposed_monetary_risk:.2f}) > budget ${agg_budget_usd:.2f} "
                f"({self.max_aggregate_open_risk_percent:.1f}% of equity)."
            )
            return base_res

        # 4. Per-instrument risk budget
        if equity > 0 and (symbol_open_risk_usd + proposed_monetary_risk) > sym_budget_usd + 1e-6:
            base_res.allowed = False
            base_res.rejection_code = "SYMBOL_RISK_BUDGET_EXHAUSTED"
            base_res.rejection_reason = (
                f"Per-instrument risk budget exhausted for {canon}: open (${symbol_open_risk_usd:.2f}) "
                f"+ proposed (${proposed_monetary_risk:.2f}) > budget ${sym_budget_usd:.2f} "
                f"({self.max_symbol_risk_percent:.1f}% of equity)."
            )
            return base_res

        return base_res

    def compute_portfolio_snapshot(
        self,
        account: AccountInfo,
        active_positions: List[Position],
        pending_orders_count: int = 0,
        pending_orders_risk_usd: float = 0.0,
    ) -> Dict[str, Any]:
        equity = float(getattr(account, "equity", 0.0) or getattr(account, "balance", 0.0) or 0.0)
        used_margin = float(getattr(account, "margin", 0.0) or 0.0)
        free_margin = float(getattr(account, "free_margin", 0.0) or 0.0)

        open_by_sym: Dict[str, int] = {}
        risk_by_sym_usd: Dict[str, float] = {}
        total_open_risk = 0.0
        floating_pnl = 0.0

        for pos in active_positions:
            canon = self._canonical(pos.symbol)
            open_by_sym[canon] = open_by_sym.get(canon, 0) + 1
            r = self._estimate_position_risk_usd(pos)
            risk_by_sym_usd[canon] = risk_by_sym_usd.get(canon, 0.0) + r
            total_open_risk += r
            floating_pnl += float(getattr(pos, "profit", 0.0) or 0.0)

        agg_budget_usd = equity * (self.max_aggregate_open_risk_percent / 100.0) if equity > 0 else 0.0
        remaining_risk_usd = max(0.0, agg_budget_usd - (total_open_risk + pending_orders_risk_usd))
        current_risk_pct = ((total_open_risk + pending_orders_risk_usd) / equity * 100.0) if equity > 0 else 0.0
        remaining_risk_pct = (remaining_risk_usd / equity * 100.0) if equity > 0 else 0.0
        margin_util_pct = (used_margin / equity * 100.0) if equity > 0 else 0.0

        return {
            "total_open_positions": len(active_positions),
            "open_positions_by_instrument": open_by_sym,
            "pending_orders": pending_orders_count,
            "aggregate_risk_budget_pct": self.max_aggregate_open_risk_percent,
            "per_instrument_risk_budget_pct": self.max_symbol_risk_percent,
            "current_portfolio_risk_pct": round(current_risk_pct, 2),
            "available_risk_capacity_pct": round(remaining_risk_pct, 2),
            "available_risk_capacity_usd": round(remaining_risk_usd, 2),
            "symbol_risk_usd": {k: round(v, 2) for k, v in risk_by_sym_usd.items()},
            "free_margin": round(free_margin, 2),
            "margin_utilization_pct": round(margin_util_pct, 2),
            "floating_pnl": round(floating_pnl, 2),
        }
