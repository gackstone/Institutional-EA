"""
Interactive & Deterministic Replay Harness for Manual Position Management.
Simulates manual position adoption, break-even ratchets, structural trailing stops,
user overrides, and scale-in executions across a candle price sequence.
Tags: [SAFETY], [VIDEO 3], [VIDEO 12], [VIDEO 15], [ART-12]
"""

import argparse
import logging
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from typing import List

from src.adapters.broker_interface import BrokerAdapter, OrderResult, TradeRequest
from src.core.contracts import AccountInfo, Candle, OrderType, Position, SymbolInfo
from src.manual_mgmt.contracts import (
    ManagementMode,
    ManualMgmtConfig,
    PositionClass
)
from src.manual_mgmt.detector import ManualPositionDetector
from src.manual_mgmt.registry import ManualPositionRegistry


class ReplayBroker(BrokerAdapter):
    def __init__(self, account_info: AccountInfo):
        self.account_info = account_info
        self.positions: List[Position] = []
        self.modify_history = []
        self.order_history = []

    def ping(self) -> bool:
        return True

    def is_connected(self) -> bool:
        return True

    def get_account_info(self) -> AccountInfo:
        return self.account_info

    def get_positions(self, symbol=None):
        if symbol:
            return [p for p in self.positions if p.symbol == symbol]
        return list(self.positions)

    def get_rates(self, symbol, timeframe, count):
        return []

    def send_order(self, request: TradeRequest) -> OrderResult:
        new_ticket = 90000 + len(self.order_history) + 1
        self.order_history.append((new_ticket, request))
        return OrderResult(success=True, ticket=new_ticket, price=request.price, volume=request.volume, retcode=10009)

    def modify_order(self, ticket: int, sl: float, tp: float) -> OrderResult:
        self.modify_history.append((ticket, sl, tp))
        for p in self.positions:
            if p.ticket == ticket:
                p.stop_loss = sl
                p.take_profit = tp
        return OrderResult(success=True, ticket=ticket, retcode=10009)

    def cancel_order(self, ticket: int) -> OrderResult:
        return OrderResult(success=True, ticket=ticket)

    def close_position(self, ticket: int, volume=None) -> OrderResult:
        self.positions = [p for p in self.positions if p.ticket != ticket]
        return OrderResult(success=True, ticket=ticket)


def generate_candle_series(base_price: float, steps: int = 20, is_buy: bool = True) -> List[Candle]:
    candles = []
    base_time = datetime(2026, 11, 10, 8, 0, tzinfo=timezone.utc)
    step_delta = 0.0006 if is_buy else -0.0006

    for i in range(steps):
        t = base_time + timedelta(minutes=15 * i)
        # Upward impulse with periodic pullbacks
        if i % 4 == 0 and i > 0:
            # Minor pullback
            o = base_price + (i * step_delta) - (0.0002 if is_buy else -0.0002)
            c = o - (0.0003 if is_buy else -0.0003)
        else:
            o = base_price + (i * step_delta)
            c = o + (0.0005 if is_buy else -0.0005)

        h = max(o, c) + 0.0002
        l = min(o, c) - 0.0002
        candles.append(Candle(time=t, open=round(o, 5), high=round(h, 5), low=round(l, 5), close=round(c, 5), complete=True))

    return candles


