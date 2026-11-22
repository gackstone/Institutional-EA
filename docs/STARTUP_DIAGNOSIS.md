# Startup Blank Screen & Auto-Refresh Diagnosis

> Branch: `fix/startup-blank-screen`
> Evidence-backed root cause analysis for the startup blank dark-navy screen and post-launch refresh/unmount failure.

---

## 1. Executive Summary of Root Causes

| # | Root Cause | File & Line | Effect |
|---|---|---|---|
| **1 (Primary)** | **SSE `snapshot` payload schema mismatch crashes React on first live event**: Control Service `/api/events` sends `{"type": "snapshot", "payload": ctx.engine.get_status()}` (only the `engine` dict, with **no `.mt5` or `.health` property**). `App.tsx` passes `parsed.payload` directly into `setRawStatus(parsed.payload)`. On the very next render, `buildNormalizedDashboardData()` accesses `rawStatus.mt5.connection_status` without optional chaining, throwing an uncaught `TypeError: Cannot read properties of undefined (reading 'connection_status')`. | `companion/service/api/server.py:204`<br>`companion/src/App.tsx:325-326`<br>`companion/src/services/dashboardDataAdapter.ts:314-315` | React 19 unmounts the entire `<App />` tree right after initial paint (appearing to the user as an automatic refresh followed by a permanently blank `#091426` dark navy screen with only the native Windows `titleBarOverlay` buttons visible). |
| **2 (Amplifier)** | **Zero React Error Boundaries**: Neither `companion/src/main.tsx` nor `companion/src/App.tsx` wraps the app or major panels in an Error Boundary. Any runtime render exception silently wipes `<div id="root"></div>` to empty. | `companion/src/main.tsx:9-15`<br>`companion/src/App.tsx:744-827` | Turns any transient payload/shape error into a permanent silent blank screen with no recovery UI. |
| **3 (Amplifier)** | **No Main-Process Watchdog, Reload-Loop Guard, or Crash Fallback**: `companion/electron/main.cjs` had no `did-fail-load`, `render-process-gone`, `unresponsive`, or mount-readiness watchdog. | `companion/electron/main.cjs:1991-2040` | A crashed or failed renderer stays on a blank `#091426` window forever with no Reload / Reset / Open Logs recovery. |
| **4 (Packaged Sidecar Drift)** | **Outdated `mt5_control_service.exe` sidecar**: `companion/resources/bin/mt5_control_service.exe` had not been rebuilt after adding `/api/chart/drawings` and `/api/mt5/disconnect`, causing repeated `Error: Unknown endpoint: /api/chart/drawings` and serving the old broken SSE `snapshot` payload. | `companion/resources/bin/mt5_control_service.exe` | Packaged app failed drawings fetch and received the broken SSE `snapshot` payload. |
| **5 (Dev Reload Trigger)** | **Vite watcher included `release/` and `dist/`**: `companion/vite.config.ts` did not ignore `release/**` or `dist/**`, causing full-page reloads whenever packaging touched `release/win-unpacked/`. | `companion/vite.config.ts:14-17` | Repeated `[vite] (client) page reload release/win-unpacked/LICENSES.chromium.html` during dev/build overlap. |

---

## 2. Exact Event Sequence of the Blank Screen

1. **T = 0.0s**: Electron launches `BrowserWindow` (`backgroundColor: "#091426"`, `titleBarStyle: "hidden"`, `titleBarOverlay` height `36px` showing native minimize/maximize/close buttons).
2. **T = 0.5s – 1.5s**: `dist/index.html` loads cleanly (`file://.../companion/dist/index.html`, HTTP 200). Initial React mount succeeds while `rawStatus === null`, rendering the Dashboard shell briefly.
3. **T = 1.5s – 5.0s**: `App.tsx` opens `EventSource("http://127.0.0.1:8765/api/events?token=...")`. As soon as the Control Service is online (immediately if already running, or on reconnect after ~3–5s boot), `server.py:204` emits:
   ```json
   {"type": "snapshot", "payload": {"state": "STOPPED", "operating_mode": "DEMO_SCALPING", ...}}
   ```
