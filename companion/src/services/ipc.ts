import {
  BotState,
  ServiceInfo,
  AccountMetrics,
  ActivePosition,
  PendingOrder,
  LogMessage,
  MT5TerminalInfo,
  PairingStatus,
  TelegramStatus,
  DiagnosticResult,
  CompanionConfig,
  ControlStatusPayload,
  ControlErrorEvent,
  AllowlistedOpInfo,
  OperationAuditRecord,
  ConfigVersionRecord,
  ControlLogEntry,
  TradeHistoryRecord,
  RiskDecisionRecord,
  AuditLogRecord,
  BTCUSDSampleStatus
} from "../types";

declare global {
  interface Window {
    electronAPI?: {
      getBotState: () => Promise<BotState>;
      startBot: () => Promise<{ success: boolean; message: string }>;
      stopBot: () => Promise<{ success: boolean; message: string }>;
      pauseTrading: () => Promise<{ success: boolean; message: string }>;
      resumeTrading: () => Promise<{ success: boolean; message: string }>;
      restartServices: () => Promise<{ success: boolean; message: string }>;
      closeAllPositions: (confirm: boolean) => Promise<{ success: boolean; message: string; closedCount?: number; failedCount?: number }>;
      modifyPosition: (ticket: number, sl: number, tp: number) => Promise<{ success: boolean; message: string }>;
      closePosition: (ticket: number, volume?: number) => Promise<{ success: boolean; message: string }>;
      setBreakEven: (ticket: number) => Promise<{ success: boolean; message: string }>;
      setTrailingStop: (ticket: number, points?: number) => Promise<{ success: boolean; message: string }>;
      getPendingOrders: () => Promise<PendingOrder[]>;
      placePendingOrder: (order: { symbol: string; orderType: string; volume: number; price: number; sl?: number; tp?: number }) => Promise<{ success: boolean; message: string }>;
      modifyPendingOrder: (ticket: number, price?: number, sl?: number, tp?: number) => Promise<{ success: boolean; message: string }>;
      cancelPendingOrder: (ticket: number) => Promise<{ success: boolean; message: string }>;
      cancelAllPendingOrders: () => Promise<{ success: boolean; message: string }>;
      emergencyKillSwitch: (closeAll?: boolean) => Promise<{ success: boolean; message: string }>;
      getServices: () => Promise<ServiceInfo[]>;
      getAccountMetrics: () => Promise<AccountMetrics>;
      getPositions: () => Promise<ActivePosition[]>;
      getLogs: (limit?: number) => Promise<LogMessage[]>;
      clearLogs: () => Promise<boolean>;
      onLogReceived: (callback: (log: LogMessage) => void) => () => void;
      onStateChanged: (callback: (state: BotState) => void) => () => void;
      onMetricsChanged: (callback: (metrics: AccountMetrics) => void) => () => void;
      onPositionsChanged: (callback: (positions: ActivePosition[]) => void) => () => void;
      onPendingOrdersChanged: (callback: (orders: PendingOrder[]) => void) => () => void;
      onPairingStatusChanged: (callback: (status: PairingStatus) => void) => () => void;
      scanMT5Terminals: () => Promise<MT5TerminalInfo[]>;
      launchMT5: (executablePath: string) => Promise<{ success: boolean; message: string }>;
      deployEA: (targetExpertsDir: string) => Promise<{ success: boolean; message: string }>;
      getPairingStatus: () => Promise<PairingStatus>;
      submitPairingCode: (code: string, instanceName?: string) => Promise<{ success: boolean; message: string }>;
      disconnectPairing: () => Promise<{ success: boolean; message: string }>;
      getTelegramStatus: () => Promise<TelegramStatus>;
      startTelegramPairing: (botToken?: string) => Promise<{ success: boolean; message: string; chatId?: string; senderName?: string }>;
      disconnectTelegram: () => Promise<{ success: boolean; message: string }>;
      testTelegramMessage: () => Promise<{ success: boolean; message: string }>;
      completeOnboarding: () => Promise<boolean>;
      runDiagnostics: () => Promise<DiagnosticResult[]>;
      getConfig: () => Promise<CompanionConfig>;
      saveConfig: (config: Partial<CompanionConfig>) => Promise<boolean>;
      minimizeWindow: () => void;
      maximizeWindow: () => void;
      closeWindow: () => void;
      controlRequest?: (method: string, apiPath: string, body?: any) => Promise<any>;
      getControlConnectionInfo?: () => Promise<{ baseUrl: string; token: string }>;
    };
    __TAURI__?: any;
  }
}

