# MT5 001 — Complete System Architecture & Dependency Map
**Forensic Technical Intelligence Audit**  
**Classification:** Institutional Algorithmic Trading Systems Audit  
**System Target:** MT5 001 Automated Trading System  
**Auditor:** Principal Quantitative Trading Systems Architect & Financial Systems Auditor  
**Date of Audit:** November 2026  

---

## 1. Executive Architectural Overview

The **MT5 001** automated trading system is a hybrid quantitative execution platform combining native MetaTrader 5 (MQL5) execution infrastructure with a modular Python 3.10+ algorithmic engine, an Electron-based desktop supervisor companion, and an outbound-only cloud telemetry/control agent (ArcadeFX Cloud).

The system bifurcates high-level quantitative decision-making (market regime detection, multi-timeframe liquidity mapping, order block/FVG detection, statistical meta-labeling, fractional Kelly sizing, and CUSUM decay guarding) into Python, while delegating low-latency pre-execution safety gating, broker ticket management, trailing stop modifications, and emergency circuit breakers to a 4,773-line native Expert Advisor (`mql5/Experts/PythonBridgeEA.mq5`).

```
                    ┌────────────────────────────────────────────────────────┐
                    │               MetaTrader 5 Client Terminal             │
                    │  ┌──────────────────────────────────────────────────┐  │
                    │  │            PythonBridgeEA.mq5 (v3.10)            │  │
                    │  │  - Single/Multi-chart attachment (M1/M5/M15/H1)  │  │
                    │  │  - Pre-trade risk gating & lot calculation       │  │
                    │  │  - Autonomous position trail, BE, & profit lock  │  │
                    │  │  - Native trade transaction event listeners      │  │
                    │  └────────────────────────┬─────────────────────────┘  │
                    └───────────────────────────┼────────────────────────────┘
                                                │ TCP Socket IPC (Localhost)
                                                │ Port 5555: MQL5 Data & Trade Link
                                                │ Port 5556: Local IPC Admin Switchboard
                    ┌───────────────────────────┴────────────────────────────┐
                    │            Python Algorithmic Trading Engine           │
                    │  ┌──────────────────────────────────────────────────┐  │
                    │  │     src/execution/bridge_server.py (Daemon)      │  │
                    │  │  - Multi-connection async socket dispatcher      │  │
                    │  │  - SO_EXCLUSIVEADDRUSE socket isolation          │  │
                    │  │  - Heartbeat supervisor & timeout monitor        │  │
                    │  └────────────────────────┬─────────────────────────┘  │
                    │                           │                            │
                    │  ┌────────────────────────┴─────────────────────────┐  │
                    │  │       src/core/orchestrator.py (Master Engine)   │  │
                    │  │  - ContinuousScalpingEngine (M1/M5/M15 models)   │  │
                    │  │  - SmcStrategyEngine (W1->M15 institutional SMC) │  │
                    │  │  - SetupQualityGate (G1-G8 hard gating)          │  │
                    │  │  - PositionSizingEngine ($5 floor, R9 2.0% cap)  │  │
                    │  │  - PortfolioRiskEngine (Drawdown/Correlation)    │  │
                    │  │  - MetaLabelingController & KellyEngine          │  │
                    │  │  - CUSUM DecayGuard & HealthMonitor              │  │
                    │  └────────────────────────┬─────────────────────────┘  │
                    └───────────────────────────┼────────────────────────────┘
                                                │
         ┌──────────────────────────────────────┼──────────────────────────────────────┐
         │                                      │                                      │
         ▼                                      ▼                                      ▼
┌─────────────────────────┐        ┌─────────────────────────┐        ┌─────────────────────────┐
│ Desktop Companion UI    │        │  ArcadeFX Cloud Agent   │        │ Telegram Notification   │
│ companion/electron/     │        │  agent/mt5_bot_agent.py │        │ src/notifications/      │
│ main.cjs (Node/React)   │        │  Outbound HTTPS Only    │        │ Rate-limited alerts &   │
│ - 6 supervised services │        │  - HMAC-SHA256 signed   │        │ 2-step command console  │
│ - Process health watch  │        │  - Telemetry heartbeats │        │ - /status, /pause,      │
│ - Local credentials     │        │  - Strict local limits  │        │   /killswitch, /balance │
└─────────────────────────┘        └─────────────────────────┘        └─────────────────────────┘
```

---

## 2. Component Inventory & Responsibilities

