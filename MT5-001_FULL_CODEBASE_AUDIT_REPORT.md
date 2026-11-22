# MT5-001 — FULL CODEBASE AUDIT, IMPLEMENTATION VERIFICATION & ENGINEERING COMPLIANCE REPORT

**Audit Date:** 2026-11-16  
**Auditor Role:** Principal Software Auditor / Quantitative Trading Systems Architect / MT5 Integration Specialist  
**Repository:** `https://github.com/gackstone/MT5-001-Bot.git`  
**Local Project Root:** `C:\Users\Gackstone_Baraka\Downloads\MT5 001`  
**Audit Scope:** Full read-only source inspection, static repository-wide search, execution pipeline tracing, and mocked/unit runtime verification. No production source files were modified; no live/demo MT5 orders were placed.

---

## 1. Executive Summary

**Overall Implementation Verdict:** **PARTIALLY IMPLEMENTED** (with **CRITICAL** configuration/enforcement gaps that bypass the three-instrument lockdown in default production execution).

While core architectural updates—removal of the 3-position minimum and 7-position maximum caps, removal of strategy-level spread rejection, removal of arbitrary grid/averaging limits, and implementation of the `SpecializedSymbolUniverse` module—have been written into the codebase, **the three-instrument restriction is disabled in the active production configuration** (`config/settings.json` sets `"strict_three_symbol_universe": false`, and `AppConfig` defaults `strict_three_symbol_universe` to `False`). As a result, unauthorized symbols (`EURUSD`, `GBPUSD`, `US30`, `US100`, `NAS100`, and arbitrary unknown symbols) **pass** `OrderManager.run_pre_trade_checklist()` under the default configuration and can reach MT5 order submission.

Furthermore, unauthorized symbols remain in active configuration registries (`config/symbols.json`, `config/instruments.json`, `config/settings.json`, `config/fast_mode.json`), fallback default lists (`agent/mt5_bot_agent.py`, `src/core/market_data.py`, `src/execution/continuous_scalper.py`, `src/engine/multi_pair_scanner.py`, `src/monitoring/health_monitor.py`), and the Desktop Companion UI/IPC (`companion/src/services/ipc.ts`, `companion/src/components/SettingsModal.tsx`), and `Companion` backend config validation does not reject unauthorized symbols.

---

## 2. Project Baseline

| Baseline Item | Observed Value |
|---|---|
| **Git Branch** | `feature/specialization-gold-jpy-btc` |
| **Commit Hash** | `2042a3002717b22d7cb0493df6e7339d5f16faaf` |
| **Git Working Tree** | Clean (`nothing to commit, working tree clean`) |
| **Main Trading Engine Entry Point** | `scripts/start_bot.py` (`main()`, invoked by `start_mt5_bot.bat` / `companion/service/orchestration/engine_controller.py`) |
| **Cloud / Agent Entry Point** | `agent/mt5_bot_agent.py` (invoked by `start_mt5_agent.bat`) |
| **Dedicated Gold Scalper Entry Point** | `scripts/start_gold_scalper.py` (invoked by `start_gold_scalper.bat`) |
| **MT5 Integration Entry Points** | Python TCP client: `src/execution/bridge_client.py` (`BridgeClient`), TCP server: `src/execution/bridge_server.py`, Direct fallback: `src/adapters/live_mt5_broker.py`, MQL5 EA: `mql5/Experts/PythonBridgeEA.mq5` |
| **Companion Backend / UI** | FastAPI/Control Service: `companion/service/main.py`, `companion/service/api/server.py`, `companion/service/orchestration/engine_controller.py`; React/Electron/Tauri UI: `companion/src/` |

### Architecture Map

1. **Configuration Layer:** `config/*.json`, `src/core/config.py` (`AppConfig`, `RiskConfig`, `StrategyConfig`, `AccountProfileConfig`)
2. **Instrument & Schedule Layer:** `src/core/symbol_universe.py` (`SpecializedSymbolUniverse`), `src/core/broker_resolver.py` (`BrokerSymbolResolver`), `src/core/instruments.py` (`InstrumentRegistry`), `src/core/trading_schedule.py` (`TradingScheduleManager`)
3. **Market Data & SMC Strategy Layer:** `src/core/market_data.py` (`MarketDataEngine`), `src/smc/mtf_analyzer.py` (`MultiTimeframeAnalyzer`), `src/smc/market_structure.py` (`MarketStructureEngine`), `src/smc/fvg_ob.py` (`FvgObEngine`), `src/smc/strategy_engine.py` (`SmcStrategyEngine`), `src/execution/continuous_scalper.py` (`ContinuousScalpingEngine`), `src/engine/multi_pair_scanner.py` (`MultiPairScanner`)
4. **Orchestration, Risk & Execution Layer:** `src/core/orchestrator.py` (`TradingBotOrchestrator`), `src/risk/position_sizing.py` (`PositionSizingEngine`), `src/risk/portfolio_risk.py` (`PortfolioRiskEngine`), `src/risk/trade_management.py` (`TradeManagementEngine`), `src/execution/order_manager.py` (`OrderManager`), `src/execution/transaction_manager.py` (`TransactionManager`)
5. **MT5 Bridge & EA Layer:** `src/execution/bridge_client.py`, `src/execution/bridge_server.py`, `mql5/Experts/PythonBridgeEA.mq5`
6. **Companion & Agent Layer:** `companion/service/`, `companion/src/`, `agent/mt5_bot_agent.py`

