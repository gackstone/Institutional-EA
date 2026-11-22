# CHANGELOG: GOLD Scalper Engine Transformation

## Summary of Changes

This document details every added, modified, preserved, and configured file associated with the conversion of the day-trading system into the dedicated high-frequency GOLD (XAUUSD) scalping system on branch `scalper-gold`.

---

## 1. Preserved Legacy Files (`/legacy/`)

In compliance with Non-Negotiable Rule 2 and Section 1, original versions of all replaced/modified source files were preserved under `/legacy/` before edits:

| Preserved File | Original Purpose |
|---|---|
| `legacy/src/core/orchestrator.py` | Original day-trading orchestrator with restrictive candle-close gates, news blackouts, and quality filters. |
| `legacy/src/core/config.py` | Original application configuration without the global `legacy_filters_enabled` bypass flag. |
| `legacy/src/execution/order_manager.py` | Original pre-trade checklist enforcing structure confirmations, drift filters, and session gates. |
| `legacy/src/execution/continuous_scalper.py` | Original multi-symbol M1/M5/M15 scalper before dedicated basket logic. |
| `legacy/mql5/Experts/PythonBridgeEA.mq5` | Original Expert Advisor with default day-trading parameters. |

---

## 2. Added Core Scalping Modules (`src/scalper/`)

A modular, clean package was implemented to power the high-frequency GOLD scalping engine:

| New File | Responsibility |
|---|---|
| `src/scalper/__init__.py` | Package initialization and public export of all scalper classes. |
| `src/scalper/config.py` | Centralized YAML configuration loader, validator, and typed dataclasses for all 21 sections. |
| `src/scalper/symbol_resolver.py` | Automatic discovery and validation of broker-specific GOLD symbols (`XAUUSD`, `XAUUSDm`, `XAUUSD.a`, `GOLD`), filling mode detection, and contract spec extraction. |
| `src/scalper/sizing.py` | Dynamic balance-based lot sizing (`floor(balance / LOT_STEP_BALANCE) * 0.01`) with broker step normalization and micro-account floor. |
| `src/scalper/direction.py` | Direction selection aggregating strategy intelligence as non-blocking scoring providers with tick velocity and M1 drift fallbacks (always outputs BUY or SELL). |
| `src/scalper/basket.py` | Multi-position basket state tracker, aggregate basket TP ($2.00), individual position TP ($0.50/0.01 lot), time stop (180s), and immediate re-entry priming. |
| `src/scalper/risk.py` | Mandatory safety controls: max positions (12), max lots, margin level >= 300%, equity drawdown stop (30%), spread filter (<= 80 pts), protective SL (300 pts), kill switch, and DEMO_MODE enforcement. |
| `src/scalper/executor.py` | Serialized thread-safe MT5 order execution pipeline with automatic filling mode selection, protective SL attachment, and retry logic. |
| `src/scalper/engine.py` | Master event loop coordinating the sub-second (200-500ms) continuous scalping cycle. |

---

## 3. Added Launchers, Configuration, Tests & Reports

| File | Purpose |
|---|---|
| `config/scalper.yaml` | Centralized YAML configuration file containing all 21 sections with safe defaults and descriptive comments. |
| `scripts/start_gold_scalper.py` | Main CLI entry point for the high-frequency Gold scalper engine with single-instance lock and graceful shutdown. |
| `start_gold_scalper.bat` | Windows batch launcher for the dedicated Gold scalper. |
| `scripts/run_gold_scalper_simulation.py` | Simulation and backtesting harness exercising live broker data, recording all metrics required by Section 10.3. |
| `reports/gold_scalper_simulation_report.json` | Detailed verified performance metrics from the simulated trading session. |
| `tests/test_gold_scalper.py` | Comprehensive test suite (22 tests) covering lot sizing, basket management, risk controls, symbol resolution, direction selection, and legacy compatibility. |

---

## 4. Modified Core Files

| File | Changes Made |
|---|---|
| `src/core/config.py` | Added `legacy_filters_enabled: bool = False` to `AppConfig`, reading from `settings.json` and `scalper.yaml`. |
| `src/core/orchestrator.py` | Modified to bypass news filter, setup quality gate, meta-labeling, active mode frequency limits, and HTF agreement when `legacy_filters_enabled == False`. Preserved original behavior when `True`. |
| `src/execution/order_manager.py` | Modified `run_pre_trade_checklist` to bypass structure confirmation, anti-chasing drift, strict R:R, replay gate, and session affinity when `legacy_filters_enabled == False`. Maintained all mandatory risk controls. |
| `requirements.txt` | Added `pyyaml>=6.0.0` dependency. |

---

## 5. Documentation Deliverables

| File | Purpose |
|---|---|
| `docs/ARCHITECTURE_BEFORE.md` | Complete architectural documentation of the repository prior to changes. |
| `docs/ARCHITECTURE_AFTER.md` | Complete architectural documentation of the new high-frequency GOLD scalping system. |
| `docs/REMOVED_FILTERS.md` | Inventory of all bypassed and removed legacy entry filters, their original locations, and compatibility behavior. |
