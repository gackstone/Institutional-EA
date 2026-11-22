# Institutional EA — UI Copy & Short-Form Audit (`PART A`)

> **Branch:** `chore/audit-chart-copy`  
> **Single Source of Truth:** `companion/src/constants/uiCopy.ts`  
> **Glossary Access:** `Settings > Glossary` and `?` Quick Glossary button in the top bar.

---

## 1. Copy Reduction Principles Applied

1. **Removed Sentences & Helper Paragraphs**: Removed multi-line explanations beneath headings and in cards; replaced with 1–3 word titles, 1–2 word buttons, and 1-line tooltips.
2. **Standard Trading Short Forms**: Standardized across all 16 screens (`Bal`, `Eq`, `P&L`, `DD`, `Exp`, `Pos`, `Ord`, `Sig`, `Hist`, `Cfg`, `Ops`, `Err`, `Perf`, `Sess`, `Instr`, `Cmd`, `SL`, `TP`, `R`, `RR`, `Lot`, `Spr`, `Lev`, `Tgt`, `Cap`, `Max`, `Min`, `Avg`, `Conn`, `Sync`, `Live`, `Demo`).
3. **Short Operating Mode Codes with Tooltips**: `OBS` (Observe Only), `DRY` (Dry Run), `SCALP` (Demo Scalping), `FAST` (Demo Fast Execution), `ASSIST` (Demo Manual Assist), `BTC` (BTCUSD Sample Mode).
4. **Safety-Critical Clarity Retained**: Kept `DEMO · LIVE_TRADING_ENABLED=false`, `Pause`, `Stop`, `Close All`, `Flatten`, `Daily Loss`, `DD Cap`, and explicit two-step confirmation dialogs (`"Close all bot trades? Cancel / Close All"` and `"Flatten bot trades & engage STOP.flag? Cancel / Flatten"`).

---

## 2. Full String Inventory (Old Text -> New Text -> File)

### 2.1 Sidebar & Navigation (`companion/src/App.tsx`)
| Old Text | New Text | Tooltip | File |
| :--- | :--- | :--- | :--- |
| `Dashboard` | `Dashboard` | `Main trading terminal` | `companion/src/App.tsx` |
| `Market Watch` | `Quotes` | `Live broker quotes & specs` | `companion/src/App.tsx` |
| `Signals Pipeline` | `Signals` | `Strategy signals & risk gate` | `companion/src/App.tsx` |
| `Positions & Orders` | `Pos & Ord` | `Open positions & pending orders` | `companion/src/App.tsx` |
| `Trade History` | `History` | `Closed trade history` | `companion/src/App.tsx` |
| `Analytics` | `Perf` | `Performance analytics` | `companion/src/App.tsx` |
| `Engine Control` | `Engine` | `Engine & bridge lifecycle` | `companion/src/App.tsx` |
| `Risk Manager` | `Risk` | `Portfolio risk & caps` | `companion/src/App.tsx` |
| `Instruments` | `Instr` | `Approved instrument profiles` | `companion/src/App.tsx` |
| `Configuration` | `Config` | `JSON config & versions` | `companion/src/App.tsx` |
| `MT5 Terminal` | `MT5` | `MetaTrader 5 connection & EA` | `companion/src/App.tsx` |
| `Operations` | `Ops` | `Allowlisted operations runner` | `companion/src/App.tsx` |
| `Error Centre` | `Errors` | `Active & resolved system errors` | `companion/src/App.tsx` |
| `Event Logs` | `Logs` | `Structured runtime event logs` | `companion/src/App.tsx` |
| `System Health` | `Health` | `SQLite, drift & audit health` | `companion/src/App.tsx` |
| `Settings` | `Settings` | `Modes, pairing & glossary` | `companion/src/App.tsx` |
| `DEMO LOCK ACTIVE` | `DEMO LOCK` | `Execution locked to DEMO` | `companion/src/App.tsx` |

