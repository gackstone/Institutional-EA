import React, { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Award,
  Bell,
  Bot,
  ChevronDown,
  Clock,
  DollarSign,
  Loader2,
  Lock,
  Moon,
  Pause,
  Play,
  Plug,
  Scissors,
  Search,
  Send,
  ShieldAlert,
  ShieldCheck,
  Square,
  Sun,
  TrendingDown,
  TrendingUp,
  Unplug,
  Wallet,
  Wifi,
  WifiOff,
  XCircle,
} from "lucide-react";
import { controlClient, formatControlError, IPC } from "../../services/ipc";
import {
  ControlPosition,
  ControlServiceStatus,
  ControlStatusPayload,
  ControlSymbolSpec,
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
import {
  calculateTradeMetrics,
  normalizeCanonicalSymbol,
  validateTightenOnlyStopLoss,
} from "../../utils/tradeChartMath";
import {
  deriveTopBarControlState,
  sanitizeControlError,
} from "../../utils/topBarControlState";
import { getNeutralSymbolChipSpec } from "../../styles/designTokens";
import { UI_COPY } from "../../constants/uiCopy";
import { useTheme } from "../../context/ThemeContext";
import { readVersionedState, writeVersionedState } from "../../utils/persistedState";
import { LiveTradingChart } from "../LiveTradingChart";
import { PanelErrorBoundary } from "../ErrorBoundary";
import type { EngineDrawingsFeed } from "../../utils/chartDrawingsSchema";

// One-time confirmation flag per app session for demo order-placing Start
let sessionStartDemoConfirmed = false;

type AccountKpiMode = "BALANCE" | "EQUITY";
const ACCOUNT_KPI_MODE_STORAGE_KEY = "iea_account_kpi_mode_v1";

function isValidAccountKpiMode(v: unknown): v is AccountKpiMode {
  return v === "BALANCE" || v === "EQUITY";
}

function formatCurrencyValue(value: number | null | undefined, signed = false): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "-";
  }
  const absFormatted = Math.abs(value).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  if (!signed) {
    return value < 0 ? `-$${absFormatted}` : `$${absFormatted}`;
  }
  return `${value >= 0 ? "+" : "-"}$${absFormatted}`;
}