---

## 3. Instrument Lockdown Audit

**Verdict:** **IMPLEMENTED BUT BROKEN** (Bypassed by default configuration).

### Authorized Symbols
`src/core/symbol_universe.py` (`APPROVED_CANONICAL_SYMBOLS`, line 24):
- `XAUUSD` (aliases: `XAUUSD`, `GOLD`, `XAU`, `XAUUSD.M`, `XAUUSDM`, `GOLD.M`, `GOLDM`, `XAUUSD.PRO`, `XAUUSD.RAW`, `XAUUSD.ECN`)
- `BTCUSD` (aliases: `BTCUSD`, `BITCOIN`, `BTC`, `BTCUSD.M`, `BTCUSDM`, `BTCUSD.PRO`, `BTCUSD.RAW`, `BTCUSD.ECN`)
- `USDJPY` (aliases: `USDJPY`, `USDJPY.M`, `USDJPYM`, `USDJPY.PRO`, `USDJPY.RAW`, `USDJPY.ECN`)

### Broker Suffix Mappings & Edge Cases
- `BrokerSymbolResolver.normalize_root()` (`src/core/broker_resolver.py:83-96`) strips `KNOWN_SUFFIXES`: `(".std", ".raw", ".ecn", "_ecn", ".pro", ".m", ".a", ".r", ".c", ".i", "_i", "+", "#", "m")`.
- **Gap:** `".micro"` (present in `config/instruments.json`) is **not** in `KNOWN_SUFFIXES` or `APPROVED_CANONICAL_ALIASES`, causing `SpecializedSymbolUniverse.validate_or_reject("XAUUSD.micro")` to return `False`.
- `InstrumentRegistry.get()` (`src/core/instruments.py:118`) still uses loose `root.startswith(profile.canonical.upper())` prefix matching, whereas `SpecializedSymbolUniverse.is_approved()` (`src/core/symbol_universe.py:75-89`) uses exact/alias/normalized-root matching.

### Critical Enforcement Bypass
- `config/settings.json:32`: `"strict_three_symbol_universe": false`
- `src/core/config.py:332`: `strict_three_symbol_universe: bool = False`
- `src/core/orchestrator.py:859, 1203, 1369`: `if strict_universe:` — skips `self.symbol_universe.validate_or_reject(symbol)` whenever `strict_three_symbol_universe` is `False`.
- `src/execution/order_manager.py:137`: `if getattr(self.config, "strict_three_symbol_universe", False):` — skips `universe.validate_or_reject(candidate.symbol)` whenever `strict_three_symbol_universe` is `False`.
- `BridgeClient`, `BridgeServer`, `LiveMT5Broker`, and `PythonBridgeEA.mq5` have **no** three-instrument allowlist enforcement.

### Active Unauthorized Symbol References Found
- `config/symbols.json`: Still defines `EURUSD`, `EURUSD.m`, `GBPUSD`, `GBPUSD.m`.
- `config/instruments.json`: Still defines `EURUSD`, `GBPUSD`, `NAS100`, `US30`.
- `config/settings.json:48-57`: `symbol_magic_offsets` includes `EURUSD`, `GBPUSD`, `GBPJPY.m`, `NAS100`, `US30`.
- `config/fast_mode.json:45-48`: `max_deviation_points` includes `EURUSD`, `GBPUSD`, `NAS100`, `US30`.
- `agent/mt5_bot_agent.py:327`: `"allowed_symbols": ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD.m"]`.
- `src/core/market_data.py:62`: `self.symbols = symbols or ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]`.
- `src/execution/continuous_scalper.py:99`: `symbols or ["BTCUSD.m", "EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "US100.std", "US30.std"]`.
- `src/engine/multi_pair_scanner.py:34-42`: `DEFAULT_SCANNER_SYMBOLS` includes `EURUSD`, `GBPUSD`, `GBPJPY`, etc.
- `src/monitoring/health_monitor.py:69`: `symbols or ["BTCUSD.m", "EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]`.
- `companion/src/services/ipc.ts:438`: `allowedSymbols: ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]`.
- `companion/src/components/SettingsModal.tsx:186`: `placeholder="EURUSD, GBPUSD, USDJPY, XAUUSD"`.
- `mql5/Experts/PythonBridgeEA.mq5:374-378, 4318-4440`: Includes `EURUSD`, `GBPUSD`, `GBPJPY`, `NAS100`, `US100`, `US30` magic offsets and alias fallbacks.

### Mandatory Authorization Test Results
Executed via `scratch/audit_tests.py` against both `SpecializedSymbolUniverse.validate_or_reject()` and default `AppConfig.load_from_dir()` -> `OrderManager.run_pre_trade_checklist()`:

| Instrument | Expected | `SpecializedSymbolUniverse` | Default `OrderManager` (`settings.json`) | Verdict |
|---|---|---|---|---|
| `XAUUSD` | ACCEPT | ACCEPT (`True`) | ACCEPT (`passed=True`) | PASS |
| `BTCUSD` | ACCEPT | ACCEPT (`True`) | ACCEPT (`passed=True`) | PASS |
| `USDJPY` | ACCEPT | ACCEPT (`True`) | ACCEPT (`passed=True`) | PASS |
| `EURUSD` | REJECT | REJECT (`False`) | **ACCEPT (`passed=True`)** | **FAIL** |
| `GBPUSD` | REJECT | REJECT (`False`) | **ACCEPT (`passed=True`)** | **FAIL** |
| `US30` | REJECT | REJECT (`False`) | **ACCEPT (`passed=True`)** | **FAIL** |
| `US100` | REJECT | REJECT (`False`) | **ACCEPT (`passed=True`)** | **FAIL** |
| `NAS100` | REJECT | REJECT (`False`) | **ACCEPT (`passed=True`)** | **FAIL** |
| `UNKNOWN_SYM` | REJECT | REJECT (`False`) | **ACCEPT (`passed=True`)** | **FAIL** |

---

## 4. Position-Count Restriction Audit

**Verdict:** **FULLY IMPLEMENTED** (3-min and 7-max rules removed in active pipeline).

- `src/core/orchestrator.py:479-483, 1358-1363`: Position counting is informational/logged only; no 3-position minimum or 7-position maximum gate exists.
- `src/execution/order_manager.py:321-325`: Arbitrary position-count limits are removed.
- `src/risk/portfolio_risk.py:573-574`: 3-min and 7-max limits removed.
- `mql5/Experts/PythonBridgeEA.mq5:118, 3828`: `InpMaxPositions = 999` and position-count veto removed in `ValidatePreTrade()`.
- `config/risk_config.json:11`, `config/account_profiles.json`, `config/instruments.json`, `config/fast_mode.json`: Position caps raised to `100`.
- **Legacy/Inactive Modules:** `src/risk/session_risk.py:35` (`max_concurrent_session_positions=2`), `src/execution/active_mode.py:70` (`max_concurrent_positions_per_symbol=1`), and `src/risk/fast_risk_guard.py:371-372` (`max_concurrent_positions_global=3`, `max_concurrent_positions_per_symbol=1`) still retain small defaults, **but** they are gated behind `if legacy_filters_enabled` in `OrderManager` (`config/settings.json` sets `LEGACY_FILTERS_ENABLED: false`), so they do not execute in production.

### Mandatory Position-Count Test Results (Mocked MT5)
Executed via `scratch/audit_tests.py` (`OrderManager.execute_signal()` with `risk_percentage=0.5%`, `balance=$10,000`):
- **Entry #1** (`existing=0`, verifying no 3-min requirement): `status=FILLED`, `ticket=7001` — **PASS**
- **Entries #2–#7** (`existing=1..6`): `status=FILLED`, `tickets=7002..7007` — **PASS**
- **Entry #8** (`existing=7`): `status=FILLED`, `ticket=7008` — **PASS**
- **Entry #9** (`existing=8`): `status=FILLED`, `ticket=7009` — **PASS**
- **Entry #10** (`existing=9`): `status=FILLED`, `ticket=7010` — **PASS**

*(Note: Under default `risk_percentage=1.0%`, the 8.0% aggregate open risk ceiling in `OrderManager:328` limits concurrent 1%-risk positions to 8 positions total due to aggregate risk, not a 7-position count cap.)*

---

## 5. Spread Restriction Audit

**Verdict:** **FULLY IMPLEMENTED** (Strategy-level spread veto removed; extreme spreads may still fail $20 target feasibility under R9 2% risk cap).

| Location | Mechanism | Classification | Effect |
|---|---|---|---|
| `src/execution/order_manager.py:212-217` | Records `spread_pts` & `spread_pct_sl` in `candidate.metadata` | **Execution analytics / Informational** | Non-blocking; logs `[SPREAD_ENGINE] Strategy-level spread rejection is disabled.` |
| `src/engine/pipeline.py:540-548` | Computes `spread_pct` and logs | **Informational** | Non-blocking. |
| `src/execution/fast_mode_engine.py:334-341` | Computes `spread_pct_of_sl` and logs | **Informational** | Non-blocking. |
| `mql5/Experts/PythonBridgeEA.mq5:3510-3529` | `ValidateSpreadFilter()` | **Informational** | Always returns `true`. |
| `src/execution/analytics/spread_filter.py:58-80` | `SpreadFilter.evaluate_spread()` | **Execution analytics / Legacy** | Returns `allowed=True` for high spread ratios; only blocks UTC rollover hours `21, 22, 23` if `allow_rollover_trading=False`, and is not called in `OrderManager`. |
| `src/execution/persistent_socket.py:389-394` | `if max_spread_points is not None and live_spread_pts > max_spread_points` | **Execution reliability (Retry guard)** | Only aborts order *retries* if `max_spread_points` is explicitly passed. |
| `src/risk/position_sizing.py` + `OrderManager:307-311` | $20 net profit target feasibility vs R9 2% cap | **Position sizing / R9 risk cap** | At extreme spreads (e.g., 2,500+ pts on a 1,000-pt SL), spread cost makes $20 net profit infeasible within 2% risk and rejects via `Target Feasibility`. |

