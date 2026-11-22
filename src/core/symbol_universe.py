"""
Strict Two-Symbol Trading Universe and Broker-Aware Resolution Engine.
Exclusively recognizes and permits:
1. XAUUSD — Gold
2. BTCUSD — Bitcoin

Rejects all symbols outside this approved universe throughout the entire trading pipeline,
with universal codebase-level exclusion of USDJPY and all its broker variants.
Integrates with BrokerSymbolResolver to dynamically detect broker symbol suffix/prefix variations
(e.g., XAUUSD.m, XAUUSD.c, BTCUSD.m, BTCUSD.c, etc.).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple, Any

from src.core.broker_resolver import BrokerSymbolResolver, SymbolResolutionResult
from src.broker_adaptation.symbol_discovery import SymbolDiscoveryEngine, DiscoveryResult
from src.broker_adaptation.symbol_specification import BrokerSymbolSpec

logger = logging.getLogger("SymbolUniverse")

# Strict, non-negotiable canonical approved trading universe: Gold and Bitcoin ONLY
APPROVED_CANONICAL_SYMBOLS: Tuple[str, ...] = ("XAUUSD", "BTCUSD")

# Common broker aliases for the 2 canonical symbols (including cent .c variants)
APPROVED_CANONICAL_ALIASES: Dict[str, Set[str]] = {
    "XAUUSD": {
        "XAUUSD", "GOLD", "XAU",
        "XAUUSD.M", "XAUUSDM", "XAUUSD.MICRO",
        "GOLD.M", "GOLDM",
        "XAUUSD.C", "XAUUSDC", "GOLD.C", "GOLDC", "XAUUSD-CENT", "XAUUSD.CENT",
        "XAUUSD.PRO", "XAUUSD.RAW", "XAUUSD.ECN", "XAUUSD.STD",
    },
    "BTCUSD": {
        "BTCUSD", "BITCOIN", "BTC",
        "BTCUSD.M", "BTCUSDM", "BTCUSD.MICRO",
        "BTCUSD.C", "BTCUSDC", "BITCOIN.C", "BTCUSD-CENT", "BTCUSD.CENT",
        "BTCUSD.PRO", "BTCUSD.RAW", "BTCUSD.ECN", "BTCUSD.STD",
    },
}


@dataclass
class ResolvedInstrument:
    canonical: str
    broker_symbol: str
    is_available: bool = True
    digits: int = 2
    point: float = 0.01
    contract_size: float = 1.0
    tick_size: float = 0.01
    tick_value: float = 1.0
    volume_min: float = 0.01
    volume_max: float = 50.0
    volume_step: float = 0.01
    broker_server: str = ""
    account_type: str = "STANDARD"
    suffix: str = ""
    trade_mode: int = 4
    filling_mode: int = 1
    stop_level: int = 0
    freeze_level: int = 0
    validation_status: str = "VALIDATED"
    discovery_timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def canonical_symbol(self) -> str:
        return self.canonical

    @property
    def actual_broker_symbol(self) -> str:
        return self.broker_symbol

    @property
    def point_size(self) -> float:
        return self.point

    @property
    def minimum_volume(self) -> float:
        return self.volume_min

    @property
    def maximum_volume(self) -> float:
        return self.volume_max

    def to_dict(self) -> Dict[str, Any]:
        return {
            "canonical_symbol": self.canonical,
            "actual_broker_symbol": self.broker_symbol,
            "broker_symbol": self.broker_symbol,
            "broker_server": self.broker_server,
            "account_type": self.account_type,
            "suffix": self.suffix,
            "contract_size": self.contract_size,
            "digits": self.digits,
            "point_size": self.point,
            "tick_size": self.tick_size,
            "tick_value": self.tick_value,
            "minimum_volume": self.volume_min,
            "maximum_volume": self.volume_max,
            "volume_step": self.volume_step,
            "trade_mode": self.trade_mode,
            "filling_mode": self.filling_mode,
            "stop_level": self.stop_level,
            "freeze_level": self.freeze_level,
            "discovery_timestamp": self.discovery_timestamp,
            "validation_status": self.validation_status,
        }


class SpecializedSymbolUniverse:
    """
    Authoritative manager for the strict two-symbol trading universe (XAUUSD, BTCUSD).
    Universally excludes USDJPY across all account types and execution pathways.
    Provides broker symbol resolution, bidirectional mapping, contract specifications, and validation guards.
    """

    def __init__(self, broker_resolver: Optional[BrokerSymbolResolver] = None):
        self.resolver = broker_resolver or BrokerSymbolResolver()
        self._canonical_to_broker: Dict[str, str] = {
            "XAUUSD": "XAUUSD",
            "BTCUSD": "BTCUSD",
        }
        self._broker_to_canonical: Dict[str, str] = {
            "XAUUSD": "XAUUSD",
            "BTCUSD": "BTCUSD",
        }
        self._resolved_instruments: Dict[str, ResolvedInstrument] = {}
        self._initialized: bool = False
        self._last_blocked_log_time: Dict[str, float] = {}

    def invalidate(self) -> None:
        """Invalidate all resolved symbol mappings on account or server changes."""
        self.resolver.invalidate_cache()
        self._canonical_to_broker = {c: c for c in APPROVED_CANONICAL_SYMBOLS}
        self._broker_to_canonical = {c: c for c in APPROVED_CANONICAL_SYMBOLS}
        self._resolved_instruments.clear()
        self._initialized = False
        logger.info("[SpecializedSymbolUniverse] Symbol universe mappings invalidated.")

    @staticmethod
    def normalize_root(symbol: str) -> str:
        """Normalizes symbol to its canonical root name."""
        return BrokerSymbolResolver.normalize_root(symbol)

    def _log_blocked_usdjpy(self) -> None:
        """Rate-limited logging for blocked USDJPY encounters."""
        now = time.monotonic()
        last = self._last_blocked_log_time.get("USDJPY", 0.0)
        if now - last >= 10.0:
            self._last_blocked_log_time["USDJPY"] = now
            logger.warning("INSTRUMENT_BLOCKED: USDJPY | REASON: NOT_IN_ALLOWED_TRADING_UNIVERSE")

    def is_approved(self, symbol: str) -> bool:
        """
        Determines whether `symbol` belongs to the approved two-symbol universe (XAUUSD, BTCUSD).
        Checks exact string, alias sets, and normalized root.
        Universally rejects USDJPY and all broker variants.
        """
        if not symbol:
            return False
        sym_upper = symbol.strip().upper()
        root = self.normalize_root(sym_upper)
        if root == "USDJPY" or "USDJPY" in sym_upper:
            self._log_blocked_usdjpy()
            return False
        if root in APPROVED_CANONICAL_SYMBOLS:
            return True
        for canon, aliases in APPROVED_CANONICAL_ALIASES.items():
            if sym_upper in aliases or root in aliases:
                return True
        return False

    def validate_or_reject(self, symbol: str) -> Tuple[bool, Optional[str]]:
        """
        Validates symbol against approved universe.
        Returns (True, None) if approved, or (False, rejection_reason) if rejected.
        Universally rejects USDJPY with required structured error.
        """
        if not symbol:
            return False, "INSTRUMENT_NOT_ALLOWED: Empty symbol name provided."
        sym_upper = symbol.strip().upper()
        root = self.normalize_root(sym_upper)
        if root == "USDJPY" or "USDJPY" in sym_upper:
            self._log_blocked_usdjpy()
            return False, "INSTRUMENT_NOT_ALLOWED: USDJPY is excluded from the trading universe. Only XAUUSD and BTCUSD are permitted."
        if not self.is_approved(symbol):
            reason = (
                f"INSTRUMENT_NOT_ALLOWED: Instrument '{symbol}' is excluded from the trading universe. "
                f"Only {', '.join(APPROVED_CANONICAL_SYMBOLS)} are permitted."
            )
            return False, reason
        return True, None

    def is_symbol_available(self, symbol: str) -> bool:
        """Returns True if the symbol is in approved universe and marked available by broker discovery."""
        if not self.is_approved(symbol):
            return False
        canon = self.get_canonical_symbol(symbol)
        if canon and canon in self._resolved_instruments:
            return self._resolved_instruments[canon].is_available
        return True

    def resolve_universe(
        self,
        inventory: Optional[List[Any]] = None,
        mt5_module: Any = None,
        bridge_client: Any = None
    ) -> Dict[str, str]:
        """
        Resolves broker symbol names for the two canonical instruments against MT5 inventory.
        Stores structured mappings and instrument specifications.
        """
        if inventory is None and bridge_client is not None:
            if hasattr(bridge_client, "get_all_symbols"):
                try:
                    inventory = bridge_client.get_all_symbols()
                except Exception:
                    pass

        logger.info(f"ACTIVE_TRADING_UNIVERSE: {', '.join(APPROVED_CANONICAL_SYMBOLS)}")
        resolved: Dict[str, str] = {}

        for canon in APPROVED_CANONICAL_SYMBOLS:
            res: SymbolResolutionResult = self.resolver.resolve(
                canon, inventory=inventory, mt5_module=mt5_module, strict_canonical=True
            )
            broker_sym = res.broker_symbol or canon
            self._canonical_to_broker[canon] = broker_sym
            self._broker_to_canonical[broker_sym] = canon
            self._broker_to_canonical[canon] = canon

            is_avail = (res.status in ("RESOLVED", "VALIDATED")) or (inventory is None and res.broker_symbol is not None)
            if is_avail:
                status_str = "VALIDATED"
            elif res.status in ("SYMBOL_RESOLUTION_FAILED", "SYMBOL_NOT_FOUND"):
                status_str = "SYMBOL_NOT_AVAILABLE"
            else:
                status_str = res.status

            self._resolved_instruments[canon] = ResolvedInstrument(
                canonical=canon,
                broker_symbol=broker_sym,
                is_available=is_avail,
                digits=res.digits,
                point=res.point,
                contract_size=res.contract_size,
                tick_size=res.tick_size,
                tick_value=res.tick_value,
                volume_min=res.volume_min,
                volume_max=res.volume_max,
                volume_step=res.volume_step,
                broker_server=res.broker_server,
                account_type=res.account_type,
                suffix=res.suffix,
                trade_mode=res.trade_mode,
                filling_mode=res.filling_mode,
                stop_level=res.stop_level,
                freeze_level=res.freeze_level,
                validation_status=status_str,
                discovery_timestamp=res.discovery_timestamp,
            )
            resolved[canon] = broker_sym
            logger.info(
                f"[SYMBOL_MANAGER] Resolved {canon} -> {broker_sym} "
                f"(status={status_str}, suffix='{res.suffix}', point={res.point}, "
                f"tick_val={res.tick_value}, contract_size={res.contract_size})"
            )

        # Log account type and resolved symbols per specification
        account_type = "STANDARD"
        for inst in self._resolved_instruments.values():
            if inst.account_type:
                account_type = inst.account_type
                break
        logger.info(
            f"[SYMBOL_MANAGER] Account Type: {account_type} | "
            f"Resolved symbols: " + ", ".join(f"{c} -> {resolved.get(c, c)}" for c in APPROVED_CANONICAL_SYMBOLS)
        )

        self._initialized = True
        return resolved

    def get_broker_symbol(self, canonical_or_broker: str) -> Optional[str]:
        """Returns the broker's active symbol name for a given canonical symbol, or None if unauthorized."""
        if not self.is_approved(canonical_or_broker):
            return None
        sym_upper = canonical_or_broker.strip().upper()
        root = self.normalize_root(sym_upper)
        if root in self._canonical_to_broker:
            return self._canonical_to_broker[root]
        if sym_upper in self._broker_to_canonical:
            canon = self._broker_to_canonical[sym_upper]
            return self._canonical_to_broker.get(canon, sym_upper)
        return canonical_or_broker

    def get_canonical_symbol(self, symbol: str) -> Optional[str]:
        """Returns canonical symbol name (XAUUSD or BTCUSD), or None if unauthorized."""
        if not self.is_approved(symbol):
            return None
        sym_upper = symbol.strip().upper()
        if sym_upper in self._broker_to_canonical:
            return self._broker_to_canonical[sym_upper]
        root = self.normalize_root(sym_upper)
        if root in APPROVED_CANONICAL_SYMBOLS:
            return root
        return None

    def get_all_resolved_symbols(self) -> List[str]:
        """Returns the list of active broker symbols for the 2 instruments."""
        return [self._canonical_to_broker[c] for c in APPROVED_CANONICAL_SYMBOLS]

    def get_approved_symbols(self) -> List[str]:
        """Returns the canonical list of approved symbols."""
        return list(APPROVED_CANONICAL_SYMBOLS)

    def get_resolved_symbols(self) -> List[str]:
        """Alias for get_all_resolved_symbols()."""
        return self.get_all_resolved_symbols()

    def get_instrument_spec(self, symbol: str) -> Optional[ResolvedInstrument]:
        canon = self.get_canonical_symbol(symbol)
        return self._resolved_instruments.get(canon)

    def get_structured_mappings(self) -> Dict[str, Dict[str, Any]]:
        """Returns structured mappings for all 3 canonical symbols."""
        mappings: Dict[str, Dict[str, Any]] = {}
        for canon in APPROVED_CANONICAL_SYMBOLS:
            spec = self._resolved_instruments.get(canon)
            if spec:
                mappings[canon] = spec.to_dict()
            else:
                broker_sym = self._canonical_to_broker.get(canon, canon)
                mappings[canon] = {
                    "canonical_symbol": canon,
                    "actual_broker_symbol": broker_sym,
                    "broker_symbol": broker_sym,
                    "broker_server": "",
                    "account_type": "STANDARD",
                    "suffix": "",
                    "contract_size": 1.0,
                    "digits": 2,
                    "point_size": 0.01,
                    "tick_size": 0.01,
                    "tick_value": 1.0,
                    "minimum_volume": 0.01,
                    "maximum_volume": 50.0,
                    "volume_step": 0.01,
                    "trade_mode": 4,
                    "filling_mode": 1,
                    "stop_level": 0,
                    "freeze_level": 0,
                    "discovery_timestamp": datetime.now(timezone.utc).isoformat(),
                    "validation_status": "PENDING_DISCOVERY",
                }
        return mappings


# Global singleton instance
_SPECIALIZED_UNIVERSE = SpecializedSymbolUniverse()


def get_symbol_universe() -> SpecializedSymbolUniverse:
    global _SPECIALIZED_UNIVERSE
    return _SPECIALIZED_UNIVERSE


def is_symbol_permitted(symbol: str) -> bool:
    """Quick helper function to check whether a broker/raw symbol resolves to an allowed instrument."""
    global _SPECIALIZED_UNIVERSE
    return _SPECIALIZED_UNIVERSE.is_approved(symbol)
