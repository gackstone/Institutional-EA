import type { ControlServiceStatus, ControlStatusPayload, OperatingMode } from "../types";

export type NormalizedEngineState =
  | "STOPPED"
  | "STARTING"
  | "RUNNING"
  | "PAUSED"
  | "EMERGENCY_STOP"
  | "ERROR";

export interface TopBarButtonState {
  enabled: boolean;
  label: string;
  tooltip: string;
  tone: "teal" | "lime" | "amber" | "neutral" | "red" | "quiet";
}

export interface TopBarDerivedState {
  serviceOnline: boolean;
  mt5Connected: boolean;
  mt5Syncing: boolean;
  demoVerified: boolean;
  engineState: NormalizedEngineState;
  engineStateLabel: string;
  engineChipTone: "neutral" | "amber" | "lime" | "red";
  modeShort: string;
  operatingMode: OperatingMode;
  placesDemoOrders: boolean;
  isLiveModeBlocked: boolean;
  connectBtn: TopBarButtonState & { showDisconnect: boolean; disconnectEnabled: boolean; disconnectTooltip: string };
  startBtn: TopBarButtonState;
  pauseResumeBtn: TopBarButtonState & { action: "PAUSE" | "RESUME" };
  stopBtn: TopBarButtonState;
  closeAllBtn: TopBarButtonState;
}

const SHORT_MODE_MAP: Record<string, string> = {
  OBSERVE: "OBS",
  DRY_RUN: "DRY",
  DEMO_SCALPING: "SCALP",
  DEMO_FAST: "FAST",
  DEMO_MANUAL_ASSIST: "ASSIST",
  BTCUSD_DEMO_SAMPLE_MODE: "BTC_DEMO",
};

export function formatShortMode(mode: string | undefined | null): string {
  const key = String(mode || "DRY_RUN").toUpperCase();
  return SHORT_MODE_MAP[key] || key.slice(0, 8);
}

export function isOrderPlacingDemoMode(mode: string | undefined | null): boolean {
  const key = String(mode || "DRY_RUN").toUpperCase();
  return (
    key === "DEMO_SCALPING" ||
    key === "DEMO_FAST" ||
    key === "DEMO_MANUAL_ASSIST" ||
    key === "BTCUSD_DEMO_SAMPLE_MODE"
  );
}

export function normalizeEngineState(
  rawState: string | undefined | null,
  stopFlagActive: boolean,
  pauseFlagActive: boolean
): NormalizedEngineState {
  if (stopFlagActive) return "EMERGENCY_STOP";
  const upper = String(rawState || "STOPPED").toUpperCase();
  if (upper === "EMERGENCY_STOP") return "EMERGENCY_STOP";
  if (upper === "ERROR") return "ERROR";
  if (upper === "STARTING") return "STARTING";
  if (upper === "PAUSED") return "PAUSED";
  if (upper === "RUNNING") return pauseFlagActive ? "PAUSED" : "RUNNING";
  return "STOPPED";
}

export function sanitizeControlError(raw: unknown, fallback = "Action failed"): string {
  if (!raw) return fallback;
  const text =
    typeof raw === "string"
      ? raw
      : raw instanceof Error
      ? raw.message
      : typeof (raw as any)?.message === "string"
      ? (raw as any).message
      : typeof (raw as any)?.error === "string"
      ? (raw as any).error
      : fallback;

  const cleaned = text.replace(/\s+/g, " ").trim();
  if (!cleaned) return fallback;
  if (/ECONNREFUSED|Failed to fetch|NetworkError|fetch failed|503/i.test(cleaned)) {
    return "Control service is offline.";
  }
  if (/Traceback|File "|SyntaxError|TypeError:/i.test(cleaned)) {
    return fallback;
  }
  return cleaned.length > 140 ? `${cleaned.slice(0, 137)}...` : cleaned;
}

