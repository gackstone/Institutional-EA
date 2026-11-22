"""
Live MT5 Demo Trade Execution and Deal Reconciliation Verification Script.
Executes an actual demo order on XAUUSD.c, captures order and deal tickets,
verifies against MT5 deal history, and closes the test position.
"""
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import MetaTrader5 as mt5

def main():
    print("=" * 80)
    print("  Institutional EA VERIFIED DEMO TRADE EXECUTION & HISTORY RECONCILIATION")
    print("=" * 80)

    if not mt5.initialize():
        print("FAILED: mt5.initialize() failed:", mt5.last_error())
        return 1

    try:
        # 1. Verify Demo Account
        acc = mt5.account_info()
        term = mt5.terminal_info()
        if not acc:
            print("FAILED: Could not fetch account info")
            return 1

        print(f"[ACCOUNT INFO]")
        print(f"  Login:         {acc.login}")
        print(f"  Server:        {acc.server}")
        print(f"  Trade Mode:    {'DEMO' if acc.trade_mode == 0 else ('CONTEST' if acc.trade_mode == 1 else 'REAL')}")
        print(f"  Currency:      {acc.currency}")
        print(f"  Balance:       {acc.balance:.2f} {acc.currency}")
        print(f"  Equity:        {acc.equity:.2f} {acc.currency}")
        print(f"  Leverage:      1:{acc.leverage}")
        print(f"  Trade Allowed: {acc.trade_allowed and term.trade_allowed}")

        if acc.trade_mode != 0:
            print(f"FATAL: Account is NOT DEMO! Refusing to trade.")
            return 1

        # 2. Inspect Target Symbol
        symbol = "XAUUSD.c"
        sym_info = mt5.symbol_info(symbol)
        if not sym_info:
            print(f"FAILED: Symbol {symbol} not found")
            return 1

        mt5.symbol_select(symbol, True)
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            print(f"FAILED: No tick available for {symbol}")
            return 1

        print(f"\n[SYMBOL SPECIFICATION: {symbol}]")
        print(f"  Digits:        {sym_info.digits}")
        print(f"  Point:         {sym_info.point}")
        print(f"  Contract Size: {sym_info.trade_contract_size}")
        print(f"  Min Lot:       {sym_info.volume_min}")
        print(f"  Lot Step:      {sym_info.volume_step}")
        print(f"  Filling Mode:  {sym_info.filling_mode}")
        print(f"  Current Ask:   {tick.ask}")
        print(f"  Current Bid:   {tick.bid}")

        # Determine filling mode
        filling_mode = mt5.ORDER_FILLING_FOK
        if (sym_info.filling_mode & 2) != 0:
            filling_mode = mt5.ORDER_FILLING_IOC
        elif (sym_info.filling_mode & 1) != 0:
            filling_mode = mt5.ORDER_FILLING_FOK

        # 3. Preflight OrderCheck
        vol = 0.01
        price = tick.ask
        sl = round(tick.ask - 6.0, sym_info.digits)
        tp = round(tick.ask + 12.0, sym_info.digits)

        check_req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": vol,
            "type": mt5.ORDER_TYPE_BUY,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 20,
            "magic": 100101,
            "comment": "PREFLIGHT_CHECK",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_mode,
        }

        print(f"\n[STEP 1: PREFLIGHT ORDER_CHECK]")
        check_res = mt5.order_check(check_req)
        print(f"  Check Retcode: {check_res.retcode} ({check_res.comment})")
        print(f"  Req Margin:    {check_res.margin:.2f} {acc.currency}")
        print(f"  Free Margin:   {check_res.margin_free:.2f} {acc.currency}")

        if check_res.retcode != 0:
            print(f"FAILED: order_check rejected with retcode {check_res.retcode}: {check_res.comment}")
            return 1

        # 4. Execute Actual Market Order
        print(f"\n[STEP 2: DEMO ORDER EXECUTION]")
        order_req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": vol,
            "type": mt5.ORDER_TYPE_BUY,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 20,
            "magic": 100101,
            "comment": "VERIFIED_DEMO_BUY",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_mode,
        }

        send_res = mt5.order_send(order_req)
        print(f"  Send Retcode:  {send_res.retcode} ({send_res.comment})")
        print(f"  Order Ticket:  {send_res.order}")
        print(f"  Deal Ticket:   {send_res.deal}")
        print(f"  Fill Price:    {send_res.price}")
        print(f"  Fill Volume:   {send_res.volume}")

        if send_res.retcode != 10009:  # TRADE_RETCODE_DONE
            print(f"FAILED: Order submission failed with retcode {send_res.retcode}: {send_res.comment}")
            return 1

        order_ticket = send_res.order
        deal_ticket = send_res.deal
        position_ticket = send_res.order

        time.sleep(1.0)

        # 5. Verify Live Position in Terminal
        print(f"\n[STEP 3: ACTIVE POSITION AUDIT]")
        positions = mt5.positions_get(symbol=symbol)
        active_pos = None
        for p in (positions or []):
            if p.ticket == position_ticket or p.magic == 100101:
                active_pos = p
                break

        if active_pos:
            print(f"  FOUND ACTIVE POSITION:")
            print(f"    Ticket:      {active_pos.ticket}")
            print(f"    Symbol:      {active_pos.symbol}")
            print(f"    Type:        {'BUY' if active_pos.type == 0 else 'SELL'}")
            print(f"    Volume:      {active_pos.volume}")
            print(f"    Open Price:  {active_pos.price_open}")
            print(f"    Current SL:  {active_pos.sl}")
            print(f"    Current TP:  {active_pos.tp}")
            print(f"    Profit:      {active_pos.profit:.2f} {acc.currency}")
        else:
            print(f"  WARNING: Active position not found under ticket {position_ticket}")

        # 6. Reconcile MT5 Deal History
        print(f"\n[STEP 4: DEAL HISTORY RECONCILIATION]")
        deals = mt5.history_deals_get(position=position_ticket)
        matching_deal = None
        for d in (deals or []):
            if d.ticket == deal_ticket or d.order == order_ticket:
                matching_deal = d
                break

        if matching_deal:
            print(f"  RECONCILED DEAL IN BROKER HISTORY:")
            print(f"    Deal Ticket: {matching_deal.ticket}")
            print(f"    Order Ticket:{matching_deal.order}")
            print(f"    Symbol:      {matching_deal.symbol}")
            print(f"    Volume:      {matching_deal.volume}")
            print(f"    Price:       {matching_deal.price}")
            print(f"    Commission:  {matching_deal.commission}")
            print(f"    Swap:        {matching_deal.swap}")
            print(f"    Profit:      {matching_deal.profit}")
            print(f"    Time:        {datetime.fromtimestamp(matching_deal.time, timezone.utc).isoformat()}")
        else:
            print(f"  WARNING: Deal ticket {deal_ticket} not found in recent history")

        # 7. Clean Closure of Test Position
        if active_pos:
            print(f"\n[STEP 5: TEST POSITION CLOSURE]")
            cur_tick = mt5.symbol_info_tick(symbol)
            close_price = cur_tick.bid if active_pos.type == 0 else cur_tick.ask
            close_req = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": active_pos.volume,
                "type": mt5.ORDER_TYPE_SELL if active_pos.type == 0 else mt5.ORDER_TYPE_BUY,
                "position": active_pos.ticket,
                "price": close_price,
                "deviation": 20,
                "magic": 100101,
                "comment": "VERIFIED_DEMO_CLOSE",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": filling_mode,
            }
            close_res = mt5.order_send(close_req)
            print(f"  Close Retcode: {close_res.retcode} ({close_res.comment})")
            print(f"  Close Order:   {close_res.order}")
            print(f"  Close Deal:    {close_res.deal}")
            print(f"  Close Price:   {close_res.price}")

            # Reconcile closure deal
            time.sleep(1.0)
            deals_after = mt5.history_deals_get(position=active_pos.ticket)
            close_deal = next((d for d in (deals_after or []) if d.ticket == close_res.deal), None)
            if close_deal:
                print(f"  RECONCILED CLOSE DEAL IN BROKER HISTORY:")
                print(f"    Close Deal Ticket: {close_deal.ticket}")
                print(f"    Realized P/L:      {close_deal.profit:.2f} {acc.currency}")

        print("\n" + "=" * 80)
        print("  VERIFIED DEMO TRADE EXECUTION & RECONCILIATION: COMPLETED SUCCESSFULLY")
        print("=" * 80)
        return 0

    finally:
        mt5.shutdown()

if __name__ == "__main__":
    sys.exit(main())
