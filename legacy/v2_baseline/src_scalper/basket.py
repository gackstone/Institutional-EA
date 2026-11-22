"""
Basket Lifecycle and Multi-Position Management for Dual-Market Scalping.
Manages independent multi-position baskets for GOLD and BTCUSD:
- Independent basket tracking, position isolation, and magic number separation
- Independent individual position TP and aggregate basket TP per symbol
- Independent maximum holding times and breakeven exits
- Seamless position management during calendar transitions (outgoing positions managed to completion)
- Immediate re-entry primed per instrument
"""

from __future__ import annotations
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from src.scalper.config import BasketConfig, IndividualTPConfig, BasketTPConfig, HoldingTimeConfig, InstrumentScalperConfig

logger = logging.getLogger("BasketManager")


class BasketState(str, Enum):
    IDLE = "IDLE"
    OPENING = "OPENING"
    ACTIVE = "ACTIVE"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"


@dataclass
class BasketPosition:
    ticket: int
    symbol: str
    direction: str  # "BUY" or "SELL"
    volume: float
    open_price: float
    current_price: float = 0.0
    profit: float = 0.0
    commission: float = 0.0
    swap: float = 0.0
    open_time: float = field(default_factory=time.time)
    stop_loss: float = 0.0
    take_profit: float = 0.0
    magic: int = 777001
    symbol_key: str = "GOLD"

    @property
    def net_profit(self) -> float:
        return self.profit + self.commission + self.swap


@dataclass
class ScalperBasket:
    basket_id: str
    symbol_key: str = "GOLD"      # "GOLD" or "BTCUSD"
    symbol: str = "XAUUSD"        # Broker resolved symbol
    direction: str = "BUY"        # "BUY" or "SELL"
    target_size: int = 4
    magic_number: int = 777001
    positions: Dict[int, BasketPosition] = field(default_factory=dict)
    state: BasketState = BasketState.OPENING
    created_at: float = field(default_factory=time.time)
    closed_at: Optional[float] = None
    close_reason: Optional[str] = None
    realized_profit: float = 0.0
    basket_tp_usd: float = 2.00
    tp_usd_per_min_lot: float = 0.50
    max_hold_seconds: int = 180

    @property
    def position_count(self) -> int:
        return len(self.positions)

    @property
    def total_volume(self) -> float:
        return round(sum(p.volume for p in self.positions.values()), 4)

    @property
    def net_floating_profit(self) -> float:
        return round(sum(p.net_profit for p in self.positions.values()), 4)

    @property
    def duration_seconds(self) -> float:
        end_time = self.closed_at or time.time()
        return max(0.0, end_time - self.created_at)

    def add_position(self, pos: BasketPosition) -> None:
        self.positions[pos.ticket] = pos
        if len(self.positions) >= self.target_size and self.state == BasketState.OPENING:
            self.state = BasketState.ACTIVE

    def update_position(
        self,
        ticket: int,
        current_price: float,
        profit: float,
        commission: float = 0.0,
        swap: float = 0.0,
    ) -> None:
        if ticket in self.positions:
            p = self.positions[ticket]
            p.current_price = current_price
            p.profit = profit
            p.commission = commission
            p.swap = swap

    def remove_position(self, ticket: int, final_profit: Optional[float] = None) -> Optional[BasketPosition]:
        pos = self.positions.pop(ticket, None)
        if pos and final_profit is not None:
            self.realized_profit += final_profit
        elif pos:
            self.realized_profit += pos.net_profit

        if len(self.positions) == 0:
            self.state = BasketState.CLOSED
            self.closed_at = time.time()
        return pos


# Backward-compatible alias
GoldBasket = ScalperBasket