export function deriveTopBarControlState(params: {
  status: ControlStatusPayload;
  serviceStatus?: ControlServiceStatus | null;
  feedStatus?: string;
  busyAction: string | null;
  connectingMt5?: boolean;
}): TopBarDerivedState {
  const { status, serviceStatus, feedStatus, busyAction, connectingMt5 = false } = params;

  const serviceOnline =
    serviceStatus != null
      ? serviceStatus.status === "ONLINE"
      : feedStatus !== "DISCONNECTED";

  const mt5Status = String(status.mt5?.connection_status || "DISCONNECTED").toUpperCase();
  const mt5Connected = serviceOnline && mt5Status === "CONNECTED";
  const mt5Syncing = connectingMt5 || mt5Status === "SYNCHRONIZING";

  const acc = status.mt5?.account;
  const hasAccount = Number(acc?.account_number || 0) > 0;
  const demoVerified = hasAccount
    ? Boolean(acc?.demo_verified) && String(acc?.trade_mode || "").toUpperCase() === "DEMO"
    : true;

  const eng = status.engine;
  const stopFlag = Boolean(eng?.stop_flag_active ?? eng?.stop_flag_present ?? false);
  const pauseFlag = Boolean(eng?.pause_flag_active ?? eng?.pause_flag_present ?? false);
  const engineState = normalizeEngineState(eng?.engine_state ?? eng?.state, stopFlag, pauseFlag);
  const operatingMode = (eng?.operating_mode || "DRY_RUN") as OperatingMode;
  const upperMode = String(operatingMode).toUpperCase();
  const isLiveModeBlocked = upperMode === "LIVE" || upperMode === "REAL";
  const placesDemoOrders = isOrderPlacingDemoMode(operatingMode) && !eng?.dry_run;
  const busy = busyAction !== null;

  const engineStateLabel =
    engineState === "RUNNING"
      ? "Running"
      : engineState === "PAUSED"
      ? "Paused"
      : engineState === "STARTING"
      ? "Starting"
      : engineState === "EMERGENCY_STOP"
      ? "E-Stop"
      : engineState === "ERROR"
      ? "Error"
      : "Stopped";

  const engineChipTone: TopBarDerivedState["engineChipTone"] =
    engineState === "RUNNING"
      ? "lime"
      : engineState === "PAUSED" || engineState === "STARTING"
      ? "amber"
      : engineState === "ERROR" || engineState === "EMERGENCY_STOP"
      ? "red"
      : "neutral";

  const engineActive =
    engineState === "RUNNING" || engineState === "PAUSED" || engineState === "STARTING";

  // 1. Connect MT5 button
  const connectBtn = {
    enabled: serviceOnline && !busy && !mt5Syncing && !mt5Connected,
    label: mt5Syncing ? "Connecting..." : mt5Connected ? "Connected" : "Connect MT5",
    tooltip: !serviceOnline
      ? "Control service is offline"
      : mt5Connected
      ? "Connected to MT5 DEMO terminal"
      : mt5Syncing
      ? "Connecting to MT5 terminal..."
      : "Connect Control Service to MetaTrader 5 (DEMO only)",
    tone: (mt5Connected ? "quiet" : "teal") as "quiet" | "teal",
    showDisconnect: mt5Connected,
    disconnectEnabled: serviceOnline && !busy && !engineActive,
    disconnectTooltip: engineActive
      ? "Stop the engine before disconnecting MT5"
      : "Disconnect from MT5 terminal",
  };

  // 2. Start button
  let startDisabledReason = "";
  if (!serviceOnline) startDisabledReason = "Control service offline. Click Reconnect.";
  else if (busy) startDisabledReason = "Action in progress";
  else if (isLiveModeBlocked) startDisabledReason = "Live trading is locked (DEMO only)";
  else if (stopFlag || engineState === "EMERGENCY_STOP") startDisabledReason = "STOP.flag is active. Clear STOP.flag first.";
  else if (!mt5Connected) startDisabledReason = "MT5 not connected. Click Connect MT5 first.";
  else if (!demoVerified) startDisabledReason = "Non-demo MT5 account blocked. Switch to a DEMO account.";
  else if (engineState === "RUNNING") startDisabledReason = "Engine is already running";
  else if (engineState === "PAUSED") startDisabledReason = "Engine is paused — use Resume";
  else if (engineState === "STARTING") startDisabledReason = "Engine is starting";

  const isStartingNow = engineState === "STARTING" || busyAction === "Start";
  const startBtn: TopBarButtonState = {
    enabled: startDisabledReason === "",
    label: isStartingNow ? "Starting..." : "Start",
    tooltip: startDisabledReason || `Start engine in ${operatingMode} mode (DEMO)`,
    tone: "lime",
  };

  // 3. Pause / Resume toggle
  const isPaused = engineState === "PAUSED";
  const pauseAction: "PAUSE" | "RESUME" = isPaused ? "RESUME" : "PAUSE";
  let pauseDisabledReason = "";
  if (!serviceOnline) pauseDisabledReason = "Control service offline";
  else if (busy) pauseDisabledReason = "Action in progress";
  else if (stopFlag || engineState === "EMERGENCY_STOP") pauseDisabledReason = "Clear STOP.flag first";
  else if (engineState !== "RUNNING" && engineState !== "PAUSED") {
    pauseDisabledReason = "Start engine first";
  }

  const pauseResumeBtn: TopBarButtonState & { action: "PAUSE" | "RESUME" } = {
    enabled: pauseDisabledReason === "",
    action: pauseAction,
    label: isPaused ? "Resume" : "Pause",
    tooltip:
      pauseDisabledReason ||
      (isPaused
        ? "Resume automated trade entries"
        : "Pause new trade entries (open positions remain protected)"),
    tone: isPaused ? "lime" : "amber",
  };

  // 4. Stop button
  let stopDisabledReason = "";
  if (!serviceOnline) stopDisabledReason = "Control service offline";
  else if (busy) stopDisabledReason = "Action in progress";
  else if (engineState === "STOPPED") stopDisabledReason = "Engine is already stopped";

  const stopBtn: TopBarButtonState = {
    enabled: stopDisabledReason === "",
    label: "Stop",
    tooltip: stopDisabledReason || "Stop trading engine (open positions remain protected)",
    tone: "neutral",
  };

  // 5. Close All button
  let closeAllDisabledReason = "";
  if (!serviceOnline) closeAllDisabledReason = "Control service offline";
  else if (busy) closeAllDisabledReason = "Action in progress";
  else if (!mt5Connected) closeAllDisabledReason = "Connect MT5 first";

  const closeAllBtn: TopBarButtonState = {
    enabled: closeAllDisabledReason === "",
    label: "Close All",
    tooltip:
      closeAllDisabledReason ||
      "Close all bot-owned positions at market and reconcile with MT5",
    tone: "red",
  };

  return {
    serviceOnline,
    mt5Connected,
    mt5Syncing,
    demoVerified,
    engineState,
    engineStateLabel,
    engineChipTone,
    modeShort: formatShortMode(operatingMode),
    operatingMode,
    placesDemoOrders,
    isLiveModeBlocked,
    connectBtn,
    startBtn,
    pauseResumeBtn,
    stopBtn,
    closeAllBtn,
  };
}
