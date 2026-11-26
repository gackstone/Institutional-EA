const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electronAPI", {
  getBotState: () => ipcRenderer.invoke("get-bot-state"),
  startBot: () => ipcRenderer.invoke("start-bot"),
  stopBot: () => ipcRenderer.invoke("stop-bot"),
  pauseTrading: () => ipcRenderer.invoke("pause-trading"),
  resumeTrading: () => ipcRenderer.invoke("resume-trading"),
  restartServices: () => ipcRenderer.invoke("restart-services"),
  closeAllPositions: (confirm) => ipcRenderer.invoke("close-all-positions", confirm),
  getServices: () => ipcRenderer.invoke("get-services"),
  getAccountMetrics: () => ipcRenderer.invoke("get-account-metrics"),
  getPositions: () => ipcRenderer.invoke("get-positions"),
  getLogs: (limit) => ipcRenderer.invoke("get-logs", limit),
  clearLogs: () => ipcRenderer.invoke("clear-logs"),
  scanMT5Terminals: () => ipcRenderer.invoke("scan-mt5-terminals"),
  launchMT5: (executablePath) => ipcRenderer.invoke("launch-mt5", executablePath),
  deployEA: (targetExpertsDir) => ipcRenderer.invoke("deploy-ea", targetExpertsDir),

  // Trade & Order Management Controls
  modifyPosition: (ticket, sl, tp) => ipcRenderer.invoke("modify-position", ticket, sl, tp),
  closePosition: (ticket, volume) => ipcRenderer.invoke("close-position", ticket, volume),
  setBreakEven: (ticket) => ipcRenderer.invoke("set-breakeven", ticket),
  setTrailingStop: (ticket, points) => ipcRenderer.invoke("set-trailing-stop", ticket, points),
  getPendingOrders: () => ipcRenderer.invoke("get-pending-orders"),
  placePendingOrder: (order) => ipcRenderer.invoke("place-pending-order", order),
  modifyPendingOrder: (ticket, price, sl, tp) => ipcRenderer.invoke("modify-pending-order", ticket, price, sl, tp),
  cancelPendingOrder: (ticket) => ipcRenderer.invoke("cancel-pending-order", ticket),
  cancelAllPendingOrders: () => ipcRenderer.invoke("cancel-all-pending-orders"),
  emergencyKillSwitch: (closeAll) => ipcRenderer.invoke("emergency-kill-switch", closeAll),

  // Institutional EA Cloud Pairing
  getPairingStatus: () => ipcRenderer.invoke("get-pairing-status"),
  submitPairingCode: (code, instanceName) => ipcRenderer.invoke("submit-pairing-code", code, instanceName),
  disconnectPairing: () => ipcRenderer.invoke("disconnect-pairing"),

  // Telegram Control Pairing
  getTelegramStatus: () => ipcRenderer.invoke("get-telegram-status"),
  startTelegramPairing: (botToken) => ipcRenderer.invoke("start-telegram-pairing", botToken),
  disconnectTelegram: () => ipcRenderer.invoke("disconnect-telegram"),
  testTelegramMessage: () => ipcRenderer.invoke("test-telegram-message"),

  // Onboarding & Diagnostics
  completeOnboarding: () => ipcRenderer.invoke("complete-onboarding"),
  runDiagnostics: () => ipcRenderer.invoke("run-diagnostics"),
  getConfig: () => ipcRenderer.invoke("get-config"),
  saveConfig: (cfg) => ipcRenderer.invoke("save-config", cfg),

  // Local Control Service HTTP/SSE Bridge
  controlRequest: (method, apiPath, body) => ipcRenderer.invoke("control-request", method, apiPath, body),
  getControlConnectionInfo: () => ipcRenderer.invoke("get-control-connection-info"),
  getControlServiceStatus: () => ipcRenderer.invoke("get-control-service-status"),
  reconnectControlService: () => ipcRenderer.invoke("reconnect-control-service"),
  onControlServiceStatus: (callback) => {
    const handler = (_event, status) => callback(status);
    ipcRenderer.on("control-service-status", handler);
    return () => ipcRenderer.removeListener("control-service-status", handler);
  },

  // Events from main to renderer
  onLogReceived: (callback) => {
    const handler = (_event, log) => callback(log);
    ipcRenderer.on("log-received", handler);
    return () => ipcRenderer.removeListener("log-received", handler);
  },
  onStateChanged: (callback) => {
    const handler = (_event, state) => callback(state);
    ipcRenderer.on("state-changed", handler);
    return () => ipcRenderer.removeListener("state-changed", handler);
  },
  onMetricsChanged: (callback) => {
    const handler = (_event, metrics) => callback(metrics);
    ipcRenderer.on("metrics-changed", handler);
    return () => ipcRenderer.removeListener("metrics-changed", handler);
  },
  onPositionsChanged: (callback) => {
    const handler = (_event, positions) => callback(positions);
    ipcRenderer.on("positions-changed", handler);
    return () => ipcRenderer.removeListener("positions-changed", handler);
  },
  onPendingOrdersChanged: (callback) => {
    const handler = (_event, orders) => callback(orders);
    ipcRenderer.on("pending-orders-changed", handler);
    return () => ipcRenderer.removeListener("pending-orders-changed", handler);
  },
  onPairingStatusChanged: (callback) => {
    const handler = (_event, status) => callback(status);
    ipcRenderer.on("pairing-status-changed", handler);
    return () => ipcRenderer.removeListener("pairing-status-changed", handler);
  },

  // Startup Watchdog & Crash Recovery
  notifyAppReady: () => ipcRenderer.invoke("notify-app-ready"),
  reportRendererError: (payload) => ipcRenderer.invoke("report-renderer-error", payload),
  fallbackReload: () => ipcRenderer.invoke("fallback-reload"),
  fallbackResetSettings: () => ipcRenderer.invoke("fallback-reset-settings"),
  fallbackOpenLogs: () => ipcRenderer.invoke("fallback-open-logs"),

  // Cloud Account, Subscription & Device Management (OS-encrypted in main process)
  cloudGetState: () => ipcRenderer.invoke("cloud-get-state"),
  cloudSignInBrowser: () => ipcRenderer.invoke("cloud-sign-in-browser"),
  cloudSignInPassword: (email, password) => ipcRenderer.invoke("cloud-sign-in-password", email, password),
  cloudSignUp: (fullName, email, password) => ipcRenderer.invoke("cloud-sign-up", fullName, email, password),
  cloudSignOut: () => ipcRenderer.invoke("cloud-sign-out"),
  cloudRecoverPassword: (email) => ipcRenderer.invoke("cloud-recover-password", email),
  cloudResendVerification: (email) => ipcRenderer.invoke("cloud-resend-verification", email),
  cloudRefresh: () => ipcRenderer.invoke("cloud-refresh"),
  cloudGetPayments: () => ipcRenderer.invoke("cloud-get-payments"),
  cloudSubmitPayment: (payload) => ipcRenderer.invoke("cloud-submit-payment", payload),
  cloudGetDevices: () => ipcRenderer.invoke("cloud-get-devices"),
  cloudRevokeDevice: (deviceId) => ipcRenderer.invoke("cloud-revoke-device", deviceId),
  cloudOpenExternalPortal: (routePath) => ipcRenderer.invoke("cloud-open-external-portal", routePath),
  onCloudStateChanged: (callback) => {
    const handler = (_event, state) => callback(state);
    ipcRenderer.on("cloud-state-changed", handler);
    return () => ipcRenderer.removeListener("cloud-state-changed", handler);
  },

  // Window control
  minimizeWindow: () => ipcRenderer.invoke("minimize-window"),
  maximizeWindow: () => ipcRenderer.invoke("maximize-window"),
  closeWindow: () => ipcRenderer.invoke("close-window"),
});