| Component | Primary Location | Core Responsibility | Upstream Inputs | Downstream Outputs | Communication Channel |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Native Bridge EA** | `mql5/Experts/PythonBridgeEA.mq5` | Broker order execution, local tick auditing, autonomous trailing/break-even management, emergency stop loss validation, and GUI level rendering. | Tick stream, broker rates, order commands from Python. | Account state, open position ticks, order fills, rejection codes. | TCP Client (`127.0.0.1:5555`), Terminal API. |
| **Bridge Server Daemon** | `src/execution/bridge_server.py` | Asynchronous TCP IPC server managing multi-client socket communication between EA and Python engine. | MQL5 raw JSON messages, local IPC administrative requests. | Normalized JSON responses to orchestrator, CLI, and GUI. | TCP Listeners on Port 5555 (MQL5) and 5556 (Admin IPC). |
| **Trading Orchestrator** | `src/core/orchestrator.py` | Master coordination loop. Manages market data synchronization, session timers, scalping cycles, SMC opportunity scans, risk approval, and order lifecycle. | Multi-timeframe OHLCV candles, broker account status. | Evaluated signals, trade orders, diagnostic reports, telegram alerts. | In-memory Python method calls, IPC client to Bridge. |
| **Continuous Scalper** | `src/execution/continuous_scalper.py` | Low-latency state-driven scalping across M1, M5, and M15 timeframes. Implements Momentum Continuation, Pullback, and Sweep/Breakout models. | M1, M5, M15, H1 closed candles, live bid/ask spreads. | `SignalCandidate` objects with ATR-calibrated SL/TP. | In-memory method calls to Orchestrator and Sizing Engine. |
| **SMC Strategy Engine** | `src/smc/strategy_engine.py` | Institutional Smart Money Concepts pipeline. Evaluates W1/D1 liquidity sweeps, H4 market structure shifts, M15 Order Blocks, and FVGs. | W1, D1, H4, H1, M15 candles, Weekly/Daily reference levels. | `SignalCandidate` objects with strict R:R >= 2.0. | In-memory method calls to Setup Quality Gate. |
| **Setup Quality Gate** | `src/smc/setup_quality_gate.py` | Phase 2 validation firewall enforcing Rules R1 through R9 across 8 independent hard gates (G1-G8). | Raw `SignalCandidate`, `MultiTimeframeContext`, structural state. | `QualityGateVerdict` (passed, blocked, reason codes, size multiplier). | In-memory synchronous evaluation prior to risk sizing. |
| **Position Sizing Engine** | `src/risk/position_sizing.py` | Mathematical lot-size calculator enforcing Rule R9 (hard 2.0% cap), $5 operating capital floor, tick value quantization, and margin limits. | `AccountInfo`, `SymbolInfo`, structural SL distance, account tier. | `PositionSizeResult` (approved volume, monetary risk, min balance needed). | Synchronous calculation invoked by Order Manager. |
| **Portfolio Risk Engine** | `src/risk/portfolio_risk.py` | Aggregate account-level circuit breaker tracking daily/weekly loss limits, consecutive losses, trailing drawdown, and correlation clusters. | Real-time equity updates, closed trade profit/loss events. | Permission approval (`evaluate_new_order_permission`), circuit breaker halt. | Synchronous pre-trade authorization check. |
| **Order Manager** | `src/execution/order_manager.py` | Pre-trade checklist verification, idempotent ticket tracking, broker response reconciliation, and order submission. | Approved candidate, sizing result, portfolio permission. | `TradeOrder` submission via Bridge client, execution logging. | TCP Client to Port 5555 / IPC Bridge. |
| **Process Supervisor** | `scripts/supervisor.py` | 24/7 background OS supervisor with exponential backoff restart loops for Bridge Server and Trading Engine. | Windows process table (`terminal64.exe`), port health probes. | Child processes (`run_bridge_server.py`, `start_bot.py`), log rotation. | Windows OS Process API, Named Mutex, Socket Pings. |
| **Desktop Companion** | `companion/electron/main.cjs` | Electron desktop supervisor, GUI dashboard, configuration editor, local credential store, and service watchdog. | IPC requests from React UI, child process stdout/stderr. | Supervised process state, real-time metrics, emergency controls. | Electron IPC, local config files, socket health pings. |
| **ArcadeFX Cloud Agent** | `agent/mt5_bot_agent.py` | Outbound-only secure orchestration agent connecting local MT5 instance to ArcadeFX Cloud platform. | Local terminal data, signed cloud commands (HMAC-SHA256). | Outbound telemetry heartbeats, offline SQLite sync. | Outbound HTTPS (REST / WebSockets), zero listening ports. |
| **Telegram Dispatcher** | `src/notifications/telegram_service.py` | Asynchronous notification pipeline and operator remote command switchboard with rate limiting and 2-step confirmation. | System events, execution outcomes, operator chat input. | Telegram HTML alerts, parsed administrative commands. | Outbound HTTPS to Telegram Bot API (proxy supported). |

