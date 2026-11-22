"""
Universal Symbol Discovery & Mapping Engine.
Dynamically maps the canonical trading universe (XAUUSD, BTCUSD, USDJPY)
to actual broker-specific tradable instruments across standard, cent, micro, and pro accounts.
Provides graceful isolation for broker-absent symbols (e.g., missing BTCUSD on cent accounts).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from src.broker_adaptation.symbol_specification import BrokerSymbolSpec, extract_symbol_spec

logger = logging.getLogger("SymbolDiscovery")

CANONICAL_UNIVERSE = ("XAUUSD", "BTCUSD")

CANONICAL_ALIASES: Dict[str, Tuple[str, ...]] = {
    "XAUUSD": ("XAUUSD", "GOLD", "XAU"),
    "BTCUSD": ("BTCUSD", "BITCOIN", "BTC"),
}

KNOWN_SUFFIXES = (
    ".micro", ".cent", "-cent", ".std", ".raw", ".ecn", "_ecn", ".pro",
    ".m", ".a", ".r", ".c", ".i", "_i", "+", "#", "micro", "c", "m"
)


@dataclass
class DiscoveryResult:
    canonical_symbol: str
    broker_symbol: Optional[str]
    is_available: bool
    status: str  # VALIDATED, SYMBOL_NOT_AVAILABLE, AMBIGUOUS_BROKER_SYMBOL, UNAUTHORIZED_SYMBOL
    spec: Optional[BrokerSymbolSpec] = None
    candidates_found: List[str] = field(default_factory=list)
    reason: str = ""
    discovery_timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "canonical_symbol": self.canonical_symbol,
            "broker_symbol": self.broker_symbol,
            "is_available": self.is_available,
            "status": self.status,
            "candidates_found": self.candidates_found,
            "reason": self.reason,
            "spec": self.spec.to_dict() if self.spec else None,
            "discovery_timestamp": self.discovery_timestamp,
        }


class SymbolDiscoveryEngine:
    """
    Scans MT5 symbol inventory, maps canonical universe to broker instruments,
    extracts contract specifications, and handles symbol absence gracefully.
    """

    def __init__(self):
        self._canonical_to_broker: Dict[str, str] = {}
        self._broker_to_canonical: Dict[str, str] = {}
        self._discovery_results: Dict[str, DiscoveryResult] = {}
        self._cached_specs: Dict[str, BrokerSymbolSpec] = {}

    def clear(self) -> None:
        self._canonical_to_broker.clear()
        self._broker_to_canonical.clear()
        self._discovery_results.clear()
        self._cached_specs.clear()

    @staticmethod
    def normalize_root(symbol: str) -> str:
        s = str(symbol or "").strip().upper()
        if ":" in s:
            s = s.split(":", 1)[1]
        for sfx in KNOWN_SUFFIXES:
            sfx_u = sfx.upper()
            if s.endswith(sfx_u) and len(s) > len(sfx_u):
                if sfx_u in ("M", "C") and not sfx.startswith(".") and len(s) < 7:
                    continue
                s = s[: -len(sfx_u)]
                break
        return s

    def is_canonical_or_alias(self, symbol: str) -> bool:
        if not symbol:
            return False
        sym_u = symbol.strip().upper()
        norm = self.normalize_root(sym_u)
        if norm == "USDJPY" or "USDJPY" in sym_u:
            return False
        if norm in CANONICAL_UNIVERSE:
            return True
        for canon, aliases in CANONICAL_ALIASES.items():
            if norm in aliases or sym_u in aliases:
                return True
        return False

    def discover_symbols(
        self,
        inventory: List[Any],
        is_cent_account: bool = False,
        mt5_module: Any = None,
    ) -> Dict[str, DiscoveryResult]:
        """
        Discovers broker symbols for all canonical instruments in CANONICAL_UNIVERSE.
        Handles missing symbols (such as absent BTCUSD on cent accounts) without blocking others.
        """
        self.clear()
        results: Dict[str, DiscoveryResult] = {}

        if not inventory:
            for canon in CANONICAL_UNIVERSE:
                res = DiscoveryResult(
                    canonical_symbol=canon,
                    broker_symbol=None,
                    is_available=False,
                    status="SYMBOL_NOT_AVAILABLE",
                    reason="Terminal symbol inventory is empty or unavailable"
                )
                results[canon] = res
                self._discovery_results[canon] = res
            return results

        # Index available inventory
        name_map: Dict[str, Any] = {}
        for item in inventory:
            name = item.name if hasattr(item, "name") else str(item.get("name", item) if isinstance(item, dict) else item)
            name_map[name] = item

        for canon in CANONICAL_UNIVERSE:
            aliases = CANONICAL_ALIASES.get(canon, (canon,))
            exact_matches: List[str] = []
            root_matches: List[str] = []
            alias_matches: List[str] = []

            for name, item in name_map.items():
                t_mode = getattr(item, "trade_mode", item.get("trade_mode", 4) if isinstance(item, dict) else 4)
                if t_mode == 0:
                    continue  # Trade disabled

                name_u = name.upper()
                norm = self.normalize_root(name_u)

                if name_u == canon.upper():
                    exact_matches.append(name)
                elif norm == canon:
                    root_matches.append(name)
                elif norm in aliases or any(a in name_u for a in aliases):
                    alias_matches.append(name)

            # Prioritize cent variants on cent accounts (.c, -cent)
            if is_cent_account and root_matches:
                cent_cands = [m for m in root_matches if m.upper().endswith(".C") or m.upper().endswith("-CENT") or m.upper().endswith("C")]
                if cent_cands:
                    root_matches = cent_cands

            candidate_pool = exact_matches or root_matches or alias_matches

            if not candidate_pool:
                # Symbol is NOT available at this broker (e.g., BTCUSD on cent accounts)
                logger.info(
                    f"[SymbolDiscovery] Canonical '{canon}' is not offered by broker. "
                    f"Marking as SYMBOL_NOT_AVAILABLE (other instruments remain active)."
                )
                res = DiscoveryResult(
                    canonical_symbol=canon,
                    broker_symbol=None,
                    is_available=False,
                    status="SYMBOL_NOT_AVAILABLE",
                    reason=f"Broker does not offer '{canon}' or any matching tradable alias."
                )
                results[canon] = res
                self._discovery_results[canon] = res
                continue

            # If ambiguous matches exist
            if len(candidate_pool) > 1 and not exact_matches:
                unique_cands = list(set(candidate_pool))
                if is_cent_account:
                    c_only = [m for m in unique_cands if m.upper().endswith(".C")]
                    if len(c_only) == 1:
                        unique_cands = c_only
                if len(unique_cands) > 1:
                    res = DiscoveryResult(
                        canonical_symbol=canon,
                        broker_symbol=None,
                        is_available=False,
                        status="AMBIGUOUS_BROKER_SYMBOL",
                        candidates_found=unique_cands,
                        reason=f"Multiple ambiguous broker instruments matched '{canon}': {unique_cands}"
                    )
                    results[canon] = res
                    self._discovery_results[canon] = res
                    continue
                chosen_name = unique_cands[0]
            else:
                chosen_name = candidate_pool[0]

            chosen_item = name_map[chosen_name]

            # If MT5 module available, ensure symbol is selected in Market Watch
            if mt5_module is not None and hasattr(mt5_module, "symbol_select"):
                try:
                    mt5_module.symbol_select(chosen_name, True)
                except Exception:
                    pass

            spec = extract_symbol_spec(chosen_item, canonical_name=canon)
            self._cached_specs[chosen_name] = spec

            res = DiscoveryResult(
                canonical_symbol=canon,
                broker_symbol=chosen_name,
                is_available=spec.is_tradable,
                status="VALIDATED" if spec.is_tradable else "BROKER_TRADE_DISABLED",
                spec=spec,
                candidates_found=[chosen_name],
                reason="Successfully discovered and validated" if spec.is_tradable else "Trade mode is disabled for instrument"
            )
            results[canon] = res
            self._discovery_results[canon] = res

            self._canonical_to_broker[canon] = chosen_name
            self._broker_to_canonical[chosen_name] = canon
            self._broker_to_canonical[canon] = canon

            logger.info(
                f"[SymbolDiscovery] Mapped {canon} -> {chosen_name} | "
                f"ContractSize: {spec.contract_size} | TickVal: {spec.tick_value} | "
                f"MinLot: {spec.volume_min} | Step: {spec.volume_step} | Status: {res.status}"
            )

        return results

    def get_broker_symbol(self, canonical_or_broker: str) -> Optional[str]:
        """Resolves broker symbol, returning None if symbol is unavailable."""
        s = canonical_or_broker.strip()
        norm = self.normalize_root(s)
        if norm in self._canonical_to_broker:
            return self._canonical_to_broker[norm]
        if s in self._broker_to_canonical:
            canon = self._broker_to_canonical[s]
            return self._canonical_to_broker.get(canon, s)
        return self._canonical_to_broker.get(s)

    def get_canonical_symbol(self, symbol: str) -> Optional[str]:
        """Maps broker symbol to canonical symbol name (XAUUSD, BTCUSD, USDJPY)."""
        s = symbol.strip()
        if s in self._broker_to_canonical:
            return self._broker_to_canonical[s]
        norm = self.normalize_root(s)
        if norm in CANONICAL_UNIVERSE:
            return norm
        for canon, aliases in CANONICAL_ALIASES.items():
            if norm in aliases or s.upper() in aliases:
                return canon
        return None

    def get_spec(self, canonical_or_broker: str) -> Optional[BrokerSymbolSpec]:
        broker_sym = self.get_broker_symbol(canonical_or_broker)
        if broker_sym and broker_sym in self._cached_specs:
            return self._cached_specs[broker_sym]
        return None
