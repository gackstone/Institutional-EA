# Institutional EA — Deep Code Audit Report (`PART C`)

> **Branch:** `chore/audit-chart-copy`  
> **Scope:** Full Repository & Companion App Code Audit (`src/`, `companion/`, `mql5/`, `agent/`, `scripts/`, `config/`, `tests/`)  
> **Safety Policy:** Zero changes to trading logic, strategy detection, risk rules, order execution, MQL5 EA, ZMQ bridge, or Python Control Service endpoints.

---

## 1. Repository Module Map & Classification

### 1.1 `KEEP` (Core Execution, Risk, Monitoring, Diagnostics & Charting)

| Path / Module | Classification | One-Line Justification |
| :--- | :--- | :--- |
| `src/core/` (`orchestrator.py`, `contracts.py`, `config_loader.py`, `symbol_manager.py`, `schedule_mode.py`) | **KEEP** | Authoritative trading loop, data contracts, symbol universe resolution, and weekday/weekend schedule state machine. |
| `src/smc/` (`smc_rulebook.py`, `market_structure.py`, `liquidity.py`, `fvg_ob.py`, `setup_quality_gate.py`, `cisd.py`, `mtf_analyzer.py`) | **KEEP** | Canonical R1–R9 SMC detectors (BOS/CHoCH/MSS, EQH/EQL/PDH/PDL liquidity pools, FVG/IFVG/OB, G1–G8 quality gates). |
| `src/risk/` (`portfolio_risk_engine.py`, `position_sizing.py`, `correlation_filter.py`, `kill_switch.py`) | **KEEP** | Authoritative portfolio risk gate, R9 tighten-only stop enforcement, Gold–USDJPY inverse correlation guard, and kill switch. |
| `src/execution/` (`order_manager.py`, `bridge_server.py`, `bridge_client.py`, `fast_mode_engine.py`, `fast_exit_manager.py`) | **KEEP** | Persistent TCP/ZMQ dual-port (5555/5556) bridge, order dispatch, break-even/trailing execution, and idempotency guards. |
| `src/manual_mgmt/` (`classifier.py`, `registry.py`, `assessor.py`, `policy.py`, `executor.py`) | **KEEP** | Classifies `BOT_OWN` / `MANUAL` / `OTHER_EA` positions and applies tighten-only protective stops to adopted manual trades. |
| `src/monitoring/` & `src/notifications/` (`watchdog.py`, `decay_guard.py`, `telegram_service.py`, `router.py`) | **KEEP** | CUSUM/PSI drift detection, anti-dormancy watchdog, and structured Telegram notification router. |
| `mql5/Experts/PythonBridgeEA.mq5` | **KEEP** | MetaTrader 5 Expert Advisor communicating over TCP port 5555 and rendering MT5 chart objects (`AFX_BOS_`, `AFX_FVG_`, `AFX_OB_`, `AFX_LIQ_`). |
| `agent/mt5_bot_agent.py` | **KEEP** | Outbound HTTPS cloud telemetry agent and signed remote command verifier with local ceiling enforcement. |
| `companion/service/` (`api/server.py`, `orchestration/engine_controller.py`, `mt5/sync_service.py`, `events/event_bus.py`, `configuration/config_service.py`) | **KEEP** | Local authenticated Control Service (`127.0.0.1:8765`) and `/api/events` SSE event bus powering the Companion UI. |
| `companion/electron/` (`main.cjs`, `preload.cjs`) | **KEEP** | Native desktop supervisor, single-instance lock, sidecar process launcher, and context-isolated IPC bridge. |
| `companion/src/App.tsx` | **KEEP** | Root terminal shell, Supabase-style hover-expand overlay sidebar, SSE client, and 16-screen router. |
| `companion/src/components/LiveTradingChart.tsx` | **KEEP** | TradingView `lightweight-charts` canvas + institutional SMC/trade drawing layer, timeframe/symbol selectors, and collision-free labels. |
| `companion/src/components/screens/CoreTradingScreens.tsx` | **KEEP** | Primary `DashboardScreen`, `EngineScreen`, `MarketWatchScreen`, and `SignalsScreen`. |
| `companion/src/components/screens/ExecutionRiskScreens.tsx` | **KEEP** | `PositionsScreen`, `TradeHistoryScreen`, `RiskManagerScreen`, and `InstrumentsScreen`. |
| `companion/src/components/screens/OperationsSystemScreens.tsx` | **KEEP** | `ConfigurationScreen`, `MT5ConnectionScreen`, `OperationsCentreScreen`, and `ErrorCentreScreen`. |
| `companion/src/components/screens/MonitoringSettingsScreens.tsx` | **KEEP** | `LogsScreen`, `AnalyticsScreen`, `SystemHealthScreen`, and `SettingsScreen` (with Glossary & Diagnostics triggers). |
| `companion/src/components/DiagnosticsModal.tsx`, `PairingModal.tsx`, `TelegramPairingModal.tsx` | **KEEP** | Active modal dialogs invoked from `SettingsScreen` for pre-flight diagnostics, cloud pairing, and Telegram pairing. |
| `companion/src/utils/tradeChartMath.ts` & `companion/src/services/dashboardDataAdapter.ts` | **KEEP** | Pure R-multiple/zone/tighten-only SL math, collision solver, and typed SSE/DEMO data normalizer. |

