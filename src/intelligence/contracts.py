"""
Data contracts and typing definitions for the MT5-001 Adaptive Trading Intelligence (ATI) Subsystem.
Strictly defines models for trades, deals, audits, regimes, models, experiments, and candidates.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


class ATIOperatingMode(str, Enum):
    OBSERVATION = "OBSERVATION"
    LEARNING = "LEARNING"
    EXPERIMENTATION = "EXPERIMENTATION"
    SHADOW = "SHADOW"
    APPROVAL = "APPROVAL"
    CONTROLLED_ADAPTATION = "CONTROLLED_ADAPTATION"
    DISABLED = "DISABLED"


class AuditClassification(str, Enum):
    STRATEGY_FAILURE = "STRATEGY_FAILURE"
    ENTRY_TIMING_FAILURE = "ENTRY_TIMING_FAILURE"
    EXIT_OPTIMIZATION_OPPORTUNITY = "EXIT_OPTIMIZATION_OPPORTUNITY"
    EXECUTION_FAILURE = "EXECUTION_FAILURE"
    MARKET_REGIME_MISMATCH = "MARKET_REGIME_MISMATCH"
    SPREAD_OR_COST_ISSUE = "SPREAD_OR_COST_ISSUE"
    RISK_POLICY_VIOLATION = "RISK_POLICY_VIOLATION"
    NORMAL_STATISTICAL_LOSS = "NORMAL_STATISTICAL_LOSS"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class MarketRegimeType(str, Enum):
    STRONG_BULLISH = "STRONG_BULLISH"
    STRONG_BEARISH = "STRONG_BEARISH"
    SIDEWAYS_CONSOLIDATION = "SIDEWAYS_CONSOLIDATION"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    UNSTABLE_SPREAD = "UNSTABLE_SPREAD"
    ABNORMAL_EXECUTION = "ABNORMAL_EXECUTION"
    UNKNOWN = "UNKNOWN"


class CandidateStatus(str, Enum):
    DRAFT = "DRAFT"
    BACKTESTED = "BACKTESTED"
    WALK_FORWARD_VALIDATED = "WALK_FORWARD_VALIDATED"
    OUT_OF_SAMPLE_VALIDATED = "OUT_OF_SAMPLE_VALIDATED"
    SHADOW_TESTING = "SHADOW_TESTING"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ACTIVE_DEPLOYED = "ACTIVE_DEPLOYED"
    ROLLED_BACK = "ROLLED_BACK"


@dataclass
class BrokerDealRecord:
    deal_ticket: int
    order_ticket: int
    position_id: int
    symbol: str
    canonical_symbol: str
    deal_type: str  # DEAL_TYPE_BUY, DEAL_TYPE_SELL
    entry_type: str  # ENTRY_IN, ENTRY_OUT, ENTRY_INOUT, ENTRY_OUT_BY
    volume: float
    price: float
    commission: float = 0.0
    swap: float = 0.0
    profit: float = 0.0
    fee: float = 0.0
    magic: int = 0
    comment: str = ""
    timestamp: datetime = field(default_factory=utc_now)
    account_number: int = 0
    account_currency: str = "USD"
    denomination_factor: float = 1.0

    @property
    def normalized_profit(self) -> float:
        denom = self.denomination_factor if self.denomination_factor > 0 else 1.0
        return round(self.profit / denom, 4)

    @property
    def normalized_commission(self) -> float:
        denom = self.denomination_factor if self.denomination_factor > 0 else 1.0
        return round(self.commission / denom, 4)

    @property
    def normalized_swap(self) -> float:
        denom = self.denomination_factor if self.denomination_factor > 0 else 1.0
        return round(self.swap / denom, 4)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else str(self.timestamp)
        return d


@dataclass
class CompletedPositionRecord:
    position_id: int
    canonical_symbol: str
    broker_symbol: str
    direction: str  # BUY or SELL
    open_time: datetime
    close_time: datetime
    open_price: float
    close_price: float
    volume: float
    initial_sl: float = 0.0
    initial_tp: float = 0.0
    realized_gross_profit: float = 0.0
    realized_net_profit: float = 0.0
    commission: float = 0.0
    swap: float = 0.0
    slippage_pts: float = 0.0
    spread_pts: float = 0.0
    exit_reason: str = "UNKNOWN"
    strategy_id: str = "DEFAULT"
    strategy_version: str = "1.0.0"
    signal_id: str = ""
    account_number: int = 0
    account_currency: str = "USD"
    account_type: str = "STANDARD"  # STANDARD, CENT, MICRO
    denomination_factor: float = 1.0
    entry_deals: List[int] = field(default_factory=list)
    exit_deals: List[int] = field(default_factory=list)
    partial_closes_count: int = 0
    features_snapshot: Dict[str, Any] = field(default_factory=dict)
    reconciled_at: datetime = field(default_factory=utc_now)

    @property
    def normalized_net_profit(self) -> float:
        denom = self.denomination_factor if self.denomination_factor > 0 else 1.0
        return round(self.realized_net_profit / denom, 4)

    @property
    def duration_seconds(self) -> float:
        return (self.close_time - self.open_time).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["open_time"] = self.open_time.isoformat() if isinstance(self.open_time, datetime) else str(self.open_time)
        d["close_time"] = self.close_time.isoformat() if isinstance(self.close_time, datetime) else str(self.close_time)
        d["reconciled_at"] = self.reconciled_at.isoformat() if isinstance(self.reconciled_at, datetime) else str(self.reconciled_at)
        return d


@dataclass
class TradeAuditReport:
    trade_id: int
    audit_timestamp: datetime = field(default_factory=utc_now)
    audit_version: str = "1.0.0"
    classification: AuditClassification = AuditClassification.INSUFFICIENT_EVIDENCE
    root_cause_confidence: float = 0.0  # 0.0 to 1.0
    entry_quality_score: float = 0.0  # 0.0 to 100.0
    exit_quality_score: float = 0.0   # 0.0 to 100.0
    execution_quality_score: float = 0.0  # 0.0 to 100.0
    risk_quality_score: float = 0.0   # 0.0 to 100.0
    detected_issues: List[str] = field(default_factory=list)
    supporting_evidence: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)
    suggested_experiments: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "COMPLETED"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["classification"] = self.classification.value
        d["audit_timestamp"] = self.audit_timestamp.isoformat() if isinstance(self.audit_timestamp, datetime) else str(self.audit_timestamp)
        return d


@dataclass
class MarketRegimeSnapshot:
    canonical_symbol: str
    timestamp: datetime
    regime: MarketRegimeType
    confidence: float
    adx_value: float = 0.0
    atr_value: float = 0.0
    trend_slope: float = 0.0
    volatility_ratio: float = 1.0
    spread_pts: float = 0.0
    session_name: str = "UNKNOWN"
    features: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["regime"] = self.regime.value
        d["timestamp"] = self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else str(self.timestamp)
        return d


@dataclass
class StrategyCandidateRecord:
    candidate_id: str
    base_strategy: str
    version: str
    parameters: Dict[str, Any]
    target_symbols: List[str]
    target_regimes: List[str]
    creation_timestamp: datetime = field(default_factory=utc_now)
    status: CandidateStatus = CandidateStatus.DRAFT
    rationale: str = ""
    checksum: str = ""
    author: str = "ATI_LABORATORY"
    backtest_metrics: Dict[str, Any] = field(default_factory=dict)
    walk_forward_metrics: Dict[str, Any] = field(default_factory=dict)
    out_of_sample_metrics: Dict[str, Any] = field(default_factory=dict)
    shadow_test_metrics: Dict[str, Any] = field(default_factory=dict)
    promotion_notes: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["creation_timestamp"] = self.creation_timestamp.isoformat() if isinstance(self.creation_timestamp, datetime) else str(self.creation_timestamp)
        d["approved_at"] = self.approved_at.isoformat() if self.approved_at else None
        return d