class MultiBasketManager:
    """
    Multi-instrument basket manager maintaining separated state and exit tracking
    for GOLD and BTCUSD.
    """

    def __init__(self):
        self.active_baskets: Dict[str, ScalperBasket] = {}
        self.closed_baskets: List[ScalperBasket] = []
        self._reentry_ready: Dict[str, bool] = {"GOLD": True, "BTCUSD": True}

    def has_active_basket(self, symbol_key: str = "GOLD") -> bool:
        b = self.active_baskets.get(symbol_key.upper())
        return b is not None and b.state in (BasketState.OPENING, BasketState.ACTIVE, BasketState.CLOSING)

    def get_active_basket(self, symbol_key: str = "GOLD") -> Optional[ScalperBasket]:
        return self.active_baskets.get(symbol_key.upper())

    def get_all_active_baskets(self) -> List[ScalperBasket]:
        return [b for b in self.active_baskets.values() if b.state in (BasketState.OPENING, BasketState.ACTIVE, BasketState.CLOSING)]

    def is_reentry_ready(self, symbol_key: str = "GOLD") -> bool:
        return self._reentry_ready.get(symbol_key.upper(), True)

    def start_new_basket(
        self,
        symbol_key: str,
        symbol: str,
        direction: str,
        target_size: int = 4,
        magic_number: int = 777001,
        basket_tp_usd: float = 2.00,
        tp_usd_per_min_lot: float = 0.50,
        max_hold_seconds: int = 180,
    ) -> ScalperBasket:
        sym_k = symbol_key.upper()
        basket = ScalperBasket(
            basket_id=f"BSK_{sym_k}_{uuid.uuid4().hex[:6].upper()}",
            symbol_key=sym_k,
            symbol=symbol,
            direction=direction.upper(),
            target_size=target_size,
            magic_number=magic_number,
            basket_tp_usd=basket_tp_usd,
            tp_usd_per_min_lot=tp_usd_per_min_lot,
            max_hold_seconds=max_hold_seconds,
            state=BasketState.OPENING,
            created_at=time.time(),
        )
        self.active_baskets[sym_k] = basket
        self._reentry_ready[sym_k] = False
        logger.info(
            f"[BASKET] Started new {sym_k} basket {basket.basket_id} | Symbol: {symbol} | "
            f"Direction: {basket.direction} | Magic: {magic_number} | Target size: {target_size} | TP: ${basket_tp_usd:.2f}"
        )
        return basket

    def evaluate_exits_for_symbol(self, symbol_key: str) -> Tuple[List[int], Optional[str]]:
        sym_k = symbol_key.upper()
        basket = self.active_baskets.get(sym_k)
        if not basket or len(basket.positions) == 0:
            return [], None

        dur = basket.duration_seconds
        net_profit = basket.net_floating_profit

        # 1. Aggregate Basket Take Profit
        if net_profit >= basket.basket_tp_usd:
            tickets = list(basket.positions.keys())
            reason = f"BASKET_TP_REACHED: {sym_k} Net ${net_profit:.2f} >= Target ${basket.basket_tp_usd:.2f}"
            logger.info(f"[BASKET] {basket.basket_id} {reason}")
            return tickets, "BASKET_TP"

        # 2. Maximum Holding Time Expiration
        if dur >= basket.max_hold_seconds:
            tickets = list(basket.positions.keys())
            if net_profit >= 0:
                reason = f"MAX_HOLD_BREAKEVEN: {sym_k} Duration {dur:.0f}s >= {basket.max_hold_seconds}s, closing at profit ${net_profit:.2f}"
                logger.info(f"[BASKET] {basket.basket_id} {reason}")
                return tickets, "MAX_HOLD_BREAKEVEN"
            else:
                reason = f"MAX_HOLD_TIMEOUT: {sym_k} Duration {dur:.0f}s >= {basket.max_hold_seconds}s, controlling loss at ${net_profit:.2f}"
                logger.warning(f"[BASKET] {basket.basket_id} {reason}")
                return tickets, "MAX_HOLD_TIMEOUT"

        # 3. Individual Position Take Profit
        ind_tickets = []
        for ticket, pos in basket.positions.items():
            min_lot_units = max(1.0, pos.volume / 0.01)
            pos_target_usd = min_lot_units * basket.tp_usd_per_min_lot
            if pos.net_profit >= pos_target_usd:
                ind_tickets.append(ticket)
        if ind_tickets:
            logger.info(f"[BASKET] {basket.basket_id} individual TP triggered for {len(ind_tickets)} position(s): {ind_tickets}")
            return ind_tickets, "INDIVIDUAL_TP"

        return [], None

    def evaluate_all_exits(self) -> List[Tuple[str, List[int], str]]:
        """Evaluates exits across all active baskets (both GOLD and BTCUSD)."""
        results: List[Tuple[str, List[int], str]] = []
        for sym_k in list(self.active_baskets.keys()):
            tickets, reason = self.evaluate_exits_for_symbol(sym_k)
            if tickets and reason:
                results.append((sym_k, tickets, reason))
        return results

    def on_position_closed(self, ticket: int, realized_pnl: float, symbol_key: Optional[str] = None) -> None:
        """Invoked when a position closure is confirmed."""
        target_basket: Optional[ScalperBasket] = None
        if symbol_key and symbol_key.upper() in self.active_baskets:
            target_basket = self.active_baskets[symbol_key.upper()]
        else:
            # Search all active baskets for the ticket
            for b in self.active_baskets.values():
                if ticket in b.positions:
                    target_basket = b
                    break

        if not target_basket:
            return

        sym_k = target_basket.symbol_key
        target_basket.remove_position(ticket, realized_pnl)
        if len(target_basket.positions) == 0:
            self.close_basket(sym_k, reason=target_basket.close_reason or "ALL_POSITIONS_CLOSED")

    def close_basket(self, symbol_key: str, reason: str = "COMPLETED") -> None:
        sym_k = symbol_key.upper()
        basket = self.active_baskets.pop(sym_k, None)
        if not basket:
            return
        basket.state = BasketState.CLOSED
        basket.closed_at = time.time()
        basket.close_reason = reason
        self.closed_baskets.append(basket)
        self._reentry_ready[sym_k] = True
        logger.info(
            f"[BASKET] {sym_k} Basket {basket.basket_id} closed cleanly: {reason} | Duration: {basket.duration_seconds:.1f}s | "
            f"Realized PnL: ${basket.realized_profit:.2f} | Immediate re-entry primed for {sym_k}."
        )