// Fallback in-memory state for development / browser mode
let mockState: BotState = "STOPPED";
let mockLogs: LogMessage[] = [
  {
    id: "1",
    timestamp: new Date().toISOString(),
    service: "SYSTEM",
    level: "INFO",
    message: "MT5-OO1 Companion Desktop Runtime initialized.",
  },
  {
    id: "2",
    timestamp: new Date().toISOString(),
    service: "BRIDGE",
    level: "INFO",
    message: "Bridge ports pre-flight check ready: Port 5555 (EA) and 5556 (IPC) available.",
  },
  {
    id: "3",
    timestamp: new Date().toISOString(),
    service: "ARCADEFX",
    level: "INFO",
    message: "Ready for device pairing via https://arcadefx.live/api/v1/bot/pairing/claim.",
  }
];

let mockTelegram: TelegramStatus = {
  isPaired: false,
  botTokenMasked: null,
  chatIdMasked: null,
  botUsername: null,
  enabled: false
};

let mockServices: ServiceInfo[] = [
  {
    id: "engine",
    name: "Trading Engine",
    description: "Multi-Timeframe Scalping & Quantitative Engine (mt5_trading_engine)",
    status: "STOPPED",
    pid: null,
    cpu: 0,
    memoryMb: 0,
    uptimeSeconds: 0,
    restarts: 0,
    lastHeartbeat: null,
    lastError: null,
  },
  {
    id: "bridge",
    name: "Bridge Server",
    description: "Persistent dual-port TCP socket IPC on 5555/5556 (mt5_bridge_server)",
    status: "STOPPED",
    pid: null,
    cpu: 0,
    memoryMb: 0,
    uptimeSeconds: 0,
    restarts: 0,
    lastHeartbeat: null,
    lastError: null,
  },
  {
    id: "arcadefx",
    name: "ArcadeFX Cloud Sync",
    description: "Telemetry, heartbeats & signed cloud controls (mt5_bot_agent)",
    status: "STOPPED",
    pid: null,
    cpu: 0,
    memoryMb: 0,
    uptimeSeconds: 0,
    restarts: 0,
    lastHeartbeat: null,
    lastError: null,
  },
  {
    id: "telegram",
    name: "Telegram Dispatcher",
    description: "Instant trade signals & operator remote command switchboard",
    status: "STOPPED",
    pid: null,
    cpu: 0,
    memoryMb: 0,
    uptimeSeconds: 0,
    restarts: 0,
    lastHeartbeat: null,
    lastError: null,
  },
  {
    id: "health",
    name: "Health & Watchdog",
    description: "CUSUM decay guard, process health & socket ping supervisor",
    status: "STOPPED",
    pid: null,
    cpu: 0,
    memoryMb: 0,
    uptimeSeconds: 0,
    restarts: 0,
    lastHeartbeat: null,
    lastError: null,
  },
  {
    id: "logs",
    name: "Log Manager",
    description: "Real-time rolling diagnostics & audit bundle exporter",
    status: "RUNNING",
    pid: 10420,
    cpu: 0.2,
    memoryMb: 42,
    uptimeSeconds: 120,
    restarts: 0,
    lastHeartbeat: new Date().toISOString(),
    lastError: null,
  },
];