### 2.2 Top Status Bar & KPI Cards (`companion/src/components/screens/CoreTradingScreens.tsx`)
| Old Text | New Text | Tooltip | File |
| :--- | :--- | :--- | :--- |
| `Control Service Disconnected (127.0.0.1:8765) — Displaying cached DEMO state. Verify Python Control Service daemon.` | `Svc Offline (127.0.0.1:8765) · Cached DEMO` | `Local Python Control Service unreachable` | `CoreTradingScreens.tsx` |
| `Retry Reconnect` | `Reconnect` | `Retry Control Service connection` | `CoreTradingScreens.tsx` |
| `Stale Telemetry Warning — Last MT5 sync heartbeat exceeded 15s threshold.` | `Stale Sync (>15s)` | `MT5 sync heartbeat delayed over 15 seconds` | `CoreTradingScreens.tsx` |
| `Force Sync` | `Sync` | `Force immediate MT5 synchronization` | `CoreTradingScreens.tsx` |
| `EMERGENCY STOP.flag ENGAGED All new order entries are hard-blocked until cleared.` | `STOP.flag ACTIVE · Entries Blocked` | `Emergency kill switch active; clear to allow entries` | `CoreTradingScreens.tsx` |
| `Clear STOP.flag` | `Clear Stop` | `Clear emergency STOP.flag` | `CoreTradingScreens.tsx` |
| `ZMQ Bridge 5555/5556` | `ZMQ 5555/5556` | `Bridge TCP sockets 5555 (EA) & 5556 (IPC)` | `CoreTradingScreens.tsx` |
| `Telegram: READY` | `TG Ready` | `Telegram alerts & commands ready (click to test)` | `CoreTradingScreens.tsx` |
| `Balance / Equity` | `Bal / Eq` | `Account Balance & Equity` | `CoreTradingScreens.tsx` |
| `Today P&L (+R)` | `Today P&L` | `Realized + floating P&L today in USD and R` | `CoreTradingScreens.tsx` |
| `1R Unit Risk = $127.40 (0.50%)` | `1R = $127.40 (0.5%)` | `1R monetary risk unit (0.50% of balance)` | `CoreTradingScreens.tsx` |
| `Daily Loss vs Limit` | `Daily Loss` | `Daily realized loss used vs hard daily limit` | `CoreTradingScreens.tsx` |
| `Total DD vs Cap` | `DD vs Cap` | `Total drawdown used vs maximum drawdown cap` | `CoreTradingScreens.tsx` |
| `Open Exposure` | `Open Exp` | `Open Bot, Manual & Pending orders` | `CoreTradingScreens.tsx` |
| `Next Schedule Switch` | `Next Sess` | `Countdown to next schedule mode transition` | `CoreTradingScreens.tsx` |

### 2.3 Live Chart & Drawing Overlays (`companion/src/components/LiveTradingChart.tsx`)
| Old Text | New Text | Tooltip | File |
| :--- | :--- | :--- | :--- |
| `Liquidity (PDL/PWH)` | `Liq` | `Toggle Liquidity Pools (PDH/PDL/PWH/PWL/EQH/EQL)` | `LiveTradingChart.tsx` |
| `FVG/OB` | `FVG/OB` | `Toggle Fair Value Gaps & Order Blocks` | `LiveTradingChart.tsx` |
| `Structure (MSS/CHoCH)` | `Struct` | `Toggle Market Structure (MSS/CHoCH/BOS)` | `LiveTradingChart.tsx` |
| `Sessions` | `Sess` | `Toggle Session & Killzone boxes (Asia/LDN/NY)` | `LiveTradingChart.tsx` |
| `Trade Labels` | `Trades` | `Toggle Entry, SL, TP, R zones & signals` | `LiveTradingChart.tsx` |
| `Tighten-Only SL` | `Tighten-SL` | `Rule R9.3: Stop Loss can only be tightened, never widened` | `LiveTradingChart.tsx` |

### 2.4 Right Column & Bottom Panels (`companion/src/components/screens/CoreTradingScreens.tsx`)
| Old Text | New Text | Tooltip | File |
| :--- | :--- | :--- | :--- |
| `Engine Control & Supervisor` | `Engine & Mode` | `Supervisor PIDs, warm-up & operating mode` | `CoreTradingScreens.tsx` |
| `Supervisor` / `Bridge IPC` / `Warm-Up Bars` | `Eng PID` / `Brg PID` / `Warmup` | `Process IDs and historical bar warm-up` | `CoreTradingScreens.tsx` |
| `Operating Mode (DEMO-Locked)` | `Mode (DEMO)` | `Select execution mode (Live trading disabled)` | `CoreTradingScreens.tsx` |
| `OBSERVE` / `DRY_RUN` / `DEMO_SCALPING` / `DEMO_FAST` / `DEMO_MANUAL_ASSIST` | `OBS` / `DRY` / `SCALP` / `FAST` / `ASSIST` | Full mode description in tooltip | `CoreTradingScreens.tsx` |
| `Open Positions & Orders` | `Pos & Ord` | `Active MT5 positions and pending orders` | `CoreTradingScreens.tsx` |
| `Tighten-only stop policy enforced · Click symbol to focus chart` | *(Removed helper line; moved to tooltip)* | `Click symbol to focus chart; SL is tighten-only` | `CoreTradingScreens.tsx` |
| `All Positions` / `Bot Owned` / `Manual` | `All` / `Bot` / `Man` | `Filter positions by ownership` | `CoreTradingScreens.tsx` |
| `Partial 50%` / `BE+ Lock` / `Tighten SL` / `Widen/Remove SL` / `Close` | `50%` / `BE+` / `SL+` / `Widen Locked` / `Close` | `Partial close 50%`, `Lock Break-Even+`, `Tighten SL`, `Locked by R9.3`, `Close at market` | `CoreTradingScreens.tsx` |
| `Live Trade Timeline` | `Timeline` | `Real-time trade lifecycle events` | `CoreTradingScreens.tsx` |
| `Risk Manager (DEMO / PROP / LIVE Profiles)` | `Risk Profiles` | `Profile risk caps & portfolio utilization` | `CoreTradingScreens.tsx` |
| `Gold–USDJPY Inverse Coordination` | `XAU/JPY Corr` | `60m rolling inverse correlation & hedge gate` | `CoreTradingScreens.tsx` |
| `Schedule & Instruments` | `Sess & Instr` | `Active session schedule & instrument status` | `CoreTradingScreens.tsx` |
| `System Health & Drift Guards` | `Health & Drift` | `Heartbeat latency, queue depth, CUSUM/PSI & TCA` | `CoreTradingScreens.tsx` |
| `Manual Position Adoption` | `Manual Guard` | `Adopted manual trades & protective SL sync` | `CoreTradingScreens.tsx` |
| `Recent Trades` | `Recent Hist` | `Latest closed trades` | `CoreTradingScreens.tsx` |
| `Two-Step Confirmation (Step 1 of 2): Close All Bot Positions` | `Close all bot trades? (1/2)` / `Confirm close all? (2/2)` | `Explicit two-step confirmation for market liquidation` | `CoreTradingScreens.tsx` |

