# MT5-OO1 Companion Troubleshooting & Diagnostic Runbook

## 1. Quick Diagnostic Checklist

If you encounter issues during installation, startup, or trading, run through this 5-point checklist:

| Check | What to Verify | Fix / Action |
|---|---|---|
| **Ports 5555 & 5556** | Is another application or zombie process occupying the bridge ports? | Click **RUN DIAGNOSTICS** in Companion UI or kill orphan processes |
| **MT5 Algorithmic Trading** | Is the AutoTrading button GREEN in MT5? | Press `Ctrl+E` in MT5 to enable AutoTrading |
| **PythonBridgeEA on Chart** | Is the EA attached to at least one active chart? | Drag `PythonBridgeEA.mq5` onto any M1/M5 chart; check smiling face icon |
| **DLL / WebRequest Permissions** | Are EA permissions granted in MT5? | In MT5: Tools $\rightarrow$ Options $\rightarrow$ Expert Advisors $\rightarrow$ check "Allow algorithmic trading" & "Allow DLL imports" |
| **Account Mode Safety** | Are you connected to a DEMO account? | Real accounts require explicit toggle in Settings: `ALLOW_REAL_ACCOUNT_MANAGEMENT=true` |

---

## 2. Port Conflicts on 5555 / 5556

### Problem
The supervisor fails to start `run_bridge_server.py`, or logs show `OSError: [Errno 98/10048] Address already in use`.

### Solution
1. In the Companion, click **RUN DIAGNOSTICS** $\rightarrow$ **Fix Port Conflicts**.
2. Or run manually via terminal:
   - **Windows PowerShell**:
     ```powershell
     Get-NetTCPConnection -LocalPort 5555,5556 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
     ```
   - **Linux / macOS**:
     ```bash
     lsof -ti:5555,5556 | xargs kill -9
     ```
3. Restart services from the companion UI.

---

## 3. MT5 Terminal Not Detected

### Symptoms
The MT5 Setup Wizard displays "No MetaTrader 5 Terminals Detected".

### Common Causes & Fixes
1. **Custom Installation Folder**:
   - If your broker installed MT5 in a non-standard path (e.g., `D:\Trading\FTMO MetaTrader 5`), click **Browse** in the MT5 Setup Wizard and select `terminal64.exe`.
2. **AppData Data Folder Uninitialized**:
   - MetaTrader 5 only generates its hash directory in `%APPDATA%\MetaQuotes\Terminal\` after the first launch.
   - Launch MT5 manually at least once, log into any demo account, and close it. Then click **Re-scan Terminals**.
3. **Wine on macOS / Linux**:
   - Verify that your Wine prefix path is set in `.env`:
     ```env
     WINEPREFIX="/home/user/.wine"
     ```
   - Ensure Wine has Wine-Mono or requisite socket networking libraries installed.

---

## 4. ArcadeFX.live Pairing Errors

### Error: "Invalid pairing code format"
- **Cause**: The entered code is not exactly 6 alphanumeric characters.
- **Fix**: Codes are case-insensitive 6-character strings (e.g. `A7B2C9`). Do not include hyphens, spaces, or symbols.

### Error: "Pairing code expired or already claimed"
- **Cause**: Pairing codes are ephemeral and expire after 15 minutes.
- **Fix**: Generate a fresh code in the ArcadeFX.live dashboard and enter it within 15 minutes.

### Error: "Cloud cannot override local limits"
- **Cause**: A remote command attempted to execute a trade with risk higher than `agent/local_limits.json` or switch to a live account.
- **Fix**: This is an intentional security safeguard. If you intend to trade higher risk or live accounts, update your local settings in the Companion UI directly.

---

## 5. Subprocess Crash & Exponential Backoff

### Symptoms
A service card turns RED ("CRASHED") and enters a countdown timer before restarting.

### Supervisor Behavior
- When a process dies unexpectedly, the supervisor captures stderr logs and applies backoff:
  - Crash 1: 1-second delay
  - Crash 2: 2-second delay
  - Crash 3: 4-second delay
  - Crash 4: 8-second delay
  - Crash 5: 16-second delay (Max 5 attempts in 15 minutes)
- After 5 consecutive failures, the supervisor moves the service to **BLOCKED** state to protect against infinite crash loops and CPU exhaustion.
- Check the **Live Console** filter by selecting the crashed service to view the exact traceback.

---

## 6. Log Export & Support Diagnostics

To submit logs for analysis or bug reporting:
1. Click **VIEW LOGS** in the Companion UI.
2. Click **Export Logs Bundle**.
3. The companion bundles:
   - `logs/bot_engine.log`
   - `logs/bridge_server.log`
   - `logs/agent_sync.log`
   - `logs/supervisor.log`
   into a single ZIP file with all API keys and account numbers automatically redacted.
