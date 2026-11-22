"""
Automatic Symbol Resolver for MetaTrader 5.
Supports multi-instrument discovery (GOLD / XAUUSD and BITCOIN / BTCUSD),
detects broker suffixes (BTCUSDm, BTCUSD.a, BTCUSD#, BTCUSDpro, etc.),
and validates tradability, live quotes, and contract specifications.
"""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger("SymbolResolver")

_COMMON_GOLD_VARIANTS = (
    "XAUUSD",
    "XAUUSDm",
    "XAUUSD.m",
    "XAUUSD.a",
    "XAUUSD.pro",
    "XAUUSD.raw",
    "XAUUSD.std",
    "GOLD",
    "GOLD.m",
    "GOLDm",
    "XAU/USD",
)

_COMMON_BTC_VARIANTS = (
    "BTCUSD",
    "BTCUSDm",
    "BTCUSD.m",
    "BTCUSD.a",
    "BTCUSD#",
    "BTCUSD.",
    "BTCUSDpro",
    "BTCUSD.raw",
    "BTCUSD.std",
    "BTC/USD",
    "BITCOIN",
)


@dataclass
class ResolvedSymbolSpec:
    symbol: str
    canonical: str = "XAUUSD"
    digits: int = 2
    point: float = 0.01
    tick_size: float = 0.01
    tick_value: float = 1.0
    contract_size: float = 100.0
    min_lot: float = 0.01
    max_lot: float = 100.0
    lot_step: float = 0.01
    stops_level: int = 0
    freeze_level: int = 0
    filling_mode: int = 0  # 1=FOK, 2=IOC, 3=FOK+IOC, 0=RETURN
    trade_mode: int = 4    # 4 = SYMBOL_TRADE_MODE_FULL
    bid: float = 0.0
    ask: float = 0.0
    spread_points: float = 0.0
    is_tradable: bool = False
    raw_info: Dict[str, Any] = field(default_factory=dict)

    def normalize_volume(self, volume: float) -> float:
        """Clamps volume between min_lot and max_lot, snapping down to broker lot_step."""
        if self.lot_step <= 0:
            step = 0.01
        else:
            step = self.lot_step
        steps = int(round((volume - self.min_lot) / step))
        normalized = self.min_lot + max(0, steps) * step
        normalized = max(self.min_lot, min(self.max_lot, normalized))
        return round(normalized, 4)


