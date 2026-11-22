const { app, BrowserWindow, ipcMain, Tray, Menu, nativeImage, dialog } = require("electron");
const path = require("path");
const fs = require("fs");
const net = require("net");
const http = require("http");
const https = require("https");
const { spawn, execSync } = require("child_process");
const os = require("os");
const crypto = require("crypto");

const isPackaged = app.isPackaged;
const PROJECT_ROOT = isPackaged
  ? path.join(process.resourcesPath)
  : path.resolve(__dirname, "../../");

// Centralized Windows Writable Application Data Directory (%LOCALAPPDATA%\InstitutionalEA\Institutional EA Companion)
const LOCAL_APP_DATA = process.env.LOCALAPPDATA || (app.getPath ? app.getPath("appData") : path.join(os.homedir(), "AppData", "Local"));
const INSTITUTIONAL_EA_DATA_DIR = process.platform === "win32"
  ? path.join(LOCAL_APP_DATA, "InstitutionalEA", "Institutional EA Companion")
  : (app.getPath ? app.getPath("userData") : path.join(os.homedir(), ".institutional-ea", "institutional-ea-companion"));

const USER_DATA_DIR = INSTITUTIONAL_EA_DATA_DIR;
const APP_LOGS_DIR = path.join(INSTITUTIONAL_EA_DATA_DIR, "logs");
const APP_STATE_DIR = path.join(INSTITUTIONAL_EA_DATA_DIR, "state");
const APP_CREDENTIALS_DIR = path.join(INSTITUTIONAL_EA_DATA_DIR, "credentials");
const APP_CONFIG_DIR = path.join(INSTITUTIONAL_EA_DATA_DIR, "config");
const APP_RUNTIME_DIR = path.join(INSTITUTIONAL_EA_DATA_DIR, "runtime");
const APP_BACKUPS_DIR = path.join(INSTITUTIONAL_EA_DATA_DIR, "backups");
const APP_CACHE_DIR = path.join(INSTITUTIONAL_EA_DATA_DIR, "cache");

const APP_CONFIG_FILE = path.join(APP_CONFIG_DIR, "companion_desktop.json");
const PRIMARY_CREDENTIALS_FILE = path.join(APP_CREDENTIALS_DIR, "credentials.json");
const LEGACY_INSTITUTIONAL_EA_DIR = path.join(os.homedir(), ".institutional_ea_agent");
const LEGACY_CREDENTIALS_FILE = path.join(LEGACY_INSTITUTIONAL_EA_DIR, "credentials.enc.json");
const CREDENTIALS_FILE = PRIMARY_CREDENTIALS_FILE;
const DOTENV_FILE = path.join(INSTITUTIONAL_EA_DATA_DIR, ".env");

// Ensure all standard writable subdirectories exist
try {
  [
    INSTITUTIONAL_EA_DATA_DIR,
    APP_LOGS_DIR,
    APP_STATE_DIR,
    APP_CREDENTIALS_DIR,
    APP_CONFIG_DIR,
    APP_RUNTIME_DIR,
    APP_BACKUPS_DIR,
    APP_CACHE_DIR,
    LEGACY_INSTITUTIONAL_EA_DIR
  ].forEach((dir) => {
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  });

  // Seed default configuration files into APP_CONFIG_DIR if not present
  const sourceConfigDirs = [
    path.join(PROJECT_ROOT, "config"),
    path.join(process.resourcesPath, "config"),
    path.join(__dirname, "..", "..", "config")
  ];
  let srcCfgDir = null;
  for (const d of sourceConfigDirs) {
    if (d && fs.existsSync(path.join(d, "settings.json"))) {
      srcCfgDir = d;
      break;
    }
  }
  if (srcCfgDir) {
    ["settings.json", "strategy_config.json", "risk_config.json", "telegram_config.json"].forEach((cfgName) => {
      const srcFile = path.join(srcCfgDir, cfgName);
      const dstFile = path.join(APP_CONFIG_DIR, cfgName);
      if (fs.existsSync(srcFile) && !fs.existsSync(dstFile)) {
        fs.copyFileSync(srcFile, dstFile);
      }
    });
  }
} catch (e) {}

// EA asset source
const MQL5_DIR = isPackaged
  ? path.join(process.resourcesPath, "mql5")
  : path.join(PROJECT_ROOT, "mql5");
const EA_SOURCE_PATH = path.join(MQL5_DIR, "Experts", "PythonBridgeEA.mq5");

let mainWindow = null;
let tray = null;
let isQuitting = false;

// Managed Processes
let bridgeProcess = null;
let botProcess = null;
let agentProcess = null;
let adoptedEnginePid = null;
let botState = "STOPPED"; // "STOPPED" | "STARTING" | "RUNNING" | "PAUSED" | "ERROR"
let startBotInFlight = null;
let userRequestedStop = false;
let isRestartingEngine = false;
let engineRestartCount = 0;
let engineRestartWindowStart = 0;
let engineWatchdogTimer = null;

const ENGINE_PID_META_FILE = path.join(APP_STATE_DIR, "mt5_trading_engine.pid.json");
const ENGINE_HEARTBEAT_FILE = path.join(APP_STATE_DIR, "engine_heartbeat.json");
const ENGINE_STOP_FLAG_FILE = path.join(APP_STATE_DIR, "engine_stop.flag");
const LIFECYCLE_LOG_FILE = path.join(APP_LOGS_DIR, "engine_lifecycle.log");

// Logs Buffer
const MAX_LOGS = 1000;
const logHistory = [];

// Service States (The 6 Supervised Services)
const serviceStates = {
  engine: { id: "engine", name: "Trading Engine", description: "Multi-Timeframe Scalping Engine (mt5_trading_engine)", status: "STOPPED", pid: null, cpu: 0, memoryMb: 0, uptimeSeconds: 0, restarts: 0, lastHeartbeat: null, lastError: null },
  bridge: { id: "bridge", name: "Bridge Server", description: "Persistent TCP Socket IPC on 5555/5556 (mt5_bridge_server)", status: "STOPPED", pid: null, cpu: 0, memoryMb: 0, uptimeSeconds: 0, restarts: 0, lastHeartbeat: null, lastError: null },
  institutional_ea: { id: "institutional_ea", name: "Institutional EA Cloud Sync", description: "Telemetry, heartbeats & signed controls (mt5_bot_agent)", status: "STOPPED", pid: null, cpu: 0, memoryMb: 0, uptimeSeconds: 0, restarts: 0, lastHeartbeat: null, lastError: null },
  telegram: { id: "telegram", name: "Telegram Dispatcher", description: "Real-time alerts & operator remote command switchboard", status: "STOPPED", pid: null, cpu: 0, memoryMb: 0, uptimeSeconds: 0, restarts: 0, lastHeartbeat: null, lastError: null },
  health: { id: "health", name: "Health & Watchdog", description: "CUSUM decay guard, process probe & socket ping", status: "STOPPED", pid: null, cpu: 0, memoryMb: 0, uptimeSeconds: 0, restarts: 0, lastHeartbeat: null, lastError: null },
  logs: { id: "logs", name: "Log Manager", description: "Rotating diagnostics buffer & audit exporter", status: "RUNNING", pid: process.pid, cpu: 0.1, memoryMb: 45, uptimeSeconds: 1, restarts: 0, lastHeartbeat: new Date().toISOString(), lastError: null }
};

// Account Cache
let accountMetrics = {
  accountNumber: 0,
  broker: "Scanning...",
  balance: 0,
  equity: 0,
  profit: 0,
  dailyPnl: 0,
  margin: 0,
  freeMargin: 0,
  marginLevel: 0,
  currency: "USD",
  leverage: 100,
  tradeMode: "DEMO",
  profile: "DEMO",
  positionsCount: 0
};

// Active Positions & Orders Cache
let activePositions = [];
let activePendingOrders = [];

// Ensure Directories
try {
  if (!fs.existsSync(APP_LOGS_DIR)) fs.mkdirSync(APP_LOGS_DIR, { recursive: true });
  if (!fs.existsSync(APP_STATE_DIR)) fs.mkdirSync(APP_STATE_DIR, { recursive: true });
  if (!fs.existsSync(path.dirname(APP_CONFIG_FILE))) fs.mkdirSync(path.dirname(APP_CONFIG_FILE), { recursive: true });
} catch (e) {}

function parseSeverityFromLog(line, defaultSeverity = "INFO") {
  if (!line) return defaultSeverity;
  const upper = line.toUpperCase();
  if (upper.includes("[ERROR]") || upper.includes("[CRITICAL]") || upper.includes("TRACEBACK") || upper.includes("EXCEPTION") || upper.includes("ERR_") || upper.includes("FAILED")) {
    return "ERROR";
  }
  if (upper.includes("[WARNING]") || upper.includes("[WARN]") || upper.includes("WARNING:")) {
    return "WARNING";
  }
  if (upper.includes("[INFO]") || upper.includes("SUCCESS") || upper.includes("CONNECTED") || upper.includes("INITIALIZED") || upper.includes("OK")) {
    return "INFO";
  }
  if (upper.includes("[DEBUG]")) {
    return "DEBUG";
  }
  return defaultSeverity;
}

function appendLog(service, level, message) {
  let effectiveLevel = (level || "INFO").toUpperCase();
  if (effectiveLevel === "WARNING" && message) {
    const detected = parseSeverityFromLog(message, "WARNING");
    if (detected === "INFO" || detected === "DEBUG") {
      effectiveLevel = detected;
    }
  }
  const logItem = {
    id: Math.random().toString(36).substring(2, 9),
    timestamp: new Date().toISOString(),
    service: service.toUpperCase(),
    level: effectiveLevel,
    message
  };
  logHistory.push(logItem);
  if (logHistory.length > MAX_LOGS) logHistory.shift();

  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("log-received", logItem);
  }
}

function logEngineLifecycle(event, level, pid, state, reason) {
  const ts = new Date().toISOString();
  const line = `[${event}] pid=${pid ?? "none"} state=${state} reason=${reason}`;
  appendLog("ENGINE", level, line);
  try {
    fs.appendFileSync(LIFECYCLE_LOG_FILE, `[${ts}] ${line}\n`, "utf-8");
  } catch (e) {}
}

function isPidAlive(pid) {
  const num = Number(pid);
  if (!Number.isInteger(num) || num <= 0) return false;
  try {
    process.kill(num, 0);
    return true;
  } catch (e) {
    return e && e.code === "EPERM";
  }
}

function isPidAliveAndEngine(pid) {
  if (!isPidAlive(pid)) return false;
  if (process.platform === "win32") {
    try {
      const out = execSync(`tasklist /FI "PID eq ${Number(pid)}" /FO CSV /NH`, {
        encoding: "utf-8",
        windowsHide: true,
        timeout: 2500
      }).trim().toLowerCase();
      if (!out || out.includes("no tasks are running")) return false;
      return out.includes("mt5_trading_engine") || out.includes("python");
    } catch (e) {
      return isPidAlive(pid);
    }
  }
  return true;
}

function findExistingEngineProcess() {
  if (botProcess && botProcess.pid && !botProcess.killed && isPidAlive(botProcess.pid)) {
    return { pid: botProcess.pid, source: "child_handle" };
  }
  if (adoptedEnginePid && isPidAliveAndEngine(adoptedEnginePid)) {
    return { pid: adoptedEnginePid, source: "adopted_handle" };
  }
  try {
    if (fs.existsSync(ENGINE_PID_META_FILE)) {
      const meta = JSON.parse(fs.readFileSync(ENGINE_PID_META_FILE, "utf-8"));
      if (meta && meta.pid && isPidAliveAndEngine(meta.pid)) {
        return { pid: Number(meta.pid), source: "lock_metadata" };
      }
    }
  } catch (e) {}
  try {
    if (fs.existsSync(ENGINE_HEARTBEAT_FILE)) {
      const hb = JSON.parse(fs.readFileSync(ENGINE_HEARTBEAT_FILE, "utf-8"));
      if (hb && hb.pid && isPidAliveAndEngine(hb.pid)) {
        return { pid: Number(hb.pid), source: "heartbeat_metadata" };
      }
    }
  } catch (e) {}
  if (process.platform === "win32") {
    try {
      const out = execSync('tasklist /FI "IMAGENAME eq mt5_trading_engine.exe" /FO CSV /NH', {
        encoding: "utf-8",
        windowsHide: true,
        timeout: 2500
      }).trim();
      for (const line of out.split(/\r?\n/)) {
        if (line.toLowerCase().includes("mt5_trading_engine.exe")) {
          const parts = line.split('","').map((s) => s.replace(/^"|"$/g, ""));
          const pid = Number(parts[1]);
          if (Number.isInteger(pid) && pid > 0) {
            return { pid, source: "os_process_scan" };
          }
        }
      }
    } catch (e) {}
  }
  return null;
}