export const IPC = {
  isElectron: (): boolean => typeof window !== "undefined" && !!window.electronAPI,

  getBotState: async (): Promise<BotState> => {
    if (window.electronAPI) return window.electronAPI.getBotState();
    return mockState;
  },

  startBot: async (): Promise<{ success: boolean; message: string }> => {
    if (window.electronAPI) return window.electronAPI.startBot();
    mockState = "RUNNING";
    mockServices = mockServices.map((s) => ({ ...s, status: "RUNNING", uptimeSeconds: 1 }));
    return { success: true, message: "Engine and Bridge started (Browser Mock Mode)." };
  },

  stopBot: async (): Promise<{ success: boolean; message: string }> => {
    if (window.electronAPI) return window.electronAPI.stopBot();
    mockState = "STOPPED";
    mockServices = mockServices.map((s) =>
      s.id === "logs" ? s : { ...s, status: "STOPPED", pid: null, uptimeSeconds: 0 }
    );
    return { success: true, message: "Services stopped cleanly." };
  },

  pauseTrading: async (): Promise<{ success: boolean; message: string }> => {
    if (window.electronAPI) return window.electronAPI.pauseTrading();
    mockState = "PAUSED";
    return { success: true, message: "Trading paused. Emergency PAUSE flag set." };
  },

  resumeTrading: async (): Promise<{ success: boolean; message: string }> => {
    if (window.electronAPI) return window.electronAPI.resumeTrading();
    mockState = "RUNNING";
    return { success: true, message: "Trading resumed." };
  },

  restartServices: async (): Promise<{ success: boolean; message: string }> => {
    if (window.electronAPI) return window.electronAPI.restartServices();
    return { success: true, message: "Services restarted." };
  },

  closeAllPositions: async (confirm: boolean): Promise<{ success: boolean; message: string; closedCount?: number; failedCount?: number }> => {
    if (window.electronAPI) return window.electronAPI.closeAllPositions(confirm);
    return { success: true, message: "Market orders dispatched to liquidate positions." };
  },

  modifyPosition: async (ticket: number, sl: number, tp: number): Promise<{ success: boolean; message: string }> => {
    if (window.electronAPI) return window.electronAPI.modifyPosition(ticket, sl, tp);
    return { success: true, message: `Position #${ticket} modified: SL=${sl}, TP=${tp}` };
  },

  closePosition: async (ticket: number, volume?: number): Promise<{ success: boolean; message: string }> => {
    if (window.electronAPI) return window.electronAPI.closePosition(ticket, volume);
    return { success: true, message: `Position #${ticket} closed.` };
  },

  setBreakEven: async (ticket: number): Promise<{ success: boolean; message: string }> => {
    if (window.electronAPI) return window.electronAPI.setBreakEven(ticket);
    return { success: true, message: `Stop Loss moved to Break-Even for #${ticket}.` };
  },

  setTrailingStop: async (ticket: number, points?: number): Promise<{ success: boolean; message: string }> => {
    if (window.electronAPI) return window.electronAPI.setTrailingStop(ticket, points);
    return { success: true, message: `Trailing stop applied to #${ticket}.` };
  },

  getPendingOrders: async (): Promise<PendingOrder[]> => {
    if (window.electronAPI) return window.electronAPI.getPendingOrders();
    return [];
  },

  placePendingOrder: async (order: { symbol: string; orderType: string; volume: number; price: number; sl?: number; tp?: number }): Promise<{ success: boolean; message: string }> => {
    if (window.electronAPI) return window.electronAPI.placePendingOrder(order);
    return { success: true, message: `Pending order placed on ${order.symbol}.` };
  },

  modifyPendingOrder: async (ticket: number, price?: number, sl?: number, tp?: number): Promise<{ success: boolean; message: string }> => {
    if (window.electronAPI) return window.electronAPI.modifyPendingOrder(ticket, price, sl, tp);
    return { success: true, message: `Pending order #${ticket} modified.` };
  },

  cancelPendingOrder: async (ticket: number): Promise<{ success: boolean; message: string }> => {
    if (window.electronAPI) return window.electronAPI.cancelPendingOrder(ticket);
    return { success: true, message: `Pending order #${ticket} cancelled.` };
  },

  cancelAllPendingOrders: async (): Promise<{ success: boolean; message: string }> => {
    if (window.electronAPI) return window.electronAPI.cancelAllPendingOrders();
    return { success: true, message: "All pending orders cancelled." };
  },

  emergencyKillSwitch: async (closeAll?: boolean): Promise<{ success: boolean; message: string }> => {
    if (window.electronAPI) return window.electronAPI.emergencyKillSwitch(closeAll);
    return { success: true, message: "Emergency kill switch activated." };
  },

  getServices: async (): Promise<ServiceInfo[]> => {
    if (window.electronAPI) return window.electronAPI.getServices();
    return mockServices;
  },

  getAccountMetrics: async (): Promise<AccountMetrics> => {
    if (window.electronAPI) return window.electronAPI.getAccountMetrics();
    return {
      accountNumber: 50198422,
      broker: "MetaQuotes-Demo",
      balance: 50000.0,
      equity: 50420.5,
      profit: 420.5,
      dailyPnl: 420.5,
      margin: 125.0,
      freeMargin: 50295.5,
      marginLevel: 40336.4,
      currency: "USD",
      leverage: 100,
      tradeMode: "DEMO",
      profile: "DEMO",
      positionsCount: 1,
    };
  },

  getPositions: async (): Promise<ActivePosition[]> => {
    if (window.electronAPI) return window.electronAPI.getPositions();
    return [];
  },

  getLogs: async (limit = 200): Promise<LogMessage[]> => {
    if (window.electronAPI) return window.electronAPI.getLogs(limit);
    return mockLogs.slice(-limit);
  },

  clearLogs: async (): Promise<boolean> => {
    if (window.electronAPI) return window.electronAPI.clearLogs();
    mockLogs = [];
    return true;
  },

  scanMT5Terminals: async (): Promise<MT5TerminalInfo[]> => {
    if (window.electronAPI) return window.electronAPI.scanMT5Terminals();
    return [
      {
        id: "meta-trader-5",
        name: "MetaTrader 5 Default Terminal",
        executablePath: "C:\\Program Files\\MetaTrader 5\\terminal64.exe",
        dataFolder: "C:\\Users\\Operator\\AppData\\Roaming\\MetaQuotes\\Terminal\\D0E8209F77C8F",
        expertsFolder: "C:\\Users\\Operator\\AppData\\Roaming\\MetaQuotes\\Terminal\\D0E8209F77C8F\\MQL5\\Experts",
        isRunning: true,
        pid: 12890,
        eaInstalled: true,
        eaVersion: "3.10",
      },
    ];
  },

  launchMT5: async (path: string): Promise<{ success: boolean; message: string }> => {
    if (window.electronAPI) return window.electronAPI.launchMT5(path);
    return { success: true, message: `Mock launched MT5: ${path}` };
  },

  deployEA: async (targetExpertsDir: string): Promise<{ success: boolean; message: string }> => {
    if (window.electronAPI) return window.electronAPI.deployEA(targetExpertsDir);
    return { success: true, message: "PythonBridgeEA.mq5 installed with backup." };
  },

  getPairingStatus: async (): Promise<PairingStatus> => {
    if (window.electronAPI) return window.electronAPI.getPairingStatus();
    return {
      isPaired: false,
      instanceId: null,
      deviceTokenMasked: null,
      pairedAt: null,
      apiUrl: "https://arcadefx.live/api/v1",
    };
  },

  submitPairingCode: async (code: string, instanceName?: string): Promise<{ success: boolean; message: string }> => {
    if (window.electronAPI) return window.electronAPI.submitPairingCode(code, instanceName);
    return { success: true, message: "Device paired in browser simulation." };
  },

  disconnectPairing: async (): Promise<{ success: boolean; message: string }> => {
    if (window.electronAPI) return window.electronAPI.disconnectPairing();
    return { success: true, message: "Pairing cleared." };
  },

  getTelegramStatus: async (): Promise<TelegramStatus> => {
    if (window.electronAPI) return window.electronAPI.getTelegramStatus();
    return mockTelegram;
  },

  startTelegramPairing: async (botToken?: string): Promise<{ success: boolean; message: string; chatId?: string; senderName?: string }> => {
    if (window.electronAPI) return window.electronAPI.startTelegramPairing(botToken);
    mockTelegram = {
      isPaired: true,
      botTokenMasked: "782914***ABCD",
      chatIdMasked: "981***22",
      botUsername: "@MyMT5TradingBot",
      enabled: true
    };
    return { success: true, message: "Telegram paired in simulation." };
  },

  disconnectTelegram: async (): Promise<{ success: boolean; message: string }> => {
    if (window.electronAPI) return window.electronAPI.disconnectTelegram();
    mockTelegram = { isPaired: false, botTokenMasked: null, chatIdMasked: null, botUsername: null, enabled: false };
    return { success: true, message: "Telegram disconnected." };
  },

  testTelegramMessage: async (): Promise<{ success: boolean; message: string }> => {
    if (window.electronAPI) return window.electronAPI.testTelegramMessage();
    return { success: true, message: "Test alert dispatched." };
  },

  completeOnboarding: async (): Promise<boolean> => {
    if (window.electronAPI) return window.electronAPI.completeOnboarding();
    return true;
  },

  runDiagnostics: async (): Promise<DiagnosticResult[]> => {
    if (window.electronAPI) return window.electronAPI.runDiagnostics();
    return [
      { id: "1", name: "Operating System & Architecture", status: "PASS", details: "Windows 11 x64 (Build 22631)" },
      { id: "2", name: "Python Engine Executable / Runtime", status: "PASS", details: "Engine sidecar resolved" },
      { id: "3", name: "Port 5555 (MQL5 Socket Bridge)", status: "PASS", details: "Port 5555 is ready" },
      { id: "4", name: "Port 5556 (Internal IPC Switchboard)", status: "PASS", details: "Port 5556 is ready" },
      { id: "5", name: "MT5 Terminal Detection", status: "PASS", details: "Found: MetaTrader 5" },
      { id: "6", name: "PythonBridgeEA.mq5 File", status: "PASS", details: "PythonBridgeEA.mq5 verified" },
      { id: "7", name: "ArcadeFX.live Cloud Pairing", status: "PASS", details: "Cloud sync primed" },
      { id: "8", name: "Telegram Remote Control", status: "PASS", details: "Notification channel verified" },
      { id: "9", name: "Local Disk Space & State Storage", status: "PASS", details: "> 25 GB free" },
    ];
  },

  getConfig: async (): Promise<CompanionConfig> => {
    if (window.electronAPI) return window.electronAPI.getConfig();
    return {
      apiUrl: "https://arcadefx.live/api/v1",
      tradingMode: "CONTINUOUS_SCALPING",
      riskPerTradePct: 1.0,
      maxDailyLossPct: 0.0,
      bridgeHost: "127.0.0.1",
      bridgePort: 5555,
      ipcPort: 5556,
      allowedSymbols: ["XAUUSD", "BTCUSD"],
      autoStartOnBoot: false,
      minimizeToTray: true,
      runInBackground: true,
      allowRealAccount: false,
      onboardingComplete: false,
    };
  },

  saveConfig: async (cfg: Partial<CompanionConfig>): Promise<boolean> => {
    if (window.electronAPI) return window.electronAPI.saveConfig(cfg);
    return true;
  },

  minimizeWindow: (): void => {
    if (window.electronAPI) window.electronAPI.minimizeWindow();
  },
  maximizeWindow: (): void => {
    if (window.electronAPI) window.electronAPI.maximizeWindow();
  },
  closeWindow: (): void => {
    if (window.electronAPI) window.electronAPI.closeWindow();
  },

  onLogReceived: (callback: (log: LogMessage) => void): (() => void) => {
    if (window.electronAPI) return window.electronAPI.onLogReceived(callback);
    return () => {};
  },
  onStateChanged: (callback: (state: BotState) => void): (() => void) => {
    if (window.electronAPI) return window.electronAPI.onStateChanged(callback);
    return () => {};
  },
  onMetricsChanged: (callback: (metrics: AccountMetrics) => void): (() => void) => {
    if (window.electronAPI) return window.electronAPI.onMetricsChanged(callback);
    return () => {};
  },
  onPositionsChanged: (callback: (positions: ActivePosition[]) => void): (() => void) => {
    if (window.electronAPI && window.electronAPI.onPositionsChanged) return window.electronAPI.onPositionsChanged(callback);
    return () => {};
  },
  onPendingOrdersChanged: (callback: (orders: PendingOrder[]) => void): (() => void) => {
    if (window.electronAPI && window.electronAPI.onPendingOrdersChanged) return window.electronAPI.onPendingOrdersChanged(callback);
    return () => {};
  },
  onPairingStatusChanged: (callback: (status: PairingStatus) => void): (() => void) => {
    if (window.electronAPI && window.electronAPI.onPairingStatusChanged) return window.electronAPI.onPairingStatusChanged(callback);
    return () => {};
  },
};

