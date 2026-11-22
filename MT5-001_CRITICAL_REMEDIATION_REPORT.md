# MT5-001 — CRITICAL REMEDIATION REPORT

**Date:** 2026-11-16  
**Repository:** `https://github.com/gackstone/MT5-001-Bot.git`  
**Local Project Root:** `C:\Users\Gackstone_Baraka\Downloads\MT5 001`  
**Branch:** `feature/specialization-gold-jpy-btc` (base commit `2042a3002717b22d7cb0493df6e7339d5f16faaf`)  
**Recoverable Backup Location:** `backups\pre_remediation_backup\`

---

## 1. Original Defects & Root Causes

1. **CRITICAL-1: Three-Instrument Lockdown Disabled in Default Production Config & Bypassable at Execution Boundary**
   - **Root Cause:** `config/settings.json` set `"strict_three_symbol_universe": false`, and `AppConfig` (`src/core/config.py`) defaulted `strict_three_symbol_universe: bool = False`. Both `TradingBotOrchestrator` (`src/core/orchestrator.py`) and `OrderManager` (`src/execution/order_manager.py`) wrapped `symbol_universe.validate_or_reject()` inside `if strict_universe:`. `BridgeClient` (`src/execution/bridge_client.py`) and `LiveMT5Broker` (`src/adapters/live_mt5_broker.py`) had no symbol allowlist check.
   - **Impact:** Unauthorized symbols (`EURUSD`, `GBPUSD`, `US30`, `US100`, `NAS100`, `UNKNOWN_SYM`) passed pre-trade checks and could reach MT5 order submission.

2. **CRITICAL-2: `OrderManager` Ignored `PortfolioRiskEngine.evaluate_new_order_permission()`**
   - **Root Cause:** `OrderManager.run_pre_trade_checklist()` (`src/execution/order_manager.py`) called `self.portfolio_risk.evaluate_new_order_permission()` inside a `try/except` block solely for telemetry (`candidate.metadata["portfolio_risk_eval"]`), never checking the returned `allowed` boolean. Additionally, `OrderManager` read `max_aggregate_risk_percent` (default `8.0`) instead of `RiskConfig.max_aggregate_open_risk_percent` (`6.0`).
   - **Impact:** Portfolio circuit breakers (`circuit_breaker_active`), kill switches (`kill_switch_active`), drawdown halts (`buffer_halted`), and the `REAL`-account safety lock (`LIVE_TRADING_ENABLED=false`) were not enforced at order submission.

3. **HIGH-1: Unauthorized Symbols Persisted in Active Configs, Default Lists, Agent, and Companion UI**
   - **Root Cause:** `config/symbols.json`, `config/instruments.json`, `config/settings.json` (`symbol_magic_offsets`), `config/fast_mode.json`, `agent/mt5_bot_agent.py`, `src/core/market_data.py`, `src/execution/continuous_scalper.py`, `src/monitoring/health_monitor.py`, `companion/src/services/ipc.ts`, and `companion/src/components/SettingsModal.tsx` retained `EURUSD`, `GBPUSD`, `GBPJPY`, `NAS100`, `US30`, and `US100`. `ConfigurationService.validate_bundle()` did not reject unauthorized symbols.

4. **MEDIUM-1: Companion `EngineController.get_status()` AttributeError & Missing `.micro` Suffix**
   - **Root Cause:** `companion/service/orchestration/engine_controller.py` called `universe.get_approved_symbols()` and `universe.get_resolved_symbols()`, which did not exist on `SpecializedSymbolUniverse`. `BrokerSymbolResolver.KNOWN_SUFFIXES` and `APPROVED_CANONICAL_ALIASES` lacked `.micro`.
   - **Root Cause (OrderManager):** `OrderManager.run_pre_trade_checklist()` omitted `ExecutionMode.RETAIL` and `ExecutionMode.PROP` from the bridge ping/session check.

---

## 2. Files Modified & Corrections Made

| File | Correction |
|---|---|
| `config/settings.json` | Set `"strict_three_symbol_universe": true`; purged unauthorized symbols from `symbol_magic_offsets` (retained only `XAUUSD`, `USDJPY`, `BTCUSD` and `.m`). |
| `config/symbols.json` | Removed `EURUSD`, `EURUSD.m`, `GBPUSD`, `GBPUSD.m`; retained only `BTCUSD`, `BTCUSD.m`, `USDJPY`, `USDJPY.m`, `XAUUSD`, `XAUUSD.m`. |
| `config/instruments.json` | Removed `EURUSD`, `GBPUSD`, `NAS100`, `US30`; retained only `XAUUSD`, `BTCUSD`, `USDJPY`. |
| `config/fast_mode.json` | Removed `EURUSD`, `GBPUSD`, `NAS100`, `US30` from `max_deviation_points`. |
| `src/core/config.py` | Defaulted `strict_three_symbol_universe: bool = True`; forced `cfg.strict_three_symbol_universe = True` unconditionally in `AppConfig.load_from_dir()`; aligned `DEMO` default `PropFirmRulesConfig` (`no_martingale=False`, `no_grid_averaging=False`) with `config/account_profiles.json`. |
| `src/core/broker_resolver.py` | Added `.micro` to `KNOWN_SUFFIXES`. |
| `src/core/symbol_universe.py` | Added `.MICRO` aliases to `APPROVED_CANONICAL_ALIASES`; added `get_approved_symbols()` and `get_resolved_symbols()` methods on `SpecializedSymbolUniverse`. |
| `src/core/orchestrator.py` | Made `self.symbol_universe.validate_or_reject(symbol)` unconditional in `run_cycle_for_symbol()` and `run_scalping_cycle_for_symbol()`. |
| `src/execution/order_manager.py` | Made 3-symbol validation unconditional in `run_pre_trade_checklist()` and `execute_signal()`; added `RETAIL`/`PROP` to bridge ping/session check; aligned `max_aggregate_open_risk_percent`; enforced `self.portfolio_risk.evaluate_new_order_permission()` as a blocking check with structured rejection metadata (`setup_id`, `symbol`, `direction`, `reason`, `timestamp`, `safety_condition`). |
| `src/execution/bridge_client.py` | Added unconditional `get_symbol_universe().validate_or_reject()` in both `execute_trade()` and `send_request()` (`action == "TRADE"`). |
| `src/adapters/live_mt5_broker.py` | Added unconditional `get_symbol_universe().validate_or_reject(request.symbol)` in `send_order()`. |
| `src/core/market_data.py`, `src/execution/continuous_scalper.py`, `src/monitoring/health_monitor.py`, `agent/mt5_bot_agent.py` | Replaced legacy default symbol lists with `["XAUUSD", "BTCUSD", "USDJPY"]`. |
| `companion/service/configuration/config_service.py` | Added `APPROVED_CANONICAL_SYMBOLS` validation in `validate_bundle()` to reject unauthorized symbols. |
| `companion/src/services/ipc.ts`, `companion/src/components/SettingsModal.tsx` | Updated `allowedSymbols` default and placeholder to `XAUUSD, BTCUSD, USDJPY`. |
| `tests/test_remediation_compliance.py` | Added 22 regression tests covering all 18 acceptance criteria. |

---

## 3. Remaining Limitations

1. **Live MT5 Terminal Execution Not Tested:** Per audit/safety rules, no real or demo MT5 terminal orders were submitted; all execution tests used mocked `BridgeClient` / `MockEA` sockets.
2. **Legacy Tests Using `EURUSD`:** Two pre-existing tests (`tests/test_execution_bridge.py::TestExecutionBridge::test_bridge_actions` and `tests/test_pipeline_integration.py::TestPipelineIntegration::test_full_pipeline_execution`) still pass `EURUSD` as a mock symbol and therefore now fail because `EURUSD` is unconditionally blocked. They were preserved unmodified per test-integrity rules.
3. **MQL5 EA (`mql5/Experts/PythonBridgeEA.mq5`):** Retains legacy `EURUSD`/`GBPUSD`/`NAS100`/`US30` magic-offset and alias helper branches; however, Python-side `Orchestrator`, `OrderManager`, `LiveMT5Broker`, and `BridgeClient` all block unauthorized symbols before any request can reach the EA.