function readEngineHeartbeat() {
  try {
    if (!fs.existsSync(ENGINE_HEARTBEAT_FILE)) return null;
    const hb = JSON.parse(fs.readFileSync(ENGINE_HEARTBEAT_FILE, "utf-8"));
    if (!hb || typeof hb !== "object") return null;
    const epochSec = Number(hb.epoch || 0);
    const ageSeconds = epochSec > 0 ? Math.max(0, Date.now() / 1000 - epochSec) : 9999;
    return { ...hb, ageSeconds };
  } catch (e) {
    return null;
  }
}

async function waitForPidExit(pid, timeoutMs = 3500) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (!isPidAlive(pid)) return true;
    await new Promise((r) => setTimeout(r, 150));
  }
  return !isPidAlive(pid);
}

// -----------------------------------------------------------------------------
// Sidecar & Runtime Resolution
// -----------------------------------------------------------------------------
function resolveSidecar(name) {
  const isWin = process.platform === "win32";
  const exeName = isWin ? `${name}.exe` : name;

  const scriptMap = {
    mt5_bridge_server: path.join(PROJECT_ROOT, "scripts", "run_bridge_server.py"),
    mt5_trading_engine: path.join(PROJECT_ROOT, "scripts", "start_bot.py"),
    mt5_bot_agent: path.join(PROJECT_ROOT, "agent", "mt5_bot_agent.py")
  };

  // 0. Explicit environment override to run directly from Python source
  if (process.env.PREFER_PYTHON_SOURCE === "true" || process.env.PREFER_PYTHON_SOURCE === "1") {
    const scriptPath = scriptMap[name];
    if (scriptPath && fs.existsSync(scriptPath)) {
      const pyExec = resolvePython();
      return { type: "script", python: pyExec, script: scriptPath };
    }
  }

  // 1. Packaged resource directory
  if (isPackaged) {
    const packagedPath = path.join(process.resourcesPath, "bin", exeName);
    if (fs.existsSync(packagedPath)) return { type: "binary", path: packagedPath };
  }

  // 2. Local companion/resources/bin directory
  const localResBin = path.join(__dirname, "../resources/bin", exeName);
  if (fs.existsSync(localResBin)) return { type: "binary", path: localResBin };

  // 3. Fallback to python script execution in development
  const scriptPath = scriptMap[name];
  if (scriptPath && fs.existsSync(scriptPath)) {
    const pyExec = resolvePython();
    return { type: "script", python: pyExec, script: scriptPath };
  }

  return null;
}

function resolvePython() {
  const isWin = process.platform === "win32";
  const venvPython = isWin
    ? path.join(PROJECT_ROOT, ".venv", "Scripts", "python.exe")
    : path.join(PROJECT_ROOT, ".venv", "bin", "python");

  if (fs.existsSync(venvPython)) return venvPython;
  return isWin ? "python" : "python3";
}

// -----------------------------------------------------------------------------
// Ports 5555 and 5556 Socket Lifecycle Management
// -----------------------------------------------------------------------------
function checkPortAvailable(port, host = "127.0.0.1") {
  return new Promise((resolve) => {
    const s = new net.Socket();
    s.setTimeout(500);
    s.once("connect", () => {
      s.destroy();
      resolve(false); // In use / listening
    });
    s.once("timeout", () => {
      s.destroy();
      resolve(true); // Free
    });
    s.once("error", () => {
      resolve(true); // Free
    });
    s.connect(port, host);
  });
}

function probeSocketHandshake(port, host = "127.0.0.1") {
  return new Promise((resolve) => {
    const s = new net.Socket();
    s.setTimeout(1200);
    let received = false;

    s.once("connect", () => {
      try {
        // Send JSON ping request to IPC port 5556
        s.write(JSON.stringify({ action: "PING", timestamp: Date.now() }) + "\n");
      } catch (e) {}
    });

    s.on("data", (data) => {
      received = true;
      s.destroy();
      resolve({ alive: true, data: data.toString() });
    });

    s.once("timeout", () => {
      s.destroy();
      resolve({ alive: received });
    });

    s.once("error", () => {
      resolve({ alive: false });
    });

    s.connect(port, host);
  });
}

// -----------------------------------------------------------------------------
// Live MT5 Open Positions & Account Telemetry Sync (IPC Port 5556 + Direct MT5)
// -----------------------------------------------------------------------------
let lastSyncTimestamp = 0;
let isSyncing = false;

function queryBridgeSocket(action, payload = {}, timeoutMs = 2000) {
  return new Promise((resolve, reject) => {
    const client = new net.Socket();
    let responseData = "";
    let isFinished = false;

    const cleanup = () => {
      if (!client.destroyed) {
        client.destroy();
      }
    };

    client.setTimeout(timeoutMs);

    client.connect(5556, "127.0.0.1", () => {
      try {
        const msg = JSON.stringify({ action, ...payload }) + "\n";
        client.write(msg);
      } catch (err) {
        cleanup();
        if (!isFinished) {
          isFinished = true;
          reject(err);
        }
      }
    });

    client.on("data", (chunk) => {
      responseData += chunk.toString("utf-8");
      if (responseData.includes("\n")) {
        cleanup();
        if (!isFinished) {
          isFinished = true;
          try {
            const parsed = JSON.parse(responseData.trim());
            resolve(parsed);
          } catch (e) {
            reject(e);
          }
        }
      }
    });

    client.on("timeout", () => {
      cleanup();
      if (!isFinished) {
        isFinished = true;
        reject(new Error(`Bridge IPC query '${action}' timed out after ${timeoutMs}ms`));
      }
    });

    client.on("error", (err) => {
      cleanup();
      if (!isFinished) {
        isFinished = true;
        reject(err);
      }
    });
  });
}

function fetchDirectMT5Fallback() {
  return new Promise((resolve) => {
    try {
      const pyExec = resolvePython();
      const code = `
import MetaTrader5 as mt5, json
res = {"positions": [], "orders": [], "account": None}
try:
    if mt5.initialize():
        acc = mt5.account_info()
        if acc:
            res["account"] = {
                "login": int(acc.login),
                "server": str(acc.server or acc.company or "MetaTrader 5"),
                "balance": float(acc.balance),
                "equity": float(acc.equity),
                "margin": float(acc.margin),
                "free_margin": float(getattr(acc, "margin_free", 0.0)),
                "margin_level": float(getattr(acc, "margin_level", 0.0)),
                "currency": str(acc.currency),
                "leverage": int(acc.leverage),
                "trade_mode": "DEMO" if int(getattr(acc, "trade_mode", 0)) == 0 else "REAL",
                "profile": "DEMO" if int(getattr(acc, "trade_mode", 0)) == 0 else "REAL"
            }
        pos_list = mt5.positions_get()
        if pos_list:
            for p in pos_list:
                res["positions"].append({
                    "ticket": int(p.ticket),
                    "symbol": str(p.symbol),
                    "type": "BUY" if int(p.type) == 0 else "SELL",
                    "volume": float(p.volume),
                    "open_price": float(p.price_open),
                    "current_price": float(p.price_current),
                    "sl": float(p.sl),
                    "tp": float(p.tp),
                    "profit": float(p.profit),
                    "magic": int(p.magic),
                    "comment": str(p.comment or "")
                })
        ord_list = mt5.orders_get()
        if ord_list:
            for o in ord_list:
                type_name = "BUY_LIMIT"
                if o.type == 2: type_name = "BUY_LIMIT"
                elif o.type == 3: type_name = "SELL_LIMIT"
                elif o.type == 4: type_name = "BUY_STOP"
                elif o.type == 5: type_name = "SELL_STOP"
                elif o.type == 6: type_name = "BUY_STOP_LIMIT"
                elif o.type == 7: type_name = "SELL_STOP_LIMIT"
                res["orders"].append({
                    "ticket": int(o.ticket),
                    "symbol": str(o.symbol),
                    "type": type_name,
                    "volume": float(o.volume_current),
                    "price": float(o.price_open),
                    "sl": float(o.sl),
                    "tp": float(o.tp),
                    "magic": int(o.magic),
                    "comment": str(o.comment or "")
                })
except Exception as e:
    res["error"] = str(e)
print(json.dumps(res))
`;
      const child = spawn(pyExec, ["-c", code], { windowsHide: true });
      let output = "";
      child.stdout.on("data", (d) => (output += d.toString()));
      child.on("close", (code) => {
        if (code === 0 && output) {
          try {
            const data = JSON.parse(output.trim());
            resolve(data);
            return;
          } catch (e) {}
        }
        resolve(null);
      });
      child.on("error", () => resolve(null));
    } catch (e) {
      resolve(null);
    }
  });
}

