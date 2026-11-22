import { test } from "node:test";
import assert from "node:assert/strict";
import {
  deriveTopBarControlState,
  formatShortMode,
  isOrderPlacingDemoMode,
  sanitizeControlError,
} from "../topBarControlState.ts";
import type { ControlServiceStatus, ControlStatusPayload } from "../../types/index.ts";

function makeStatus(overrides: {
  mt5Status?: string;
  demoVerified?: boolean;
  tradeMode?: string;
  accountNumber?: number;
  engineState?: string;
  operatingMode?: ControlStatusPayload["engine"]["operating_mode"];
  dryRun?: boolean;
  stopFlag?: boolean;
  pauseFlag?: boolean;
} = {}): ControlStatusPayload {
  return {
    engine: {
      engine_state: overrides.engineState ?? "STOPPED",
      operating_mode: overrides.operatingMode ?? "DRY_RUN",
      dry_run: overrides.dryRun ?? true,
      live_trading_locked: true,
      stop_flag_active: overrides.stopFlag ?? false,
      pause_flag_active: overrides.pauseFlag ?? false,
      bridge_running: false,
      bridge_pid: null,
      engine_running: overrides.engineState === "RUNNING" || overrides.engineState === "PAUSED",
      engine_pid: overrides.engineState === "RUNNING" ? 1234 : null,
      started_at: null,
      last_heartbeat: null,
      last_signal: null,
      last_trade: null,
      last_execution_error: null,
    },
    mt5: {
      connection_status: overrides.mt5Status ?? "DISCONNECTED",
      last_sync_at: new Date().toISOString(),
      last_error: null,
      reconnect_attempts: 0,
      account: {
        account_number: overrides.accountNumber ?? 50123456,
        broker: "JustMarkets-Demo",
        currency: "USD",
        balance: 10000,
        equity: 10000,
        margin: 0,
        free_margin: 10000,
        margin_level: 0,
        leverage: 500,
        trade_mode: overrides.tradeMode ?? "DEMO",
        margin_mode_str: "HEDGING",
        demo_verified: overrides.demoVerified ?? true,
        netting_observe_only: false,
      },
      positions: [],
      pending_orders: [],
      symbols: {},
      reconciliation: {
        status: "RECONCILED",
        bot_owned_count: 0,
        manual_count: 0,
        other_ea_count: 0,
        unexpected_tickets: [],
        unprotected_bot_tickets: [],
      },
    },
    health: {
      timestamp: new Date().toISOString(),
      active_errors_count: 0,
      disk_free_gb: 50,
    },
  };
}

const ONLINE_SVC: ControlServiceStatus = {
  status: "ONLINE",
  host: "127.0.0.1",
  port: 8765,
  baseUrl: "http://127.0.0.1:8765",
};

const OFFLINE_SVC: ControlServiceStatus = {
  status: "OFFLINE",
  host: "127.0.0.1",
  port: 8765,
  baseUrl: "http://127.0.0.1:8765",
  lastError: "Connection refused",
};

test("DISCONNECTED MT5 state: Connect enabled, Start/Pause/Stop/CloseAll disabled with clear tooltips", () => {
  const s = deriveTopBarControlState({
    status: makeStatus({ mt5Status: "DISCONNECTED", engineState: "STOPPED" }),
    serviceStatus: ONLINE_SVC,
    busyAction: null,
  });
  assert.equal(s.mt5Connected, false);
  assert.equal(s.connectBtn.enabled, true);
  assert.equal(s.connectBtn.label, "Connect MT5");
  assert.equal(s.connectBtn.showDisconnect, false);
  assert.equal(s.startBtn.enabled, false);
  assert.match(s.startBtn.tooltip, /Connect MT5 first/i);
  assert.equal(s.pauseResumeBtn.enabled, false);
  assert.equal(s.stopBtn.enabled, false);
  assert.equal(s.closeAllBtn.enabled, false);
  assert.equal(s.engineStateLabel, "Stopped");
  assert.equal(s.modeShort, "DRY");
});

test("CONNECTED + STOPPED state: Connect shows quiet Connected + Disconnect, Start & CloseAll enabled, Pause & Stop disabled", () => {
  const s = deriveTopBarControlState({
    status: makeStatus({
      mt5Status: "CONNECTED",
      engineState: "STOPPED",
      operatingMode: "DEMO_FAST",
      dryRun: false,
    }),
    serviceStatus: ONLINE_SVC,
    busyAction: null,
  });
  assert.equal(s.mt5Connected, true);
  assert.equal(s.connectBtn.showDisconnect, true);
  assert.equal(s.connectBtn.disconnectEnabled, true);
  assert.equal(s.startBtn.enabled, true);
  assert.equal(s.placesDemoOrders, true);
  assert.equal(s.pauseResumeBtn.enabled, false);
  assert.equal(s.stopBtn.enabled, false);
  assert.equal(s.closeAllBtn.enabled, true);
  assert.equal(s.modeShort, "FAST");
});

