"""
Strict Three-Symbol Trading Universe and Broker-Aware Resolution Engine.
Exclusively recognizes and permits:
1. XAUUSD — Gold
2. BTCUSD — Bitcoin
3. USDJPY — US Dollar / Japanese Yen

Rejects all symbols outside this approved universe throughout the entire trading pipeline.
Integrates with BrokerSymbolResolver to dynamically detect broker symbol suffix/prefix variations
(e.g., XAUUSD.m, BTCUSD.m, USDJPY.m, XAUUSD.pro, etc.).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Any

from src.core.broker_resolver import BrokerSymbolResolver

logger = logging.getLogger("SymbolUniverse")

# Strict, non-negotiable canonical approved trading universe
APPROVED_CANONICAL_SYMBOLS: Tuple[str, ...] = ("XAUUSD", "BTCUSD", "USDJPY")

# Common broker aliases for the 3 canonical symbols
APPROVED_CANONICAL_ALIASES: Dict[str, Set[str]] = {
    "XAUUSD": {"XAUUSD", "GOLD", "XAU", "XAUUSD.M", "XAUUSDM", "XAUUSD.MICRO", "GOLD.M", "GOLDM", "XAUUSD.PRO", "XAUUSD.RAW", "XAUUSD.ECN"},
    "BTCUSD": {"BTCUSD", "BITCOIN", "BTC", "BTCUSD.M", "BTCUSDM", "BTCUSD.MICRO", "BTCUSD.PRO", "BTCUSD.RAW", "BTCUSD.ECN"},
    "USDJPY": {"USDJPY", "USDJPY.M", "USDJPYM", "USDJPY.MICRO", "USDJPY.PRO", "USDJPY.RAW", "USDJPY.ECN"},
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


class SpecializedSymbolUniverse:
    """
    Authoritative manager for the strict three-symbol trading universe (XAUUSD, BTCUSD, USDJPY).
    Provides broker symbol resolution, bidirectional mapping, and validation guards.
    """

    def __init__(self, broker_resolver: Optional[BrokerSymbolResolver] = None):
        self.resolver = broker_resolver or BrokerSymbolResolver()
        self._canonical_to_broker: Dict[str, str] = {
            "XAUUSD": "XAUUSD",
            "BTCUSD": "BTCUSD",
            "USDJPY": "USDJPY",
        }
        self._broker_to_canonical: Dict[str, str] = {
            "XAUUSD": "XAUUSD",
            "BTCUSD": "BTCUSD",
            "USDJPY": "USDJPY",
        }
        self._resolved_instruments: Dict[str, ResolvedInstrument] = {}
        self._initialized: bool = False

    @staticmethod
    def normalize_root(symbol: str) -> str:
        """Normalizes symbol to its canonical root name."""
        return BrokerSymbolResolver.normalize_root(symbol)

    def is_approved(self, symbol: str) -> bool:
        """
        Determines whether `symbol` belongs to the approved three-symbol universe.
        Checks both exact string, alias sets, and normalized root.
        """
        if not symbol:
            return False
        sym_upper = symbol.strip().upper()
        root = self.normalize_root(sym_upper)
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
        """
        if not self.is_approved(symbol):
            reason = (
                f"UNAUTHORIZED_SYMBOL: Instrument '{symbol}' is outside the approved three-symbol universe "
                f"({', '.join(APPROVED_CANONICAL_SYMBOLS)}). Execution blocked."
            )
            return False, reason
        return True, None

    def resolve_universe(
        self,
        inventory: Optional[List[Any]] = None,
        mt5_module: Any = None,
        bridge_client: Any = None
    ) -> Dict[str, str]:
        """
        Resolves broker symbol names for the three canonical instruments against MT5 inventory.
        Stores mappings and instrument specifications.
        """
        if inventory is None and bridge_client is not None:
            if hasattr(bridge_client, "get_all_symbols"):
                try:
                    inventory = bridge_client.get_all_symbols()
                except Exception:
                    pass

        logger.info(f"[SYMBOL_MANAGER] Approved trading universe: {', '.join(APPROVED_CANONICAL_SYMBOLS)}")
        resolved: Dict[str, str] = {}

        for canon in APPROVED_CANONICAL_SYMBOLS:
            res = self.resolver.resolve(canon, inventory=inventory, mt5_module=mt5_module)
            broker_sym = res.broker_symbol or canon
            self._canonical_to_broker[canon] = broker_sym
            self._broker_to_canonical[broker_sym] = canon
            self._broker_to_canonical[canon] = canon

            self._resolved_instruments[canon] = ResolvedInstrument(
                canonical=canon,
                broker_symbol=broker_sym,
                is_available=res.status == "RESOLVED" or inventory is None,
                digits=res.digits,
                point=res.point,
                contract_size=res.contract_size,
                tick_size=res.tick_size,
                tick_value=res.tick_value,
                volume_min=res.volume_min,
                volume_max=res.volume_max,
                volume_step=res.volume_step,
            )
            resolved[canon] = broker_sym
            logger.info(
                f"[SYMBOL_MANAGER] Resolved {canon} -> {broker_sym} "
                f"(status={res.status}, point={res.point}, contract_size={res.contract_size})"
            )

        self._initialized = True
        return resolved

    def get_broker_symbol(self, canonical_or_broker: str) -> str:
        """Returns the broker's active symbol name for a given canonical symbol."""
        sym_upper = canonical_or_broker.strip().upper()
        root = self.normalize_root(sym_upper)
        if root in self._canonical_to_broker:
            return self._canonical_to_broker[root]
        if sym_upper in self._broker_to_canonical:
            canon = self._broker_to_canonical[sym_upper]
            return self._canonical_to_broker.get(canon, sym_upper)
        return canonical_or_broker

    def get_canonical_symbol(self, symbol: str) -> Optional[str]:
        """Returns canonical symbol name (XAUUSD, BTCUSD, or USDJPY), or None if unauthorized."""
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
        """Returns the list of active broker symbols for the 3 instruments."""
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


# Global singleton instance
_SPECIALIZED_UNIVERSE = SpecializedSymbolUniverse()


def get_symbol_universe() -> SpecializedSymbolUniverse:
    global _SPECIALIZED_UNIVERSE
    return _SPECIALIZED_UNIVERSE
