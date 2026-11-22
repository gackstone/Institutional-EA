# Deployment Instructions & Operational Risk Guide (v3.1.0)

## 1. Safety & Execution Mode Policy

> [!IMPORTANT]
> The system defaults to **`DEMO_MODE: true`** (`execution_mode: DEMO`) with `allow_real_trading: false` and `require_live_confirmation: true` in `config/scalper.yaml`. **Live trading is blocked by default and requires explicit manual operator approval** (`allow_real_trading: true` in `config/scalper.yaml`) only after out-of-sample backtesting, stress testing, and multi-session MT5 Demo validation have been reviewed.

---

## 2. Prerequisites & Environment Setup

1. **MetaTrader 5 Terminal**:
   - Installed at `C:\Program Files\MetaTrader 5\terminal64.exe` (MetaEditor at `C:\Program Files\MetaTrader 5\metaeditor64.exe`).
   - Logged into Demo account (`JustMarkets-Demo3`, Login `1200057798`, `TRADE_MODE_DEMO`).
   - Ensure `XAUUSD.m` and `BTCUSD.m` are visible in the **Market Watch** window and **Algo Trading** is enabled.
2. **Python Virtual Environment**:
   ```powershell
   cd "c:\Users\Gackstone_Baraka\Downloads\MT5 001"
   .\.venv\Scripts\python.exe --version
   ```

---

## 3. Pre-Launch Operator Checklist (`STOP.flag` & Unprotected Manual Positions)

> [!WARNING]
> **Active `STOP.flag` Present on Disk**:
> An active emergency kill-switch file currently exists at `c:\Users\Gackstone_Baraka\Downloads\MT5 001\STOP.flag` (and `scripts\STOP.flag`). By design, the scalper engine **refuses to start** while `STOP.flag` exists and never deletes or bypasses `STOP.flag` automatically.
>
> **Unprotected Manual Positions on `JustMarkets-Demo3` (`1200057798`)**:
> Live terminal inspection detected 2 open manual positions (`Magic: 0`, `XAUUSD.m` BUY `0.08` lots, tickets `#1039529266` @ `3891.99` and `#1039529450` @ `3892.62`) that currently have **`SL = 0.0`** (`TP = 3900.31` / `3900.60`). Before starting automated trading, verify or attach protective stop-losses to those manual positions (or run the Manual Position Manager).

### Operator Procedure to Clear `STOP.flag` When Ready to Trade DEMO

1. Inspect the MT5 terminal and confirm account `1200057798` (`JustMarkets-Demo3`, `TRADE_MODE_DEMO`) is healthy.
2. Manually remove `STOP.flag` only when you are ready to allow DEMO execution:
   ```powershell
   Remove-Item "c:\Users\Gackstone_Baraka\Downloads\MT5 001\STOP.flag" -Force
   ```
3. To re-engage the emergency kill switch at any time:
   ```powershell
   New-Item -Path "c:\Users\Gackstone_Baraka\Downloads\MT5 001\STOP.flag" -ItemType File -Force
   ```

---

## 4. Compiling & Deploying the MQL5 Expert Advisor

1. Compile `mql5/Experts/PythonBridgeEA.mq5` using MetaEditor:
   ```powershell
   & "C:\Program Files\MetaTrader 5\metaeditor64.exe" /compile:"c:\Users\Gackstone_Baraka\Downloads\MT5 001\mql5\Experts\PythonBridgeEA.mq5" /log:"c:\Users\Gackstone_Baraka\Downloads\MT5 001\compile.log"
   ```
2. Verify `0 errors, 0 warnings` in `compile.log`.
3. Copy both `.mq5` and `.ex5` to the active MT5 Terminal `MQL5\Experts\` folder and attach `PythonBridgeEA` to an `XAUUSD.m` (M1) chart.

---

## 5. Running Automated Verification & Reports

1. **Run the complete 132-test automated suite**:
   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests\test_gold_scalper.py tests\test_btc_scalper.py tests\test_market_scheduler.py tests\test_manual_management.py tests\test_master_scalping_upgrade.py tests\test_master_repair_suite.py -v
   ```
2. **Regenerate all 10 verification & benchmark reports**:
   ```powershell
   .\.venv\Scripts\python.exe .\scripts\generate_master_reports.py
   ```
   Output files in `reports/`:
   - `reports/realistic_backtest_report.json`
   - `reports/stress_test_report.json`
   - `reports/execution_latency_report.json`
   - `reports/risk_validation_report.json`
   - `reports/demo_execution_report.json`
   - `reports/gold_scalping_report.json`
   - `reports/btcusd_weekend_report.json`
   - `reports/basket_performance_report.json`
   - `reports/risk_events_report.json`
   - `reports/demo_readiness_report.json`

---

## 6. Verified Launch Commands (DEMO Mode)

### Primary Dual-Market Launcher (GOLD Weekdays + BTCUSD Weekends)
```powershell
# Simulation dry-run (bounded cycles, zero live MT5 order_send):
.\.venv\Scripts\python.exe .\scripts\start_dual_scalper.py --config config\scalper.yaml --simulation --max-cycles 20

# Live MT5 DEMO execution (requires STOP.flag to be cleared by operator first):
.\.venv\Scripts\python.exe .\scripts\start_dual_scalper.py --config config\scalper.yaml
```

### Dedicated Single-Symbol GOLD Launcher
```powershell
.\.venv\Scripts\python.exe .\scripts\start_gold_scalper.py --config config\scalper.yaml
```

### Graceful Stop Behavior
- Pressing **`Ctrl+C`** (or reaching `--max-cycles`) invokes `engine.shutdown(liquidate_positions=False)`, which stops the loop, preserves open broker positions with their verified server-side protective stop-losses intact, disconnects MT5 cleanly, and releases the `SingleInstanceLock`.
- Pass `--liquidate-on-exit` if you explicitly want `Ctrl+C` or `--max-cycles` to flatten all scalper positions on exit.

---

## 7. Unresolved Operational Risks & Live Readiness Notes

1. **Profitability Is Never Guaranteed**: Historical backtest and simulated stress test performance do not guarantee future live profitability. Real broker liquidity during tier-1 macroeconomic releases (NFP, FOMC, CPI) or weekend crypto exchange outages can cause slippage exceeding modeled assumptions.
2. **Minimum Account Equity for Risk-Budget Sizing**: Because `XAUUSD.m` has `contract_size = 100` (`0.01` lot = `1 oz`), a `300`-point (`$3.00`) stop loss plus spread/commission represents `~$3.35` risk per `0.01` lot. Under strict risk-budget sizing (`STANDARD = 0.25%`), accounts smaller than `$1,500` will have `min_lot = 0.01` rejected when `strict_min_lot_rejection` is active unless a tighter SL or `AGGRESSIVE_DEMO` profile is selected.
3. **Broker Weekend Maintenance Windows**: Even on 24/7 crypto brokers, `BTCUSD.m` may enter `SYMBOL_TRADE_MODE_CLOSEONLY` or `DISABLED` during scheduled Sunday server maintenance. The `MarketScheduler` detects this via `spec.trade_mode` and blocks new entries while continuing to monitor existing positions once quotes resume.
4. **Host / VPS Network Continuity**: If both the Python engine and the MT5 terminal lose internet connectivity simultaneously, only server-side stop-loss levels (`sl` sent with each `order_send`) protect open positions at the broker. Always keep `protective_sl.enforce_immediate_placement: true` enabled.
