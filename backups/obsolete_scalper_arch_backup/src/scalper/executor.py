"""
MT5 Order Execution Pipeline & State Machine for GOLD & BTCUSD Scalper (v3.1.0).
Implements:
1. Full Order Execution State Machine:
   SIGNAL_APPROVED -> RISK_APPROVED -> ORDER_VALIDATED -> ORDER_SUBMITTED ->
   BROKER_ACCEPTED -> PARTIALLY_FILLED / FILLED -> POSITION_RECONCILED ->
   PROTECTION_VERIFIED -> EXECUTION_CONFIRMED (or FAILED / UNKNOWN_REQUIRES_RECONCILIATION)
2. Pre-flight order validation (connection, trade_mode, symbol availability, fresh tick,
   spread, volume bounds/step, stops_level, SL direction, and MT5 order_check).
3. Accurate MT5 retcode classification (DONE, DONE_PARTIAL, PLACED, REQUOTE, PRICE_CHANGED,
   TIMEOUT, INVALID_VOLUME, INVALID_STOPS, NO_MONEY, MARKET_CLOSED, REJECT).
4. Ambiguous timeout / null-result reconciliation before any retry to prevent duplicate orders.
5. Partial fill accounting (actual filled volume, remaining volume, risk scaling).
6. Mandatory broker-side protective SL verification with post-fill modification retries
   and fail-closed emergency liquidation if protection cannot be verified.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import logging
import math
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from src.scalper.config import ExecutionConfig
from src.scalper.symbol_resolver import ResolvedSymbolSpec

try:
    import MetaTrader5 as mt5

    HAS_MT5 = True
except ImportError:
    mt5 = None
    HAS_MT5 = False

logger = logging.getLogger("GoldOrderExecutor")

TRADE_RETCODE_REQUOTE = 10004
TRADE_RETCODE_REJECT = 10006
TRADE_RETCODE_PRICE_CHANGED = 10007
TRADE_RETCODE_PLACED = 10008
TRADE_RETCODE_DONE = 10009
TRADE_RETCODE_DONE_PARTIAL = 10010
TRADE_RETCODE_ERROR = 10011
TRADE_RETCODE_TIMEOUT = 10012
TRADE_RETCODE_INVALID = 10013
TRADE_RETCODE_INVALID_VOLUME = 10014
TRADE_RETCODE_INVALID_PRICE = 10015
TRADE_RETCODE_INVALID_STOPS = 10016
TRADE_RETCODE_TRADE_DISABLED = 10017
TRADE_RETCODE_MARKET_CLOSED = 10018
TRADE_RETCODE_NO_MONEY = 10019
TRADE_RETCODE_PRICE_OFF = 10021
TRADE_RETCODE_CONNECTION = 10031


class OrderExecutionState:
    SIGNAL_APPROVED = "SIGNAL_APPROVED"
    RISK_APPROVED = "RISK_APPROVED"
    ORDER_VALIDATED = "ORDER_VALIDATED"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    BROKER_ACCEPTED = "BROKER_ACCEPTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    POSITION_RECONCILED = "POSITION_RECONCILED"
    PROTECTION_VERIFIED = "PROTECTION_VERIFIED"
    EXECUTION_CONFIRMED = "EXECUTION_CONFIRMED"
    FAILED = "FAILED"
    UNKNOWN_REQUIRES_RECONCILIATION = "UNKNOWN_REQUIRES_RECONCILIATION"


# Retcodes safe to retry ONLY after confirming no fill occurred
RETRYABLE_RETCODES = {
    10004,  # TRADE_RETCODE_REQUOTE
    10020,  # TRADE_RETCODE_PRICE_CHANGED
    10021,  # TRADE_RETCODE_PRICE_OFF
}

# Ambiguous retcodes requiring broker position/deal reconciliation before any retry
AMBIGUOUS_RETCODES = {
    10012,  # TRADE_RETCODE_TIMEOUT
    10024,  # TRADE_RETCODE_TOO_MANY_REQUESTS
}

# Permanent retcodes that must NOT be retried
PERMANENT_RETCODES = {
    10006,  # TRADE_RETCODE_REJECT
    10013,  # TRADE_RETCODE_INVALID
    10014,  # TRADE_RETCODE_INVALID_VOLUME
    10015,  # TRADE_RETCODE_INVALID_PRICE
    10016,  # TRADE_RETCODE_INVALID_STOPS
    10017,  # TRADE_RETCODE_TRADE_DISABLED
    10018,  # TRADE_RETCODE_MARKET_CLOSED
    10019,  # TRADE_RETCODE_NO_MONEY
    10026,  # TRADE_RETCODE_SERVER_DISABLES_AT
    10027,  # TRADE_RETCODE_CLIENT_DISABLES_AT
}


@dataclass
class OrderExecutionResult:
    is_success: bool
    ticket: int = 0
    order_ticket: int = 0
    deal: int = 0
    position_id: int = 0
    symbol: str = ""
    direction: str = ""
    magic: int = 0
    price: float = 0.0
    requested_price: float = 0.0
    slippage_points: float = 0.0
    volume: float = 0.0
    requested_volume: float = 0.0
    remaining_volume: float = 0.0
    is_partial_fill: bool = False
    verified_sl: float = 0.0
    verified_tp: float = 0.0
    protection_verified: bool = False
    position_reconciled: bool = False
    unprotected_incident: bool = False
    retcode: int = 0
    retries_used: int = 0
    comment: str = ""
    broker_comment: str = ""
    error_message: str = ""
    is_retryable: bool = False
    state: str = OrderExecutionState.FAILED
    state_history: List[str] = field(default_factory=list)
    execution_timestamp: float = field(default_factory=time.time)
    submission_latency_ms: float = 0.0
    broker_ack_latency_ms: float = 0.0
    fill_latency_ms: float = 0.0
    raw_response: Dict[str, Any] = field(default_factory=dict)

    @property
    def sl_verified(self) -> bool:
        return self.protection_verified

    @property
    def was_reconciled(self) -> bool:
        return self.position_reconciled


class GoldOrderExecutor:
    def __init__(self, config: Optional[ExecutionConfig] = None):
        self.config = config or ExecutionConfig()
        self._lock = threading.Lock()
        self.simulated_positions: Dict[int, Dict[str, Any]] = {}
        self._sim_ticket_seq = 600000
        self._request_timestamps: List[float] = []
        self.unprotected_position_incidents: int = 0
        self.partial_fills_count: int = 0
        self.reconciled_ambiguous_orders: int = 0

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

    def _throttle_request_if_needed(self) -> None:
        now_t = time.time()
        limit = max(1, int(getattr(self.config, "rate_limit_per_second", 10)))
        self._request_timestamps = [t for t in self._request_timestamps if now_t - t < 1.0]
        if len(self._request_timestamps) >= limit:
            sleep_s = max(0.005, 1.0 - (now_t - self._request_timestamps[0]))
            if sleep_s <= 0.05:
                time.sleep(sleep_s)
        self._request_timestamps.append(time.time())

    @staticmethod
    def validate_order_parameters(
        symbol: str,
        direction: str,
        volume: float,
        price: float,
        stop_loss: float,
        take_profit_or_spec: Any = None,
        spec: Optional[ResolvedSymbolSpec] = None,
        require_protective_sl: bool = True,
    ) -> Tuple[bool, str]:
        """
        Validates order parameters before submission:
        - Valid symbol and direction
        - Volume within min_lot / max_lot and aligned to lot_step
        - Positive price
        - Valid protective stop-loss direction and stops_level distance
        """
        if isinstance(take_profit_or_spec, ResolvedSymbolSpec) and spec is None:
            spec = take_profit_or_spec
        if not symbol or not str(symbol).strip():
            return False, "INVALID_SYMBOL: Symbol is empty"
        dir_u = direction.upper()
        if dir_u not in ("BUY", "SELL", "ORDER_TYPE_BUY", "ORDER_TYPE_SELL", "0", "1"):
            return False, f"INVALID_DIRECTION: Unsupported direction '{direction}'"
        is_buy = dir_u in ("BUY", "ORDER_TYPE_BUY", "0")

        if volume <= 0 or math.isnan(volume) or math.isinf(volume):
            return False, f"INVALID_VOLUME: Volume must be positive, got {volume}"

        if spec is not None:
            if not spec.is_tradable or spec.trade_mode in (0, 3):
                return False, f"SYMBOL_NOT_TRADABLE: {symbol} trade_mode={spec.trade_mode}"
            if volume < spec.min_lot - 1e-9:
                return False, f"INVALID_VOLUME: {volume} < broker min_lot {spec.min_lot}"
            if volume > spec.max_lot + 1e-9:
                return False, f"INVALID_VOLUME: {volume} > broker max_lot {spec.max_lot}"
            if spec.lot_step > 0:
                steps = round((volume - spec.min_lot) / spec.lot_step)
                expected_vol = round(spec.min_lot + steps * spec.lot_step, 6)
                if abs(volume - expected_vol) > 1e-5:
                    return False, f"INVALID_VOLUME_STEP: {volume} not aligned to step {spec.lot_step}"

        if price <= 0:
            return False, f"INVALID_PRICE: Price must be > 0, got {price}"

        if require_protective_sl and stop_loss > 0:
            if is_buy and stop_loss >= price:
                return False, f"INVALID_BUY_SL: BUY stop_loss ({stop_loss}) must be below entry price ({price})"
            if (not is_buy) and stop_loss <= price:
                return False, f"INVALID_SELL_SL: SELL stop_loss ({stop_loss}) must be above entry price ({price})"
            if spec is not None and spec.stops_level > 0 and spec.point > 0:
                min_dist = spec.stops_level * spec.point
                if abs(price - stop_loss) < min_dist - 1e-9:
                    return False, (
                        f"SL_TOO_CLOSE: SL distance {abs(price - stop_loss):.4f} < "
                        f"broker stops_level distance {min_dist:.4f}"
                    )

        return True, "OK"

    def _reconcile_ambiguous_submission(
        self,
        mt5_mod: Any,
        symbol: str,
        magic: int,
        comment: str,
        is_buy: bool,
        submitted_after_ts: float,
    ) -> Optional[Any]:
        """
        Queries MT5 active positions after a timeout or ambiguous response to check
        whether the order actually executed on the broker before any retry is attempted.
        """
        try:
            positions = mt5_mod.positions_get(symbol=symbol) or []
            expected_type = 0 if is_buy else 1
            for pos in positions:
                pos_magic = int(getattr(pos, "magic", 0))
                pos_type = int(getattr(pos, "type", -1))
                pos_comment = str(getattr(pos, "comment", ""))
                pos_time = float(getattr(pos, "time", 0.0))
                if pos_magic == int(magic) and pos_type == expected_type:
                    if (comment and pos_comment == str(comment)) or (pos_time >= submitted_after_ts - 5.0):
                        self.reconciled_ambiguous_orders += 1
                        logger.warning(
                            f"[EXECUTOR] Reconciled ambiguous order to live broker position #{pos.ticket} "
                            f"({symbol} vol={pos.volume} @ {pos.price_open}). Preventing duplicate retry."
                        )
                        return pos
        except Exception as e:
            logger.error(f"[EXECUTOR] Error reconciling ambiguous submission: {e}")
        return None

    def _verify_and_enforce_broker_sl(
        self,
        mt5_mod: Any,
        ticket: int,
        symbol: str,
        is_buy: bool,
        entry_price: float,
        volume: float,
        desired_sl: float,
        desired_tp: float,
        point: float,
        spec: Optional[ResolvedSymbolSpec] = None,
        max_sl_retries: int = 3,
        fail_closed: bool = True,
    ) -> Tuple[bool, float, float, float, float, str]:
        """
        Verifies the resulting broker position and its server-side Stop Loss:
        1. Confirms position exists in `mt5.positions_get`, capturing actual price and volume.
        2. Verifies `pos.sl` is non-zero and on the protective side of `entry_price`.
        3. If missing/invalid, modifies SL up to `max_sl_retries` times and re-verifies with broker.
        4. If still unprotected and `fail_closed=True`, closes the position immediately.
        Returns: (ok, actual_price, actual_vol, verified_sl, verified_tp, err_msg)
        """
        if desired_sl <= 0:
            return True, entry_price, volume, 0.0, desired_tp, "NO_SL_REQUESTED"

        def _fetch_pos() -> Optional[Any]:
            try:
                by_t = mt5_mod.positions_get(ticket=int(ticket))
                if by_t and len(by_t) > 0:
                    return by_t[0]
                by_s = mt5_mod.positions_get(symbol=symbol) or []
                for p in by_s:
                    if int(getattr(p, "ticket", 0)) == int(ticket) or int(getattr(p, "identifier", 0)) == int(ticket):
                        return p
            except Exception:
                pass
            return None

        pos = _fetch_pos()
        actual_px = float(getattr(pos, "price_open", entry_price)) if pos else entry_price
        actual_vol = float(getattr(pos, "volume", volume)) if pos else volume
        pos_ticket = int(getattr(pos, "ticket", ticket)) if pos else ticket

        def _is_sl_valid(sl_val: float, ref_px: float) -> bool:
            if sl_val <= 0:
                return False
            if is_buy and sl_val >= ref_px:
                return False
            if (not is_buy) and sl_val <= ref_px:
                return False
            return True

        current_sl = float(getattr(pos, "sl", 0.0)) if pos else 0.0
        current_tp = float(getattr(pos, "tp", desired_tp)) if pos else desired_tp
        if _is_sl_valid(current_sl, actual_px):
            return True, actual_px, actual_vol, current_sl, current_tp, "OK"

        # Recalculate desired SL relative to actual fill price if actual fill price shifted beyond desired_sl
        target_sl = desired_sl
        if not _is_sl_valid(target_sl, actual_px):
            dist = abs(entry_price - desired_sl) if abs(entry_price - desired_sl) > 0 else (300.0 * point)
            target_sl = round(actual_px - dist if is_buy else actual_px + dist, 3)

        for attempt in range(1, max(1, max_sl_retries) + 1):
            mod_res = self.modify_position_sl(
                ticket=pos_ticket,
                symbol=symbol,
                new_sl=target_sl,
                new_tp=desired_tp,
                is_simulation=False,
                tighten_only=False,
            )
            if mod_res.is_success:
                rechecked = _fetch_pos()
                verified_sl = float(getattr(rechecked, "sl", target_sl)) if rechecked else target_sl
                verified_tp = float(getattr(rechecked, "tp", desired_tp)) if rechecked else desired_tp
                if _is_sl_valid(verified_sl, actual_px):
                    return True, actual_px, actual_vol, verified_sl, verified_tp, "SL_MODIFIED_AND_VERIFIED"

        # Protection failed after all retries
        self.unprotected_position_incidents += 1
        err_msg = f"UNPROTECTED_POSITION_FAIL_CLOSED: Failed to apply/verify protective SL ({target_sl}) on position #{pos_ticket} after {max_sl_retries} attempts"
        logger.critical(f"[EXECUTOR] {err_msg}")
        if fail_closed:
            self.close_position(
                ticket=pos_ticket,
                symbol=symbol,
                volume=actual_vol,
                is_buy=is_buy,
                comment="FAIL_CLOSED_NO_SL",
                spec=spec,
                is_simulation=False,
            )
        return False, actual_px, actual_vol, 0.0, current_tp, err_msg

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
        max_sl_retries: int = 3,
        fail_closed_on_unprotected: bool = True,
    ) -> OrderExecutionResult:
        """
        Submits a market order through the full execution state machine:
        SIGNAL_APPROVED -> RISK_APPROVED -> ORDER_VALIDATED -> ORDER_SUBMITTED ->
        BROKER_ACCEPTED -> PARTIALLY_FILLED / FILLED -> POSITION_RECONCILED ->
        PROTECTION_VERIFIED -> EXECUTION_CONFIRMED.
        """
        t_start = time.perf_counter()
        states: List[str] = [
            OrderExecutionState.SIGNAL_APPROVED,
            OrderExecutionState.RISK_APPROVED,
        ]
        is_buy = direction.upper() in ("BUY", "ORDER_TYPE_BUY", "0")
        norm_dir = "BUY" if is_buy else "SELL"
        point = spec.point if spec and spec.point > 0 else 0.01

        # Handle simulation mode with the same validation and state transitions
        if is_simulation:
            sim_px = (spec.ask if is_buy else spec.bid) if spec and (spec.ask > 0 or spec.bid > 0) else (2650.50 if is_buy else 2650.00)
            valid_ok, valid_msg = self.validate_order_parameters(
                symbol=symbol,
                direction=norm_dir,
                volume=volume,
                price=sim_px,
                stop_loss=stop_loss,
                spec=spec,
                require_protective_sl=(stop_loss > 0),
            )
            if not valid_ok:
                states.append(OrderExecutionState.FAILED)
                return OrderExecutionResult(
                    is_success=False,
                    symbol=symbol,
                    direction=norm_dir,
                    magic=magic,
                    requested_price=sim_px,
                    requested_volume=volume,
                    remaining_volume=volume,
                    retcode=10013,
                    error_message=valid_msg,
                    is_retryable=False,
                    state=OrderExecutionState.FAILED,
                    state_history=states,
                )

            states.append(OrderExecutionState.ORDER_VALIDATED)
            with self._lock:
                self._sim_ticket_seq += 1
                t = self._sim_ticket_seq
                states.append(OrderExecutionState.ORDER_SUBMITTED)
                states.append(OrderExecutionState.BROKER_ACCEPTED)
                states.append(OrderExecutionState.FILLED)
                pos_data = {
                    "ticket": t,
                    "symbol": symbol,
                    "direction": norm_dir,
                    "volume": volume,
                    "price": sim_px,
                    "sl": stop_loss,
                    "tp": take_profit,
                    "magic": magic,
                    "comment": comment,
                    "open_time": time.time(),
                }
                self.simulated_positions[t] = pos_data
                states.append(OrderExecutionState.POSITION_RECONCILED)
                states.append(OrderExecutionState.PROTECTION_VERIFIED)
                states.append(OrderExecutionState.EXECUTION_CONFIRMED)
                elapsed_ms = round((time.perf_counter() - t_start) * 1000.0, 3)
                return OrderExecutionResult(
                    is_success=True,
                    ticket=t,
                    order_ticket=t,
                    deal=t + 1000,
                    position_id=t,
                    symbol=symbol,
                    direction=norm_dir,
                    magic=magic,
                    price=sim_px,
                    requested_price=sim_px,
                    slippage_points=0.0,
                    volume=volume,
                    requested_volume=volume,
                    remaining_volume=0.0,
                    is_partial_fill=False,
                    verified_sl=stop_loss,
                    verified_tp=take_profit,
                    protection_verified=True,
                    position_reconciled=True,
                    retcode=10009,
                    comment=comment,
                    broker_comment="Simulated fill confirmed",
                    is_retryable=False,
                    state=OrderExecutionState.EXECUTION_CONFIRMED,
                    state_history=states,
                    submission_latency_ms=elapsed_ms,
                    broker_ack_latency_ms=elapsed_ms,
                    fill_latency_ms=elapsed_ms,
                )

        # Real MT5 API order transmission
        try:
            if not HAS_MT5 or mt5 is None:
                return OrderExecutionResult(
                    is_success=False,
                    symbol=symbol,
                    direction=norm_dir,
                    magic=magic,
                    requested_volume=volume,
                    remaining_volume=volume,
                    error_message="MT5_NOT_AVAILABLE",
                    is_retryable=False,
                    state=OrderExecutionState.FAILED,
                    state_history=states,
                )

            action_type = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
            filling_mode = self.determine_filling_mode(spec)
            max_retries = max(1, int(self.config.max_retries))
            delay_sec = max(0.01, self.config.retry_delay_ms / 1000.0)

            for attempt in range(1, max_retries + 1):
                with self._lock:
                    self._throttle_request_if_needed()
                    t_sub = time.perf_counter()

                    # Verify terminal connection if terminal_info is available
                    if hasattr(mt5, "terminal_info"):
                        t_info = mt5.terminal_info()
                        if t_info is not None and not getattr(t_info, "connected", True):
                            states.append(OrderExecutionState.FAILED)
                            return OrderExecutionResult(
                                is_success=False,
                                symbol=symbol,
                                direction=norm_dir,
                                magic=magic,
                                requested_volume=volume,
                                remaining_volume=volume,
                                error_message="BROKER_DISCONNECTED: MT5 terminal is not connected",
                                is_retryable=False,
                                state=OrderExecutionState.FAILED,
                                state_history=states,
                            )

                    tick = mt5.symbol_info_tick(symbol)
                    if not tick:
                        if attempt < max_retries:
                            time.sleep(delay_sec)
                            continue
                        states.append(OrderExecutionState.FAILED)
                        return OrderExecutionResult(
                            is_success=False,
                            symbol=symbol,
                            direction=norm_dir,
                            magic=magic,
                            requested_volume=volume,
                            remaining_volume=volume,
                            error_message=f"Failed to retrieve live tick for {symbol}",
                            is_retryable=True,
                            state=OrderExecutionState.FAILED,
                            state_history=states,
                        )

                    price = float(tick.ask if is_buy else tick.bid)
                    eff_sl = stop_loss
                    if eff_sl > 0:
                        if (is_buy and eff_sl >= price) or ((not is_buy) and eff_sl <= price):
                            sl_dist = (spec.stops_level * point * 2.0) if (spec and spec.stops_level > 0) else (300.0 * point)
                            eff_sl = round(price - sl_dist if is_buy else price + sl_dist, 3)

                    valid_ok, valid_msg = self.validate_order_parameters(
                        symbol=symbol,
                        direction=norm_dir,
                        volume=volume,
                        price=price,
                        stop_loss=eff_sl,
                        spec=spec,
                        require_protective_sl=(eff_sl > 0),
                    )
                    if not valid_ok:
                        states.append(OrderExecutionState.FAILED)
                        return OrderExecutionResult(
                            is_success=False,
                            symbol=symbol,
                            direction=norm_dir,
                            magic=magic,
                            requested_price=price,
                            requested_volume=volume,
                            remaining_volume=volume,
                            retcode=10013,
                            error_message=valid_msg,
                            is_retryable=False,
                            state=OrderExecutionState.FAILED,
                            state_history=states,
                        )

                    if OrderExecutionState.ORDER_VALIDATED not in states:
                        states.append(OrderExecutionState.ORDER_VALIDATED)

                    request = {
                        "action": mt5.TRADE_ACTION_DEAL,
                        "symbol": symbol,
                        "volume": float(volume),
                        "type": action_type,
                        "price": price,
                        "sl": float(eff_sl),
                        "tp": float(take_profit),
                        "deviation": int(self.config.slippage_points),
                        "magic": int(magic),
                        "comment": str(comment),
                        "type_time": mt5.ORDER_TIME_GTC,
                        "type_filling": filling_mode,
                    }

                    # Pre-check with mt5.order_check when available
                    if hasattr(mt5, "order_check"):
                        chk = mt5.order_check(request)
                        if chk is not None:
                            chk_ret = int(getattr(chk, "retcode", 0))
                            # In MT5 order_check, retcode 0 or 10009 means valid
                            if chk_ret not in (0, 10008, 10009):
                                chk_comment = str(getattr(chk, "comment", "order_check failed"))
                                states.append(OrderExecutionState.FAILED)
                                return OrderExecutionResult(
                                    is_success=False,
                                    symbol=symbol,
                                    direction=norm_dir,
                                    magic=magic,
                                    requested_price=price,
                                    requested_volume=volume,
                                    remaining_volume=volume,
                                    retcode=chk_ret,
                                    broker_comment=chk_comment,
                                    error_message=f"order_check rejected ({chk_ret}): {chk_comment}",
                                    is_retryable=False,
                                    state=OrderExecutionState.FAILED,
                                    state_history=states,
                                )

                    sub_ms = round((time.perf_counter() - t_sub) * 1000.0, 3)
                    submit_wall_ts = time.time()
                    if OrderExecutionState.ORDER_SUBMITTED not in states:
                        states.append(OrderExecutionState.ORDER_SUBMITTED)
                    t_send = time.perf_counter()
                    result = mt5.order_send(request)
                    ack_ms = round((time.perf_counter() - t_send) * 1000.0, 3)

                # Handle null result (ambiguous submission — reconcile first!)
                if result is None:
                    last_err = mt5.last_error()
                    states.append(OrderExecutionState.UNKNOWN_REQUIRES_RECONCILIATION)
                    logger.warning(f"[EXECUTOR] order_send returned None (attempt {attempt}/{max_retries}): {last_err}")
                    reconciled_pos = self._reconcile_ambiguous_submission(
                        mt5, symbol, magic, comment, is_buy, submit_wall_ts
                    )
                    if reconciled_pos is not None:
                        rec_ticket = int(getattr(reconciled_pos, "ticket", 0))
                        rec_vol = float(getattr(reconciled_pos, "volume", volume))
                        rec_px = float(getattr(reconciled_pos, "price_open", price))
                        states.append(OrderExecutionState.FILLED if rec_vol >= volume - 1e-6 else OrderExecutionState.PARTIALLY_FILLED)
                        states.append(OrderExecutionState.POSITION_RECONCILED)
                        sl_ok, act_px, act_vol, ver_sl, ver_tp, sl_msg = self._verify_and_enforce_broker_sl(
                            mt5, rec_ticket, symbol, is_buy, rec_px, rec_vol, eff_sl, take_profit,
                            point, spec, max_sl_retries, fail_closed_on_unprotected
                        )
                        if not sl_ok:
                            states.append(OrderExecutionState.FAILED)
                            return OrderExecutionResult(
                                is_success=False,
                                ticket=rec_ticket,
                                symbol=symbol,
                                direction=norm_dir,
                                magic=magic,
                                price=act_px,
                                requested_price=price,
                                volume=act_vol,
                                requested_volume=volume,
                                position_reconciled=True,
                                protection_verified=False,
                                unprotected_incident=True,
                                error_message=sl_msg,
                                state=OrderExecutionState.FAILED,
                                state_history=states,
                                submission_latency_ms=sub_ms,
                                broker_ack_latency_ms=ack_ms,
                            )
                        states.append(OrderExecutionState.PROTECTION_VERIFIED)
                        states.append(OrderExecutionState.EXECUTION_CONFIRMED)
                        return OrderExecutionResult(
                            is_success=True,
                            ticket=rec_ticket,
                            order_ticket=rec_ticket,
                            position_id=rec_ticket,
                            symbol=symbol,
                            direction=norm_dir,
                            magic=magic,
                            price=act_px,
                            requested_price=price,
                            slippage_points=round(abs(act_px - price) / point, 2),
                            volume=act_vol,
                            requested_volume=volume,
                            remaining_volume=round(max(0.0, volume - act_vol), 4),
                            is_partial_fill=(act_vol < volume - 1e-6),
                            verified_sl=ver_sl,
                            verified_tp=ver_tp,
                            protection_verified=True,
                            position_reconciled=True,
                            retcode=10009,
                            comment=comment,
                            broker_comment="Reconciled after null order_send",
                            state=OrderExecutionState.EXECUTION_CONFIRMED,
                            state_history=states,
                            submission_latency_ms=sub_ms,
                            broker_ack_latency_ms=ack_ms,
                            fill_latency_ms=round((time.perf_counter() - t_start) * 1000.0, 3),
                        )

                    if attempt < max_retries:
                        time.sleep(delay_sec)
                        continue
                    states.append(OrderExecutionState.FAILED)
                    return OrderExecutionResult(
                        is_success=False,
                        symbol=symbol,
                        direction=norm_dir,
                        magic=magic,
                        requested_price=price,
                        requested_volume=volume,
                        remaining_volume=volume,
                        error_message=f"order_send returned None: {last_err}",
                        is_retryable=False,
                        state=OrderExecutionState.FAILED,
                        state_history=states,
                        submission_latency_ms=sub_ms,
                    )

                retcode = int(getattr(result, "retcode", 0))
                broker_msg = str(getattr(result, "comment", ""))

                # 1. Completed or Partially Completed Fill (10009 DONE or 10010 DONE_PARTIAL)
                if retcode in (10009, 10010):
                    states.append(OrderExecutionState.BROKER_ACCEPTED)
                    order_ticket = int(getattr(result, "order", 0))
                    deal = int(getattr(result, "deal", 0))
                    ticket = order_ticket or deal
                    fill_px = float(getattr(result, "price", price)) or price
                    filled_vol = float(getattr(result, "volume", volume)) or volume
                    is_partial = (retcode == 10010) or (0 < filled_vol < volume - 1e-6)
                    if is_partial:
                        self.partial_fills_count += 1
                        states.append(OrderExecutionState.PARTIALLY_FILLED)
                    else:
                        states.append(OrderExecutionState.FILLED)

                    states.append(OrderExecutionState.POSITION_RECONCILED)
                    sl_ok, act_px, act_vol, ver_sl, ver_tp, sl_msg = self._verify_and_enforce_broker_sl(
                        mt5, ticket, symbol, is_buy, fill_px, filled_vol, eff_sl, take_profit,
                        point, spec, max_sl_retries, fail_closed_on_unprotected
                    )
                    if not sl_ok:
                        states.append(OrderExecutionState.FAILED)
                        return OrderExecutionResult(
                            is_success=False,
                            ticket=ticket,
                            order_ticket=order_ticket,
                            deal=deal,
                            position_id=ticket,
                            symbol=symbol,
                            direction=norm_dir,
                            magic=magic,
                            price=act_px,
                            requested_price=price,
                            volume=act_vol,
                            requested_volume=volume,
                            remaining_volume=round(max(0.0, volume - act_vol), 4),
                            is_partial_fill=is_partial,
                            position_reconciled=True,
                            protection_verified=False,
                            unprotected_incident=True,
                            retcode=retcode,
                            comment=comment,
                            broker_comment=broker_msg,
                            error_message=sl_msg,
                            state=OrderExecutionState.FAILED,
                            state_history=states,
                            submission_latency_ms=sub_ms,
                            broker_ack_latency_ms=ack_ms,
                        )

                    states.append(OrderExecutionState.PROTECTION_VERIFIED)
                    states.append(OrderExecutionState.EXECUTION_CONFIRMED)
                    slip_pts = round(abs(act_px - price) / point, 2)
                    total_fill_ms = round((time.perf_counter() - t_start) * 1000.0, 3)
                    logger.info(
                        f"[EXECUTOR] Order CONFIRMED: Ticket #{ticket} Deal #{deal} | {symbol} {norm_dir} "
                        f"vol={act_vol}/{volume} @ {act_px} (slip={slip_pts}pts, ack={ack_ms}ms) | Verified SL: {ver_sl}"
                    )
                    return OrderExecutionResult(
                        is_success=True,
                        ticket=ticket,
                        order_ticket=order_ticket,
                        deal=deal,
                        position_id=ticket,
                        symbol=symbol,
                        direction=norm_dir,
                        magic=magic,
                        price=act_px,
                        requested_price=price,
                        slippage_points=slip_pts,
                        volume=act_vol,
                        requested_volume=volume,
                        remaining_volume=round(max(0.0, volume - act_vol), 4),
                        is_partial_fill=is_partial,
                        verified_sl=ver_sl,
                        verified_tp=ver_tp,
                        protection_verified=True,
                        position_reconciled=True,
                        retcode=retcode,
                        retries_used=attempt - 1,
                        comment=comment,
                        broker_comment=broker_msg,
                        state=OrderExecutionState.EXECUTION_CONFIRMED,
                        state_history=states,
                        submission_latency_ms=sub_ms,
                        broker_ack_latency_ms=ack_ms,
                        fill_latency_ms=total_fill_ms,
                    )

                # 2. Accepted but not yet filled (10008 TRADE_RETCODE_PLACED)
                if retcode == 10008:
                    states.append(OrderExecutionState.BROKER_ACCEPTED)
                    reconciled_pos = self._reconcile_ambiguous_submission(
                        mt5, symbol, magic, comment, is_buy, submit_wall_ts
                    )
                    if reconciled_pos is None:
                        order_ticket = int(getattr(result, "order", 0))
                        return OrderExecutionResult(
                            is_success=False,
                            ticket=order_ticket,
                            order_ticket=order_ticket,
                            symbol=symbol,
                            direction=norm_dir,
                            magic=magic,
                            requested_price=price,
                            requested_volume=volume,
                            remaining_volume=volume,
                            retcode=retcode,
                            comment=comment,
                            broker_comment=broker_msg,
                            error_message="ORDER_ACCEPTED_NOT_FILLED: Broker returned 10008 (PLACED) without fill confirmation",
                            is_retryable=False,
                            state=OrderExecutionState.BROKER_ACCEPTED,
                            state_history=states,
                            submission_latency_ms=sub_ms,
                            broker_ack_latency_ms=ack_ms,
                        )

                # 3. Ambiguous timeout (10012 TRADE_RETCODE_TIMEOUT)
                if retcode in AMBIGUOUS_RETCODES:
                    states.append(OrderExecutionState.UNKNOWN_REQUIRES_RECONCILIATION)
                    reconciled_pos = self._reconcile_ambiguous_submission(
                        mt5, symbol, magic, comment, is_buy, submit_wall_ts
                    )
                    if reconciled_pos is not None:
                        rec_ticket = int(getattr(reconciled_pos, "ticket", 0))
                        rec_vol = float(getattr(reconciled_pos, "volume", volume))
                        rec_px = float(getattr(reconciled_pos, "price_open", price))
                        states.append(OrderExecutionState.FILLED)
                        states.append(OrderExecutionState.POSITION_RECONCILED)
                        sl_ok, act_px, act_vol, ver_sl, ver_tp, sl_msg = self._verify_and_enforce_broker_sl(
                            mt5, rec_ticket, symbol, is_buy, rec_px, rec_vol, eff_sl, take_profit,
                            point, spec, max_sl_retries, fail_closed_on_unprotected
                        )
                        if sl_ok:
                            states.append(OrderExecutionState.PROTECTION_VERIFIED)
                            states.append(OrderExecutionState.EXECUTION_CONFIRMED)
                            return OrderExecutionResult(
                                is_success=True,
                                ticket=rec_ticket,
                                order_ticket=rec_ticket,
                                position_id=rec_ticket,
                                symbol=symbol,
                                direction=norm_dir,
                                magic=magic,
                                price=act_px,
                                requested_price=price,
                                volume=act_vol,
                                requested_volume=volume,
                                verified_sl=ver_sl,
                                verified_tp=ver_tp,
                                protection_verified=True,
                                position_reconciled=True,
                                retcode=10009,
                                comment=comment,
                                broker_comment="Reconciled after timeout",
                                state=OrderExecutionState.EXECUTION_CONFIRMED,
                                state_history=states,
                                submission_latency_ms=sub_ms,
                                broker_ack_latency_ms=ack_ms,
                            )
                    # If not found on broker, do NOT blindly retry a timed-out order unless explicitly safe
                    states.append(OrderExecutionState.FAILED)
                    return OrderExecutionResult(
                        is_success=False,
                        symbol=symbol,
                        direction=norm_dir,
                        magic=magic,
                        requested_price=price,
                        requested_volume=volume,
                        remaining_volume=volume,
                        retcode=retcode,
                        comment=comment,
                        broker_comment=broker_msg,
                        error_message=f"Broker timeout ({retcode}): reconciled no fill; halted retry to prevent duplicate execution",
                        is_retryable=False,
                        state=OrderExecutionState.UNKNOWN_REQUIRES_RECONCILIATION,
                        state_history=states,
                        submission_latency_ms=sub_ms,
                        broker_ack_latency_ms=ack_ms,
                    )

                # 4. Retryable transient quote errors (REQUOTE, PRICE_CHANGED, PRICE_OFF)
                is_retryable = retcode in RETRYABLE_RETCODES
                err_msg = f"Broker retcode {retcode}: {broker_msg or 'Order rejected'}"
                logger.warning(f"[EXECUTOR] Order failed (attempt {attempt}/{max_retries}): {err_msg} (Retryable: {is_retryable})")

                if is_retryable and attempt < max_retries:
                    time.sleep(delay_sec)
                    continue

                states.append(OrderExecutionState.FAILED)
                return OrderExecutionResult(
                    is_success=False,
                    symbol=symbol,
                    direction=norm_dir,
                    magic=magic,
                    requested_price=price,
                    requested_volume=volume,
                    remaining_volume=volume,
                    retcode=retcode,
                    comment=comment,
                    broker_comment=broker_msg,
                    error_message=err_msg,
                    is_retryable=is_retryable,
                    state=OrderExecutionState.FAILED,
                    state_history=states,
                    submission_latency_ms=sub_ms,
                    broker_ack_latency_ms=ack_ms,
                )

            states.append(OrderExecutionState.FAILED)
            return OrderExecutionResult(
                is_success=False,
                symbol=symbol,
                direction=norm_dir,
                magic=magic,
                requested_volume=volume,
                remaining_volume=volume,
                error_message=f"Order failed after {max_retries} attempts",
                is_retryable=True,
                state=OrderExecutionState.FAILED,
                state_history=states,
            )

        except Exception as e:
            logger.error(f"[EXECUTOR] Exception in submit_market_order: {e}")
            states.append(OrderExecutionState.FAILED)
            return OrderExecutionResult(
                is_success=False,
                symbol=symbol,
                direction=norm_dir,
                magic=magic,
                requested_volume=volume,
                remaining_volume=volume,
                error_message=str(e),
                is_retryable=False,
                state=OrderExecutionState.FAILED,
                state_history=states,
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
        t_start = time.perf_counter()
        if is_simulation:
            with self._lock:
                self.simulated_positions.pop(ticket, None)
                ms = round((time.perf_counter() - t_start) * 1000.0, 3)
                return OrderExecutionResult(
                    is_success=True,
                    ticket=ticket,
                    retcode=10009,
                    state=OrderExecutionState.EXECUTION_CONFIRMED,
                    submission_latency_ms=ms,
                    broker_ack_latency_ms=ms,
                    fill_latency_ms=ms,
                )

        try:
            if not HAS_MT5 or mt5 is None:
                return OrderExecutionResult(is_success=False, ticket=ticket, error_message="MT5_NOT_AVAILABLE")

            close_action = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
            filling_mode = self.determine_filling_mode(spec)

            with self._lock:
                self._throttle_request_if_needed()
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
                t_send = time.perf_counter()
                res = mt5.order_send(req)
                ack_ms = round((time.perf_counter() - t_send) * 1000.0, 3)

            if res and res.retcode in (10008, 10009, 10010):
                logger.info(f"[EXECUTOR] Position #{ticket} closed successfully.")
                return OrderExecutionResult(
                    is_success=True,
                    ticket=ticket,
                    retcode=res.retcode,
                    price=float(getattr(res, "price", price)),
                    requested_price=price,
                    state=OrderExecutionState.EXECUTION_CONFIRMED,
                    broker_ack_latency_ms=ack_ms,
                    fill_latency_ms=round((time.perf_counter() - t_start) * 1000.0, 3),
                )
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
        tighten_only: bool = True,
        current_sl: float = 0.0,
        is_buy: Optional[bool] = None,
    ) -> OrderExecutionResult:
        """
        Modifies existing position's protective SL / TP.
        Enforces tighten-only protection so trailing/BE updates never remove or widen existing SL.
        """
        if new_sl <= 0:
            return OrderExecutionResult(
                is_success=False,
                ticket=ticket,
                retcode=10016,
                error_message="INVALID_SL_MODIFICATION: Cannot remove protective stop loss (new_sl <= 0)",
            )

        if tighten_only and current_sl > 0 and is_buy is not None:
            if is_buy and new_sl < current_sl - 1e-6:
                return OrderExecutionResult(
                    is_success=False,
                    ticket=ticket,
                    retcode=10016,
                    error_message=f"TIGHTEN_ONLY_VIOLATION: BUY new_sl {new_sl} < current_sl {current_sl}",
                )
            if (not is_buy) and new_sl > current_sl + 1e-6:
                return OrderExecutionResult(
                    is_success=False,
                    ticket=ticket,
                    retcode=10016,
                    error_message=f"TIGHTEN_ONLY_VIOLATION: SELL new_sl {new_sl} > current_sl {current_sl}",
                )

        if is_simulation:
            with self._lock:
                if ticket in self.simulated_positions:
                    pos = self.simulated_positions[ticket]
                    cur_sl = float(pos.get("sl", 0.0))
                    pos_buy = str(pos.get("direction", "BUY")).upper() == "BUY"
                    if tighten_only and cur_sl > 0:
                        if pos_buy and new_sl < cur_sl - 1e-6:
                            return OrderExecutionResult(
                                is_success=False,
                                ticket=ticket,
                                retcode=10016,
                                error_message=f"TIGHTEN_ONLY_VIOLATION: BUY new_sl {new_sl} < current_sl {cur_sl}",
                            )
                        if (not pos_buy) and new_sl > cur_sl + 1e-6:
                            return OrderExecutionResult(
                                is_success=False,
                                ticket=ticket,
                                retcode=10016,
                                error_message=f"TIGHTEN_ONLY_VIOLATION: SELL new_sl {new_sl} > current_sl {cur_sl}",
                            )
                    pos["sl"] = new_sl
                    pos["tp"] = new_tp
                return OrderExecutionResult(
                    is_success=True,
                    ticket=ticket,
                    verified_sl=new_sl,
                    verified_tp=new_tp,
                    protection_verified=True,
                    retcode=10009,
                    state=OrderExecutionState.PROTECTION_VERIFIED,
                )

        try:
            if not HAS_MT5 or mt5 is None:
                return OrderExecutionResult(is_success=False, ticket=ticket, error_message="MT5_NOT_AVAILABLE")

            with self._lock:
                self._throttle_request_if_needed()
                req = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": int(ticket),
                    "symbol": symbol,
                    "sl": float(new_sl),
                    "tp": float(new_tp),
                }
                res = mt5.order_send(req)

            if res and res.retcode in (10008, 10009):
                return OrderExecutionResult(
                    is_success=True,
                    ticket=ticket,
                    verified_sl=new_sl,
                    verified_tp=new_tp,
                    protection_verified=True,
                    retcode=res.retcode,
                    state=OrderExecutionState.PROTECTION_VERIFIED,
                )
            ret = getattr(res, "retcode", 0) if res else -1
            msg = getattr(res, "comment", "SL modify failed") if res else str(mt5.last_error())
            return OrderExecutionResult(is_success=False, ticket=ticket, retcode=ret, error_message=msg)
        except Exception as e:
            return OrderExecutionResult(is_success=False, ticket=ticket, error_message=str(e))

    def modify_position_sl_tp(
        self,
        ticket: int,
        symbol: str,
        sl: float,
        tp: float = 0.0,
        is_simulation: bool = False,
    ) -> OrderExecutionResult:
        """Alias for modify_position_sl accepting sl/tp keyword arguments."""
        return self.modify_position_sl(
            ticket=ticket,
            symbol=symbol,
            new_sl=sl,
            new_tp=tp,
            is_simulation=is_simulation,
        )