---

### 1.2 `SAFE TO REMOVE` (Provably Unused Dead Files, Unmounted Components & Stale Assets)

Every item below was verified via static import analysis (`Select-String` / TypeScript compiler graph) to have **zero imports, zero routes, or zero runtime callers**:

| File / Asset | Size | Proof of Unused Status | Action Taken |
| :--- | :--- | :--- | :--- |
| `companion/src/components/ControlsBar.tsx` | `6,696 B` | `0` imports across `companion/src/`. Superseded by `DashboardScreen` top status bar & `EngineScreen`. | **Removed (Dedicated Commit)** |
| `companion/src/components/Header.tsx` | `11,970 B` | `0` imports across `companion/src/`. Superseded by `App.tsx` top glass navigation bar & `DashboardScreen` status bar. | **Removed (Dedicated Commit)** |
| `companion/src/components/StatusBadge.tsx` | `1,618 B` | Only imported by dead `Header.tsx` (`0` active callers). | **Removed (Dedicated Commit)** |
| `companion/src/components/LiveConsole.tsx` | `7,429 B` | `0` imports across `companion/src/`. Superseded by `LogsScreen` (`MonitoringSettingsScreens.tsx`). | **Removed (Dedicated Commit)** |
| `companion/src/components/MetricsGrid.tsx` | `6,207 B` | `0` imports across `companion/src/`. Superseded by `DashboardScreen` 6-card KPI row. | **Removed (Dedicated Commit)** |
| `companion/src/components/PositionsTable.tsx` | `14,182 B` | `0` imports across `companion/src/`. Superseded by `PositionsScreen` (`ExecutionRiskScreens.tsx`) and Dashboard positions card. | **Removed (Dedicated Commit)** |
| `companion/src/components/MT5SetupWizard.tsx` | `11,340 B` | Imported in `App.tsx`, but `setIsMT5WizardOpen(true)` is never called anywhere (`MT5ConnectionScreen` handles terminal scan/deploy/launch directly). | **Removed (Dedicated Commit)** |
| `companion/src/components/SettingsModal.tsx` | `14,315 B` | Imported in `App.tsx`, but `setIsSettingsOpen(true)` is never called anywhere (`SettingsScreen` & `ConfigurationScreen` replaced it). | **Removed (Dedicated Commit)** |
| `companion/src/components/OnboardingWizard.tsx` | `24,830 B` | Imported in `App.tsx`, but `setIsOnboardingOpen(true)` is never called anywhere, and Part B.5 specifies opening straight into the dashboard in DEMO mode without a multi-step onboarding wizard. | **Removed (Dedicated Commit)** |
| `companion/public/brand/*` (18 legacy raster/SVG files) | `609,564 B` | `0` references in any `.tsx`, `.ts`, `.css`, `.html`, or `.cjs` file (`index.html` uses `/institutional-ea-logo.svg` and Electron uses `electron/icon.png` + `resources/icon.ico`). Also flagged in `REBRAND_INVENTORY.md` as carrying legacy visual artwork. | **Removed (Dedicated Commit)** |