class MultiSymbolResolver:
    """
    Universal broker symbol discovery engine.
    Resolves broker-specific symbol names against canonical instruments (XAUUSD, BTCUSD).
    """

    def __init__(
        self,
        canonical: str = "XAUUSD",
        aliases: Optional[Sequence[str]] = None,
        fallback: Optional[str] = None,
    ):
        self.canonical = canonical.upper()
        if aliases:
            self.aliases = list(aliases)
        else:
            if "BTC" in self.canonical:
                self.aliases = list(_COMMON_BTC_VARIANTS)
            else:
                self.aliases = list(_COMMON_GOLD_VARIANTS)
        self.fallback = fallback or self.canonical
        self.selected_spec: Optional[ResolvedSymbolSpec] = None

    def resolve_from_names(self, available_symbols: Sequence[str]) -> Optional[str]:
        """Resolves symbol name from a sequence of available broker symbol strings."""
        avail_upper = {s.upper(): s for s in available_symbols}

        # 1. Exact canonical match
        if self.canonical in avail_upper:
            return avail_upper[self.canonical]

        # 2. Configured aliases in priority order
        for alias in self.aliases:
            al_u = alias.upper()
            if al_u in avail_upper:
                return avail_upper[al_u]

        # 3. Fuzzy prefix match
        target_root = "BTC" if "BTC" in self.canonical else "XAU"
        for s_u, original in avail_upper.items():
            if s_u.startswith(target_root) and "USD" in s_u:
                return original

        # 4. Fallback if present
        if self.fallback.upper() in avail_upper:
            return avail_upper[self.fallback.upper()]

        return None

    def resolve_with_mt5(self) -> Optional[ResolvedSymbolSpec]:
        """Queries live MetaTrader 5 terminal to discover and validate the instrument."""
        try:
            import MetaTrader5 as mt5

            if not mt5.initialize():
                logger.warning(f"[RESOLVER] MT5 initialize() returned False for {self.canonical}")
                return None

            symbols = mt5.symbols_get()
            if not symbols:
                logger.warning(f"[RESOLVER] symbols_get() returned empty for {self.canonical}")
                return None

            symbol_names = [s.name for s in symbols]
            chosen_name = self.resolve_from_names(symbol_names)

            if not chosen_name:
                logger.warning(f"[RESOLVER] Could not find any match for {self.canonical} among broker symbols.")
                return None

            # Ensure symbol is selected in Market Watch
            mt5.symbol_select(chosen_name, True)
            info = mt5.symbol_info(chosen_name)
            if not info:
                logger.error(f"[RESOLVER] symbol_info({chosen_name}) returned None")
                return None

            tick = mt5.symbol_info_tick(chosen_name)
            bid = float(tick.bid) if tick else float(getattr(info, "bid", 0.0))
            ask = float(tick.ask) if tick else float(getattr(info, "ask", 0.0))
            point = float(getattr(info, "point", 0.01)) or 0.01
            spread_pts = (
                round((ask - bid) / point, 1)
                if (ask > 0 and bid > 0 and point > 0)
                else float(getattr(info, "spread", 0))
            )

            trade_mode = int(getattr(info, "trade_mode", 4))
            # trade_mode == 4 is SYMBOL_TRADE_MODE_FULL
            is_tradable = (trade_mode == 4) and (bid > 0) and (ask > 0)

            spec = ResolvedSymbolSpec(
                symbol=chosen_name,
                canonical=self.canonical,
                digits=int(getattr(info, "digits", 2)),
                point=point,
                tick_size=float(getattr(info, "trade_tick_size", point)),
                tick_value=float(getattr(info, "trade_tick_value", 1.0)),
                contract_size=float(getattr(info, "trade_contract_size", 100.0 if "XAU" in self.canonical else 1.0)),
                min_lot=float(getattr(info, "volume_min", 0.01)),
                max_lot=float(getattr(info, "volume_max", 100.0)),
                lot_step=float(getattr(info, "volume_step", 0.01)),
                stops_level=int(getattr(info, "trade_stops_level", 0)),
                freeze_level=int(getattr(info, "trade_freeze_level", 0)),
                filling_mode=int(getattr(info, "filling_mode", 0)),
                trade_mode=trade_mode,
                bid=bid,
                ask=ask,
                spread_points=spread_pts,
                is_tradable=is_tradable,
                raw_info={
                    "name": info.name,
                    "description": getattr(info, "description", ""),
                    "currency_base": getattr(info, "currency_base", ""),
                    "currency_profit": getattr(info, "currency_profit", ""),
                    "margin_initial": getattr(info, "margin_initial", 0.0),
                },
            )
            self.selected_spec = spec
            logger.info(
                f"[RESOLVER] Successfully resolved {self.canonical} -> '{spec.symbol}' | Digits: {spec.digits} | "
                f"Point: {spec.point} | ContractSize: {spec.contract_size} | Min/Max/Step Lot: {spec.min_lot}/{spec.max_lot}/{spec.lot_step} | "
                f"FillingMode: {spec.filling_mode} | Bid: {spec.bid} | Ask: {spec.ask} | Tradable: {spec.is_tradable}"
            )
            return spec
        except Exception as e:
            logger.error(f"[RESOLVER] Exception during {self.canonical} symbol resolution: {e}")
            return None


# Backward-compatible Gold symbol resolver alias
class GoldSymbolResolver(MultiSymbolResolver):
    def __init__(self, aliases: Optional[Sequence[str]] = None, fallback: str = "XAUUSD"):
        super().__init__(canonical="XAUUSD", aliases=aliases, fallback=fallback)


# Dedicated Bitcoin symbol resolver
class BtcSymbolResolver(MultiSymbolResolver):
    def __init__(self, aliases: Optional[Sequence[str]] = None, fallback: str = "BTCUSD"):
        super().__init__(canonical="BTCUSD", aliases=aliases, fallback=fallback)