function formatHeaderClock(now: Date): string {
  const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const day = days[now.getDay()];
  const hh = String(now.getHours()).padStart(2, "0");
  const mm = String(now.getMinutes()).padStart(2, "0");
  return `${day} ${hh}:${mm}`;
}

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
  const { theme, toggleTheme } = useTheme();
  const [selectedSymbol, setSelectedSymbol] = useState<ChartSymbol>(initialSymbol);
  const [selectedTimeframe, setSelectedTimeframe] = useState<ChartTimeframe>("M5");
  const [realCandles, setRealCandles] = useState<CandleBar[]>([]);
  const [liveQuote, setLiveQuote] = useState<ControlSymbolSpec | null>(null);
  const [candleWaitingReason, setCandleWaitingReason] = useState<string | undefined>(undefined);
  const [drawingsFeed, setDrawingsFeed] = useState<EngineDrawingsFeed | null>(null);
  const [drawingsError, setDrawingsError] = useState<string | null>(null);
  const [headerClockText, setHeaderClockText] = useState<string>(() =>
    formatHeaderClock(new Date())
  );
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [connectingMt5, setConnectingMt5] = useState<boolean>(false);
  const [mt5PickerTerminals, setMt5PickerTerminals] = useState<MT5TerminalInfo[] | null>(null);

  // Account KPI mode & quick search
  const [accountKpiMode, setAccountKpiMode] = useState<AccountKpiMode>(
    () =>
      readVersionedState<AccountKpiMode>({
        key: ACCOUNT_KPI_MODE_STORAGE_KEY,
        defaultValue: "BALANCE",
        validate: isValidAccountKpiMode,
        migrate: (legacy) => (isValidAccountKpiMode(legacy) ? legacy : null),
      }).value
  );
  const [isSearchOpen, setIsSearchOpen] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>("");

  const handleSelectAccountKpiMode = (nextMode: AccountKpiMode) => {
    setAccountKpiMode(nextMode);
    writeVersionedState(ACCOUNT_KPI_MODE_STORAGE_KEY, nextMode);
  };

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

  // Lightweight clock pill updater ("Tue 17:38")
  useEffect(() => {
    const timer = setInterval(() => {
      setHeaderClockText(formatHeaderClock(new Date()));
    }, 10000);
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

  // Fetch engine drawings feed (/api/chart/drawings) on load and live refresh
  useEffect(() => {
    let cancelled = false;
    const loadDrawings = async () => {
      try {
        const feed = await controlClient.getChartDrawings(selectedSymbol, selectedTimeframe, 160);
        if (!cancelled) {
          setDrawingsFeed(feed);
          setDrawingsError(null);
        }
      } catch (err: any) {
        if (!cancelled) {
          setDrawingsError(sanitizeControlError(err, "Unable to fetch engine drawings"));
        }
      }
    };
    loadDrawings();
    const timer = setInterval(loadDrawings, 5000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [selectedSymbol, selectedTimeframe, serviceStatus?.status, status?.mt5?.last_sync_at]);

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

  const syncedTimeLabel = dash.provenance.connected
    ? `Synced ${
        dash.provenance.updatedAt
          ? new Date(dash.provenance.updatedAt).toTimeString().slice(0, 5)
          : new Date().toTimeString().slice(0, 5)
      }`
    : "Waiting for MT5";

  // Derive 4 KPI Metrics: Account (Balance/Equity), Win Rate, Today P/L, Total Profits
  const kpiSummary = useMemo(() => {
    const closedTrades = (dash.recentTrades || []).filter(
      (t) =>
        String(t.status || "")
          .toUpperCase()
          .includes("CLOSED") || Boolean(t.closed_at)
    );
    const wins = closedTrades.filter((t) => Number(t.profit || 0) > 0);
    const losses = closedTrades.filter((t) => Number(t.profit || 0) < 0);
    const realizedNetPnl = closedTrades.reduce((sum, t) => {
      const p = Number(t.profit || 0);
      return Number.isFinite(p) ? sum + p : sum;
    }, 0);

    const todayUtcDate = new Date().toISOString().slice(0, 10);
    const closedToday = closedTrades.filter(
      (t) => t.closed_at && String(t.closed_at).slice(0, 10) === todayUtcDate
    );
    const closedPnlToday = closedToday.reduce((sum, t) => {
      const p = Number(t.profit || 0);
      return Number.isFinite(p) ? sum + p : sum;
    }, 0);
    const todayTradesCount = closedToday.length + activePositions.length;

    const todayPnlVal =
      kpis.todayPnlUsd !== null && Number.isFinite(kpis.todayPnlUsd)
        ? kpis.todayPnlUsd
        : closedToday.length > 0
        ? Number(closedPnlToday.toFixed(2))
        : dash.connected
        ? 0
        : null;

    const totalProfitsVal =
      closedTrades.length > 0
        ? Number(realizedNetPnl.toFixed(2))
        : dash.connected
        ? kpis.todayPnlUsd ?? kpis.floatingPnl ?? 0
        : null;

    const netPnlValue =
      closedTrades.length > 0
        ? Number(realizedNetPnl.toFixed(2))
        : kpis.todayPnlUsd !== null && Number.isFinite(kpis.todayPnlUsd)
        ? kpis.todayPnlUsd
        : kpis.floatingPnl;

    const winRatePct =
      closedTrades.length > 0
        ? Number(((wins.length / closedTrades.length) * 100).toFixed(1))
        : dash.connected
        ? 0
        : null;

    return {
      closedCount: closedTrades.length,
      winsCount: wins.length,
      lossesCount: losses.length,
      todayTradesCount,
      todayPnlVal,
      totalProfitsVal,
      netPnlValue,
      winRatePct,
    };
  }, [dash.recentTrades, dash.connected, activePositions.length, kpis.todayPnlUsd, kpis.floatingPnl]);

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
    <div className="max-w-[1920px] mx-auto space-y-[18px] text-iea-textPrimary">
      {/* Compact Connection / Stale / Emergency Banner States */}
      {feedStatus === "DISCONNECTED" && (
        <div
          role="alert"
          title="Local Python Control Service unreachable on 127.0.0.1:8765"
          className="flex items-center justify-between px-4 py-2.5 rounded-[14px] bg-iea-dangerSoft border border-iea-dangerBorder text-xs text-iea-textPrimary"
        >
          <div className="flex items-center space-x-2">
            <WifiOff className="w-4 h-4 text-iea-danger shrink-0" />
            <span>
              <strong>Svc Offline (127.0.0.1:8765)</strong> · Cached DEMO
            </span>
          </div>
          <button
            type="button"
            onClick={() => onRefresh()}
            className="px-3 py-1 rounded-full bg-iea-danger hover:opacity-90 text-white font-semibold transition"
          >
            Reconnect
          </button>
        </div>
      )}

      {feedStatus === "STALE" && (
        <div
          role="alert"
          title="Last MT5 sync heartbeat exceeded 15 seconds"
          className="flex items-center justify-between px-4 py-2.5 rounded-[14px] bg-iea-warningSoft border border-iea-warningBorder text-xs text-iea-textPrimary"
        >
          <div className="flex items-center space-x-2">
            <AlertTriangle className="w-4 h-4 text-iea-warning shrink-0" />
            <strong>Stale Sync (&gt;15s)</strong>
          </div>
          <button
            type="button"
            onClick={() => onRefresh()}
            className="px-3 py-1 rounded-full bg-iea-warning text-iea-canvas font-semibold transition"
          >
            Sync
          </button>
        </div>
      )}

      {eng.stop_flag_active && (
        <div
          role="alert"
          title="Emergency STOP.flag kill switch is active; all new entries are blocked"
          className="flex items-center justify-between px-4 py-2.5 rounded-[14px] bg-iea-dangerSoft border border-iea-dangerBorder text-xs"
        >
          <div className="flex items-center space-x-2">
            <ShieldAlert className="w-4 h-4 text-iea-danger shrink-0" />
            <span className="font-bold text-iea-danger">STOP.flag ACTIVE · Entries Blocked</span>
          </div>
          <button
            type="button"
            onClick={() =>
              executeControlAction("Clear Stop", () => controlClient.clearEmergencyStop(true))
            }
            className="px-3 py-1 rounded-full bg-iea-profit hover:opacity-90 text-white font-bold transition"
          >
            Clear Stop
          </button>
        </div>
      )}

      {topBar.engineState === "ERROR" && eng.last_execution_error && (
        <div
          role="alert"
          className="flex items-center justify-between px-4 py-2.5 rounded-[14px] bg-iea-dangerSoft border border-iea-dangerBorder text-xs"
        >
          <div className="flex items-center space-x-2 min-w-0">
            <AlertTriangle className="w-4 h-4 text-iea-danger shrink-0" />
            <span className="font-semibold text-iea-danger truncate">
              {eng.last_execution_error}
            </span>
          </div>
          {topBar.startBtn.enabled && (
            <button
              type="button"
              onClick={handleStartEngineClick}
              className="ml-3 px-3 py-1 rounded-full bg-iea-accent hover:bg-iea-accentHover text-white font-bold shrink-0 transition"
            >
              Retry Start
            </button>
          )}
        </div>
      )}

      {/* =====================================================================
          ROW 1: BM FOREX HUB SLIM TOP HEADER BAR (Bottom Border, Search Left,
          Telemetry + Controls Center, Clock Pill + Rounded-Square Icon Buttons Right)
      ====================================================================== */}
      <PanelErrorBoundary panelName="Top Control Bar">
        <section
          aria-label="Terminal Top Status Bar"
          className="relative flex flex-wrap xl:flex-nowrap items-center justify-between gap-2 pb-3.5 border-b border-iea-borderSubtle"
        >
          {/* Left: Rounded Search Icon Button + Status Pills */}
          <div className="flex flex-wrap items-center gap-1.5 text-[11px] min-w-0">
            <button
              type="button"
              onClick={() => setIsSearchOpen((prev) => !prev)}
              aria-label="Search instruments and terminal actions"
              title="Search instruments (XAUUSD, BTCUSD, USDJPY)"
              className="iea-header-icon-btn shrink-0"
            >
              <Search className="w-4 h-4" />
            </button>

            {isSearchOpen && (
              <div className="inline-flex items-center bg-iea-card border border-iea-borderDefault rounded-[10px] px-2.5 h-9">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => {
                    const next = e.target.value;
                    setSearchQuery(next);
                    const upper = next.trim().toUpperCase();
                    if (upper === "XAU" || upper === "XAUUSD" || upper === "GOLD") {
                      setSelectedSymbol("XAUUSD");
                    } else if (upper === "BTC" || upper === "BTCUSD") {
                      setSelectedSymbol("BTCUSD");
                    } else if (upper === "JPY" || upper === "USDJPY") {
                      setSelectedSymbol("USDJPY");
                    }
                  }}
                  placeholder="Jump symbol..."
                  aria-label="Quick jump chart symbol"
                  className="bg-transparent text-xs text-iea-textPrimary placeholder:text-iea-textMuted focus:outline-none w-24 font-mono"
                />
              </div>
            )}

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
                <Wifi className="w-3 h-3 text-iea-profit shrink-0" />
              ) : (
                <WifiOff className="w-3 h-3 text-iea-danger shrink-0" />
              )}
              <span className="font-medium text-iea-textPrimary">MT5</span>
              <span
                className={`font-mono font-bold ${
                  topBar.mt5Connected ? "text-iea-profit" : "text-iea-textMuted"
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
                  ? "bg-iea-profitSoft border-iea-profitBorder text-iea-profit"
                  : topBar.engineChipTone === "amber"
                  ? "bg-iea-warningSoft border-iea-warningBorder text-iea-warning"
                  : topBar.engineChipTone === "red"
                  ? "bg-iea-dangerSoft border-iea-dangerBorder text-iea-danger"
                  : "bg-iea-card border-iea-borderSubtle text-iea-textSecondary"
              }`}
            >
              <span
                className={`w-2 h-2 rounded-full shrink-0 ${
                  topBar.engineChipTone === "lime"
                    ? "bg-iea-profit"
                    : topBar.engineChipTone === "amber"
                    ? "bg-iea-warning"
                    : topBar.engineChipTone === "red"
                    ? "bg-iea-danger"
                    : "bg-iea-textMuted"
                }`}
              />
              <span>{topBar.engineStateLabel}</span>
              <span className="opacity-60">·</span>
              <span className="text-iea-textPrimary">{topBar.modeShort}</span>
            </div>

            {/* Hard Safety Lock Badge */}
            <div
              data-testid="demo-lock-badge"
              title={UI_COPY.brand.demoLockTooltip}
              className="hidden 2xl:inline-flex items-center space-x-1 px-2.5 py-1 rounded-full bg-iea-accentSoft border border-iea-accentBorder text-iea-accent font-mono text-[11px] font-bold whitespace-nowrap"
            >
              <Lock className="w-3 h-3 text-iea-accent shrink-0" />
              <span>{UI_COPY.brand.demoLockShort}</span>
            </div>

            {/* Control Service Status Pill + Reconnect */}
            {serviceStatus && (
              <div
                data-testid="control-service-status-pill"
                title={`Control Service on ${serviceStatus.baseUrl}${
                  serviceStatus.lastError ? ` · ${serviceStatus.lastError}` : ""
                }`}
                className="iea-pill-control inline-flex items-center space-x-1.5 px-2.5 py-1 font-mono text-[11px] whitespace-nowrap"
              >
                <span
                  className={`w-2 h-2 rounded-full shrink-0 ${
                    serviceStatus.status === "ONLINE"
                      ? "bg-iea-profit"
                      : serviceStatus.status === "STARTING"
                      ? "bg-iea-warning"
                      : "bg-iea-danger"
                  }`}
                />
                <span className="text-iea-textSecondary">SVC</span>
                <span
                  className={`font-bold ${
                    serviceStatus.status === "ONLINE"
                      ? "text-iea-profit"
                      : serviceStatus.status === "STARTING"
                      ? "text-iea-warning"
                      : "text-iea-danger"
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
                    className="ml-1 px-2 py-0.5 rounded-full bg-iea-accent text-white font-bold text-[10px] hover:bg-iea-accentHover"
                  >
                    Reconnect
                  </button>
                )}
              </div>
            )}

            {/* ZMQ Bridge Ports 5555 / 5556 (Real TCP Probe Status) */}
            <div
              title={`ZMQ/TCP Bridge Sockets: Port 5555 (${
                effectiveStatus.mt5.zmq_bridge?.port_5555 ? "LISTENING" : "IDLE"
              }) & Port 5556 (${
                effectiveStatus.mt5.zmq_bridge?.port_5556 ? "LISTENING" : "IDLE"
              })`}
              className="iea-pill-control hidden 2xl:inline-flex items-center space-x-1.5 px-2.5 py-1 font-mono text-[11px] whitespace-nowrap"
            >
              <span
                className={`w-2 h-2 rounded-full shrink-0 ${
                  effectiveStatus.mt5.zmq_bridge?.port_5555
                    ? "bg-iea-profit"
                    : "bg-iea-textMuted"
                }`}
              />
              <span className="text-iea-textSecondary">ZMQ</span>
              <span
                className={`font-bold ${
                  effectiveStatus.mt5.zmq_bridge?.port_5555
                    ? "text-iea-profit"
                    : "text-iea-textMuted"
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
              className="iea-pill-control hidden 2xl:inline-flex items-center space-x-1.5 px-2.5 py-1 text-[11px] text-iea-textPrimary whitespace-nowrap"
            >
              <Send className="w-3 h-3 text-iea-accent shrink-0" />
              <span className="text-iea-profit font-semibold">TG Ready</span>
            </button>
          </div>

          {/* Right: Engine & MT5 Controls + Clock Pill ("Tue 17:38") + Rounded-Square Icon Buttons (Bot, Notifications, Theme Toggle) */}
          <div
            aria-label="Engine and MT5 Controls"
            className="flex flex-wrap items-center gap-1.5 shrink-0"
          >
            {/* 1. Connect MT5 (or Connected + Disconnect) */}
            {!readOnlyMobile && (
              <div className="relative inline-flex items-center">
                {topBar.connectBtn.showDisconnect ? (
                  <div className="inline-flex items-center rounded-[10px] bg-iea-card border border-iea-borderDefault text-xs overflow-hidden h-9">
                    <span
                      data-testid="btn-connect-mt5-connected"
                      title={topBar.connectBtn.tooltip}
                      className="px-2.5 py-1 text-iea-profit font-semibold inline-flex items-center space-x-1 whitespace-nowrap"
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
                      className="px-2.5 h-full border-l border-iea-borderSubtle text-iea-textSecondary hover:text-iea-danger hover:bg-iea-dangerSoft disabled:opacity-40 disabled:cursor-not-allowed inline-flex items-center space-x-1 transition"
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
                    className="h-9 px-3 rounded-[10px] bg-iea-accentSoft hover:bg-iea-accent/25 border border-iea-accentBorder disabled:opacity-40 disabled:cursor-not-allowed text-iea-accent text-xs font-semibold inline-flex items-center space-x-1.5 whitespace-nowrap transition"
                  >
                    {topBar.mt5Syncing ||
                    busyAction === "Connect MT5" ||
                    busyAction === "Scan MT5" ? (
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
                    className="absolute right-0 top-full mt-2 z-50 w-72 iea-card p-2 shadow-pop border border-iea-accentBorder space-y-1"
                  >
                    <div className="flex items-center justify-between px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-iea-textMuted">
                      <span>Select MT5 Terminal ({mt5PickerTerminals.length})</span>
                      <button
                        type="button"
                        onClick={() => setMt5PickerTerminals(null)}
                        className="text-iea-textSecondary hover:text-iea-textPrimary"
                      >
                        Close
                      </button>
                    </div>
                    {mt5PickerTerminals.map((t) => (
                      <button
                        key={t.executablePath}
                        type="button"
                        onClick={() => connectToTerminalPath(t.executablePath)}
                        className="w-full text-left px-2.5 py-1.5 rounded-xl hover:bg-iea-accentSoft text-xs transition flex items-center justify-between gap-2"
                      >
                        <div className="min-w-0">
                          <div className="font-semibold text-iea-textPrimary truncate">
                            {t.name}
                          </div>
                          <div className="text-[10px] font-mono text-iea-textMuted truncate">
                            {t.executablePath}
                          </div>
                        </div>
                        {t.isRunning && (
                          <span className="px-1.5 py-0.5 rounded-full bg-iea-profitSoft text-iea-profit text-[9px] font-mono font-bold shrink-0">
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
              <div
                onClick={() => {
                  if (!topBar.startBtn.enabled && busyAction === null) {
                    onActionMessage(`Start: ${topBar.startBtn.tooltip}`, true);
                  }
                }}
                className="inline-flex"
              >
                <button
                  type="button"
                  data-testid="btn-start-engine"
                  disabled={!topBar.startBtn.enabled}
                  onClick={handleStartEngineClick}
                  aria-label="Start trading engine"
                  title={topBar.startBtn.tooltip}
                  className="h-9 px-3.5 rounded-[10px] bg-iea-accent hover:bg-iea-accentHover disabled:bg-iea-card disabled:text-iea-textMuted disabled:border disabled:border-iea-borderSubtle disabled:cursor-not-allowed text-white text-xs font-bold inline-flex items-center space-x-1.5 whitespace-nowrap transition"
                >
                  {busyAction === "Start" || topBar.engineState === "STARTING" ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" />
                  ) : (
                    <Play className="w-3.5 h-3.5 shrink-0 fill-current" />
                  )}
                  <span>{topBar.startBtn.label}</span>
                </button>
              </div>
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
              className={`h-9 px-3 rounded-[10px] border disabled:opacity-40 disabled:cursor-not-allowed text-xs font-semibold inline-flex items-center space-x-1.5 whitespace-nowrap transition ${
                topBar.pauseResumeBtn.tone === "lime"
                  ? "bg-iea-profitSoft hover:bg-iea-profit/25 border-iea-profitBorder text-iea-profit"
                  : "bg-iea-warningSoft hover:bg-iea-warning/25 border-iea-warningBorder text-iea-warning"
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
                className="h-9 px-3 rounded-[10px] bg-iea-dangerSoft hover:bg-iea-danger/25 border border-iea-dangerBorder disabled:opacity-40 disabled:cursor-not-allowed text-iea-danger text-xs font-semibold inline-flex items-center space-x-1.5 whitespace-nowrap transition"
              >
                {busyAction === "Stop" ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0 text-iea-danger" />
                ) : (
                  <Square className="w-3.5 h-3.5 shrink-0 text-iea-danger" />
                )}
                <span>{topBar.stopBtn.label}</span>
              </button>
            )}

            {/* 5. Close All */}
            {!readOnlyMobile && (
              <button
                type="button"
                data-testid="btn-close-all"
                disabled={!topBar.closeAllBtn.enabled}
                onClick={() => setConfirmModal({ type: "CLOSE_ALL", step: 1 })}
                aria-label="Close all bot-owned positions (two-step confirmation)"
                title={topBar.closeAllBtn.tooltip}
                className="h-9 px-3 rounded-[10px] bg-iea-danger hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-bold inline-flex items-center space-x-1.5 whitespace-nowrap transition"
              >
                {busyAction === "Close All" ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" />
                ) : (
                  <XCircle className="w-3.5 h-3.5 shrink-0" />
                )}
                <span>{topBar.closeAllBtn.label}</span>
              </button>
            )}

            {/* Divider before BM Forex Hub Clock Pill & Rounded-Square Icon Buttons */}
            <div className="h-5 w-px bg-iea-borderSubtle mx-0.5 hidden sm:block" />

            {/* Clock Pill (icon + "Tue 17:38") */}
            <div
              title="Live Terminal Clock"
              className="h-9 px-3 rounded-[10px] bg-iea-card border border-iea-borderSubtle inline-flex items-center space-x-2 text-xs whitespace-nowrap"
            >
              <Clock className="w-3.5 h-3.5 text-iea-accent shrink-0" />
              <span
                className="font-mono text-iea-textPrimary tabular-nums font-medium"
                data-testid="utc-clock"
              >
                {headerClockText}
              </span>
            </div>

            {/* Rounded-Square Icon Button 1: Bot */}
            <button
              type="button"
              onClick={() => onNavigate("operations")}
              aria-label="Bot Engine & Operations Centre"
              title={`Bot Engine: ${topBar.engineStateLabel} (${topBar.operatingMode}) — Open Operations`}
              className={`iea-header-icon-btn relative ${
                topBar.engineState === "RUNNING"
                  ? "text-iea-accent border-iea-accentBorder bg-iea-accentSoft"
                  : ""
              }`}
            >
              <Bot className="w-4 h-4" />
              {topBar.engineState === "RUNNING" && (
                <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 rounded-full bg-iea-profit" />
              )}
            </button>

            {/* Rounded-Square Icon Button 2: Notifications */}
            <button
              type="button"
              onClick={() => onNavigate("alerts")}
              aria-label="Open Alert & Notification Centre"
              title="Notifications & Alert Centre"
              className="iea-header-icon-btn relative"
            >
              <Bell className="w-4 h-4" />
              {activePositions.length > 0 && (
                <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 rounded-full bg-iea-accent" />
              )}
            </button>

            {/* Rounded-Square Icon Button 3: Theme Toggle */}
            <button
              type="button"
              onClick={toggleTheme}
              aria-label="Toggle color theme"
              title={`Theme: ${theme.toUpperCase()} (click to switch)`}
              className="iea-header-icon-btn"
            >
              <span className="inline-flex items-center justify-center transition-transform duration-200">
                {theme === "dark" ? (
                  <Moon className="w-4 h-4 transition-opacity duration-200" />
                ) : (
                  <Sun className="w-4 h-4 transition-opacity duration-200" />
                )}
              </span>
            </button>
          </div>
        </section>
      </PanelErrorBoundary>

      {/* =====================================================================
          ROW 2: 4 EQUAL KPI CARDS IN A RESPONSIVE GRID
          (Account [Balance | Equity], Win Rate, Today P/L, Total Profits)
      ====================================================================== */}
      <PanelErrorBoundary panelName="KPI Summary">
        <section
          aria-label="Account and Risk Key Performance Indicators"
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-[18px]"
        >
          {/* KPI 1: ACCOUNT (Balance / Equity Switch) */}
          <div
            data-testid="kpi-card-account"
            className="iea-card p-5 flex flex-col justify-between"
            title={`Live MT5 Account ${accountKpiMode === "BALANCE" ? "Balance" : "Equity"} · ${syncedTimeLabel}`}
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                <span className="iea-label-caps">ACCOUNT</span>
                <div
                  role="tablist"
                  aria-label="Toggle Account Balance or Equity"
                  className="inline-flex items-center p-0.5 rounded-[8px] bg-iea-inset border border-iea-borderSubtle text-[10px]"
                >
                  {(["BALANCE", "EQUITY"] as const).map((m) => {
                    const active = accountKpiMode === m;
                    return (
                      <button
                        key={m}
                        type="button"
                        role="tab"
                        aria-selected={active}
                        data-testid={`account-kpi-toggle-${m.toLowerCase()}`}
                        onClick={() => handleSelectAccountKpiMode(m)}
                        className={`px-2 py-0.5 rounded-[6px] font-semibold transition ${
                          active
                            ? "bg-iea-accent text-white"
                            : "text-iea-textMuted hover:text-iea-textPrimary"
                        }`}
                      >
                        {m === "BALANCE" ? "Balance" : "Equity"}
                      </button>
                    );
                  })}
                </div>
              </div>
              <div className="w-8 h-8 rounded-[10px] bg-iea-accentSoft border border-iea-accentBorder text-iea-accent flex items-center justify-center shrink-0">
                <Wallet className="w-4 h-4" />
              </div>
            </div>

            <div
              data-testid="kpi-account-primary-value"
              className="text-2xl md:text-[26px] font-bold font-mono tabular-nums tracking-tight text-iea-textPrimary mt-3"
            >
              {accountKpiMode === "BALANCE"
                ? formatCurrencyValue(kpis.balance, false)
                : formatCurrencyValue(kpis.equity, false)}
            </div>

            <div className="h-px bg-iea-borderSubtle my-3.5" />

            <div className="flex items-center justify-between font-mono text-[11px] tabular-nums">
              <span
                data-testid="kpi-account-secondary-caption"
                className="text-iea-textSecondary truncate"
              >
                {accountKpiMode === "BALANCE"
                  ? `Equity: ${formatCurrencyValue(kpis.equity, false)}`
                  : `Balance: ${formatCurrencyValue(kpis.balance, false)}`}
              </span>
              <span className="px-2 py-0.5 rounded-[6px] bg-iea-accentSoft text-iea-accent text-[10px] font-bold uppercase tracking-wider shrink-0">
                {accountKpiMode}
              </span>
            </div>
          </div>

          {/* KPI 2: WIN RATE */}
          <div
            data-testid="kpi-card-win-rate"
            className="iea-card p-5 flex flex-col justify-between"
            title="Closed trade win rate percentage"
          >
            <div className="flex items-center justify-between">
              <span className="iea-label-caps">WIN RATE</span>
              <div className="w-8 h-8 rounded-[10px] bg-iea-accentSoft border border-iea-accentBorder text-iea-accent flex items-center justify-center">
                <Award className="w-4 h-4" />
              </div>
            </div>

            <div className="text-2xl md:text-[26px] font-bold font-mono tabular-nums tracking-tight text-iea-textPrimary mt-3">
              {kpiSummary.winRatePct !== null && Number.isFinite(kpiSummary.winRatePct)
                ? `${kpiSummary.winRatePct.toFixed(1)}%`
                : "-"}
            </div>

            <div className="h-px bg-iea-borderSubtle my-3.5" />

            <div className="flex items-center justify-between font-mono text-[11px] tabular-nums">
              <span className="text-iea-textSecondary truncate">
                {kpiSummary.winsCount}W / {kpiSummary.lossesCount}L ({kpiSummary.closedCount} total)
              </span>
              <span className="px-2 py-0.5 rounded-[6px] bg-iea-accentSoft text-iea-accent text-[10px] font-bold uppercase tracking-wider shrink-0">
                {kpiSummary.winRatePct !== null && kpiSummary.winRatePct >= 55
                  ? "OPTIMAL"
                  : kpiSummary.closedCount > 0
                  ? "ACTIVE"
                  : "READY"}
              </span>
            </div>
          </div>

          {/* KPI 3: TODAY P/L */}
          <div
            data-testid="kpi-card-today-pnl"
            className="iea-card p-5 flex flex-col justify-between"
            title={`${UI_COPY.kpis.todayPnl.tooltip} · Realized + floating P/L for the current trading day`}
          >
            <div className="flex items-center justify-between">
              <span className="iea-label-caps">TODAY P/L</span>
              <div
                className={`w-8 h-8 rounded-[10px] flex items-center justify-center border ${
                  (kpiSummary.todayPnlVal ?? 0) >= 0
                    ? "bg-iea-profitSoft border-iea-profitBorder text-iea-profit"
                    : "bg-iea-dangerSoft border-iea-dangerBorder text-iea-danger"
                }`}
              >
                {(kpiSummary.todayPnlVal ?? 0) >= 0 ? (
                  <TrendingUp className="w-4 h-4" />
                ) : (
                  <TrendingDown className="w-4 h-4" />
                )}
              </div>
            </div>

            <div
              className={`text-2xl md:text-[26px] font-bold font-mono tabular-nums tracking-tight mt-3 ${
                kpiSummary.todayPnlVal === null
                  ? "text-iea-textMuted"
                  : kpiSummary.todayPnlVal >= 0
                  ? "text-iea-profit"
                  : "text-iea-danger"
              }`}
            >
              {formatCurrencyValue(kpiSummary.todayPnlVal, true)}
            </div>

            <div className="h-px bg-iea-borderSubtle my-3.5" />

            <div className="flex items-center justify-between font-mono text-[11px] tabular-nums">
              <span className="text-iea-textSecondary truncate">
                {kpiSummary.todayTradesCount}{" "}
                {kpiSummary.todayTradesCount === 1 ? "trade" : "trades"} today
              </span>
              <span
                className={`px-2 py-0.5 rounded-[6px] text-[10px] font-bold uppercase tracking-wider shrink-0 ${
                  kpiSummary.todayPnlVal === null
                    ? "bg-iea-elevated text-iea-textMuted"
                    : kpiSummary.todayPnlVal >= 0
                    ? "bg-iea-profitSoft text-iea-profit"
                    : "bg-iea-dangerSoft text-iea-danger"
                }`}
              >
                {kpiSummary.todayPnlVal === null
                  ? "IDLE"
                  : kpiSummary.todayPnlVal >= 0
                  ? "PROFIT"
                  : "LOSS"}
              </span>
            </div>
          </div>

          {/* KPI 4: TOTAL PROFITS */}
          <div
            data-testid="kpi-card-total-profits"
            className="iea-card p-5 flex flex-col justify-between"
            title="Cumulative net profit across connected account history"
          >
            <div className="flex items-center justify-between">
              <span className="iea-label-caps">TOTAL PROFITS</span>
              <div
                className={`w-8 h-8 rounded-[10px] flex items-center justify-center border ${
                  (kpiSummary.totalProfitsVal ?? 0) >= 0
                    ? "bg-iea-profitSoft border-iea-profitBorder text-iea-profit"
                    : "bg-iea-dangerSoft border-iea-dangerBorder text-iea-danger"
                }`}
              >
                <DollarSign className="w-4 h-4" />
              </div>
            </div>

            <div
              className={`text-2xl md:text-[26px] font-bold font-mono tabular-nums tracking-tight mt-3 ${
                kpiSummary.totalProfitsVal === null
                  ? "text-iea-textMuted"
                  : kpiSummary.totalProfitsVal >= 0
                  ? "text-iea-profit"
                  : "text-iea-danger"
              }`}
            >
              {formatCurrencyValue(kpiSummary.totalProfitsVal, true)}
            </div>

            <div className="h-px bg-iea-borderSubtle my-3.5" />

            <div className="flex items-center justify-between font-mono text-[11px] tabular-nums">
              <span className="text-iea-textSecondary truncate">
                {kpiSummary.closedCount} total{" "}
                {kpiSummary.closedCount === 1 ? "deal" : "deals"}
              </span>
              <span
                className={`px-2 py-0.5 rounded-[6px] text-[10px] font-bold uppercase tracking-wider shrink-0 ${
                  kpiSummary.totalProfitsVal === null
                    ? "bg-iea-elevated text-iea-textMuted"
                    : kpiSummary.totalProfitsVal >= 0
                    ? "bg-iea-profitSoft text-iea-profit"
                    : "bg-iea-dangerSoft text-iea-danger"
                }`}
              >
                {kpiSummary.totalProfitsVal === null
                  ? "IDLE"
                  : kpiSummary.totalProfitsVal >= 0
                  ? "PROFIT"
                  : "LOSS"}
              </span>
            </div>
          </div>
        </section>
      </PanelErrorBoundary>

      {/* =====================================================================
          ROW 3: FULL-WIDTH MAIN CHART CARD
      ====================================================================== */}
      <section aria-label="Main Trading Chart Card" className="w-full">
        <div className="w-full iea-card p-5 flex flex-col">
          {/* LiveTradingChart Container */}
          <PanelErrorBoundary panelName="Live Chart">
            <div
              className="w-full flex flex-col"
              style={{ height: "clamp(480px, 56vh, 680px)" }}
            >
              <LiveTradingChart
                bundle={chartBundle}
                selectedSymbol={selectedSymbol}
                selectedTimeframe={selectedTimeframe}
                feedStatus={feedStatus}
                waitingReason={candleWaitingReason}
                drawingsFeed={drawingsFeed}
                drawingsError={drawingsError}
                onSelectSymbol={setSelectedSymbol}
                onSelectTimeframe={setSelectedTimeframe}
                onCaptureScreenshot={handleSaveScreenshot}
              />
            </div>
          </PanelErrorBoundary>
        </div>
      </section>

      {/* =====================================================================
          ROW 4: FULL-WIDTH OPEN POSITIONS & ORDERS TABLE (STICKY HEADERS)
      ====================================================================== */}
      <PanelErrorBoundary panelName="Positions Table">
        <section
          aria-label="Open Positions and Pending Orders"
          className="iea-card p-5 space-y-3.5"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center space-x-3">
              <h2
                className="text-sm font-bold text-iea-textPrimary"
                title="Active MT5 positions & pending orders (Rule R9.3 Tighten-Only SL)"
              >
                Open Positions &amp; Orders ({activePositions.length})
              </h2>
              <span
                title="All open positions carry verified server-side Stop Loss protection"
                className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full bg-iea-profitSoft border border-iea-profitBorder text-iea-profit font-mono text-[10px] font-semibold"
              >
                <ShieldCheck className="w-3 h-3" />
                <span>SL Guarded</span>
              </span>
            </div>

            <div className="flex items-center space-x-3 text-xs">
              <span className="text-iea-textSecondary">
                Pending Ord:{" "}
                <strong className="font-mono text-iea-textPrimary">
                  {kpis.pendingOrdersCount}
                </strong>
              </span>
              <button
                type="button"
                onClick={() => onNavigate("positions")}
                className="iea-pill-control px-3 py-1 text-[11px] text-iea-accent hover:text-iea-textPrimary font-semibold"
              >
                Full View →
              </button>
            </div>
          </div>

          <div className="overflow-x-auto max-h-[340px] overflow-y-auto rounded-[14px] border border-iea-borderSubtle">
            <table className="w-full text-left text-xs iea-table">
              <thead className="sticky top-0 z-10">
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
                    <td colSpan={7} className="py-8 text-center text-iea-textMuted font-sans">
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
                    const chip = getNeutralSymbolChipSpec(pos.symbol);

                    return (
                      <tr key={pos.ticket}>
                        <td className="py-2.5 pl-4 pr-3">
                          <div className="flex items-center space-x-2.5">
                            <span
                              className={`w-7 h-7 rounded-full text-[10px] font-extrabold inline-flex items-center justify-center shrink-0 ${chip.chipBg} ${chip.chipRing}`}
                            >
                              {chip.shortCode}
                            </span>
                            <div>
                              <button
                                type="button"
                                onClick={() => setSelectedSymbol(symClean)}
                                title={`Focus ${symClean} on chart`}
                                className="font-bold text-iea-textPrimary hover:text-iea-accent transition"
                              >
                                {pos.symbol}
                              </button>
                              <div className="text-[10px] font-sans text-iea-textMuted">
                                #{pos.ticket}
                              </div>
                            </div>
                          </div>
                        </td>

                        <td className="py-2.5 pr-3">
                          <span
                            className={`px-2 py-0.5 rounded-full font-bold text-[10px] ${
                              dir === "BUY"
                                ? "bg-iea-profitSoft text-iea-profit"
                                : "bg-iea-dangerSoft text-iea-danger"
                            }`}
                          >
                            {dir} {pos.volume.toFixed(2)}L
                          </span>
                        </td>

                        <td className="py-2.5 pr-3 text-iea-textSecondary">
                          <span className="text-iea-textPrimary">
                            {pos.open_price.toFixed(digits)}
                          </span>
                          <span className="text-iea-textMuted mx-1">→</span>
                          <span className="text-iea-textPrimary font-semibold">
                            {pos.current_price.toFixed(digits)}
                          </span>
                        </td>

                        <td className="py-2.5 pr-3 text-iea-danger font-semibold">
                          {pos.sl > 0 ? pos.sl.toFixed(digits) : "—"}
                        </td>

                        <td className="py-2.5 pr-3 text-iea-profit font-semibold">
                          {pos.tp > 0 ? pos.tp.toFixed(digits) : "—"}
                        </td>

                        <td
                          className={`py-2.5 pr-3 font-bold ${
                            pos.profit >= 0 ? "text-iea-profit" : "text-iea-danger"
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
                            <span className="text-[10px] text-iea-textMuted font-mono">
                              READ-ONLY
                            </span>
                          ) : (
                            <div className="inline-flex flex-wrap items-center justify-end gap-1.5">
                              <button
                                type="button"
                                onClick={() => handlePartialClose50(pos)}
                                aria-label={`Partial close 50% of ticket ${pos.ticket}`}
                                title="Partial Close 50% volume"
                                className="px-2.5 py-1 rounded-full bg-iea-elevated hover:bg-iea-active border border-iea-borderSubtle text-iea-textPrimary text-[10px] font-semibold inline-flex items-center space-x-1 transition"
                              >
                                <Scissors className="w-2.5 h-2.5 text-iea-accent" />
                                <span>50%</span>
                              </button>

                              <button
                                type="button"
                                onClick={() => handleMoveToBreakEven(pos)}
                                aria-label={`Move stop loss to break-even for ticket ${pos.ticket}`}
                                title="Lock Stop Loss at Break-Even+"
                                className="px-2.5 py-1 rounded-full bg-iea-accentSoft hover:bg-iea-accent/25 border border-iea-accentBorder text-iea-accent text-[10px] font-semibold transition"
                              >
                                BE+
                              </button>

                              <button
                                type="button"
                                onClick={() => openTightenSlModal(pos)}
                                aria-label={`Tighten stop loss for ticket ${pos.ticket}`}
                                title="Tighten Stop Loss (Rule R9.3)"
                                className="px-2.5 py-1 rounded-full bg-iea-profitSoft hover:bg-iea-profit/25 border border-iea-profitBorder text-iea-profit text-[10px] font-semibold transition"
                              >
                                SL+
                              </button>

                              <button
                                type="button"
                                disabled
                                aria-disabled="true"
                                title="Hard Safety Rule R9.3: Widening or removing Stop Loss is permanently disabled"
                                className="px-2.5 py-1 rounded-full bg-iea-inset border border-iea-borderSubtle text-iea-textMuted text-[10px] font-medium cursor-not-allowed opacity-60 inline-flex items-center space-x-1"
                              >
                                <Lock className="w-2.5 h-2.5" />
                                <span>Widen</span>
                              </button>

                              <button
                                type="button"
                                onClick={() => handleCloseSinglePosition(pos)}
                                aria-label={`Close position ticket ${pos.ticket}`}
                                title="Close position at market"
                                className="px-2.5 py-1 rounded-full bg-iea-danger hover:opacity-90 text-white text-[10px] font-bold transition"
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
      </PanelErrorBoundary>

      {/* =====================================================================
          CONFIRMATION MODAL (Start Demo / Stop / Close All / Mobile Pause)
      ====================================================================== */}
      {confirmModal && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="two-step-confirm-title"
          className="fixed inset-0 z-50 bg-[var(--overlay-bg)] backdrop-blur-sm flex items-center justify-center p-4"
        >
          <div
            className={`iea-card p-5 max-w-sm w-full space-y-3 shadow-pop ${
              confirmModal.type === "START_DEMO"
                ? "border-iea-accentBorder"
                : confirmModal.type === "STOP"
                ? "border-iea-warningBorder"
                : "border-iea-dangerBorder"
            }`}
          >
            <div
              className={`flex items-center space-x-2 ${
                confirmModal.type === "START_DEMO"
                  ? "text-iea-accent"
                  : confirmModal.type === "STOP"
                  ? "text-iea-warning"
                  : "text-iea-danger"
              }`}
            >
              {confirmModal.type === "START_DEMO" ? (
                <Play className="w-5 h-5 shrink-0" />
              ) : (
                <ShieldAlert className="w-5 h-5 shrink-0" />
              )}
              <h3 id="two-step-confirm-title" className="text-sm font-bold text-iea-textPrimary">
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
              <p className="text-xs text-iea-textSecondary">
                The engine will run in{" "}
                <strong className="text-iea-accent font-mono">{topBar.operatingMode}</strong> on
                DEMO <span className="font-mono">{dash.maskedAccount}</span> and may place DEMO
                orders. LIVE trading remains locked.
              </p>
            ) : confirmModal.type === "STOP" ? (
              <p className="text-xs text-iea-textSecondary">
                Stop the trading engine process? Any open positions in MT5 will keep their existing
                broker SL/TP levels.
              </p>
            ) : confirmModal.step === 1 ? (
              <p className="text-xs text-iea-textSecondary">
                {confirmModal.type === "PAUSE" ? (
                  <>
                    {topBar.pauseResumeBtn.label} automated entries on DEMO{" "}
                    <span className="font-mono">{dash.maskedAccount}</span>? Existing SL/TP stay
                    active.
                  </>
                ) : (
                  <>
                    Close{" "}
                    <strong className="text-iea-textPrimary">{botOpenCount} bot positions</strong>{" "}
                    at market on DEMO <span className="font-mono">{dash.maskedAccount}</span>?
                    Positions will be reconciled with MT5 before confirming.
                  </>
                )}
              </p>
            ) : (
              <div className="p-3 rounded-xl bg-iea-dangerSoft border border-iea-dangerBorder text-xs text-iea-danger font-semibold">
                {confirmModal.type === "PAUSE"
                  ? `Final step: Confirm ${topBar.pauseResumeBtn.label.toLowerCase()}ing entries.`
                  : `Final step: Confirm immediate market closure on ${dash.maskedAccount}.`}
              </div>
            )}

            <div className="flex items-center justify-end space-x-2 pt-1">
              <button
                type="button"
                onClick={() => setConfirmModal(null)}
                className="iea-pill-control px-4 py-1.5 text-xs text-iea-textPrimary"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmTwoStep}
                className={`px-4 py-1.5 rounded-full text-xs font-bold transition ${
                  confirmModal.type === "START_DEMO"
                    ? "bg-iea-accent hover:bg-iea-accentHover text-white"
                    : confirmModal.type === "STOP"
                    ? "bg-iea-warning hover:opacity-90 text-iea-canvas"
                    : "bg-iea-danger hover:opacity-90 text-white"
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
          className="fixed inset-0 z-50 bg-[var(--overlay-bg)] backdrop-blur-sm flex items-center justify-center p-4"
        >
          <div className="iea-card p-5 max-w-sm w-full space-y-3 shadow-pop">
            <div className="flex items-center justify-between">
              <h3 id="tighten-sl-modal-title" className="text-sm font-bold text-iea-textPrimary">
                Tighten SL · #{slModalPos.ticket}
              </h3>
              <span className="px-2 py-0.5 rounded-full bg-iea-profitSoft text-iea-profit text-[10px] font-mono font-bold">
                R9.3 TIGHTEN-ONLY
              </span>
            </div>

            <div className="text-xs text-iea-textSecondary iea-inset p-2.5 font-mono flex items-center justify-between">
              <span>In: {slModalPos.open_price}</span>
              <span>Now: {slModalPos.current_price}</span>
              <span className="text-iea-danger">SL: {slModalPos.sl}</span>
            </div>

            <div className="space-y-2 text-xs">
              <label className="block">
                <span className="text-iea-textSecondary font-semibold">
                  New SL (
                  {slModalPos.direction === "BUY"
                    ? `>= ${slModalPos.sl}`
                    : `<= ${slModalPos.sl}`}
                  )
                </span>
                <input
                  type="number"
                  step="any"
                  value={proposedSlInput}
                  onChange={(e) => setProposedSlInput(e.target.value)}
                  className="w-full mt-1 iea-input px-3 py-1.5 font-mono"
                />
              </label>

              <label className="block">
                <span className="text-iea-textSecondary font-semibold">TP Target</span>
                <input
                  type="number"
                  step="any"
                  value={proposedTpInput}
                  onChange={(e) => setProposedTpInput(e.target.value)}
                  className="w-full mt-1 iea-input px-3 py-1.5 font-mono"
                />
              </label>
            </div>

            {!slValidation.allowed && (
              <div className="p-2.5 rounded-xl bg-iea-dangerSoft border border-iea-dangerBorder text-[11px] text-iea-danger">
                {slValidation.reason}
              </div>
            )}

            <div className="flex items-center justify-end space-x-2 pt-1">
              <button
                type="button"
                onClick={() => setSlModalPos(null)}
                className="iea-pill-control px-4 py-1.5 text-xs text-iea-textPrimary"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={!slValidation.allowed || busyAction !== null}
                onClick={handleApplyTightenSl}
                className="px-4 py-1.5 rounded-full bg-iea-profit hover:opacity-90 disabled:opacity-40 text-xs font-extrabold text-white"
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
