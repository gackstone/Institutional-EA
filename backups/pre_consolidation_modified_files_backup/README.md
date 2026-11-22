# Institutional Multi-Timeframe MT5 Algorithmic Day-Trading Bot

[![Platform](https://img.shields.io/badge/Platform-MetaTrader%205%20%7C%20Python%203.10%2B-blue.svg)]()
[![Architecture](https://img.shields.io/badge/Architecture-Modular%20SMC%2FICT%20IPC-orange.svg)]()
[![Tests](https://img.shields.io/badge/Tests-294%2F294%20Passing-brightgreen.svg)]()
[![Build](https://img.shields.io/badge/MQL5%20Build-0%20Errors%20%7C%200%20Warnings-success.svg)]()
[![Account Adaptation](https://img.shields.io/badge/Account%20Floor-%245%20Micro%2FCent-blueviolet.svg)]()

Institutional-grade, multi-timeframe algorithmic trading system combining MetaTrader 5 (MQL5) with a high-performance Python quantitative engine. The bot features universal account-size adaptation (supporting any account from a $5 minimum floor upward, including Cent accounts), quantitative validation (Bailey & Lopez de Prado DSR, CSCV PBO, Monte Carlo ruin), dynamic regime detection, meta-labeling, GARCH/EWMA volatility modeling, fractional Kelly risk capping, execution TCA, and real-time CUSUM decay monitoring.

---

## 1. System Architecture

```
                    ┌──────────────────────────────────────────────┐
                    │               MetaTrader 5                   │
                    │  ┌────────────────────────────────────────┐  │
                    │  │           PythonBridgeEA.mq5           │  │
                    │  │  - Single chart attachment (e.g. M15)  │  │
                    │  │  - Chart labels & visual levels (PWH)  │  │
                    │  │  - Local execution & order safety gate │  │
                    │  │  - WebRequest fallback notifications   │  │
                    │  └──────────────────┬─────────────────────┘  │
                    └─────────────────────┼────────────────────────┘
                                          │ TCP Socket IPC (Localhost)
                                          │ Port 5555 (Data & Trade)
                                          │ Port 5556 (Admin/Monitor)
                    ┌─────────────────────┴────────────────────────┐
                    │            Python Algorithmic Engine         │
                    │  ┌────────────────────────────────────────┐  │
                    │  │           src/core/bridge_server       │  │
                    │  │  - Asynchronous event dispatcher       │  │
                    │  │  - Heartbeat & connection supervisor   │  │
                    │  └──────────────────┬─────────────────────┘  │
                    │                     │                        │
                    │  ┌──────────────────┴─────────────────────┐  │
                    │  │      src/smc/ & src/risk/              │  │
                    │  │  - Weekly / Daily liquidity sweeps     │  │
                    │  │  - MTF cascading structure (W1->M15)   │  │
                    │  │  - Exact tick-value lot sizing         │  │
                    │  │  - Reward-to-Risk (min 1:2) filter     │  │
                    │  └──────────────────┬─────────────────────┘  │
                    │                     │                        │
                    │  ┌──────────────────┴─────────────────────┐  │
                    │  │      src/notifications/                │  │
                    │  │  - 6-tier continuous activity feed     │  │
                    │  │  - 10s silent batch digest queue       │  │
                    │  │  - Immediate loud alerts (SIGNAL/TRADE)│  │
                    │  │  - Telegram 429 rate-limit backoff     │  │
                    │  │  - Interactive bot command handler     │  │
                    │  └──────────────────┬─────────────────────┘  │
                    └─────────────────────┼────────────────────────┘
                                          │ HTTPS (Proxy Supported)
                                          ▼
                                   Telegram Bot API
```

### Directory Structure
```
├── mql5/
│   ├── Experts/PythonBridgeEA.mq5   # Native MT5 Expert Advisor bridge (compiled with MetaEditor)
│   └── Sounds/                     # Native audio cues (signal.wav, trade.wav, alert.wav)
├── src/
│   ├── core/                       # TCP bridge server, data contracts, session clock
│   ├── data/                       # Multi-timeframe loader, UTC conversion, broker cost model
│   ├── smc/                        # Liquidity levels, market structure, FVG/OB, MTF analyzer
│   ├── regime/                     # Gaussian volatility state classifier, shadow mode
│   ├── risk/                       # Position sizing ($5 floor), GARCH/EWMA vol, Kelly, drawdown throttle, exposure
│   ├── execution/                  # Pre-trade checklist, bridge client, order dispatcher
│   │   └── analytics/              # TCA engine, slippage audit, time-of-day spread filter, idempotency
│   ├── monitoring/                 # CLI dashboard, CUSUM decay guard, PSI feature drift, deal reconciler
│   ├── notifications/              # Telegram feed manager, transport, commands, formatting
│   └── learning/                   # Champion/challenger evaluator, walk-forward, DSR, PBO, meta-labeling
├── config/
│   ├── account_tiers.json          # $5-$50,000+ tiers (MICRO, MINI, SMALL, STANDARD, LARGE)
│   ├── account_profiles.json       # DEMO, LIVE, and PROP firm parameters
│   ├── risk_config.json            # Max daily loss, max trade risk %, drawdown caps
│   ├── sessions.json               # London, NY, Asian session definitions & filters
│   ├── symbols.json                # Per-symbol minimum history and parameters
│   └── strategy_config.json        # SMC/ICT and quant feature flags (default OFF in shadow mode)
├── scripts/
│   ├── run_bridge_server.py        # Starts standalone IPC bridge server
│   ├── start_bot.py                # Launches end-to-end trading pipeline
│   ├── run_validation.py           # Quantitative validation suite (DSR, PBO, Monte Carlo)
│   ├── generate_sizing_table.py    # Sizing matrix generator for $5-$50k accounts
│   ├── promotion_check.py          # Stage 8 production promotion gate evaluation
│   ├── verify_deep.py              # 12-suite deep architecture and regression test
│   └── verify_all.py               # Comprehensive end-to-end regression suite
├── tests/                          # 294 automated unit, integration & Golden Master test suites
├── reports/                        # Sizing matrices, market profiles, validation reports
├── docs/                           # ARCHITECTURE.md, STRATEGY.md, SECURITY.md
├── CHANGELOG.md                    # Detailed version history and defect resolutions
├── requirements.txt                # Pinned Python package dependencies
└── README.md                       # Complete deployment & operations manual
```

---

## 2. Prerequisites & Requirements

- **Operating System:** Windows 10, Windows 11, or Windows Server 2019/2022.
- **MetaTrader 5:** Build 4150 or newer with 64-bit `metaeditor64.exe`.
- **Python:** Python 3.10 or newer (tested on Python 3.12 64-bit).
- **Network / Proxy (Optional):** SOCKS5 / HTTP proxy supported via `.env` for environments requiring routed connections.

### Python Dependencies
Install required packages via `pip`:
```bash
pip install -r requirements.txt
```
Key libraries:
- `MetaTrader5` (Official MT5 Python IPC library)
- `python-dotenv` (Secure environment credential loader)
- `numpy` (Fast vector calculations for liquidity and volatility)
- `requests` (HTTP transport fallback)

---

## 3. Installation & Setup

### Step 1: Copy and Compile the MQL5 EA
1. Open MetaTrader 5 and press `F4` to open **MetaEditor**.
2. Copy `mql5/Experts/PythonBridgeEA.mq5` into your MetaTrader 5 terminal directory:
   `<MT5_DATA_FOLDER>/MQL5/Experts/PythonBridgeEA.mq5`
3. Copy audio files from `mql5/Sounds/` into `<MT5_DATA_FOLDER>/MQL5/Sounds/`.
4. In MetaEditor, open `PythonBridgeEA.mq5` and click **Compile** (`F7`).
   *Ensure the compiler outputs: `0 errors, 0 warnings`.*

### Step 2: Configure MetaTrader 5 Terminal Permissions
1. In MetaTrader 5, navigate to **Tools** > **Options** (`Ctrl+O`) > **Expert Advisors**.
2. Check **Allow Algo Trading**.
3. Check **Allow WebRequest for listed URL** and add:
   ```
   https://api.telegram.org
   ```
4. Attach `PythonBridgeEA` to **ONE chart only** (recommended: `EURUSD` or `XAUUSD`, timeframe `M15`).

### Step 3: Configure Environment Secrets (.env)
Copy the template `.env.example` to `.env`:
```bash
copy .env.example .env
```
Edit `.env` with your secure credentials:
```ini
# Telegram Bot Token from @BotFather
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ_example
# Authorized numeric Telegram Chat ID
TELEGRAM_CHAT_ID=123456789
TELEGRAM_ENABLED=true
# Optional proxy URL (e.g. socks5h://127.0.0.1:1080)
TELEGRAM_PROXY=

# Socket Bridge Settings
BRIDGE_HOST=127.0.0.1
BRIDGE_PORT=5555

# Execution Mode: DEMO | LIVE | PROP
EXECUTION_MODE=DEMO
```

> [!WARNING]
> Never commit `.env` or any file containing live tokens to git. `.env` is explicitly ignored in `.gitignore`.

---

## 4. Running the System

### Option A: Running the Standalone Bridge Server
To run the IPC bridge server that connects MT5 to Telegram and logs events:
```bash
python scripts/run_bridge_server.py
```

### Option B: Running the Full Automated Strategy Pipeline
```bash
python scripts/start_bot.py
```

### Option C: Running the Institutional EA Cloud Bot Agent (Interactive Pairing)
Connect your MT5 machine to the [Institutional EA Cloud](https://Institutional EA Cloud) cloud dashboard:
```bash
# Interactive pairing prompt:
python agent/mt5_bot_agent.py

# Or via Windows VPS launcher:
start_mt5_agent.bat

# Or with one-time pairing code directly:
python agent/mt5_bot_agent.py --pair <6-CHAR-CODE>
```
1. Open [https://Institutional EA Cloud](https://Institutional EA Cloud)
2. Navigate to **MT5 Bot** > **Pair MT5 Machine**
3. Click **Generate 10-Minute Pairing Code**
4. Enter the 6-character code into the agent terminal
5. Upon successful verification, the agent connects to the local MT5 terminal, starts telemetry heartbeats, and begins listening for signed cloud control commands (Start, Pause, Resume, Stop, Emergency Actions).

### Option D: Institutional EA Companion Desktop Application (Cross-Platform GUI)
For a visual, zero-CLI operator experience with unified supervision of all engine processes:
```bash
cd companion
npm start
```
Features:
- **Zero-Terminal Operations:** Install, configure, supervise, and trade with zero manual command-line steps.
- **One-Click MT5 Wizard:** Auto-detects local MT5 terminals (Windows & Wine) and deploys `PythonBridgeEA.mq5` with automatic backup.
- **Institutional EA Cloud Pairing:** Built-in modal for 6-character ephemeral pairing and token management.
- **Unified Process Supervision:** Manages Engine, Bridge Server, Cloud Sync, Telegram Feed, Watchdog, and Log rotation with automated port pre-flight checks and crash backoff.
- **Live Observability:** Real-time Account Metrics (Balance, Equity, Daily PnL, Margin %), Active Positions Table, and Streaming Console with log filters and export.
- **Pre-Flight Diagnostics:** 9-point system verification covering Python runtime, MT5 terminal, bridge ports 5555/5556, disk space, and cloud connectivity.



---

## 5. Account Profiles & Risk Controls

The system supports three strict risk execution profiles configured in `config/account_profiles.json`:

| Parameter | DEMO | LIVE | PROP (FTMO / MFF / Funded) |
|---|---|---|---|
| **MaxRiskPercentPerTrade** | 2.0% | 1.0% | 0.5% |
| **MaxDailyLossPercent** | 5.0% | 3.0% | 4.0% |
| **MaxTotalDrawdownPercent** | 10.0% | 6.0% | 8.0% |
| **MinRewardToRisk** | 1:2.0 | 1:2.0 | 1:2.5 |
| **ForceMinLotRiskFloor** | Active | Active | Active |

### Mathematical Position Sizing
Lot sizes are calculated strictly according to account balance and broker contract specifications:
$$\text{Loss Per Lot} = \frac{|\text{Entry} - \text{SL}|}{\text{Tick Size}} \times \text{Tick Value}$$
$$\text{Calculated Lots} = \left\lfloor \frac{\text{Balance} \times \text{Risk \%}}{\text{Loss Per Lot} \times \text{Volume Step}} \right\rfloor \times \text{Volume Step}$$

- **No Round-Up Risk Inflation:** Volumes are rounded *down* to `SYMBOL_VOLUME_STEP` and clamped between `SYMBOL_VOLUME_MIN` and `SYMBOL_VOLUME_MAX`.
- **Minimum Lot Safety Floor:** If the minimum tradeable volume (`0.01` lots) risks more than `MaxRiskPercentPerTrade`, the trade is **automatically skipped** and logged with the exact risk percentage.
- **Unified Profit Calculation:** Stop-loss risk and take-profit gains are computed using `OrderCalcProfit` through a shared code path including commission and spread estimates.

---

## 6. Startup Warm-Up & History Validation

Before any trade setup is evaluated, `PythonBridgeEA` executes a 7-point pre-flight checklist:
1. **Bridge Socket Connection:** Verifies TCP ping-pong response.
2. **Symbol Selection:** Ensures all enabled symbols are selected in Market Watch.
3. **History Depth Check:** Asynchronously verifies and force-loads bars:
   - W1: 52 bars
   - D1: 200 bars
   - H4: 300 bars
   - H1: 500 bars
   - M15: 500 bars
4. **Hard Floor Indicator Enforcement:** Calculates mathematical floor from longest active indicator periods. Trading is permanently blocked if bars fall below this floor.
5. **Broker UTC Offset Detection:** Synchronizes server clock to UTC.
6. **Spread & ATR Readability:** Validates tick data and market liquidity.
7. **Single-Instance Mutex:** Prevents duplicate EA instances on the same account.

---

## 7. Structured Telegram Notification Layer & Commands

The bot uses a structured 3-tier notification layer (`src/notifications/`, documented in [`docs/NOTIFICATIONS.md`](docs/NOTIFICATIONS.md)) with 28 typed event payloads and centralized HTML templates (`src/notifications/templates/`):

- **Tier 1 — `LOUD` (Immediate push with sound)**: `TradeSetup`, `TradeOpened`, `TargetHit`, `StopLossHit`, `OrderRejected`, `ConnectionLost`, `DailyLossLimitHit`, `DrawdownWarning`, `MarginWarning`, `BotStopped`, `UnauthorizedAccess`, and escalated `CRITICAL` alerts.
- **Tier 2 — `SILENT` (`disable_notification=true`)**: `BreakEvenMoved`, `PartialClosed`, `SessionOpen`, `SessionClose`, `NewsBlackout`, `DailySummary`, `WeeklySummary`, `BotStarted`, `BotPaused`, `BotResumed`, `ConnectionRestored`, `SpreadWarning`, `DailyLossWarning`, `WarmupProgress`, `ConfigChanged`, `HealthOK`.
- **Tier 3 — `ON_DEMAND` (Logged on disk; never pushed by default)**: Per-bar `NO SETUP`, `SetupSkipped` filter reasons, and raw bar diagnostics (available via `/logs [N]` or `/last [N]`).

### Live Trade Threading, Noise Policy & Security
- **Live Trade Card & Threading**: Posts `TRADE SETUP`, edits the card in-place with a live timeline as the trade opens, moves to break-even, banks partial TP, and closes, and threads replies via `reply_to_message_id` (with automatic fallback to a new card if `editMessageText` fails).
- **Single Pinned Status Card & Transition Alerting**: Replaces 5/15-minute heartbeat spam with one Pinned Status Card edited in place + optional hourly `HealthOK` check + state-transition alerts (`OK -> WARNING -> CRITICAL -> RECOVERED`) with cooldowns and repeat merging.
- **Zero Secrets**: Account numbers are masked (`****0001`), MT5 retcodes are mapped to plain English, and tokens/keys are automatically redacted.

### Telegram Remote Commands & Inline Buttons
*All commands and inline callback buttons (`Pause`, `Resume`, `Status`, `Positions`, `Close All` two-step confirmation) are strictly restricted to the authorized `TELEGRAM_CHAT_ID` configured in `.env`.*

| Command | Arguments | Description |
|---|---|---|
| `/status` | *(none)* | Clean status card (mode, connection, session, balance, equity, today P&L + R, DD, open positions, fast-mode state) + inline action buttons. |
| `/positions` | *(none)* | Formatted open positions (entry, SL, TP, floating P&L, risk) with automatic retry and friendly fallback. |
| `/today` \| `/week` | *(none)* | Daily or weekly performance & risk summary card. |
| `/health` | *(none)* | Bridge connection, queue depth, `Suppressed Alert Duplicates` counter, quiet hours, and market-watch status. |
| `/marketwatch` | `on` \| `off` | Toggle optional hourly market-watch digest. |
| `/quiet` | `<hours>` | Silence non-critical alerts for `<hours>` (`0` to disable). |
| `/logs` \| `/last` | `[N]` | Show the last $N$ on-demand activity log lines (default 20). |
| `/preview_alerts` | *(none)* | Sends 1 sample of all 28 structured message types labelled `🧪 [SAMPLE]`. |
| `/pause` \| `/resume` | *(none)* | Pause or resume automated market scanning and entries. |
| `/closeall` \| `/flatten` | *(none)* | Close all open positions (`/closeall` requires two-step confirmation). |

---

## 8. Testing & Quality Verification

### Run Unit and Integration Tests
```bash
python -m unittest discover -s tests -v
```

### Run Comprehensive Deep Regression Suite
```bash
python scripts/verify_deep.py
```

### Run Continuous Scalping Upgrade & 20-Trade Suite
```bash
python scripts/run_20_trade_validation_suite.py
python -m unittest tests/test_continuous_scalping_upgrade.py -v
```

### Run Risk Sizing and Noise Suppression Verification
```bash
python scripts/verify_risk_and_noise.py
```

### Validate EA Compilation
From the command line using MetaEditor 64:
```powershell
& "C:\Program Files\JustMarkets MetaTrader 5\metaeditor64.exe" /compile:"mql5\Experts\PythonBridgeEA.mq5" /log:"compile.log"
Get-Content compile.log
```
*Expected: `0 errors, 0 warnings`.*

---

## 9. Production Deployment & Autonomous Windows Supervisor

The repository provides an autonomous, multi-process supervisor (`scripts/supervisor.py`) designed for 24/7 continuous operation on Windows 10/11 and Windows VPS environments without human intervention:

- **Dual-Process Supervision:** Runs `python scripts/run_bridge_server.py` and `python scripts/start_bot.py` independently.
- **MT5 Process Gating:** Monitors `terminal64.exe` (or configured `MT5_TERMINAL_PATH`). Children run while MT5 is active and gracefully stop when MT5 exits, restarting automatically when MT5 reopens.
- **Independent Crash Backoff:** Each process has independent exponential backoff (2s $\rightarrow$ 60s), auto-resetting to 2s after 60s of stable execution.
- **Start Order & Port Readiness:** Waits for Bridge Socket ports (5555/5556) to be accepting connections before starting the bot engine.
- **Single-Instance Locking:** Enforces named Windows Mutex (`Local\InstitutionalEA_MT5_Supervisor_Mutex`) and PID lockfile with automatic stale-lock reclamation and orphan child termination.
- **Zero Console Popups:** Runs invisibly (`CREATE_NO_WINDOW`) with stdout/stderr piped to rotating 5 MB log files in `logs/` (`supervisor.log`, `bridge.log`, `bot.log`).

### Commands

#### 1. Install Autonomous Autostart (Windows Task Scheduler / Startup Folder)
```powershell
# Standard User Installation (Runs on user logon with zero-admin fallback):
powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1

# Administrator / VPS Boot Installation (Runs on system boot whether logged on or not):
powershell -ExecutionPolicy Bypass -File scripts\install_autostart.ps1 -AtStartup -RunWhetherOrNotLoggedOn
```

#### 2. Manual One-Click Start
```cmd
:: Background mode (zero console popups):
scripts\start_supervisor.bat

:: Interactive debug mode (visible console):
scripts\start_supervisor.bat --visible
```

#### 3. Inspect Status and Live Health
```powershell
powershell -ExecutionPolicy Bypass -File scripts\status.ps1
```

#### 4. Uninstall
```powershell
powershell -ExecutionPolicy Bypass -File scripts\uninstall_autostart.ps1
```

### Configuration Options (`.env` / `config/settings.json`)

| Variable | Default | Purpose |
|---|---|---|
| `SUPERVISOR_REQUIRE_MT5` | `true` | Gate bot/bridge execution to MT5 terminal process presence (`true`/`false`) |
| `MT5_TERMINAL_PATH` | *(empty)* | Optional absolute path to specific MT5 `terminal64.exe` |
| `SUPERVISOR_REQUIRE_EA_HEARTBEAT` | `false` | Optional gating to fresh EA heartbeat file (`MQL5/Files/institutional_ea_heartbeat.txt`) |
| `EA_HEARTBEAT_PATH` | *(auto)* | Path to EA heartbeat file |
| `SUPERVISOR_POLL_INTERVAL` | `3` | Polling and health check interval in seconds |
| `SUPERVISOR_PYTHON_PATH` | *(auto)* | Optional path to custom Python interpreter |
| `BRIDGE_HOST` | `127.0.0.1` | Local IP address for bridge server |
| `BRIDGE_PORT` | `5555` | TCP port for PythonBridgeEA socket |
| `BRIDGE_SUB_PORT` | `5556` | IPC socket port for bot orchestrator communication |


---

## 10. Manual Position Adoption & Trade Management

The bot features a dedicated **Manual Position Management Subsystem** (`src/manual_mgmt/`) that detects trades opened manually by the user in the MT5 desktop, mobile, or WebTrader terminal and manages their risk lifecycle using the 28 transferred strategy skills.

### Key Capabilities
- **Deterministic Classification:** Categorizes account positions into `BOT_OWN`, `MANUAL`, `OTHER_EA`, `EXCLUDED`, or `UNKNOWN`.
- **Naked Position Adoption (`PROTECT` mode):** Detects positions opened without a stop loss, computes structural invalidation levels using `protected_swing_marker`, and places the initial protective stop.
- **Cost-Covering Break-Even (`+1.0R`):** Advances stop loss to entry price + spread/commission buffer once structure reaches +1.0R (`[VIDEO 12]`).
- **Structural Trailing Stops (`+1.5R`, `ASSIST` mode):** Progressively trails stops behind confirmed higher lows / lower highs using `swing_hierarchy` and `structure_momentum_monitor` (`[VIDEO 15]`).
- **User Supremacy Invariant `[SAFETY]`:** If the trader modifies SL or TP directly in MT5, the bot immediately cedes control and locks itself out for 30 minutes.
- **Tighten-Only Stop Policy (R9.3):** The engine mathematically forbids widening stops or removing stops; it can only reduce risk.
- **Real Account Barrier:** Real accounts (`account_info.trade_mode == REAL`) are hard-locked in `OBSERVE` (read-only) mode unless `allow_real_account_management: true` is explicitly configured.

```powershell
# Run the Manual Position Replay Harness:
python scripts/run_manual_replay.py --mode PROTECT --entry 1.1000 --sl 0.0 --steps 12

# Run the 13-scenario unit test suite:
python -m unittest -v tests/test_manual_management.py
```
For complete operational procedures, refer to [docs/manual_management_runbook.md](docs/manual_management_runbook.md).

---

## 11. Adding New Symbols or Strategy Logic

1. **Add Symbol to Configuration:**
   Add entry to `config/symbols.json` with appropriate digits, tick value, and minimum history lookbacks.
2. **Implement Strategy Logic:**
   Subclass the strategy engine in `src/smc/strategy_engine.py` or implement custom entry triggers adhering to the closed-candle M15 protocol.
3. **Register in Pipeline:**
   Include the new strategy module in `src/execution/order_manager.py` and run `scripts/verify_deep.py` to confirm zero regressions.

---

## 12. Risk Disclaimer

> [!CAUTION]
> **HIGH RISK INVESTMENT WARNING:**
> Algorithmic trading in financial instruments, foreign exchange (Forex), commodities, and contracts for difference (CFDs) carries a high level of risk and may not be suitable for all investors. The high degree of leverage can work against you as well as for you. Before deciding to trade foreign exchange or CFDs, you should carefully consider your investment objectives, level of experience, and risk appetite.
>
> Past performance is no guarantee of future results. No software or automated algorithm can guarantee profits or eliminate the risk of loss. You should never trade with borrowed capital or money that you cannot afford to lose. The developers and contributors of this software assume no liability for financial losses incurred through its deployment.