### Mandatory Spread Test Results
Executed via `scratch/audit_tests.py` (`XAUUSD`, SL distance = $10 / 1,000 pts):
- `Spread = 10 pts (1.0% of SL)` -> `passed=True`
- `Spread = 500 pts (50.0% of SL)` -> `passed=True`
- `Spread = 2500 pts (250.0% of SL)` -> `passed=False` (Rejected by `[FEASIBILITY]`: $20 net target requires > 2.0% R9 risk cap due to spread cost)

---

## 6. Grid and Averaging Audit

**Verdict:** **PARTIALLY IMPLEMENTED** (Permitted in active `OrderManager` and MQL5 EA; `PortfolioRiskEngine` still contains `no_grid_averaging` / `no_martingale` checks in telemetry).

- **Active `OrderManager.run_pre_trade_checklist()` (`src/execution/order_manager.py:321-356`):** Allows multiple independent same-direction setups on the same symbol (`XAUUSD` + `XAUUSD`). Rejects only opposite-direction conflicting positions on the same symbol (`p.symbol == candidate.symbol and p.order_type != candidate.direction`).
- **MQL5 EA (`mql5/Experts/PythonBridgeEA.mq5:126-127, 3854-3892`):** `InpNoMartingale = false` and `InpNoGridAveraging = false` by default, permitting multiple independent same-direction entries.
- **`PortfolioRiskEngine.evaluate_new_order_permission()` (`src/risk/portfolio_risk.py:542-554`):** Still checks `self.profile.rules.no_martingale` (`True` in `DEMO` profile) and `self.profile.rules.no_grid_averaging` (`True` in `DEMO` profile, blocking same-direction entry if an existing position is in drawdown). However, `OrderManager` (`order_manager.py:338-347`) invokes `portfolio_risk.evaluate_new_order_permission` **only for telemetry** and ignores its boolean return value.
- **Distinction:** The engine executes independent SMC/scalping signals with per-trade fixed fractional sizing (<= 2.0% R9 cap) rather than blind grid spacing or martingale lot multiplication.

---

## 7. Portfolio Risk Audit

**Verdict:** **PARTIALLY IMPLEMENTED** (Arbitrary position-count and daily-loss blockers removed from active path, but `OrderManager` bypasses `PortfolioRiskEngine` circuit breakers and has a config-key mismatch).

Every active blocking condition in the default `OrderManager.run_pre_trade_checklist()` (`legacy_filters_enabled=False`, `strict_three_symbol_universe=False`):

| File & Function | Condition | Trigger | Result | Permitted? |
|---|---|---|---|---|
| `order_manager.py:154-163` | Bridge health & market session | `bridge.ping()` false or `market_open == False` | Rejects order | **Permitted** (Broker/Execution reliability; note: omits `RETAIL`/`PROP` modes) |
| `order_manager.py:168-198` | Signal `APPROVED`, `SL > 0`, `stops_level` | Missing/invalid SL/TP or `sl_distance < stops_level` | Rejects order | **Permitted** (R9.2 & Broker validation) |
| `order_manager.py:205-210` | Valid Bid/Ask | `ask <= 0` or `bid <= 0` or `ask < bid` | Rejects order | **Permitted** (Market data validation) |
| `order_manager.py:220-224, 301-311` | Sizing & R9 2.0% cap | `risk_pct > 2.0%` or `size_result.is_approved == False` | Rejects order | **Permitted** (Position sizing / R9.1) |
| `order_manager.py:315-319` | Critical margin level | `margin_level < 150.0%` | Rejects order | **Permitted** (Account/margin constraint) |
| `order_manager.py:328-334` | Aggregate open risk cap | `agg_risk_pct > max_aggregate_risk_percent` (defaults to `8.0%`) | Rejects order | **Permitted** (Note: reads `max_aggregate_risk_percent` instead of `RiskConfig.max_aggregate_open_risk_percent` which is `6.0%`) |
| `order_manager.py:350-351` | Duplicate signal ID | `candidate.id in self._executed_signal_ids` | Rejects order | **Permitted** (Duplicate protection) |
| `order_manager.py:354-356` | Conflicting direction | Same symbol, opposite `order_type` | Rejects order | **Permitted** (Prevents accidental self-hedging) |
| `order_manager.py:385-386` | Free margin sufficiency | `size_result.margin_required > account.free_margin` | Rejects order | **Permitted** (Account/margin constraint) |
| `orchestrator.py:1054-1065, 1314-1325` | Inverse Coordination (`USDJPY` vs `XAUUSD`) | `inverse_coordination_enabled=True` & opposing direction under strong negative correlation | Rejects `USDJPY` candidate (`INVERSE_COORDINATION_REJECT`) | **Uncertain / Strategy-level** (Blocks valid `USDJPY` setups based on `XAUUSD` signal direction) |

**Defect:** Because `OrderManager` (`order_manager.py:338-347`) treats `self.portfolio_risk.evaluate_new_order_permission()` as non-blocking telemetry, **PortfolioRiskEngine's circuit breaker (`circuit_breaker_active`), drawdown safety buffer (`buffer_halted`), and `DEMO Account Safety Lock` (`acct_mode == "REAL"` when `LIVE_TRADING_ENABLED=false`) are NOT enforced by `OrderManager`**!

