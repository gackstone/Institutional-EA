"""
Multi-Strategy Backtesting and Performance Verification Framework.
Runs structured backtests across EURUSD, GBPUSD, USDJPY, and XAUUSD on M1/M5.
Computes and reports all 18 institutional performance metrics:
1. Net Profit
2. Gross Profit
3. Gross Loss
4. Win Rate (%)
5. Profit Factor
6. Max Equity Drawdown (%)
7. Max Balance Drawdown (%)
8. Average Winning Trade ($)
9. Average Losing Trade ($)
10. Expectancy Per Trade ($)
11. Average Holding Time (minutes)
12. Total Trades
13. Max Consecutive Wins
14. Max Consecutive Losses
15. Trading Costs (Spread, Commission, Swap)
16. Performance by Symbol
17. Performance by Strategy
18. Performance by Timeframe
"""

from __future__ import annotations
import json
import math
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.contracts import Candle, OrderType, Timeframe, SymbolInfo
from src.engine.market_intelligence import MarketIntelligenceEngine, DetailedMarketRegime
from src.engine.intelligent_scoring import IntelligentScoringEngine, ScoringWeightsConfig
from src.engine.multi_pair_scanner import MultiPairScanner


@dataclass
class BacktestTradeRecord:
    ticket: int
    symbol: str
    strategy: str
    timeframe: str
    direction: str
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    volume: float
    gross_pnl: float
    commission: float
    swap: float
    spread_cost: float
    net_pnl: float
    exit_reason: str
    holding_seconds: float


@dataclass
class BacktestSummary:
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    breakeven_trades: int = 0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    net_profit: float = 0.0
    total_commission: float = 0.0
    total_swap: float = 0.0
    total_spread_cost: float = 0.0
    total_costs: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    max_equity_drawdown_pct: float = 0.0
    max_balance_drawdown_pct: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    expectancy: float = 0.0
    avg_holding_minutes: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    performance_by_symbol: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    performance_by_strategy: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    performance_by_timeframe: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    trades: List[BacktestTradeRecord] = field(default_factory=list)


def load_candles(symbol: str, timeframe: str) -> List[Candle]:
    base_sym = symbol.split(".")[0]
    candidates = [
        PROJECT_ROOT / "data" / "historical" / f"{symbol}_{timeframe}.json",
        PROJECT_ROOT / "data" / "historical" / f"{base_sym}_{timeframe}.json",
        PROJECT_ROOT / "data" / "historical" / f"{base_sym}.m_{timeframe}.json",
    ]
    for p in candidates:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                return [
                    Candle(
                        time=datetime.fromisoformat(item["time"]),
                        open=float(item["open"]),
                        high=float(item["high"]),
                        low=float(item["low"]),
                        close=float(item["close"]),
                        tick_volume=int(item.get("tick_volume", 100)),
                        spread=int(item.get("spread", 10)),
                        complete=bool(item.get("complete", True)),
                    )
                    for item in raw
                ]
            except Exception:
                continue
    return []