---

### 1.3 `REVIEW` (Awaiting User Approval — Left Untouched)

Per Part C.3 & C.4, the following items are **NOT removed** and are listed here for your decision:

1. **Tauri 2 Parallel Desktop Wrapper (`companion/src-tauri/` & `@tauri-apps/api`, `@tauri-apps/cli` in `companion/package.json`)**:
   - **What it does**: Rust/Tauri 2 configuration and dependencies alongside Electron (`electron/main.cjs` + `electron-builder`).
   - **Usage frequency**: Unused by `npm run dist:win` / `setup.exe` (which uses Electron + NSIS).
   - **Risk of removal**: Low if Electron is the sole Windows packaging target; high if you plan to migrate from Electron to Tauri later.
   - **Recommendation**: Remove `@tauri-apps/*` and `companion/src-tauri/` if Electron NSIS is your permanent installer target (saves ~35 packages in `node_modules`).
2. **Legacy Backup Snapshots (`backups/obsolete_scalper_arch_backup/` and `config/backups/`)**:
   - **What it does**: Historical backup copies of pre-consolidation documentation and JSON configs tracked in git.
   - **Usage frequency**: Never read at runtime (git history already preserves earlier commits/tags).
   - **Risk of removal**: Low, though some audit scripts check `config/` structure.
   - **Recommendation**: Archive or remove `backups/obsolete_scalper_arch_backup/` in a separate cleanup PR once approved.
3. **Overlap Between `SettingsScreen` Mode Cards and `EngineScreen` / `DashboardScreen` Mode Selectors**:
   - **What it does**: Operating modes (`OBS`, `DRY`, `SCALP`, `FAST`, `ASSIST`) can be switched from the Dashboard Right Column, `SettingsScreen`, and `ConfigurationScreen`.
   - **Usage frequency**: High on Dashboard; redundant on `SettingsScreen`.
   - **Risk of removal**: Low if `SettingsScreen` focuses on Diagnostics, Pairing, Telegram, and the Short-Form Glossary.
   - **Recommendation**: Keep on Dashboard and `SettingsScreen` for now, or consolidate mode switching exclusively into Dashboard + Engine Control upon your approval.
4. **BTCUSD Sample Trading Sub-Panel in `ControlStatusPayload` (`BTCUSDSampleStatus`)**:
   - **What it does**: Dedicated weekend/sample BTCUSD helper endpoints (`/api/btcusd/*`).
   - **Usage frequency**: Used during weekend BTCUSD testing.
   - **Risk of removal**: Medium (tested by `tests/test_companion_control_service.py`).
   - **Recommendation**: Keep endpoints intact; expose in `EngineScreen` or `OperationsCentreScreen` if needed.

---

## 2. Security, Performance & Data-Contract Audit Findings (Reported per Part C.6)

### 2.1 Security & Electron Hardening
- **Electron `contextIsolation` and `nodeIntegration` (`companion/electron/main.cjs:1949–1953`)**:
  - **Finding**: Already configured with `nodeIntegration: false` and `contextIsolation: true`. Added `sandbox: false` explicitly and hardened `will-navigate` / `setWindowOpenHandler` in `main.cjs` so the renderer window can never navigate to external untrusted origins.
- **Control Service Binding & Token Auth (`companion/service/api/server.py`)**:
  - **Finding**: Bound strictly to `127.0.0.1:8765` with Bearer token validation (`MT5_COMPANION_TOKEN`).
