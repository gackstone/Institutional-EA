# Phase 1 Audit Report: MT5-OO1 Companion Desktop Application

> **Document Version:** 1.0.0  
> **Target:** MT5-OO1 Arcade FX Desktop Companion  
> **Repository:** `https://github.com/gackstonew-lgtm/MT5-OO1.git`  
> **Auditor:** Principal Quantitative Systems & Desktop Software Architect  
> **Classification Tagging:** `[SAFETY]` (Protective controls & trading invariants), `[ARCHITECTURE]` (Design & IPC contracts), `[DERIVED]` (Execution pipeline requirements).

---

## 1. Executive Summary

This audit establishes the factual foundation for building the **MT5-OO1 Companion** desktop application. The companion application serves as the production desktop runtime, process supervisor, and synchronization controller for the existing algorithmic trading engine, eliminating the need for manual command-line execution (`python scripts/start_bot.py`, `python scripts/run_bridge_server.py`, or manual pairing scripts).

The existing codebase contains robust, institutional-grade components:
- A multi-timeframe quantitative scalping engine (`src/core/orchestrator.py`, `scripts/start_bot.py`).
- A persistent dual-port TCP socket bridge server (`src/execution/bridge_server.py`, `scripts/run_bridge_server.py`).
- A real cloud agent protocol integrating with `https://arcadefx.live/api/v1` (`agent/mt5_bot_agent.py`).
- A production MQL5 Expert Advisor (`mql5/Experts/PythonBridgeEA.mq5`).
- An autonomous multi-process Windows supervisor (`scripts/supervisor.py`).
- A 28-video pure skill quantitative strategy suite (`src/engine/skills/`) and manual position adoption subsystem (`src/manual_mgmt/`).

---

## 2. Component Inspection & Inventory

### 2.1. Python Trading Engine Entry Point (`scripts/start_bot.py`)
- **Role:** Main executable loop initializing `TradingBotOrchestrator(config)`.
- **Startup Sequence:**
  1. Parses `--dry-run`, `--max-cycles`, and `--interval` (default `1.0s`).
  2. Loads configuration from directory (`AppConfig.load_from_dir()`).
  3. Initializes `TradingBotOrchestrator`.
  4. In `DEMO`, `REAL`, or `RETAIL` mode, connects via `BridgeClient` to `127.0.0.1:5556` (IPC port). If unavailable, falls back to direct `MetaTrader5` C-API initialization.
  5. Initializes and warms up candle history across all configured symbols (`W1` down to `M1`).
  6. Dispatches startup alert via `TelegramAlertManager`.
  7. Enters continuous scan loop: calls `continuous_scalper.get_ordered_symbols_for_cycle()`, runs cycle, calls `manage_active_positions()` and `manage_manual_positions()`.
- **Termination:** Intercepts `SIGTERM`, `SIGBREAK`, and `KeyboardInterrupt`, gracefully disconnecting `orchestrator.bridge.disconnect()` and flushing state.

### 2.2. Persistent Bridge Server (`scripts/run_bridge_server.py` & `src/execution/bridge_server.py`)
- **Role:** Long-lived daemon acting as the bidirectional switchboard between Python and MT5.
- **Ports & Protocols:**
  - **Port 5555 (`ea_port`):** Listens for incoming native TCP socket connections from `PythonBridgeEA.mq5`. Uses exclusive address binding (`SO_EXCLUSIVEADDRUSE` on Windows, `SO_REUSEADDR` on POSIX) to prevent split-traffic port binding.
  - **Port 5556 (`ipc_port`):** Listens for local clients (`BridgeClient` in `start_bot.py`, CLI commands, or GUI IPC).
- **Communication Protocol:** Newline-delimited JSON (`\n`) wire format.
- **Reliability:** Built-in `WatchdogManager` monitoring a 60-second heartbeat thread. Pre-flight socket check (`run_startup_selfcheck`) detects port conflicts before binding. Rotating log writer in `logs/bridge_service.log` (10 MB, 14 backups).

### 2.3. ArcadeFX.live Pairing & Synchronization (`agent/mt5_bot_agent.py`)
- **Role:** Outbound-only HTTPS orchestration agent communicating with ArcadeFX Cloud.
- **Endpoints & Contracts:**
  - `POST /bot/pairing/claim`: Submits `{"pairingCode": "XXXXXX", "instanceName": "NAME-MT5", "engineVersion": "1.2.0"}`.
  - Returns `{"success": true, "deviceToken": "...", "instanceId": "...", "signingSecret": "..."}`.
  - `POST /bot/heartbeat`: Pushes account equity, balance, active positions, EA connection state, and local limits every 15–30 seconds.
  - `POST /bot/commands/poll`: Retrieves signed cloud commands (`start`, `stop`, `pause`, `resume`, `close_all`, `kill_switch`).
  - `POST /bot/commands/:id/ack`: Acknowledges executed command status.
  - `POST /bot/events/sync`: Synchronizes queued offline events from `~/.arcadefx_agent/offline_queue.sqlite`.
- **Security:** Zero open inbound listening ports on the host. Cryptographic HMAC-SHA256 signature verification with nonce and 5-minute timestamp expiration. Local machine hard ceilings (`agent/local_limits.json`) prevent remote cloud commands from increasing risk or enabling live trading without local physical authorization.

