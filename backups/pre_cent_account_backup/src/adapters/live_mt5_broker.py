"""
Live MT5 Broker Adapter.
Wraps the low-level BridgeClient to communicate with PythonBridgeEA.mq5 via TCP socket,
and provides native fallback directly to MetaTrader5 Python API when running locally.
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from src.adapters.broker_interface import BrokerAdapter, TradeRequest, OrderResult
from src.core.contracts import AccountInfo, Position, Candle, OrderType
from src.execution.bridge_client import BridgeClient


class LiveMT5Broker(BrokerAdapter):
    """
    MT5 Broker implementation of BrokerAdapter.
    Supports both:
    1. Communication via BridgeClient (TCP socket to PythonBridgeEA).
    2. Direct communication via native MetaTrader5 Python package.
    """

    def __init__(self, bridge_client: Optional[BridgeClient] = None):
        self.bridge = bridge_client
        self._mt5_initialized = False

    def _ensure_direct_mt5(self) -> bool:
        try:
            import MetaTrader5 as mt5
            if not self._mt5_initialized:
                if mt5.initialize():
                    self._mt5_initialized = True
                else:
                    return False
            return True
        except Exception:
            return False

    def ping(self) -> bool:
        if self.bridge is not None:
            return self.bridge.ping()
        if self._ensure_direct_mt5():
            import MetaTrader5 as mt5
            ti = mt5.terminal_info()
            return bool(ti and ti.connected)
        return False

    def is_connected(self) -> bool:
        if self.bridge is not None:
            return self.bridge.is_connected()
        if self._ensure_direct_mt5():
            import MetaTrader5 as mt5
            ti = mt5.terminal_info()
            return bool(ti and ti.connected)
        return False

    def get_account_info(self) -> AccountInfo:
        if self.bridge is not None:
            return self.bridge.get_account_info()
        if self._ensure_direct_mt5():
            import MetaTrader5 as mt5
            acc = mt5.account_info()
            if acc:
                return AccountInfo(
                    account_number=int(acc.login),
                    currency=str(acc.currency),
                    balance=float(acc.balance),
                    equity=float(acc.equity),
                    margin=float(acc.margin),
                    free_margin=float(acc.margin_free),
                    margin_level=float(acc.margin_level) if acc.margin > 0 else 10000.0,
                    leverage=int(acc.leverage),
                )
        return AccountInfo()

    def get_positions(self, symbol: Optional[str] = None) -> List[Position]:
        if self.bridge is not None:
            positions = self.bridge.get_positions()
            if symbol:
                return [p for p in positions if p.symbol == symbol]
            return positions
        if self._ensure_direct_mt5():
            import MetaTrader5 as mt5
            raw_pos = mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
            if not raw_pos:
                return []
            positions: List[Position] = []
            for p in raw_pos:
                ot = OrderType.BUY if p.type == 0 else OrderType.SELL
                positions.append(
                    Position(
                        ticket=int(p.ticket),
                        symbol=str(p.symbol),
                        order_type=ot,
                        volume=float(p.volume),
                        open_price=float(p.price_open),
                        current_price=float(p.price_current),
                        stop_loss=float(p.sl),
                        take_profit=float(p.tp),
                        profit=float(p.profit),
                        magic=int(p.magic),
                        comment=str(p.comment),
                        open_time=datetime.fromtimestamp(p.time, timezone.utc) if p.time else datetime.now(timezone.utc),
                    )
                )
            return positions
        return []

    def get_rates(self, symbol: str, timeframe: str, count: int) -> List[Candle]:
        if self.bridge is not None:
            res = self.bridge.get_rates(symbol=symbol, timeframe=timeframe, count=count)
            if not isinstance(res, dict) or res.get("status") != "SUCCESS":
                return []
            data = res.get("data", [])
            candles: List[Candle] = []
            for item in data:
                try:
                    t_val = item.get("time")
                    if isinstance(t_val, str):
                        t = datetime.fromisoformat(t_val)
                    elif isinstance(t_val, (int, float)):
                        t = datetime.fromtimestamp(t_val, timezone.utc)
                    else:
                        t = datetime.now(timezone.utc)
                    candles.append(
                        Candle(
                            time=t,
                            open=float(item.get("open", 0.0)),
                            high=float(item.get("high", 0.0)),
                            low=float(item.get("low", 0.0)),
                            close=float(item.get("close", 0.0)),
                            tick_volume=int(item.get("tick_volume", 0)),
                            spread=int(item.get("spread", 0)),
                            complete=bool(item.get("complete", True)),
                        )
                    )
                except Exception:
                    continue
            return candles

        if self._ensure_direct_mt5():
            import MetaTrader5 as mt5
            tf_map = {
                "M1": mt5.TIMEFRAME_M1,
                "M5": mt5.TIMEFRAME_M5,
                "M15": mt5.TIMEFRAME_M15,
                "H1": mt5.TIMEFRAME_H1,
                "D1": mt5.TIMEFRAME_D1,
            }
            tf = tf_map.get(timeframe.upper(), mt5.TIMEFRAME_M1)
            rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
            if rates is None:
                return []
            candles = []
            for r in rates:
                candles.append(
                    Candle(
                        time=datetime.fromtimestamp(r["time"], timezone.utc),
                        open=float(r["open"]),
                        high=float(r["high"]),
                        low=float(r["low"]),
                        close=float(r["close"]),
                        tick_volume=int(r["tick_volume"]),
                        spread=int(r["spread"]),
                        complete=True,
                    )
                )
            return candles
        return []

    def send_order(self, request: TradeRequest) -> OrderResult:
        from src.core.symbol_universe import get_symbol_universe
        sym_ok, sym_reason = get_symbol_universe().validate_or_reject(request.symbol)
        if not sym_ok:
            return OrderResult(
                success=False,
                ticket=0,
                deal=0,
                price=request.price,
                volume=request.volume,
                retcode=10016,
                comment=request.comment,
                error_message=sym_reason or f"Unauthorized symbol '{request.symbol}' blocked at LiveMT5Broker.",
                raw_response={"status": "ERROR", "retcode": 10016, "message": sym_reason},
            )

        if self.bridge is not None:
            ot = OrderType.BUY if request.action.upper() == "BUY" else OrderType.SELL
            res = self.bridge.execute_trade(
                symbol=request.symbol,
                order_type=ot,
                volume=request.volume,
                stop_loss=request.sl,
                take_profit=request.tp,
                price=request.price,
                magic=request.magic,
                comment=request.comment
            )
            success = res.get("status") == "SUCCESS"
            return OrderResult(
                success=success,
                ticket=int(res.get("ticket", 0)),
                deal=int(res.get("deal", 0)),
                price=float(res.get("price", request.price)),
                volume=request.volume,
                retcode=int(res.get("retcode", 10009 if success else 10004)),
                comment=request.comment,
                error_message="" if success else str(res.get("message", "Unknown MT5 execution error")),
                raw_response=res
            )

        if self._ensure_direct_mt5():
            import MetaTrader5 as mt5
            action_type = mt5.ORDER_TYPE_BUY if request.action.upper() == "BUY" else mt5.ORDER_TYPE_SELL
            price = request.price
            if price <= 0:
                tick = mt5.symbol_info_tick(request.symbol)
                if tick:
                    price = tick.ask if request.action.upper() == "BUY" else tick.bid

            req_dict = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": request.symbol,
                "volume": float(request.volume),
                "type": action_type,
                "price": float(price),
                "sl": float(request.sl),
                "tp": float(request.tp),
                "deviation": int(request.deviation),
                "magic": int(request.magic),
                "comment": str(request.comment),
                "type_time": mt5.ORDER_TIME_GTC,
            }

            sym_info = mt5.symbol_info(request.symbol)
            if sym_info:
                filling_mode = sym_info.filling_mode
                if filling_mode & 2:
                    req_dict["type_filling"] = mt5.ORDER_FILLING_IOC
                elif filling_mode & 1:
                    req_dict["type_filling"] = mt5.ORDER_FILLING_FOK
                else:
                    req_dict["type_filling"] = mt5.ORDER_FILLING_RETURN
            else:
                req_dict["type_filling"] = mt5.ORDER_FILLING_IOC

            result = mt5.order_send(req_dict)
            if result is None:
                err = mt5.last_error()
                return OrderResult(
                    success=False,
                    ticket=0,
                    error_message=f"mt5.order_send returned None: {err}",
                    raw_response={"error": err},
                )
            success = result.retcode == mt5.TRADE_RETCODE_DONE
            return OrderResult(
                success=success,
                ticket=int(result.order),
                deal=int(result.deal),
                price=float(result.price),
                volume=float(result.volume),
                retcode=int(result.retcode),
                comment=str(result.comment),
                error_message="" if success else f"MT5 Retcode: {result.retcode} ({result.comment})",
                raw_response={"retcode": result.retcode, "comment": result.comment},
            )

        return OrderResult(success=False, error_message="No bridge client and MT5 initialization failed.")

    def modify_order(self, ticket: int, sl: float, tp: float) -> OrderResult:
        if self.bridge is not None:
            res = self.bridge.modify_order(ticket=ticket, sl=sl, tp=tp)
            success = res.get("status") == "SUCCESS"
            return OrderResult(
                success=success,
                ticket=ticket,
                error_message="" if success else str(res.get("message", "Modify failed")),
                raw_response=res
            )
        if self._ensure_direct_mt5():
            import MetaTrader5 as mt5
            positions = mt5.positions_get(ticket=ticket)
            if not positions:
                return OrderResult(success=False, ticket=ticket, error_message=f"Position {ticket} not found.")
            pos = positions[0]
            req_dict = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": int(ticket),
                "symbol": pos.symbol,
                "sl": float(sl),
                "tp": float(tp),
            }
            result = mt5.order_send(req_dict)
            if result is None:
                err = mt5.last_error()
                return OrderResult(success=False, ticket=ticket, error_message=f"Modify returned None: {err}")
            success = result.retcode == mt5.TRADE_RETCODE_DONE
            return OrderResult(
                success=success,
                ticket=int(result.order),
                deal=int(result.deal),
                retcode=int(result.retcode),
                comment=str(result.comment),
                error_message="" if success else f"Modify Retcode: {result.retcode} ({result.comment})",
                raw_response={"retcode": result.retcode, "comment": result.comment},
            )
        return OrderResult(success=False, ticket=ticket, error_message="No bridge and MT5 direct failed.")

    def cancel_order(self, ticket: int) -> OrderResult:
        if self.bridge is not None:
            res = self.bridge.cancel_order(ticket=ticket)
            success = res.get("status") == "SUCCESS"
            return OrderResult(
                success=success,
                ticket=ticket,
                error_message="" if success else str(res.get("message", "Cancel failed")),
                raw_response=res
            )
        return OrderResult(success=False, ticket=ticket, error_message="Cancel pending orders not supported directly.")

    def close_position(self, ticket: int, volume: Optional[float] = None) -> OrderResult:
        if self.bridge is not None:
            res = self.bridge.close_position(ticket=ticket, volume=volume)
            success = res.get("status") == "SUCCESS"
            return OrderResult(
                success=success,
                ticket=ticket,
                error_message="" if success else str(res.get("message", "Close failed")),
                raw_response=res
            )

        if self._ensure_direct_mt5():
            import MetaTrader5 as mt5
            positions = mt5.positions_get(ticket=ticket)
            if not positions:
                return OrderResult(success=False, ticket=ticket, error_message=f"Position {ticket} not found.")
            pos = positions[0]
            close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            tick = mt5.symbol_info_tick(pos.symbol)
            if not tick:
                return OrderResult(success=False, ticket=ticket, error_message=f"Could not get tick for {pos.symbol}")
            close_price = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask
            close_vol = volume if volume and volume > 0 else pos.volume

            req_dict = {
                "action": mt5.TRADE_ACTION_DEAL,
                "position": int(ticket),
                "symbol": pos.symbol,
                "volume": float(close_vol),
                "type": close_type,
                "price": float(close_price),
                "deviation": 20,
                "magic": int(pos.magic),
                "comment": "CLOSE_POSITION",
                "type_time": mt5.ORDER_TIME_GTC,
            }
            sym_info = mt5.symbol_info(pos.symbol)
            if sym_info:
                filling_mode = sym_info.filling_mode
                if filling_mode & 2:
                    req_dict["type_filling"] = mt5.ORDER_FILLING_IOC
                elif filling_mode & 1:
                    req_dict["type_filling"] = mt5.ORDER_FILLING_FOK
                else:
                    req_dict["type_filling"] = mt5.ORDER_FILLING_RETURN
            else:
                req_dict["type_filling"] = mt5.ORDER_FILLING_IOC

            result = mt5.order_send(req_dict)
            if result is None:
                err = mt5.last_error()
                return OrderResult(success=False, ticket=ticket, error_message=f"Close order_send returned None: {err}")
            success = result.retcode == mt5.TRADE_RETCODE_DONE
            return OrderResult(
                success=success,
                ticket=int(result.order),
                deal=int(result.deal),
                price=float(result.price),
                volume=float(result.volume),
                retcode=int(result.retcode),
                comment=str(result.comment),
                error_message="" if success else f"Close Retcode: {result.retcode} ({result.comment})",
                raw_response={"retcode": result.retcode, "comment": result.comment},
            )
        return OrderResult(success=False, ticket=ticket, error_message="No bridge and MT5 direct failed.")
