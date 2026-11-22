"""
Broker Capability Discovery & Lifecycle Orchestration Service.
Discovers the connected MT5 broker's capabilities, account classification,
tradable symbol mappings, and execution constraints into a unified BrokerCapabilityProfile.
Manages session-aware cache invalidation on account, server, or broker switches.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.broker_adaptation.account_classifier import AccountClassifier, AccountProfile, AccountCategory
from src.broker_adaptation.currency_normalizer import CurrencyNormalizer, NormalizedMonetaryValue
from src.broker_adaptation.symbol_specification import BrokerSymbolSpec
from src.broker_adaptation.symbol_discovery import SymbolDiscoveryEngine, DiscoveryResult, CANONICAL_UNIVERSE
from src.broker_adaptation.execution_capabilities import ExecutionCapabilitiesEngine, ExecutionValidationResult

logger = logging.getLogger("BrokerDiscovery")


@dataclass
class BrokerCapabilityProfile:
    account: AccountProfile
    symbols: Dict[str, DiscoveryResult]
    session_key: str
    discovered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def is_cent(self) -> bool:
        return self.account.is_cent

    @property
    def denomination_factor(self) -> float:
        return self.account.denomination_factor

    @property
    def tradable_symbols(self) -> List[str]:
        return [res.broker_symbol for res in self.symbols.values() if res.is_available and res.broker_symbol]

    @property
    def unavailable_canonical(self) -> List[str]:
        return [canon for canon, res in self.symbols.items() if not res.is_available]

    def get_broker_symbol(self, canonical: str) -> Optional[str]:
        res = self.symbols.get(canonical)
        return res.broker_symbol if res and res.is_available else None

    def get_spec(self, canonical: str) -> Optional[BrokerSymbolSpec]:
        res = self.symbols.get(canonical)
        return res.spec if res else None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_key": self.session_key,
            "discovered_at": self.discovered_at,
            "account": {
                "login": self.account.login,
                "server": self.account.server,
                "company": self.account.company,
                "currency": self.account.currency,
                "category": self.account.category.value,
                "trade_mode": self.account.trade_mode.value,
                "leverage": self.account.leverage,
                "denomination_factor": self.account.denomination_factor,
                "native_balance": self.account.native_balance,
                "native_equity": self.account.native_equity,
                "native_free_margin": self.account.native_free_margin,
                "normalized_balance": self.account.normalized_balance,
                "normalized_equity": self.account.normalized_equity,
                "confidence": self.account.confidence,
                "evidence": self.account.evidence,
                "anomalies": self.account.anomalies,
            },
            "symbols": {canon: res.to_dict() for canon, res in self.symbols.items()},
            "tradable_symbols": self.tradable_symbols,
            "unavailable_symbols": self.unavailable_canonical,
        }


class BrokerDiscoveryManager:
    """
    Orchestrates broker capability discovery, account profiling, and symbol resolution.
    Caches profile per session (server:login) and automatically invalidates on reconnect or account change.
    """

    def __init__(
        self,
        classifier: Optional[AccountClassifier] = None,
        normalizer: Optional[CurrencyNormalizer] = None,
        symbol_engine: Optional[SymbolDiscoveryEngine] = None,
        exec_engine: Optional[ExecutionCapabilitiesEngine] = None,
    ):
        self.classifier = classifier or AccountClassifier()
        self.normalizer = normalizer or CurrencyNormalizer()
        self.symbol_engine = symbol_engine or SymbolDiscoveryEngine()
        self.exec_engine = exec_engine or ExecutionCapabilitiesEngine()

        self._active_profile: Optional[BrokerCapabilityProfile] = None
        self._last_session_key: str = ""

    @property
    def active_profile(self) -> Optional[BrokerCapabilityProfile]:
        return self._active_profile

    def invalidate(self) -> None:
        """Explicitly clear cache on account/broker change."""
        self._active_profile = None
        self._last_session_key = ""
        self.symbol_engine.clear()
        logger.info("[BrokerDiscoveryManager] Broker capability cache invalidated.")

    def discover(
        self,
        account_info: Any,
        terminal_info: Any = None,
        inventory: Optional[List[Any]] = None,
        mt5_module: Any = None,
        force_refresh: bool = False
    ) -> BrokerCapabilityProfile:
        """
        Discovers broker profile, classifies account, resolves symbols, and constructs capability profile.
        Detects session changes and invalidates cache if necessary.
        """
        # Extract basic login and server to check session
        def _get(obj: Any, key: str, default: Any = None) -> Any:
            if obj is None:
                return default
            if hasattr(obj, key):
                return getattr(obj, key)
            if isinstance(obj, dict):
                return obj.get(key, default)
            return default

        login = int(_get(account_info, "login", 0) or 0)
        server = str(_get(account_info, "server", "") or "").strip()
        current_session_key = f"{server}:{login}"

        # Session invalidation guard
        if current_session_key != self._last_session_key and self._last_session_key != "":
            logger.info(
                f"[BrokerDiscoveryManager] Account/server switched from '{self._last_session_key}' "
                f"to '{current_session_key}'. Invalidating previous profile cache."
            )
            self.invalidate()

        if self._active_profile is not None and not force_refresh and current_session_key == self._last_session_key:
            return self._active_profile

        # Retrieve inventory from mt5_module if not provided
        sym_inventory = inventory
        if sym_inventory is None and mt5_module is not None and hasattr(mt5_module, "symbols_get"):
            try:
                sym_inventory = list(mt5_module.symbols_get() or [])
            except Exception as e:
                logger.debug(f"[BrokerDiscoveryManager] symbols_get failed: {e}")
                sym_inventory = []

        symbols_sample = []
        if sym_inventory:
            for item in sym_inventory[:30]:
                name = item.name if hasattr(item, "name") else str(item.get("name", item) if isinstance(item, dict) else item)
                symbols_sample.append(name)

        # 1. Classify account
        account_prof = self.classifier.classify(
            account_info=account_info,
            terminal_info=terminal_info,
            symbols_sample=symbols_sample
        )

        # 2. Discover symbols
        symbols_disc = self.symbol_engine.discover_symbols(
            inventory=sym_inventory or [],
            is_cent_account=account_prof.is_cent,
            mt5_module=mt5_module
        )

        profile = BrokerCapabilityProfile(
            account=account_prof,
            symbols=symbols_disc,
            session_key=current_session_key
        )

        self._active_profile = profile
        self._last_session_key = current_session_key

        logger.info(
            f"[BrokerDiscoveryManager] Discovered Profile for {current_session_key}: "
            f"Category={account_prof.category.value} | Currency={account_prof.currency} | "
            f"DenomFactor={account_prof.denomination_factor} | Tradable={profile.tradable_symbols} | "
            f"Unavailable={profile.unavailable_canonical}"
        )

        return profile
