# Control Service Connectivity Diagnosis (`ECONNREFUSED 127.0.0.1:8765`)

**Branch**: `fix/service-connectivity-mt5-deploy`  
**Date**: 2026-11-22  
**Symptom**: Every Control Service IPC call (`control-request`) fails with `Error invoking remote method 'control-request': Error: connect ECONNREFUSED 127.0.0.1:8765`; Dashboard KPIs wait indefinitely; chart stays on `Waiting for MT5 Candles`; MT5 Terminal shows `Conn: DISCONNECTED` and `Sync MT5` fails with `ECONNREFUSED`; `Stop` and `Close All` fail with `ECONNREFUSED`.

---

## 1. Live Environment Observations

| Check | Command / Observation | Finding |
|---|---|---|
| Port 8765 listener | `netstat -ano \| findstr 8765` | **Nothing listening on `127.0.0.1:8765`**. Running `Institutional EA.exe` (PID 13392) stuck in `SYN_SENT` to `127.0.0.1:8765`. |
| Running processes | `Get-Process` | `Institutional EA.exe` running from `companion\release\win-unpacked\`; `terminal64.exe` running (PID 888, `C:\Program Files\MetaTrader 5\terminal64.exe`); **0 Python / `mt5_control_service.exe` processes running**. |
| Sidecar binary age | `ls companion\resources\bin\` | `mt5_control_service.exe` timestamp is `2026-11-18 14:25` (predates `src/data/market_feed.py`, Migration `002`, `/api/market/candles`, `/api/signals`, `/api/alerts`, `/api/analytics/equity`, `/api/trades/replay`). |
| Dev CLI reproduction | `.\.venv\Scripts\python.exe -m companion.service.main --host 127.0.0.1 --port 8765 --project-root "<repo>"` | **Immediate exit code 2**: `main.py: error: unrecognized arguments: --project-root ...` |
| Packaged binary reproduction | `companion\resources\bin\mt5_control_service.exe --host 127.0.0.1 --port 18765 --project-root "<repo>"` | **Immediate exit code 2**: `mt5_control_service.exe: error: unrecognized arguments: --project-root ...` |
| Manual start without `--project-root` | `.\.venv\Scripts\python.exe -m companion.service.main --host 127.0.0.1 --port 18765` | Starts cleanly in `< 3s` and responds `HTTP 200 {"status": "ok", "service": "institutional-ea-control-service"}` on `/healthz`. |

---

## 2. Root Causes Identified

### Root Cause 1 (Primary Fatal Crash — 100% Reproducible in Both Dev & Packaged App)
- **`companion/electron/main.cjs:2521-2530`** spawns the Control Service with `--project-root <PROJECT_ROOT>` in all three launch branches (packaged `mt5_control_service.exe`, `.venv\Scripts\python.exe`, and system `python`).
- **`companion/service/main.py:21-24`** only defines `--host` and `--port` in `argparse`.
- **Effect**: On every app launch, the Control Service immediately terminates with exit code `2` (`unrecognized arguments: --project-root ...`) before binding `127.0.0.1:8765`.
- Because `main.cjs:2537-2541` spawns with `stdio: ["ignore", "pipe", "pipe"]` and never attaches `stdout`/`stderr` listeners or logs non-zero exit codes, the crash is completely silent.

### Root Cause 2 (Stale PyInstaller Binary + Wrong Writable Directories in Packaged Mode)
- **`companion/resources/bin/mt5_control_service.exe`** was last built on `2026-11-18`, so it lacks all recent API routes (`/api/market/candles`, `/api/signals`, `/api/alerts`, `/api/analytics/equity`, `/api/trades/replay`) and `src/data/market_feed.py`.
- **`companion/electron/main.cjs:12-14, 2495`** sets `PROJECT_ROOT = process.resourcesPath` when packaged and reads `CONTROL_TOKEN_FILE` from `path.join(PROJECT_ROOT, "state", "companion_token.txt")`.
- **`companion/service/main.py:13`** computes `PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent`, which inside a PyInstaller `--onefile` binary points to the temporary `_MEIxxxxx` extraction directory instead of writable user data or packaged `resources/config`.
- **`companion/service/api/server.py:472-473`** writes `companion_control.db` and `companion_token.txt` under `project_root/data` and `project_root/state`, which fails or loses state if `process.resourcesPath` is read-only (e.g., `Program Files`) or ephemeral (`_MEI`).
- **Fix required**: Pass `--project-root` (read-only bundled assets/config) AND `--data-dir` (writable `%LOCALAPPDATA%\InstitutionalEA\Institutional EA Companion`) to the Control Service, store DB/token/logs in `--data-dir`, and rebuild `mt5_control_service.exe`.

### Root Cause 3 (No Readiness Probe, No `/health` Alias, No Auto-Restart, Raw IPC Errors)
- **`companion/electron/main.cjs:2643-2646`** calls `startControlService()` and immediately opens `createWindow()` without polling `/health` or `/healthz`.
- **`companion/service/api/server.py:94`** exposes `/healthz` but not `/health`.
- There is no bounded auto-restart on unexpected service exit, no port-conflict fallback if `8765` is held by another process, and no structured service-status channel to the renderer.
- When the service is down, `httpControlRequest()` rejects with Node's raw `Error: connect ECONNREFUSED 127.0.0.1:8765`, which Electron wraps as `Error invoking remote method 'control-request': ...` and renders verbatim in multiple banners across the UI.

### Root Cause 4 (Background MT5 Sync Never Auto-Connects + No Terminal Path / `last_error`)
- **`companion/service/main.py:31-38`** only calls `ctx.mt5_sync.sync_all()` when `ctx.mt5_sync.connection_status == "CONNECTED"`, even though `connection_status` initializes to `"DISCONNECTED"`. As a result, MT5 is never auto-connected on startup and never auto-recovers after a disconnect.
- **`companion/service/mt5/sync_service.py:145, 198`** calls `mt5.initialize()` with no `path` parameter and never surfaces `mt5.last_error()` when initialization fails.

---

## 3. Baseline Test & Build Record (Before Changes)

| Suite | Command | Result |
|---|---|---|
| Python tests | `.\.venv\Scripts\python.exe -m pytest tests/test_companion_control_service.py tests/test_market_feed.py tests/test_no_hardcoded_market_data.py -q` | **13 passed** (5.96s) |
| Companion unit tests | `cd companion && npm test` | **9 passed** (0.44s) |
| Companion TypeScript + Vite build | `cd companion && npm run build` | **PASS** (`tsc && vite build`, 13.05s) |
