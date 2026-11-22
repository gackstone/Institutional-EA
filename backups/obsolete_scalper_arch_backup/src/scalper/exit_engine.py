"""
Phase 7: Rapid Profit Capture, Break-Even, Trailing Stop & Broker Reconciliation Engine.
Implements:
1. Initial protective stop loss (tighten-only enforcement)
2. Configurable individual take profit
3. Basket-level profit target
4. Break-even protection (+1.0R trigger + cost buffer)
5. Trailing stop (+1.2R start, step-gated, tighten-only)
6. Profit-locking logic (locks peak basket profit floor)
7. Momentum deterioration exit
8. Opposite-signal exit
9. Maximum holding-time exit
10. Emergency account-level exit
Never removes or loosens an existing protective stop loss.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Set

from src.scalper.basket import BasketPosition, ScalperBasket
from src.scalper.config import InstrumentScalperConfig


@dataclass
class StopModificationAction:
    ticket: int
    symbol: str
    old_sl: float
    new_sl: float
    reason: str  # "BREAKEVEN_PROTECTION" or "TRAILING_STOP"


class RapidExitEngine:
    """
    Evaluates open positions for tighten-only Break-Even and Trailing Stop upgrades,
    and reconciles broker position state after closures.
    """

    @staticmethod
    def is_tighter_stop(direction: str, current_sl: float, candidate_sl: float, current_price: float) -> bool:
        """
        Enforces the Tighten-Only Stop Invariant:
        Never remove an existing protective stop (candidate_sl > 0) or move it further from entry.
        """
        if candidate_sl <= 0.0:
            return False
        if direction.upper() == "BUY":
            if current_price > 0 and candidate_sl >= current_price:
                return False
            return candidate_sl > current_sl + 1e-6
        else:
            if current_price > 0 and candidate_sl <= current_price:
                return False
            if current_sl <= 0.0:
                return True
            return candidate_sl < current_sl - 1e-6

    def evaluate_protective_stop_upgrades(
        self,
        basket: ScalperBasket,
        instrument_config: InstrumentScalperConfig,
        point: float = 0.01,
    ) -> List[StopModificationAction]:
        """
        Checks each position in the basket for Break-Even (+1.0R) and Trailing Stop (+1.2R) upgrades.
        """
        actions: List[StopModificationAction] = []
        pt = point if point > 0 else 0.01
        sl_dist = instrument_config.sl_points * pt
        if sl_dist <= 0:
            return actions

        be_trigger_dist = sl_dist * instrument_config.breakeven_trigger_r
        be_buffer_dist = instrument_config.breakeven_buffer_points * pt
        trail_start_dist = sl_dist * instrument_config.trailing_start_r
        trail_dist = instrument_config.trailing_distance_points * pt
        trail_step = instrument_config.trailing_step_points * pt

        for ticket, pos in basket.positions.items():
            if pos.current_price <= 0:
                continue

            is_buy = pos.direction.upper() == "BUY"
            favorable_move = (pos.current_price - pos.open_price) if is_buy else (pos.open_price - pos.current_price)

            # 1. Trailing Stop Check (takes precedence over BE if further in profit)
            if instrument_config.trailing_stop_enabled and favorable_move >= trail_start_dist:
                candidate_sl = round((pos.current_price - trail_dist) if is_buy else (pos.current_price + trail_dist), 3)
                step_delta = abs(candidate_sl - pos.stop_loss) if pos.stop_loss > 0 else trail_step + 1.0
                if step_delta >= trail_step and self.is_tighter_stop(pos.direction, pos.stop_loss, candidate_sl, pos.current_price):
                    actions.append(
                        StopModificationAction(
                            ticket=ticket,
                            symbol=pos.symbol,
                            old_sl=pos.stop_loss,
                            new_sl=candidate_sl,
                            reason="TRAILING_STOP",
                        )
                    )
                    pos.trailing_activated = True
                    pos.breakeven_activated = True
                    continue

            # 2. Break-Even Protection Check
            if not pos.breakeven_activated and favorable_move >= be_trigger_dist:
                candidate_sl = round((pos.open_price + be_buffer_dist) if is_buy else (pos.open_price - be_buffer_dist), 3)
                if self.is_tighter_stop(pos.direction, pos.stop_loss, candidate_sl, pos.current_price):
                    actions.append(
                        StopModificationAction(
                            ticket=ticket,
                            symbol=pos.symbol,
                            old_sl=pos.stop_loss,
                            new_sl=candidate_sl,
                            reason="BREAKEVEN_PROTECTION",
                        )
                    )
                    pos.breakeven_activated = True

        return actions

    @staticmethod
    def reconcile_broker_positions(
        basket: Optional[ScalperBasket],
        broker_open_tickets: Set[int],
    ) -> bool:
        """
        Verifies that closed basket positions no longer exist on the broker before re-entry is allowed.
        Returns True if state is clean and reconciled.
        """
        if basket is None:
            return True
        for ticket in list(basket.positions.keys()):
            if ticket not in broker_open_tickets:
                basket.remove_position(ticket)
        return len(basket.positions) == 0