def main():
    parser = argparse.ArgumentParser(description="Manual Position Management Replay Harness")
    parser.add_argument("--mode", type=str, default="PROTECT", choices=["OBSERVE", "PROTECT", "ASSIST", "FULL"],
                        help="Operational management mode")
    parser.add_argument("--symbol", type=str, default="EURUSD.m", help="Trading symbol")
    parser.add_argument("--direction", type=str, default="BUY", choices=["BUY", "SELL"], help="Order direction")
    parser.add_argument("--entry", type=float, default=1.1000, help="Manual position open price")
    parser.add_argument("--sl", type=float, default=1.0950, help="Initial manual SL (0.0 for naked position test)")
    parser.add_argument("--tp", type=float, default=1.1150, help="Initial manual TP")
    parser.add_argument("--volume", type=float, default=0.20, help="Lot volume")
    parser.add_argument("--steps", type=int, default=16, help="Number of candle steps")
    parser.add_argument("--override-step", type=int, default=8, help="Step where user overrides SL directly in MT5 (-1 to disable)")
    args = parser.parse_args()

    mode_enum = ManagementMode(args.mode.upper())
    is_buy = args.direction.upper() == "BUY"
    ot = OrderType.BUY if is_buy else OrderType.SELL

    temp_dir = tempfile.mkdtemp()
    state_file = os.path.join(temp_dir, "manual_positions.json")
    hist_file = os.path.join(temp_dir, "manual_positions_history.json")

    account = AccountInfo(account_number=88888, trade_mode="DEMO", margin_mode=2, margin_mode_str="HEDGING")
    broker = ReplayBroker(account_info=account)

    sym_info = SymbolInfo(
        symbol=args.symbol,
        digits=5,
        point=0.00001,
        tick_size=0.00001,
        tick_value=1.0,
        contract_size=100000.0,
        min_lot=0.01,
        max_lot=50.0,
        lot_step=0.01,
        stops_level=5
    )

    ticket = 77701
    initial_pos = Position(
        ticket=ticket,
        symbol=args.symbol,
        order_type=ot,
        volume=args.volume,
        open_price=args.entry,
        current_price=args.entry,
        stop_loss=args.sl,
        take_profit=args.tp,
        profit=0.0,
        magic=0,  # Manual trade
        comment="Discretionary Phone Entry"
    )
    broker.positions.append(initial_pos)

    config = ManualMgmtConfig(
        mode=mode_enum,
        allow_real_account_management=False,
        break_even_activation_r=1.0,
        trailing_stop_activation_r=1.5,
        max_addons_per_position=1,
        min_addon_rr_in_profit=1.0
    )

    registry = ManualPositionRegistry(state_file=state_file, history_file=hist_file, lockout_minutes=30)
    detector = ManualPositionDetector(config=config, broker=broker, registry=registry, bot_magic=100101)

    all_candles = generate_candle_series(base_price=args.entry, steps=args.steps, is_buy=is_buy)

    print("=" * 100)
    print(f" MANUAL POSITION ADOPTION & TRADE MANAGEMENT REPLAY HARNESS")
    print(f" Mode: {mode_enum.value} | Symbol: {args.symbol} | Direction: {ot.value} | Entry: {args.entry:.5f} | SL: {args.sl:.5f}")
    print("=" * 100)
    print(f"{'Step':<5} | {'Time (UTC)':<16} | {'Price':<9} | {'Current SL':<10} | {'Action':<10} | {'Rec SL/Vol':<12} | {'Status':<10} | {'Reason'}")
    print("-" * 100)

    for i in range(1, len(all_candles) + 1):
        c_sub = all_candles[:i]
        cur_c = c_sub[-1]
        cur_px = cur_c.close

        # Update broker position price
        p = broker.positions[0]
        p.current_price = cur_px
        diff = (cur_px - p.open_price) if is_buy else (p.open_price - cur_px)
        p.profit = round(diff * sym_info.contract_size * p.volume, 2)

        # Simulate user manual override event
        if i == args.override_step and args.override_step > 0:
            user_dragged_sl = cur_px - 0.0005 if is_buy else cur_px + 0.0005
            p.stop_loss = round(user_dragged_sl, 5)
            override_msg = f"[USER INTERVENTION] User moved SL directly to {p.stop_loss:.5f}!"
        else:
            override_msg = ""

        cycle_res = detector.run_cycle(
            market_data_candles_m15={args.symbol: c_sub},
            symbol_info_map={args.symbol: sym_info}
        )

        assessment = cycle_res["assessments"].get(ticket, {})
        action = assessment.get("action", "NONE")
        rec_val = assessment.get("recommended_sl") or assessment.get("add_on_volume") or "-"
        rec_str = f"{rec_val:.5f}" if isinstance(rec_val, float) else str(rec_val)

        status = "NONE"
        if cycle_res["executed_actions"]:
            status = "EXECUTED"
        elif cycle_res["rejected_actions"]:
            status = "BLOCKED"

        reason = assessment.get("reason", "")
        if cycle_res["rejected_actions"]:
            reason = cycle_res["rejected_actions"][0]["reason"]
        if override_msg:
            reason = f"{override_msg} | {reason}"

        print(f"{i:<5} | {cur_c.time.strftime('%H:%M'):<16} | {cur_px:<9.5f} | {p.stop_loss:<10.5f} | {action:<10} | {rec_str:<12} | {status:<10} | {reason}")

    print("=" * 100)
    print(" REPLAY SUMMARY & AUDIT TRAIL")
    print("=" * 100)
    rec = registry.get_record(ticket)
    if rec:
        print(f"Final Adopted Record: #{rec.ticket} in {rec.assigned_mode}")
        print(f"  • Initial SL: {rec.initial_sl:.5f} -> Final SL: {rec.current_sl:.5f}")
        print(f"  • Break-Even Applied: {rec.break_even_applied}")
        print(f"  • User Override Detected: {rec.user_override_detected}")
        print(f"  • Lockout Until: {rec.lockout_until}")
        print(f"  • Scale-ins (Add-ons): {rec.add_ons_count}")
        print("  • Audit Notes:")
        for note in rec.notes:
            print(f"      - {note}")

    print(f"Broker Order Modifications Executed: {len(broker.modify_history)}")
    for m in broker.modify_history:
        print(f"  • Modify Ticket #{m[0]}: SL={m[1]:.5f}, TP={m[2]:.5f}")

    shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
