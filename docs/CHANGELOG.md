# Changelog

## [3.0.0] - 2026-11-14 — 18-Phase Master Scalping Upgrade (GOLD Weekday + BTCUSD Weekend)

### Added
- **Phase 1 Audit & Backups**: Archived v2 baseline files to `legacy/v2_baseline/` and added `docs/PHASE1_ARCHITECTURE_AUDIT.md` (architecture audit, execution-flow diagram, performance bottleneck report, implementation plan, regression risk assessment).
- **Phase 2 Event-Driven Low-Latency Execution**:
  - `src/scalper/market_cache.py`: `TickCache` (quote validation, staleness gating, duplicate-tick suppression) and `IndicatorCache` (incremental multi-timeframe `M1`/`M5`/`M15`/`H1` indicator caching).
  - `src/scalper/telemetry.py`: `ExecutionLatencyTracker` (signal, submission, broker-ack, and fill latency + slippage tracking) and `DuplicateOrderGuard` (order-fingerprint idempotency protection).
  - `mql5/Experts/PythonBridgeEA.mq5`: Added `OnTradeTransaction` event handler streaming real-time `TRADE_TRANSACTION` deal confirmations and enforcing immediate EA-side protective SL on magic `777001` (GOLD) and `777002` (BTCUSD). Compiled cleanly with MetaEditor (`0 errors, 0 warnings`).
- **Phase 3 Multi-Position Entry Engine (`src/scalper/entry_engine.py`)**:
  - Added `MultiPositionEntryEngine` supporting `SINGLE_ENTRY`, `CONTROLLED_MULTI_ENTRY`, `PYRAMID_ENTRY`, `RE_ENTRY`, and `REVERSAL` modes with unique `entry_id` and rationale per position.
- **Phase 4 Smart Dynamic Risk-Based Position Sizing (`src/scalper/sizing.py`)**:
  - Added `calculate_risk_based_lot()` and `compute_worst_case_loss_per_lot()` supporting `CONSERVATIVE` (0.10%), `STANDARD` (0.25%), and `AGGRESSIVE_DEMO` (0.50%) risk profiles, accounting for SL distance, spread, slippage, and commission, consuming remaining basket risk budget, rejecting under-budget `min_lot` trades, and strictly prohibiting martingale/loss-chasing.
- **Phase 5 & 6 Dedicated GOLD & BTCUSD Strategy Engines (`src/scalper/strategy_gold.py`, `src/scalper/strategy_btc.py`)**:
  - `GoldScalpingStrategy`: Weekday `XAUUSD` setup evaluation (`MOMENTUM_CONTINUATION`, `CONFIRMED_BREAKOUT`, `PULLBACK_CONTINUATION`, `LIQUIDITY_SWEEP_CONFIRMED`, `SIGNIFICANT_LEVEL_REJECTION`) with reward-to-cost gating.
  - `BtcWeekendScalpingStrategy`: Weekend `BTCUSD` strategy calibrated to crypto volatility, spread, and contract size (`1.0 BTC`).
- **Phase 7 & 8 Rapid Exit & Controlled Direction Reversal Engines (`src/scalper/exit_engine.py`, `src/scalper/reversal.py`)**:
  - `RapidExitEngine`: 10-way exit evaluation (protective SL, individual TP, basket TP, break-even, trailing stop, profit-locking floor, momentum deterioration, opposite signal, max holding time, emergency account exit) + tighten-only SL enforcement and broker reconciliation.
  - `DirectionReversalEngine`: Controlled reversal workflow closing and reconciling existing opposing positions before opening new reversed baskets, with full `ReversalRecord` audit history.
- **Phase 9, 10 & 14 Risk, Scheduler & Notification Upgrades (`src/scalper/risk.py`, `src/scalper/scheduler.py`, `src/scalper/notifier.py`)**:
  - Added open risk %, daily realized+floating loss limits, slippage check, consecutive-loss cooldown, and broker disconnect protection in `AccountRiskManager`.
  - Added broker UTC offset and DST detection in `MarketScheduler`.
  - Added `ScalperNotificationManager` with 15 telemetry fields and per-event rate limiting across 10 alert types.
- **Phase 12 & 13 Realistic Backtester & 16-Scenario Stress Harness (`src/scalper/backtester.py`, `src/scalper/stress_tester.py`)**:
  - `RealisticScalperBacktester` with chronological Train (50%) / Validation (25%) / Out-of-Sample (25%) splits, transaction costs, losing days, and 100%-win-rate anomaly detection.
  - `ScalperStressTester` validating all 16 stress and recovery scenarios.
- **Phase 15–18 Configuration, 109-Test Suite & Reports**:
  - Updated `config/scalper.yaml` with `gold:`, `btc:`, `account_risk:`, and `execution:` sections.
  - Added `tests/test_master_scalping_upgrade.py` (20 master upgrade test scenarios; `109/109` total tests passing).
  - Generated `reports/realistic_backtest_report.json`, `reports/stress_test_report.json`, `reports/execution_latency_report.json`, `reports/risk_validation_report.json`, and `reports/demo_execution_report.json`.

---

## [2.0.0] - 2026-11-14 — Dual-Market Calendar-Aware Scalper (XAUUSD Weekday + BTCUSD Weekend)

### Added
- Calendar-aware `MarketScheduler` (`src/scalper/scheduler.py`) routing Mon–Fri to `GOLD` (`777001`) and Sat–Sun to `BTCUSD` (`777002`).
- Multi-symbol `MultiSymbolResolver`, `SymbolLotSizingEngine`, and `MultiBasketManager`.
- 89 automated tests across `test_gold_scalper.py`, `test_btc_scalper.py`, `test_market_scheduler.py`, and `test_manual_management.py`.
