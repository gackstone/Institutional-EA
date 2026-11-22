"""
Basket Lifecycle and Multi-Position Management for High-Speed Dual-Market Scalping.
Manages independent multi-position baskets for GOLD and BTCUSD:
- Independent basket tracking, position isolation, and magic number separation (777001 vs 777002)
- Tracks worst-case monetary risk, peak floating profit (for profit-locking), and per-position break-even/trailing state
- Seamless position management during calendar transitions (outgoing positions managed to completion)
- Broker position reconciliation before re-entry
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import logging
import time
import uuid
from typing import Dict, List, Optional, Tuple

from src.scalper.config import BasketConfig, BasketTPConfig, HoldingTimeConfig, IndividualTPConfig

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
    entry_id: str = ""
    entry_reason: str = ""
    worst_case_risk_usd: float = 0.50
    breakeven_activated: bool = False
    trailing_activated: bool = False
    peak_favorable_price: float = 0.0

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
    peak_floating_profit_usd: float = 0.0
    profit_lock_active: bool = False
    profit_lock_floor_usd: float = 0.0
    profit_lock_trigger_usd: float = 1.50
    allocated_risk_budget_usd: float = 2.50

    @property
    def position_count(self) -> int:
        return len(self.positions)

    @property
    def total_volume(self) -> float:
        return round(sum(p.volume for p in self.positions.values()), 4)

    @property
    def net_floating_profit(self) -> float:
        net = round(sum(p.net_profit for p in self.positions.values()), 4)
        if net > self.peak_floating_profit_usd:
            self.peak_floating_profit_usd = net
        if self.peak_floating_profit_usd >= self.profit_lock_trigger_usd and not self.profit_lock_active:
            self.profit_lock_active = True
            if self.profit_lock_floor_usd <= 0.0:
                self.profit_lock_floor_usd = round(self.profit_lock_trigger_usd * 0.60, 2)
        return net

    @property
    def total_open_risk_usd(self) -> float:
        return round(sum(p.worst_case_risk_usd for p in self.positions.values()), 4)

    @property
    def duration_seconds(self) -> float:
        end_time = self.closed_at or time.time()
        return max(0.0, end_time - self.created_at)

    def add_position(self, pos: BasketPosition) -> None:
        if pos.peak_favorable_price <= 0:
            pos.peak_favorable_price = pos.open_price
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
            if p.direction == "BUY" and current_price > p.peak_favorable_price:
                p.peak_favorable_price = current_price
            elif p.direction == "SELL" and (p.peak_favorable_price <= 0 or (current_price > 0 and current_price < p.peak_favorable_price)):
                p.peak_favorable_price = current_price
        _ = self.net_floating_profit

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
    Multi-instrument basket manager maintaining separated state, exit tracking,
    and post-closure broker reconciliation for GOLD and BTCUSD.
    """

    def __init__(self):
        self.active_baskets: Dict[str, ScalperBasket] = {}
        self.closed_baskets: List[ScalperBasket] = []
        self._reentry_ready: Dict[str, bool] = {"GOLD": True, "BTCUSD": True}
        self._reconciled: Dict[str, bool] = {"GOLD": True, "BTCUSD": True}

    def has_active_basket(self, symbol_key: str = "GOLD") -> bool:
        b = self.active_baskets.get(symbol_key.upper())
        return b is not None and b.state in (BasketState.OPENING, BasketState.ACTIVE, BasketState.CLOSING)

    def get_active_basket(self, symbol_key: str = "GOLD") -> Optional[ScalperBasket]:
        return self.active_baskets.get(symbol_key.upper())

    def get_all_active_baskets(self) -> List[ScalperBasket]:
        return [b for b in self.active_baskets.values() if b.state in (BasketState.OPENING, BasketState.ACTIVE, BasketState.CLOSING)]

    def get_total_open_positions(self) -> int:
        return sum(b.position_count for b in self.active_baskets.values())

    @property
    def total_open_positions(self) -> int:
        return self.get_total_open_positions()

    def is_reentry_ready(self, symbol_key: str = "GOLD") -> bool:
        sym_k = symbol_key.upper()
        return self._reentry_ready.get(sym_k, True) and self._reconciled.get(sym_k, True)

    def mark_reconciled(self, symbol_key: str, is_reconciled: bool = True) -> None:
        self._reconciled[symbol_key.upper()] = is_reconciled

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
        profit_lock_trigger_usd: float = 1.50,
        profit_lock_floor_usd: float = 0.90,
        allocated_risk_budget_usd: float = 2.50,
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
            profit_lock_trigger_usd=profit_lock_trigger_usd,
            profit_lock_floor_usd=profit_lock_floor_usd,
            allocated_risk_budget_usd=allocated_risk_budget_usd,
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

    def evaluate_exits_for_symbol(
        self,
        symbol_key: str,
        tick_momentum: float = 0.0,
        opposite_signal_confirmed: bool = False,
    ) -> Tuple[List[int], Optional[str]]:
        sym_k = symbol_key.upper()
        basket = self.active_baskets.get(sym_k)
        if not basket or len(basket.positions) == 0:
            return [], None

        dur = basket.duration_seconds
        net_profit = basket.net_floating_profit
        all_tickets = list(basket.positions.keys())

        # 1. Aggregate Basket Take Profit
        if net_profit >= basket.basket_tp_usd:
            return all_tickets, "BASKET_TP"

        # 2. Profit-Locking Floor Exit (locks peak gains if price retraces to floor)
        if basket.profit_lock_active and net_profit <= basket.profit_lock_floor_usd and net_profit > 0:
            return all_tickets, "PROFIT_LOCK_FLOOR"

        # 3. Confirmed Opposite Signal Exit
        if opposite_signal_confirmed:
            return all_tickets, "OPPOSITE_SIGNAL_EXIT"

        # 4. Momentum Deterioration Exit (when profit is positive/near-BE and momentum sharply reverses)
        dir_sign = 1.0 if basket.direction == "BUY" else -1.0
        if dur >= 15.0 and net_profit > 0.15 and (tick_momentum * dir_sign) <= -0.65:
            return all_tickets, "MOMENTUM_DETERIORATION_EXIT"

        # 5. Maximum Holding Time Expiration
        if dur >= basket.max_hold_seconds:
            if net_profit >= 0:
                return all_tickets, "MAX_HOLD_BREAKEVEN"
            return all_tickets, "MAX_HOLD_TIMEOUT"

        # 6. Protective Stop-Loss Hit Check (in simulation or broker fallback) & Individual Position TP
        sl_tickets = []
        ind_tickets = []
        for ticket, pos in basket.positions.items():
            if pos.stop_loss > 0 and pos.current_price > 0:
                if pos.direction == "BUY" and pos.current_price <= pos.stop_loss:
                    sl_tickets.append(ticket)
                    continue
                if pos.direction == "SELL" and pos.current_price >= pos.stop_loss:
                    sl_tickets.append(ticket)
                    continue
            min_lot_units = max(1.0, pos.volume / 0.01)
            pos_target_usd = min_lot_units * basket.tp_usd_per_min_lot
            if pos.net_profit >= pos_target_usd:
                ind_tickets.append(ticket)

        if sl_tickets:
            return sl_tickets, "PROTECTIVE_SL_HIT"
        if ind_tickets:
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
        target_basket: Optional[ScalperBasket] = None
        if symbol_key and symbol_key.upper() in self.active_baskets:
            target_basket = self.active_baskets[symbol_key.upper()]
        else:
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
        self._reconciled[sym_k] = True
        logger.info(
            f"[BASKET] {sym_k} Basket {basket.basket_id} closed cleanly: {reason} | Duration: {basket.duration_seconds:.1f}s | "
            f"Realized PnL: ${basket.realized_profit:.2f} | Immediate re-entry primed for {sym_k}."
        )


class GoldBasketManager(MultiBasketManager):
    """
    Direct backward-compatibility adapter for legacy single-symbol GOLD test suites.
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
        profit_lock_trigger_usd: float = 1.50,
        profit_lock_floor_usd: float = 0.90,
        allocated_risk_budget_usd: float = 2.50,
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
            profit_lock_trigger_usd=profit_lock_trigger_usd,
            profit_lock_floor_usd=profit_lock_floor_usd,
            allocated_risk_budget_usd=allocated_risk_budget_usd,
        )

    def evaluate_exits(self) -> Tuple[List[int], Optional[str]]:
        return self.evaluate_exits_for_symbol("GOLD")

    def on_position_closed(self, ticket: int, realized_pnl: float, symbol_key: Optional[str] = "GOLD") -> None:
        super().on_position_closed(ticket, realized_pnl, symbol_key=symbol_key or "GOLD")

    def close_active_basket(self, reason: str = "COMPLETED") -> None:
        self.close_basket("GOLD", reason=reason)