---

## 8. SMC Strategy Audit

**Verdict:** **FULLY IMPLEMENTED** (Core SMC detectors are causal and rule-aligned; minor precision normalization reliance on EA).

- **Swing Highs / Lows (`src/smc/market_structure.py:30-59`):** Symmetric `k`-bar lookback (`range(k, n - k)`). Confirmed only after `k` closed bars—**no look-ahead bias**.
- **BOS / CHoCH / MSS (`src/smc/market_structure.py:73-174`):** Enforces `bos_body_close_required` (`c.close > last_high`) and R1 (`HH+HL` for bullish, `LH+LL` for bearish). Verified by `test_smc_rulebook_golden.py` (10/10 PASS).
- **Closed-Candle Enforcement (`src/smc/strategy_engine.py:220-221`):** Filters `getattr(c, "complete", True)` before scanning, preventing intrabar repainting.
- **FVG / IFVG / Order Blocks (`src/smc/fvg_ob.py:57-405`):** Uses causal local ATR (`candles[max(0, i-14):i+1]`), 3-candle non-overlap (`c3.low > c1.high`), and forward-only mitigation checks (`candles[i+1:]`).
- **Liquidity Sweeps, Breaker Blocks, P/D Zones:** Implemented in `src/smc/liquidity.py`, `src/smc/advanced_market_structure.py`, and `src/smc/strategy_engine.py`.
- **Precision Note:** `strategy_engine.py:912-914` rounds `entry_price`, `stop_loss`, `take_profit` to 5 decimal places regardless of instrument digits (XAUUSD=2, USDJPY=3). Broker/EA normalization (`PythonBridgeEA.mq5`) is required before `OrderSend`.

---

## 9. Shadow-Mode Audit

**Verdict:** **FULLY IMPLEMENTED** (Shadow mode does not silently override live/demo execution; `dry_run` is explicitly separated).

- `config/strategy_config.json:123` sets `"shadow_mode": true` under `feature_flags`, which applies only to `RegimeDetector` (`src/regime/regime_detector.py:62`) and `MetaLabelingController` (`src/core/orchestrator.py:592`). Both features are disabled (`regime_detection: false`, `meta_labeling: false`) and non-blocking when `shadow_mode=true`.
- `config/settings.json:58` sets `"dry_run": false` and `"execution_mode": "DEMO"`.
- `src/core/config.py:582-584`: Enforces Ground Rule 3 (`LIVE_TRADING_ENABLED=true` required for `REAL`/`PROP`/`RETAIL`, otherwise falls back to `DEMO`, which executes against MT5 Demo via `BridgeClient`).
- **Companion Note:** `companion/service/orchestration/engine_controller.py:133, 141-143` launches `scripts/start_bot.py --dry-run` only when `operating_mode` is `DRY_RUN`/`OBSERVE` or when a **NETTING** account is detected (`netting_observe_only=True`).

---

## 10. Signal-to-Order Pipeline Audit

**Verdict:** **PARTIALLY IMPLEMENTED** (End-to-end execution, broker verification, and transaction ledger are solid, but symbol lockdown is bypassed by default config).

1. **Entry Loop:** `scripts/start_bot.py:217-224` iterates `orchestrator.continuous_scalper.get_ordered_symbols_for_cycle()` -> calls `orchestrator.run_scalping_cycle_for_symbol(sym)`, falling back to `orchestrator.run_cycle_for_symbol(sym)` if `None`.
2. **Universe & Schedule Guard:** `src/core/orchestrator.py:859, 1203` — **Skipped** when `strict_three_symbol_universe` is `False` (default).
3. **Market Data & MTF:** `MarketDataEngine.sync_symbol_history()` -> `MultiTimeframeAnalyzer.analyze()`.
4. **Strategy Scan:** `ContinuousScalpingEngine.scan_symbol_timeframes()` / `MultiPairScanner.scan_single_symbol()` / `SmcStrategyEngine.scan_for_opportunities()`.
5. **Inverse Coordination:** `InverseDirectionCoordinator` (`orchestrator.py:1036-1074, 1296-1334`).
6. **Pre-Trade Checklist & Sizing:** `orchestrator._execute_approved_candidate()` -> `OrderManager.run_pre_trade_checklist()` -> `PositionSizingEngine.calculate_lot_size()`.
7. **Idempotency & Ledger:** `TransactionManager.record_submission()` (`order_manager.py:678`).
8. **MT5 Submission & Retry:** `BridgeClient.execute_trade()` (`order_manager.py:723`) -> `BridgeServer` -> `PythonBridgeEA.mq5` (`ValidatePreTrade()` -> `OrderSend`).
9. **Broker Position Verification:** `order_manager.py:858-938` polls `bridge.get_positions()` up to 8 times (0.25s interval) and checks `ORDERS` before reporting `FILLED` / `PARTIALLY_FILLED` / `ACCEPTED` / `UNCONFIRMED`. **Never reports a generated signal as a filled trade without broker verification.**
10. **Post-Fill SL Enforcement & TCA:** `order_manager.py:949-986` attaches SL/TP if missing at broker or closes unprotected position, then logs to `TCAEngine`.