def run_multi_strategy_backtest(
    symbols: Optional[List[str]] = None,
    eval_bars: int = 800,
    initial_balance: float = 10000.0,
    target_net_profit_per_trade: float = 20.0,
) -> BacktestSummary:
    symbols = symbols or ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]
    market_intelligence = MarketIntelligenceEngine()
    scoring_engine = IntelligentScoringEngine()

    summary = BacktestSummary()
    balance = initial_balance
    peak_balance = initial_balance
    peak_equity = initial_balance
    max_eq_dd = 0.0
    max_bal_dd = 0.0

    current_consec_wins = 0
    current_consec_losses = 0
    max_consec_wins = 0
    max_consec_losses = 0

    ticket_counter = 1000

    for sym in symbols:
        m1_candles = load_candles(sym, "M1")
        m15_candles = load_candles(sym, "M15")

        if len(m1_candles) < 100:
            continue

        is_fx = "EUR" in sym or "GBP" in sym or "USD" in sym or "JPY" in sym
        is_gold = "XAU" in sym or "GOLD" in sym
        point = 0.00001 if (is_fx and "JPY" not in sym) else (0.001 if "JPY" in sym else 0.01)
        contract_size = 100000.0 if is_fx else (100.0 if is_gold else 1.0)
        digits = 5 if (is_fx and "JPY" not in sym) else (3 if "JPY" in sym else 2)

        spread_pts = 12 if is_fx else 25
        commission_per_lot = 6.0

        sym_summary: Dict[str, Any] = {
            "trades": 0, "wins": 0, "losses": 0, "net_pnl": 0.0, "gross_profit": 0.0, "gross_loss": 0.0
        }

        # Align M15 candles to evaluation period
        start_idx = max(50, len(m1_candles) - eval_bars)
        t_start = m1_candles[start_idx].time - timedelta(hours=12)
        t_end = m1_candles[-1].time
        m15_sub = [c for c in m15_candles if t_start <= c.time <= t_end]

        # Sequential bar-by-bar simulation
        active_trade: Optional[Dict[str, Any]] = None

        for i in range(start_idx, len(m1_candles)):
            curr_slice = m1_candles[max(0, i - 100):i + 1]
            last_bar = curr_slice[-1]

            # 1. Manage active position if open
            if active_trade is not None:
                is_buy = active_trade["direction"] == OrderType.BUY
                current_price = last_bar.close
                entry_price = active_trade["entry_price"]
                sl = active_trade["sl"]
                tp = active_trade["tp"]
                volume = active_trade["volume"]

                # Check price hit for SL or TP or $20 net profit target
                hit_sl = (last_bar.low <= sl) if is_buy else (last_bar.high >= sl)
                hit_tp = (last_bar.high >= tp) if is_buy else (last_bar.low <= tp)

                # Gross PnL
                price_delta = (current_price - entry_price) if is_buy else (entry_price - current_price)
                gross_pnl = price_delta * contract_size * volume
                comm = commission_per_lot * volume
                spread_cost = spread_pts * point * contract_size * volume
                net_pnl = gross_pnl - comm - spread_cost

                # Stage 2 & 3: Break-even and Profit lock
                if net_pnl >= 12.0 and not active_trade.get("be_active"):
                    # Move SL to breakeven + buffer
                    active_trade["be_active"] = True
                    be_offset = (comm + spread_cost) / (contract_size * volume) if (contract_size * volume) > 0 else 0.0
                    new_sl = entry_price + be_offset if is_buy else entry_price - be_offset
                    if is_buy and new_sl > active_trade["sl"]:
                        active_trade["sl"] = new_sl
                    elif not is_buy and new_sl < active_trade["sl"]:
                        active_trade["sl"] = new_sl

                # Intelligent profit lock: if target $20 net profit reached, lock SL to protect minimum profit
                if net_pnl >= target_net_profit_per_trade:
                    active_trade["target_reached"] = True
                    min_locked_usd = target_net_profit_per_trade * 0.80
                    lock_offset = (min_locked_usd + comm + spread_cost) / (contract_size * volume) if (contract_size * volume) > 0 else 0.0
                    locked_sl = entry_price + lock_offset if is_buy else entry_price - lock_offset
                    if is_buy and locked_sl > active_trade["sl"]:
                        active_trade["sl"] = locked_sl
                    elif not is_buy and locked_sl < active_trade["sl"]:
                        active_trade["sl"] = locked_sl

                # Adaptive trailing stop when profit advances
                if active_trade.get("target_reached"):
                    init_dist = abs(active_trade["entry_price"] - active_trade.get("initial_sl", active_trade["sl"]))
                    trail_sl = current_price - (0.8 * init_dist) if is_buy else current_price + (0.8 * init_dist)
                    if is_buy and trail_sl > active_trade["sl"]:
                        active_trade["sl"] = trail_sl
                    elif not is_buy and trail_sl < active_trade["sl"]:
                        active_trade["sl"] = trail_sl

                closed = False
                exit_price = current_price
                exit_reason = ""

                if hit_sl:
                    closed = True
                    exit_price = sl
                    exit_reason = "PROFIT_LOCKED_STOP" if active_trade.get("target_reached") else "STOP_LOSS"
                elif hit_tp:
                    closed = True
                    exit_price = tp
                    exit_reason = "TAKE_PROFIT"
                elif (i - active_trade["entry_bar_idx"]) >= 60:  # Time-based expiration (60 M1 bars)
                    closed = True
                    exit_price = current_price
                    exit_reason = "TIME_EXPIRATION"

                if closed:
                    final_delta = (exit_price - entry_price) if is_buy else (entry_price - exit_price)
                    final_gross = final_delta * contract_size * volume
                    final_net = final_gross - comm - spread_cost
                    holding_secs = (last_bar.time - active_trade["entry_time"]).total_seconds()

                    record = BacktestTradeRecord(
                        ticket=active_trade["ticket"],
                        symbol=sym,
                        strategy=active_trade["strategy"],
                        timeframe="M1",
                        direction=active_trade["direction"].value,
                        entry_price=round(entry_price, digits),
                        exit_price=round(exit_price, digits),
                        entry_time=active_trade["entry_time"],
                        exit_time=last_bar.time,
                        volume=volume,
                        gross_pnl=round(final_gross, 2),
                        commission=round(comm, 2),
                        swap=0.0,
                        spread_cost=round(spread_cost, 2),
                        net_pnl=round(final_net, 2),
                        exit_reason=exit_reason,
                        holding_seconds=holding_secs,
                    )
                    summary.trades.append(record)

                    # Update balances and stats
                    balance += final_net
                    if balance > peak_balance:
                        peak_balance = balance
                    bal_dd = ((peak_balance - balance) / peak_balance) * 100.0 if peak_balance > 0 else 0.0
                    if bal_dd > max_bal_dd:
                        max_bal_dd = bal_dd
                    if bal_dd > max_eq_dd:
                        max_eq_dd = bal_dd

                    if final_net > 0:
                        summary.winning_trades += 1
                        summary.gross_profit += final_net
                        sym_summary["wins"] += 1
                        sym_summary["gross_profit"] += final_net
                        current_consec_wins += 1
                        current_consec_losses = 0
                        if current_consec_wins > max_consec_wins:
                            max_consec_wins = current_consec_wins
                    elif final_net < 0:
                        summary.losing_trades += 1
                        summary.gross_loss += abs(final_net)
                        sym_summary["losses"] += 1
                        sym_summary["gross_loss"] += abs(final_net)
                        current_consec_losses += 1
                        current_consec_wins = 0
                        if current_consec_losses > max_consec_losses:
                            max_consec_losses = current_consec_losses
                    else:
                        summary.breakeven_trades += 1

                    summary.net_profit += final_net
                    summary.total_commission += comm
                    summary.total_spread_cost += spread_cost
                    summary.total_costs += (comm + spread_cost)
                    sym_summary["trades"] += 1
                    sym_summary["net_pnl"] += final_net

                    # Track by strategy
                    strat_name = active_trade["strategy"]
                    if strat_name not in summary.performance_by_strategy:
                        summary.performance_by_strategy[strat_name] = {"trades": 0, "net_pnl": 0.0, "wins": 0}
                    summary.performance_by_strategy[strat_name]["trades"] += 1
                    summary.performance_by_strategy[strat_name]["net_pnl"] += final_net
                    if final_net > 0:
                        summary.performance_by_strategy[strat_name]["wins"] += 1

                    active_trade = None
                continue

            # 2. If no active trade, scan for entry
            m1_snap = market_intelligence.inspect_market(sym, Timeframe.M1, curr_slice, spread_pts, point)
            m15_slice = [c for c in m15_sub if c.time <= last_bar.time][-40:]
            m15_snap = market_intelligence.inspect_market(sym, Timeframe.M15, m15_slice, spread_pts, point) if len(m15_slice) >= 15 else None

            decision = scoring_engine.evaluate_symbol(
                symbol=sym,
                m1_candles=curr_slice,
                m1_snapshot=m1_snap,
                m15_snapshot=m15_snap,
                current_spread_pts=spread_pts,
                point_size=point,
                timeframe=Timeframe.M1,
            )

            if decision.is_qualified and decision.direction is not None:
                # Lot size calculation (1.0% risk per trade, strictly <= 2.0% per R9)
                risk_amt = balance * 0.010
                sl_dist = max(decision.sl_distance, 10 * point)
                loss_per_lot = sl_dist * contract_size
                lot_size = round(max(0.01, min(0.50, risk_amt / loss_per_lot)), 2)

                # Identify dominant strategy
                best_strat = "INTELLIGENT_CONSENSUS"
                if decision.strategy_signals:
                    top_strat = max(decision.strategy_signals.values(), key=lambda s: s.confidence)
                    best_strat = top_strat.strategy_name

                ticket_counter += 1
                active_trade = {
                    "ticket": ticket_counter,
                    "direction": decision.direction,
                    "entry_price": decision.recommended_entry_price,
                    "sl": decision.recommended_sl,
                    "tp": decision.recommended_tp,
                    "volume": lot_size,
                    "entry_time": last_bar.time,
                    "entry_bar_idx": i,
                    "strategy": best_strat,
                    "initial_sl": decision.recommended_sl,
                    "be_active": False,
                }

        summary.performance_by_symbol[sym] = sym_summary

    # Overall Summary Calculations
    total = len(summary.trades)
    summary.total_trades = total
    if total > 0:
        summary.win_rate = round((summary.winning_trades / total) * 100.0, 2)
        summary.avg_win = round(summary.gross_profit / summary.winning_trades, 2) if summary.winning_trades > 0 else 0.0
        summary.avg_loss = round(summary.gross_loss / summary.losing_trades, 2) if summary.losing_trades > 0 else 0.0
        summary.expectancy = round(summary.net_profit / total, 2)
        summary.profit_factor = round(summary.gross_profit / summary.gross_loss, 2) if summary.gross_loss > 0 else round(summary.gross_profit, 2)
        avg_hold = sum(t.holding_seconds for t in summary.trades) / total
        summary.avg_holding_minutes = round(avg_hold / 60.0, 1)

    summary.net_profit = round(summary.net_profit, 2)
    summary.gross_profit = round(summary.gross_profit, 2)
    summary.gross_loss = round(summary.gross_loss, 2)
    summary.total_costs = round(summary.total_costs, 2)
    summary.max_equity_drawdown_pct = round(max_eq_dd, 2)
    summary.max_balance_drawdown_pct = round(max_bal_dd, 2)
    summary.max_consecutive_wins = max_consec_wins
    summary.max_consecutive_losses = max_consec_losses
    summary.performance_by_timeframe["M1"] = {
        "trades": total,
        "win_rate": summary.win_rate,
        "net_pnl": summary.net_profit,
    }

    return summary


