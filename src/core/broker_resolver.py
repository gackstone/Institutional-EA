"""
Broker Auto-Detection & Universal Symbol Resolution Service.
Automatically detects the logged-in MT5 broker, server, account type (STANDARD / CENT / DEMO / REAL),
and resolves canonical strategy symbols (XAUUSD, BTCUSD, USDJPY) against
the terminal's actual symbol inventory and contract metadata without hardcoding a single broker.

Features:
1. Support for standard, cent (.c, -cent, c), micro, raw, and pro broker suffix variants.
2. Complete symbol contract specification extraction (contract size, tick size/value, min/max/step volume, stops, filling).
3. Structured mapping representation with validation status.
4. Session-aware cache invalidation on account, broker, or terminal reconnection.
5. Strict canonical universe enforcement where required.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.core.account_detector import AccountDetector, AccountDetectionResult, AccountType

logger = logging.getLogger("BrokerSymbolResolver")

KNOWN_SUFFIXES = (
    ".micro", ".cent", "-cent", ".std", ".raw", ".ecn", "_ecn", ".pro", ".m", ".a", ".r", ".c", ".i", "_i", "+", "#", "micro", "c", "m"
)

CANONICAL_ALIAS_GROUPS: Tuple[Tuple[str, ...], ...] = (
    ("XAUUSD", "GOLD", "XAU"),
    ("BTCUSD", "BITCOIN", "BTC"),
    ("NAS100", "US100", "USTEC", "NDX", "NQ100"),
    ("US30", "DJ30", "WS30", "DJI", "YM"),
    ("SPX500", "US500", "SP500", "ES"),
    ("GER40", "DAX40", "DE40", "DAX"),
    ("UK100", "FTSE100"),
    ("XAGUSD", "SILVER"),
)

CENT_CURRENCIES = {"USC", "EUC", "GBX", "JPC", "USCENT", "EURCENT", "GLD", "CENT"}
APPROVED_CANONICAL_SYMBOLS = ("XAUUSD", "BTCUSD")


@dataclass
class BrokerContext:
    broker_company: str = ""
    broker_server: str = ""
    account_login: int = 0
    currency: str = "USD"
    is_cent_account: bool = False
    account_type: str = "STANDARD"
    trade_mode: str = "DEMO"
    balance: float = 0.0
    equity: float = 0.0
    leverage: int = 100
    margin: float = 0.0
    free_margin: float = 0.0
    denomination_factor: float = 1.0
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def session_key(self) -> str:
        return f"{self.broker_server}:{self.account_login}"


@dataclass
class SymbolResolutionResult:
    canonical_symbol: str
    broker_symbol: Optional[str]
    status: str  # VALIDATED, RESOLVED, SYMBOL_RESOLUTION_FAILED, AMBIGUOUS_BROKER_SYMBOL, UNAUTHORIZED_SYMBOL
    candidates: List[str] = field(default_factory=list)
    reason: str = ""
    broker_server: str = ""
    account_type: str = "STANDARD"
    suffix: str = ""
    contract_size: float = 1.0
    digits: int = 5
    point: float = 0.00001
    tick_size: float = 0.00001
    tick_value: float = 1.0
    volume_min: float = 0.01
    volume_max: float = 100.0
    volume_step: float = 0.01
    trade_mode: int = 4
    filling_mode: int = 1
    stop_level: int = 0
    freeze_level: int = 0
    discovery_timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Compatibility properties
    @property
    def actual_broker_symbol(self) -> Optional[str]:
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

    @property
    def validation_status(self) -> str:
        return self.status

    def to_dict(self) -> Dict[str, Any]:
        return {
            "canonical_symbol": self.canonical_symbol,
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
            "validation_status": self.status,
            "candidates": self.candidates,
            "reason": self.reason,
        }


class BrokerSymbolResolver:
    """
    Resolves canonical symbols against live MT5 terminal inventory (or injected inventory for tests),
    caches mappings per broker/account session, and invalidates on account/broker change.
    """

    def __init__(self, account_detector: Optional[AccountDetector] = None):
        self._broker_ctx: Optional[BrokerContext] = None
        self._cache: Dict[str, SymbolResolutionResult] = {}
        self._last_session_key: str = ""
        self._account_detector = account_detector or AccountDetector()

    def invalidate_cache(self) -> None:
        """Explicitly clear cached resolutions on account or terminal reconnection."""
        self._cache.clear()
        self._broker_ctx = None
        self._last_session_key = ""
        logger.info("[BrokerSymbolResolver] Cache explicitly invalidated.")

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

    @staticmethod
    def extract_suffix(symbol: str, root: str) -> str:
        s = str(symbol or "").strip()
        r = str(root or "").strip()
        if s.upper().startswith(r.upper()):
            return s[len(r):]
        return ""

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

            detection: AccountDetectionResult = self._account_detector.detect(
                account_info=acc,
                terminal_info=term
            )

            ctx = BrokerContext(
                broker_company=detection.account_company,
                broker_server=detection.broker_server,
                account_login=detection.account_login,
                currency=detection.account_currency,
                is_cent_account=detection.account_type.is_cent,
                account_type=detection.account_type.value,
                trade_mode=detection.trade_mode,
                balance=detection.account_balance,
                equity=detection.account_equity,
                leverage=detection.leverage,
                margin=detection.margin,
                free_margin=detection.free_margin,
                denomination_factor=detection.denomination_factor,
            )

            if ctx.session_key != self._last_session_key:
                logger.info(
                    f"[BrokerSymbolResolver] Detected account/server change: "
                    f"'{self._last_session_key}' -> '{ctx.session_key}'. Invalidating cache."
                )
                self._cache.clear()
                self._last_session_key = ctx.session_key

            self._broker_ctx = ctx
            return ctx
        except Exception as e:
            logger.debug(f"[BrokerSymbolResolver] Context detection error: {e}")
            return self._broker_ctx

    def resolve(
        self,
        canonical_symbol: str,
        inventory: Optional[List[Any]] = None,
        mt5_module: Any = None,
        strict_canonical: bool = False,
    ) -> SymbolResolutionResult:
        canon = str(canonical_symbol or "").strip()
        if not canon:
            return SymbolResolutionResult(
                canonical_symbol="",
                broker_symbol=None,
                status="SYMBOL_RESOLUTION_FAILED",
                reason="Empty canonical symbol",
            )

        norm_root = self.normalize_root(canon)
        if norm_root == "USDJPY" or "USDJPY" in canon.upper():
            return SymbolResolutionResult(
                canonical_symbol=canon,
                broker_symbol=None,
                status="UNAUTHORIZED_SYMBOL",
                reason="INSTRUMENT_NOT_ALLOWED: USDJPY is excluded from the trading universe. Only XAUUSD and BTCUSD are permitted.",
            )

        if strict_canonical and norm_root not in APPROVED_CANONICAL_SYMBOLS:
            return SymbolResolutionResult(
                canonical_symbol=canon,
                broker_symbol=None,
                status="UNAUTHORIZED_SYMBOL",
                reason=f"INSTRUMENT_NOT_ALLOWED: Instrument '{canon}' is excluded from the trading universe. Only {', '.join(APPROVED_CANONICAL_SYMBOLS)} are permitted.",
            )

        if mt5_module is not None:
            self.detect_broker_context(mt5_module)

        if canon in self._cache:
            return self._cache[canon]

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

        is_cent = self._broker_ctx.is_cent_account if self._broker_ctx else False

        for item in symbols_list:
            name = item.name if hasattr(item, "name") else str(item.get("name", item) if isinstance(item, dict) else item)
            trade_mode = getattr(item, "trade_mode", item.get("trade_mode", 4) if isinstance(item, dict) else 4)
            # Skip disabled instruments
            if trade_mode == 0:
                continue

            name_u = name.upper()
            norm = self.normalize_root(name_u)
            if name_u == req_upper:
                exact_matches.append((name, item))
            elif norm == norm_root:
                root_matches.append((name, item))
            elif norm in family:
                alias_matches.append((name, item))

        # Prioritize cent suffix (.c) if on a cent account, or standard suffix if on standard
        if is_cent and root_matches:
            cent_candidates = [m for m in root_matches if m[0].upper().endswith(".C") or m[0].upper().endswith("C")]
            if cent_candidates:
                root_matches = cent_candidates

        selected_pool = exact_matches or root_matches or alias_matches
        if not selected_pool:
            return SymbolResolutionResult(
                canonical_symbol=canon,
                broker_symbol=None,
                status="SYMBOL_RESOLUTION_FAILED",
                reason=f"No tradable broker instrument matched canonical symbol '{canon}'",
            )

        if len(selected_pool) > 1 and not exact_matches:
            names = [n for n, _ in selected_pool]
            unique_names = list(set(names))
            if len(unique_names) > 1:
                if is_cent:
                    c_matches = [m for m in selected_pool if m[0].upper().endswith(".C") or m[0].upper().endswith("C")]
                    if len(c_matches) == 1:
                        selected_pool = c_matches
                if len(selected_pool) > 1:
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

        live_sym_info = None
        if mt5_module is not None and hasattr(mt5_module, "symbol_info"):
            try:
                live_sym_info = mt5_module.symbol_info(chosen_name)
            except Exception:
                live_sym_info = None

        def _get(obj: Any, attr: str, default: Any) -> Any:
            if live_sym_info is not None and hasattr(live_sym_info, attr):
                val = getattr(live_sym_info, attr)
                if val is not None:
                    return val
            if hasattr(obj, attr):
                val = getattr(obj, attr)
                if val is not None:
                    return val
            if isinstance(obj, dict):
                return obj.get(attr, default)
            return default

        contract_size = float(_get(chosen_item, "trade_contract_size", 100000.0) or 100000.0)
        digits = int(_get(chosen_item, "digits", 5) or 5)
        point = float(_get(chosen_item, "point", 0.00001) or 0.00001)
        tick_size = float(_get(chosen_item, "trade_tick_size", point) or point)
        tick_value = float(_get(chosen_item, "trade_tick_value", 1.0) or 1.0)
        volume_min = float(_get(chosen_item, "volume_min", 0.01) or 0.01)
        volume_max = float(_get(chosen_item, "volume_max", 100.0) or 100.0)
        volume_step = float(_get(chosen_item, "volume_step", 0.01) or 0.01)
        trade_mode = int(_get(chosen_item, "trade_mode", 4) or 4)
        filling_mode = int(_get(chosen_item, "filling_mode", 1) or 1)
        stop_level = int(_get(chosen_item, "trade_stops_level", 0) or 0)
        freeze_level = int(_get(chosen_item, "trade_freeze_level", 0) or 0)

        suffix = self.extract_suffix(chosen_name, norm_root)
        server_str = self._broker_ctx.broker_server if self._broker_ctx else ""
        account_type_str = self._broker_ctx.account_type if self._broker_ctx else "STANDARD"

        res = SymbolResolutionResult(
            canonical_symbol=canon,
            broker_symbol=chosen_name,
            status="VALIDATED",
            candidates=[n for n, _ in selected_pool],
            broker_server=server_str,
            account_type=account_type_str,
            suffix=suffix,
            contract_size=contract_size,
            digits=digits,
            point=point,
            tick_size=tick_size,
            tick_value=tick_value,
            volume_min=volume_min,
            volume_max=volume_max,
            volume_step=volume_step,
            trade_mode=trade_mode,
            filling_mode=filling_mode,
            stop_level=stop_level,
            freeze_level=freeze_level,
        )
        self._cache[canon] = res
        return res