### 2.4. MQL5 Expert Advisor (`mql5/Experts/PythonBridgeEA.mq5`)
- **Role:** Chart-attached native MQL5 script executing trade requests and streaming tick/rates data.
- **Input Parameters:**
  - `InpServerHost`: `127.0.0.1`
  - `InpServerPort`: `5555`
  - `InpMagicNumber`: `100101`
  - `InpTimeoutMs`: `2000`
- **Supported Actions:** `PING`, `ACCOUNT_INFO`, `POSITIONS`, `RATES`, `DAILY_SUMMARY`, `TRADE`, `MODIFY`, `CANCEL`, `CLOSE`, `KILL_SWITCH`.

### 2.5. Existing Windows Supervisor (`scripts/supervisor.py`)
- **Role:** Autonomous Windows supervisor providing dual-process supervision of `run_bridge_server.py` and `start_bot.py`.
- **Key Mechanics:**
  - Detects `terminal64.exe` MT5 terminal process presence.
  - Enforces start order: Bridge ports 5555 and 5556 must be listening before starting `start_bot.py`.
  - Single-instance locking via named Windows Mutex (`Local\ArcadeFX_MT5_Supervisor_Mutex`) and `logs/supervisor.lock`.
  - Independent exponential restart backoff (2s $\rightarrow$ 60s).
  - Background process execution using `CREATE_NO_WINDOW` and clean child termination on shutdown.

---

## 3. Architecture & Startup Dependency Graph

```
                                [ MT5-OO1 Companion App ]
                                            │
                     ┌──────────────────────┴──────────────────────┐
                     ▼                                             ▼
          [ 1. Environment & Pre-Flight ]               [ 2. ArcadeFX.live Pairing ]
          - OS & Architecture Check                     - Verify ~/.arcadefx_agent/credentials
          - MT5 Terminal Detection                      - If missing: prompt 6-char code
          - Ports 5555 & 5556 Conflict Check            - Authenticate with POST /bot/pairing/claim
                     │                                             │
                     └──────────────────────┬──────────────────────┘
                                            ▼
                               [ 3. MT5 Terminal & EA Check ]
                               - Detect terminal64.exe running
                               - Check MQL5/Experts/PythonBridgeEA.mq5
                               - Deploy / Update EA if needed
                                            │
                                            ▼
                               [ 4. Launch Bridge Server ]
                               - Bind Port 5555 (EA) & 5556 (IPC)
                               - Verify TCP Socket Acceptance
                                            │
                                            ▼
                               [ 5. Launch Trading Engine ]
                               - Connect IPC Client to 127.0.0.1:5556
                               - Warm up Candle History (W1..M1)
                               - Initialize Risk & Strategy Rules
                                            │
                                            ▼
                               [ 6. Establish EA Handshake ]
                               - Verify EA Socket connection on 5555
                               - Receive ACCOUNT_INFO & POSITIONS
                               - Report Bot Operational State: READY
```

---

## 4. Platform Compatibility Matrix

| Operating System | MT5 Terminal Integration | Python Quantitative Engine | Companion Desktop Runtime | Production Readiness |
| :--- | :--- | :--- | :--- | :--- |
| **Windows 10/11 (x64)** | **Native** (`terminal64.exe`, direct Registry detection, full C-API & MQL5 socket bridge) | Native Python 3.10+ / Bundled Frozen Runtime | Native Desktop UI + Process Supervisor | **Full Production** |
| **macOS (Apple Silicon & Intel)** | **Wine-Emulated MT5** (PlayOnMac/CrossOver/Wine prefix socket loopback to 127.0.0.1:5555) | Native macOS Python / Bundled Runtime | Native Desktop UI | **Supported (Wine MT5)** |
| **Linux (x86_64 & ARM64)** | **Wine-Emulated MT5** (Wine prefix socket loopback to 127.0.0.1:5555) | Native Linux Python / Bundled Runtime | Native Desktop UI (AppImage, deb) | **Supported (Wine MT5)** |

---

## 5. Desktop Application Requirements & Module Layout

The Companion application directory will be structured under `companion/`:
```
companion/
├── src/                          # Modern React + TypeScript Dashboard
│   ├── components/               # Status cards, live activity console, MT5 wizard, pairing modal
│   ├── hooks/                    # Live state hooks, socket listeners, process telemetry
│   ├── types/                    # Shared TypeScript interfaces for contracts and events
│   ├── App.tsx                   # Main layout and view routing
│   └── main.tsx                  # Application entry point
├── src-tauri/                    # Tauri 2 Desktop Runtime (Rust)
│   ├── src/
│   │   ├── main.rs               # Application lifecycle & command registration
│   │   ├── supervisor.rs         # Native child process manager & health checks
│   │   ├── mt5.rs                # MT5 installation scanner & EA deployer
│   │   ├── bridge.rs             # Bridge socket probe & diagnostics
│   │   └── arcadefx.rs           # ArcadeFX pairing client
│   ├── Cargo.toml                # Rust dependencies
│   └── tauri.conf.json           # Tauri 2 configuration & bundle metadata
├── electron/                     # Cross-platform Electron runtime runner
│   ├── main.cjs                  # Electron main process supervising background services
│   └── preload.cjs               # Secure contextBridge IPC
├── packaging/                    # PyInstaller freeze specs & bundle scripts
│   ├── build_sidecars.py         # Freezes bridge_server, start_bot, and agent
│   └── sidecars.spec             # PyInstaller multi-binary spec
├── package.json                  # Node.js dependencies (Vite, React, Tailwind, Lucide)
├── tsconfig.json                 # TypeScript compiler configuration
└── vite.config.ts                # Vite build configuration
```

---
*End of Phase 1 Audit Report.*
