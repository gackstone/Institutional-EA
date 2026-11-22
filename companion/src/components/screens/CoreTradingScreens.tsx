import React, { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ChevronDown,
  Clock,
  Loader2,
  Lock,
  Pause,
  Play,
  Plug,
  Scissors,
  Send,
  ShieldAlert,
  ShieldCheck,
  Square,
  TrendingDown,
  TrendingUp,
  Unplug,
  Wifi,
  WifiOff,
  XCircle,
} from "lucide-react";
import { controlClient, formatControlError, IPC } from "../../services/ipc";
import {
  ControlPosition,
  ControlServiceStatus,
  ControlStatusPayload,
  MT5TerminalInfo,
  ScreenId,
  TradeHistoryRecord,
} from "../../types";
import {
  buildNormalizedDashboardData,
  buildSymbolChartBundle,
  CandleBar,
  ChartSymbol,
  ChartTimeframe,
  DataFeedStatus,
} from "../../services/dashboardDataAdapter";
import { ControlSymbolSpec } from "../../types";
import {
  calculateTradeMetrics,
  validateTightenOnlyStopLoss,
} from "../../utils/tradeChartMath";
import {
  deriveTopBarControlState,
  sanitizeControlError,
} from "../../utils/topBarControlState";
import { getSymbolChipSpec } from "../../styles/designTokens";
import { UI_COPY } from "../../constants/uiCopy";
import { LiveTradingChart } from "../LiveTradingChart";

// One-time confirmation flag per app session for demo order-placing Start
let sessionStartDemoConfirmed = false;

interface CommonProps {
  status: ControlStatusPayload | null;
  onRefresh: () => Promise<void>;
  onActionMessage: (msg: string, isError?: boolean) => void;
}

export const DashboardScreen: React.FC<
  CommonProps & {
    onNavigate: (s: ScreenId) => void;
    trades?: TradeHistoryRecord[];
    feedStatus?: DataFeedStatus;
    initialSymbol?: ChartSymbol;
    readOnlyMobile?: boolean;
    serviceStatus?: ControlServiceStatus | null;
    onReconnectService?: () => Promise<void>;
  }