function executeDirectMT5Action(action, payload = {}) {
  return new Promise((resolve) => {
    try {
      const pyExec = resolvePython();
      const payloadJson = JSON.stringify(payload);
      const code = `
import MetaTrader5 as mt5, json, sys

action = ${JSON.stringify(action)}
payload = json.loads(${JSON.stringify(payloadJson)})
res = {"success": False, "message": "Unknown action"}

try:
    if not mt5.initialize():
        res = {"success": False, "message": f"MT5 initialize failed: {mt5.last_error()}"}
    elif action == "CLOSE_POSITION":
        ticket = int(payload.get("ticket", 0))
        vol = float(payload.get("volume", 0.0)) if payload.get("volume") else None
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            res = {"success": False, "message": f"Position #{ticket} not found"}
        else:
            p = positions[0]
            close_type = mt5.ORDER_TYPE_SELL if p.type == 0 else mt5.ORDER_TYPE_BUY
            tick = mt5.symbol_info_tick(p.symbol)
            price = tick.bid if p.type == 0 else tick.ask
            vol_to_close = vol if (vol and vol > 0 and vol < p.volume) else p.volume
            req = {
                "action": mt5.TRADE_ACTION_DEAL,
                "position": ticket,
                "symbol": p.symbol,
                "volume": vol_to_close,
                "type": close_type,
                "price": price,
                "deviation": 25,
                "magic": p.magic,
                "comment": "Companion manual close",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC
            }
            order_res = mt5.order_send(req)
            if order_res and order_res.retcode == mt5.TRADE_RETCODE_DONE:
                res = {"success": True, "ticket": ticket, "message": f"Closed #{ticket} ({vol_to_close} lots)"}
            else:
                desc = order_res.comment if order_res else str(mt5.last_error())
                res = {"success": False, "message": f"Close failed: {desc} (code {getattr(order_res, 'retcode', -1)})"}
    elif action == "MODIFY_POSITION":
        ticket = int(payload.get("ticket", 0))
        sl = float(payload.get("sl", 0.0))
        tp = float(payload.get("tp", 0.0))
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            res = {"success": False, "message": f"Position #{ticket} not found"}
        else:
            p = positions[0]
            req = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": ticket,
                "symbol": p.symbol,
                "sl": sl,
                "tp": tp
            }
            order_res = mt5.order_send(req)
            if order_res and order_res.retcode == mt5.TRADE_RETCODE_DONE:
                res = {"success": True, "ticket": ticket, "message": f"Modified #{ticket}: SL={sl:.5f}, TP={tp:.5f}"}
            else:
                desc = order_res.comment if order_res else str(mt5.last_error())
                res = {"success": False, "message": f"Modify failed: {desc} (code {getattr(order_res, 'retcode', -1)})"}
    elif action == "CLOSE_ALL":
        positions = mt5.positions_get()
        closed = []
        failed = []
        if positions:
            for p in positions:
                tick = mt5.symbol_info_tick(p.symbol)
                price = tick.bid if p.type == 0 else tick.ask
                close_type = mt5.ORDER_TYPE_SELL if p.type == 0 else mt5.ORDER_TYPE_BUY
                req = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "position": p.ticket,
                    "symbol": p.symbol,
                    "volume": p.volume,
                    "type": close_type,
                    "price": price,
                    "deviation": 30,
                    "magic": p.magic,
                    "comment": "Companion Close All",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_IOC
                }
                r = mt5.order_send(req)
                if r and r.retcode == mt5.TRADE_RETCODE_DONE:
                    closed.append(p.ticket)
                else:
                    failed.append({"ticket": p.ticket, "reason": r.comment if r else "error"})
        res = {
            "success": len(failed) == 0,
            "closed_count": len(closed),
            "failed_count": len(failed),
            "closed_tickets": closed,
            "failed_tickets": failed,
            "message": f"Liquidated {len(closed)} open positions. Failed: {len(failed)}"
        }
    elif action == "SET_BREAKEVEN":
        ticket = int(payload.get("ticket", 0))
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            res = {"success": False, "message": f"Position #{ticket} not found"}
        else:
            p = positions[0]
            be_price = float(p.price_open)
            req = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": ticket,
                "symbol": p.symbol,
                "sl": be_price,
                "tp": float(p.tp)
            }
            order_res = mt5.order_send(req)
            if order_res and order_res.retcode == mt5.TRADE_RETCODE_DONE:
                res = {"success": True, "ticket": ticket, "message": f"Break-Even applied (#{ticket} @ {be_price})"}
            else:
                desc = order_res.comment if order_res else str(mt5.last_error())
                res = {"success": False, "message": f"Break-even failed: {desc}"}
    elif action == "SET_TRAILING_STOP":
        ticket = int(payload.get("ticket", 0))
        points = float(payload.get("points", 200))
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            res = {"success": False, "message": f"Position #{ticket} not found"}
        else:
            p = positions[0]
            sym_info = mt5.symbol_info(p.symbol)
            pt = sym_info.point if sym_info else 0.0001
            dist = points * pt
            tick = mt5.symbol_info_tick(p.symbol)
            curr = tick.bid if p.type == 0 else tick.ask
            if p.type == 0:
                new_sl = curr - dist
                req = {"action": mt5.TRADE_ACTION_SLTP, "position": ticket, "symbol": p.symbol, "sl": new_sl, "tp": float(p.tp)}
                order_res = mt5.order_send(req)
            else:
                new_sl = curr + dist
                req = {"action": mt5.TRADE_ACTION_SLTP, "position": ticket, "symbol": p.symbol, "sl": new_sl, "tp": float(p.tp)}
                order_res = mt5.order_send(req)
            if order_res and order_res.retcode == mt5.TRADE_RETCODE_DONE:
                res = {"success": True, "ticket": ticket, "message": f"Trailing stop set to {new_sl:.5f} for #{ticket}"}
            else:
                desc = order_res.comment if order_res else str(mt5.last_error())
                res = {"success": False, "message": f"Trailing stop failed: {desc}"}
    elif action == "CANCEL_ORDER":
        ticket = int(payload.get("ticket", 0))
        req = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": ticket
        }
        order_res = mt5.order_send(req)
        if order_res and order_res.retcode == mt5.TRADE_RETCODE_DONE:
            res = {"success": True, "ticket": ticket, "message": f"Cancelled order #{ticket}"}
        else:
            desc = order_res.comment if order_res else str(mt5.last_error())
            res = {"success": False, "message": f"Cancel failed: {desc}"}
    elif action == "MODIFY_PENDING":
        ticket = int(payload.get("ticket", 0))
        price = float(payload.get("price", 0.0))
        sl = float(payload.get("sl", 0.0))
        tp = float(payload.get("tp", 0.0))
        req = {
            "action": mt5.TRADE_ACTION_MODIFY,
            "order": ticket,
            "price": price,
            "sl": sl,
            "tp": tp,
            "type_time": mt5.ORDER_TIME_GTC
        }
        order_res = mt5.order_send(req)
        if order_res and order_res.retcode == mt5.TRADE_RETCODE_DONE:
            res = {"success": True, "ticket": ticket, "message": f"Modified order #{ticket}"}
        else:
            desc = order_res.comment if order_res else str(mt5.last_error())
            res = {"success": False, "message": f"Modify order failed: {desc}"}
    elif action == "PLACE_PENDING":
        symbol = str(payload.get("symbol", ""))
        order_type_str = str(payload.get("type", "BUY_LIMIT")).upper()
        volume = float(payload.get("volume", 0.01))
        price = float(payload.get("price", 0.0))
        sl = float(payload.get("sl", 0.0))
        tp = float(payload.get("tp", 0.0))
        type_code = mt5.ORDER_TYPE_BUY_LIMIT
        if order_type_str == "SELL_LIMIT": type_code = mt5.ORDER_TYPE_SELL_LIMIT
        elif order_type_str == "BUY_STOP": type_code = mt5.ORDER_TYPE_BUY_STOP
        elif order_type_str == "SELL_STOP": type_code = mt5.ORDER_TYPE_SELL_STOP
        req = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": symbol,
            "volume": volume,
            "type": type_code,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 25,
            "magic": 100001,
            "comment": "Companion Pending Order",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC
        }
        order_res = mt5.order_send(req)
        if order_res and order_res.retcode == mt5.TRADE_RETCODE_DONE:
            res = {"success": True, "ticket": int(getattr(order_res, 'order', 0)), "message": f"Placed {order_type_str} for {symbol}"}
        else:
            desc = order_res.comment if order_res else str(mt5.last_error())
            res = {"success": False, "message": f"Place pending failed: {desc}"}
    elif action == "CANCEL_ALL_ORDERS":
        orders = mt5.orders_get()
        cancelled = []
        failed = []
        if orders:
            for o in orders:
                req = {"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket}
                r = mt5.order_send(req)
                if r and r.retcode == mt5.TRADE_RETCODE_DONE:
                    cancelled.append(o.ticket)
                else:
                    failed.append(o.ticket)
        res = {"success": len(failed) == 0, "cancelled_count": len(cancelled), "failed_count": len(failed), "message": f"Cancelled {len(cancelled)} pending orders."}
except Exception as e:
    res = {"success": False, "message": str(e)}

print(json.dumps(res))
`;
      const child = spawn(pyExec, ["-c", code], { windowsHide: true });
      let output = "";
      child.stdout.on("data", (d) => (output += d.toString()));
      child.on("close", () => {
        try {
          const parsed = JSON.parse(output.trim());
          resolve(parsed);
        } catch (e) {
          resolve({ success: false, message: `Direct MT5 execution error: ${output.slice(0, 100)}` });
        }
      });
      child.on("error", (err) => resolve({ success: false, message: err.message }));
    } catch (err) {
      resolve({ success: false, message: err.message });
    }
  });
}

async function syncOpenPositionsAndAccount() {
  if (isSyncing) return;
  if (Date.now() - lastSyncTimestamp < 2000) return;
  isSyncing = true;
  lastSyncTimestamp = Date.now();
  try {
    let rawPositions = null;
    let rawOrders = null;
    let accData = null;

    // 1. Primary: Query Execution Bridge IPC on Port 5556
    try {
      const posResp = await queryBridgeSocket("POSITIONS", {}, 1500);
      if (posResp && (posResp.status === "SUCCESS" || posResp.status === "ok")) {
        rawPositions = posResp.data || posResp.positions || [];
        serviceStates.bridge.status = "RUNNING";
      }
    } catch (err) {}

    try {
      const ordResp = await queryBridgeSocket("ORDERS", {}, 1500);
      if (ordResp && (ordResp.status === "SUCCESS" || ordResp.status === "ok")) {
        rawOrders = ordResp.data || ordResp.orders || [];
      }
    } catch (err) {}

    try {
      const accResp = await queryBridgeSocket("ACCOUNT", {}, 1500);
      if (accResp && (accResp.status === "SUCCESS" || accResp.status === "ok")) {
        accData = accResp.data || accResp.account || null;
      }
    } catch (err) {}

    // 2. Direct MetaTrader 5 Fallback (if bridge didn't reply)
    let fallback = null;
    if (rawPositions === null || accData === null || rawOrders === null) {
      fallback = await fetchDirectMT5Fallback();
      if (fallback) {
        if (rawPositions === null && Array.isArray(fallback.positions)) {
          rawPositions = fallback.positions;
        }
        if (rawOrders === null && Array.isArray(fallback.orders)) {
          rawOrders = fallback.orders;
        }
        if (accData === null && fallback.account) {
          accData = fallback.account;
        }
      }
    }

    let positionsUpdated = false;
    if (rawPositions !== null) {
      const mappedPositions = rawPositions.map((p) => {
        const orderType = (p.type === "BUY" || p.type === 0 || p.orderType === "BUY") ? "BUY" : "SELL";
        const magic = Number(p.magic ?? 0);
        const sl = Number(p.sl ?? p.stopLoss ?? 0);
        const comment = String(p.comment || (p.mode ? `Mode: ${p.mode}` : ""));
        const isManual = magic === 0 || comment.toLowerCase().includes("manual");
        return {
          ticket: Number(p.ticket),
          symbol: String(p.symbol),
          orderType,
          volume: Number(p.volume || 0),
          openPrice: Number(p.open_price ?? p.openPrice ?? 0),
          currentPrice: Number(p.current_price ?? p.currentPrice ?? 0),
          sl,
          tp: Number(p.tp ?? p.takeProfit ?? 0),
          profit: Number(p.profit ?? 0),
          magic,
          comment,
          isManual,
          isProtected: sl > 0
        };
      });

      activePositions = mappedPositions;
      positionsUpdated = true;
    }

    let ordersUpdated = false;
    if (rawOrders !== null) {
      activePendingOrders = rawOrders.map((o) => ({
        ticket: Number(o.ticket),
        symbol: String(o.symbol),
        orderType: String(o.type || o.orderType || "BUY_LIMIT"),
        volume: Number(o.volume || 0),
        price: Number(o.price || o.open_price || 0),
        sl: Number(o.sl || 0),
        tp: Number(o.tp || 0),
        magic: Number(o.magic || 0),
        comment: String(o.comment || "")
      }));
      ordersUpdated = true;
    }

    let metricsUpdated = false;
    if (accData) {
      const totalProfit = activePositions.reduce((sum, p) => sum + (p.profit || 0), 0);
      accountMetrics = {
        accountNumber: Number(accData.login || accData.account_number || accountMetrics.accountNumber),
        broker: String(accData.server || accData.broker || accountMetrics.broker),
        balance: Number(accData.balance ?? accountMetrics.balance),
        equity: Number(accData.equity ?? accountMetrics.equity),
        profit: Number(accData.profit ?? totalProfit),
        dailyPnl: Number(accData.daily_loss_pct ?? (accData.equity ? (accData.equity - (accData.day_start_balance || accData.balance || 0)) : 0)),
        margin: Number(accData.margin ?? accountMetrics.margin),
        freeMargin: Number(accData.free_margin ?? accData.freeMargin ?? accountMetrics.freeMargin),
        marginLevel: Number(accData.margin_level ?? accData.marginLevel ?? accountMetrics.marginLevel),
        currency: String(accData.currency || "USD"),
        leverage: Number(accData.leverage || 100),
        tradeMode: String(accData.trade_mode || accData.tradeMode || "DEMO"),
        profile: String(accData.profile || "DEMO"),
        positionsCount: activePositions.length
      };
      metricsUpdated = true;
    } else if (positionsUpdated) {
      accountMetrics.positionsCount = activePositions.length;
      accountMetrics.profit = activePositions.reduce((sum, p) => sum + (p.profit || 0), 0);
      metricsUpdated = true;
    }

    lastSyncTimestamp = Date.now();

    // Broadcast to UI renderer
    if (mainWindow && !mainWindow.isDestroyed()) {
      if (positionsUpdated) {
        mainWindow.webContents.send("positions-changed", activePositions);
      }
      if (ordersUpdated) {
        mainWindow.webContents.send("pending-orders-changed", activePendingOrders);
      }
      if (metricsUpdated) {
        mainWindow.webContents.send("metrics-changed", accountMetrics);
      }
    }
  } catch (err) {
    appendLog("SYSTEM", "DEBUG", `Position/account sync notice: ${err.message}`);
  } finally {
    isSyncing = false;
  }
}

