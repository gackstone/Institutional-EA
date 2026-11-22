"""
Basket Lifecycle and Multi-Position Management for GOLD Scalper.
Manages multi-position baskets, individual position TP, aggregate basket TP,
maximum holding time (time stop), and immediate re-entry triggering upon basket closure.
"""

from __future__ import annotations
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from src.scalper.config import BasketConfig, IndividualTPConfig, BasketTPConfig, HoldingTimeConfig

logger = logging.getLogger("GoldBasketManager")


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

    @property
    def net_profit(self) -> float:
        return self.profit + self.commission + self.swap


@dataclass
class GoldBasket:
    basket_id: str
    direction: str  # "BUY" or "SELL"
    target_size: int = 4
    positions: Dict[int, BasketPosition] = field(default_factory=dict)
    state: BasketState = BasketState.OPENING
    created_at: float = field(default_factory=time.time)
    closed_at: Optional[float] = None
    close_reason: Optional[str] = None
    realized_profit: float = 0.0

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
        swap: float = 0.0
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


class GoldBasketManager:
    def __init__(
        self,
        basket_cfg: Optional[BasketConfig] = None,
        ind_tp_cfg: Optional[IndividualTPConfig] = None,
        basket_tp_cfg: Optional[BasketTPConfig] = None,
        holding_cfg: Optional[HoldingTimeConfig] = None,
    ):
        self.basket_cfg = basket_cfg or BasketConfig()
        self.ind_tp_cfg = ind_tp_cfg or IndividualTPConfig()
        self.basket_tp_cfg = basket_tp_cfg or BasketTPConfig()
        self.holding_cfg = holding_cfg or HoldingTimeConfig()

        self.active_basket: Optional[GoldBasket] = None
        self.closed_baskets: List[GoldBasket] = []
        self.ready_for_reentry: bool = True

    def has_active_basket(self) -> bool:
        return self.active_basket is not None and self.active_basket.state in (
            BasketState.OPENING,
            BasketState.ACTIVE,
            BasketState.CLOSING,
        )

    def start_new_basket(self, direction: str, target_size: Optional[int] = None) -> GoldBasket:
        """Initializes a new trading basket in the specified direction."""
        size = target_size or self.basket_cfg.basket_size
        size = min(size, self.basket_cfg.max_basket_size)
        basket = GoldBasket(
            basket_id=f"BSK_{uuid.uuid4().hex[:8].upper()}",
            direction=direction.upper(),
            target_size=size,
            state=BasketState.OPENING,
            created_at=time.time(),
        )
        self.active_basket = basket
        self.ready_for_reentry = False
        logger.info(f"[BASKET] Started new basket {basket.basket_id} | Direction: {basket.direction} | Target size: {basket.target_size}")
        return basket

    def evaluate_exits(self) -> Tuple[List[int], Optional[str]]:
        """
        Evaluates active basket against:
        1. Aggregate basket TP threshold
        2. Individual position TP thresholds
        3. Maximum holding duration / breakeven urgency
        Returns: (tickets_to_close, reason)
        """
        if not self.active_basket or len(self.active_basket.positions) == 0:
            return [], None

        basket = self.active_basket
        dur = basket.duration_seconds
        net_profit = basket.net_floating_profit

        # 1. Aggregate Basket Take Profit
        if self.basket_tp_cfg.enabled:
            target_usd = self.basket_tp_cfg.basket_tp_usd
            if net_profit >= target_usd:
                tickets = list(basket.positions.keys())
                reason = f"BASKET_TP_REACHED: Net ${net_profit:.2f} >= Target ${target_usd:.2f}"
                logger.info(f"[BASKET] {basket.basket_id} {reason}")
                return tickets, "BASKET_TP"

        # 2. Maximum Holding Time Expiration
        max_hold = self.holding_cfg.max_hold_seconds
        if dur >= max_hold:
            tickets = list(basket.positions.keys())
            if net_profit >= 0:
                reason = f"MAX_HOLD_BREAKEVEN: Duration {dur:.0f}s >= {max_hold}s, closing at profit ${net_profit:.2f}"
                logger.info(f"[BASKET] {basket.basket_id} {reason}")
                return tickets, "MAX_HOLD_BREAKEVEN"
            elif self.holding_cfg.allow_controlled_loss_exit:
                reason = f"MAX_HOLD_TIMEOUT: Duration {dur:.0f}s >= {max_hold}s, controlling loss at ${net_profit:.2f}"
                logger.warning(f"[BASKET] {basket.basket_id} {reason}")
                return tickets, "MAX_HOLD_TIMEOUT"

        # 3. Individual Position Take Profit
        if self.ind_tp_cfg.enabled:
            ind_tickets = []
            for ticket, pos in basket.positions.items():
                min_lot_units = max(1.0, pos.volume / 0.01)
                pos_target_usd = min_lot_units * self.ind_tp_cfg.tp_usd_per_min_lot
                if pos.net_profit >= pos_target_usd:
                    ind_tickets.append(ticket)
            if ind_tickets:
                logger.info(f"[BASKET] {basket.basket_id} individual TP triggered for {len(ind_tickets)} position(s): {ind_tickets}")
                return ind_tickets, "INDIVIDUAL_TP"

        return [], None

    def on_position_closed(self, ticket: int, realized_pnl: float) -> None:
        """Invoked when a broker confirmation confirms position closure."""
        if not self.active_basket:
            return
        self.active_basket.remove_position(ticket, realized_pnl)
        if len(self.active_basket.positions) == 0:
            self.close_active_basket(reason=self.active_basket.close_reason or "ALL_POSITIONS_CLOSED")

    def close_active_basket(self, reason: str = "COMPLETED") -> None:
        """Marks active basket as closed and immediately primes engine for next re-entry."""
        if not self.active_basket:
            return
        basket = self.active_basket
        basket.state = BasketState.CLOSED
        basket.closed_at = time.time()
        basket.close_reason = reason
        self.closed_baskets.append(basket)
        self.active_basket = None
        self.ready_for_reentry = True
        logger.info(
            f"[BASKET] Basket {basket.basket_id} closed cleanly: {reason} | Duration: {basket.duration_seconds:.1f}s | "
            f"Realized PnL: ${basket.realized_profit:.2f} | Immediate re-entry primed."
        )