> = ({
  status,
  onRefresh,
  onNavigate,
  onActionMessage,
  trades = [],
  feedStatus = "LIVE_SSE",
  initialSymbol = "XAUUSD",
  readOnlyMobile = false,
  serviceStatus = null,
  onReconnectService,
}) => {
  const [selectedSymbol, setSelectedSymbol] = useState<ChartSymbol>(initialSymbol);
  const [selectedTimeframe, setSelectedTimeframe] = useState<ChartTimeframe>("M5");
  const [realCandles, setRealCandles] = useState<CandleBar[]>([]);
  const [liveQuote, setLiveQuote] = useState<ControlSymbolSpec | null>(null);
  const [candleWaitingReason, setCandleWaitingReason] = useState<string | undefined>(undefined);
  const [utcClockText, setUtcClockText] = useState<string>(() =>
    `${new Date().toISOString().slice(11, 19)} UTC`
  );
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [connectingMt5, setConnectingMt5] = useState<boolean>(false);
  const [mt5PickerTerminals, setMt5PickerTerminals] = useState<MT5TerminalInfo[] | null>(null);

  // Sync external symbol jump (e.g., clicking a row in Live Signal Grid)
  useEffect(() => {
    setSelectedSymbol(initialSymbol);
  }, [initialSymbol]);

  // Confirmation modal state for Close All (2-step), Mobile Pause (2-step), Stop (1-step), Start Demo Orders (1-step)
  const [confirmModal, setConfirmModal] = useState<{
    type: "CLOSE_ALL" | "PAUSE" | "STOP" | "START_DEMO";
    step: 1 | 2;
  } | null>(null);

  // Tighten-Only Stop Loss modification modal state
  const [slModalPos, setSlModalPos] = useState<ControlPosition | null>(null);
  const [proposedSlInput, setProposedSlInput] = useState<string>("");
  const [proposedTpInput, setProposedTpInput] = useState<string>("");

  // Lightweight 1-second UTC clock (isolated from chart series)
  useEffect(() => {
    const timer = setInterval(() => {
      setUtcClockText(`${new Date().toISOString().slice(11, 19)} UTC`);
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  // Fetch real OHLC candles directly from MT5 via Control Service (/api/market/candles)
  useEffect(() => {
    let cancelled = false;
    const loadCandles = async () => {
      try {
        const res = await controlClient.getCandles(selectedSymbol, selectedTimeframe, 120);
        if (!cancelled) {
          setRealCandles(res.candles || []);
          setLiveQuote(res.quote || null);
          if ((res.candles || []).length > 0) {
            setCandleWaitingReason(undefined);
          } else if (res.status_reason === "MT5_NOT_CONNECTED") {
            setCandleWaitingReason("MT5 Not Connected");
          } else if (res.status_reason === "SYMBOL_NOT_FOUND") {
            setCandleWaitingReason(`Symbol Not Found (${res.broker_symbol})`);
          } else if (res.status_reason === "MARKET_CLOSED") {
            setCandleWaitingReason("Market Closed");
          } else {
            setCandleWaitingReason("Waiting for MT5 Candles");
          }
        }
      } catch {
        if (!cancelled) {
          setRealCandles([]);
          setLiveQuote(null);
          setCandleWaitingReason(
            serviceStatus?.status === "STARTING"
              ? "Control Service Starting..."
              : "Service Offline — Retrying..."
          );
        }
      }
    };
    loadCandles();
    const timer = setInterval(loadCandles, 5000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [selectedSymbol, selectedTimeframe, serviceStatus?.status]);

  // Build normalized dashboard state strictly from real MT5/bot data
  const dash = useMemo(
    () => buildNormalizedDashboardData(status, trades),
    [status, trades]
  );

  const activePositions = dash.status.mt5.positions;
  const effectiveStatus = dash.status;

  // Build Live Chart bundle strictly from real MT5 candles & positions
  const chartBundle = useMemo(
    () =>
      buildSymbolChartBundle(
        selectedSymbol,
        selectedTimeframe,
        effectiveStatus,
        realCandles,
        liveQuote
      ),
    [selectedSymbol, selectedTimeframe, effectiveStatus, realCandles, liveQuote]
  );

  const eng = effectiveStatus.engine;
  const kpis = dash.kpis;
  const botOpenCount = activePositions.filter((p) => p.ownership === "BOT").length;
  const topBar = useMemo(
    () =>
      deriveTopBarControlState({
        status: effectiveStatus,
        serviceStatus,
        feedStatus,
        busyAction,
        connectingMt5,
      }),
    [effectiveStatus, serviceStatus, feedStatus, busyAction, connectingMt5]
  );
  const provenanceLabel = dash.provenance.connected
    ? `${dash.provenance.source}${
        dash.provenance.updatedAt
          ? ` · ${new Date(dash.provenance.updatedAt).toISOString().slice(11, 19)}`
          : ""
      }`
    : "Waiting for MT5";

  const handleSaveScreenshot = async (
    ticket: number,
    symbol: string,
    stage: string,
    dataUrl: string
  ) => {
    try {
      const res = await controlClient.saveTradeScreenshot(ticket, symbol, stage, dataUrl);
      if (res.success && stage === "MANUAL") {
        onActionMessage(`Saved chart PNG (${res.filename})`);
      }
    } catch {
      // ignore offline
    }
  };

  // Execute existing Control Service endpoints safely (ignores double clicks)
  const executeControlAction = async (
    label: string,
    fn: () => Promise<{ success?: boolean; message?: string; error?: string | null }>
  ) => {
    if (busyAction !== null) return;
    setBusyAction(label);
    try {
      const res = await fn();
      if (res.success === false) {
        onActionMessage(
          `${label}: ${sanitizeControlError(res.message || res.error, "Request rejected")}`,
          true
        );
      } else {
        onActionMessage(`${label}: ${res.message || "OK"}`, false);
      }
      await onRefresh();
    } catch (e: any) {
      const friendly = sanitizeControlError(formatControlError(e), "Action failed");
      const offlineSafetyNote =
        /offline/i.test(friendly) && /close all|stop|pause/i.test(label)
          ? " Manage open positions directly in MT5."
          : "";
      onActionMessage(`${label} failed: ${friendly}${offlineSafetyNote}`, true);
    } finally {
      setBusyAction(null);
    }
  };

  // Connect MT5 reusing the exact scan + connectMT5 flow from MT5 Terminal screen
  const connectToTerminalPath = async (terminalPath?: string) => {
    if (busyAction !== null) return;
    setMt5PickerTerminals(null);
    setConnectingMt5(true);
    setBusyAction("Connect MT5");
    try {
      const res = await controlClient.connectMT5(terminalPath);
      if (res.success) {
        const acct = res.snapshot?.account;
        if (acct?.account_number && !acct?.demo_verified) {
          await controlClient.disconnectMT5().catch(() => {});
          onActionMessage("DEMO Lock: Non-demo MT5 account refused.", true);
        } else {
          onActionMessage(
            `MT5 Connected (${acct?.broker || "DEMO"} · ${
              acct?.account_number ? `***${String(acct.account_number).slice(-4)}` : "DEMO"
            })`
          );
        }
      } else {
        onActionMessage(
          `Connect MT5: ${sanitizeControlError(res.error, "Unable to connect to MT5 terminal")}`,
          true
        );
      }
      await onRefresh();
    } catch (e: any) {
      onActionMessage(`Connect MT5 failed: ${sanitizeControlError(formatControlError(e))}`, true);
    } finally {
      setConnectingMt5(false);
      setBusyAction(null);
    }
  };

  const handleConnectMt5Click = async () => {
    if (!topBar.connectBtn.enabled || busyAction !== null) return;
    setConnectingMt5(true);
    setBusyAction("Scan MT5");
    try {
      const terminals = await IPC.scanMT5Terminals().catch(() => [] as MT5TerminalInfo[]);
      if (terminals.length > 1) {
        setMt5PickerTerminals(terminals);
        setConnectingMt5(false);
        setBusyAction(null);
        return;
      }
      setConnectingMt5(false);
      setBusyAction(null);
      await connectToTerminalPath(terminals[0]?.executablePath);
    } catch {
      setConnectingMt5(false);
      setBusyAction(null);
      await connectToTerminalPath(undefined);
    }
  };

  const handleDisconnectMt5Click = async () => {
    if (!topBar.connectBtn.disconnectEnabled || busyAction !== null) return;
    await executeControlAction("Disconnect MT5", async () => {
      const res = await controlClient.disconnectMT5();
      return {
        success: res.success,
        message: res.success ? "Disconnected from MT5 terminal." : res.error || "Disconnect blocked",
      };
    });
  };

  const handleStartEngineClick = async () => {
    if (!topBar.startBtn.enabled || busyAction !== null) return;
    if (topBar.placesDemoOrders && !sessionStartDemoConfirmed) {
      setConfirmModal({ type: "START_DEMO", step: 1 });
      return;
    }
    await executeControlAction("Start", () => controlClient.startEngine());
  };

  // Confirmation modal handler
  const handleConfirmTwoStep = async () => {
    if (!confirmModal) return;
    if ((confirmModal.type === "CLOSE_ALL" || confirmModal.type === "PAUSE") && confirmModal.step === 1) {
      setConfirmModal({ ...confirmModal, step: 2 });
      return;
    }

    const actionType = confirmModal.type;
    setConfirmModal(null);
    if (actionType === "START_DEMO") {
      sessionStartDemoConfirmed = true;
      await executeControlAction("Start", () => controlClient.startEngine());
      return;
    }
    if (actionType === "STOP") {
      await executeControlAction("Stop", () => controlClient.stopEngine());
      return;
    }
    if (actionType === "PAUSE") {
      await executeControlAction(
        topBar.pauseResumeBtn.label,
        () =>
          topBar.pauseResumeBtn.action === "RESUME"
            ? controlClient.resumeEntries()
            : controlClient.pauseEntries()
      );
      return;
    }
    await executeControlAction("Close All", () => controlClient.closeAllBotPositions(true));
  };

  // Partial Close 50%
  const handlePartialClose50 = async (pos: ControlPosition) => {
    const halfVol = Number(Math.max(0.01, pos.volume / 2).toFixed(2));
    setBusyAction(`50% #${pos.ticket}`);
    try {
      const res = await IPC.closePosition(pos.ticket, halfVol);
      onActionMessage(`50% closed #${pos.ticket} (${halfVol.toFixed(2)}L). ${res.message}`);
      await onRefresh();
    } catch (e: any) {
      onActionMessage(`Partial close error: ${e.message}`, true);
    } finally {
      setBusyAction(null);
    }
  };

  // Full Close single position
  const handleCloseSinglePosition = async (pos: ControlPosition) => {
    setBusyAction(`Close #${pos.ticket}`);
    try {
      const res = await controlClient.closePosition(pos.ticket, true);
      onActionMessage(`Closed #${pos.ticket}: ${res.message}`);
      await onRefresh();
    } catch (e: any) {
      onActionMessage(`Close #${pos.ticket} error: ${e.message}`, true);
    } finally {
      setBusyAction(null);
    }
  };

  // Move SL to Break-Even+ (Tighten-Only)
  const handleMoveToBreakEven = async (pos: ControlPosition) => {
    const dir = pos.direction === "SELL" ? "SELL" : "BUY";
    const digits = pos.symbol.includes("JPY") ? 3 : 2;
    const buffer = pos.symbol.includes("BTC") ? 15 : pos.symbol.includes("JPY") ? 0.015 : 0.35;
    const targetBeSl = Number(
      (dir === "BUY" ? pos.open_price + buffer : pos.open_price - buffer).toFixed(digits)
    );

    const validation = validateTightenOnlyStopLoss({
      direction: dir,
      currentSl: pos.sl,
      proposedSl: targetBeSl,
      currentPrice: pos.current_price,
    });

    if (!validation.allowed) {
      onActionMessage(`BE+ blocked: ${validation.reason}`, true);
      return;
    }

    setBusyAction(`BE #${pos.ticket}`);
    try {
      const res = await controlClient.modifyPosition(pos.ticket, targetBeSl, pos.tp);
      onActionMessage(`#${pos.ticket} SL -> BE+ (${targetBeSl.toFixed(digits)}) ${res.message || ""}`);
      await onRefresh();
    } catch (e: any) {
      onActionMessage(`BE+ error: ${e.message}`, true);
    } finally {
      setBusyAction(null);
    }
  };

  // Open Tighten-Only SL Modal
  const openTightenSlModal = (pos: ControlPosition) => {
    const digits = pos.symbol.includes("JPY") ? 3 : 2;
    const step = pos.symbol.includes("BTC") ? 25 : pos.symbol.includes("JPY") ? 0.03 : 0.6;
    const dir = pos.direction === "SELL" ? "SELL" : "BUY";
    const baseSl = pos.sl > 0 ? pos.sl : pos.open_price;
    const suggestedTighterSl = Number(
      (dir === "BUY"
        ? Math.min(pos.current_price - step, baseSl + step)
        : Math.max(pos.current_price + step, baseSl - step)
      ).toFixed(digits)
    );
    setSlModalPos(pos);
    setProposedSlInput(String(suggestedTighterSl));
    setProposedTpInput(String(pos.tp || 0));
  };

  const slValidation = useMemo(() => {
    if (!slModalPos) return { allowed: false, reason: "" };
    const dir = slModalPos.direction === "SELL" ? "SELL" : "BUY";
    return validateTightenOnlyStopLoss({
      direction: dir,
      currentSl: slModalPos.sl,
      proposedSl: Number(proposedSlInput),
      currentPrice: slModalPos.current_price,
    });
  }, [slModalPos, proposedSlInput]);

  const handleApplyTightenSl = async () => {
    if (!slModalPos) return;
    if (!slValidation.allowed) {
      onActionMessage(slValidation.reason, true);
      return;
    }
    const newSl = Number(proposedSlInput);
    const newTp = Number(proposedTpInput);
    setBusyAction(`SL+ #${slModalPos.ticket}`);
    try {
      const res = await controlClient.modifyPosition(slModalPos.ticket, newSl, newTp);
      onActionMessage(`SL+ #${slModalPos.ticket} -> ${newSl}: ${res.message}`);
      setSlModalPos(null);
      await onRefresh();
    } catch (e: any) {
      onActionMessage(`SL+ error: ${e.message}`, true);
    } finally {
      setBusyAction(null);
    }
  };

  return (
    <div className="max-w-[1920px] mx-auto space-y-3.5 text-[#F4F7FF]">
      {/* Compact Connection / Stale / Emergency Banner States */}
      {feedStatus === "DISCONNECTED" && (
        <div
          role="alert"
          title="Local Python Control Service unreachable on 127.0.0.1:8765"
          className="flex items-center justify-between px-4 py-2.5 rounded-2xl bg-[#FF5A6E]/18 border border-[#FF5A6E]/50 backdrop-blur-xl text-xs text-[#F4F7FF]"
        >
          <div className="flex items-center space-x-2">
            <WifiOff className="w-4 h-4 text-[#FF5A6E] shrink-0" />
            <span>
              <strong>Svc Offline (127.0.0.1:8765)</strong> · Cached DEMO
            </span>
          </div>
          <button
            type="button"
            onClick={() => onRefresh()}
            className="px-3 py-1 rounded-full bg-[#FF5A6E] hover:bg-[#FF7A8A] text-white font-semibold transition"
          >
            Reconnect
          </button>
        </div>
      )}

      {feedStatus === "STALE" && (
        <div
          role="alert"
          title="Last MT5 sync heartbeat exceeded 15 seconds"
          className="flex items-center justify-between px-4 py-2.5 rounded-2xl bg-[#FBBF24]/18 border border-[#FBBF24]/50 backdrop-blur-xl text-xs text-[#F4F7FF]"
        >
          <div className="flex items-center space-x-2">
            <AlertTriangle className="w-4 h-4 text-[#FBBF24] shrink-0" />
            <strong>Stale Sync (&gt;15s)</strong>
          </div>
          <button
            type="button"
            onClick={() => onRefresh()}
            className="px-3 py-1 rounded-full bg-[#FBBF24] text-[#081321] font-semibold transition"
          >
            Sync
          </button>
        </div>
      )}

      {eng.stop_flag_active && (
        <div
          role="alert"
          title="Emergency STOP.flag kill switch is active; all new entries are blocked"
          className="flex items-center justify-between px-4 py-2.5 rounded-2xl bg-[#FF5A6E]/22 border border-[#FF5A6E]/60 backdrop-blur-xl text-xs"
        >
          <div className="flex items-center space-x-2">
            <ShieldAlert className="w-4 h-4 text-[#FF5A6E] shrink-0" />
            <span className="font-bold text-[#FFD9DF]">STOP.flag ACTIVE · Entries Blocked</span>
          </div>
          <button
            type="button"
            onClick={() =>
              executeControlAction("Clear Stop", () => controlClient.clearEmergencyStop(true))
            }
            className="px-3 py-1 rounded-full bg-[#B0F648] hover:bg-[#C2F076] text-[#081321] font-bold transition"
          >
            Clear Stop
          </button>
        </div>
      )}

      {/* =====================================================================
          ROW 1: COMPACT TOP STATUS BAR + CONTROLS (Connect MT5 / Start / Pause-Resume / Stop | Close All)
      ====================================================================== */}
      <section
        aria-label="Terminal Top Status Bar"
        className="iea-glass-card relative flex flex-wrap items-center justify-between gap-2 px-3.5 py-2"
      >
        <div className="flex flex-wrap items-center gap-1.5 text-xs min-w-0">
          {/* MT5 Connection + Masked Account */}
          <div
            title={
              topBar.mt5Connected
                ? `Connected MT5 Account ${dash.maskedAccount} (${effectiveStatus.mt5.account.broker})`
                : "MT5 Terminal disconnected"
            }
            className="iea-pill-control inline-flex items-center space-x-1.5 px-2.5 py-1 whitespace-nowrap"
          >
            {topBar.mt5Connected ? (
              <Wifi className="w-3.5 h-3.5 text-[#B0F648] shrink-0" />
            ) : (
              <WifiOff className="w-3.5 h-3.5 text-[#FF5A6E] shrink-0" />
            )}
            <span className="font-medium text-[#F4F7FF]">MT5</span>
            <span
              className={`font-mono font-bold ${
                topBar.mt5Connected ? "text-[#B0F648]" : "text-[#8496B8]"
              }`}
              data-testid="masked-account-badge"
            >
              {topBar.mt5Connected ? dash.maskedAccount : "OFF"}
            </span>
          </div>

          {/* Compact Engine State + Mode Chip */}
          <div
            data-testid="engine-state-chip"
            title={`Engine State: ${topBar.engineState} · Mode: ${topBar.operatingMode}${
              eng.engine_pid ? ` · PID ${eng.engine_pid}` : ""
            }`}
            className={`inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-full border font-mono text-[11px] font-bold whitespace-nowrap ${
              topBar.engineChipTone === "lime"
                ? "bg-[#B0F648]/16 border-[#B0F648]/50 text-[#B0F648]"
                : topBar.engineChipTone === "amber"
                ? "bg-[#FBBF24]/16 border-[#FBBF24]/50 text-[#FBBF24]"
                : topBar.engineChipTone === "red"
                ? "bg-[#FF5A6E]/18 border-[#FF5A6E]/55 text-[#FF7A8A]"
                : "bg-[#192E58]/60 border-[rgba(186,214,255,0.2)] text-[#B6C5E0]"
            }`}
          >
            <span
              className={`w-2 h-2 rounded-full shrink-0 ${
                topBar.engineChipTone === "lime"
                  ? "bg-[#B0F648] shadow-[0_0_8px_#B0F648]"
                  : topBar.engineChipTone === "amber"
                  ? "bg-[#FBBF24]"
                  : topBar.engineChipTone === "red"
                  ? "bg-[#FF5A6E]"
                  : "bg-[#8496B8]"
              }`}
            />
            <span>{topBar.engineStateLabel}</span>
            <span className="opacity-60">·</span>
            <span className="text-[#F4F7FF]/90">{topBar.modeShort}</span>
          </div>

          {/* Hard Safety Lock Badge */}
          <div
            data-testid="demo-lock-badge"
            title={UI_COPY.brand.demoLockTooltip}
            className="inline-flex items-center space-x-1 px-2.5 py-1 rounded-full bg-[#B0F648]/14 border border-[#B0F648]/45 text-[#C2F076] font-mono text-[11px] font-bold whitespace-nowrap"
          >
            <Lock className="w-3 h-3 text-[#B0F648] shrink-0" />
            <span>{UI_COPY.brand.demoLockChip}</span>
          </div>

          {/* Control Service Status Pill + Reconnect */}
          {serviceStatus && (
            <div
              data-testid="control-service-status-pill"
              title={`Control Service on ${serviceStatus.baseUrl}${serviceStatus.lastError ? ` · ${serviceStatus.lastError}` : ""}`}
              className="iea-pill-control inline-flex items-center space-x-1.5 px-2.5 py-1 font-mono text-[11px] whitespace-nowrap"
            >
              <span
                className={`w-2 h-2 rounded-full shrink-0 ${
                  serviceStatus.status === "ONLINE"
                    ? "bg-[#B0F648] shadow-[0_0_8px_#B0F648]"
                    : serviceStatus.status === "STARTING"
                    ? "bg-[#FBBF24]"
                    : "bg-[#FF5A6E]"
                }`}
              />
              <span className="text-[#B6C5E0]">SVC</span>
              <span
                className={`font-bold ${
                  serviceStatus.status === "ONLINE"
                    ? "text-[#B0F648]"
                    : serviceStatus.status === "STARTING"
                    ? "text-[#FBBF24]"
                    : "text-[#FF5A6E]"
                }`}
              >
                {serviceStatus.status === "ONLINE"
                  ? "ONLINE"
                  : serviceStatus.status === "STARTING"
                  ? "STARTING"
                  : "OFFLINE"}
              </span>
              {serviceStatus.status !== "ONLINE" && onReconnectService && (
                <button
                  type="button"
                  onClick={() => onReconnectService()}
                  className="ml-1 px-2 py-0.5 rounded-full bg-[#B0F648] text-[#081321] font-bold text-[10px] hover:bg-[#C2F076] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B0F648]"
                >
                  Reconnect
                </button>
              )}
            </div>
          )}

          {/* ZMQ Bridge Ports 5555 / 5556 (Real TCP Probe Status) */}
          <div
            title={`ZMQ/TCP Bridge Sockets: Port 5555 (${effectiveStatus.mt5.zmq_bridge?.port_5555 ? "LISTENING" : "IDLE"}) & Port 5556 (${effectiveStatus.mt5.zmq_bridge?.port_5556 ? "LISTENING" : "IDLE"})`}
            className="iea-pill-control inline-flex items-center space-x-1.5 px-2.5 py-1 font-mono text-[11px] whitespace-nowrap"
          >
            <span
              className={`w-2 h-2 rounded-full shrink-0 ${
                effectiveStatus.mt5.zmq_bridge?.port_5555
                  ? "bg-[#B0F648] shadow-[0_0_8px_#B0F648]"
                  : "bg-[#8496B8]"
              }`}
            />
            <span className="text-[#B6C5E0]">ZMQ</span>
            <span
              className={`font-bold ${
                effectiveStatus.mt5.zmq_bridge?.port_5555 ? "text-[#B0F648]" : "text-[#8496B8]"
              }`}
            >
              {effectiveStatus.mt5.zmq_bridge?.port_5555 ? "5555 UP" : "5555 IDLE"}
            </span>
          </div>

          {/* Telegram Status */}
          <button
            type="button"
            onClick={() =>
              executeControlAction("TG Test", () => controlClient.testTelegram(false))
            }
            aria-label="Telegram status and quick connectivity test"
            title="Telegram notification dispatcher ready (click to test)"
            className="iea-pill-control inline-flex items-center space-x-1.5 px-2.5 py-1 text-[11px] text-[#F4F7FF] whitespace-nowrap focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#5EEAD4]"
          >
            <Send className="w-3 h-3 text-[#5EEAD4] shrink-0" />
            <span className="text-[#B0F648] font-semibold">TG Ready</span>
          </button>

          {/* Live UTC Clock */}
          <div
            title="Live UTC Terminal Clock"
            className="iea-pill-control inline-flex items-center space-x-1.5 px-2.5 py-1 text-[11px] whitespace-nowrap"
          >
            <Clock className="w-3 h-3 text-[#8496B8] shrink-0" />
            <span className="font-mono text-[#F4F7FF] tabular-nums" data-testid="utc-clock">
              {utcClockText}
            </span>
          </div>
        </div>

        {/* Right: Ordered Action Group [Connect MT5] [Start] [Pause / Resume] [Stop]  |  [Close All] */}
        <div
          aria-label="Engine and MT5 Controls"
          className="flex flex-wrap items-center gap-1.5 shrink-0"
        >
          {/* 1. Connect MT5 (or quiet Connected + Disconnect) */}
          {!readOnlyMobile && (
            <div className="relative inline-flex items-center">
              {topBar.connectBtn.showDisconnect ? (
                <div className="inline-flex items-center rounded-full bg-[#192E58]/55 border border-[#5EEAD4]/35 text-xs overflow-hidden">
                  <span
                    data-testid="btn-connect-mt5-connected"
                    title={topBar.connectBtn.tooltip}
                    className="px-2.5 py-1 text-[#5EEAD4] font-semibold inline-flex items-center space-x-1 whitespace-nowrap"
                  >
                    <Plug className="w-3 h-3 shrink-0" />
                    <span>Connected</span>
                  </span>
                  <button
                    type="button"
                    data-testid="btn-disconnect-mt5"
                    disabled={!topBar.connectBtn.disconnectEnabled}
                    onClick={handleDisconnectMt5Click}
                    aria-label="Disconnect MT5"
                    title={topBar.connectBtn.disconnectTooltip}
                    className="px-2 py-1 border-l border-[#5EEAD4]/25 text-[#B6C5E0] hover:text-[#FF7A8A] hover:bg-[#FF5A6E]/15 disabled:opacity-40 disabled:cursor-not-allowed inline-flex items-center space-x-1 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#5EEAD4]"
                  >
                    {busyAction === "Disconnect MT5" ? (
                      <Loader2 className="w-3 h-3 animate-spin" />
                    ) : (
                      <Unplug className="w-3 h-3" />
                    )}
                    <span className="text-[11px]">Disconnect</span>
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  data-testid="btn-connect-mt5"
                  disabled={!topBar.connectBtn.enabled}
                  onClick={handleConnectMt5Click}
                  aria-label="Connect MT5 terminal"
                  title={topBar.connectBtn.tooltip}
                  className="px-3 py-1.5 rounded-full bg-[#5EEAD4]/14 hover:bg-[#5EEAD4]/24 border border-[#5EEAD4]/55 disabled:opacity-40 disabled:cursor-not-allowed text-[#5EEAD4] text-xs font-semibold inline-flex items-center space-x-1.5 whitespace-nowrap transition duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#5EEAD4]"
                >
                  {topBar.mt5Syncing || busyAction === "Connect MT5" || busyAction === "Scan MT5" ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" />
                  ) : (
                    <Plug className="w-3.5 h-3.5 shrink-0" />
                  )}
                  <span>{topBar.connectBtn.label}</span>
                  {mt5PickerTerminals && mt5PickerTerminals.length > 1 && (
                    <ChevronDown className="w-3 h-3 shrink-0" />
                  )}
                </button>
              )}

              {/* Multi-terminal picker popover */}
              {mt5PickerTerminals && mt5PickerTerminals.length > 1 && (
                <div
                  role="menu"
                  aria-label="Select MT5 Terminal"
                  className="absolute right-0 top-full mt-2 z-50 w-72 iea-glass-card p-2 shadow-2xl border border-[#5EEAD4]/40 space-y-1"
                >
                  <div className="flex items-center justify-between px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-[#8496B8]">
                    <span>Select MT5 Terminal ({mt5PickerTerminals.length})</span>
                    <button
                      type="button"
                      onClick={() => setMt5PickerTerminals(null)}
                      className="text-[#B6C5E0] hover:text-white"
                    >
                      Close
                    </button>
                  </div>
                  {mt5PickerTerminals.map((t) => (
                    <button
                      key={t.executablePath}
                      type="button"
                      onClick={() => connectToTerminalPath(t.executablePath)}
                      className="w-full text-left px-2.5 py-1.5 rounded-xl hover:bg-[#5EEAD4]/15 text-xs transition flex items-center justify-between gap-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#5EEAD4]"
                    >
                      <div className="min-w-0">
                        <div className="font-semibold text-[#F4F7FF] truncate">{t.name}</div>
                        <div className="text-[10px] font-mono text-[#8496B8] truncate">
                          {t.executablePath}
                        </div>
                      </div>
                      {t.isRunning && (
                        <span className="px-1.5 py-0.5 rounded-full bg-[#B0F648]/20 text-[#B0F648] text-[9px] font-mono font-bold shrink-0">
                          RUN
                        </span>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* 2. Start */}
          {!readOnlyMobile && (
            <button
              type="button"
              data-testid="btn-start-engine"
              disabled={!topBar.startBtn.enabled}
              onClick={handleStartEngineClick}
              aria-label="Start trading engine"
              title={topBar.startBtn.tooltip}
              className="px-3 py-1.5 rounded-full bg-[#B0F648] hover:bg-[#C2F076] disabled:bg-[#B0F648]/25 disabled:text-[#B0F648]/60 disabled:border disabled:border-[#B0F648]/30 disabled:cursor-not-allowed text-[#081321] text-xs font-extrabold inline-flex items-center space-x-1.5 whitespace-nowrap shadow-[0_2px_12px_rgba(176,246,72,0.28)] disabled:shadow-none transition duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#B0F648]"
            >
              {busyAction === "Start" ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" />
              ) : (
                <Play className="w-3.5 h-3.5 shrink-0 fill-current" />
              )}
              <span>{topBar.startBtn.label}</span>
            </button>
          )}

          {/* 3. Pause / Resume toggle */}
          <button
            type="button"
            data-testid="btn-pause-resume-engine"
            disabled={!topBar.pauseResumeBtn.enabled}
            onClick={() =>
              readOnlyMobile
                ? setConfirmModal({ type: "PAUSE", step: 1 })
                : executeControlAction(topBar.pauseResumeBtn.label, () =>
                    topBar.pauseResumeBtn.action === "RESUME"
                      ? controlClient.resumeEntries()
                      : controlClient.pauseEntries()
                  )
            }
            aria-label={
              topBar.pauseResumeBtn.action === "RESUME"
                ? "Resume new trade entries"
                : "Pause new trade entries"
            }
            title={topBar.pauseResumeBtn.tooltip}
            className={`px-3 py-1.5 rounded-full border disabled:opacity-40 disabled:cursor-not-allowed text-xs font-semibold inline-flex items-center space-x-1.5 whitespace-nowrap transition duration-200 focus-visible:outline-none focus-visible:ring-2 ${
              topBar.pauseResumeBtn.tone === "lime"
                ? "bg-[#B0F648]/20 hover:bg-[#B0F648]/30 border-[#B0F648]/55 text-[#B0F648] focus-visible:ring-[#B0F648]"
                : "bg-[#FBBF24]/20 hover:bg-[#FBBF24]/30 border-[#FBBF24]/55 text-[#FBBF24] focus-visible:ring-[#FBBF24]"
            }`}
          >
            {busyAction === "Pause" || busyAction === "Resume" ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" />
            ) : topBar.pauseResumeBtn.action === "RESUME" ? (
              <Play className="w-3.5 h-3.5 shrink-0" />
            ) : (
              <Pause className="w-3.5 h-3.5 shrink-0" />
            )}
            <span>{topBar.pauseResumeBtn.label}</span>
          </button>

          {/* 4. Stop */}
          {!readOnlyMobile && (
            <button
              type="button"
              data-testid="btn-stop-engine"
              disabled={!topBar.stopBtn.enabled}
              onClick={() => setConfirmModal({ type: "STOP", step: 1 })}
              aria-label="Stop trading engine"
              title={topBar.stopBtn.tooltip}
              className="iea-pill-control px-3 py-1.5 disabled:opacity-40 disabled:cursor-not-allowed text-[#F4F7FF] text-xs font-semibold inline-flex items-center space-x-1.5 whitespace-nowrap transition duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#F4F7FF]"
            >
              {busyAction === "Stop" ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0 text-[#FF5A6E]" />
              ) : (
                <Square className="w-3.5 h-3.5 shrink-0 text-[#FF5A6E]" />
              )}
              <span>{topBar.stopBtn.label}</span>
            </button>
          )}

          {/* 5. Visually separated Close All on far right */}
          {!readOnlyMobile && (
            <div className="ml-1.5 pl-2.5 border-l border-[rgba(186,214,255,0.2)]">
              <button
                type="button"
                data-testid="btn-close-all"
                disabled={!topBar.closeAllBtn.enabled}
                onClick={() => setConfirmModal({ type: "CLOSE_ALL", step: 1 })}
                aria-label="Close all bot-owned positions (two-step confirmation)"
                title={topBar.closeAllBtn.tooltip}
                className="px-3.5 py-1.5 rounded-full bg-gradient-to-r from-[#FF5A6E] to-[#E11D48] hover:brightness-110 disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-bold inline-flex items-center space-x-1.5 whitespace-nowrap shadow-[0_4px_16px_rgba(255,90,110,0.4)] disabled:shadow-none transition duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#FF5A6E]"
              >
                {busyAction === "Close All" ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" />
                ) : (
                  <XCircle className="w-3.5 h-3.5 shrink-0" />
                )}
                <span>{topBar.closeAllBtn.label}</span>
              </button>
            </div>
          )}
        </div>
      </section>

      {/* =====================================================================
          ROW 2: 5 EVENLY DISTRIBUTED, EQUAL-HEIGHT KPI CARDS
      ====================================================================== */}
      <section
        aria-label="Account and Risk Key Performance Indicators"
        className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3"
      >
        {/* 1. Bal / Eq */}
        <div
          className="iea-glass-card p-4 flex flex-col justify-between min-h-[112px]"
          title={`${UI_COPY.kpis.balEq.tooltip} · ${provenanceLabel}`}
        >
          <div className="flex items-center justify-between text-xs text-[#B6C5E0]">
            <span className="font-medium">{UI_COPY.kpis.balEq.label}</span>
            <span
              className={`font-mono text-[10px] px-2 py-0.5 rounded-full border ${
                dash.provenance.stale
                  ? "text-[#FBBF24] bg-[#FBBF24]/15 border-[#FBBF24]/35"
                  : "text-[#B0F648] bg-[#B0F648]/14 border-[#B0F648]/30"
              }`}
            >
              {dash.connected
                ? `Lev 1:${effectiveStatus.mt5.account.leverage}`
                : "Waiting"}
            </span>
          </div>
          <div className="text-[clamp(1.35rem,1.8vw,1.75rem)] font-light font-mono tabular-nums tracking-tight text-[#F4F7FF] mt-2">
            {kpis.equity !== null
              ? `$${kpis.equity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
              : "—"}
          </div>
          <div className="text-[11px] font-mono tabular-nums text-[#8496B8] mt-1.5 flex items-center justify-between">
            <span>
              {kpis.balance !== null
                ? `Bal $${kpis.balance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                : provenanceLabel}
            </span>
            {kpis.floatingPnl !== null && (
              <span
                className={
                  kpis.floatingPnl >= 0 ? "text-[#B0F648] font-semibold" : "text-[#FF5A6E] font-semibold"
                }
              >
                {kpis.floatingPnl >= 0 ? "+" : ""}${kpis.floatingPnl.toFixed(2)}
              </span>
            )}
          </div>
        </div>

        {/* 2. Today P&L (Primary Accent Highlight) */}
        <div
          className="iea-glass-card-lime p-4 flex flex-col justify-between min-h-[112px]"
          title={`${UI_COPY.kpis.todayPnl.tooltip} · ${provenanceLabel}`}
        >
          <div className="flex items-center justify-between text-xs text-[#C2F076]">
            <span className="font-medium">{UI_COPY.kpis.todayPnl.label}</span>
            {(kpis.todayPnlUsd ?? 0) >= 0 ? (
              <TrendingUp className="w-4 h-4 text-[#B0F648]" />
            ) : (
              <TrendingDown className="w-4 h-4 text-[#FF5A6E]" />
            )}
          </div>
          <div
            className={`text-[clamp(1.35rem,1.8vw,1.75rem)] font-light font-mono tabular-nums tracking-tight mt-2 ${
              kpis.todayPnlUsd === null
                ? "text-[#8496B8]"
                : kpis.todayPnlUsd >= 0
                ? "text-[#B0F648]"
                : "text-[#FF5A6E]"
            }`}
          >
            {kpis.todayPnlUsd !== null ? (
              <>
                {kpis.todayPnlUsd >= 0 ? "+" : ""}${kpis.todayPnlUsd.toFixed(2)}{" "}
                {kpis.todayPnlR !== null && (
                  <span className="text-xs font-semibold">
                    ({kpis.todayPnlR >= 0 ? "+" : ""}
                    {kpis.todayPnlR.toFixed(2)}R)
                  </span>
                )}
              </>
            ) : (
              "—"
            )}
          </div>
          <div className="text-[11px] font-mono tabular-nums text-[#B6C5E0] mt-1.5">
            {kpis.balance !== null
              ? `1R = $${(kpis.balance * 0.005).toFixed(2)} · ${provenanceLabel}`
              : provenanceLabel}
          </div>
        </div>

        {/* 3. Daily Loss */}
        <div
          className="iea-glass-card p-4 flex flex-col justify-between min-h-[112px]"
          title={UI_COPY.kpis.dailyLoss.tooltip}
        >
          <div className="flex items-center justify-between text-xs text-[#B6C5E0]">
            <span className="font-medium">{UI_COPY.kpis.dailyLoss.label}</span>
            <span className="font-mono tabular-nums text-[11px] text-[#F4F7FF]">
              {kpis.dailyLossUsedPct.toFixed(2)}% / {kpis.dailyLossLimitPct.toFixed(1)}%
            </span>
          </div>
          <div className="text-[clamp(1.35rem,1.8vw,1.75rem)] font-light font-mono tabular-nums tracking-tight text-[#F4F7FF] mt-2">
            ${kpis.dailyLossUsedUsd.toFixed(0)}{" "}
            <span className="text-xs text-[#8496B8] font-normal">
              / ${kpis.dailyLossLimitUsd.toFixed(0)}
            </span>
          </div>
          <div className="w-full h-1.5 bg-[#091426]/80 rounded-full overflow-hidden mt-2 border border-[rgba(186,214,255,0.12)]">
            <div
              className="h-full bg-[#B0F648] rounded-full shadow-[0_0_8px_#B0F648]"
              style={{
                width: `${Math.min(100, (kpis.dailyLossUsedPct / kpis.dailyLossLimitPct) * 100)}%`,
              }}
            />
          </div>
        </div>

        {/* 4. DD vs Cap */}
        <div
          className="iea-glass-card p-4 flex flex-col justify-between min-h-[112px]"
          title={UI_COPY.kpis.ddCap.tooltip}
        >
          <div className="flex items-center justify-between text-xs text-[#B6C5E0]">
            <span className="font-medium">{UI_COPY.kpis.ddCap.label}</span>
            <span className="font-mono text-[10px] text-[#B0F648] bg-[#B0F648]/14 px-2 py-0.5 rounded-full">
              SAFE
            </span>
          </div>
          <div className="text-[clamp(1.35rem,1.8vw,1.75rem)] font-light font-mono tabular-nums tracking-tight text-[#F4F7FF] mt-2">
            {kpis.totalDrawdownUsedPct.toFixed(2)}%{" "}
            <span className="text-xs text-[#8496B8] font-normal">
              / {kpis.totalDrawdownCapPct.toFixed(1)}%
            </span>
          </div>
          <div className="w-full h-1.5 bg-[#091426]/80 rounded-full overflow-hidden mt-2 border border-[rgba(186,214,255,0.12)]">
            <div
              className="h-full bg-[#5EEAD4] rounded-full"
              style={{
                width: `${Math.min(100, (kpis.totalDrawdownUsedPct / kpis.totalDrawdownCapPct) * 100)}%`,
              }}
            />
          </div>
        </div>

        {/* 5. Open Exp (Simplified — spans 2 cols at sm so there is never an empty hole) */}
        <div
          className="iea-glass-card p-4 flex flex-col justify-between min-h-[112px] sm:col-span-2 lg:col-span-1"
          title={UI_COPY.kpis.openExp.tooltip}
        >
          <div className="flex items-center justify-between text-xs text-[#B6C5E0]">
            <span className="font-medium">{UI_COPY.kpis.openExp.label}</span>
            <span className="font-mono text-[10px] text-[#5EEAD4] bg-[#5EEAD4]/14 px-2 py-0.5 rounded-full">
              {activePositions.length} Open
            </span>
          </div>
          <div className="text-[clamp(1.35rem,1.8vw,1.75rem)] font-light font-mono tabular-nums tracking-tight text-[#F4F7FF] mt-2">
            {activePositions.length}{" "}
            <span className="text-xs text-[#8496B8] font-normal">
              Pos · {kpis.pendingOrdersCount} Ord
            </span>
          </div>
          <div className="text-[11px] font-mono tabular-nums text-[#8496B8] mt-1.5 flex items-center justify-between">
            <span>Bot {botOpenCount}</span>
            <span className="text-[#B0F648]">SL Guarded</span>
          </div>
        </div>
      </section>

      {/* =====================================================================
          ROW 3: DOMINANT FULL-WIDTH LIVE CHART (12 COLUMNS, FLUID HEIGHT)
      ====================================================================== */}
      <section
        aria-label="Live Institutional Chart"
        className="grid grid-cols-12"
      >
        <div
          className="col-span-12 flex flex-col"
          style={{ height: "clamp(480px, 56vh, 680px)" }}
        >
          <LiveTradingChart
            bundle={chartBundle}
            selectedSymbol={selectedSymbol}
            selectedTimeframe={selectedTimeframe}
            feedStatus={feedStatus}
            waitingReason={candleWaitingReason}
            onSelectSymbol={setSelectedSymbol}
            onSelectTimeframe={setSelectedTimeframe}
            onCaptureScreenshot={handleSaveScreenshot}
          />
        </div>
      </section>

      {/* =====================================================================
          ROW 4: FULL-WIDTH OPEN POSITIONS & ORDERS TABLE (STICKY HEADERS)
      ====================================================================== */}
      <section
        aria-label="Open Positions and Pending Orders"
        className="iea-glass-card p-4 md:p-5 space-y-3"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center space-x-3">
            <h2
              className="text-sm font-semibold text-[#F4F7FF]"
              title="Active MT5 positions & pending orders (Rule R9.3 Tighten-Only SL)"
            >
              Open Positions &amp; Orders ({activePositions.length})
            </h2>
            <span
              title="All open positions carry verified server-side Stop Loss protection"
              className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full bg-[#B0F648]/14 border border-[#B0F648]/35 text-[#B0F648] font-mono text-[10px] font-semibold"
            >
              <ShieldCheck className="w-3 h-3" />
              <span>SL Guarded</span>
            </span>
          </div>

          <div className="flex items-center space-x-3 text-xs">
            <span className="text-[#B6C5E0]">
              Pending Ord: <strong className="font-mono text-[#F4F7FF]">{kpis.pendingOrdersCount}</strong>
            </span>
            <button
              type="button"
              onClick={() => onNavigate("positions")}
              className="iea-pill-control px-3 py-1 text-[11px] text-[#B0F648] hover:text-[#C2F076] font-semibold"
            >
              Full View →
            </button>
          </div>
        </div>

        <div className="overflow-x-auto max-h-[340px] overflow-y-auto rounded-2xl border border-[rgba(186,214,255,0.12)]">
          <table className="w-full text-left text-xs iea-glass-table">
            <thead className="sticky top-0 z-10 backdrop-blur-md">
              <tr>
                <th className="py-2.5 pl-4 pr-3">Instrument</th>
                <th className="py-2.5 pr-3">Side / Lot</th>
                <th className="py-2.5 pr-3">Entry → Live</th>
                <th className="py-2.5 pr-3">SL</th>
                <th className="py-2.5 pr-3">TP</th>
                <th className="py-2.5 pr-3">P&amp;L (R)</th>
                <th className="py-2.5 pr-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="font-mono tabular-nums">
              {activePositions.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-[#8496B8] font-sans">
                    No open positions.
                  </td>
                </tr>
              ) : (
                activePositions.map((pos) => {
                  const symClean: ChartSymbol = pos.symbol.includes("JPY")
                    ? "USDJPY"
                    : pos.symbol.includes("BTC")
                    ? "BTCUSD"
                    : "XAUUSD";
                  const digits = symClean === "USDJPY" ? 3 : 2;
                  const contractVal =
                    symClean === "XAUUSD" ? 100 : symClean === "USDJPY" ? 650 : 1;
                  const dir = pos.direction === "SELL" ? "SELL" : "BUY";
                  const m = calculateTradeMetrics({
                    direction: dir,
                    entryPrice: pos.open_price,
                    stopLoss: pos.sl,
                    currentPrice: pos.current_price,
                    volumeLots: pos.volume,
                    contractValuePerPoint: contractVal,
                  });
                  const chip = getSymbolChipSpec(pos.symbol);

                  return (
                    <tr key={pos.ticket}>
                      <td className="py-2.5 pl-4 pr-3">
                        <div className="flex items-center space-x-2.5">
                          <span
                            className={`w-6 h-6 rounded-full text-[10px] font-extrabold inline-flex items-center justify-center shrink-0 ${chip.chipBg} ${chip.chipRing}`}
                          >
                            {chip.shortCode}
                          </span>
                          <div>
                            <button
                              type="button"
                              onClick={() => setSelectedSymbol(symClean)}
                              title={`Focus ${symClean} on chart`}
                              className="font-bold text-[#F4F7FF] hover:text-[#B0F648] transition"
                            >
                              {pos.symbol}
                            </button>
                            <div className="text-[10px] font-sans text-[#8496B8]">#{pos.ticket}</div>
                          </div>
                        </div>
                      </td>

                      <td className="py-2.5 pr-3">
                        <span
                          className={`px-2 py-0.5 rounded-full font-bold text-[10px] ${
                            dir === "BUY"
                              ? "bg-[#B0F648]/18 text-[#B0F648]"
                              : "bg-[#FF5A6E]/20 text-[#FF5A6E]"
                          }`}
                        >
                          {dir} {pos.volume.toFixed(2)}L
                        </span>
                      </td>

                      <td className="py-2.5 pr-3 text-[#B6C5E0]">
                        <span className="text-[#F4F7FF]">{pos.open_price.toFixed(digits)}</span>
                        <span className="text-[#8496B8] mx-1">→</span>
                        <span className="text-[#F4F7FF] font-semibold">
                          {pos.current_price.toFixed(digits)}
                        </span>
                      </td>

                      <td className="py-2.5 pr-3 text-[#FF7A8A] font-semibold">
                        {pos.sl > 0 ? pos.sl.toFixed(digits) : "—"}
                      </td>

                      <td className="py-2.5 pr-3 text-[#B0F648] font-semibold">
                        {pos.tp > 0 ? pos.tp.toFixed(digits) : "—"}
                      </td>

                      <td
                        className={`py-2.5 pr-3 font-bold ${
                          pos.profit >= 0 ? "text-[#B0F648]" : "text-[#FF5A6E]"
                        }`}
                      >
                        {pos.profit >= 0 ? "+" : ""}${pos.profit.toFixed(2)}{" "}
                        <span className="text-[11px] opacity-85">
                          ({m.floatingR >= 0 ? "+" : ""}
                          {m.floatingR.toFixed(2)}R)
                        </span>
                      </td>

                      <td className="py-2.5 pr-4 text-right font-sans">
                        {readOnlyMobile ? (
                          <span className="text-[10px] text-[#8496B8] font-mono">READ-ONLY</span>
                        ) : (
                          <div className="inline-flex flex-wrap items-center justify-end gap-1.5">
                            <button
                              type="button"
                              onClick={() => handlePartialClose50(pos)}
                              aria-label={`Partial close 50% of ticket ${pos.ticket}`}
                              title="Partial Close 50% volume"
                              className="px-2.5 py-1 rounded-full bg-[#192F5A] hover:bg-[#234078] border border-[rgba(186,214,255,0.18)] text-[#F4F7FF] text-[10px] font-semibold inline-flex items-center space-x-1 transition"
                            >
                              <Scissors className="w-2.5 h-2.5 text-[#5EEAD4]" />
                              <span>50%</span>
                            </button>

                            <button
                              type="button"
                              onClick={() => handleMoveToBreakEven(pos)}
                              aria-label={`Move stop loss to break-even for ticket ${pos.ticket}`}
                              title="Lock Stop Loss at Break-Even+"
                              className="px-2.5 py-1 rounded-full bg-[#5EEAD4]/15 hover:bg-[#5EEAD4]/25 border border-[#5EEAD4]/40 text-[#5EEAD4] text-[10px] font-semibold transition"
                            >
                              BE+
                            </button>

                            <button
                              type="button"
                              onClick={() => openTightenSlModal(pos)}
                              aria-label={`Tighten stop loss for ticket ${pos.ticket}`}
                              title="Tighten Stop Loss (Rule R9.3)"
                              className="px-2.5 py-1 rounded-full bg-[#B0F648]/16 hover:bg-[#B0F648]/28 border border-[#B0F648]/45 text-[#C2F076] text-[10px] font-semibold transition"
                            >
                              SL+
                            </button>

                            <button
                              type="button"
                              disabled
                              aria-disabled="true"
                              title="Hard Safety Rule R9.3: Widening or removing Stop Loss is permanently disabled"
                              className="px-2.5 py-1 rounded-full bg-[#0A152B]/60 border border-[rgba(186,214,255,0.1)] text-[#8496B8] text-[10px] font-medium cursor-not-allowed opacity-60 inline-flex items-center space-x-1"
                            >
                              <Lock className="w-2.5 h-2.5" />
                              <span>Widen</span>
                            </button>

                            <button
                              type="button"
                              onClick={() => handleCloseSinglePosition(pos)}
                              aria-label={`Close position ticket ${pos.ticket}`}
                              title="Close position at market"
                              className="px-2.5 py-1 rounded-full bg-[#FF5A6E]/90 hover:bg-[#FF5A6E] text-white text-[10px] font-bold transition"
                            >
                              Close
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* =====================================================================
          CONFIRMATION MODAL (Start Demo / Stop / Close All / Mobile Pause)
      ====================================================================== */}
      {confirmModal && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="two-step-confirm-title"
          className="fixed inset-0 z-50 bg-[#050C1A]/80 backdrop-blur-md flex items-center justify-center p-4"
        >
          <div
            className={`iea-glass-card p-5 max-w-sm w-full space-y-3 shadow-2xl ${
              confirmModal.type === "START_DEMO"
                ? "border-[#B0F648]/55"
                : confirmModal.type === "STOP"
                ? "border-[#FBBF24]/55"
                : "border-[#FF5A6E]/60"
            }`}
          >
            <div
              className={`flex items-center space-x-2 ${
                confirmModal.type === "START_DEMO"
                  ? "text-[#B0F648]"
                  : confirmModal.type === "STOP"
                  ? "text-[#FBBF24]"
                  : "text-[#FF5A6E]"
              }`}
            >
              {confirmModal.type === "START_DEMO" ? (
                <Play className="w-5 h-5 shrink-0" />
              ) : (
                <ShieldAlert className="w-5 h-5 shrink-0" />
              )}
              <h3 id="two-step-confirm-title" className="text-sm font-bold text-[#F4F7FF]">
                {confirmModal.type === "START_DEMO"
                  ? `Start engine in ${topBar.operatingMode}?`
                  : confirmModal.type === "STOP"
                  ? "Stop trading engine?"
                  : confirmModal.type === "PAUSE"
                  ? `${topBar.pauseResumeBtn.label} new entries? (${confirmModal.step}/2)`
                  : `Close all bot trades? (${confirmModal.step}/2)`}
              </h3>
            </div>

            {confirmModal.type === "START_DEMO" ? (
              <p className="text-xs text-[#B6C5E0]">
                The engine will run in{" "}
                <strong className="text-[#B0F648] font-mono">{topBar.operatingMode}</strong> on DEMO{" "}
                <span className="font-mono">{dash.maskedAccount}</span> and may place DEMO orders.
                LIVE trading remains locked.
              </p>
            ) : confirmModal.type === "STOP" ? (
              <p className="text-xs text-[#B6C5E0]">
                Stop the trading engine process? Any open positions in MT5 will keep their existing
                broker SL/TP levels.
              </p>
            ) : confirmModal.step === 1 ? (
              <p className="text-xs text-[#B6C5E0]">
                {confirmModal.type === "PAUSE" ? (
                  <>
                    {topBar.pauseResumeBtn.label} automated entries on DEMO{" "}
                    <span className="font-mono">{dash.maskedAccount}</span>? Existing SL/TP stay active.
                  </>
                ) : (
                  <>
                    Close{" "}
                    <strong className="text-[#F4F7FF]">{botOpenCount} bot positions</strong> at market on
                    DEMO <span className="font-mono">{dash.maskedAccount}</span>? Positions will be
                    reconciled with MT5 before confirming.
                  </>
                )}
              </p>
            ) : (
              <div className="p-3 rounded-xl bg-[#FF5A6E]/18 border border-[#FF5A6E]/50 text-xs text-[#FFD9DF] font-semibold">
                {confirmModal.type === "PAUSE"
                  ? `Final step: Confirm ${topBar.pauseResumeBtn.label.toLowerCase()}ing entries.`
                  : `Final step: Confirm immediate market closure on ${dash.maskedAccount}.`}
              </div>
            )}

            <div className="flex items-center justify-end space-x-2 pt-1">
              <button
                type="button"
                onClick={() => setConfirmModal(null)}
                className="iea-pill-control px-4 py-1.5 text-xs text-[#F4F7FF] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#F4F7FF]"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmTwoStep}
                className={`px-4 py-1.5 rounded-full text-xs font-bold transition focus-visible:outline-none focus-visible:ring-2 ${
                  confirmModal.type === "START_DEMO"
                    ? "bg-[#B0F648] hover:bg-[#C2F076] text-[#081321] focus-visible:ring-[#B0F648]"
                    : confirmModal.type === "STOP"
                    ? "bg-[#FBBF24] hover:brightness-110 text-[#081321] focus-visible:ring-[#FBBF24]"
                    : "bg-gradient-to-r from-[#FF5A6E] to-[#E11D48] hover:brightness-110 text-white focus-visible:ring-[#FF5A6E]"
                }`}
              >
                {confirmModal.type === "START_DEMO"
                  ? `Start (${topBar.modeShort})`
                  : confirmModal.type === "STOP"
                  ? "Stop Engine"
                  : confirmModal.step === 1
                  ? "Next →"
                  : confirmModal.type === "PAUSE"
                  ? topBar.pauseResumeBtn.label
                  : "Close All"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* =====================================================================
          TIGHTEN-ONLY STOP LOSS MODIFICATION MODAL
      ====================================================================== */}
      {slModalPos && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="tighten-sl-modal-title"
          className="fixed inset-0 z-50 bg-[#050C1A]/80 backdrop-blur-md flex items-center justify-center p-4"
        >
          <div className="iea-glass-card p-5 max-w-sm w-full space-y-3 shadow-2xl">
            <div className="flex items-center justify-between">
              <h3 id="tighten-sl-modal-title" className="text-sm font-bold text-[#F4F7FF]">
                Tighten SL · #{slModalPos.ticket}
              </h3>
              <span className="px-2 py-0.5 rounded-full bg-[#B0F648]/20 text-[#B0F648] text-[10px] font-mono font-bold">
                R9.3 TIGHTEN-ONLY
              </span>
            </div>

            <div className="text-xs text-[#B6C5E0] iea-glass-tile p-2.5 font-mono flex items-center justify-between">
              <span>In: {slModalPos.open_price}</span>
              <span>Now: {slModalPos.current_price}</span>
              <span className="text-[#FF7A8A]">SL: {slModalPos.sl}</span>
            </div>

            <div className="space-y-2 text-xs">
              <label className="block">
                <span className="text-[#B6C5E0] font-semibold">
                  New SL ({slModalPos.direction === "BUY" ? `>= ${slModalPos.sl}` : `<= ${slModalPos.sl}`})
                </span>
                <input
                  type="number"
                  step="any"
                  value={proposedSlInput}
                  onChange={(e) => setProposedSlInput(e.target.value)}
                  className="w-full mt-1 bg-[#091426]/80 border border-[rgba(186,214,255,0.22)] rounded-xl px-3 py-1.5 text-[#F4F7FF] font-mono"
                />
              </label>

              <label className="block">
                <span className="text-[#B6C5E0] font-semibold">TP Target</span>
                <input
                  type="number"
                  step="any"
                  value={proposedTpInput}
                  onChange={(e) => setProposedTpInput(e.target.value)}
                  className="w-full mt-1 bg-[#091426]/80 border border-[rgba(186,214,255,0.22)] rounded-xl px-3 py-1.5 text-[#F4F7FF] font-mono"
                />
              </label>
            </div>

            {!slValidation.allowed && (
              <div className="p-2.5 rounded-xl bg-[#FF5A6E]/20 border border-[#FF5A6E]/50 text-[11px] text-[#FFD9DF]">
                {slValidation.reason}
              </div>
            )}

            <div className="flex items-center justify-end space-x-2 pt-1">
              <button
                type="button"
                onClick={() => setSlModalPos(null)}
                className="iea-pill-control px-4 py-1.5 text-xs text-[#F4F7FF]"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={!slValidation.allowed || busyAction !== null}
                onClick={handleApplyTightenSl}
                className="px-4 py-1.5 rounded-full bg-[#B0F648] hover:bg-[#C2F076] disabled:opacity-40 text-xs font-extrabold text-[#081321]"
              >
                Apply SL
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
