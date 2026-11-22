"""
MT5 Order Execution Pipeline for GOLD Scalper.
Provides serialized, thread-safe market order execution, compatible filling mode selection,
protective SL enforcement, and retry logic distinguishing transient requotes from permanent errors.
"""

from __future__ import annotations
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.scalper.config import ExecutionConfig
from src.scalper.symbol_resolver import ResolvedSymbolSpec

logger = logging.getLogger("GoldOrderExecutor")

# Retcodes classification
RETRYABLE_RETCODES = {
    10004,  # TRADE_RETCODE_REQUOTE
    10006,  # TRADE_RETCODE_REJECT
    10012,  # TRADE_RETCODE_TIMEOUT
    10018,  # TRADE_RETCODE_MARKET_CLOSED
    10020,  # TRADE_RETCODE_PRICE_CHANGED
    10021,  # TRADE_RETCODE_PRICE_OFF
}

PERMANENT_RETCODES = {
    10013,  # TRADE_RETCODE_INVALID
    10014,  # TRADE_RETCODE_INVALID_VOLUME
    10015,  # TRADE_RETCODE_INVALID_PRICE
    10016,  # TRADE_RETCODE_INVALID_STOPS
    10017,  # TRADE_RETCODE_TRADE_DISABLED
    10019,  # TRADE_RETCODE_NO_MONEY
}


@dataclass
class OrderExecutionResult:
    is_success: bool
    ticket: int = 0
    deal: int = 0
    price: float = 0.0
    volume: float = 0.0
    retcode: int = 0
    comment: str = ""
    error_message: str = ""
    is_retryable: bool = False
    raw_response: Dict[str, Any] = field(default_factory=dict)