---

## 11. Multiple-Position Management Audit

**Verdict:** **FULLY IMPLEMENTED** (on Hedging accounts; Netting accounts are forced to observe-only in Companion).

- **Per-Ticket Tracking:** `TradeManagementEngine` (`src/risk/trade_management.py`) tracks state per `ticket` (`Dict[int, ...]`) with disk persistence for restart recovery.
- **Per-Position Actions:** `TradingBotOrchestrator.manage_active_positions()` (`src/core/orchestrator.py:1410-1611`) evaluates each position independently by `ticket` for $20 target full close (`QUICK_SCALP`), $20 floor lock + progressive ratchets (`PROFIT_RUNNING`), break-even, trailing SL, and partial close (`PARTIAL_CLOSE` with broker volume-step normalization).
- **Hedging vs Netting:** Verified by `tests/test_account_mode_hedging.py` (3/3 PASS). On **HEDGING** accounts, multiple independent positions on the same symbol maintain separate MT5 tickets. On **NETTING** accounts, MT5 aggregates positions on the same symbol into a single net position, making independent per-setup SL/TP/partial-close management impossible; `start_bot.py:76` detects `margin_mode_str` and `companion/service/orchestration/engine_controller.py:141-143` forces `DRY-RUN` if `netting_observe_only` is true.
- **Duplicate Protection:** Enforced via `sig_key` in `orchestrator._executed_signal_keys`, `continuous_scalper.is_duplicate_signal()`, `order_manager._executed_signal_ids`, and `transaction_manager.is_signal_executed_or_in_flight()`.

---

## 12. Companion Application Audit

**Verdict:** **PARTIALLY IMPLEMENTED** (Core lifecycle, auth, and config services work, but symbol lists and `engine_controller` calls are out of sync).

- **API & Auth & Engine Control:** `companion/service/api/server.py`, `config_service.py`, `engine_controller.py`, and `sync_service.py` pass all 7 tests in `tests/test_companion_control_service.py`.
- **Sync Defects Found:**
  1. `companion/service/orchestration/engine_controller.py:433-434` calls `universe.get_approved_symbols()` and `universe.get_resolved_symbols()`, which **do not exist** on `SpecializedSymbolUniverse` (it has `get_all_resolved_symbols()`), causing `AttributeError` caught silently by `try/except`.
  2. `companion/service/configuration/config_service.py:85-123` (`validate_bundle`) does **not** validate `settings.symbols` against `APPROVED_CANONICAL_SYMBOLS`.
  3. `companion/src/services/ipc.ts:438` hardcodes `allowedSymbols: ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]` in default config.
  4. `companion/src/components/SettingsModal.tsx:186` displays `placeholder="EURUSD, GBPUSD, USDJPY, XAUUSD"`.

---

## 13. Automated Testing Report

### Executed Test Suites
*(Note: An initial full-suite `pytest` run stalled at ~40% on a blocking test and was terminated; targeted suites covering all audit domains were executed directly and observed to pass.)*

| Test Suite / Script | Tests Run | Passed | Failed | Verdict |
|---|---|---|---|---|
| `tests/test_specialized_three_instrument_universe.py` | 26 | 26 | 0 | **PASS** *(uses test-overridden `strict_three_symbol_universe=True`)* |
| `tests/test_unrestricted_positions_and_spread.py` | 8 | 8 | 0 | **PASS** |
| `tests/test_pipeline_integration.py` | 1 | 1 | 0 | **PASS** |
| `tests/test_smc_rulebook_golden.py` | 10 | 10 | 0 | **PASS** |
| `tests/test_risk_management.py` | 6 | 6 | 0 | **PASS** |
| `tests/test_execution_bridge.py` | 1 | 1 | 0 | **PASS** |
| `tests/test_companion_control_service.py` | 7 | 7 | 0 | **PASS** |
| `tests/test_account_mode_hedging.py` | 3 | 3 | 0 | **PASS** |
| `tests/test_execution_analytics.py` | 5 | 5 | 0 | **PASS** |
| `tests/test_multi_connection_bridge.py` | 3 | 3 | 0 | **PASS** |
| `tests/test_mt5_bot_agent.py` | 18 | 18 | 0 | **PASS** |
| `tests/test_dual_mode_profit_management.py` | 11 | 11 | 0 | **PASS** |
| `tests/test_engine_lifecycle_fixes.py` | 4 | 4 | 0 | **PASS** |
| `scratch/audit_tests.py` (Phase 2, 3, 4 Mandatory Audit) | 3 groups | 2 groups | **1 group (Phase 2)** | **FAIL** (Default config allows `EURUSD`, `GBPUSD`, `US30`, `US100`, `NAS100`, `UNKNOWN_SYM`) |
| Live MT5 Terminal Order Execution | - | - | - | **NOT VERIFIED** (Audit rule: no live/demo orders submitted) |

---

## 14. Critical Defects

