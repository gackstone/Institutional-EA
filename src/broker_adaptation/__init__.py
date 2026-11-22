"""
Universal Broker Adaptation Architecture.
Provides automatic account classification, currency normalization,
dynamic symbol discovery, execution capability profiling, and broker constraint validation.
"""

from src.broker_adaptation.account_classifier import (
    AccountClassifier,
    AccountProfile,
    AccountCategory,
    TradeMode,
)
from src.broker_adaptation.currency_normalizer import (
    CurrencyNormalizer,
    NormalizedMonetaryValue,
)
from src.broker_adaptation.symbol_specification import (
    BrokerSymbolSpec,
    extract_symbol_spec,
)
from src.broker_adaptation.symbol_discovery import (
    SymbolDiscoveryEngine,
    DiscoveryResult,
    CANONICAL_UNIVERSE,
    CANONICAL_ALIASES,
)
from src.broker_adaptation.execution_capabilities import (
    ExecutionCapabilitiesEngine,
    ExecutionValidationResult,
    StandardRejectionCode,
)
from src.broker_adaptation.broker_discovery import (
    BrokerCapabilityProfile,
    BrokerDiscoveryManager,
)
from src.broker_adaptation.account_normalization import (
    AccountType,
    NormalizedAccountSnapshot,
    AdaptiveMonetaryThresholds,
    AccountNormalizationEngine,
)

__all__ = [
    "AccountClassifier",
    "AccountProfile",
    "AccountCategory",
    "TradeMode",
    "CurrencyNormalizer",
    "NormalizedMonetaryValue",
    "BrokerSymbolSpec",
    "extract_symbol_spec",
    "SymbolDiscoveryEngine",
    "DiscoveryResult",
    "CANONICAL_UNIVERSE",
    "CANONICAL_ALIASES",
    "ExecutionCapabilitiesEngine",
    "ExecutionValidationResult",
    "StandardRejectionCode",
    "BrokerCapabilityProfile",
    "BrokerDiscoveryManager",
    "AccountType",
    "NormalizedAccountSnapshot",
    "AdaptiveMonetaryThresholds",
    "AccountNormalizationEngine",
]