### 2.5 Secondary Screens & Modals (`ExecutionRiskScreens.tsx`, `OperationsSystemScreens.tsx`, `MonitoringSettingsScreens.tsx`, Modals)
| Old Text | New Text | Tooltip | File |
| :--- | :--- | :--- | :--- |
| `Trading Engine Lifecycle Controller` + helper sentence | `Engine Lifecycle` | `Start, pause, stop, restart or emergency-stop engine` | `CoreTradingScreens.tsx` |
| `Live Market Watch & Broker Specifications` + helper sentence | `Market Quotes` | `Live MT5 bid/ask, spread, lot steps & stops level` | `CoreTradingScreens.tsx` |
| `Unfiltered Signal Pipeline & Risk Authorization` + helper sentence | `Signal Gate` | `Unfiltered strategy signals evaluated by PortfolioRiskEngine` | `CoreTradingScreens.tsx` |
| `Open MT5 Positions` + helper sentence | `Open Pos` | `MT5 positions classified by Magic Number` | `ExecutionRiskScreens.tsx` |
| `Close All Bot Positions` | `Close Bot Pos` | `Liquidate all bot-owned positions` | `ExecutionRiskScreens.tsx` |
| `Persisted Trade History` + helper sentence | `Trade Hist` | `Closed trades persisted in SQLite` | `ExecutionRiskScreens.tsx` |
| `Authoritative PortfolioRiskEngine` | `Risk Engine` | `Kill switch, daily P&L, drawdown & margin utilization` | `ExecutionRiskScreens.tsx` |
| `Approved Instrument Profiles` | `Instruments` | `Configured symbol specifications` | `ExecutionRiskScreens.tsx` |
| `Authoritative Configuration Editor` | `Config Editor` | `Edit, preview, apply & rollback JSON config` | `OperationsSystemScreens.tsx` |
| `MetaTrader 5 Terminal Synchronization` | `MT5 Terminals` | `Scan, deploy EA & launch MT5 terminals` | `OperationsSystemScreens.tsx` |
| `Approved Operations Runner (Fixed Allowlist)` | `Ops Runner` | `Execute allowlisted diagnostic & sync scripts` | `OperationsSystemScreens.tsx` |
| `Error Centre` | `Errors` | `Active & resolved runtime errors` | `OperationsSystemScreens.tsx` |
| `Structured Event Logs` | `Event Logs` | `Filterable system event log stream` | `MonitoringSettingsScreens.tsx` |
| `Performance Analytics (DEMO Execution Metrics)` | `Performance` | `Closed trade count, win rate, net P&L & profit factor` | `MonitoringSettingsScreens.tsx` |
| `System Health & Embedded SQLite Persistence` | `System Health` | `SQLite schema health, DEMO verification & audit trail` | `MonitoringSettingsScreens.tsx` |
| `Operating Mode & Safety Locks` | `Modes & Glossary` | `Switch operating modes, run diagnostics & view short-form glossary` | `MonitoringSettingsScreens.tsx` |
| `System Pre-Flight Diagnostics` (`DiagnosticsModal.tsx`) | `Diagnostics` | `Hardware, port, MT5 & EA pre-flight checks` | `DiagnosticsModal.tsx` |
| `Institutional EA Cloud Pairing` (`PairingModal.tsx`) | `Cloud Pairing` | `Link 6-character pairing code` | `PairingModal.tsx` |
| `Telegram Remote Control` (`TelegramPairingModal.tsx`) | `Telegram Setup` | `Pair Telegram bot token & test alerts` | `TelegramPairingModal.tsx` |