async function callControl<T = any>(method: "GET" | "POST", apiPath: string, body?: any): Promise<T> {
  if (window.electronAPI?.controlRequest) {
    return window.electronAPI.controlRequest(method, apiPath, body);
  }
  const resp = await fetch(`http://127.0.0.1:8765${apiPath}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) {
    const errText = await resp.text();
    throw new Error(errText || `HTTP ${resp.status}`);
  }
  return resp.json();
}

export const controlClient = {
  getStatus: () => callControl<ControlStatusPayload>("GET", "/api/status"),
  getEngineStatus: () => callControl<ControlStatusPayload["engine"]>("GET", "/api/engine/status"),
  getHealth: () => callControl<ControlStatusPayload["health"]>("GET", "/api/health"),

  // Engine Lifecycle
  startEngine: (dryRun?: boolean) => callControl<{ success: boolean; message: string; state: string }>("POST", "/api/engine/start", dryRun !== undefined ? { dry_run: dryRun } : {}),
  stopEngine: () => callControl<{ success: boolean; message: string; state: string }>("POST", "/api/engine/stop", {}),
  restartEngine: () => callControl<{ success: boolean; message: string; state: string }>("POST", "/api/engine/restart", {}),
  pauseEntries: () => callControl<{ success: boolean; message: string; state: string }>("POST", "/api/engine/pause", {}),
  resumeEntries: () => callControl<{ success: boolean; message: string; state: string }>("POST", "/api/engine/resume", {}),
  emergencyStop: (closeBotPositions = false, confirmed = false) =>
    callControl<{ success: boolean; message: string; state: string; closed_count: number }>("POST", "/api/engine/emergency-stop", {
      close_bot_positions: closeBotPositions,
      confirmed,
    }),
  clearEmergencyStop: (confirmed = false) =>
    callControl<{ success: boolean; message: string; state?: string }>("POST", "/api/engine/clear-emergency-stop", { confirmed }),

  // MT5 Connection & Sync
  detectMT5: () => callControl<{ installed_paths: string[]; running: boolean }>("GET", "/api/mt5/detect"),
  connectMT5: () => callControl<{ success: boolean; snapshot: ControlStatusPayload["mt5"] }>("POST", "/api/mt5/connect", {}),
  syncMT5: (symbols?: string[]) => callControl<{ success: boolean; snapshot: ControlStatusPayload["mt5"] }>("POST", "/api/mt5/sync", { symbols }),

  // Trade & Order Controls
  modifyPosition: (ticket: number, sl: number, tp: number) =>
    callControl<{ success: boolean; message: string }>("POST", "/api/trades/modify", { ticket, sl, tp }),
  closePosition: (ticket: number, confirmed: boolean) =>
    callControl<{ success: boolean; message: string }>("POST", "/api/trades/close", { ticket, confirmed }),
  closeAllBotPositions: (confirmed: boolean) =>
    callControl<{ success: boolean; message: string; closed_count?: number }>("POST", "/api/trades/close-all-bot", { confirmed }),
  cancelPendingOrder: (ticket: number, confirmed: boolean) =>
    callControl<{ success: boolean; message: string }>("POST", "/api/orders/cancel", { ticket, confirmed }),

  // Configuration & Versioning
  getConfig: () => callControl<{ operating_mode: string; settings: Record<string, any>; risk: Record<string, any>; strategy: Record<string, any>; instruments: Record<string, any>; live_trading_locked: boolean }>("GET", "/api/config"),
  getConfigHistory: () => callControl<{ versions: ConfigVersionRecord[] }>("GET", "/api/config/history"),
  previewConfig: (patch: Record<string, any>) => callControl<{ valid: boolean; errors: string[]; changed_keys: string[]; requires_restart: boolean; proposed: Record<string, any> }>("POST", "/api/config/preview", { patch }),
  applyConfig: (patch: Record<string, any>, changeSummary = "Updated via Companion Control Centre") =>
    callControl<{ version: number; changed_keys: string[]; requires_restart: boolean; config: Record<string, any> }>("POST", "/api/config/apply", { patch, change_summary: changeSummary }),
  rollbackConfig: (version: number) =>
    callControl<{ version: number; changed_keys: string[]; requires_restart: boolean; config: Record<string, any> }>("POST", "/api/config/rollback", { version }),

  // Operations Centre (Allowlisted PowerShell & Scripts)
  getOperations: () => callControl<{ operations: AllowlistedOpInfo[]; audits: OperationAuditRecord[] }>("GET", "/api/operations"),
  runOperation: (opId: string) => callControl<OperationAuditRecord>("POST", "/api/operations/run", { op_id: opId }),
  cancelOperation: (auditId: string) => callControl<{ success: boolean }>("POST", "/api/operations/cancel", { audit_id: auditId }),

  // Error Centre
  getErrors: (status?: "ACTIVE" | "RESOLVED") => callControl<{ errors: ControlErrorEvent[] }>("GET", status ? `/api/errors?status=${status}` : "/api/errors"),
  resolveError: (errorId: number, note: string) => callControl<{ success: boolean }>("POST", "/api/errors/resolve", { error_id: errorId, note }),

  // Logs, History, Risk & Audit
  getLogs: (params?: { limit?: number; severity?: string; component?: string; instrument?: string }) => {
    const qs = new URLSearchParams();
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.severity) qs.set("severity", params.severity);
    if (params?.component) qs.set("component", params.component);
    if (params?.instrument) qs.set("instrument", params.instrument);
    const q = qs.toString();
    return callControl<{ logs: ControlLogEntry[] }>("GET", q ? `/api/logs?${q}` : "/api/logs");
  },
  clearLogs: () => callControl<{ success: boolean }>("POST", "/api/logs/clear", {}),
  getTradeHistory: () => callControl<{ trades: TradeHistoryRecord[] }>("GET", "/api/trades/history"),
  getRiskDecisions: () => callControl<{ decisions: RiskDecisionRecord[]; risk_state: Record<string, any> }>("GET", "/api/risk/decisions"),
  getAudit: () => callControl<{ audits: AuditLogRecord[]; connections: Array<Record<string, any>> }>("GET", "/api/audit"),

  // BTCUSD DEMO Sample Trading & Telegram
  getBtcSampleStatus: () => callControl<BTCUSDSampleStatus>("GET", "/api/btcusd/status"),
  enableBtcSample: () => callControl<{ success: boolean; message: string; status: BTCUSDSampleStatus }>("POST", "/api/btcusd/enable", {}),
  disableBtcSample: () => callControl<{ success: boolean; message: string; status: BTCUSDSampleStatus }>("POST", "/api/btcusd/disable", {}),
  startBtcSample: () => callControl<{ success: boolean; message: string; status: BTCUSDSampleStatus }>("POST", "/api/btcusd/start", {}),
  stopBtcSample: () => callControl<{ success: boolean; message: string; status: BTCUSDSampleStatus }>("POST", "/api/btcusd/stop", {}),
  pauseBtcSample: () => callControl<{ success: boolean; message: string; status: BTCUSDSampleStatus }>("POST", "/api/btcusd/pause", {}),
  resumeBtcSample: () => callControl<{ success: boolean; message: string; status: BTCUSDSampleStatus }>("POST", "/api/btcusd/resume", {}),
  placeBtcManualTestOrder: (direction: "BUY" | "SELL") =>
    callControl<{ success: boolean; message: string; trade?: Record<string, any> }>("POST", "/api/btcusd/manual-test-order", { direction }),
  testTelegram: (sendMessage = true) =>
    callControl<{ success: boolean; message: string }>("POST", "/api/telegram/test", { send_message: sendMessage }),
};