---

## 3. Comprehensive Execution Sequence

### A. System Boot and Initialization Sequence
1. **Supervisor / Electron Launch**:
   - `scripts/supervisor.py` acquires the Named Windows Mutex (`Local\ArcadeFX_MT5_Supervisor_Mutex`) or Electron acquires single-instance lock.
   - Verifies whether MT5 client terminal (`terminal64.exe`) is actively running. If absent, enters polling loop.
2. **Bridge Server Start**:
   - Spawns `python scripts/run_bridge_server.py`.
   - Bridge server binds exclusively (`SO_EXCLUSIVEADDRUSE`) to Port 5555 (MQL5 Link) and Port 5556 (IPC Link).
3. **Trading Engine Launch**:
   - Once Port 5555/5556 probe succeeds, supervisor launches `python scripts/start_bot.py`.
   - `start_bot.py` acquires `SingleInstanceLock("mt5_trading_engine")`.
4. **Configuration & Tier Loading**:
   - `AppConfig.load_from_dir()` reads `config/settings.json`, `config/strategy_config.json`, `config/risk_config.json`, and `config/account_tiers.json`.
5. **Bridge Connection & Account Mode Handshake**:
   - Python connects to `127.0.0.1:5555`.
   - Sends `ACCOUNT` command to EA. EA replies with account balance, equity, leverage, currency, trade mode (`DEMO`/`REAL`), and margin mode (`NETTING`/`HEDGING`).
   - If bridge TCP is disconnected, attempts fallback synchronization directly via Python `MetaTrader5` API.
6. **Multi-Timeframe History Warm-Up**:
   - `orchestrator.initialize_market_data()` requests historical candle arrays across all configured symbols for timeframes: W1, D1, H4, H1, M30, M15, M5, M1.
   - Enforces minimum bar count check (W1 >= 52, D1 >= 200, H4 >= 300, H1 >= 500, M15 >= 500).

```
[Supervisor] ──> Spawns Bridge Server (Port 5555/5556)
                       │
                       ▼ (Socket Probe OK)
[Supervisor] ──> Spawns Trading Engine (start_bot.py)
                       │
                       ▼
[Engine]     ──> Connects TCP 5555 ──> [PythonBridgeEA.mq5]
                       │
                       ▼ (Synchronize Account Mode & Balance)
[Engine]     ──> Warmup Multi-Timeframe Candles (W1..M1)
                       │
                       ▼
[Engine]     ──> Enters Continuous Scalp & SMC Scan Loop
```

---

### B. Live Trading Cycle Execution Sequence
For every monitored symbol in each scan loop iteration:
1. **Health & Connection Audit**:
   - `health_monitor.check_and_recover_connections()` validates socket ping latency and MT5 data feed freshness.
2. **Account Synchronization**:
   - Every 5 cycles, synchronizes latest balance, equity, and margin from MT5.
3. **Data Acquisition & Staleness Check**:
   - Queries latest M1, M5, M15, H1 candles from `MarketDataEngine`.
   - Checks candle timestamp against system clock: if age exceeds `max_candle_staleness_seconds` (180s), skips evaluation with `TRADE_SKIPPED / STALE_DATA`.
4. **Continuous Scalping Model Evaluation**:
   - `run_scalping_cycle_for_symbol(symbol)` triggers `ContinuousScalpingEngine`.
   - Classifies market regime: `BULLISH_TREND`, `BEARISH_TREND`, `RANGING`, `HIGH_VOLATILITY`.
   - Computes EMA9, EMA21, EMA50, and ATR14.
   - Evaluates Model 1 (Momentum Continuation), Model 2 (Pullback / FVG / OTE), Model 3 (Sweep / Breakout).
   - If candidate found, adjusts confluence score via RSI14 and volume expansion filters.
5. **SMC Fallback Opportunity Evaluation**:
   - If no scalping candidate triggers, falls back to `run_cycle_for_symbol(symbol)`.
   - Updates `StructureStateMachine` (CHoCH Warning -> Pullback -> BOS Confirmation).
   - Detects M15 FVGs, Order Blocks, and Weekly/Daily liquidity sweeps (PWL/PWH/PDL/PDH).
   - Generates candidate if weighted confluence score >= 75.0 (or instrument confidence floor).
