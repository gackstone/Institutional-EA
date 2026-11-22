import React, { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Cpu,
  Gauge,
  GitCompare,
  History,
  Layers,
  Lock,
  Pause,
  Play,
  RefreshCw,
  RotateCcw,
  Scissors,
  Send,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Square,
  TrendingDown,
  TrendingUp,
  Wifi,
  WifiOff,
  XCircle,
  Zap,
} from "lucide-react";
import { controlClient, IPC } from "../../services/ipc";
import {
  BTCUSDSampleStatus,
  ControlErrorEvent,
  ControlPosition,
  ControlStatusPayload,
  OperatingMode,
  RiskDecisionRecord,
  ScreenId,
  TradeHistoryRecord,
} from "../../types";
import {
  buildNormalizedDashboardData,
  buildSymbolChartBundle,
  ChartSymbol,
  ChartTimeframe,
  DataFeedStatus,
} from "../../services/dashboardDataAdapter";
import {
  calculateTradeMetrics,
  computeScheduleAndSession,
  validateTightenOnlyStopLoss,
} from "../../utils/tradeChartMath";
import { getSymbolChipSpec } from "../../styles/designTokens";
import { UI_COPY } from "../../constants/uiCopy";
import { LiveTradingChart } from "../LiveTradingChart";

interface CommonProps {
  status: ControlStatusPayload | null;
  onRefresh: () => Promise<void>;
  onActionMessage: (msg: string, isError?: boolean) => void;
}

export const DashboardScreen: React.FC<
  CommonProps & {
    onNavigate: (s: ScreenId) => void;
    btcStatus?: BTCUSDSampleStatus | null;
    onRefreshBtc?: () => Promise<void>;
    trades?: TradeHistoryRecord[];
    decisions?: RiskDecisionRecord[];
    errors?: ControlErrorEvent[];
    feedStatus?: DataFeedStatus;
    telegramEnabled?: boolean;
  }