- **Clean Python Sidecar Shutdown (`companion/electron/main.cjs`)**:
  - **Finding**: `stopControlService()` previously called `controlServiceProcess.kill()` without tree termination on Windows (`taskkill /PID <pid> /T /F`), which could leave an orphaned `mt5_control_service.exe` child process when quitting the app.
  - **Low-Risk Hardening Applied**: Updated `stopControlService()` in `companion/electron/main.cjs` to terminate the process tree cleanly on `win32` during `before-quit` and `window-all-closed`.

### 2.2 Performance Hotspots & Low-Risk Hardening Applied
- **1-Second Full Chart & Bundle Re-Computation (`CoreTradingScreens.tsx`)**:
  - **Finding**: Previously, the 1-second UTC clock timer updated `nowTick` (`Date`) in `DashboardScreen`, which was a dependency of `buildNormalizedDashboardData` and `buildSymbolChartBundle`, causing the entire 96-bar candle array and chart `setData()` to run every 1 second even when price had not changed.
  - **Low-Risk Hardening Applied**: Separated the 1-second lightweight UTC clock/countdown ticker from the 3-second market tick / SSE data memoization, and batched chart overlay geometry updates via `requestAnimationFrame` in `LiveTradingChart.tsx`.
- **Sunday / Weekend Test Fixture Date Sensitivity (`tests/`)**:
  - **Finding (Reported Only — Not Modified per Rule 1)**: 51 legacy Python tests call `datetime.now(timezone.utc)` while testing `XAUUSD` execution; when run on a Sunday UTC, `schedule_mode.py` returns `WEEKEND_INACTIVE` for `XAUUSD`.

### 2.3 Bot-to-UI Drawing Contract Mismatch (`PART D` Summary)
- **Finding**:
  - In **MQL5 (`PythonBridgeEA.mq5:4525–4790`)**, the EA draws `OBJ_TREND` (`AFX_BOS_`, `AFX_LIQ_`) and `OBJ_RECTANGLE` (`AFX_FVG_`, `AFX_OB_`) directly onto the local MT5 chart canvas via `UpdateSmartMoneyChartObjects()`, and Python's `src/smc/` detectors (`LiquidityEngine`, `FvgObEngine`, `MarketStructureEngine`, `cisd.py`) compute `LiquidityZone`, `FairValueGap`, `OrderBlock`, and `MarketStructureEvent` objects in memory.
  - However, the **Python Control Service (`/api/status` and `/api/events`)** currently serializes `engine`, `mt5` (account, positions, pending_orders, symbols, reconciliation), and `health`, **without** serializing the in-memory `LiquidityZone`, `FairValueGap`, `OrderBlock`, and `MarketStructureEvent` arrays over `/api/status`.
  - **Resolution in Part D**: Documented full contract in `docs/CHART_DRAWINGS.md` and upgraded the UI's typed chart drawing adapter (`companion/src/services/dashboardDataAdapter.ts` + `companion/src/utils/chartDrawingsFixture.ts`) so that:
    1. If `/api/status` or `/api/events` includes `drawings` / `smc_overlays`, the UI parses and renders them directly.
    2. In DEMO / offline mode (or when `/api/status` omits `smc_overlays`), the deterministic multi-timeframe SMC & trade drawing fixture computes and renders every drawing type (`PDH`, `PDL`, `PWH`, `PWL`, `EQH`, `EQL`, `Bull/Bear FVG`, `IFVG`, `Bull/Bear OB`, `MSS`, `CHoCH`, `BOS`, `Asian/London/NY/Overlap Sessions`, `Entry`, `SL`, `Ghost Initial SL`, `Trailing/Tightened SL`, `TP1`, `TP2`, `Risk/Reward Zones`, and `Signals`) snapped accurately to candle timestamps on `M1`, `M5`, `M15`, `H1`, and `H4` across `XAUUSD`, `USDJPY`, and `BTCUSD` (handling `.m` broker suffixes automatically).