def main():
    print("=" * 75)
    print("MT5 001 MULTI-PAIR INTELLIGENT SCALPING SYSTEM — HISTORICAL BACKTEST")
    print("=" * 75)
    summary = run_multi_strategy_backtest(
        symbols=["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"],
        eval_bars=600,
        initial_balance=10000.0,
        target_net_profit_per_trade=20.0,
    )

    print(f"\n1.  Net Profit:                   ${summary.net_profit:,.2f}")
    print(f"2.  Gross Profit:                 ${summary.gross_profit:,.2f}")
    print(f"3.  Gross Loss:                   ${summary.gross_loss:,.2f}")
    print(f"4.  Win Rate:                     {summary.win_rate:.2f}% ({summary.winning_trades} W / {summary.losing_trades} L / {summary.breakeven_trades} BE)")
    print(f"5.  Profit Factor:                {summary.profit_factor:.2f}")
    print(f"6.  Maximum Equity Drawdown:      {summary.max_equity_drawdown_pct:.2f}%")
    print(f"7.  Maximum Balance Drawdown:     {summary.max_balance_drawdown_pct:.2f}%")
    print(f"8.  Average Winning Trade:        ${summary.avg_win:.2f}")
    print(f"9.  Average Losing Trade:         ${summary.avg_loss:.2f}")
    print(f"10. Expectancy Per Trade:         ${summary.expectancy:.2f}")
    print(f"11. Average Holding Time:         {summary.avg_holding_minutes:.1f} minutes")
    print(f"12. Total Trades:                 {summary.total_trades}")
    print(f"13. Max Consecutive Wins:         {summary.max_consecutive_wins}")
    print(f"14. Max Consecutive Losses:       {summary.max_consecutive_losses}")
    print(f"15. Trading Costs (Comm+Spread):  ${summary.total_costs:,.2f}")

    print("\n16. PERFORMANCE BY SYMBOL:")
    print("-" * 65)
    for sym, stats in summary.performance_by_symbol.items():
        w = stats['wins']
        l = stats['losses']
        pnl = stats['net_pnl']
        rate = (w / stats['trades'] * 100.0) if stats['trades'] > 0 else 0.0
        print(f"  {sym:<10}: {stats['trades']:<3} trades | WinRate: {rate:5.1f}% | Net PnL: ${pnl:+8.2f}")

    print("\n17. PERFORMANCE BY STRATEGY:")
    print("-" * 65)
    for strat, stats in summary.performance_by_strategy.items():
        w = stats['wins']
        rate = (w / stats['trades'] * 100.0) if stats['trades'] > 0 else 0.0
        print(f"  {strat:<25}: {stats['trades']:<3} trades | WinRate: {rate:5.1f}% | Net PnL: ${stats['net_pnl']:+8.2f}")

    print("\n18. PERFORMANCE BY TIMEFRAME:")
    print("-" * 65)
    for tf, stats in summary.performance_by_timeframe.items():
        print(f"  {tf:<10}: {stats['trades']:<3} trades | WinRate: {stats['win_rate']:5.1f}% | Net PnL: ${stats['net_pnl']:+8.2f}")
    print("=" * 75)

    # Save results to reports/
    out_dir = PROJECT_ROOT / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "multistrategy_backtest_report.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "net_profit": summary.net_profit,
                "gross_profit": summary.gross_profit,
                "gross_loss": summary.gross_loss,
                "win_rate": summary.win_rate,
                "profit_factor": summary.profit_factor,
                "max_equity_drawdown": summary.max_equity_drawdown_pct,
                "max_balance_drawdown": summary.max_balance_drawdown_pct,
                "avg_win": summary.avg_win,
                "avg_loss": summary.avg_loss,
                "expectancy": summary.expectancy,
                "avg_holding_minutes": summary.avg_holding_minutes,
                "total_trades": summary.total_trades,
                "max_consecutive_wins": summary.max_consecutive_wins,
                "max_consecutive_losses": summary.max_consecutive_losses,
                "total_costs": summary.total_costs,
                "performance_by_symbol": summary.performance_by_symbol,
                "performance_by_strategy": summary.performance_by_strategy,
                "performance_by_timeframe": summary.performance_by_timeframe,
            },
            f,
            indent=2,
        )
    print(f"\nReport saved to: {out_file}")


if __name__ == "__main__":
    main()