> = ({
  status,
  onRefresh,
  onNavigate,
  onActionMessage,
  trades = [],
  decisions = [],
  errors = [],
  feedStatus = "LIVE_SSE",
}) => {
  const [selectedSymbol, setSelectedSymbol] = useState<ChartSymbol>("XAUUSD");
  const [selectedTimeframe, setSelectedTimeframe] = useState<ChartTimeframe>("M5");
  const [clockTick, setClockTick] = useState<Date>(() => new Date());
  const [dataTick, setDataTick] = useState<number>(0);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [modeOverride, setModeOverride] = useState<OperatingMode | null>(null);
  const [exposureTab, setExposureTab] = useState<"ALL" | "BOT" | "MANUAL">("ALL");

  // Two-step confirmation modal state for Close All / Emergency Flatten
  const [confirmModal, setConfirmModal] = useState<{
    type: "CLOSE_ALL_BOT" | "EMERGENCY_FLATTEN";
    step: 1 | 2;
  } | null>(null);

  // Tighten-Only Stop Loss modification modal state
  const [slModalPos, setSlModalPos] = useState<ControlPosition | null>(null);
  const [proposedSlInput, setProposedSlInput] = useState<string>("");
  const [proposedTpInput, setProposedTpInput] = useState<string>("");

  // Local optimistic modifications for positions (when in DEMO preview/simulation)
  const [localPositionOverrides, setLocalPositionOverrides] = useState<
    Record<number, Partial<ControlPosition> & { closed?: boolean }>
  >({});

  // Lightweight 1-second UTC clock & countdown timer (does NOT re-create chart candle series)
  useEffect(() => {
    const timer = setInterval(() => {
      setClockTick(new Date());
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  // Batched 3-second market tick pulse for DEMO chart quote updates
  useEffect(() => {
    const timer = setInterval(() => {
      setDataTick((c) => (c + 1) % 24);
    }, 3000);
    return () => clearInterval(timer);
  }, []);

  const liveSched = useMemo(() => computeScheduleAndSession(clockTick), [clockTick]);

  // Build normalized dashboard state (memoized on data changes, not 1s clock ticks)
  const dash = useMemo(
    () => buildNormalizedDashboardData(status, trades, decisions, errors),
    [status, trades, decisions, errors]
  );

  // Apply local optimistic overrides to positions
  const activePositions = useMemo(() => {
    return dash.status.mt5.positions
      .filter((p) => !localPositionOverrides[p.ticket]?.closed)
      .map((p) => ({
        ...p,
        ...(localPositionOverrides[p.ticket] || {}),
      }));
  }, [dash.status.mt5.positions, localPositionOverrides]);

  const visiblePositions = useMemo(() => {
    if (exposureTab === "BOT") return activePositions.filter((p) => p.ownership === "BOT");
    if (exposureTab === "MANUAL") return activePositions.filter((p) => p.ownership === "MANUAL");
    return activePositions;
  }, [activePositions, exposureTab]);

  const effectiveStatus: ControlStatusPayload = useMemo(
    () => ({
      ...dash.status,
      engine: {
        ...dash.status.engine,
        operating_mode: modeOverride || dash.status.engine.operating_mode,
      },
      mt5: {
        ...dash.status.mt5,
        positions: activePositions,
      },
    }),
    [dash.status, modeOverride, activePositions]
  );

  // Build Live Chart bundle for selected symbol & timeframe
  const chartBundle = useMemo(() => {
    const jitter = Math.sin(dataTick * 0.65) * 0.25;
    return buildSymbolChartBundle(selectedSymbol, selectedTimeframe, effectiveStatus, jitter);
  }, [selectedSymbol, selectedTimeframe, effectiveStatus, dataTick]);

  const eng = effectiveStatus.engine;
  const kpis = dash.kpis;
  const healthExt = dash.healthExtended;
  const inv = dash.inverseCoordination;

  // Execute existing Control Service endpoints safely
  const executeControlAction = async (
    label: string,
    fn: () => Promise<{ success?: boolean; message?: string }>
  ) => {
    setBusyAction(label);
    try {
      const res = await fn();
      onActionMessage(`${label}: ${res.message || "OK"}`, res.success === false);
      await onRefresh();
    } catch (e: any) {
      onActionMessage(`${label} failed: ${e.message}`, true);
    } finally {
      setBusyAction(null);
    }
  };

  const handleModeSwitch = async (mode: OperatingMode) => {
    setBusyAction(`Mode ${mode}`);
    try {
      setModeOverride(mode);
      await controlClient.applyConfig({ operating_mode: mode }, `Mode -> ${mode}`);
      onActionMessage(`Mode -> ${mode} (DEMO Locked)`);
      await onRefresh();
    } catch (e: any) {
      onActionMessage(`Mode error: ${e.message}`, true);
    } finally {
      setBusyAction(null);
    }
  };

  // Two-step confirmation handler for Close All Bot Positions & Emergency Flatten
  const handleConfirmTwoStep = async () => {
    if (!confirmModal) return;
    if (confirmModal.step === 1) {
      setConfirmModal({ ...confirmModal, step: 2 });
      return;
    }

    const actionType = confirmModal.type;
    setConfirmModal(null);

    if (actionType === "CLOSE_ALL_BOT") {
      await executeControlAction("Close All", async () => {
        const res = await controlClient.closeAllBotPositions(true);
        const nextOverrides = { ...localPositionOverrides };
        for (const p of activePositions) {
          if (p.ownership === "BOT") {
            nextOverrides[p.ticket] = { closed: true };
          }
        }
        setLocalPositionOverrides(nextOverrides);
        return res;
      });
    } else {
      await executeControlAction("Flatten", async () => {
        const res = await controlClient.emergencyStop(true, true);
        const nextOverrides = { ...localPositionOverrides };
        for (const p of activePositions) {
          if (p.ownership === "BOT") {
            nextOverrides[p.ticket] = { closed: true };
          }
        }
        setLocalPositionOverrides(nextOverrides);
        return res;
      });
    }
  };

  // Partial Close 50%
  const handlePartialClose50 = async (pos: ControlPosition) => {
    const halfVol = Number(Math.max(0.01, pos.volume / 2).toFixed(2));
    setBusyAction(`50% #${pos.ticket}`);
    try {
      const res = await IPC.closePosition(pos.ticket, halfVol);
      setLocalPositionOverrides((prev) => ({
        ...prev,
        [pos.ticket]: {
          ...(prev[pos.ticket] || {}),
          volume: Number(Math.max(0.01, pos.volume - halfVol).toFixed(2)),
          profit: Number((pos.profit * 0.5).toFixed(2)),
        },
      }));
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
      setLocalPositionOverrides((prev) => ({
        ...prev,
        [pos.ticket]: { closed: true },
      }));
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
      setLocalPositionOverrides((prev) => ({
        ...prev,
        [pos.ticket]: { ...(prev[pos.ticket] || {}), sl: targetBeSl, protected: true },
      }));
      onActionMessage(`#${pos.ticket} SL -> BE+ (${targetBeSl.toFixed(digits)})`);
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
      (dir === "BUY" ? Math.min(pos.current_price - step, baseSl + step) : Math.max(pos.current_price + step, baseSl - step)).toFixed(
        digits
      )
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
      setLocalPositionOverrides((prev) => ({
        ...prev,
        [slModalPos.ticket]: {
          ...(prev[slModalPos.ticket] || {}),
          sl: newSl,
          tp: newTp,
          protected: true,
        },
      }));
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
    <div className="space-y-3 text-[#F4F7FF]">
      {/* Compact Connection / Stale / Emergency Banner States */}
      {feedStatus === "DISCONNECTED" && (
        <div
          role="alert"
          title="Local Python Control Service unreachable on 127.0.0.1:8765"
          className="flex items-center justify-between px-4 py-2 rounded-2xl bg-[#FF5A6E]/18 border border-[#FF5A6E]/50 backdrop-blur-xl text-xs text-[#F4F7FF]"
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
            className="px-3 py-1 rounded-full bg-[#FF5A6E] hover:bg-[#FF7A8A] text-white font-semibold"
          >
            Reconnect
          </button>
        </div>
      )}

      {feedStatus === "STALE" && (
        <div
          role="alert"
          title="Last MT5 sync heartbeat exceeded 15 seconds"
          className="flex items-center justify-between px-4 py-2 rounded-2xl bg-[#FBBF24]/18 border border-[#FBBF24]/50 backdrop-blur-xl text-xs text-[#F4F7FF]"
        >
          <div className="flex items-center space-x-2">
            <AlertTriangle className="w-4 h-4 text-[#FBBF24] shrink-0" />
            <strong>Stale Sync (&gt;15s)</strong>
          </div>
          <button
            type="button"
            onClick={() => onRefresh()}
            className="px-3 py-1 rounded-full bg-[#FBBF24] text-[#081321] font-semibold"
          >
            Sync
          </button>
        </div>
      )}

      {eng.stop_flag_active && (
        <div
          role="alert"
          title="Emergency STOP.flag kill switch is active; all new entries are blocked"
          className="flex items-center justify-between px-4 py-2 rounded-2xl bg-[#FF5A6E]/22 border border-[#FF5A6E]/60 backdrop-blur-xl text-xs"
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
            className="px-3 py-1 rounded-full bg-[#B0F648] hover:bg-[#C2F076] text-[#081321] font-bold"
          >
            Clear Stop
          </button>
        </div>
      )}

      {/* =====================================================================
          SECTION (a): TOP STATUS BAR (Compact Short-Form Glass Pill Header)
      ====================================================================== */}
      <section
        aria-label="Terminal Top Status Bar"
        className="iea-glass-card flex flex-wrap items-center justify-between gap-2 px-3.5 py-2"
      >
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          {/* MT5 Connection + Masked Account ****0001 */}
          <div
            title={`Connected MT5 Account ${dash.maskedAccount} (${effectiveStatus.mt5.account.broker})`}
            className="iea-pill-control inline-flex items-center space-x-1.5 px-2.5 py-1"
          >
            <Wifi className="w-3.5 h-3.5 text-[#B0F648]" />
            <span className="font-medium text-[#F4F7FF]">MT5</span>
            <span className="font-mono font-bold text-[#B0F648]" data-testid="masked-account-badge">
              {dash.maskedAccount}
            </span>
          </div>

          {/* Hard Safety Lock Badge: DEMO · LIVE_TRADING_ENABLED=false */}
          <div
            data-testid="demo-lock-badge"
            title={UI_COPY.brand.demoLockTooltip}
            className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-full bg-[#B0F648]/16 border border-[#B0F648]/50 text-[#C2F076] font-mono text-[11px] font-bold"
          >
            <Lock className="w-3 h-3 text-[#B0F648] shrink-0" />
            <span>{UI_COPY.brand.demoLockChip}</span>
          </div>

          {/* Active Schedule Mode Badge */}
          <div
            data-testid="schedule-mode-badge"
            title={`Active Schedule Mode: ${liveSched.scheduleMode}`}
            className={`inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-full border font-mono text-[11px] font-bold ${
              liveSched.scheduleMode === "WEEKDAY_GOLD_MODE"
                ? "bg-[#FBBF24]/15 border-[#FBBF24]/45 text-[#FBBF24]"
                : "bg-[#C077FA]/18 border-[#C077FA]/45 text-[#E5C7FF]"
            }`}
          >
            <Clock className="w-3 h-3 shrink-0" />
            <span>{liveSched.scheduleMode}</span>
          </div>

          {/* Session + Live UTC Clock */}
          <div
            title="Active Trading Session & Live UTC Clock"
            className="iea-pill-control inline-flex items-center space-x-1.5 px-2.5 py-1 text-[11px]"
          >
            <span className="text-[#5EEAD4] font-semibold">{liveSched.sessionName}</span>
            <span className="text-[#8496B8]">·</span>
            <span className="font-mono text-[#F4F7FF]" data-testid="utc-clock">
              {liveSched.utcClockText}
            </span>
          </div>

          {/* ZMQ Bridge Ports 5555 / 5556 */}
          <div
            title="ZMQ/TCP Bridge Sockets: Port 5555 (EA) & Port 5556 (IPC)"
            className="iea-pill-control inline-flex items-center space-x-1.5 px-2.5 py-1 font-mono text-[11px]"
          >
            <span className="w-2 h-2 rounded-full bg-[#B0F648] shadow-[0_0_8px_#B0F648]" />
            <span className="text-[#B6C5E0]">ZMQ</span>
            <span className="text-[#B0F648] font-bold">5555/5556</span>
          </div>

          {/* Telegram Status */}
          <button
            type="button"
            onClick={() =>
              executeControlAction("TG Test", () => controlClient.testTelegram(false))
            }
            aria-label="Telegram status and quick connectivity test"
            title="Telegram notification dispatcher ready (click to test)"
            className="iea-pill-control inline-flex items-center space-x-1 px-2.5 py-1 text-[11px] text-[#F4F7FF]"
          >
            <Send className="w-3 h-3 text-[#5EEAD4]" />
            <span className="text-[#B0F648] font-semibold">TG Ready</span>
          </button>
        </div>

        {/* Right: Safety-Critical Quick Action Controls (Pause / Stop / Close All) */}
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            disabled={busyAction !== null}
            onClick={() =>
              executeControlAction(
                eng.pause_flag_active ? "Resume" : "Pause",
                () =>
                  eng.pause_flag_active
                    ? controlClient.resumeEntries()
                    : controlClient.pauseEntries()
              )
            }
            aria-label={eng.pause_flag_active ? "Resume new trade entries" : "Pause new trade entries"}
            title={eng.pause_flag_active ? "Resume automated trade entries" : "Pause new trade entries (existing SL/TP stay active)"}
            className="px-3 py-1 rounded-full bg-[#FBBF24]/20 hover:bg-[#FBBF24]/30 border border-[#FBBF24]/55 disabled:opacity-40 text-[#FBBF24] text-xs font-semibold inline-flex items-center space-x-1 transition"
          >
            <Pause className="w-3 h-3" />
            <span>{eng.pause_flag_active ? "Resume" : "Pause"}</span>
          </button>

          <button
            type="button"
            disabled={busyAction !== null}
            onClick={() =>
              executeControlAction("Stop", () => controlClient.stopEngine())
            }
            aria-label="Stop trading engine"
            title="Stop trading engine process (open positions remain protected)"
            className="iea-pill-control px-3 py-1 disabled:opacity-40 text-[#F4F7FF] text-xs font-semibold inline-flex items-center space-x-1"
          >
            <Square className="w-3 h-3 text-[#FF5A6E]" />
            <span>Stop</span>
          </button>

          <button
            type="button"
            disabled={busyAction !== null}
            onClick={() => setConfirmModal({ type: "CLOSE_ALL_BOT", step: 1 })}
            aria-label="Close all bot-owned positions (two-step confirmation)"
            title="Close all bot-owned positions at market (2-step confirmation)"
            className="px-3.5 py-1 rounded-full bg-gradient-to-r from-[#FF5A6E] to-[#E11D48] hover:brightness-110 disabled:opacity-40 text-white text-xs font-bold inline-flex items-center space-x-1 shadow-[0_4px_16px_rgba(255,90,110,0.4)] transition"
          >
            <XCircle className="w-3.5 h-3.5" />
            <span>Close All</span>
          </button>
        </div>
      </section>

      {/* =====================================================================
          SECTION (b): KPI ROW (6 COMPACT SHORT-FORM GLASS STAT CARDS)
      ====================================================================== */}
      <section
        aria-label="Account and Risk Key Performance Indicators"
        className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-2.5"
      >
        {/* 1. Bal / Eq */}
        <div className="iea-glass-card p-3 flex flex-col justify-between" title={UI_COPY.kpis.balEq.tooltip}>
          <div className="flex items-center justify-between text-xs text-[#B6C5E0]">
            <span className="font-medium">{UI_COPY.kpis.balEq.label}</span>
            <span
              title="Account Margin Leverage"
              className="font-mono text-[10px] text-[#B0F648] bg-[#B0F648]/14 border border-[#B0F648]/30 px-1.5 py-0.2 rounded-full"
            >
              Lev 1:{effectiveStatus.mt5.account.leverage}
            </span>
          </div>
          <div className="text-2xl font-light font-mono tracking-tight text-[#F4F7FF] mt-1.5">
            ${kpis.equity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="text-[11px] font-mono text-[#8496B8] mt-1 flex items-center justify-between">
            <span>Bal ${kpis.balance.toLocaleString(undefined, { minimumFractionDigits: 0 })}</span>
            <span className={kpis.floatingPnl >= 0 ? "text-[#B0F648] font-semibold" : "text-[#FF5A6E] font-semibold"}>
              {kpis.floatingPnl >= 0 ? "+" : ""}${kpis.floatingPnl.toFixed(2)}
            </span>
          </div>
        </div>

        {/* 2. Today P&L */}
        <div className="iea-glass-card-lime p-3 flex flex-col justify-between" title={UI_COPY.kpis.todayPnl.tooltip}>
          <div className="flex items-center justify-between text-xs text-[#C2F076]">
            <span className="font-medium">{UI_COPY.kpis.todayPnl.label}</span>
            {kpis.todayPnlUsd >= 0 ? (
              <TrendingUp className="w-3.5 h-3.5 text-[#B0F648]" />
            ) : (
              <TrendingDown className="w-3.5 h-3.5 text-[#FF5A6E]" />
            )}
          </div>
          <div
            className={`text-2xl font-light font-mono tracking-tight mt-1.5 ${
              kpis.todayPnlUsd >= 0 ? "text-[#B0F648]" : "text-[#FF5A6E]"
            }`}
          >
            {kpis.todayPnlUsd >= 0 ? "+" : ""}${kpis.todayPnlUsd.toFixed(2)}{" "}
            <span className="text-xs font-semibold">
              ({kpis.todayPnlR >= 0 ? "+" : ""}
              {kpis.todayPnlR.toFixed(2)}R)
            </span>
          </div>
          <div className="text-[11px] font-mono text-[#B6C5E0] mt-1">
            1R = ${(kpis.balance * 0.005).toFixed(2)} (0.5%)
          </div>
        </div>

        {/* 3. Daily Loss */}
        <div className="iea-glass-card p-3 flex flex-col justify-between" title={UI_COPY.kpis.dailyLoss.tooltip}>
          <div className="flex items-center justify-between text-xs text-[#B6C5E0]">
            <span className="font-medium">{UI_COPY.kpis.dailyLoss.label}</span>
            <span className="font-mono text-[11px] text-[#F4F7FF]">
              {kpis.dailyLossUsedPct.toFixed(2)}% / {kpis.dailyLossLimitPct.toFixed(1)}%
            </span>
          </div>
          <div className="text-2xl font-light font-mono tracking-tight text-[#F4F7FF] mt-1.5">
            ${kpis.dailyLossUsedUsd.toFixed(0)}{" "}
            <span className="text-xs text-[#8496B8] font-normal">
              / ${kpis.dailyLossLimitUsd.toFixed(0)}
            </span>
          </div>
          <div className="w-full h-1.5 bg-[#091426]/80 rounded-full overflow-hidden mt-1.5 border border-[rgba(186,214,255,0.12)]">
            <div
              className="h-full bg-[#B0F648] rounded-full shadow-[0_0_8px_#B0F648]"
              style={{
                width: `${Math.min(100, (kpis.dailyLossUsedPct / kpis.dailyLossLimitPct) * 100)}%`,
              }}
            />
          </div>
        </div>

        {/* 4. DD vs Cap */}
        <div className="iea-glass-card p-3 flex flex-col justify-between" title={UI_COPY.kpis.ddCap.tooltip}>
          <div className="flex items-center justify-between text-xs text-[#B6C5E0]">
            <span className="font-medium">{UI_COPY.kpis.ddCap.label}</span>
            <span className="font-mono text-[10px] text-[#B0F648] bg-[#B0F648]/14 px-2 py-0.2 rounded-full">
              SAFE
            </span>
          </div>
          <div className="text-2xl font-light font-mono tracking-tight text-[#F4F7FF] mt-1.5">
            {kpis.totalDrawdownUsedPct.toFixed(2)}%{" "}
            <span className="text-xs text-[#8496B8] font-normal">
              / {kpis.totalDrawdownCapPct.toFixed(1)}%
            </span>
          </div>
          <div className="w-full h-1.5 bg-[#091426]/80 rounded-full overflow-hidden mt-1.5 border border-[rgba(186,214,255,0.12)]">
            <div
              className="h-full bg-[#5EEAD4] rounded-full"
              style={{
                width: `${Math.min(100, (kpis.totalDrawdownUsedPct / kpis.totalDrawdownCapPct) * 100)}%`,
              }}
            />
          </div>
        </div>

        {/* 5. Open Exp */}
        <div className="iea-glass-card p-3 flex flex-col justify-between" title={UI_COPY.kpis.openExp.tooltip}>
          <div className="flex items-center justify-between text-xs text-[#B6C5E0]">
            <span className="font-medium">{UI_COPY.kpis.openExp.label}</span>
            <span className="font-mono text-[10px] text-[#5EEAD4] bg-[#5EEAD4]/14 px-2 py-0.2 rounded-full">
              {activePositions.length} Pos
            </span>
          </div>
          <div className="text-xl font-light font-mono tracking-tight text-[#F4F7FF] mt-1.5">
            Bot {activePositions.filter((p) => p.ownership === "BOT").length} · Man{" "}
            {activePositions.filter((p) => p.ownership === "MANUAL").length} · Ord{" "}
            {kpis.pendingOrdersCount}
          </div>
          <div className="text-[11px] font-mono text-[#8496B8] mt-1">
            Ext {kpis.otherEaPositionsCount} · #202601
          </div>
        </div>

        {/* 6. Next Sess */}
        <div className="iea-glass-card-violet p-3 flex flex-col justify-between" title={UI_COPY.kpis.nextSess.tooltip}>
          <div className="flex items-center justify-between text-xs text-[#E5C7FF]">
            <span className="font-medium">{UI_COPY.kpis.nextSess.label}</span>
            <Clock className="w-3.5 h-3.5 text-[#C077FA]" />
          </div>
          <div
            className="text-2xl font-light font-mono tracking-tight text-[#F4F7FF] mt-1.5"
            data-testid="schedule-countdown"
          >
            {liveSched.nextSwitchCountdown}
          </div>
          <div className="text-[11px] font-mono text-[#B6C5E0] truncate mt-1" title={liveSched.nextSwitchLabel}>
            → {liveSched.nextSwitchLabel.split(" ")[0]}
          </div>
        </div>
      </section>

      {/* =====================================================================
          MAIN TERMINAL WORKSPACE:
          SECTION (c) LIVE CHART (8 cols) + SECTION (d) RIGHT COLUMN (4 cols)
      ====================================================================== */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-3 items-stretch">
        {/* SECTION (c): LIVE CHART */}
        <div className="xl:col-span-8 flex flex-col min-h-[540px]">
          <LiveTradingChart
            bundle={chartBundle}
            selectedSymbol={selectedSymbol}
            selectedTimeframe={selectedTimeframe}
            feedStatus={feedStatus}
            onSelectSymbol={setSelectedSymbol}
            onSelectTimeframe={setSelectedTimeframe}
          />
        </div>

        {/* SECTION (d): RIGHT COLUMN — Engine & Mode + Pos & Ord */}
        <div className="xl:col-span-4 flex flex-col gap-3">
          {/* d.1: Engine & Mode Card */}
          <section
            aria-label="Engine Control and Supervisor Status"
            className="iea-glass-card p-3.5 space-y-2.5"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Cpu className="w-4 h-4 text-[#B0F648]" />
                <h2 className="text-sm font-semibold text-[#F4F7FF]">Engine &amp; Mode</h2>
              </div>
              <span
                className={`px-2 py-0.5 rounded-full text-[10px] font-mono font-bold ${
                  eng.engine_state === "RUNNING"
                    ? "bg-[#B0F648]/20 text-[#B0F648] border border-[#B0F648]/45"
                    : eng.engine_state === "PAUSED"
                    ? "bg-[#FBBF24]/20 text-[#FBBF24] border border-[#FBBF24]/45"
                    : "bg-white/10 text-[#B6C5E0]"
                }`}
              >
                {eng.engine_state}
              </span>
            </div>

            {/* Compact PID & Warmup Strip */}
            <div className="grid grid-cols-3 gap-2 text-[11px] font-mono">
              <div className="iea-glass-tile p-2" title="Trading Engine Supervisor Process ID">
                <div className="text-[#8496B8] font-sans text-[10px]">Eng PID</div>
                <div className="text-[#F4F7FF] font-bold mt-0.5">{eng.engine_pid ?? 15204}</div>
              </div>
              <div className="iea-glass-tile p-2" title="MT5 TCP Bridge Server Process ID">
                <div className="text-[#8496B8] font-sans text-[10px]">Brg PID</div>
                <div className="text-[#5EEAD4] font-bold mt-0.5">{eng.bridge_pid ?? 14820}</div>
              </div>
              <div className="iea-glass-tile p-2" title="Historical Candle Warm-up Status">
                <div className="text-[#8496B8] font-sans text-[10px]">Warmup</div>
                <div className="text-[#B0F648] font-bold mt-0.5">
                  {healthExt.warmupBarsLoaded}/{healthExt.warmupBarsRequired}
                </div>
              </div>
            </div>

            {/* Short-Code Operating Mode Selector (OBS, DRY, SCALP, FAST, ASSIST) */}
            <div>
              <div className="flex items-center justify-between text-[11px] text-[#B6C5E0] mb-1.5">
                <span className="font-medium">Mode (DEMO)</span>
                <span className="font-mono text-[10px] text-[#B0F648]">LIVE=false</span>
              </div>
              <div
                className="grid grid-cols-5 gap-1"
                role="radiogroup"
                aria-label="Select Engine Operating Mode"
              >
                {UI_COPY.modes.map((m) => {
                  const active = eng.operating_mode === m.mode;
                  return (
                    <button
                      key={m.mode}
                      type="button"
                      onClick={() => handleModeSwitch(m.mode)}
                      aria-pressed={active}
                      title={m.tooltip}
                      className={`px-1.5 py-2 rounded-xl border text-center transition-all duration-150 ${
                        active
                          ? "bg-[#B0F648] border-[#B0F648] text-[#081321] font-extrabold shadow-[0_0_14px_rgba(176,246,72,0.3)]"
                          : "bg-[#0D1B36]/65 border-[rgba(186,214,255,0.12)] text-[#B6C5E0] hover:border-[rgba(186,214,255,0.28)] hover:text-[#F4F7FF]"
                      }`}
                    >
                      <div className="text-[11px] font-mono font-bold leading-none">{m.code}</div>
                      <div
                        className={`text-[9px] truncate mt-1 ${
                          active ? "text-[#081321]/80 font-bold" : "text-[#8496B8]"
                        }`}
                      >
                        {m.label.split(" ")[0]}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Engine Lifecycle Action Buttons */}
            <div className="grid grid-cols-4 gap-1.5 pt-0.5">
              <button
                type="button"
                disabled={busyAction !== null}
                onClick={() =>
                  executeControlAction("Start", () =>
                    controlClient.startEngine(eng.operating_mode === "DRY_RUN")
                  )
                }
                title="Start Trading Engine & ZMQ Bridge"
                className="px-2 py-1.5 rounded-xl bg-[#B0F648] hover:bg-[#C2F076] text-[#081321] text-[11px] font-bold inline-flex items-center justify-center space-x-1 shadow-[0_0_12px_rgba(176,246,72,0.3)] transition"
              >
                <Play className="w-3 h-3" />
                <span>Start</span>
              </button>

              <button
                type="button"
                disabled={busyAction !== null}
                onClick={() =>
                  executeControlAction(
                    eng.pause_flag_active ? "Resume" : "Pause",
                    () =>
                      eng.pause_flag_active
                        ? controlClient.resumeEntries()
                        : controlClient.pauseEntries()
                  )
                }
                title="Pause or resume new trade entries"
                className="px-2 py-1.5 rounded-xl bg-[#FBBF24]/20 hover:bg-[#FBBF24]/30 border border-[#FBBF24]/50 text-[#FBBF24] text-[11px] font-semibold inline-flex items-center justify-center space-x-1 transition"
              >
                <Pause className="w-3 h-3" />
                <span>{eng.pause_flag_active ? "Resume" : "Pause"}</span>
              </button>

              <button
                type="button"
                disabled={busyAction !== null}
                onClick={() =>
                  executeControlAction("Restart", () => controlClient.restartEngine())
                }
                title="Restart Trading Engine process"
                className="px-2 py-1.5 rounded-xl bg-[#223D6A]/80 hover:bg-[#2F497C] border border-[rgba(186,214,255,0.22)] text-[#F4F7FF] text-[11px] font-semibold inline-flex items-center justify-center space-x-1 transition"
              >
                <RotateCcw className="w-3 h-3 text-[#5EEAD4]" />
                <span>Restart</span>
              </button>

              <button
                type="button"
                disabled={busyAction !== null}
                onClick={() => setConfirmModal({ type: "EMERGENCY_FLATTEN", step: 1 })}
                className="px-2 py-1.5 rounded-xl bg-gradient-to-r from-[#FF5A6E] to-[#E11D48] hover:brightness-110 text-white text-[11px] font-bold inline-flex items-center justify-center space-x-1 shadow-[0_0_12px_rgba(255,90,110,0.35)] transition"
                title="Engage STOP.flag and flatten all bot positions (2-step confirmation)"
              >
                <ShieldAlert className="w-3 h-3" />
                <span>Flatten</span>
              </button>
            </div>
          </section>

          {/* d.2: Pos & Ord Card */}
          <section
            aria-label="Open Positions and Pending Orders"
            className="flex-1 iea-glass-card p-3.5 flex flex-col justify-between space-y-2.5"
          >
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <h2
                  className="text-sm font-semibold text-[#F4F7FF]"
                  title="Active MT5 positions & pending orders (Rule R9.3 Tighten-Only SL)"
                >
                  Pos &amp; Ord ({activePositions.length})
                </h2>
                <button
                  type="button"
                  onClick={() => onNavigate("positions")}
                  className="text-[11px] text-[#B0F648] hover:text-[#C2F076] font-semibold"
                >
                  All →
                </button>
              </div>

              {/* Short-Form Segmented Underline Tabs */}
              <div className="flex items-center space-x-4 border-b border-[rgba(186,214,255,0.12)] text-xs">
                {(
                  [
                    { id: "ALL", label: `All (${activePositions.length})` },
                    {
                      id: "BOT",
                      label: `Bot (${activePositions.filter((p) => p.ownership === "BOT").length})`,
                    },
                    {
                      id: "MANUAL",
                      label: `Man (${activePositions.filter((p) => p.ownership === "MANUAL").length})`,
                    },
                  ] as const
                ).map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    data-active={exposureTab === t.id ? "true" : "false"}
                    onClick={() => setExposureTab(t.id)}
                    className="iea-tab-button text-xs"
                  >
                    {t.label}
                  </button>
                ))}
              </div>

              {visiblePositions.length === 0 ? (
                <div className="py-6 text-center text-xs text-[#8496B8] iea-glass-tile">
                  No open positions.
                </div>
              ) : (
                <div className="space-y-2 max-h-[320px] overflow-y-auto pr-1">
                  {visiblePositions.map((pos) => {
                    const symClean: ChartSymbol = pos.symbol.includes("JPY")
                      ? "USDJPY"
                      : pos.symbol.includes("BTC")
                      ? "BTCUSD"
                      : "XAUUSD";
                    const digits = symClean === "USDJPY" ? 3 : 2;
                    const contractVal = symClean === "XAUUSD" ? 100 : symClean === "USDJPY" ? 650 : 1;
                    const dir = pos.direction === "SELL" ? "SELL" : "BUY";
                    const m = calculateTradeMetrics({
                      direction: dir,
                      entryPrice: pos.open_price,
                      stopLoss: pos.sl,
                      currentPrice: pos.current_price,
                      volumeLots: pos.volume,
                      contractValuePerPoint: contractVal,
                    });

                    const ownerLabel =
                      pos.ownership === "BOT"
                        ? "BOT"
                        : pos.ownership === "MANUAL"
                        ? "MAN"
                        : "EXT";

                    const chip = getSymbolChipSpec(pos.symbol);

                    return (
                      <div
                        key={pos.ticket}
                        className="iea-glass-tile p-2.5 text-xs space-y-1.5 hover:border-[rgba(186,214,255,0.24)] transition"
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center space-x-1.5">
                            <span
                              className={`w-5 h-5 rounded-full text-[9px] font-extrabold inline-flex items-center justify-center shrink-0 ${chip.chipBg}`}
                            >
                              {chip.shortCode}
                            </span>

                            <button
                              type="button"
                              onClick={() => setSelectedSymbol(symClean)}
                              title={`Focus ${symClean} on chart`}
                              className="font-mono font-bold text-[#F4F7FF] hover:text-[#B0F648] transition"
                            >
                              {pos.symbol}
                            </button>

                            <span
                              className={`px-1.5 py-0.2 rounded-full font-mono font-bold text-[10px] ${
                                dir === "BUY"
                                  ? "bg-[#B0F648]/18 text-[#B0F648]"
                                  : "bg-[#FF5A6E]/20 text-[#FF5A6E]"
                              }`}
                            >
                              {dir} {pos.volume.toFixed(2)}L
                            </span>

                            <span
                              title={`Position Ownership: ${pos.ownership}`}
                              className={`px-1.5 py-0.2 rounded-full font-mono text-[9px] font-bold ${
                                ownerLabel === "BOT"
                                  ? "bg-[#5EEAD4]/15 text-[#5EEAD4]"
                                  : ownerLabel === "MAN"
                                  ? "bg-[#C077FA]/18 text-[#E5C7FF]"
                                  : "bg-white/10 text-[#B6C5E0]"
                              }`}
                            >
                              {ownerLabel}
                            </span>
                          </div>

                          <div
                            className={`font-mono font-bold ${
                              pos.profit >= 0 ? "text-[#B0F648]" : "text-[#FF5A6E]"
                            }`}
                          >
                            {pos.profit >= 0 ? "+" : ""}${pos.profit.toFixed(2)} (
                            {m.floatingR >= 0 ? "+" : ""}
                            {m.floatingR.toFixed(2)}R)
                          </div>
                        </div>

                        <div className="grid grid-cols-3 gap-1 font-mono text-[11px] bg-[#091426]/65 rounded-lg px-2 py-1 border border-[rgba(186,214,255,0.1)]">
                          <div>
                            <span className="text-[#8496B8]">In</span>{" "}
                            <span className="text-[#F4F7FF]">{pos.open_price.toFixed(digits)}</span>
                          </div>
                          <div>
                            <span className="text-[#8496B8]">SL</span>{" "}
                            <span className="text-[#FF7A8A] font-semibold">
                              {pos.sl > 0 ? pos.sl.toFixed(digits) : "-"}
                            </span>
                          </div>
                          <div>
                            <span className="text-[#8496B8]">TP</span>{" "}
                            <span className="text-[#B0F648] font-semibold">
                              {pos.tp > 0 ? pos.tp.toFixed(digits) : "-"}
                            </span>
                          </div>
                        </div>

                        {/* Compact 1-Word Position Action Controls */}
                        <div className="flex flex-wrap items-center justify-between gap-1 pt-0.5">
                          <div className="flex flex-wrap items-center gap-1">
                            <button
                              type="button"
                              onClick={() => handlePartialClose50(pos)}
                              aria-label={`Partial close 50% of ticket ${pos.ticket}`}
                              title="Partial Close 50% volume"
                              className="px-2 py-0.5 rounded-full bg-[#192F5A] hover:bg-[#234078] border border-[rgba(186,214,255,0.18)] text-[#F4F7FF] text-[10px] font-semibold inline-flex items-center space-x-1 transition"
                            >
                              <Scissors className="w-2.5 h-2.5 text-[#5EEAD4]" />
                              <span>50%</span>
                            </button>

                            <button
                              type="button"
                              onClick={() => handleMoveToBreakEven(pos)}
                              aria-label={`Move stop loss to break-even for ticket ${pos.ticket}`}
                              title="Lock Stop Loss at Break-Even+"
                              className="px-2 py-0.5 rounded-full bg-[#5EEAD4]/15 hover:bg-[#5EEAD4]/25 border border-[#5EEAD4]/40 text-[#5EEAD4] text-[10px] font-semibold transition"
                            >
                              BE+
                            </button>

                            <button
                              type="button"
                              onClick={() => openTightenSlModal(pos)}
                              aria-label={`Tighten stop loss for ticket ${pos.ticket}`}
                              title="Tighten Stop Loss (Rule R9.3)"
                              className="px-2 py-0.5 rounded-full bg-[#B0F648]/16 hover:bg-[#B0F648]/28 border border-[#B0F648]/45 text-[#C2F076] text-[10px] font-semibold transition"
                            >
                              SL+
                            </button>

                            <button
                              type="button"
                              disabled
                              aria-disabled="true"
                              title="Hard Safety Rule R9.3: Widening or removing Stop Loss is permanently disabled"
                              className="px-2 py-0.5 rounded-full bg-[#0A152B]/60 border border-[rgba(186,214,255,0.1)] text-[#8496B8] text-[10px] font-medium cursor-not-allowed opacity-60 inline-flex items-center space-x-1"
                            >
                              <Lock className="w-2.5 h-2.5" />
                              <span>Widen</span>
                            </button>
                          </div>

                          <button
                            type="button"
                            onClick={() => handleCloseSinglePosition(pos)}
                            aria-label={`Close position ticket ${pos.ticket}`}
                            title="Close position at market"
                            className="px-2 py-0.5 rounded-full bg-[#FF5A6E]/90 hover:bg-[#FF5A6E] text-white text-[10px] font-bold transition"
                          >
                            Close
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Compact Pending Orders Summary Footer */}
            <div className="pt-1.5 border-t border-[rgba(186,214,255,0.12)] flex items-center justify-between text-[11px]">
              <span className="text-[#B6C5E0]" title="Active Pending Limit & Stop Orders">
                Pending Ord: <strong className="font-mono text-[#F4F7FF]">{kpis.pendingOrdersCount}</strong>
              </span>
              <span
                title="All open positions carry verified server-side Stop Loss protection"
                className="inline-flex items-center space-x-1 text-[#B0F648] font-mono text-[10px]"
              >
                <ShieldCheck className="w-3.5 h-3.5" />
                <span>SL Guarded</span>
              </span>
            </div>
          </section>
        </div>
      </div>

      {/* =====================================================================
          SECTION (e): ANALYTICAL & OPERATIONAL PANELS (7 COMPACT GLASS PANELS)
      ====================================================================== */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
        {/* Panel 1: Timeline (4 cols) */}
        <section
          aria-label="Live Trade Lifecycle Timeline"
          className="lg:col-span-4 iea-glass-card p-3.5 space-y-2.5"
        >
          <div className="flex items-center justify-between">
            <h3
              className="text-sm font-semibold text-[#F4F7FF] flex items-center space-x-1.5"
              title="Real-time trade lifecycle events"
            >
              <Activity className="w-4 h-4 text-[#B0F648]" />
              <span>Timeline</span>
            </h3>
            <span className="iea-pill-control text-[10px] font-mono text-[#5EEAD4] px-2 py-0.5">
              SSE
            </span>
          </div>

          <div className="space-y-1.5 max-h-[220px] overflow-y-auto pr-1">
            {dash.timelineEvents.map((ev) => {
              const badgeStyles: Record<typeof ev.tone, string> = {
                emerald: "bg-[#B0F648]/18 text-[#B0F648] border-[#B0F648]/40",
                sky: "bg-[#5EEAD4]/18 text-[#5EEAD4] border-[#5EEAD4]/40",
                amber: "bg-[#FBBF24]/18 text-[#FBBF24] border-[#FBBF24]/40",
                rose: "bg-[#FF5A6E]/20 text-[#FF7A8A] border-[#FF5A6E]/45",
                slate: "bg-white/10 text-[#B6C5E0] border-white/15",
              };
              const chip = getSymbolChipSpec(ev.symbol);
              return (
                <div key={ev.id} className="iea-glass-tile p-2.5 text-xs space-y-1" title={ev.detail}>
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center space-x-1.5 min-w-0">
                      <span
                        className={`w-4 h-4 rounded-full text-[8px] font-extrabold inline-flex items-center justify-center shrink-0 ${chip.chipBg}`}
                      >
                        {chip.shortCode}
                      </span>
                      <span className="font-semibold text-[#F4F7FF] truncate">{ev.title}</span>
                    </div>
                    {ev.rMultiple && (
                      <span
                        className={`px-1.5 py-0.2 rounded-full border font-mono text-[10px] font-bold shrink-0 ${
                          badgeStyles[ev.tone]
                        }`}
                      >
                        {ev.rMultiple}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center justify-between text-[10px] font-mono text-[#8496B8]">
                    <span>
                      #{ev.ticket} · {ev.stage}
                    </span>
                    <span>{new Date(ev.timestamp).toLocaleTimeString()}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        {/* Panel 2: Risk Profiles (4 cols) */}
        <section
          aria-label="Risk Manager Profile Limits"
          className="lg:col-span-4 iea-glass-card p-3.5 space-y-2.5 flex flex-col justify-between"
        >
          <div className="space-y-2.5">
            <div className="flex items-center justify-between">
              <h3
                className="text-sm font-semibold text-[#F4F7FF] flex items-center space-x-1.5"
                title="DEMO, PROP & LIVE Risk Profile Ceilings"
              >
                <Shield className="w-4 h-4 text-[#B0F648]" />
                <span>Risk Profiles</span>
              </h3>
              <button
                type="button"
                onClick={() => onNavigate("risk")}
                className="text-[11px] text-[#B0F648] hover:text-[#C2F076] font-semibold"
              >
                Risk →
              </button>
            </div>

            <div className="overflow-x-auto rounded-xl border border-[rgba(186,214,255,0.12)]">
              <table className="w-full text-left text-xs iea-glass-table">
                <thead>
                  <tr>
                    <th className="py-2 pl-2.5 pr-2">Profile</th>
                    <th className="py-2 pr-2" title="Risk per Trade %">Risk/Trd</th>
                    <th className="py-2 pr-2" title="Max Daily Loss %">Daily</th>
                    <th className="py-2 pr-2" title="Max Total Drawdown %">Max DD</th>
                    <th className="py-2 pr-2.5">State</th>
                  </tr>
                </thead>
                <tbody className="font-mono text-[11px]">
                  {dash.riskProfiles.map((rp) => (
                    <tr key={rp.profile} className={rp.active ? "!bg-[#B0F648]/10" : ""}>
                      <td className="py-2 pl-2.5 pr-2 font-bold text-[#F4F7FF]">{rp.profile}</td>
                      <td className="py-2 pr-2 text-[#B0F648] font-semibold">
                        {rp.riskPerTradePct.toFixed(2)}%
                      </td>
                      <td className="py-2 pr-2 text-[#F4F7FF]">{rp.dailyLossLimitPct.toFixed(1)}%</td>
                      <td className="py-2 pr-2 text-[#F4F7FF]">{rp.maxTotalDrawdownPct.toFixed(1)}%</td>
                      <td className="py-2 pr-2.5 font-sans">
                        {rp.active ? (
                          <span className="px-2 py-0.2 rounded-full bg-[#B0F648] text-[#081321] text-[9px] font-extrabold">
                            ACTIVE
                          </span>
                        ) : rp.locked ? (
                          <span className="px-2 py-0.2 rounded-full bg-[#162749] text-[#B6C5E0] border border-[rgba(186,214,255,0.2)] text-[9px] font-semibold inline-flex items-center space-x-1">
                            <Lock className="w-2.5 h-2.5 text-[#FBBF24]" />
                            <span>LOCK</span>
                          </span>
                        ) : (
                          <span className="px-2 py-0.2 rounded-full bg-white/5 text-[#8496B8] text-[9px]">
                            IDLE
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="iea-glass-tile px-3 py-2 text-[11px] flex items-center justify-between">
            <span className="text-[#B6C5E0]">Portfolio Risk Used</span>
            <span className="font-mono font-bold text-[#B0F648]">1.15% / 6.0% (Free 4.85%)</span>
          </div>
        </section>

        {/* Panel 3: XAU/JPY Corr + Panel 4: Sess & Instr (4 cols) */}
        <div className="lg:col-span-4 flex flex-col gap-3">
          {/* Panel 3: XAU/JPY Corr */}
          <section
            aria-label="Gold and USDJPY Inverse Correlation Coordination"
            className="iea-glass-card p-3.5 space-y-2"
            title={inv.note}
          >
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-[#F4F7FF] flex items-center space-x-1.5">
                <GitCompare className="w-4 h-4 text-[#C077FA]" />
                <span>XAU/JPY Corr</span>
              </h3>
              <span className="px-2 py-0.2 rounded-full bg-[#B0F648]/18 text-[#B0F648] border border-[#B0F648]/40 font-mono text-[10px] font-bold">
                {inv.coherenceState}
              </span>
            </div>

            <div className="grid grid-cols-3 gap-2 font-mono text-xs">
              <div className="iea-glass-tile p-2" title="60-Minute Rolling Pearson Correlation">
                <div className="text-[10px] font-sans text-[#8496B8]">60m r</div>
                <div className="text-[#B0F648] font-bold mt-0.5">{inv.rollingCorrelation60m}</div>
              </div>
              <div className="iea-glass-tile p-2" title="Directional Bias Alignment">
                <div className="text-[10px] font-sans text-[#8496B8]">Bias</div>
                <div className="text-[#F4F7FF] font-bold mt-0.5">
                  {inv.goldBias === "BULLISH" ? "XAU↑" : "XAU↓"} /{" "}
                  {inv.usdjpyBias === "BEARISH" ? "JPY↓" : "JPY↑"}
                </div>
              </div>
              <div className="iea-glass-tile p-2" title="Inverse Exposure Hedge Gate">
                <div className="text-[10px] font-sans text-[#8496B8]">Gate</div>
                <div className="text-[#5EEAD4] font-bold mt-0.5">{inv.hedgeGateStatus}</div>
              </div>
            </div>
          </section>

          {/* Panel 4: Sess & Instr */}
          <section
            aria-label="Schedule and Approved Instruments Matrix"
            className="iea-glass-card p-3.5 space-y-2"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-[#F4F7FF] flex items-center space-x-1.5">
                <Layers className="w-4 h-4 text-[#5EEAD4]" />
                <span>Sess &amp; Instr</span>
              </h3>
              <button
                type="button"
                onClick={() => onNavigate("instruments")}
                className="text-[11px] text-[#B0F648] hover:text-[#C2F076] font-semibold"
              >
                Specs →
              </button>
            </div>

            <div className="grid grid-cols-3 gap-2 text-xs">
              {(["XAUUSD", "USDJPY", "BTCUSD"] as ChartSymbol[]).map((sym) => {
                const isActiveInSchedule = liveSched.activeInstruments.includes(sym);
                const chip = getSymbolChipSpec(sym);
                const active = selectedSymbol === sym;
                return (
                  <button
                    key={sym}
                    type="button"
                    onClick={() => setSelectedSymbol(sym)}
                    title={`${sym}: ${isActiveInSchedule ? "Active Session" : "24/7 Crypto / Standby"}`}
                    className={`p-2 rounded-2xl border text-left transition-all duration-150 ${
                      active
                        ? "bg-gradient-to-br from-[#B0F648]/18 to-[#223D6A]/70 border-[#B0F648]/55"
                        : "iea-glass-tile hover:border-[rgba(186,214,255,0.28)]"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span
                        className={`w-5 h-5 rounded-full text-[9px] font-extrabold inline-flex items-center justify-center ${chip.chipBg}`}
                      >
                        {chip.shortCode}
                      </span>
                      <span
                        className={`text-[10px] font-mono font-bold ${
                          isActiveInSchedule ? "text-[#B0F648]" : "text-[#FBBF24]"
                        }`}
                      >
                        {isActiveInSchedule ? "LIVE" : "24/7"}
                      </span>
                    </div>
                    <div className="font-mono font-bold text-[#F4F7FF] mt-1">{sym}</div>
                  </button>
                );
              })}
            </div>
          </section>
        </div>
      </div>

      {/* Bottom Row of Section (e): Health & Drift + Manual Guard + Recent Hist */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
        {/* Panel 5: Health & Drift (4 cols) */}
        <section
          aria-label="System Health and Quantitative Drift Telemetry"
          className="lg:col-span-4 iea-glass-card p-3.5 space-y-2.5 flex flex-col justify-between"
        >
          <div className="space-y-2.5">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-[#F4F7FF] flex items-center space-x-1.5">
                <Gauge className="w-4 h-4 text-[#B0F648]" />
                <span>Health &amp; Drift</span>
              </h3>
              <button
                type="button"
                onClick={() => onNavigate("errors")}
                className="text-[11px] text-[#B0F648] hover:text-[#C2F076] font-semibold"
              >
                Err ({healthExt.activeErrorCount}) →
              </button>
            </div>

            <div className="grid grid-cols-2 gap-2 text-xs font-mono">
              <div className="iea-glass-tile p-2.5" title="MT5 EA Heartbeat Latency">
                <div className="text-[10px] font-sans text-[#8496B8]">EA Ping</div>
                <div className="text-[#B0F648] font-bold mt-0.5">
                  {healthExt.eaHeartbeatAgeMs}ms ({healthExt.eaHeartbeatStatus})
                </div>
              </div>

              <div className="iea-glass-tile p-2.5" title="Outbound ZMQ Event Queue Depth">
                <div className="text-[10px] font-sans text-[#8496B8]">ZMQ Queue</div>
                <div className="text-[#F4F7FF] font-bold mt-0.5">{healthExt.outboundQueueDepth} msgs</div>
              </div>

              <div className="iea-glass-tile p-2.5" title="CUSUM Edge Decay & Population Stability Index">
                <div className="text-[10px] font-sans text-[#8496B8]">CUSUM / PSI</div>
                <div className="text-[#5EEAD4] font-bold mt-0.5">
                  {healthExt.cusumDecayScore} / {healthExt.psiFeatureDrift}
                </div>
              </div>

              <div className="iea-glass-tile p-2.5" title="Transaction Cost Analysis: Slippage & Fill Latency">
                <div className="text-[10px] font-sans text-[#8496B8]">TCA / Fill</div>
                <div className="text-[#B0F648] font-bold mt-0.5">
                  {healthExt.tcaAvgSlippageBps}bps · {healthExt.tcaFillLatencyMs}ms
                </div>
              </div>
            </div>
          </div>

          <div className="flex items-center justify-between iea-glass-tile px-3 py-2 text-xs">
            <span className="text-[#B6C5E0]">Active Errors</span>
            <span
              className={`font-mono font-bold px-2 py-0.2 rounded-full ${
                healthExt.activeErrorCount === 0
                  ? "bg-[#B0F648]/20 text-[#B0F648]"
                  : "bg-[#FF5A6E]/25 text-[#FF5A6E]"
              }`}
            >
              {healthExt.activeErrorCount}
            </span>
          </div>
        </section>

        {/* Panel 6: Manual Guard (3 cols) */}
        <section
          aria-label="Manual Position Adoption and Protection"
          className="lg:col-span-3 iea-glass-card p-3.5 space-y-2.5 flex flex-col justify-between"
        >
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h3
                className="text-sm font-semibold text-[#F4F7FF] flex items-center space-x-1.5"
                title="Manual discretionary positions adopted by Tighten-Only SL Guard"
              >
                <ShieldCheck className="w-4 h-4 text-[#C077FA]" />
                <span>Manual Guard</span>
              </h3>
              <span className="text-[10px] font-mono text-[#E5C7FF] bg-[#C077FA]/20 border border-[#C077FA]/35 px-2 py-0.2 rounded-full">
                {dash.manualAdoptionQueue.length} Man
              </span>
            </div>

            {dash.manualAdoptionQueue.length === 0 ? (
              <div className="py-5 text-center text-xs text-[#8496B8] iea-glass-tile px-2">
                0 manual trades.
              </div>
            ) : (
              <div className="space-y-2">
                {dash.manualAdoptionQueue.map((mp) => {
                  const chip = getSymbolChipSpec(mp.symbol);
                  return (
                    <div key={mp.ticket} className="iea-glass-tile p-2.5 text-xs space-y-1.5">
                      <div className="flex items-center justify-between font-mono">
                        <div className="flex items-center space-x-1.5">
                          <span
                            className={`w-5 h-5 rounded-full text-[9px] font-extrabold inline-flex items-center justify-center ${chip.chipBg}`}
                          >
                            {chip.shortCode}
                          </span>
                          <span className="font-bold text-[#F4F7FF]">
                            #{mp.ticket} {mp.symbol} {mp.direction} {mp.volume}L
                          </span>
                        </div>
                        <span className="text-[#B0F648] font-bold">+${mp.profit.toFixed(2)}</span>
                      </div>
                      <div className="flex items-center justify-between pt-0.5">
                        <span className="font-mono text-[10px] text-[#8496B8]">
                          SL {mp.sl > 0 ? mp.sl : mp.suggestedProtectiveSl} · TP {mp.tp > 0 ? mp.tp : mp.suggestedTp1}
                        </span>
                        <button
                          type="button"
                          onClick={() =>
                            executeControlAction(`Sync SL #${mp.ticket}`, () =>
                              controlClient.modifyPosition(
                                mp.ticket,
                                mp.sl > 0 ? mp.sl : mp.suggestedProtectiveSl,
                                mp.tp > 0 ? mp.tp : mp.suggestedTp1
                              )
                            )
                          }
                          title="Sync protective Stop Loss on manual position"
                          className="px-2 py-0.5 rounded-full bg-[#B0F648] hover:bg-[#C2F076] text-[#081321] text-[10px] font-extrabold transition"
                        >
                          Sync SL
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div className="text-[11px] text-[#B6C5E0] iea-glass-tile px-2.5 py-1.5 flex items-center justify-between">
            <span>Guard Mode</span>
            <strong className="font-mono text-[#5EEAD4]">ASSIST · R9.3</strong>
          </div>
        </section>

        {/* Panel 7: Recent Hist (5 cols) */}
        <section
          aria-label="Recent Closed Trades Table"
          className="lg:col-span-5 iea-glass-card p-3.5 space-y-2.5"
        >
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-[#F4F7FF] flex items-center space-x-1.5">
              <History className="w-4 h-4 text-[#B0F648]" />
              <span>Recent Hist ({dash.recentTrades.length})</span>
            </h3>
            <button
              type="button"
              onClick={() => onNavigate("history")}
              className="iea-pill-control px-2.5 py-0.5 text-[11px] text-[#B0F648] font-semibold"
            >
              Hist →
            </button>
          </div>

          <div className="overflow-x-auto rounded-xl border border-[rgba(186,214,255,0.12)]">
            <table className="w-full text-left text-xs iea-glass-table">
              <thead>
                <tr>
                  <th className="py-2 pl-2.5 pr-1.5">#</th>
                  <th className="py-2 pr-2">Instr</th>
                  <th className="py-2 pr-2">Side</th>
                  <th className="py-2 pr-2">In → Out</th>
                  <th className="py-2 pr-2">P&amp;L</th>
                  <th className="py-2 pr-2.5">Result</th>
                </tr>
              </thead>
              <tbody className="font-mono text-[11px]">
                {dash.recentTrades.slice(0, 6).map((t, idx) => {
                  const chip = getSymbolChipSpec(t.symbol);
                  return (
                    <tr key={t.id}>
                      <td className="py-2 pl-2.5 pr-1.5 text-[#8496B8]">{idx + 1}</td>
                      <td className="py-2 pr-2">
                        <div className="flex items-center space-x-1.5">
                          <span
                            className={`w-5 h-5 rounded-full text-[9px] font-extrabold inline-flex items-center justify-center shrink-0 ${chip.chipBg}`}
                          >
                            {chip.shortCode}
                          </span>
                          <span className="font-bold text-[#F4F7FF]">{t.symbol}</span>
                        </div>
                      </td>
                      <td
                        className={`py-2 pr-2 font-bold ${
                          t.direction === "BUY" ? "text-[#B0F648]" : "text-[#FF5A6E]"
                        }`}
                      >
                        {t.direction} {t.volume.toFixed(2)}
                      </td>
                      <td className="py-2 pr-2 text-[#B6C5E0]">
                        {t.open_price} → {t.close_price}
                      </td>
                      <td
                        className={`py-2 pr-2 font-bold ${
                          t.profit >= 0 ? "text-[#B0F648]" : "text-[#FF5A6E]"
                        }`}
                      >
                        {t.profit >= 0 ? "+" : ""}${t.profit.toFixed(2)}
                      </td>
                      <td className="py-2 pr-2.5 font-sans text-[10px]">
                        <span
                          className={`px-2 py-0.2 rounded-full ${
                            t.profit >= 0
                              ? "bg-[#B0F648]/14 text-[#C2F076]"
                              : "bg-[#FF5A6E]/15 text-[#FF7A8A]"
                          }`}
                        >
                          {t.status.replace("CLOSED ", "")}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      {/* =====================================================================
          BRIEF & EXPLICIT TWO-STEP CONFIRMATION MODAL (Part A.3 & Safety Rule #5)
      ====================================================================== */}
      {confirmModal && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="two-step-confirm-title"
          className="fixed inset-0 z-50 bg-[#050C1A]/80 backdrop-blur-md flex items-center justify-center p-4"
        >
          <div className="iea-glass-card border-[#FF5A6E]/60 p-5 max-w-sm w-full space-y-3 shadow-2xl">
            <div className="flex items-center space-x-2 text-[#FF5A6E]">
              <ShieldAlert className="w-5 h-5 shrink-0" />
              <h3 id="two-step-confirm-title" className="text-sm font-bold text-[#F4F7FF]">
                {confirmModal.type === "CLOSE_ALL_BOT"
                  ? `Close all bot trades? (${confirmModal.step}/2)`
                  : `Flatten bot trades & STOP.flag? (${confirmModal.step}/2)`}
              </h3>
            </div>

            {confirmModal.step === 1 ? (
              <p className="text-xs text-[#B6C5E0]">
                Close{" "}
                <strong className="text-[#F4F7FF]">
                  {activePositions.filter((p) => p.ownership === "BOT").length} bot positions
                </strong>{" "}
                at market on DEMO <span className="font-mono">{dash.maskedAccount}</span>? Manual trades stay untouched.
              </p>
            ) : (
              <div className="p-3 rounded-xl bg-[#FF5A6E]/18 border border-[#FF5A6E]/50 text-xs text-[#FFD9DF] font-semibold">
                Final step: Confirm immediate market closure on {dash.maskedAccount}.
              </div>
            )}

            <div className="flex items-center justify-end space-x-2 pt-1">
              <button
                type="button"
                onClick={() => setConfirmModal(null)}
                className="iea-pill-control px-4 py-1.5 text-xs text-[#F4F7FF]"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmTwoStep}
                className="px-4 py-1.5 rounded-full bg-gradient-to-r from-[#FF5A6E] to-[#E11D48] hover:brightness-110 text-xs font-bold text-white"
              >
                {confirmModal.step === 1
                  ? "Next →"
                  : confirmModal.type === "CLOSE_ALL_BOT"
                  ? "Close All"
                  : "Flatten"}
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

export const EngineScreen: React.FC<CommonProps> = ({ status, onRefresh, onActionMessage }) => {
  const [busy, setBusy] = useState(false);
  const [dryRunChoice, setDryRunChoice] = useState<boolean>(status?.engine.dry_run ?? true);
  const eng = status?.engine;

  const runAction = async (label: string, fn: () => Promise<{ success?: boolean; message?: string }>) => {
    setBusy(true);
    try {
      const res = await fn();
      onActionMessage(`${label}: ${res.message || "OK"}`, res.success === false);
      await onRefresh();
    } catch (e: any) {
      onActionMessage(`${label} failed: ${e.message}`, true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="iea-glass-card p-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <h2 className="text-lg font-light text-[#F4F7FF] flex items-center space-x-2">
            <Cpu className="w-5 h-5 text-[#B0F648]" />
            <span>Engine Lifecycle</span>
          </h2>
          <label
            title="Evaluate signals and risk gate without placing broker orders"
            className="iea-pill-control flex items-center space-x-2 text-xs text-[#F4F7FF] px-3.5 py-1.5 cursor-pointer"
          >
            <input
              type="checkbox"
              checked={dryRunChoice}
              onChange={(e) => setDryRunChoice(e.target.checked)}
              className="rounded border-[rgba(186,214,255,0.3)] accent-[#B0F648]"
            />
            <span>DRY Mode</span>
          </label>
        </div>

        <div className="flex flex-wrap gap-2.5 mt-4">
          <button
            disabled={busy || eng?.engine_running}
            onClick={() => runAction("Start", () => controlClient.startEngine(dryRunChoice))}
            className="px-4 py-2 bg-[#B0F648] hover:bg-[#C2F076] disabled:opacity-40 text-[#081321] text-xs font-bold rounded-full flex items-center space-x-1.5"
          >
            <Play className="w-4 h-4" />
            <span>Start</span>
          </button>

          <button
            disabled={busy}
            onClick={() =>
              runAction(
                eng?.pause_flag_active ? "Resume" : "Pause",
                () => (eng?.pause_flag_active ? controlClient.resumeEntries() : controlClient.pauseEntries())
              )
            }
            className="px-4 py-2 bg-[#FBBF24]/20 hover:bg-[#FBBF24]/30 border border-[#FBBF24]/55 disabled:opacity-40 text-[#FBBF24] text-xs font-semibold rounded-full flex items-center space-x-1.5"
          >
            <Pause className="w-4 h-4" />
            <span>{eng?.pause_flag_active ? "Resume" : "Pause"}</span>
          </button>

          <button
            disabled={busy || !eng?.engine_running}
            onClick={() => runAction("Stop", () => controlClient.stopEngine())}
            className="iea-pill-control px-4 py-2 disabled:opacity-40 text-[#F4F7FF] text-xs font-semibold flex items-center space-x-1.5"
          >
            <Square className="w-4 h-4 text-[#FF5A6E]" />
            <span>Stop</span>
          </button>

          <button
            disabled={busy}
            onClick={() => runAction("Restart", () => controlClient.restartEngine())}
            className="iea-pill-control px-4 py-2 disabled:opacity-40 text-[#5EEAD4] text-xs font-semibold flex items-center space-x-1.5"
          >
            <RotateCcw className="w-4 h-4" />
            <span>Restart</span>
          </button>

          {!eng?.stop_flag_active ? (
            <button
              disabled={busy}
              onClick={() => {
                if (window.confirm("Engage STOP.flag? Halts all new order entries.")) {
                  runAction("Kill Switch", () => controlClient.emergencyStop(false, true));
                }
              }}
              className="px-4 py-2 bg-gradient-to-r from-[#FF5A6E] to-[#E11D48] hover:brightness-110 disabled:opacity-40 text-white text-xs font-bold rounded-full flex items-center space-x-1.5 ml-auto"
            >
              <ShieldAlert className="w-4 h-4" />
              <span>Kill Switch</span>
            </button>
          ) : (
            <button
              disabled={busy}
              onClick={() => {
                if (window.confirm("Clear STOP.flag kill switch?")) {
                  runAction("Clear Stop", () => controlClient.clearEmergencyStop(true));
                }
              }}
              className="px-4 py-2 bg-[#B0F648] hover:bg-[#C2F076] disabled:opacity-40 text-[#081321] text-xs font-bold rounded-full flex items-center space-x-1.5 ml-auto"
            >
              <CheckCircle2 className="w-4 h-4" />
              <span>Clear Stop</span>
            </button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5">
        <div className="iea-glass-card p-4 text-xs space-y-1.5">
          <div className="text-[#8496B8]">Processes</div>
          <div>Bridge: <span className="font-mono text-[#F4F7FF]">{String(eng?.bridge_running ?? false)}</span> (PID {eng?.bridge_pid ?? "-"})</div>
          <div>Engine: <span className="font-mono text-[#F4F7FF]">{String(eng?.engine_running ?? false)}</span> (PID {eng?.engine_pid ?? "-"})</div>
        </div>
        <div className="iea-glass-card p-4 text-xs space-y-1.5">
          <div className="text-[#8496B8]">Flags</div>
          <div>STOP.flag: <span className={`font-mono font-bold ${eng?.stop_flag_active ? "text-[#FF5A6E]" : "text-[#B0F648]"}`}>{eng?.stop_flag_active ? "ACTIVE" : "CLEAR"}</span></div>
          <div>PAUSE: <span className={`font-mono font-bold ${eng?.pause_flag_active ? "text-[#FBBF24]" : "text-[#B0F648]"}`}>{eng?.pause_flag_active ? "PAUSED" : "CLEAR"}</span></div>
        </div>
        <div className="iea-glass-card-lime p-4 text-xs space-y-1.5">
          <div className="text-[#C2F076]">Safety Lock</div>
          <div>Mode: <span className="font-mono text-[#F4F7FF] font-bold">{eng?.operating_mode || "DEMO_SCALPING"}</span></div>
          <div>Live: <span className="font-mono text-[#B0F648] font-bold">LOCKED (DEMO)</span></div>
        </div>
      </div>
    </div>
  );
};

export const MarketWatchScreen: React.FC<CommonProps> = ({ status, onRefresh, onActionMessage }) => {
  const [syncing, setSyncing] = useState(false);
  const symbols = Object.values(status?.mt5.symbols || {});

  const handleSync = async () => {
    setSyncing(true);
    try {
      await controlClient.syncMT5();
      await onRefresh();
      onActionMessage("Quotes synced.");
    } catch (e: any) {
      onActionMessage(`Sync failed: ${e.message}`, true);
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="iea-glass-card p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-light text-[#F4F7FF] flex items-center space-x-2">
          <Activity className="w-5 h-5 text-[#B0F648]" />
          <span>Market Quotes</span>
        </h2>
        <button
          disabled={syncing}
          onClick={handleSync}
          className="px-4 py-1.5 bg-[#B0F648] hover:bg-[#C2F076] text-[#081321] text-xs font-bold rounded-full flex items-center space-x-1.5"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${syncing ? "animate-spin" : ""}`} />
          <span>Sync</span>
        </button>
      </div>

      <div className="overflow-x-auto rounded-2xl border border-[rgba(186,214,255,0.12)]">
        <table className="w-full text-left text-xs iea-glass-table">
          <thead>
            <tr>
              <th className="py-3 pl-4 pr-3">#</th>
              <th className="py-3 pr-3">Instr</th>
              <th className="py-3 pr-3">Bid</th>
              <th className="py-3 pr-3">Ask</th>
              <th className="py-3 pr-3" title="Spread in points">Spr</th>
              <th className="py-3 pr-3">Digits</th>
              <th className="py-3 pr-3" title="Min / Max / Step Lot">Lot (Min/Max/Step)</th>
              <th className="py-3 pr-4">Stops Lvl</th>
            </tr>
          </thead>
          <tbody className="font-mono">
            {symbols.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-8 text-center text-[#8496B8] font-sans">
                  No quotes cached. Click Sync.
                </td>
              </tr>
            ) : (
              symbols.map((s, idx) => {
                const chip = getSymbolChipSpec(s.symbol);
                return (
                  <tr key={s.symbol}>
                    <td className="py-3 pl-4 pr-3 text-[#8496B8]">{idx + 1}</td>
                    <td className="py-3 pr-3">
                      <div className="flex items-center space-x-2.5">
                        <span
                          className={`w-7 h-7 rounded-full text-[11px] font-extrabold inline-flex items-center justify-center ${chip.chipBg} ${chip.chipRing}`}
                        >
                          {chip.shortCode}
                        </span>
                        <div>
                          <div className="font-bold text-[#F4F7FF]">{s.symbol}</div>
                          <div className="text-[10px] font-sans text-[#8496B8]">{chip.tagLabel}</div>
                        </div>
                      </div>
                    </td>
                    <td className="py-3 pr-3 text-[#B0F648] font-bold">{s.bid.toFixed(s.digits)}</td>
                    <td className="py-3 pr-3 text-[#FF5A6E] font-bold">{s.ask.toFixed(s.digits)}</td>
                    <td className="py-3 pr-3 text-[#FBBF24]">{s.spread_points}</td>
                    <td className="py-3 pr-3 text-[#B6C5E0]">{s.digits}</td>
                    <td className="py-3 pr-3 text-[#B6C5E0]">{s.volume_min} / {s.volume_max} / {s.volume_step}</td>
                    <td className="py-3 pr-4 text-[#B6C5E0]">{s.stops_level}</td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export const SignalsScreen: React.FC<{ decisions: RiskDecisionRecord[]; onReload: () => Promise<void> }> = ({
  decisions,
  onReload,
}) => {
  return (
    <div className="space-y-4">
      <div className="iea-glass-card p-5 flex items-center justify-between">
        <h2
          className="text-lg font-light text-[#F4F7FF] flex items-center space-x-2"
          title="Unfiltered strategy signals evaluated by PortfolioRiskEngine"
        >
          <Zap className="w-5 h-5 text-[#B0F648]" />
          <span>Signal Gate</span>
        </h2>
        <button
          onClick={() => onReload()}
          className="iea-pill-control px-4 py-1.5 text-xs text-[#F4F7FF] font-semibold"
        >
          Refresh
        </button>
      </div>

      <div className="iea-glass-card p-5 overflow-x-auto">
        <div className="rounded-2xl border border-[rgba(186,214,255,0.12)] overflow-hidden">
          <table className="w-full text-left text-xs iea-glass-table">
            <thead>
              <tr>
                <th className="py-3 pl-4 pr-3">Time</th>
                <th className="py-3 pr-3">Instr</th>
                <th className="py-3 pr-3">Side</th>
                <th className="py-3 pr-3">Gate</th>
                <th className="py-3 pr-3">Lot</th>
                <th className="py-3 pr-3">Risk</th>
                <th className="py-3 pr-4">Note</th>
              </tr>
            </thead>
            <tbody>
              {decisions.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-[#8496B8]">
                    0 signals logged.
                  </td>
                </tr>
              ) : (
                decisions.map((d) => {
                  const chip = getSymbolChipSpec(d.symbol);
                  return (
                    <tr key={d.id}>
                      <td className="py-3 pl-4 pr-3 font-mono text-[#8496B8]">{new Date(d.created_at).toLocaleTimeString()}</td>
                      <td className="py-3 pr-3 font-mono font-bold text-[#F4F7FF]">
                        <div className="flex items-center space-x-2">
                          <span
                            className={`w-6 h-6 rounded-full text-[10px] font-extrabold inline-flex items-center justify-center ${chip.chipBg}`}
                          >
                            {chip.shortCode}
                          </span>
                          <span>{d.symbol}</span>
                        </div>
                      </td>
                      <td className="py-3 pr-3 font-mono text-[#F4F7FF]">{d.direction}</td>
                      <td className="py-3 pr-3">
                        <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold ${d.approved ? "bg-[#B0F648]/20 text-[#B0F648]" : "bg-[#FF5A6E]/20 text-[#FF5A6E]"}`}>
                          {d.approved ? "OK" : "BLOCK"}
                        </span>
                      </td>
                      <td className="py-3 pr-3 font-mono">{d.lot_size.toFixed(2)}</td>
                      <td className="py-3 pr-3 font-mono text-[#B0F648]">{d.risk_pct.toFixed(2)}%</td>
                      <td className="py-3 pr-4 text-[#B6C5E0]">{d.reason}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
