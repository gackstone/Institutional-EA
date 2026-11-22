"""
Broker Auto-Detection & Universal Symbol Resolution Service.
Automatically detects the logged-in MT5 broker, server, account type (STANDARD / CENT / DEMO / REAL),
and resolves canonical strategy symbols (e.g. EURUSD, XAUUSD, NAS100, US30, BTCUSD) against
the terminal's actual symbol inventory and contract metadata without hardcoding a single broker.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("BrokerSymbolResolver")

KNOWN_SUFFIXES = (
    ".micro", ".std", ".raw", ".ecn", "_ecn", ".pro", ".m", ".a", ".r", ".c", ".i", "_i", "+", "#", "m"
)

CANONICAL_ALIAS_GROUPS: Tuple[Tuple[str, ...], ...] = (
    ("NAS100", "US100", "USTEC", "NDX", "NQ100"),
    ("US30", "DJ30", "WS30", "DJI", "YM"),
    ("SPX500", "US500", "SP500", "ES"),
    ("GER40", "DAX40", "DE40", "DAX"),
    ("UK100", "FTSE100"),
    ("XAUUSD", "GOLD"),
    ("XAGUSD", "SILVER"),
    ("BTCUSD", "BITCOIN"),
)

CENT_CURRENCIES = {"USC", "EUC", "GBX", "JPC", "USCENT", "EURCENT"}


@dataclass
class BrokerContext:
    broker_company: str = ""
    broker_server: str = ""
    account_login: int = 0
    currency: str = "USD"
    is_cent_account: bool = False
    trade_mode: str = "DEMO"
    balance: float = 0.0
    equity: float = 0.0
    leverage: int = 100
    margin: float = 0.0
    free_margin: float = 0.0
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def session_key(self) -> str:
        return f"{self.broker_server}:{self.account_login}"


@dataclass
class SymbolResolutionResult:
    canonical_symbol: str
    broker_symbol: Optional[str]
    status: str  # RESOLVED, SYMBOL_RESOLUTION_FAILED, AMBIGUOUS_BROKER_SYMBOL
    candidates: List[str] = field(default_factory=list)
    reason: str = ""
    contract_size: float = 0.0
    digits: int = 5
    point: float = 0.00001
    tick_size: float = 0.00001
    tick_value: float = 1.0
    volume_min: float = 0.01
    volume_max: float = 100.0
    volume_step: float = 0.01


class BrokerSymbolResolver:
    """
    Resolves canonical symbols against live MT5 terminal inventory (or injected inventory for tests),
    caches mappings per broker/account session, and invalidates on account/broker change.
    """

    def __init__(self):
        self._broker_ctx: Optional[BrokerContext] = None
        self._cache: Dict[str, SymbolResolutionResult] = {}
        self._last_session_key: str = ""

    @staticmethod
    def normalize_root(symbol: str) -> str:
        s = str(symbol or "").strip().upper()
        # Strip common broker prefixes if present (e.g. "FX:EURUSD", "iEURUSD")
        if ":" in s:
            s = s.split(":", 1)[1]
        for sfx in KNOWN_SUFFIXES:
            sfx_u = sfx.upper()
            if s.endswith(sfx_u) and len(s) > len(sfx_u):
                # Only strip single-letter 'm' when attached to a 6+ char FX/metal/crypto root
                if sfx_u == "M" and len(s) < 7:
                    continue
                s = s[: -len(sfx_u)]
                break
        return s

    @staticmethod
    def alias_family(canonical_symbol: str) -> List[str]:
        root = BrokerSymbolResolver.normalize_root(canonical_symbol)
        for grp in CANONICAL_ALIAS_GROUPS:
            if root in grp:
                return list(grp)
        return [root]

    def detect_broker_context(self, mt5_module: Any = None) -> Optional[BrokerContext]:
        if mt5_module is None:
            try:
                import MetaTrader5 as mt5_module
            except ImportError:
                return self._broker_ctx

        try:
            acc = mt5_module.account_info()
            term = mt5_module.terminal_info() if hasattr(mt5_module, "terminal_info") else None
            if acc is None:
                return self._broker_ctx

            currency = str(getattr(acc, "currency", "USD") or "USD").upper()
            is_cent = currency in CENT_CURRENCIES
            trade_mode_int = int(getattr(acc, "trade_mode", 0))
            trade_mode_str = "REAL" if trade_mode_int == 2 else ("CONTEST" if trade_mode_int == 1 else "DEMO")

            ctx = BrokerContext(
                broker_company=str(getattr(acc, "company", "") or getattr(term, "company", "") or ""),
                broker_server=str(getattr(acc, "server", "") or ""),
                account_login=int(getattr(acc, "login", 0) or 0),
                currency=currency,
                is_cent_account=is_cent,
                trade_mode=trade_mode_str,
                balance=float(getattr(acc, "balance", 0.0)),
                equity=float(getattr(acc, "equity", 0.0)),
                leverage=int(getattr(acc, "leverage", 100) or 100),
                margin=float(getattr(acc, "margin", 0.0)),
                free_margin=float(getattr(acc, "margin_free", 0.0)),
            )
            if ctx.session_key != self._last_session_key:
                self._cache.clear()
                self._last_session_key = ctx.session_key
            self._broker_ctx = ctx
            return ctx
        except Exception as e:
            logger.debug(f"[BrokerResolver] Context detection error: {e}")
            return self._broker_ctx

    def resolve(
        self,
        canonical_symbol: str,
        inventory: Optional[List[Any]] = None,
        mt5_module: Any = None,
    ) -> SymbolResolutionResult:
        canon = str(canonical_symbol or "").strip()
        if not canon:
            return SymbolResolutionResult(
                canonical_symbol="",
                broker_symbol=None,
                status="SYMBOL_RESOLUTION_FAILED",
                reason="Empty canonical symbol",
            )

        if mt5_module is not None:
            self.detect_broker_context(mt5_module)

        if canon in self._cache:
            return self._cache[canon]

        # Acquire symbol inventory from MT5 if not explicitly passed
        symbols_list = inventory
        if symbols_list is None:
            if mt5_module is None:
                try:
                    import MetaTrader5 as mt5_module
                except ImportError:
                    mt5_module = None
            if mt5_module is not None:
                try:
                    self.detect_broker_context(mt5_module)
                    symbols_list = list(mt5_module.symbols_get() or [])
                except Exception:
                    symbols_list = []

        if not symbols_list:
            return SymbolResolutionResult(
                canonical_symbol=canon,
                broker_symbol=None,
                status="SYMBOL_RESOLUTION_FAILED",
                reason=f"No terminal symbol inventory available to resolve {canon}",
            )

        family = self.alias_family(canon)
        req_upper = canon.upper()

        exact_matches: List[Any] = []
        root_matches: List[Any] = []
        alias_matches: List[Any] = []

        for item in symbols_list:
            name = item.name if hasattr(item, "name") else str(item.get("name", item) if isinstance(item, dict) else item)
            trade_mode = getattr(item, "trade_mode", item.get("trade_mode", 4) if isinstance(item, dict) else 4)
            # Skip explicitly disabled instruments (SYMBOL_TRADE_MODE_DISABLED == 0)
            if trade_mode == 0:
                continue

            name_u = name.upper()
            norm = self.normalize_root(name_u)
            if name_u == req_upper:
                exact_matches.append((name, item))
            elif norm == self.normalize_root(canon):
                root_matches.append((name, item))
            elif norm in family:
                alias_matches.append((name, item))

        selected_pool = exact_matches or root_matches or alias_matches
        if not selected_pool:
            return SymbolResolutionResult(
                canonical_symbol=canon,
                broker_symbol=None,
                status="SYMBOL_RESOLUTION_FAILED",
                reason=f"No tradable broker instrument matched canonical symbol '{canon}'",
            )

        if len(selected_pool) > 1 and not exact_matches:
            # Prefer a single suffix match if one is clearly the account's standard/micro suffix,
            # otherwise report ambiguity unless one candidate is unambiguous.
            names = [n for n, _ in selected_pool]
            if len(set(names)) > 1:
                # If all share the exact same normalized root (e.g. only US100.std vs US100.pro),
                # report ambiguity instead of guessing arbitrarily.
                res = SymbolResolutionResult(
                    canonical_symbol=canon,
                    broker_symbol=None,
                    status="AMBIGUOUS_BROKER_SYMBOL",
                    candidates=names,
                    reason=f"Multiple tradable broker symbols matched '{canon}': {names}",
                )
                return res

        chosen_name, chosen_item = selected_pool[0]
        if mt5_module is not None and hasattr(mt5_module, "symbol_select"):
            try:
                mt5_module.symbol_select(chosen_name, True)
            except Exception:
                pass

        def _get(obj: Any, attr: str, default: float) -> float:
            if hasattr(obj, attr):
                return float(getattr(obj, attr) or default)
            if isinstance(obj, dict):
                return float(obj.get(attr, default) or default)
            return default

        res = SymbolResolutionResult(
            canonical_symbol=canon,
            broker_symbol=chosen_name,
            status="RESOLVED",
            candidates=[n for n, _ in selected_pool],
            contract_size=_get(chosen_item, "trade_contract_size", 100000.0),
            digits=int(_get(chosen_item, "digits", 5)),
            point=_get(chosen_item, "point", 0.00001),
            tick_size=_get(chosen_item, "trade_tick_size", 0.00001),
            tick_value=_get(chosen_item, "trade_tick_value", 1.0),
            volume_min=_get(chosen_item, "volume_min", 0.01),
            volume_max=_get(chosen_item, "volume_max", 100.0),
            volume_step=_get(chosen_item, "volume_step", 0.01),
        )
        self._cache[canon] = res
        return res