class GoldOrderExecutor:
    def __init__(self, config: Optional[ExecutionConfig] = None):
        self.config = config or ExecutionConfig()
        self._lock = threading.Lock()
        self.simulated_positions: Dict[int, Dict[str, Any]] = {}
        self._sim_ticket_seq = 600000

    @staticmethod
    def determine_filling_mode(spec: Optional[ResolvedSymbolSpec] = None) -> int:
        """
        Queries symbol filling_mode bitmask:
        Bit 0 (1): SYMBOL_FILLING_FOK
        Bit 1 (2): SYMBOL_FILLING_IOC
        Returns compatible MT5 filling type:
        1 = ORDER_FILLING_FOK
        2 = ORDER_FILLING_IOC
        0 = ORDER_FILLING_RETURN
        """
        if not spec or spec.filling_mode is None:
            return 2  # Default IOC
        fm = spec.filling_mode
        if fm & 2:
            return 2  # ORDER_FILLING_IOC
        elif fm & 1:
            return 1  # ORDER_FILLING_FOK
        else:
            return 0  # ORDER_FILLING_RETURN

    def submit_market_order(
        self,
        symbol: str,
        direction: str,
        volume: float,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        comment: str = "GS_GOLD",
        magic: int = 777001,
        spec: Optional[ResolvedSymbolSpec] = None,
        is_simulation: bool = False,
    ) -> OrderExecutionResult:
        """
        Submits market order with serialized thread-safe MT5 execution and transient retries.
        """
        is_buy = direction.upper() in ("BUY", "ORDER_TYPE_BUY", "0")

        # Handle simulation mode
        if is_simulation:
            with self._lock:
                self._sim_ticket_seq += 1
                t = self._sim_ticket_seq
                fill_px = (spec.ask if is_buy else spec.bid) if spec and (spec.ask > 0 or spec.bid > 0) else (2650.50 if is_buy else 2650.00)
                pos_data = {
                    "ticket": t,
                    "symbol": symbol,
                    "direction": "BUY" if is_buy else "SELL",
                    "volume": volume,
                    "price": fill_px,
                    "sl": stop_loss,
                    "tp": take_profit,
                    "open_time": time.time(),
                }
                self.simulated_positions[t] = pos_data
                return OrderExecutionResult(
                    is_success=True,
                    ticket=t,
                    deal=t + 1000,
                    price=fill_px,
                    volume=volume,
                    retcode=10009,  # TRADE_RETCODE_DONE
                    comment=comment,
                    is_retryable=False,
                )

        # Real MT5 API order transmission
        try:
            import MetaTrader5 as mt5

            action_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
            filling_mode = self.determine_filling_mode(spec)

            max_retries = self.config.max_retries
            delay_sec = max(0.05, self.config.retry_delay_ms / 1000.0)

            for attempt in range(1, max_retries + 1):
                with self._lock:
                    # Fetch latest tick inside lock to get accurate market price
                    tick = mt5.symbol_info_tick(symbol)
                    if not tick:
                        if attempt < max_retries:
                            time.sleep(delay_sec)
                            continue
                        return OrderExecutionResult(
                            is_success=False,
                            error_message=f"Failed to retrieve live tick for {symbol}",
                            is_retryable=True,
                        )

                    price = float(tick.ask if is_buy else tick.bid)

                    request = {
                        "action": mt5.TRADE_ACTION_DEAL,
                        "symbol": symbol,
                        "volume": float(volume),
                        "type": action_type,
                        "price": price,
                        "sl": float(stop_loss),
                        "tp": float(take_profit),
                        "deviation": int(self.config.slippage_points),
                        "magic": int(magic),
                        "comment": str(comment),
                        "type_time": mt5.ORDER_TIME_GTC,
                        "type_filling": filling_mode,
                    }

                    result = mt5.order_send(request)

                if result is None:
                    last_err = mt5.last_error()
                    logger.warning(f"[EXECUTOR] order_send returned None (attempt {attempt}/{max_retries}): {last_err}")
                    if attempt < max_retries:
                        time.sleep(delay_sec)
                        continue
                    return OrderExecutionResult(
                        is_success=False,
                        error_message=f"order_send returned None: {last_err}",
                        is_retryable=True,
                    )

                retcode = int(getattr(result, "retcode", 0))
                if retcode in (10008, 10009):  # PLACED or DONE
                    ticket = int(getattr(result, "order", getattr(result, "deal", 0)))
                    deal = int(getattr(result, "deal", 0))
                    fill_px = float(getattr(result, "price", price))
                    logger.info(f"[EXECUTOR] Order SUCCESS: Ticket #{ticket} Deal #{deal} | {symbol} {direction} {volume} @ {fill_px} | SL: {stop_loss}")
                    return OrderExecutionResult(
                        is_success=True,
                        ticket=ticket,
                        deal=deal,
                        price=fill_px,
                        volume=volume,
                        retcode=retcode,
                        comment=comment,
                    )

                is_retryable = retcode in RETRYABLE_RETCODES
                err_msg = f"Broker retcode {retcode}: {getattr(result, 'comment', 'Order rejected')}"
                logger.warning(f"[EXECUTOR] Order failed (attempt {attempt}/{max_retries}): {err_msg} (Retryable: {is_retryable})")

                if is_retryable and attempt < max_retries:
                    time.sleep(delay_sec)
                    continue

                return OrderExecutionResult(
                    is_success=False,
                    retcode=retcode,
                    error_message=err_msg,
                    is_retryable=is_retryable,
                )

            return OrderExecutionResult(
                is_success=False,
                error_message=f"Order failed after {max_retries} attempts",
                is_retryable=True,
            )

        except Exception as e:
            logger.error(f"[EXECUTOR] Exception in submit_market_order: {e}")
            return OrderExecutionResult(
                is_success=False,
                error_message=str(e),
                is_retryable=False,
            )

    def close_position(
        self,
        ticket: int,
        symbol: str,
        volume: float,
        is_buy: bool,
        comment: str = "GS_CLOSE",
        spec: Optional[ResolvedSymbolSpec] = None,
        is_simulation: bool = False,
    ) -> OrderExecutionResult:
        """Closes position by sending an opposing deal."""
        if is_simulation:
            with self._lock:
                self.simulated_positions.pop(ticket, None)
                return OrderExecutionResult(is_success=True, ticket=ticket, retcode=10009)

        try:
            import MetaTrader5 as mt5

            close_action = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
            filling_mode = self.determine_filling_mode(spec)

            with self._lock:
                tick = mt5.symbol_info_tick(symbol)
                price = float(tick.bid if is_buy else tick.ask) if tick else 0.0

                req = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "position": int(ticket),
                    "symbol": symbol,
                    "volume": float(volume),
                    "type": close_action,
                    "price": price,
                    "deviation": int(self.config.slippage_points),
                    "comment": str(comment),
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": filling_mode,
                }
                res = mt5.order_send(req)

            if res and res.retcode in (10008, 10009):
                logger.info(f"[EXECUTOR] Position #{ticket} closed successfully.")
                return OrderExecutionResult(is_success=True, ticket=ticket, retcode=res.retcode)
            ret = getattr(res, "retcode", 0) if res else -1
            msg = getattr(res, "comment", "Close failed") if res else str(mt5.last_error())
            return OrderExecutionResult(is_success=False, ticket=ticket, retcode=ret, error_message=msg)
        except Exception as e:
            return OrderExecutionResult(is_success=False, ticket=ticket, error_message=str(e))

    def modify_position_sl(
        self,
        ticket: int,
        symbol: str,
        new_sl: float,
        new_tp: float = 0.0,
        is_simulation: bool = False,
    ) -> OrderExecutionResult:
        """Modifies existing position's protective SL / TP."""
        if is_simulation:
            with self._lock:
                if ticket in self.simulated_positions:
                    self.simulated_positions[ticket]["sl"] = new_sl
                    self.simulated_positions[ticket]["tp"] = new_tp
                return OrderExecutionResult(is_success=True, ticket=ticket, retcode=10009)

        try:
            import MetaTrader5 as mt5

            with self._lock:
                req = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": int(ticket),
                    "symbol": symbol,
                    "sl": float(new_sl),
                    "tp": float(new_tp),
                }
                res = mt5.order_send(req)

            if res and res.retcode in (10008, 10009):
                return OrderExecutionResult(is_success=True, ticket=ticket, retcode=res.retcode)
            ret = getattr(res, "retcode", 0) if res else -1
            msg = getattr(res, "comment", "SL modify failed") if res else str(mt5.last_error())
            return OrderExecutionResult(is_success=False, ticket=ticket, retcode=ret, error_message=msg)
        except Exception as e:
            return OrderExecutionResult(is_success=False, ticket=ticket, error_message=str(e))