### CRITICAL
1. **Three-Instrument Lockdown Disabled in Default Production Config**
   - **Files:** `config/settings.json:32`, `src/core/config.py:332`, `src/core/orchestrator.py:859,1203,1369`, `src/execution/order_manager.py:137`
   - **Problem:** `strict_three_symbol_universe` defaults to `False` and is set to `false` in `config/settings.json`. Both `TradingBotOrchestrator` and `OrderManager` skip `symbol_universe.validate_or_reject()` when this flag is `False`, and `BridgeClient`/`PythonBridgeEA.mq5` have no allowlist.
   - **Trading Impact:** Unauthorized instruments (`EURUSD`, `GBPUSD`, `US30`, `US100`, `NAS100`, etc.) pass pre-trade validation and can reach MT5 order submission.
   - **Recommended Correction:** Set `"strict_three_symbol_universe": true` in `config/settings.json`, default `strict_three_symbol_universe: bool = True` in `AppConfig`, and enforce `get_symbol_universe().validate_or_reject()` unconditionally inside `OrderManager.run_pre_trade_checklist()`, `OrderManager.execute_signal()`, and `BridgeClient.execute_trade()`.

2. **`OrderManager` Ignores `PortfolioRiskEngine` Circuit Breakers & Safety Locks**
   - **Files:** `src/execution/order_manager.py:337-347`
   - **Problem:** `self.portfolio_risk.evaluate_new_order_permission()` is called in a `try/except` block solely to populate `candidate.metadata["portfolio_risk_eval"]`; its `(allowed, risk_reason)` return value is never checked to block orders.
   - **Trading Impact:** `PortfolioRiskEngine.circuit_breaker_active`, `buffer_halted`, `max_lot_cap`, and the `REAL`-account safety lock (`LIVE_TRADING_ENABLED=false`) are bypassed at the `OrderManager` level.
   - **Recommended Correction:** Enforce critical safety locks (`circuit_breaker_active`, `buffer_halted`, `REAL` account lock, `max_lot_cap`) in `OrderManager.run_pre_trade_checklist()` while keeping arbitrary position-count/daily-loss vetoes disabled.

### HIGH
3. **Unauthorized Symbols Persist in Active Configs, Agent, and Companion UI**
   - **Files:** `config/symbols.json`, `config/instruments.json`, `config/settings.json:48-57`, `config/fast_mode.json:45-48`, `agent/mt5_bot_agent.py:327`, `companion/src/services/ipc.ts:438`, `companion/src/components/SettingsModal.tsx:186`, `src/core/market_data.py:62`, `src/execution/continuous_scalper.py:99`, `src/engine/multi_pair_scanner.py:34-42`
   - **Problem:** Legacy symbol lists containing `EURUSD`, `GBPUSD`, `NAS100`, `US30`, `GBPJPY` remain active defaults across configs, agent, and UI, and `companion/service/configuration/config_service.py` does not reject unauthorized symbols in `validate_bundle()`.
   - **Trading Impact:** UI, agent, or fallback initializations can subscribe to, scan, or display unauthorized instruments.
   - **Recommended Correction:** Purge all unauthorized symbols from active configs/defaults/UI and enforce `APPROVED_CANONICAL_SYMBOLS` in `ConfigurationService.validate_bundle()`.

4. **Aggregate Open Risk Config Key Mismatch**
   - **Files:** `src/execution/order_manager.py:328`, `src/risk/portfolio_risk.py:587`, `src/core/config.py:175`
   - **Problem:** `OrderManager` and `PortfolioRiskEngine` read `getattr(self.config.risk, "max_aggregate_risk_percent", 8.0)`, whereas `RiskConfig` and `config/risk_config.json` define `max_aggregate_open_risk_percent` (`6.0`).
   - **Trading Impact:** Configured `max_aggregate_open_risk_percent` (`6.0%`) is silently ignored in `OrderManager`, always falling back to `8.0%`.
   - **Recommended Correction:** Read `max_aggregate_open_risk_percent` consistently.

### MEDIUM
5. **Companion `EngineController.get_status()` Calls Non-Existent `SpecializedSymbolUniverse` Methods**
   - **Files:** `companion/service/orchestration/engine_controller.py:433-434`, `src/core/symbol_universe.py:176`
   - **Problem:** Calls `universe.get_approved_symbols()` and `universe.get_resolved_symbols()`, which raise `AttributeError` and silently fall back to hardcoded lists.
   - **Recommended Correction:** Use `APPROVED_CANONICAL_SYMBOLS` and `universe.get_all_resolved_symbols()`.

6. **`.micro` Suffix Missing from `BrokerSymbolResolver.KNOWN_SUFFIXES`**
   - **Files:** `src/core/broker_resolver.py:16-18`, `src/core/symbol_universe.py:27-31`
   - **Problem:** `XAUUSD.micro` is rejected by `SpecializedSymbolUniverse.validate_or_reject()`.
   - **Recommended Correction:** Add `.micro` to `KNOWN_SUFFIXES` and `APPROVED_CANONICAL_ALIASES`.

7. **`OrderManager` Bridge Ping/Session Check Omits `RETAIL` and `PROP` Modes**
   - **Files:** `src/execution/order_manager.py:154`
   - **Problem:** `if self.config.execution_mode in [ExecutionMode.DEMO, ExecutionMode.REAL]:` skips `bridge.ping()` and `check_symbol_session()` in `RETAIL` or `PROP` mode.
   - **Recommended Correction:** Include `ExecutionMode.RETAIL` and `ExecutionMode.PROP`.