class GoldBasketManager(MultiBasketManager):
    """
    Direct backward-compatibility adapter for legacy single-symbol GOLD test suites.
    Exposes the exact single-symbol interface.
    """

    def __init__(
        self,
        basket_cfg: Optional[BasketConfig] = None,
        ind_tp_cfg: Optional[IndividualTPConfig] = None,
        basket_tp_cfg: Optional[BasketTPConfig] = None,
        holding_cfg: Optional[HoldingTimeConfig] = None,
    ):
        super().__init__()
        self.basket_cfg = basket_cfg or BasketConfig()
        self.ind_tp_cfg = ind_tp_cfg or IndividualTPConfig()
        self.basket_tp_cfg = basket_tp_cfg or BasketTPConfig()
        self.holding_cfg = holding_cfg or HoldingTimeConfig()

    @property
    def active_basket(self) -> Optional[ScalperBasket]:
        return self.active_baskets.get("GOLD")

    @active_basket.setter
    def active_basket(self, val: Optional[ScalperBasket]) -> None:
        if val is None:
            self.active_baskets.pop("GOLD", None)
        else:
            self.active_baskets["GOLD"] = val

    @property
    def ready_for_reentry(self) -> bool:
        return self._reentry_ready.get("GOLD", True)

    @ready_for_reentry.setter
    def ready_for_reentry(self, val: bool) -> None:
        self._reentry_ready["GOLD"] = bool(val)

    def has_active_basket(self, symbol_key: str = "GOLD") -> bool:
        return super().has_active_basket("GOLD")

    def start_new_basket(
        self,
        direction: str = "BUY",
        target_size: Optional[int] = None,
        symbol_key: str = "GOLD",
        symbol: str = "XAUUSD",
        magic_number: int = 777001,
        basket_tp_usd: Optional[float] = None,
        tp_usd_per_min_lot: Optional[float] = None,
        max_hold_seconds: Optional[int] = None,
    ) -> ScalperBasket:
        size = target_size or self.basket_cfg.basket_size
        size = min(size, self.basket_cfg.max_basket_size)
        return super().start_new_basket(
            symbol_key=symbol_key,
            symbol=symbol,
            direction=direction,
            target_size=size,
            magic_number=magic_number,
            basket_tp_usd=basket_tp_usd if basket_tp_usd is not None else self.basket_tp_cfg.basket_tp_usd,
            tp_usd_per_min_lot=tp_usd_per_min_lot if tp_usd_per_min_lot is not None else self.ind_tp_cfg.tp_usd_per_min_lot,
            max_hold_seconds=max_hold_seconds if max_hold_seconds is not None else self.holding_cfg.max_hold_seconds,
        )

    def evaluate_exits(self) -> Tuple[List[int], Optional[str]]:
        return self.evaluate_exits_for_symbol("GOLD")

    def on_position_closed(self, ticket: int, realized_pnl: float, symbol_key: Optional[str] = "GOLD") -> None:
        super().on_position_closed(ticket, realized_pnl, symbol_key=symbol_key or "GOLD")

    def close_active_basket(self, reason: str = "COMPLETED") -> None:
        self.close_basket("GOLD", reason=reason)
