"""
Institutional EA Adaptive Trading Intelligence (ATI) Subsystem.
Transforms Institutional EA into a continuously learning, performance-auditing,
and experimentally self-improving algorithmic trading system.
"""

from src.intelligence.contracts import (
    ATIOperatingMode,
    AuditClassification,
    BrokerDealRecord,
    CompletedPositionRecord,
    TradeAuditReport,
    MarketRegimeSnapshot,
    MarketRegimeType,
    StrategyCandidateRecord,
    CandidateStatus,
)
from src.intelligence.config import ATIConfig, ATISafetyConfig
from src.intelligence.storage.repository import ATIRepository, DEFAULT_ATI_DB_PATH
from src.intelligence.facade import AdaptiveTradingIntelligence

__all__ = [
    "ATIOperatingMode",
    "AuditClassification",
    "BrokerDealRecord",
    "CompletedPositionRecord",
    "TradeAuditReport",
    "MarketRegimeSnapshot",
    "MarketRegimeType",
    "StrategyCandidateRecord",
    "CandidateStatus",
    "ATIConfig",
    "ATISafetyConfig",
    "ATIRepository",
    "DEFAULT_ATI_DB_PATH",
    "AdaptiveTradingIntelligence",
]