test("RUNNING state: Start disabled, Pause amber enabled, Stop enabled, Disconnect blocked with tooltip", () => {
  const s = deriveTopBarControlState({
    status: makeStatus({
      mt5Status: "CONNECTED",
      engineState: "RUNNING",
      operatingMode: "OBSERVE",
      dryRun: true,
    }),
    serviceStatus: ONLINE_SVC,
    busyAction: null,
  });
  assert.equal(s.engineState, "RUNNING");
  assert.equal(s.engineStateLabel, "Running");
  assert.equal(s.engineChipTone, "lime");
  assert.equal(s.startBtn.enabled, false);
  assert.equal(s.pauseResumeBtn.enabled, true);
  assert.equal(s.pauseResumeBtn.action, "PAUSE");
  assert.equal(s.pauseResumeBtn.label, "Pause");
  assert.equal(s.pauseResumeBtn.tone, "amber");
  assert.equal(s.stopBtn.enabled, true);
  assert.equal(s.connectBtn.disconnectEnabled, false);
  assert.match(s.connectBtn.disconnectTooltip, /Stop the engine before disconnecting/i);
});

test("PAUSED state: Pause/Resume becomes lime Resume, Stop enabled, Disconnect blocked", () => {
  const s = deriveTopBarControlState({
    status: makeStatus({
      mt5Status: "CONNECTED",
      engineState: "PAUSED",
      pauseFlag: true,
      operatingMode: "DEMO_SCALPING",
      dryRun: false,
    }),
    serviceStatus: ONLINE_SVC,
    busyAction: null,
  });
  assert.equal(s.engineState, "PAUSED");
  assert.equal(s.engineStateLabel, "Paused");
  assert.equal(s.engineChipTone, "amber");
  assert.equal(s.startBtn.enabled, false);
  assert.equal(s.pauseResumeBtn.enabled, true);
  assert.equal(s.pauseResumeBtn.action, "RESUME");
  assert.equal(s.pauseResumeBtn.label, "Resume");
  assert.equal(s.pauseResumeBtn.tone, "lime");
  assert.equal(s.stopBtn.enabled, true);
  assert.equal(s.connectBtn.disconnectEnabled, false);
});

test("ERROR and EMERGENCY_STOP states: chip red, Start blocked on STOP.flag", () => {
  const errState = deriveTopBarControlState({
    status: makeStatus({ mt5Status: "CONNECTED", engineState: "ERROR" }),
    serviceStatus: ONLINE_SVC,
    busyAction: null,
  });
  assert.equal(errState.engineState, "ERROR");
  assert.equal(errState.engineChipTone, "red");
  assert.equal(errState.startBtn.enabled, true); // can restart after error if MT5 connected

  const estopState = deriveTopBarControlState({
    status: makeStatus({ mt5Status: "CONNECTED", engineState: "STOPPED", stopFlag: true }),
    serviceStatus: ONLINE_SVC,
    busyAction: null,
  });
  assert.equal(estopState.engineState, "EMERGENCY_STOP");
  assert.equal(estopState.engineStateLabel, "E-Stop");
  assert.equal(estopState.startBtn.enabled, false);
  assert.match(estopState.startBtn.tooltip, /STOP\.flag/i);
});

test("Non-demo account & OFFLINE service block Start and all actions cleanly", () => {
  const realAcc = deriveTopBarControlState({
    status: makeStatus({
      mt5Status: "CONNECTED",
      engineState: "STOPPED",
      demoVerified: false,
      tradeMode: "REAL",
    }),
    serviceStatus: ONLINE_SVC,
    busyAction: null,
  });
  assert.equal(realAcc.demoVerified, false);
  assert.equal(realAcc.startBtn.enabled, false);
  assert.match(realAcc.startBtn.tooltip, /Non-demo/i);

  const offline = deriveTopBarControlState({
    status: makeStatus({ mt5Status: "CONNECTED", engineState: "RUNNING" }),
    serviceStatus: OFFLINE_SVC,
    busyAction: null,
  });
  assert.equal(offline.serviceOnline, false);
  assert.equal(offline.connectBtn.enabled, false);
  assert.equal(offline.startBtn.enabled, false);
  assert.equal(offline.pauseResumeBtn.enabled, false);
  assert.equal(offline.stopBtn.enabled, false);
  assert.equal(offline.closeAllBtn.enabled, false);
});

test("In-flight busyAction disables all buttons to prevent double clicks", () => {
  const busy = deriveTopBarControlState({
    status: makeStatus({ mt5Status: "CONNECTED", engineState: "RUNNING" }),
    serviceStatus: ONLINE_SVC,
    busyAction: "Pause",
  });
  assert.equal(busy.connectBtn.enabled, false);
  assert.equal(busy.connectBtn.disconnectEnabled, false);
  assert.equal(busy.startBtn.enabled, false);
  assert.equal(busy.pauseResumeBtn.enabled, false);
  assert.equal(busy.stopBtn.enabled, false);
  assert.equal(busy.closeAllBtn.enabled, false);
});

test("Helper functions formatShortMode, isOrderPlacingDemoMode, sanitizeControlError", () => {
  assert.equal(formatShortMode("OBSERVE"), "OBS");
  assert.equal(formatShortMode("DEMO_FAST"), "FAST");
  assert.equal(isOrderPlacingDemoMode("OBSERVE"), false);
  assert.equal(isOrderPlacingDemoMode("DRY_RUN"), false);
  assert.equal(isOrderPlacingDemoMode("DEMO_FAST"), true);
  assert.equal(sanitizeControlError("TypeError: undefined is not a function", "Fallback"), "Fallback");
  assert.equal(sanitizeControlError("connect ECONNREFUSED 127.0.0.1:8765"), "Control service is offline.");
});