6. **Setup Quality Gate Validation (Phase 2)**:
   - Passes candidate to `SetupQualityGate.evaluate()`.
   - Evaluates Hard Gates: G1 (Structure), G2 (Zone), G3 (Sweep), G4 (POI Quality), G5 (LTF Confirmation), G6 (HTF Alignment), G7 (Stops/Targets), G8 (Risk Cap).
   - If gate mode is `ENFORCE` and any enabled hard gate fails, rejects candidate with explicit reason code.
7. **Secondary Machine Learning & Kelly Modulation**:
   - If enabled, `MetaLabelingController` computes probabilistic meta-score via logistic regression with Platt calibration.
   - If probability < threshold, candidate is vetoed or down-sized.
   - `KellyEngine` computes fractional Kelly risk cap based on historical win-rate and expectancy.
8. **Position Sizing & Quantization**:
   - `PositionSizingEngine.calculate_lot_size()` evaluates account capital base (`min(balance, equity)`).
   - Enforces $5.00 capital floor.
   - Calculates structural loss per lot via MT5 tick size/value or `OrderCalcProfit`.
   - Quantizes volume to `lot_step` (strictly rounding down).
   - Rejects if minimum lot risk exceeds R9 hard ceiling (2.0%).
9. **Portfolio Risk & Circuit Breaker Permission**:
   - `PortfolioRiskEngine.evaluate_new_order_permission()` checks daily loss limit, weekly loss limit, trailing drawdown, consecutive loss pause, max simultaneous positions, and correlation group limits.
10. **Order Submission & Bridge Dispatch**:
    - `OrderManager.execute_signal()` formats JSON request with unique `request_id`, magic number, stop loss, take profit, and filling mode.
    - Dispatches JSON over TCP Port 5555 to `PythonBridgeEA.mq5`.
11. **MQL5 Execution & Post-Fill Reconciliation**:
    - EA receives JSON, validates allowed account login, checks internal watchdog status, verifies spread, computes real money at risk via `OrderCalcProfit`, and invokes `CTrade::Buy` or `CTrade::Sell`.
    - Returns JSON reply with deal ticket, order ticket, and execution price.
    - If TCP timeout occurs, Order Manager initiates reconciliation to detect if the position was filled at the broker.
12. **Active Position Supervision**:
    - `orchestrator.manage_active_positions()` audits all open tickets.
    - Evaluates $5.00+ net profit target locking, break-even transitions, partial profit taking (50% at 1.0R/1.5R), and ATR/swing trailing stops.
    - Feeds realized outcomes into `portfolio_risk`, `performance_tracker`, and CUSUM `decay_guard`.

---