### LOW
8. **Hardcoded `round(..., 5)` in `SmcStrategyEngine`**
   - **Files:** `src/smc/strategy_engine.py:912-914`
   - **Problem:** Rounds prices to 5 decimals regardless of symbol `digits` (2 for `XAUUSD`/`BTCUSD`, 3 for `USDJPY`), relying on EA normalization.
   - **Recommended Correction:** Normalize to `symbol_info.digits` before order submission.

---

## 15. Final Compliance Matrix

| Requirement | Expected behavior | Actual status | Evidence | Verdict |
|---|---|---|---|---|
| Three-symbol restriction | Only XAUUSD, BTCUSD, USDJPY | `strict_three_symbol_universe` is `false` in `config/settings.json` & `AppConfig` | `config/settings.json:32`, `audit_tests.py` | **FAIL** |
| Unauthorized symbols | Cannot reach MT5 | `EURUSD`, `GBPUSD`, `US30`, `US100`, `NAS100` pass `OrderManager` under default config | `order_manager.py:137`, `audit_tests.py` | **FAIL** |
| Three-position minimum | Removed | Completely removed from `Orchestrator`, `OrderManager`, `PortfolioRisk`, `EA` | `orchestrator.py:1358`, `audit_tests.py` (Entry #1 at 0 pos) | **PASS** |
| Seven-position maximum | Removed | Completely removed from active execution path | `order_manager.py:321`, `PythonBridgeEA.mq5:118,3828` | **PASS** |
| More than seven entries | Supported subject to broker constraints | Entries #8, #9, #10 filled in mocked execution | `audit_tests.py` (tickets `7008`-`7010`) | **PASS** |
| Spread restrictions | No strategy-level veto | Strategy-level veto removed; extreme spreads fail $20 R9 feasibility | `order_manager.py:212-217`, `PythonBridgeEA.mq5:3510`, `audit_tests.py` | **PASS** |
| Grid restrictions | Old arbitrary limits removed | Permitted in `OrderManager` & `EA`; `PortfolioRisk` check non-blocking | `order_manager.py:338`, `PythonBridgeEA.mq5:127` | **PASS** |
| Averaging restrictions | Old arbitrary limits removed | Permitted in `OrderManager` & `EA`; `PortfolioRisk` check non-blocking | `order_manager.py:338`, `PythonBridgeEA.mq5:126` | **PASS** |
| Portfolio blockers | Arbitrary trade vetoes removed | Arbitrary count/daily-loss vetoes removed, but safety locks also bypassed | `order_manager.py:337-347`, `portfolio_risk.py:573` | **PARTIAL** |
| SMC strategy | Correctly validated | Causal swings, closed-candle enforcement, R1-R8 golden tests pass | `market_structure.py`, `test_smc_rulebook_golden.py` (10/10) | **PASS** |
| Shadow mode | Cannot silently override live mode | `dry_run=false`, `shadow_mode` only affects disabled/non-blocking ML/regime | `settings.json:58`, `strategy_config.json:123` | **PASS** |
| Execution pipeline | Valid setups reach submission | Reaches `BridgeClient.execute_trade()` & verifies position; lacks symbol lock | `order_manager.py:723-940`, `audit_tests.py` | **PARTIAL** |
| Multiple positions | Independently managed | Per-ticket state machine & actions; hedging verified | `trade_management.py`, `test_account_mode_hedging.py` (3/3) | **PASS** |
| Duplicate protection | Working | `sig_key`, `_executed_signal_ids`, `TransactionManager` in-flight guard | `orchestrator.py:406`, `order_manager.py:584` | **PASS** |
| MT5 synchronization | Accurate | Polls `get_positions()` & `ORDERS` before `FILLED`; reconciles timeouts | `order_manager.py:740-940`, `test_execution_bridge.py` | **PASS** |
| Companion application | Backend synchronized | Control service passes tests, but `ipc.ts`, `SettingsModal`, `engine_controller` out of sync | `engine_controller.py:433`, `ipc.ts:438`, `test_companion_control_service.py` | **PARTIAL** |

---

## 16. Final Recommendation

**Decision:** **NOT READY FOR LIVE VALIDATION** (and **NOT READY FOR DEMO TESTING** until Critical Defect #1 and Critical Defect #2 are resolved).

**Rationale:**
1. Under the default production configuration (`config/settings.json`), `"strict_three_symbol_universe": false` **disables** the three-instrument lockdown, allowing unauthorized symbols (`EURUSD`, `GBPUSD`, `US30`, `US100`, `NAS100`, and arbitrary strings) to pass `OrderManager.run_pre_trade_checklist()`.
2. `OrderManager` currently treats `PortfolioRiskEngine.evaluate_new_order_permission()` as non-blocking telemetry, leaving portfolio circuit breakers and drawdown halts unenforced at order submission.
3. Once `strict_three_symbol_universe` is unconditionally enforced (default `True` + `OrderManager`/`BridgeClient` enforcement), `PortfolioRiskEngine` safety halts are wired as blocking checks, and unauthorized symbols are purged from active configs/agent/Companion UI, the system will be **READY FOR DEMO TESTING** on a Hedging MT5 Demo account.
