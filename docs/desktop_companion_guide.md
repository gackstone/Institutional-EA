# Institutional EA Companion Desktop Application Guide

> **Application Name:** Institutional EA Companion  
> **Repository:** `https://github.com/gackstone/Institutional-EA.git`  
> **Target Audience:** Traders, DevOps Engineers, and Quantitative Operators  
> **Classification Tagging:** `[SAFETY]`, `[ARCHITECTURE]`, `[DERIVED]`

---

## 1. Overview & Vision

The **Institutional EA Companion** transforms the institutional MT5 algorithmic day-trading and scalping engine into a fully packaged, self-contained desktop companion.

Before this desktop companion, running the trading system required technical command-line interventions:
- Opening a shell to execute `python scripts/run_bridge_server.py`.
- Opening a second shell to execute `python scripts/start_bot.py`.
- Manually running pairing commands via `python agent/mt5_bot_agent.py --pair <CODE>`.
- Manually locating MT5 data folders to install `PythonBridgeEA.mq5`.
- Managing port readiness and background process supervision.

The **Institutional EA Companion** completely automates this workflow:
```
  INSTALL → LAUNCH APP → PAIR INSTITUTIONAL_EA → CONNECT MT5 → START BOT
```
No manual Python, pip, Node.js, Git, or terminal execution is required by the end-user.

---

## 2. Desktop System Architecture

The desktop application uses a modular, multi-tier architecture:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   Institutional EA Desktop Companion UI                         │
│  - React 19 + TypeScript + Tailwind CSS                                │
│  - Financial Status Dashboard (Balance, Equity, Daily PnL, Trades)     │
│  - Service Health Monitoring Cards (Engine, Bridge, Cloud, Telegram)  │
│  - One-Click Primary Controls (Start, Stop, Pause, Restart, Deploy EA)  │
│  - Real-Time Streaming Activity & Telemetry Console                    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ IPC Bridge (Tauri 2 / Electron)
┌───────────────────────────────────┴────────────────────────────────────┐
│                  Native Desktop Supervisor Process                     │
│  - Process Lifecycle & Multi-Process Supervision                       │
│  - Port Availability Pre-Flight Probes (5555 / 5556)                   │
│  - Single-Instance Mutex Locking                                       │
│  - System Tray Minimization & Background Execution                     │
│  - Auto-Restart with Exponential Backoff (2s -> 60s)                   │
│  - MetaTrader 5 Terminal Scanner & Automatic EA Deployment             │
│  - Outbound HTTPS Pairing to https://arcadefx.live/api/v1              │
└───────────────┬───────────────────────────────┬────────────────────────┘
                │ IPC Socket (127.0.0.1:5556)   │ TCP Socket (127.0.0.1:5555)
                ▼                               ▼
┌───────────────────────────────┐   ┌────────────────────────────────────┐
│   Python Algorithmic Engine   │   │       MetaTrader 5 Terminal        │
│   (scripts/start_bot.py)      │   │  - terminal64.exe                  │
│  - Institutional EA + Art of Trading│   │  - PythonBridgeEA.mq5 attached     │
│  - 25 Pure Strategy Skills    │   │  - Zero DLL requirement            │
│  - R9 Risk Rulebook & Trailing│   │  - Live Account & Market Data Feed │
│  - Manual Position Adoption   │   └────────────────────────────────────┘
└───────────────────────────────┘
```

---

## 3. Supervised Background Services

The companion application supervises six independent background services:

| Service | Executable / Script | Role & Health Check |
| :--- | :--- | :--- |
| **Python Trading Engine** | `scripts/start_bot.py` | Runs multi-symbol M1/M5/M15 scalping loops, market structure analysis, and trade lifecycle management. Probed via process ID and IPC heartbeat. |
| **MT5 Bridge Server** | `scripts/run_bridge_server.py` | Persistent TCP socket daemon on Port 5555 (EA) and Port 5556 (IPC). Probed via pre-flight socket connect. |
| **Institutional EA Cloud Sync** | `agent/mt5_bot_agent.py` | Outbound HTTPS telemetry, heartbeats, and signed cloud control. Probed via device token authentication. |
| **Telegram Dispatcher** | `src/notifications/telegram_service.py` | Structured HTML cards, pinned status messages, and operator commands (`/status`, `/positions`, `/pause`). |
| **Health & Watchdog** | `src/execution/watchdog.py` | Anti-dormancy monitor, 60s hang detection, and CUSUM decay guard. |
| **Log Manager** | `RotatingFileHandler` | Captures, deduplicates, and rotates log files into `logs/` (10 MB per file, 14 backups). |

---

## 4. Operational Controls & Lifecycles

### Primary Action Controls
- **`START BOT`**:
  1. Checks port 5555 and 5556 availability.
  2. Spawns Bridge Server process.
  3. Verifies TCP socket acceptance.
  4. Spawns Trading Engine process.
  5. Connects engine to Bridge IPC.
  6. Warms up candle history (W1 to M1).
  7. Transitions state to `RUNNING`.
- **`STOP BOT`**:
  1. Issues clean termination signals (`SIGTERM` / `SIGBREAK`).
  2. Waits for open order reconciliation.
  3. Closes bridge sockets without zombie processes.
  4. Transitions state to `STOPPED`.
  > [!IMPORTANT]
  > Stopping the engine does NOT close open trading positions automatically. Existing trades remain protected by broker-side Stop Loss and Take Profit levels.
- **`PAUSE TRADING`**:
  - Creates `state/PAUSE`. Signals the Python engine to immediately halt new order submissions while continuing to manage active trailing stops and break-even levels.
- **`RESUME TRADING`**:
  - Removes `state/PAUSE` and resumes normal automated market scanning.
- **`CONNECT MT5`**:
  - Opens the MT5 Integration & EA Wizard to auto-deploy the EA and verify socket connection on port 5555.
- **`PAIR INSTITUTIONAL_EA`**:
  - Opens the Cloud Pairing dialog to submit a 6-character pairing code to `https://arcadefx.live/api/v1/bot/pairing/claim`.

---

## 5. Security & Trading Safeguards `[SAFETY]`

1. **Local Ceilings Win (`agent/local_limits.json`):**
   Remote cloud commands CANNOT raise risk percentages or enable live real-money trading above local machine limits.
2. **Zero Inbound Ports:**
   Cloud communication is 100% outbound HTTPS over TLS 1.3. No open listening ports exist on the internet.
3. **No Password Transmission:**
   MT5 broker login passwords and private server credentials are NEVER transmitted to the cloud or stored unencrypted.
4. **Real Account Barrier:**
   Live real-money trading is hard-locked by default. Enabling real execution requires explicitly checking `Allow Real Capital Automated Trading` in Configuration Settings.
5. **Tighten-Only Stop Loss Rule (R9.3):**
   The bot is mathematically forbidden from widening a stop loss or removing a stop loss. It can only reduce risk.

---

## 6. Packaging & Production Builds

### Build Commands
```powershell
# 1. Install Node.js dependencies:
cd companion
npm install

# 2. Build React production bundle:
npm run build

# 3. Package Windows Installer (NSIS .exe):
npm run electron:build -- --win nsis

# 4. Package Tauri 2 Native Executable:
npm run tauri:build
```

Distributable installers are placed in `companion/dist_electron/` or `companion/src-tauri/target/release/bundle/`.