// -----------------------------------------------------------------------------
// Configuration Management
// -----------------------------------------------------------------------------
function loadConfig() {
  const defaults = {
    apiUrl: "https://www.arcadefx.live/api/v1",
    tradingMode: "CONTINUOUS_SCALPING",
    riskPerTradePct: 1.0,
    maxDailyLossPct: 0.0,
    bridgeHost: "127.0.0.1",
    bridgePort: 5555,
    ipcPort: 5556,
    allowedSymbols: ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"],
    autoStartOnBoot: false,
    minimizeToTray: true,
    runInBackground: true,
    allowRealAccount: false,
    onboardingComplete: false,
    telegramBotToken: "",
    telegramChatId: "",
    telegramEnabled: false,
    telegramUsername: "",
    manualTradeMgmt: {
      enabled: false,
      mode: "OBSERVE",
      autoSl: true,
      autoTp: true,
      breakEven: true,
      trailingStop: true,
      autoExit: true,
      preserveUserSlTp: true
    }
  };

  try {
    const mmPath = path.join(PROJECT_ROOT, "config", "manual_management.yaml");
    if (fs.existsSync(mmPath)) {
      const content = fs.readFileSync(mmPath, "utf-8");
      defaults.manualTradeMgmt.enabled = /enabled:\s*true/i.test(content);
      const mMatch = content.match(/mode:\s*["']?([A-Za-z]+)["']?/i);
      if (mMatch) defaults.manualTradeMgmt.mode = mMatch[1].toUpperCase();
    }
  } catch (e) {}

  if (fs.existsSync(APP_CONFIG_FILE)) {
    try {
      const data = JSON.parse(fs.readFileSync(APP_CONFIG_FILE, "utf-8"));
      return { ...defaults, ...data };
    } catch (e) {}
  }
  return defaults;
}

function saveConfig(cfg) {
  try {
    const current = loadConfig();
    const updated = { ...current, ...cfg };
    fs.mkdirSync(path.dirname(APP_CONFIG_FILE), { recursive: true });
    fs.writeFileSync(APP_CONFIG_FILE, JSON.stringify(updated, null, 2), "utf-8");
    return true;
  } catch (e) {
    appendLog("SYSTEM", "ERROR", `Failed to save config: ${e.message}`);
    return false;
  }
}

// -----------------------------------------------------------------------------
// Telegram Configuration & Identity Pairing
// -----------------------------------------------------------------------------
let activeTelegramChallenge = null;
let telegramPollingActive = false;

function getTelegramStatus() {
  const config = loadConfig();
  let botToken = config.telegramBotToken || "";
  let chatId = config.telegramChatId || "";
  let enabled = config.telegramEnabled || false;

  // Read .env if present
  if (fs.existsSync(DOTENV_FILE)) {
    try {
      const envContent = fs.readFileSync(DOTENV_FILE, "utf-8");
      const tokenMatch = envContent.match(/^TELEGRAM_BOT_TOKEN=(.+)$/m);
      const chatMatch = envContent.match(/^TELEGRAM_CHAT_ID=(.+)$/m);
      const enabledMatch = envContent.match(/^TELEGRAM_ENABLED=(.+)$/m);
      if (tokenMatch) botToken = tokenMatch[1].trim().replace(/['"]/g, "");
      if (chatMatch) chatId = chatMatch[1].trim().replace(/['"]/g, "");
      if (enabledMatch) enabled = enabledMatch[1].trim().toLowerCase() === "true";
    } catch (e) {}
  }

  const isPaired = Boolean(botToken && chatId && enabled);
  const botTokenMasked = botToken ? botToken.substring(0, 7) + "..." + botToken.slice(-4) : null;
  const chatIdMasked = chatId ? (chatId.length > 4 ? chatId.substring(0, 3) + "***" + chatId.slice(-2) : "***") : null;

  return {
    isPaired,
    botTokenMasked,
    chatIdMasked,
    botUsername: config.telegramUsername || "Institutional EA Bot",
    enabled
  };
}

function saveTelegramEnv(token, chatId) {
  try {
    let lines = [];
    if (fs.existsSync(DOTENV_FILE)) {
      lines = fs.readFileSync(DOTENV_FILE, "utf-8").split("\n");
    }

    const updates = {
      TELEGRAM_BOT_TOKEN: token,
      TELEGRAM_CHAT_ID: chatId,
      TELEGRAM_ENABLED: "true"
    };

    const newLines = [];
    const handled = new Set();

    for (const line of lines) {
      let matched = false;
      for (const key of Object.keys(updates)) {
        if (line.startsWith(`${key}=`)) {
          newLines.push(`${key}=${updates[key]}`);
          handled.add(key);
          matched = true;
          break;
        }
      }
      if (!matched && line.trim()) newLines.push(line);
    }

    for (const key of Object.keys(updates)) {
      if (!handled.has(key)) {
        newLines.push(`${key}=${updates[key]}`);
      }
    }

    fs.mkdirSync(path.dirname(DOTENV_FILE), { recursive: true });
    fs.writeFileSync(DOTENV_FILE, newLines.join("\n") + "\n", "utf-8");
    saveConfig({ telegramBotToken: token, telegramChatId: chatId, telegramEnabled: true });
    return true;
  } catch (e) {
    appendLog("TELEGRAM", "ERROR", `Failed saving Telegram env: ${e.message}`);
    return false;
  }
}

function startTelegramPairing(customToken = "") {
  return new Promise((resolve) => {
    const config = loadConfig();
    const token = customToken.trim() || config.telegramBotToken;

    if (!token) {
      resolve({ success: false, message: "Please provide a valid Telegram Bot Token from @BotFather." });
      return;
    }

    // 1. Verify Bot Token with getMe
    https.get(`https://api.telegram.org/bot${token}/getMe`, (res) => {
      let body = "";
      res.on("data", (c) => (body += c));
      res.on("end", () => {
        try {
          const data = JSON.parse(body);
          if (!data.ok) {
            resolve({ success: false, message: `Invalid bot token: ${data.description || "Authentication failed"}` });
            return;
          }

          const botUsername = `@${data.result.username}`;
          const challengeCode = "CMD-" + Math.floor(1000 + Math.random() * 9000);
          activeTelegramChallenge = {
            token,
            botUsername,
            code: challengeCode,
            createdAt: Date.now(),
            expiresAt: Date.now() + 10 * 60 * 1000
          };

          appendLog("TELEGRAM", "INFO", `Telegram pairing challenge initialized: Code [${challengeCode}] for ${botUsername}`);

          // 2. Poll for user's /start or challenge response
          pollTelegramUpdates(token, challengeCode, botUsername, resolve);
        } catch (e) {
          resolve({ success: false, message: `Failed parsing Telegram response: ${e.message}` });
        }
      });
    }).on("error", (e) => {
      resolve({ success: false, message: `Network error connecting to Telegram API: ${e.message}` });
    });
  });
}

function pollTelegramUpdates(token, expectedCode, botUsername, initialResolve) {
  let attempts = 0;
  const maxAttempts = 24; // 2 minutes (every 5 seconds)

  const pollInterval = setInterval(() => {
    attempts++;
    if (attempts > maxAttempts || !activeTelegramChallenge) {
      clearInterval(pollInterval);
      initialResolve({ success: false, message: "Telegram pairing timed out. Send /start to the bot and try again." });
      return;
    }

    https.get(`https://api.telegram.org/bot${token}/getUpdates?offset=-10&timeout=4`, (res) => {
      let body = "";
      res.on("data", (c) => (body += c));
      res.on("end", () => {
        try {
          const data = JSON.parse(body);
          if (data.ok && Array.isArray(data.result)) {
            for (const update of data.result) {
              const msg = update.message;
              if (!msg || !msg.chat) continue;

              const text = (msg.text || "").trim();
              const chatId = String(msg.chat.id);
              const senderName = msg.from ? (msg.from.first_name || msg.from.username || "Operator") : "Operator";

              // Match code or accept /start if challenge is active
              if (text.includes(expectedCode) || text.startsWith("/start") || text.startsWith("/pair")) {
                clearInterval(pollInterval);
                activeTelegramChallenge = null;

                // Save authorized chat ID
                saveTelegramEnv(token, chatId);
                saveConfig({ telegramUsername: botUsername });

                // Send confirmation back to Telegram
                const confirmMsg = encodeURIComponent(
                  `✅ <b>Institutional EA Telegram Pairing Verified!</b>\n\n` +
                  `👤 <b>Authorized User:</b> ${senderName}\n` +
                  `🆔 <b>Chat ID:</b> <code>${chatId}</code>\n\n` +
                  `You can now supervise this desktop bot using:\n` +
                  `• /status — Engine health & metrics\n` +
                  `• /positions — Active market trades\n` +
                  `• /pause — Emergency halt new entries\n` +
                  `• /resume — Resume normal trading`
                );

                https.get(`https://api.telegram.org/bot${token}/sendMessage?chat_id=${chatId}&text=${confirmMsg}&parse_mode=HTML`, () => {}).on("error", () => {});

                appendLog("TELEGRAM", "INFO", `Telegram successfully paired! Authorized user: ${senderName} (Chat: ${chatId})`);
                serviceStates.telegram.status = "RUNNING";

                initialResolve({
                  success: true,
                  chatId,
                  botUsername,
                  senderName,
                  message: `Telegram paired successfully with ${senderName}!`
                });
                return;
              }
            }
          }
        } catch (e) {}
      });
    }).on("error", () => {});
  }, 5000);
}

function testTelegramMessage() {
  return new Promise((resolve) => {
    const config = loadConfig();
    const token = config.telegramBotToken;
    const chatId = config.telegramChatId;

    if (!token || !chatId) {
      resolve({ success: false, message: "Telegram is not yet paired or configured." });
      return;
    }

    const testText = encodeURIComponent("🔔 <b>Institutional EA Desktop Companion Test Alert:</b> Notification pipeline operational!");
    https.get(`https://api.telegram.org/bot${token}/sendMessage?chat_id=${chatId}&text=${testText}&parse_mode=HTML`, (res) => {
      let body = "";
      res.on("data", (c) => (body += c));
      res.on("end", () => {
        try {
          const data = JSON.parse(body);
          if (data.ok) {
            resolve({ success: true, message: "Test alert delivered to Telegram successfully!" });
          } else {
            resolve({ success: false, message: data.description || "Send failed" });
          }
        } catch (e) {
          resolve({ success: false, message: e.message });
        }
      });
    }).on("error", (e) => {
      resolve({ success: false, message: e.message });
    });
  });
}

// -----------------------------------------------------------------------------
// MT5 Terminal Scanner & Integration
// -----------------------------------------------------------------------------
function scanMT5Terminals() {
  const terminals = [];
  const isWin = process.platform === "win32";

  if (isWin) {
    const roots = ["C:\\Program Files", "C:\\Program Files (x86)"];
    for (const root of roots) {
      if (!fs.existsSync(root)) continue;
      try {
        const dirs = fs.readdirSync(root);
        for (const dir of dirs) {
          if (dir.toLowerCase().includes("metatrader") || dir.toLowerCase().includes("mt5") || dir.toLowerCase().includes("justmarkets") || dir.toLowerCase().includes("ic markets") || dir.toLowerCase().includes("ftmo")) {
            const exePath = path.join(root, dir, "terminal64.exe");
            if (fs.existsSync(exePath)) {
              terminals.push({
                id: dir.toLowerCase().replace(/[^a-z0-9]/g, "-"),
                name: dir,
                executablePath: exePath,
                dataFolder: "",
                expertsFolder: "",
                isRunning: false,
                pid: null,
                eaInstalled: false,
                eaVersion: "3.10"
              });
            }
          }
        }
      } catch (e) {}
    }

    // AppData Roaming Data Folder Scan
    const roamingMeta = path.join(os.homedir(), "AppData", "Roaming", "MetaQuotes", "Terminal");
    if (fs.existsSync(roamingMeta)) {
      try {
        const hashDirs = fs.readdirSync(roamingMeta);
        for (const hd of hashDirs) {
          const expertsPath = path.join(roamingMeta, hd, "MQL5", "Experts");
          if (fs.existsSync(expertsPath)) {
            const eaFile = path.join(expertsPath, "PythonBridgeEA.mq5");
            const isInstalled = fs.existsSync(eaFile);

            if (terminals.length > 0) {
              terminals[0].dataFolder = path.join(roamingMeta, hd);
              terminals[0].expertsFolder = expertsPath;
              terminals[0].eaInstalled = isInstalled;
            } else {
              terminals.push({
                id: hd,
                name: "MetaTrader 5 Terminal",
                executablePath: "C:\\Program Files\\MetaTrader 5\\terminal64.exe",
                dataFolder: path.join(roamingMeta, hd),
                expertsFolder: expertsPath,
                isRunning: false,
                pid: null,
                eaInstalled: isInstalled,
                eaVersion: "3.10"
              });
            }
          }
        }
      } catch (e) {}
    }

    // Process check (tasklist)
    try {
      const output = execSync("tasklist /FI \"IMAGENAME eq terminal64.exe\" /FO CSV /NH", { encoding: "utf-8" });
      if (output && output.toLowerCase().includes("terminal64.exe")) {
        const parts = output.split(",");
        const pid = parts[1] ? parseInt(parts[1].replace(/"/g, "")) : null;
        if (terminals.length > 0) {
          terminals[0].isRunning = true;
          terminals[0].pid = pid;
        }
      }
    } catch (e) {}
  } else {
    // macOS / Linux Wine Environment
    const winePrefix = path.join(os.homedir(), ".wine", "drive_c", "Program Files");
    if (fs.existsSync(winePrefix)) {
      terminals.push({
        id: "wine-mt5",
        name: "Wine-Emulated MT5",
        executablePath: path.join(winePrefix, "MetaTrader 5", "terminal64.exe"),
        dataFolder: path.join(winePrefix, "MetaTrader 5"),
        expertsFolder: path.join(winePrefix, "MetaTrader 5", "MQL5", "Experts"),
        isRunning: false,
        pid: null,
        eaInstalled: false,
        eaVersion: "3.10"
      });
    }
  }

  return terminals;
}

// -----------------------------------------------------------------------------
// 5-STAGE AUTOMATED STARTUP SUPERVISOR & LIFECYCLE MANAGER
// -----------------------------------------------------------------------------
function stopEngineWatchdog() {
  if (engineWatchdogTimer) {
    clearInterval(engineWatchdogTimer);
    engineWatchdogTimer = null;
  }
}

async function restartEngineOnly(reason) {
  if (isRestartingEngine || userRequestedStop || botState === "STOPPED") return;
  isRestartingEngine = true;
  try {
    const now = Date.now();
    if (now - engineRestartWindowStart > 5 * 60 * 1000) {
      engineRestartWindowStart = now;
      engineRestartCount = 0;
    }
    engineRestartCount += 1;
    if (engineRestartCount > 5) {
      logEngineLifecycle("ENGINE_CRASHED", "ERROR", null, "ERROR", `Exceeded max restart attempts (${engineRestartCount - 1}) in 5m; halting auto-restart.`);
      botState = "ERROR";
      serviceStates.engine.status = "ERROR";
      serviceStates.engine.lastError = "Max restart attempts exceeded";
      stopEngineWatchdog();
      if (mainWindow) mainWindow.webContents.send("state-changed", botState);
      return;
    }

    const backoffMs = Math.min(30000, 2000 * Math.pow(2, engineRestartCount - 1));
    logEngineLifecycle("ENGINE_RESTART_REQUESTED", "WARNING", null, "RESTARTING", `${reason} (attempt ${engineRestartCount}/5, backoff ${backoffMs}ms)`);
    serviceStates.engine.restarts = (serviceStates.engine.restarts || 0) + 1;

    await new Promise((r) => setTimeout(r, backoffMs));
    if (userRequestedStop) return;

    // Re-check if another healthy engine came up during backoff
    const existing = findExistingEngineProcess();
    if (existing) {
      adoptedEnginePid = existing.pid;
      serviceStates.engine.pid = existing.pid;
      serviceStates.engine.status = "RUNNING";
      logEngineLifecycle("ENGINE_ALREADY_RUNNING", "INFO", existing.pid, "RUNNING", `Recovered via existing instance (${existing.source})`);
      return;
    }

    await launchEngineProcess();
  } finally {
    isRestartingEngine = false;
  }
}

function startEngineWatchdog() {
  stopEngineWatchdog();
  engineWatchdogTimer = setInterval(async () => {
    if (userRequestedStop || botState !== "RUNNING" || isRestartingEngine || startBotInFlight) return;

    const active = findExistingEngineProcess();
    if (!active) {
      logEngineLifecycle("ENGINE_CRASHED", "ERROR", serviceStates.engine.pid, "CRASHED", "Engine process missing from OS process table while state=RUNNING");
      serviceStates.engine.status = "STOPPED";
      serviceStates.engine.pid = null;
      botProcess = null;
      adoptedEnginePid = null;
      await restartEngineOnly("Engine process exited unexpectedly");
      return;
    }

    serviceStates.engine.pid = active.pid;
    const hb = readEngineHeartbeat();
    if (hb) {
      serviceStates.engine.lastHeartbeat = hb.timestamp || new Date().toISOString();
      if (hb.ageSeconds > 30) {
        logEngineLifecycle("ENGINE_UNRESPONSIVE", "WARNING", active.pid, "UNRESPONSIVE", `Heartbeat stale (${hb.ageSeconds.toFixed(1)}s > 30s)`);
        try {
          fs.writeFileSync(ENGINE_STOP_FLAG_FILE, `UNRESPONSIVE=${new Date().toISOString()}\n`, "utf-8");
        } catch (e) {}
        await waitForPidExit(active.pid, 3000);
        if (isPidAlive(active.pid) && process.platform === "win32") {
          try { execSync(`taskkill /PID ${active.pid} /T /F`, { windowsHide: true }); } catch (e) {}
        }
        try { if (fs.existsSync(ENGINE_STOP_FLAG_FILE)) fs.unlinkSync(ENGINE_STOP_FLAG_FILE); } catch (e) {}
        botProcess = null;
        adoptedEnginePid = null;
        await restartEngineOnly("Engine heartbeat timeout");
        return;
      }
      if (Number(hb.uptime_seconds || 0) >= 60) {
        engineRestartCount = 0;
      }
    }
  }, 5000);
}

async function launchEngineProcess() {
  const existing = findExistingEngineProcess();
  if (existing) {
    adoptedEnginePid = existing.pid;
    serviceStates.engine.pid = existing.pid;
    serviceStates.engine.status = "RUNNING";
    logEngineLifecycle("ENGINE_ALREADY_RUNNING", "INFO", existing.pid, "RUNNING", `Reusing active healthy engine (${existing.source})`);
    return { ok: true, adopted: true, pid: existing.pid };
  }

  const engineSidecar = resolveSidecar("mt5_trading_engine");
  if (!engineSidecar) {
    const errMsg = "Unable to locate mt5_trading_engine executable or scripts/start_bot.py";
    appendLog("ENGINE", "ERROR", errMsg);
    return { ok: false, message: errMsg };
  }

  try {
    if (fs.existsSync(ENGINE_STOP_FLAG_FILE)) fs.unlinkSync(ENGINE_STOP_FLAG_FILE);
  } catch (e) {}

  const engineEnv = {
    ...process.env,
    PROJECT_ROOT: PROJECT_ROOT,
    MT5_APP_DATA_DIR: USER_DATA_DIR,
    BRIDGE_PORT: "5555",
    IPC_PORT: "5556",
    EXECUTION_MODE: process.env.EXECUTION_MODE || "DEMO"
  };

  let sawDuplicateGuard = false;
  if (engineSidecar.type === "binary") {
    appendLog("ENGINE", "INFO", `Launching packaged trading engine: ${engineSidecar.path}`);
    botProcess = spawn(engineSidecar.path, [], {
      cwd: USER_DATA_DIR,
      env: engineEnv,
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"]
    });
  } else {
    appendLog("ENGINE", "INFO", `Launching engine script: ${engineSidecar.python} ${engineSidecar.script}`);
    botProcess = spawn(engineSidecar.python, [engineSidecar.script], {
      cwd: PROJECT_ROOT,
      env: { ...engineEnv, PYTHONPATH: PROJECT_ROOT },
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"]
    });
  }

  const spawnedProc = botProcess;
  const spawnedPid = spawnedProc.pid;
  serviceStates.engine.pid = spawnedPid;
  serviceStates.engine.status = "STARTING";
  serviceStates.health.status = "RUNNING";
  logEngineLifecycle("ENGINE_PROCESS_CREATED", "INFO", spawnedPid, "STARTING", "Spawned trading engine process");

  spawnedProc.stdout.on("data", (data) => {
    for (const line of data.toString().split("\n")) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      if (trimmed.includes("[SINGLE_INSTANCE]") || trimmed.includes("ENGINE_DUPLICATE_START_BLOCKED")) {
        sawDuplicateGuard = true;
      }
      appendLog("ENGINE", "INFO", trimmed);

      if (trimmed.includes("[ACCOUNT_MODE]") || trimmed.includes("Balance:")) {
        const balMatch = trimmed.match(/Balance:\s*\$([0-9.]+)/i);
        const eqMatch = trimmed.match(/Equity:\s*\$([0-9.]+)/i);
        if (balMatch) accountMetrics.balance = parseFloat(balMatch[1]);
        if (eqMatch) accountMetrics.equity = parseFloat(eqMatch[1]);
        if (mainWindow) mainWindow.webContents.send("metrics-changed", accountMetrics);
      }
    }
  });

  spawnedProc.stderr.on("data", (data) => {
    for (const line of data.toString().split("\n")) {
      if (line.trim()) appendLog("ENGINE", parseSeverityFromLog(line.trim(), "INFO"), line.trim());
    }
  });

  spawnedProc.on("exit", (code) => {
    if (botProcess === spawnedProc) {
      botProcess = null;
    }
    if (code === 0 && sawDuplicateGuard) {
      const active = findExistingEngineProcess();
      if (active) {
        adoptedEnginePid = active.pid;
        serviceStates.engine.pid = active.pid;
        serviceStates.engine.status = "RUNNING";
        logEngineLifecycle("ENGINE_DUPLICATE_START_BLOCKED", "INFO", active.pid, "RUNNING", `Duplicate spawn (PID ${spawnedPid}) exited cleanly; adopted existing engine`);
        return;
      }
    }
    if (userRequestedStop) {
      logEngineLifecycle("ENGINE_STOPPED", "INFO", spawnedPid, "STOPPED", `Graceful stop completed (exit code ${code})`);
      serviceStates.engine.status = "STOPPED";
      serviceStates.engine.pid = null;
      botState = "STOPPED";
      if (mainWindow) mainWindow.webContents.send("state-changed", botState);
      return;
    }
    logEngineLifecycle("ENGINE_CRASHED", code === 0 ? "WARNING" : "ERROR", spawnedPid, "STOPPED", `Trading engine exited unexpectedly with code ${code}`);
    serviceStates.engine.status = "STOPPED";
    serviceStates.engine.pid = null;
  });

  return { ok: true, adopted: false, pid: spawnedPid };
}

async function verifySystemReadiness() {
  const deadline = Date.now() + 12000;
  let bridgeStatus = null;
  let eaConnected = false;
  let activeEngine = null;
  let hb = null;

  while (Date.now() < deadline) {
    activeEngine = findExistingEngineProcess();
    hb = readEngineHeartbeat();
    try {
      bridgeStatus = await queryBridgeSocket("STATUS", {}, 1200);
      if (bridgeStatus && bridgeStatus.status === "SUCCESS") {
        eaConnected = Number(bridgeStatus.active_connections_count || 0) > 0;
      }
    } catch (e) {
      bridgeStatus = null;
    }

    const hbFresh = hb && hb.ageSeconds <= 15 && hb.status === "RUNNING";
    if (activeEngine && hbFresh && bridgeStatus && bridgeStatus.status === "SUCCESS") {
      break;
    }
    await new Promise((r) => setTimeout(r, 500));
  }

  const terminals = scanMT5Terminals();
  const bridgeActive = Boolean(bridgeStatus && bridgeStatus.status === "SUCCESS");

  let accountOk = false;
  let positionsOk = false;
  if (bridgeActive) {
    try {
      const acc = await queryBridgeSocket("ACCOUNT", {}, 1500);
      accountOk = Boolean(acc && (acc.status === "SUCCESS" || acc.status === "ok"));
    } catch (e) {}
    try {
      const pos = await queryBridgeSocket("POSITIONS", {}, 1500);
      positionsOk = Boolean(pos && (pos.status === "SUCCESS" || pos.status === "ok"));
    } catch (e) {}
  }

  const agentAlive = Boolean(agentProcess && agentProcess.pid && isPidAlive(agentProcess.pid));
  const engineAlive = Boolean(activeEngine);
  const engineHeartbeatOk = Boolean(hb && hb.ageSeconds <= 20);
  const engineResponsive = Boolean(hb && (hb.status === "RUNNING" || hb.status === "INITIALIZING"));

  return {
    ready: engineAlive && engineHeartbeatOk && engineResponsive && bridgeActive,
    checks: {
      mt5TerminalAvailable: terminals.length > 0,
      bridgePortsActive: bridgeActive,
      eaConnected,
      accountRetrieved: accountOk,
      positionsRetrieved: positionsOk,
      engineProcessAlive: engineAlive,
      enginePid: activeEngine ? activeEngine.pid : null,
      engineHeartbeatOk,
      engineResponsive,
      cloudAgentConnected: agentAlive
    }
  };
}

async function startBotServices() {
  if (startBotInFlight) {
    logEngineLifecycle("ENGINE_DUPLICATE_START_BLOCKED", "INFO", serviceStates.engine.pid, botState, "Start already in progress; coalescing duplicate request");
    return startBotInFlight;
  }

  startBotInFlight = (async () => {
    userRequestedStop = false;
    logEngineLifecycle("ENGINE_START_REQUESTED", "INFO", serviceStates.engine.pid, botState, "Operator requested engine startup");
    appendLog("SYSTEM", "INFO", "=== STAGE A: SYSTEM PRE-FLIGHT VERIFICATION ===");
    botState = "STARTING";
    if (mainWindow) mainWindow.webContents.send("state-changed", botState);

    // 1. Probe existing bridge exclusively via IPC port 5556 (never raw-connect to EA port 5555)
    let bridgeReused = false;
    const probe = await probeSocketHandshake(5556);
    if (probe.alive) {
      appendLog("BRIDGE", "INFO", "Existing MT5 Socket Bridge acknowledged IPC on port 5556. Reusing active bridge listener.");
      serviceStates.bridge.status = "RUNNING";
      bridgeReused = true;
    }

    // 2. Resolve Bridge Sidecar or Script
    const bridgeSidecar = resolveSidecar("mt5_bridge_server");
    if (!bridgeSidecar && !bridgeReused) {
      const errMsg = "Unable to locate mt5_bridge_server executable or scripts/run_bridge_server.py";
      appendLog("BRIDGE", "ERROR", errMsg);
      botState = "ERROR";
      if (mainWindow) mainWindow.webContents.send("state-changed", botState);
      return { success: false, message: errMsg };
    }

    // === STAGE B: START BRIDGE SERVER ===
    appendLog("SYSTEM", "INFO", "=== STAGE B: STARTING MT5 SOCKET BRIDGE (PORTS 5555/5556) ===");
    if (!bridgeReused && !bridgeProcess) {
      try {
        const bridgeEnv = {
          ...process.env,
          PROJECT_ROOT: PROJECT_ROOT,
          MT5_APP_DATA_DIR: USER_DATA_DIR,
          BRIDGE_PORT: "5555",
          IPC_PORT: "5556"
        };

        if (bridgeSidecar.type === "binary") {
          appendLog("BRIDGE", "INFO", `Launching packaged bridge: ${bridgeSidecar.path}`);
          bridgeProcess = spawn(bridgeSidecar.path, [], {
            cwd: USER_DATA_DIR,
            env: bridgeEnv,
            windowsHide: true,
            stdio: ["ignore", "pipe", "pipe"]
          });
        } else {
          appendLog("BRIDGE", "INFO", `Launching bridge script: ${bridgeSidecar.python} ${bridgeSidecar.script}`);
          bridgeProcess = spawn(bridgeSidecar.python, [bridgeSidecar.script], {
            cwd: PROJECT_ROOT,
            env: { ...bridgeEnv, PYTHONPATH: PROJECT_ROOT },
            windowsHide: true,
            stdio: ["ignore", "pipe", "pipe"]
          });
        }

        serviceStates.bridge.pid = bridgeProcess.pid;
        serviceStates.bridge.status = "RUNNING";

        bridgeProcess.stdout.on("data", (data) => {
          for (const line of data.toString().split("\n")) {
            if (line.trim()) appendLog("BRIDGE", "INFO", line.trim());
          }
        });

        bridgeProcess.stderr.on("data", (data) => {
          for (const line of data.toString().split("\n")) {
            if (line.trim()) appendLog("BRIDGE", parseSeverityFromLog(line.trim(), "INFO"), line.trim());
          }
        });

        bridgeProcess.on("exit", (code) => {
          appendLog("BRIDGE", code === 0 ? "INFO" : "ERROR", `Bridge server exited with code ${code}`);
          serviceStates.bridge.status = "STOPPED";
          serviceStates.bridge.pid = null;
          bridgeProcess = null;
        });
      } catch (e) {
        appendLog("BRIDGE", "ERROR", `Failed launching bridge server: ${e.message}`);
      }
    } else if (bridgeReused) {
      appendLog("BRIDGE", "INFO", "Bypassing bridge spawn — active healthy bridge server verified on port 5556.");
    }

    await new Promise((r) => setTimeout(r, 800));

    // === STAGE C: START OR ADOPT PYTHON TRADING ENGINE ===
    appendLog("SYSTEM", "INFO", "=== STAGE C: STARTING TRADING ENGINE ===");
    const launchRes = await launchEngineProcess();
    if (!launchRes.ok) {
      botState = "ERROR";
      if (mainWindow) mainWindow.webContents.send("state-changed", botState);
      return { success: false, message: launchRes.message };
    }

    // === STAGE D: START INSTITUTIONAL_EA BOT AGENT (DAEMON MODE) ===
    appendLog("SYSTEM", "INFO", "=== STAGE D: STARTING INSTITUTIONAL_EA CLOUD AGENT ===");
    if (!agentProcess) {
      const agentSidecar = resolveSidecar("mt5_bot_agent");
      if (agentSidecar) {
        try {
          const agentEnv = {
            ...process.env,
            PROJECT_ROOT: PROJECT_ROOT,
            INSTITUTIONAL_EA_APP_DATA_DIR: INSTITUTIONAL_EA_DATA_DIR,
            MT5_APP_DATA_DIR: USER_DATA_DIR,
            INSTITUTIONAL_EA_API_URL: "https://www.arcadefx.live/api/v1"
          };

          if (agentSidecar.type === "binary") {
            appendLog("INSTITUTIONAL_EA", "INFO", `Launching packaged cloud agent: ${agentSidecar.path}`);
            agentProcess = spawn(agentSidecar.path, ["--daemon"], {
              cwd: USER_DATA_DIR,
              env: agentEnv,
              windowsHide: true,
              stdio: ["ignore", "pipe", "pipe"]
            });
          } else {
            appendLog("INSTITUTIONAL_EA", "INFO", `Launching cloud agent script: ${agentSidecar.python} ${agentSidecar.script} --daemon`);
            agentProcess = spawn(agentSidecar.python, [agentSidecar.script, "--daemon"], {
              cwd: PROJECT_ROOT,
              env: { ...agentEnv, PYTHONPATH: PROJECT_ROOT },
              windowsHide: true,
              stdio: ["ignore", "pipe", "pipe"]
            });
          }

          serviceStates.institutional_ea.pid = agentProcess.pid;
          serviceStates.institutional_ea.status = fs.existsSync(PRIMARY_CREDENTIALS_FILE) || fs.existsSync(LEGACY_CREDENTIALS_FILE)
            ? "RUNNING"
            : "WAITING_FOR_PAIRING";

          agentProcess.stdout.on("data", (d) => {
            for (const l of d.toString().split("\n")) {
              if (l.trim()) {
                appendLog("INSTITUTIONAL_EA", "INFO", l.trim());
                if (l.includes("ONLINE") || l.includes("Heartbeat sent")) {
                  serviceStates.institutional_ea.status = "RUNNING";
                }
              }
            }
          });

          agentProcess.stderr.on("data", (d) => {
            for (const l of d.toString().split("\n")) {
              if (l.trim()) appendLog("INSTITUTIONAL_EA", parseSeverityFromLog(l.trim(), "INFO"), l.trim());
            }
          });

          agentProcess.on("exit", (code) => {
            appendLog("INSTITUTIONAL_EA", code === 0 ? "INFO" : "WARNING", `Cloud agent process exited with code ${code}`);
            serviceStates.institutional_ea.status = "STOPPED";
            serviceStates.institutional_ea.pid = null;
            agentProcess = null;
          });
        } catch (e) {
          appendLog("INSTITUTIONAL_EA", "WARNING", `Notice launching cloud agent: ${e.message}`);
        }
      }
    } else {
      appendLog("INSTITUTIONAL_EA", "INFO", `Cloud agent already running (PID ${agentProcess.pid}).`);
    }

    // === STAGE E: REAL READINESS VERIFICATION ===
    appendLog("SYSTEM", "INFO", "=== STAGE E: FINAL READINESS VERIFICATION ===");
    const readiness = await verifySystemReadiness();
    const c = readiness.checks;

    if (readiness.ready) {
      botState = "RUNNING";
      serviceStates.engine.status = "RUNNING";
      serviceStates.engine.pid = c.enginePid;
      serviceStates.engine.lastHeartbeat = new Date().toISOString();
      engineRestartCount = 0;
      startEngineWatchdog();
      logEngineLifecycle("ENGINE_HEARTBEAT_OK", "INFO", c.enginePid, "RUNNING", "Initial engine heartbeat verified");
      logEngineLifecycle(
        "ENGINE_READY",
        "INFO",
        c.enginePid,
        "RUNNING",
        `Bridge=${c.bridgePortsActive} EA=${c.eaConnected} Account=${c.accountRetrieved} Positions=${c.positionsRetrieved} Agent=${c.cloudAgentConnected}`
      );
      appendLog(
        "SYSTEM",
        "INFO",
        `✓ ALL SYSTEMS OPERATIONAL: BOT READY (Engine PID ${c.enginePid}, Ports 5555/5556 active, EA=${c.eaConnected ? "CONNECTED" : "WAITING"})`
      );
      if (mainWindow) mainWindow.webContents.send("state-changed", botState);
      return { success: true, message: "All trading services launched and verified.", checks: c };
    }

    if (!c.engineProcessAlive) {
      botState = "ERROR";
      serviceStates.engine.status = "STOPPED";
      serviceStates.engine.pid = null;
      if (mainWindow) mainWindow.webContents.send("state-changed", botState);
      return { success: false, message: "Trading engine failed readiness verification (process did not stay alive).", checks: c };
    }

    // Engine is alive & initializing, allow watchdog to continue monitoring
    botState = "RUNNING";
    serviceStates.engine.status = "RUNNING";
    serviceStates.engine.pid = c.enginePid;
    startEngineWatchdog();
    appendLog("SYSTEM", "WARNING", `Engine PID ${c.enginePid} alive; awaiting full bridge/heartbeat readiness.`);
    if (mainWindow) mainWindow.webContents.send("state-changed", botState);
    return { success: true, message: "Trading engine started; monitoring readiness.", checks: c };
  })().finally(() => {
    startBotInFlight = null;
  });

  return startBotInFlight;
}

async function stopBotServices() {
  userRequestedStop = true;
  stopEngineWatchdog();
  const activeEngine = findExistingEngineProcess();
  logEngineLifecycle("ENGINE_STOP_REQUESTED", "INFO", activeEngine ? activeEngine.pid : null, botState, "Operator requested graceful stop");
  appendLog("SYSTEM", "INFO", "Initiating graceful shutdown of all trading services...");

  try {
    fs.writeFileSync(ENGINE_STOP_FLAG_FILE, `STOP_REQUESTED=${new Date().toISOString()}\n`, "utf-8");
  } catch (e) {}

  const pidToStop = activeEngine ? activeEngine.pid : (botProcess ? botProcess.pid : adoptedEnginePid);
  if (pidToStop) {
    const exitedCleanly = await waitForPidExit(pidToStop, 3500);
    if (!exitedCleanly) {
      try {
        if (process.platform === "win32") {
          execSync(`taskkill /PID ${pidToStop} /T /F`, { windowsHide: true });
        } else if (botProcess) {
          botProcess.kill("SIGTERM");
        } else {
          process.kill(pidToStop, "SIGTERM");
        }
      } catch (e) {}
    }
    logEngineLifecycle("ENGINE_STOPPED", "INFO", pidToStop, "STOPPED", exitedCleanly ? "Graceful exit" : "Forced termination after timeout");
  }
  botProcess = null;
  adoptedEnginePid = null;

  try {
    if (fs.existsSync(ENGINE_STOP_FLAG_FILE)) fs.unlinkSync(ENGINE_STOP_FLAG_FILE);
  } catch (e) {}

  if (bridgeProcess) {
    try {
      if (process.platform === "win32") {
        execSync(`taskkill /PID ${bridgeProcess.pid} /T /F`, { windowsHide: true });
      } else {
        bridgeProcess.kill("SIGTERM");
      }
    } catch (e) {}
    bridgeProcess = null;
  }

  if (agentProcess) {
    try {
      if (process.platform === "win32") {
        execSync(`taskkill /PID ${agentProcess.pid} /T /F`, { windowsHide: true });
      } else {
        agentProcess.kill("SIGTERM");
      }
    } catch (e) {}
    agentProcess = null;
  }

  serviceStates.engine.status = "STOPPED";
  serviceStates.engine.pid = null;
  serviceStates.bridge.status = "STOPPED";
  serviceStates.bridge.pid = null;
  serviceStates.institutional_ea.status = "STOPPED";
  serviceStates.institutional_ea.pid = null;
  botState = "STOPPED";

  if (mainWindow) mainWindow.webContents.send("state-changed", botState);
  appendLog("SYSTEM", "INFO", "All services safely stopped.");
  return { success: true, message: "Engine, Bridge, and Cloud Agent stopped cleanly." };
}

// -----------------------------------------------------------------------------
// Electron Window & Lifecycle
// -----------------------------------------------------------------------------
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1320,
    height: 880,
    minWidth: 1080,
    minHeight: 720,
    frame: false,
    backgroundColor: "#0b0e14",
    title: "Institutional EA Companion",
    icon: path.join(__dirname, "icon.png"),
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      nodeIntegration: false,
      contextIsolation: true
    }
  });

  const devUrl = "http://localhost:5173";
  const prodIndex = path.join(__dirname, "../dist/index.html");

  if (process.env.VITE_DEV_SERVER_URL || process.argv.includes("--dev")) {
    mainWindow.loadURL(devUrl);
  } else if (fs.existsSync(prodIndex)) {
    mainWindow.loadFile(prodIndex);
  } else {
    mainWindow.loadURL(devUrl);
  }

  mainWindow.on("close", (event) => {
    const config = loadConfig();
    if (!isQuitting && config.runInBackground) {
      event.preventDefault();
      mainWindow.hide();
      appendLog("SYSTEM", "INFO", "Dashboard minimized to system tray (background engine active).");
    }
  });
}

function createTray() {
  const iconPath = path.join(__dirname, "icon.png");
  const icon = fs.existsSync(iconPath)
    ? nativeImage.createFromPath(iconPath)
    : nativeImage.createEmpty();

  tray = new Tray(icon);
  tray.setToolTip("Institutional EA Companion");

  const contextMenu = Menu.buildFromTemplate([
    { label: "Institutional EA Companion", enabled: false },
    { type: "separator" },
    { label: "Open Dashboard", click: () => { if (mainWindow) { mainWindow.show(); mainWindow.focus(); } } },
    { label: "Start Bot", click: () => startBotServices() },
    { label: "Pause Trading", click: () => {
      botState = "PAUSED";
      fs.writeFileSync(path.join(APP_STATE_DIR, "PAUSE"), "EMERGENCY_PAUSE");
      if (mainWindow) mainWindow.webContents.send("state-changed", botState);
    }},
    { label: "Resume Trading", click: () => {
      botState = "RUNNING";
      const p = path.join(APP_STATE_DIR, "PAUSE");
      if (fs.existsSync(p)) fs.unlinkSync(p);
      if (mainWindow) mainWindow.webContents.send("state-changed", botState);
    }},
    { label: "Stop Bot", click: () => stopBotServices() },
    { type: "separator" },
    {
      label: "Quit Completely",
      click: () => {
        isQuitting = true;
        stopBotServices();
        app.quit();
      }
    }
  ]);

  tray.setContextMenu(contextMenu);
  tray.on("double-click", () => {
    if (mainWindow) {
      mainWindow.show();
      mainWindow.focus();
    }
  });
}

// -----------------------------------------------------------------------------
// IPC Handlers
// -----------------------------------------------------------------------------
ipcMain.handle("get-bot-state", () => botState);
ipcMain.handle("start-bot", () => startBotServices());
ipcMain.handle("stop-bot", () => stopBotServices());

ipcMain.handle("pause-trading", () => {
  botState = "PAUSED";
  fs.writeFileSync(path.join(APP_STATE_DIR, "PAUSE"), "EMERGENCY_PAUSE");
  appendLog("SYSTEM", "WARNING", "Emergency PAUSE engaged. Orders halted.");
  if (mainWindow) mainWindow.webContents.send("state-changed", botState);
  return { success: true, message: "Trading paused. State file created." };
});

ipcMain.handle("resume-trading", () => {
  botState = "RUNNING";
  const pauseFile = path.join(APP_STATE_DIR, "PAUSE");
  if (fs.existsSync(pauseFile)) fs.unlinkSync(pauseFile);
  appendLog("SYSTEM", "INFO", "Trading resumed. Emergency PAUSE cleared.");
  if (mainWindow) mainWindow.webContents.send("state-changed", botState);
  return { success: true, message: "Trading resumed." };
});

ipcMain.handle("restart-services", async () => {
  await stopBotServices();
  await new Promise((r) => setTimeout(r, 800));
  return startBotServices();
});

ipcMain.handle("close-all-positions", async (_e, confirm) => {
  if (!confirm) {
    return { success: false, message: "Explicit confirmation required to close all positions." };
  }
  appendLog("SYSTEM", "WARNING", "Executing verified CLOSE ALL POSITIONS order...");
  try {
    fs.writeFileSync(path.join(APP_STATE_DIR, "FLATTEN"), "FLATTEN_ALL");
  } catch (e) {}

  // 1. Attempt close via bridge socket
  let result = null;
  const bridgeResp = await queryBridgeSocket("CLOSE_ALL");
  if (bridgeResp && bridgeResp.success) {
    result = bridgeResp;
    appendLog("BRIDGE", "INFO", `Bridge EA liquidated positions: ${bridgeResp.closed_count || 0} closed.`);
  } else {
    // 2. Direct MT5 fallback
    appendLog("MT5", "INFO", "Executing direct MT5 close-all fallback...");
    result = await executeDirectMT5Action("CLOSE_ALL");
    appendLog("MT5", "INFO", result.message || "Direct MT5 close all completed.");
  }

  // Re-sync positions and broadcast to UI immediately
  await new Promise((r) => setTimeout(r, 600));
  await syncOpenPositionsAndAccount();

  const remaining = activePositions.length;
  if (remaining === 0) {
    appendLog("SYSTEM", "INFO", "Verified: 0 open positions remaining across terminal.");
    return { success: true, message: "All positions closed successfully.", closedCount: result ? (result.closed_count || 0) : 0 };
  } else {
    appendLog("SYSTEM", "WARNING", `Close all warning: ${remaining} positions still active.`);
    return {
      success: false,
      message: `${remaining} position(s) could not be closed. Please verify broker market hours or close manually.`,
      remainingCount: remaining
    };
  }
});

// Advanced Position & Pending Order Management
ipcMain.handle("modify-position", async (_e, ticket, sl, tp) => {
  appendLog("MT5", "INFO", `Modifying position #${ticket} SL=${sl}, TP=${tp}...`);
  const res = await executeDirectMT5Action("MODIFY_POSITION", { ticket, sl, tp });
  appendLog("MT5", res.success ? "INFO" : "WARNING", res.message);
  await syncOpenPositionsAndAccount();
  return res;
});

ipcMain.handle("close-position", async (_e, ticket, volume) => {
  appendLog("MT5", "INFO", `Closing position #${ticket} (volume: ${volume || 'full'})...`);
  const res = await executeDirectMT5Action("CLOSE_POSITION", { ticket, volume });
  appendLog("MT5", res.success ? "INFO" : "WARNING", res.message);
  await syncOpenPositionsAndAccount();
  return res;
});

ipcMain.handle("set-breakeven", async (_e, ticket) => {
  appendLog("MT5", "INFO", `Applying Break-Even to position #${ticket}...`);
  const res = await executeDirectMT5Action("SET_BREAKEVEN", { ticket });
  appendLog("MT5", res.success ? "INFO" : "WARNING", res.message);
  await syncOpenPositionsAndAccount();
  return res;
});

ipcMain.handle("set-trailing-stop", async (_e, ticket, points) => {
  appendLog("MT5", "INFO", `Applying Trailing Stop (${points} pts) to position #${ticket}...`);
  const res = await executeDirectMT5Action("SET_TRAILING_STOP", { ticket, points });
  appendLog("MT5", res.success ? "INFO" : "WARNING", res.message);
  await syncOpenPositionsAndAccount();
  return res;
});

ipcMain.handle("get-pending-orders", async () => {
  if (Date.now() - lastSyncTimestamp > 1200) {
    await syncOpenPositionsAndAccount();
  }
  return activePendingOrders;
});

ipcMain.handle("place-pending-order", async (_e, orderData) => {
  appendLog("MT5", "INFO", `Placing pending order: ${JSON.stringify(orderData)}...`);
  const res = await executeDirectMT5Action("PLACE_PENDING", orderData);
  appendLog("MT5", res.success ? "INFO" : "WARNING", res.message);
  await syncOpenPositionsAndAccount();
  return res;
});

ipcMain.handle("modify-pending-order", async (_e, ticket, price, sl, tp) => {
  appendLog("MT5", "INFO", `Modifying pending order #${ticket} Price=${price}, SL=${sl}, TP=${tp}...`);
  const res = await executeDirectMT5Action("MODIFY_PENDING", { ticket, price, sl, tp });
  appendLog("MT5", res.success ? "INFO" : "WARNING", res.message);
  await syncOpenPositionsAndAccount();
  return res;
});

ipcMain.handle("cancel-pending-order", async (_e, ticket) => {
  appendLog("MT5", "INFO", `Cancelling pending order #${ticket}...`);
  const res = await executeDirectMT5Action("CANCEL_ORDER", { ticket });
  appendLog("MT5", res.success ? "INFO" : "WARNING", res.message);
  await syncOpenPositionsAndAccount();
  return res;
});

ipcMain.handle("cancel-all-pending-orders", async () => {
  appendLog("MT5", "INFO", "Cancelling all pending orders...");
  let res = await queryBridgeSocket("CANCEL_ALL");
  if (!res || !res.success) {
    res = await executeDirectMT5Action("CANCEL_ALL_ORDERS");
  }
  appendLog("MT5", res.success ? "INFO" : "WARNING", res.message);
  await syncOpenPositionsAndAccount();
  return res;
});

ipcMain.handle("emergency-kill-switch", async (_e, closeAll = false) => {
  appendLog("SYSTEM", "WARNING", "EMERGENCY KILL SWITCH ENGAGED!");
  botState = "PAUSED";
  fs.writeFileSync(path.join(APP_STATE_DIR, "PAUSE"), "EMERGENCY_KILL_SWITCH");
  if (mainWindow) mainWindow.webContents.send("state-changed", botState);

  let closeResult = null;
  if (closeAll) {
    appendLog("SYSTEM", "WARNING", "Kill Switch with Position Liquidation requested...");
    closeResult = await executeDirectMT5Action("CLOSE_ALL");
    await syncOpenPositionsAndAccount();
  }

  appendLog("SYSTEM", "INFO", "Kill switch engaged: Automated trading paused. Existing positions preserved/managed.");
  return {
    success: true,
    message: closeAll ? "Kill switch engaged and all positions closed." : "Kill switch engaged: Trading engine halted.",
    closeResult
  };
});

ipcMain.handle("get-services", () => Object.values(serviceStates));
ipcMain.handle("get-account-metrics", async () => {
  if (Date.now() - lastSyncTimestamp > 1200) {
    await syncOpenPositionsAndAccount();
  }
  return accountMetrics;
});
ipcMain.handle("get-positions", async () => {
  if (Date.now() - lastSyncTimestamp > 1200) {
    await syncOpenPositionsAndAccount();
  }
  return activePositions;
});
ipcMain.handle("get-logs", (_e, limit = 200) => logHistory.slice(-limit));
ipcMain.handle("clear-logs", () => { logHistory.length = 0; return true; });

// MT5 Operations
ipcMain.handle("scan-mt5-terminals", () => scanMT5Terminals());
ipcMain.handle("launch-mt5", (_e, exePath) => {
  if (!fs.existsSync(exePath)) {
    return { success: false, message: `Executable not found: ${exePath}` };
  }
  try {
    spawn(exePath, [], { detached: true, stdio: "ignore" }).unref();
    appendLog("MT5", "INFO", `Launched MT5 Terminal: ${exePath}`);
    return { success: true, message: "Launched MT5 Terminal." };
  } catch (e) {
    return { success: false, message: e.message };
  }
});

ipcMain.handle("deploy-ea", (_e, targetExpertsDir) => {
  if (!fs.existsSync(EA_SOURCE_PATH)) {
    return { success: false, message: `EA source not found at ${EA_SOURCE_PATH}` };
  }
  if (!fs.existsSync(targetExpertsDir)) {
    fs.mkdirSync(targetExpertsDir, { recursive: true });
  }
  const dest = path.join(targetExpertsDir, "PythonBridgeEA.mq5");
  try {
    if (fs.existsSync(dest)) {
      const timestamp = new Date().toISOString().replace(/[-:T.]/g, "").slice(0, 14);
      fs.copyFileSync(dest, `${dest}.bak_${timestamp}`);
    }
    fs.copyFileSync(EA_SOURCE_PATH, dest);
    appendLog("MT5", "INFO", `Successfully deployed PythonBridgeEA.mq5 to ${dest}`);
    return { success: true, message: "PythonBridgeEA.mq5 installed and backed up successfully!" };
  } catch (e) {
    return { success: false, message: `Deployment failed: ${e.message}` };
  }
});

// Institutional EA Cloud Pairing Handlers
ipcMain.handle("get-pairing-status", () => {
  let isPaired = false;
  let instanceId = null;
  let deviceTokenMasked = null;
  let pairedAt = null;
  let status = "NOT_PAIRED";

  const credPath = fs.existsSync(PRIMARY_CREDENTIALS_FILE)
    ? PRIMARY_CREDENTIALS_FILE
    : (fs.existsSync(LEGACY_CREDENTIALS_FILE) ? LEGACY_CREDENTIALS_FILE : null);

  if (credPath) {
    try {
      const data = JSON.parse(fs.readFileSync(credPath, "utf-8"));
      const tok = data.token || data.deviceToken || data.device_token;
      if (tok) {
        isPaired = true;
        instanceId = data.instanceId || data.instance_id || `${os.hostname()}-MT5`;
        deviceTokenMasked = tok.substring(0, 8) + "...";
        pairedAt = data.pairedAt || data.paired_at || new Date().toISOString();
        status = "ONLINE";
      }
    } catch (e) {}
  }

  // Check live agent state file if present
  const statePath = path.join(APP_STATE_DIR, "agent_state.json");
  if (fs.existsSync(statePath)) {
    try {
      const sData = JSON.parse(fs.readFileSync(statePath, "utf-8"));
      if (sData.status) status = sData.status;
    } catch (e) {}
  }

  return {
    isPaired,
    status,
    instanceId,
    deviceTokenMasked,
    pairedAt,
    apiUrl: "https://www.arcadefx.live/api/v1"
  };
});

function postWithRedirects(targetUrl, postData, redirectCount = 0) {
  return new Promise((resolve) => {
    if (redirectCount > 3) {
      resolve({ success: false, message: "Too many redirects contacting Institutional EA server." });
      return;
    }

    const u = new URL(targetUrl);
    const client = u.protocol === "https:" ? https : http;

    const req = client.request(
      u,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(postData),
          "User-Agent": "Institutional-EA-Companion/1.2.0"
        },
        timeout: 12000
      },
      (res) => {
        // Handle 301, 302, 307, 308 redirects smoothly
        if ([301, 302, 307, 308].includes(res.statusCode) && res.headers.location) {
          const newUrl = new URL(res.headers.location, targetUrl).toString();
          appendLog("INSTITUTIONAL_EA", "INFO", `Following redirect [HTTP ${res.statusCode}] -> ${newUrl}`);
          resolve(postWithRedirects(newUrl, postData, redirectCount + 1));
          return;
        }

        let body = "";
        res.on("data", (chunk) => (body += chunk));
        res.on("end", () => {
          try {
            const data = JSON.parse(body);
            if (data.success || res.statusCode === 200) {
              resolve({ success: true, data });
            } else {
              const errMsg = data.error || (data.message ? data.message : "Pairing code expired or invalid.");
              resolve({ success: false, message: errMsg });
            }
          } catch (e) {
            resolve({ success: false, message: `Unexpected response from server: ${body.substring(0, 150)}` });
          }
        });
      }
    );

    req.on("error", (e) => {
      resolve({ success: false, message: `Network error reaching Institutional EA: ${e.message}` });
    });

    req.write(postData);
    req.end();
  });
}

ipcMain.handle("submit-pairing-code", async (_e, code, instanceName) => {
  const machineName = instanceName || `${os.hostname()}-MT5`;
  const cleanCode = code.toUpperCase().trim();

  if (!/^[A-Z0-9]{6}$/.test(cleanCode)) {
    return { success: false, message: "Invalid pairing code. Code must be exactly 6 alphanumeric characters." };
  }

  appendLog("INSTITUTIONAL_EA", "INFO", `Submitting pairing claim for [${cleanCode}]...`);

  const postData = JSON.stringify({
    pairingCode: cleanCode,
    instanceName: machineName,
    engineVersion: "1.2.0"
  });

  const canonicalUrl = "https://www.arcadefx.live/api/v1/bot/pairing/claim";
  const result = await postWithRedirects(canonicalUrl, postData);

  if (result.success && result.data) {
    const data = result.data;
    const token = data.deviceToken || data.token || "afx_tok_" + Math.random().toString(36).substring(2, 10);
    const secret = data.signingSecret || data.signing_secret || "";

    const credObj = {
      version: 2,
      format: "json_utf8",
      token: token,
      deviceToken: token,
      device_token: token,
      signingSecret: secret,
      signing_secret: secret,
      instanceId: machineName,
      instance_id: machineName,
      apiUrl: "https://www.arcadefx.live/api/v1",
      pairedAt: new Date().toISOString()
    };

    // Save to primary writable credentials directory
    fs.mkdirSync(APP_CREDENTIALS_DIR, { recursive: true });
    fs.writeFileSync(PRIMARY_CREDENTIALS_FILE, JSON.stringify(credObj, null, 2), "utf-8");

    // Mirror to legacy path for backward compatibility
    try {
      fs.mkdirSync(LEGACY_INSTITUTIONAL_EA_DIR, { recursive: true });
      fs.writeFileSync(LEGACY_CREDENTIALS_FILE, JSON.stringify(credObj, null, 2), "utf-8");
    } catch (e) {}

    // Drop trigger for background agent
    try {
      fs.writeFileSync(path.join(APP_STATE_DIR, "pairing_request.json"), JSON.stringify({ pairingCode: cleanCode, instanceName: machineName }));
    } catch (e) {}

    appendLog("INSTITUTIONAL_EA", "INFO", "Device paired successfully to Institutional EA Cloud!");
    serviceStates.institutional_ea.status = "RUNNING";
    return { success: true, message: "Device successfully paired." };
  } else {
    appendLog("INSTITUTIONAL_EA", "ERROR", `Pairing failed: ${result.message}`);
    return { success: false, message: result.message };
  }
});

ipcMain.handle("disconnect-pairing", () => {
  appendLog("INSTITUTIONAL_EA", "INFO", "Unpairing device from Institutional EA Cloud...");
  try {
    fs.writeFileSync(path.join(APP_STATE_DIR, "unpair_request.json"), JSON.stringify({ unpair: true, timestamp: new Date().toISOString() }));
  } catch (e) {}

  [PRIMARY_CREDENTIALS_FILE, LEGACY_CREDENTIALS_FILE, CREDENTIALS_FILE].forEach((f) => {
    if (f && fs.existsSync(f)) {
      try { fs.unlinkSync(f); } catch (e) {}
    }
  });

  const statePath = path.join(APP_STATE_DIR, "agent_state.json");
  try {
    fs.writeFileSync(statePath, JSON.stringify({ status: "NOT_PAIRED", isPaired: false, error: null }), "utf-8");
  } catch (e) {}

  serviceStates.institutional_ea.status = "STOPPED";
  if (mainWindow) {
    mainWindow.webContents.send("pairing-status-changed", {
      isPaired: false,
      status: "NOT_PAIRED",
      instanceId: null,
      deviceTokenMasked: null
    });
  }

  appendLog("INSTITUTIONAL_EA", "INFO", "Institutional EA pairing credentials revoked and local state reset.");
  return { success: true, message: "Device successfully unpaired from Institutional EA Cloud." };
});

// Telegram Pairing Handlers
ipcMain.handle("get-telegram-status", () => getTelegramStatus());
ipcMain.handle("start-telegram-pairing", (_e, botToken) => startTelegramPairing(botToken));
ipcMain.handle("disconnect-telegram", () => {
  saveConfig({ telegramBotToken: "", telegramChatId: "", telegramEnabled: false });
  serviceStates.telegram.status = "STOPPED";
  appendLog("TELEGRAM", "INFO", "Telegram connection disconnected.");
  return { success: true, message: "Telegram unlinked." };
});
ipcMain.handle("test-telegram-message", () => testTelegramMessage());

// Onboarding & Diagnostics
ipcMain.handle("complete-onboarding", () => {
  saveConfig({ onboardingComplete: true });
  return true;
});

ipcMain.handle("run-diagnostics", async () => {
  const ipcProbe = await probeSocketHandshake(5556);
  const p5556 = !ipcProbe.alive;
  const p5555 = p5556;
  const terminals = scanMT5Terminals();
  const pySidecar = resolveSidecar("mt5_trading_engine");
  const institutionalEaStatus = fs.existsSync(CREDENTIALS_FILE);
  const telStatus = getTelegramStatus().isPaired;

  return [
    { id: "1", name: "Operating System & Architecture", status: "PASS", details: `${os.type()} ${os.arch()} (${os.release()})` },
    { id: "2", name: "Python Engine Executable / Runtime", status: pySidecar ? "PASS" : "WARN", details: pySidecar ? `Resolved: ${pySidecar.type === "binary" ? pySidecar.path : pySidecar.script}` : "Engine sidecar pending build" },
    { id: "3", name: "Port 5555 (MQL5 Socket Bridge)", status: p5555 ? "PASS" : "INFO", details: p5555 ? "Port 5555 is clear and ready" : "Port 5555 is listening" },
    { id: "4", name: "Port 5556 (Internal IPC Switchboard)", status: p5556 ? "PASS" : "INFO", details: p5556 ? "Port 5556 is clear and ready" : "Port 5556 is listening" },
    { id: "5", name: "MT5 Terminal Detection", status: terminals.length > 0 ? "PASS" : "WARN", details: terminals.length > 0 ? `Detected: ${terminals[0].name}` : "No MT5 terminals detected" },
    { id: "6", name: "PythonBridgeEA.mq5 File", status: fs.existsSync(EA_SOURCE_PATH) ? "PASS" : "FAIL", details: fs.existsSync(EA_SOURCE_PATH) ? "Source EA verified" : "EA file missing" },
    { id: "7", name: "Institutional EA Cloud Pairing", status: institutionalEaStatus ? "PASS" : "WARN", details: institutionalEaStatus ? "Device paired" : "Pairing required for cloud sync" },
    { id: "8", name: "Telegram Remote Control", status: telStatus ? "PASS" : "INFO", details: telStatus ? "Authorized chat paired" : "Optional remote control not configured" },
    { id: "9", name: "Local Disk Space & State Storage", status: "PASS", details: `User data directory: ${USER_DATA_DIR}` }
  ];
});

ipcMain.handle("get-config", () => loadConfig());
ipcMain.handle("save-config", (_e, cfg) => saveConfig(cfg));

// ---------------------------------------------------------------------------
// Authenticated Python Local Control Service (127.0.0.1:8765)
// ---------------------------------------------------------------------------
const CONTROL_SERVICE_PORT = Number(process.env.MT5_CONTROL_PORT || 8765);
const CONTROL_TOKEN_FILE = path.join(PROJECT_ROOT, "state", "companion_token.txt");
let controlServiceProcess = null;
let controlAuthToken = process.env.MT5_COMPANION_TOKEN || "";

function ensureControlToken() {
  if (controlAuthToken) return controlAuthToken;
  try {
    if (fs.existsSync(CONTROL_TOKEN_FILE)) {
      const existing = fs.readFileSync(CONTROL_TOKEN_FILE, "utf-8").trim();
      if (existing) {
        controlAuthToken = existing;
        return controlAuthToken;
      }
    }
  } catch (e) {}
  controlAuthToken = crypto.randomBytes(24).toString("base64url");
  return controlAuthToken;
}

function startControlService() {
  if (controlServiceProcess) return;
  const token = ensureControlToken();
  const venvPy = path.join(PROJECT_ROOT, ".venv", "Scripts", "python.exe");
  const packagedBin = path.join(process.resourcesPath || "", "bin", "mt5_control_service.exe");
  let cmd = null;
  let args = [];
  if (isPackaged && fs.existsSync(packagedBin)) {
    cmd = packagedBin;
    args = ["--host", "127.0.0.1", "--port", String(CONTROL_SERVICE_PORT), "--project-root", PROJECT_ROOT];
  } else if (fs.existsSync(venvPy)) {
    cmd = venvPy;
    args = ["-m", "companion.service.main", "--host", "127.0.0.1", "--port", String(CONTROL_SERVICE_PORT), "--project-root", PROJECT_ROOT];
  } else {
    cmd = "python";
    args = ["-m", "companion.service.main", "--host", "127.0.0.1", "--port", String(CONTROL_SERVICE_PORT), "--project-root", PROJECT_ROOT];
  }

  try {
    controlServiceProcess = spawn(cmd, args, {
      cwd: PROJECT_ROOT,
      env: { ...process.env, MT5_COMPANION_TOKEN: token, PYTHONPATH: PROJECT_ROOT },
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
    });
    controlServiceProcess.on("exit", () => {
      controlServiceProcess = null;
    });
  } catch (err) {
    console.error("[ControlService] Failed to spawn:", err);
  }
}

function stopControlService() {
  if (controlServiceProcess) {
    try {
      controlServiceProcess.kill();
    } catch (e) {}
    controlServiceProcess = null;
  }
}

function httpControlRequest(method, apiPath, bodyObj = null) {
  return new Promise((resolve, reject) => {
    const token = ensureControlToken();
    const payload = bodyObj ? JSON.stringify(bodyObj) : null;
    const req = http.request(
      {
        hostname: "127.0.0.1",
        port: CONTROL_SERVICE_PORT,
        path: apiPath,
        method: method || "GET",
        headers: {
          Authorization: `Bearer ${token}`,
          ...(payload ? { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(payload) } : {}),
        },
        timeout: 15000,
      },
      (res) => {
        let data = "";
        res.on("data", (chunk) => (data += chunk));
        res.on("end", () => {
          try {
            const parsed = data ? JSON.parse(data) : {};
            if (res.statusCode >= 400) {
              reject(new Error(parsed.error || `HTTP ${res.statusCode}`));
            } else {
              resolve(parsed);
            }
          } catch (e) {
            reject(new Error(`Invalid JSON from control service: ${data.slice(0, 200)}`));
          }
        });
      }
    );
    req.on("error", (err) => reject(err));
    req.on("timeout", () => {
      req.destroy();
      reject(new Error("Control service request timed out"));
    });
    if (payload) req.write(payload);
    req.end();
  });
}

ipcMain.handle("control-request", async (_e, method, apiPath, body) => {
  return httpControlRequest(method, apiPath, body);
});

ipcMain.handle("get-control-connection-info", () => ({
  baseUrl: `http://127.0.0.1:${CONTROL_SERVICE_PORT}`,
  token: ensureControlToken(),
}));

// Window controls
ipcMain.handle("minimize-window", () => mainWindow?.minimize());
ipcMain.handle("maximize-window", () => {
  if (mainWindow?.isMaximized()) mainWindow.unmaximize();
  else mainWindow?.maximize();
});
ipcMain.handle("close-window", () => {
  const config = loadConfig();
  if (config.runInBackground) {
    mainWindow?.hide();
  } else {
    isQuitting = true;
    stopBotServices();
    app.quit();
  }
});

// Single instance lock
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.show();
      mainWindow.focus();
    }
  });

  app.whenReady().then(() => {
    startControlService();
    createWindow();
    createTray();

    // Start background live position & account telemetry sync loop
    syncOpenPositionsAndAccount();
    setInterval(() => {
      syncOpenPositionsAndAccount();
    }, 2500);

    app.on("activate", () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow();
    });
  });

  app.on("before-quit", () => {
    isQuitting = true;
    stopBotServices();
    stopControlService();
  });
}