4. **T + 0.01s**: `App.tsx:326` executes `setRawStatus(parsed.payload)`. `rawStatus` is now an object whose `.mt5` property is `undefined`.
5. **T + 0.02s**: React re-renders `App` -> `buildNormalizedDashboardData(rawStatus, trades)` -> `dashboardDataAdapter.ts:315` evaluates `rawStatus.mt5.connection_status` -> throws uncaught `TypeError: Cannot read properties of undefined (reading 'connection_status')`.
6. **T + 0.03s**: With no Error Boundary, React unmounts the entire component tree. The window flashes once (perceived as an automatic refresh) and settles on an empty `#091426` dark navy canvas with only the Windows `titleBarOverlay` buttons visible.
   - The thin bars seen at the very top center / bottom edges in the user's screenshot are the OS window-chrome edge / compositor artifact over the empty `#091426` document body (no orange progress bar exists in `companion/src/`).

---

## 3. Captured Log Evidence

### A. Built Electron Run (`startup_diagnostics.log`)
```text
2026-11-22T20:31:28.306Z [window-created] {"isPackaged":false,"argv":["electron/main.cjs"]}
2026-11-22T20:31:28.380Z [did-start-navigation] {"url":"file:///.../companion/dist/index.html","isInPlace":false,"isMainFrame":true}
2026-11-22T20:31:30.384Z [did-navigate] {"url":"file:///.../companion/dist/index.html","httpResponseCode":200}
2026-11-22T20:31:30.717Z [dom-ready] {"url":"file:///.../companion/dist/index.html"}
2026-11-22T20:31:30.719Z [did-finish-load] {"url":"file:///.../companion/dist/index.html"}
```

### B. Packaged App (`companion/release/win-unpacked/Institutional EA.exe`)
```text
Error occurred in handler for 'control-request': Error: Unknown endpoint: /api/chart/drawings
    at IncomingMessage.<anonymous> (...\resources\app.asar\electron\main.cjs:2901:22)
```

### C. Old Installed App (`%LOCALAPPDATA%\Programs\Institutional EA\Institutional EA.exe`, built prior to this branch)
```text
Error occurred in handler for 'control-request': Error: Unauthorized: invalid or missing session token
```
(Occurred when an older `mt5_control_service.exe` instance was still holding port `8765` with a stale token.)

### D. Auto-Start Engine Check (Safety Rule 4)
- Audited `main.cjs`, `App.tsx`, and `companion/service/main.py`: **Nothing auto-starts the trading engine on launch.** `main.cjs` only starts the Control Service (`startControlService()`), and `companion/service/main.py` only auto-connects MT5 telemetry (`mt5-sync-loop`). `autoStartOnBoot` in `types/index.ts` is an OS-login companion launch preference only.

---

## 4. Planned Fixes (Parts 2–4)

1. **Fix SSE `snapshot` payload in `server.py:204`** to send the full `{ engine, mt5, health }` snapshot AND include `Access-Control-Allow-Origin: *` on `/api/events`.
2. **Harden `App.tsx:325-336` & `dashboardDataAdapter.ts:314-370`** with defensive optional chaining and shape checks so partial/legacy payloads can never throw.
3. **Add versioned persisted-state storage (`companion/src/utils/persistedState.ts`)** with schema validation, migration, and safe per-key reset on corruption (never blocking startup).
4. **Add Root & Panel React Error Boundaries (`companion/src/components/ErrorBoundary.tsx`)** with inline Retry buttons so no crash can blank the screen.
5. **Add Boot Splash in `index.html`** (logo + spinner, dismissed on first React paint) so the window is never an empty color block.
6. **Add Main-Process Startup Watchdog (8s), Reload-Loop Guard (>3 loads in 30s), Crash Fallback Screen (Reload / Reset Settings with Backup / Open Logs), and Global Uncaught Exception / Unhandled Rejection Handlers** in `companion/electron/main.cjs`.
7. **Ignore `release/**` and `dist/**` in `companion/vite.config.ts`**.
8. **Add Automated Smoke Tests (`npm run test:smoke`), Unit Tests (persisted state, error boundary, watchdog), and Preload/IPC Contract Tests**.
9. **Rebuild `mt5_control_service.exe` sidecar (`npm run sidecars`) and Windows installer (`npm run dist:win`)**.