## 4. Cross-Process Communication Map

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   COMMUNICATION CHANNELS                                    │
├───────────────────┬───────────────────┬───────────────┬─────────────────────────────────────┤
│ From Process      │ To Process        │ Protocol      │ Data Payloads / Schema              │
├───────────────────┼───────────────────┼───────────────┼─────────────────────────────────────┤
│ PythonBridgeEA    │ bridge_server.py  │ TCP Socket    │ JSON Command Payloads:              │
│ (MT5 Client)      │ (Port 5555)       │ Localhost     │ - PING / PONG (Heartbeats)          │
│                   │                   │               │ - ACCOUNT (Balance, Equity, Mode)   │
│                   │                   │               │ - POSITIONS (Open tickets, PnL)     │
│                   │                   │               │ - RATES (Multi-timeframe OHLCV)     │
│                   │                   │               │ - TRADE (Order submission & fills)  │
│                   │                   │               │ - MODIFY (SL/TP updates)            │
│                   │                   │               │ - CLOSE / CLOSE_ALL                 │
├───────────────────┼───────────────────┼───────────────┼─────────────────────────────────────┤
│ orchestrator.py   │ bridge_server.py  │ TCP Socket    │ IPC Dispatch Commands:              │
│ (Trading Engine)  │ (Port 5556)       │ Localhost     │ - Forwarded trade actions           │
│                   │                   │               │ - Symbol history queries            │
│                   │                   │               │ - Status diagnostics                │
├───────────────────┼───────────────────┼───────────────┼─────────────────────────────────────┤
│ Electron UI       │ Managed Children  │ Node.js       │ Process Supervision:                │
│ (main.cjs)        │ (Engine, Bridge,  │ child_process │ - stdin / stdout / stderr streaming │
│                   │  Agent)           │ spawn()       │ - SIGTERM / SIGKILL controls        │
│                   │                   │               │ - Named Mutex / Lockfile management │
├───────────────────┼───────────────────┼───────────────┼─────────────────────────────────────┤
│ mt5_bot_agent.py  │ ArcadeFX Cloud    │ Outbound      │ Telemetry & Signed Control:         │
│ (Cloud Agent)     │ Backend           │ HTTPS / WSS   │ - Heartbeat telemetry (every 15s)   │
│                   │                   │ (Port 443)    │ - Inbound commands (HMAC-SHA256)    │
│                   │                   │               │ - Offline SQLite event queue        │
├───────────────────┼───────────────────┼───────────────┼─────────────────────────────────────┤
│ telegram_service  │ Telegram Bot API  │ Outbound      │ Alerts & Operator Switchboard:      │
│ (Python Engine)   │                   │ HTTPS         │ - Rate-limited HTML alerts (1 msg/s)│
│                   │                   │ (Port 443)    │ - Operator polling (/status, /pause)│
│                   │                   │               │ - Two-step confirmation tokens      │
└───────────────────┴───────────────────┴───────────────┴─────────────────────────────────────┤
```

---

## 5. Architectural Redundancy & Single-Instance Guards

To prevent catastrophic dual-execution, split-brain routing, or overlapping positions:
1. **Bridge Server Socket Exclusivity**:
   - `bridge_server.py` configures `socket.SO_EXCLUSIVEADDRUSE` on Windows.
   - Prevents duplicate processes from hijacking Port 5555 or 5556 and intercepting execution traffic.
2. **Single Instance Engine Lock**:
   - `start_bot.py` instantiates `SingleInstanceLock("mt5_trading_engine")` backed by an OS-level file lock in `%LOCALAPPDATA%\ArcadeFX\MT5-OO1 Companion\state\mt5_trading_engine.lock`.
   - If another instance is running, cleanly terminates immediately.
3. **Supervisor Mutex**:
   - `scripts/supervisor.py` creates a Win32 Named Mutex `Local\ArcadeFX_MT5_Supervisor_Mutex`.
   - Prevents multiple supervisors from competing to spawn duplicate bridge or engine instances.
4. **MQL5 EA Chart-Level Guard**:
   - `PythonBridgeEA.mq5` verifies global terminal variables (`GlobalVariableCheck`) to prevent multiple EA instances from conflicting on the same magic number across multiple charts.
   - Enforces unique magic number offsets per symbol (`InpMagicNumber + InpSymbolMagicOffset`).
5. **Idempotent Order De-Duplication**:
   - Every trade order generated by the Python engine carries a unique `request_id` (`REQ_<SYMBOL>_<TIMESTAMP>_<UUID>`).
   - `PythonBridgeEA.mq5` maintains a circular cache of recent `request_id` strings (`g_processed_requests[]`). If a duplicate request arrives, it is immediately discarded and the cached response returned without executing a second trade.

---

## 6. Authoritative State Matrix

A critical design inquiry in hybrid algorithmic architectures is determining which subsystem is authoritative for system state:

| State Domain | Primary Authoritative Subsystem | Fallback / Secondary Sync | Reconciliation Mechanism |
| :--- | :--- | :--- | :--- |
| **Account Balance & Equity** | **MetaTrader 5 Client Terminal** | Direct Python MT5 API | Periodic TCP polling (`ACCOUNT` action every 5 cycles); direct API read on socket timeout. |
| **Open Positions & Tickets** | **MetaTrader 5 Client Terminal** | Engine Internal Cache (`_active_positions_cache`) | Polled via `POSITIONS` action; post-closure detection via `history_deals_get`. |
| **Pending Orders** | **MetaTrader 5 Client Terminal** | Order Manager Cache | Polled via `ORDERS` action; cancellations confirmed by broker retcode. |
| **Stop Loss & Take Profit Values** | **MetaTrader 5 Client Terminal** | Native EA GlobalVariables (`SMC_INITSL_*`) | Terminal `POSITION_SL` / `POSITION_TP` are ground truth; EA modifies values directly on chart ticks. |
| **Trading Permission / Risk State** | **Python Portfolio Risk Engine & Native EA (Dual-Gated)** | Local Limits JSON (`local_limits.json`) | Both systems maintain independent veto power: if either Python or MQL5 signals a circuit breaker breach, no trade can execute. |
| **Historical Candle Data** | **MetaTrader 5 Client Terminal** | Python Local Cache (`MarketDataEngine`) | Incremental sync via `RATES` command or `mt5.copy_rates_range()`. |

---
**Audit Verification:** Component paths, socket ports, execution flows, and IPC commands forensicly verified against repository source code.
