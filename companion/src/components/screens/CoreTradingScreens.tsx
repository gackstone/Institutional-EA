import React, { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertOctagon,
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
  validateTightenOnlyStopLoss,
} from "../../utils/tradeChartMath";
import { getSymbolChipSpec } from "../../styles/designTokens";
import { LiveTradingChart } from "../LiveTradingChart";

interface CommonProps {
  status: ControlStatusPayload | null;
  onRefresh: () => Promise<void>;
  onActionMessage: (msg: string, isError?: boolean) => void;
}

const DASHBOARD_MODES: Array<{ mode: OperatingMode; short: string; desc: string }> = [
  { mode: "OBSERVE", short: "OBSERVE", desc: "Stream telemetry & signals only" },
  { mode: "DRY_RUN", short: "DRY_RUN", desc: "Evaluate risk gate without broker orders" },
  { mode: "DEMO_SCALPING", short: "DEMO_SCALPING", desc: "Authoritative Gold/USDJPY/BTC DEMO execution" },
  { mode: "DEMO_FAST", short: "DEMO_FAST", desc: "Low-latency M1/M5 DEMO execution profile" },
  { mode: "DEMO_MANUAL_ASSIST", short: "DEMO_MANUAL_ASSIST", desc: "Adopt & guard manual positions with tighten-only SL" },
];

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
  const [nowTick, setNowTick] = useState<Date>(() => new Date());
  const [tickCounter, setTickCounter] = useState<number>(0);
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

  // Live 1-second UTC clock & SSE/tick pulse
  useEffect(() => {
    const timer = setInterval(() => {
      setNowTick(new Date());
      setTickCounter((c) => (c + 1) % 24);
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  // Build normalized dashboard state
  const dash = useMemo(
    () => buildNormalizedDashboardData(status, trades, decisions, errors, nowTick),
    [status, trades, decisions, errors, nowTick]
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
    const jitter = Math.sin(tickCounter * 0.65) * 0.25;
    return buildSymbolChartBundle(selectedSymbol, selectedTimeframe, effectiveStatus, jitter);
  }, [selectedSymbol, selectedTimeframe, effectiveStatus, tickCounter]);

  const eng = effectiveStatus.engine;
  const kpis = dash.kpis;
  const sched = dash.scheduleInfo;
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
      onActionMessage(`${label}: ${res.message || "Completed"}`, res.success === false);
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
      await controlClient.applyConfig(
        { operating_mode: mode },
        `Dashboard operator switched mode to ${mode}`
      );
      onActionMessage(`Engine operating mode switched to ${mode} (DEMO lock active).`);
      await onRefresh();
    } catch (e: any) {
      onActionMessage(`Mode switch error: ${e.message}`, true);
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
      await executeControlAction("Close All Bot Positions", async () => {
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
      await executeControlAction("Emergency Flatten & STOP.flag", async () => {
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

  // Partial Close 50% using existing IPC.closePosition(ticket, volume * 0.5)
  const handlePartialClose50 = async (pos: ControlPosition) => {
    const halfVol = Number(Math.max(0.01, pos.volume / 2).toFixed(2));
    setBusyAction(`Partial #${pos.ticket}`);
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
      onActionMessage(
        `Partial Close 50% (#${pos.ticket} ${pos.symbol}): Closed ${halfVol.toFixed(2)} lots. ${res.message}`
      );
      await onRefresh();
    } catch (e: any) {
      onActionMessage(`Partial close failed: ${e.message}`, true);
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
      onActionMessage(`Closed position #${pos.ticket} (${pos.symbol}): ${res.message}`);
      await onRefresh();
    } catch (e: any) {
      onActionMessage(`Close #${pos.ticket} failed: ${e.message}`, true);
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
      onActionMessage(`Break-Even rejected: ${validation.reason}`, true);
      return;
    }

    setBusyAction(`BE #${pos.ticket}`);
    try {
      const res = await controlClient.modifyPosition(pos.ticket, targetBeSl, pos.tp);
      setLocalPositionOverrides((prev) => ({
        ...prev,
        [pos.ticket]: { ...(prev[pos.ticket] || {}), sl: targetBeSl, protected: true },
      }));
      onActionMessage(
        `Ticket #${pos.ticket} SL tightened to Break-Even+ (${targetBeSl.toFixed(digits)}). ${res.message}`
      );
      await onRefresh();
    } catch (e: any) {
      onActionMessage(`Move to BE failed: ${e.message}`, true);
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
    setBusyAction(`Modify #${slModalPos.ticket}`);
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
      onActionMessage(`Tightened SL on #${slModalPos.ticket} → ${newSl}: ${res.message}`);
      setSlModalPos(null);
      await onRefresh();
    } catch (e: any) {
      onActionMessage(`SL modification failed: ${e.message}`, true);
    } finally {
      setBusyAction(null);
    }
  };

  return (
    <div className="space-y-3.5 text-[#F4F7FF]">
      {/* Connection / Stale-Data / Emergency Banner States */}
      {feedStatus === "DISCONNECTED" && (
        <div
          role="alert"
          className="flex items-center justify-between px-4 py-2.5 rounded-2xl bg-[#FF5A6E]/18 border border-[#FF5A6E]/50 backdrop-blur-xl text-xs text-[#F4F7FF]"
        >
          <div className="flex items-center space-x-2.5">
            <WifiOff className="w-4 h-4 text-[#FF5A6E] shrink-0" />
            <span>
              <strong>Control Service Disconnected (127.0.0.1:8765)</strong> — Displaying cached DEMO state. Verify Python Control Service daemon.
            </span>
          </div>
          <button
            type="button"
            onClick={() => onRefresh()}
            className="px-3 py-1 rounded-full bg-[#FF5A6E] hover:bg-[#FF7A8A] text-white font-semibold"
          >
            Retry Reconnect
          </button>
        </div>
      )}

      {feedStatus === "STALE" && (
        <div
          role="alert"
          className="flex items-center justify-between px-4 py-2.5 rounded-2xl bg-[#FBBF24]/18 border border-[#FBBF24]/50 backdrop-blur-xl text-xs text-[#F4F7FF]"
        >
          <div className="flex items-center space-x-2.5">
            <AlertTriangle className="w-4 h-4 text-[#FBBF24] shrink-0" />
            <span>
              <strong>Stale Telemetry Warning</strong> — Last MT5 sync heartbeat exceeded 15s threshold.
            </span>
          </div>
          <button
            type="button"
            onClick={() => onRefresh()}
            className="px-3 py-1 rounded-full bg-[#FBBF24] text-[#081321] font-semibold"
          >
            Force Sync
          </button>
        </div>
      )}

      {eng.stop_flag_active && (
        <div
          role="alert"
          className="flex items-center justify-between px-4 py-2.5 rounded-2xl bg-[#FF5A6E]/22 border border-[#FF5A6E]/60 backdrop-blur-xl text-xs"
        >
          <div className="flex items-center space-x-2.5">
            <ShieldAlert className="w-4 h-4 text-[#FF5A6E] shrink-0" />
            <div>
              <span className="font-bold text-[#FFD9DF]">EMERGENCY STOP.flag ENGAGED</span>
              <span className="text-[#F4F7FF] ml-2">All new order entries are hard-blocked until cleared.</span>
            </div>
          </div>
          <button
            type="button"
            onClick={() =>
              executeControlAction("Clear STOP.flag", () => controlClient.clearEmergencyStop(true))
            }
            className="px-3 py-1 rounded-full bg-[#B0F648] hover:bg-[#C2F076] text-[#081321] font-bold"
          >
            Clear STOP.flag
          </button>
        </div>
      )}

      {/* =====================================================================
          SECTION (a): TOP STATUS BAR (Translucent Glass Pill Header)
          MT5 connection (masked account ****0001), DEMO + LIVE_TRADING_ENABLED=false badge,
          active schedule mode (WEEKDAY_GOLD_MODE / WEEKEND_BTC_MODE), session + UTC clock,
          bridge ports 5555/5556, Telegram status, Pause / Stop / Close all.
      ====================================================================== */}
      <section
        aria-label="Terminal Top Status Bar"
        className="iea-glass-card flex flex-wrap items-center justify-between gap-2.5 px-4 py-2.5"
      >
        {/* Left telemetry pill chips */}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          {/* MT5 Connection + Masked Account ****0001 */}
          <div className="iea-pill-control inline-flex items-center space-x-1.5 px-3 py-1">
            <Wifi className="w-3.5 h-3.5 text-[#B0F648]" />
            <span className="font-medium text-[#F4F7FF]">MT5</span>
            <span className="font-mono font-bold text-[#B0F648]" data-testid="masked-account-badge">
              {dash.maskedAccount}
            </span>
            <span className="text-[#8496B8] text-[11px]">({effectiveStatus.mt5.account.broker})</span>
          </div>

          {/* Hard Safety Lock Badge: DEMO • LIVE_TRADING_ENABLED=false */}
          <div
            data-testid="demo-lock-badge"
            className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-full bg-[#B0F648]/16 border border-[#B0F648]/50 text-[#C2F076] font-mono text-[11px] font-bold shadow-[0_0_16px_rgba(176,246,72,0.16)]"
            title="Hard Safety Rule: execution_mode=DEMO and LIVE_TRADING_ENABLED=false are permanently locked"
          >
            <Lock className="w-3.5 h-3.5 text-[#B0F648] shrink-0" />
            <span>DEMO</span>
            <span className="text-[#B0F648]">·</span>
            <span>LIVE_TRADING_ENABLED=false</span>
          </div>

          {/* Active Schedule Mode Badge (WEEKDAY_GOLD_MODE / WEEKEND_BTC_MODE) */}
          <div
            data-testid="schedule-mode-badge"
            className={`inline-flex items-center space-x-1.5 px-3 py-1 rounded-full border font-mono text-[11px] font-bold ${
              sched.scheduleMode === "WEEKDAY_GOLD_MODE"
                ? "bg-[#FBBF24]/15 border-[#FBBF24]/45 text-[#FBBF24]"
                : "bg-[#C077FA]/18 border-[#C077FA]/45 text-[#E5C7FF]"
            }`}
          >
            <Clock className="w-3.5 h-3.5 shrink-0" />
            <span>{sched.scheduleMode}</span>
          </div>

          {/* Session + Live UTC Clock */}
          <div className="iea-pill-control inline-flex items-center space-x-1.5 px-3 py-1 text-[11px]">
            <span className="text-[#5EEAD4] font-semibold">{sched.sessionName}</span>
            <span className="text-[#8496B8]">|</span>
            <span className="font-mono text-[#F4F7FF]" data-testid="utc-clock">
              {sched.utcClockText}
            </span>
          </div>

          {/* Bridge Ports 5555 / 5556 */}
          <div className="iea-pill-control inline-flex items-center space-x-1.5 px-3 py-1 font-mono text-[11px]">
            <span className="w-2 h-2 rounded-full bg-[#B0F648] shadow-[0_0_8px_#B0F648]" />
            <span className="text-[#B6C5E0]">ZMQ Bridge</span>
            <span className="text-[#B0F648] font-bold">5555/5556</span>
          </div>

          {/* Telegram Status */}
          <button
            type="button"
            onClick={() =>
              executeControlAction("Test Telegram", () => controlClient.testTelegram(false))
            }
            aria-label="Telegram status and quick connectivity test"
            className="iea-pill-control inline-flex items-center space-x-1.5 px-3 py-1 text-[11px] text-[#F4F7FF]"
          >
            <Send className="w-3 h-3 text-[#5EEAD4]" />
            <span className="text-[#B6C5E0]">Telegram:</span>
            <span className="text-[#B0F648] font-semibold">READY</span>
          </button>
        </div>

        {/* Right: Safety-Critical Quick Action Controls (Pause / Stop / Close All) */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={busyAction !== null}
            onClick={() =>
              executeControlAction(
                eng.pause_flag_active ? "Resume Entries" : "Pause Entries",
                () =>
                  eng.pause_flag_active
                    ? controlClient.resumeEntries()
                    : controlClient.pauseEntries()
              )
            }
            aria-label={eng.pause_flag_active ? "Resume new trade entries" : "Pause new trade entries"}
            className="px-3.5 py-1.5 rounded-full bg-[#FBBF24]/20 hover:bg-[#FBBF24]/30 border border-[#FBBF24]/55 disabled:opacity-40 text-[#FBBF24] text-xs font-semibold inline-flex items-center space-x-1.5 transition"
          >
            <Pause className="w-3.5 h-3.5" />
            <span>{eng.pause_flag_active ? "Resume" : "Pause"}</span>
          </button>

          <button
            type="button"
            disabled={busyAction !== null}
            onClick={() =>
              executeControlAction("Stop Engine", () => controlClient.stopEngine())
            }
            aria-label="Stop trading engine"
            className="iea-pill-control px-3.5 py-1.5 disabled:opacity-40 text-[#F4F7FF] text-xs font-semibold inline-flex items-center space-x-1.5"
          >
            <Square className="w-3.5 h-3.5 text-[#FF5A6E]" />
            <span>Stop</span>
          </button>

          <button
            type="button"
            disabled={busyAction !== null}
            onClick={() => setConfirmModal({ type: "CLOSE_ALL_BOT", step: 1 })}
            aria-label="Close all bot-owned positions (two-step confirmation)"
            className="px-4 py-1.5 rounded-full bg-gradient-to-r from-[#FF5A6E] to-[#E11D48] hover:brightness-110 disabled:opacity-40 text-white text-xs font-bold inline-flex items-center space-x-1.5 shadow-[0_4px_18px_rgba(255,90,110,0.4)] transition"
          >
            <XCircle className="w-3.5 h-3.5" />
            <span>Close All</span>
          </button>
        </div>
      </section>

      {/* =====================================================================
          SECTION (b): KPI ROW (6 GLASS STAT CARDS)
          Modeled on reference image's translucent glass cards with large light-weight
          tabular numbers ($678.567 / 1.632.67) and subtle muted labels underneath.
      ====================================================================== */}
      <section
        aria-label="Account and Risk Key Performance Indicators"
        className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3"
      >
        {/* 1. Balance / Equity */}
        <div className="iea-glass-card p-3.5 flex flex-col justify-between">
          <div className="flex items-center justify-between text-xs text-[#B6C5E0]">
            <span className="font-medium">Balance / Equity</span>
            <span className="font-mono text-[10px] text-[#B0F648] bg-[#B0F648]/14 border border-[#B0F648]/30 px-2 py-0.5 rounded-full">
              1:{effectiveStatus.mt5.account.leverage}
            </span>
          </div>
          <div className="text-2xl font-light font-mono tracking-tight text-[#F4F7FF] mt-2">
            ${kpis.equity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="text-[11px] font-mono text-[#8496B8] mt-1 flex items-center justify-between">
            <span>Bal: ${kpis.balance.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
            <span className={kpis.floatingPnl >= 0 ? "text-[#B0F648] font-semibold" : "text-[#FF5A6E] font-semibold"}>
              {kpis.floatingPnl >= 0 ? "+" : ""}${kpis.floatingPnl.toFixed(2)}
            </span>
          </div>
        </div>

        {/* 2. Today P&L (+R) — Featured Lime-Sheen Glass Card */}
        <div className="iea-glass-card-lime p-3.5 flex flex-col justify-between">
          <div className="flex items-center justify-between text-xs text-[#C2F076]">
            <span className="font-medium">Today P&amp;L (+R)</span>
            {kpis.todayPnlUsd >= 0 ? (
              <TrendingUp className="w-4 h-4 text-[#B0F648]" />
            ) : (
              <TrendingDown className="w-4 h-4 text-[#FF5A6E]" />
            )}
          </div>
          <div
            className={`text-2xl font-light font-mono tracking-tight mt-2 ${
              kpis.todayPnlUsd >= 0 ? "text-[#B0F648]" : "text-[#FF5A6E]"
            }`}
          >
            {kpis.todayPnlUsd >= 0 ? "+" : ""}${kpis.todayPnlUsd.toFixed(2)}{" "}
            <span className="text-sm font-semibold">
              ({kpis.todayPnlR >= 0 ? "+" : ""}
              {kpis.todayPnlR.toFixed(2)}R)
            </span>
          </div>
          <div className="text-[11px] text-[#B6C5E0] mt-1">
            1R Unit Risk = ${(kpis.balance * 0.005).toFixed(2)} (0.50%)
          </div>
        </div>

        {/* 3. Daily Loss Used vs Limit */}
        <div className="iea-glass-card p-3.5 flex flex-col justify-between">
          <div className="flex items-center justify-between text-xs text-[#B6C5E0]">
            <span className="font-medium">Daily Loss vs Limit</span>
            <span className="font-mono text-[11px] text-[#F4F7FF]">
              {kpis.dailyLossUsedPct.toFixed(2)}% / {kpis.dailyLossLimitPct.toFixed(1)}%
            </span>
          </div>
          <div className="text-2xl font-light font-mono tracking-tight text-[#F4F7FF] mt-2">
            ${kpis.dailyLossUsedUsd.toFixed(2)}{" "}
            <span className="text-xs text-[#8496B8] font-normal">
              of ${kpis.dailyLossLimitUsd.toFixed(2)}
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

        {/* 4. Total Drawdown vs Cap */}
        <div className="iea-glass-card p-3.5 flex flex-col justify-between">
          <div className="flex items-center justify-between text-xs text-[#B6C5E0]">
            <span className="font-medium">Total DD vs Cap</span>
            <span className="font-mono text-[10px] text-[#B0F648] bg-[#B0F648]/14 px-2 py-0.5 rounded-full">
              SAFE
            </span>
          </div>
          <div className="text-2xl font-light font-mono tracking-tight text-[#F4F7FF] mt-2">
            {kpis.totalDrawdownUsedPct.toFixed(2)}%{" "}
            <span className="text-xs text-[#8496B8] font-normal">
              / {kpis.totalDrawdownCapPct.toFixed(1)}% Cap
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

        {/* 5. Open Positions (Bot / Manual / Pending) */}
        <div className="iea-glass-card p-3.5 flex flex-col justify-between">
          <div className="flex items-center justify-between text-xs text-[#B6C5E0]">
            <span className="font-medium">Open Exposure</span>
            <span className="font-mono text-[10px] text-[#5EEAD4] bg-[#5EEAD4]/14 px-2 py-0.5 rounded-full">
              {activePositions.length} Active
            </span>
          </div>
          <div className="text-xl font-light font-mono tracking-tight text-[#F4F7FF] mt-2">
            Bot {activePositions.filter((p) => p.ownership === "BOT").length} · Man{" "}
            {activePositions.filter((p) => p.ownership === "MANUAL").length} · Pend{" "}
            {kpis.pendingOrdersCount}
          </div>
          <div className="text-[11px] text-[#8496B8] mt-1">
            Other EA: {kpis.otherEaPositionsCount} · Magic #202601
          </div>
        </div>

        {/* 6. Next Schedule Switch — Violet Sheen Glass Card */}
        <div className="iea-glass-card-violet p-3.5 flex flex-col justify-between">
          <div className="flex items-center justify-between text-xs text-[#E5C7FF]">
            <span className="font-medium">Next Schedule Switch</span>
            <Clock className="w-3.5 h-3.5 text-[#C077FA]" />
          </div>
          <div
            className="text-2xl font-light font-mono tracking-tight text-[#F4F7FF] mt-2"
            data-testid="schedule-countdown"
          >
            {sched.nextSwitchCountdown}
          </div>
          <div className="text-[11px] text-[#B6C5E0] truncate mt-1" title={sched.nextSwitchLabel}>
            → {sched.nextSwitchLabel}
          </div>
        </div>
      </section>

      {/* =====================================================================
          MAIN TERMINAL WORKSPACE:
          SECTION (c) LIVE CHART (Center-Left, 8 cols) + SECTION (d) RIGHT COLUMN (4 cols)
      ====================================================================== */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-3.5 items-stretch">
        {/* SECTION (c): LIVE CHART (Main Feature) — stretches to fill 100% of column height */}
        <div className="xl:col-span-8 flex flex-col min-h-[550px]">
          <LiveTradingChart
            bundle={chartBundle}
            selectedSymbol={selectedSymbol}
            selectedTimeframe={selectedTimeframe}
            feedStatus={feedStatus}
            onSelectSymbol={setSelectedSymbol}
            onSelectTimeframe={setSelectedTimeframe}
          />
        </div>

        {/* SECTION (d): RIGHT COLUMN — Engine Control + Open Positions & Orders */}
        <div className="xl:col-span-4 flex flex-col gap-3.5">
          {/* d.1: Engine Control Card */}
          <section
            aria-label="Engine Control and Supervisor Status"
            className="iea-glass-card p-4 space-y-3"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Cpu className="w-4 h-4 text-[#B0F648]" />
                <h2 className="text-sm font-semibold text-[#F4F7FF]">
                  Engine Control &amp; Supervisor
                </h2>
              </div>
              <span
                className={`px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold ${
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

            {/* State / Supervisor / Warm-up telemetry strip */}
            <div className="grid grid-cols-3 gap-2 text-[11px] font-mono">
              <div className="iea-glass-tile p-2.5">
                <div className="text-[#8496B8] font-sans text-[10px]">Supervisor</div>
                <div className="text-[#F4F7FF] font-bold mt-0.5">
                  PID {eng.engine_pid ?? 15204}
                </div>
              </div>
              <div className="iea-glass-tile p-2.5">
                <div className="text-[#8496B8] font-sans text-[10px]">Bridge IPC</div>
                <div className="text-[#5EEAD4] font-bold mt-0.5">
                  PID {eng.bridge_pid ?? 14820}
                </div>
              </div>
              <div className="iea-glass-tile p-2.5">
                <div className="text-[#8496B8] font-sans text-[10px]">Warm-Up Bars</div>
                <div className="text-[#B0F648] font-bold mt-0.5">
                  {healthExt.warmupBarsLoaded}/{healthExt.warmupBarsRequired} READY
                </div>
              </div>
            </div>

            {/* Operating Mode Selector (OBSERVE, DRY_RUN, DEMO_SCALPING, DEMO_FAST, DEMO_MANUAL_ASSIST) */}
            <div>
              <div className="flex items-center justify-between text-[11px] text-[#B6C5E0] mb-1.5">
                <span className="font-medium">Operating Mode (DEMO-Locked)</span>
                <span className="font-mono text-[10px] text-[#B0F648]">LIVE_TRADING=false</span>
              </div>
              <div className="grid grid-cols-1 gap-1.5" role="radiogroup" aria-label="Select Engine Operating Mode">
                {DASHBOARD_MODES.map((m) => {
                  const active = eng.operating_mode === m.mode;
                  return (
                    <button
                      key={m.mode}
                      type="button"
                      onClick={() => handleModeSwitch(m.mode)}
                      aria-pressed={active}
                      className={`flex items-center justify-between px-3 py-1.5 rounded-xl border text-left transition-all duration-150 ${
                        active
                          ? "bg-gradient-to-r from-[#B0F648]/18 to-[#2F497C]/40 border-[#B0F648]/55 text-[#F4F7FF] shadow-[0_0_16px_rgba(176,246,72,0.12)]"
                          : "bg-[#0D1B36]/60 border-[rgba(186,214,255,0.12)] text-[#B6C5E0] hover:border-[rgba(186,214,255,0.28)] hover:text-[#F4F7FF]"
                      }`}
                    >
                      <div>
                        <div className="text-[11px] font-mono font-bold">{m.short}</div>
                        <div className="text-[10px] text-[#8496B8]">{m.desc}</div>
                      </div>
                      <span
                        className={`text-[10px] font-mono px-2 py-0.5 rounded-full ${
                          active
                            ? "bg-[#B0F648] text-[#081321] font-extrabold"
                            : "bg-[#162749] text-[#8496B8]"
                        }`}
                      >
                        {active ? "ACTIVE" : "SELECT"}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Engine Lifecycle Action Buttons */}
            <div className="grid grid-cols-4 gap-2 pt-1">
              <button
                type="button"
                disabled={busyAction !== null}
                onClick={() =>
                  executeControlAction("Start Engine", () =>
                    controlClient.startEngine(eng.operating_mode === "DRY_RUN")
                  )
                }
                className="px-2.5 py-1.5 rounded-xl bg-[#B0F648] hover:bg-[#C2F076] text-[#081321] text-[11px] font-bold inline-flex items-center justify-center space-x-1 shadow-[0_0_14px_rgba(176,246,72,0.3)] transition"
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
                className="px-2.5 py-1.5 rounded-xl bg-[#FBBF24]/20 hover:bg-[#FBBF24]/30 border border-[#FBBF24]/50 text-[#FBBF24] text-[11px] font-semibold inline-flex items-center justify-center space-x-1 transition"
              >
                <Pause className="w-3 h-3" />
                <span>{eng.pause_flag_active ? "Resume" : "Pause"}</span>
              </button>

              <button
                type="button"
                disabled={busyAction !== null}
                onClick={() =>
                  executeControlAction("Restart Engine", () => controlClient.restartEngine())
                }
                className="px-2.5 py-1.5 rounded-xl bg-[#223D6A]/80 hover:bg-[#2F497C] border border-[rgba(186,214,255,0.22)] text-[#F4F7FF] text-[11px] font-semibold inline-flex items-center justify-center space-x-1 transition"
              >
                <RotateCcw className="w-3 h-3 text-[#5EEAD4]" />
                <span>Restart</span>
              </button>

              <button
                type="button"
                disabled={busyAction !== null}
                onClick={() => setConfirmModal({ type: "EMERGENCY_FLATTEN", step: 1 })}
                className="px-2.5 py-1.5 rounded-xl bg-gradient-to-r from-[#FF5A6E] to-[#E11D48] hover:brightness-110 text-white text-[11px] font-bold inline-flex items-center justify-center space-x-1 shadow-[0_0_14px_rgba(255,90,110,0.35)] transition"
                title="Engage STOP.flag and flatten all bot positions (Two-Step Confirmation)"
              >
                <ShieldAlert className="w-3 h-3" />
                <span>Flatten</span>
              </button>
            </div>
          </section>

          {/* d.2: Open Positions & Orders Card (with Reference-Style Segmented Underline Tabs) */}
          <section
            aria-label="Open Positions and Pending Orders"
            className="flex-1 iea-glass-card p-4 flex flex-col justify-between space-y-3"
          >
            <div className="space-y-2.5">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-[#F4F7FF]">
                    Open Positions &amp; Orders ({activePositions.length})
                  </h2>
                  <p className="text-[11px] text-[#8496B8]">
                    Tighten-only stop policy enforced · Click symbol to focus chart
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => onNavigate("positions")}
                  className="text-[11px] text-[#B0F648] hover:text-[#C2F076] font-semibold"
                >
                  Full Table →
                </button>
              </div>

              {/* Reference-Style Segmented Tabs with Neon Lime Underline (Portfolio / Transactions style) */}
              <div className="flex items-center space-x-5 border-b border-[rgba(186,214,255,0.12)] text-xs">
                {(
                  [
                    { id: "ALL", label: `All Positions (${activePositions.length})` },
                    {
                      id: "BOT",
                      label: `Bot Owned (${activePositions.filter((p) => p.ownership === "BOT").length})`,
                    },
                    {
                      id: "MANUAL",
                      label: `Manual (${activePositions.filter((p) => p.ownership === "MANUAL").length})`,
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
                <div className="py-8 text-center text-xs text-[#8496B8] iea-glass-tile">
                  No open positions matching filter. Waiting for next risk-authorized setup.
                </div>
              ) : (
                <div className="space-y-2 max-h-[300px] overflow-y-auto pr-1">
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
                        ? "BOT_OWN"
                        : pos.ownership === "MANUAL"
                        ? "MANUAL"
                        : "OTHER_EA";

                    const chip = getSymbolChipSpec(pos.symbol);

                    return (
                      <div
                        key={pos.ticket}
                        className="iea-glass-tile p-3 text-xs space-y-2 hover:border-[rgba(186,214,255,0.24)] transition"
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center space-x-2">
                            {/* Reference-Style Circular Symbol Coin Chip */}
                            <span
                              className={`w-6 h-6 rounded-full text-[10px] font-extrabold inline-flex items-center justify-center shrink-0 ${chip.chipBg} ${chip.chipRing}`}
                            >
                              {chip.shortCode}
                            </span>

                            <button
                              type="button"
                              onClick={() => setSelectedSymbol(symClean)}
                              className="font-mono font-bold text-[#F4F7FF] hover:text-[#B0F648] transition"
                            >
                              {pos.symbol}
                            </button>

                            <span
                              className={`px-2 py-0.5 rounded-full font-mono font-bold text-[10px] ${
                                dir === "BUY"
                                  ? "bg-[#B0F648]/18 text-[#B0F648]"
                                  : "bg-[#FF5A6E]/20 text-[#FF5A6E]"
                              }`}
                            >
                              {dir} {pos.volume.toFixed(2)}L
                            </span>

                            <span
                              className={`px-2 py-0.5 rounded-full font-mono text-[10px] font-bold ${
                                ownerLabel === "BOT_OWN"
                                  ? "bg-[#5EEAD4]/15 text-[#5EEAD4] border border-[#5EEAD4]/30"
                                  : ownerLabel === "MANUAL"
                                  ? "bg-[#C077FA]/18 text-[#E5C7FF] border border-[#C077FA]/35"
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

                        <div className="grid grid-cols-3 gap-1.5 font-mono text-[11px] bg-[#091426]/65 rounded-xl px-2.5 py-1.5 border border-[rgba(186,214,255,0.1)]">
                          <div>
                            <span className="text-[#8496B8]">Entry:</span>{" "}
                            <span className="text-[#F4F7FF]">{pos.open_price.toFixed(digits)}</span>
                          </div>
                          <div>
                            <span className="text-[#8496B8]">SL:</span>{" "}
                            <span className="text-[#FF7A8A] font-semibold">
                              {pos.sl > 0 ? pos.sl.toFixed(digits) : "NONE"}
                            </span>
                          </div>
                          <div>
                            <span className="text-[#8496B8]">TP:</span>{" "}
                            <span className="text-[#B0F648] font-semibold">
                              {pos.tp > 0 ? pos.tp.toFixed(digits) : "-"}
                            </span>
                          </div>
                        </div>

                        {/* Position Action Controls (respecting Tighten-Only Stop Policy) */}
                        <div className="flex flex-wrap items-center justify-between gap-1 pt-0.5">
                          <div className="flex flex-wrap items-center gap-1">
                            <button
                              type="button"
                              onClick={() => handlePartialClose50(pos)}
                              aria-label={`Partial close 50% of ticket ${pos.ticket}`}
                              className="px-2.5 py-1 rounded-full bg-[#192F5A] hover:bg-[#234078] border border-[rgba(186,214,255,0.18)] text-[#F4F7FF] text-[10px] font-semibold inline-flex items-center space-x-1 transition"
                            >
                              <Scissors className="w-3 h-3 text-[#5EEAD4]" />
                              <span>Partial 50%</span>
                            </button>

                            <button
                              type="button"
                              onClick={() => handleMoveToBreakEven(pos)}
                              aria-label={`Move stop loss to break-even for ticket ${pos.ticket}`}
                              className="px-2.5 py-1 rounded-full bg-[#5EEAD4]/15 hover:bg-[#5EEAD4]/25 border border-[#5EEAD4]/40 text-[#5EEAD4] text-[10px] font-semibold transition"
                            >
                              BE+ Lock
                            </button>

                            <button
                              type="button"
                              onClick={() => openTightenSlModal(pos)}
                              aria-label={`Tighten stop loss for ticket ${pos.ticket}`}
                              className="px-2.5 py-1 rounded-full bg-[#B0F648]/16 hover:bg-[#B0F648]/28 border border-[#B0F648]/45 text-[#C2F076] text-[10px] font-semibold transition"
                            >
                              Tighten SL
                            </button>

                            {/* Explicitly Disabled Widen / Remove SL per Hard Safety Rule #5 */}
                            <button
                              type="button"
                              disabled
                              aria-disabled="true"
                              title="Hard Safety Rule #5: Tighten-Only Stop Policy blocks widening or removing Stop Loss"
                              className="px-2 py-1 rounded-full bg-[#0A152B]/60 border border-[rgba(186,214,255,0.1)] text-[#8496B8] text-[10px] font-medium cursor-not-allowed opacity-60 inline-flex items-center space-x-1"
                            >
                              <Lock className="w-2.5 h-2.5" />
                              <span>Widen/Remove SL</span>
                            </button>
                          </div>

                          <button
                            type="button"
                            onClick={() => handleCloseSinglePosition(pos)}
                            aria-label={`Close position ticket ${pos.ticket}`}
                            className="px-2.5 py-1 rounded-full bg-[#FF5A6E]/90 hover:bg-[#FF5A6E] text-white text-[10px] font-bold transition"
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

            {/* Pending Orders Summary Footer */}
            <div className="pt-2 border-t border-[rgba(186,214,255,0.12)] flex items-center justify-between text-[11px]">
              <span className="text-[#B6C5E0]">
                Pending Limit/Stop Orders:{" "}
                <strong className="font-mono text-[#F4F7FF]">{kpis.pendingOrdersCount}</strong>
              </span>
              <span className="inline-flex items-center space-x-1 text-[#B0F648] font-mono text-[10px]">
                <ShieldCheck className="w-3.5 h-3.5" />
                <span>100% SL Protected</span>
              </span>
            </div>
          </section>
        </div>
      </div>

      {/* =====================================================================
          SECTION (e): ANALYTICAL & OPERATIONAL PANELS (7 GLASS PANELS)
          1. Live Trade Timeline
          2. Risk Manager (DEMO / LIVE / PROP Profile Limits)
          3. Gold–USDJPY Inverse Coordination
          4. Schedule & Instruments
          5. System Health (EA Heartbeat, Queue Depth, CUSUM/PSI, TCA, Error Centre Count)
          6. Manual Position Adoption
          7. Recent Trades Table (Reference-Style Coin Chips & Clean Table Header)
      ====================================================================== */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3.5">
        {/* Panel 1: Live Trade Timeline (4 cols) */}
        <section
          aria-label="Live Trade Lifecycle Timeline"
          className="lg:col-span-4 iea-glass-card p-4 space-y-3"
        >
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-[#F4F7FF] flex items-center space-x-2">
              <Activity className="w-4 h-4 text-[#B0F648]" />
              <span>Live Trade Timeline</span>
            </h3>
            <span className="iea-pill-control text-[10px] font-mono text-[#5EEAD4] px-2.5 py-0.5">
              SSE Stream
            </span>
          </div>

          <div className="space-y-2 max-h-[245px] overflow-y-auto pr-1">
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
                <div
                  key={ev.id}
                  className="iea-glass-tile p-3 text-xs space-y-1.5"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center space-x-2 min-w-0">
                      <span
                        className={`w-5 h-5 rounded-full text-[9px] font-extrabold inline-flex items-center justify-center shrink-0 ${chip.chipBg}`}
                      >
                        {chip.shortCode}
                      </span>
                      <span className="font-semibold text-[#F4F7FF] truncate">{ev.title}</span>
                    </div>
                    {ev.rMultiple && (
                      <span
                        className={`px-2 py-0.5 rounded-full border font-mono text-[10px] font-bold shrink-0 ${
                          badgeStyles[ev.tone]
                        }`}
                      >
                        {ev.rMultiple}
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-[#B6C5E0] leading-snug">{ev.detail}</p>
                  <div className="flex items-center justify-between text-[10px] font-mono text-[#8496B8]">
                    <span>
                      {ev.symbol} · #{ev.ticket} · {ev.stage}
                    </span>
                    <span>{new Date(ev.timestamp).toLocaleTimeString()}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        {/* Panel 2: Risk Manager — DEMO / LIVE / PROP Profile Limits (4 cols) */}
        <section
          aria-label="Risk Manager Profile Limits"
          className="lg:col-span-4 iea-glass-card p-4 space-y-3 flex flex-col justify-between"
        >
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-[#F4F7FF] flex items-center space-x-2">
                <Shield className="w-4 h-4 text-[#B0F648]" />
                <span>Risk Manager (DEMO / PROP / LIVE Profiles)</span>
              </h3>
              <button
                type="button"
                onClick={() => onNavigate("risk")}
                className="text-[11px] text-[#B0F648] hover:text-[#C2F076] font-semibold"
              >
                Details →
              </button>
            </div>

            <div className="overflow-x-auto rounded-xl border border-[rgba(186,214,255,0.12)]">
              <table className="w-full text-left text-xs iea-glass-table">
                <thead>
                  <tr>
                    <th className="py-2.5 pl-3 pr-2">Profile</th>
                    <th className="py-2.5 pr-2">Risk/Trade</th>
                    <th className="py-2.5 pr-2">Daily Limit</th>
                    <th className="py-2.5 pr-2">Max DD</th>
                    <th className="py-2.5 pr-3">Status</th>
                  </tr>
                </thead>
                <tbody className="font-mono text-[11px]">
                  {dash.riskProfiles.map((rp) => (
                    <tr key={rp.profile} className={rp.active ? "!bg-[#B0F648]/10" : ""}>
                      <td className="py-2.5 pl-3 pr-2 font-bold text-[#F4F7FF]">{rp.profile}</td>
                      <td className="py-2.5 pr-2 text-[#B0F648] font-semibold">
                        {rp.riskPerTradePct.toFixed(2)}%
                      </td>
                      <td className="py-2.5 pr-2 text-[#F4F7FF]">{rp.dailyLossLimitPct.toFixed(1)}%</td>
                      <td className="py-2.5 pr-2 text-[#F4F7FF]">{rp.maxTotalDrawdownPct.toFixed(1)}%</td>
                      <td className="py-2.5 pr-3 font-sans">
                        {rp.active ? (
                          <span className="px-2 py-0.5 rounded-full bg-[#B0F648] text-[#081321] text-[10px] font-extrabold">
                            ACTIVE
                          </span>
                        ) : rp.locked ? (
                          <span className="px-2 py-0.5 rounded-full bg-[#162749] text-[#B6C5E0] border border-[rgba(186,214,255,0.2)] text-[10px] font-semibold inline-flex items-center space-x-1">
                            <Lock className="w-2.5 h-2.5 text-[#FBBF24]" />
                            <span>LOCKED</span>
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 rounded-full bg-white/5 text-[#8496B8] text-[10px]">
                            STANDBY
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="iea-glass-tile p-3 text-[11px] flex items-center justify-between">
            <span className="text-[#B6C5E0]">Portfolio Risk Budget Used:</span>
            <span className="font-mono font-bold text-[#B0F648]">
              1.15% / 6.00% (Cap Available: 4.85%)
            </span>
          </div>
        </section>

        {/* Panel 3: Gold–USDJPY Inverse Coordination + Panel 4: Schedule & Instruments (4 cols) */}
        <div className="lg:col-span-4 flex flex-col gap-3.5">
          {/* Panel 3: Gold–USDJPY Inverse Coordination */}
          <section
            aria-label="Gold and USDJPY Inverse Correlation Coordination"
            className="iea-glass-card p-4 space-y-2.5"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-[#F4F7FF] flex items-center space-x-2">
                <GitCompare className="w-4 h-4 text-[#C077FA]" />
                <span>Gold–USDJPY Inverse Coordination</span>
              </h3>
              <span className="px-2.5 py-0.5 rounded-full bg-[#B0F648]/18 text-[#B0F648] border border-[#B0F648]/40 font-mono text-[10px] font-bold">
                {inv.coherenceState}
              </span>
            </div>

            <div className="grid grid-cols-3 gap-2 font-mono text-xs">
              <div className="iea-glass-tile p-2.5">
                <div className="text-[10px] font-sans text-[#8496B8]">60m Rolling r</div>
                <div className="text-[#B0F648] font-bold mt-0.5">{inv.rollingCorrelation60m}</div>
              </div>
              <div className="iea-glass-tile p-2.5">
                <div className="text-[10px] font-sans text-[#8496B8]">XAU / JPY Bias</div>
                <div className="text-[#F4F7FF] font-bold mt-0.5">
                  {inv.goldBias === "BULLISH" ? "XAU↑" : "XAU↓"} /{" "}
                  {inv.usdjpyBias === "BEARISH" ? "JPY↓" : "JPY↑"}
                </div>
              </div>
              <div className="iea-glass-tile p-2.5">
                <div className="text-[10px] font-sans text-[#8496B8]">Hedge Gate</div>
                <div className="text-[#5EEAD4] font-bold mt-0.5">{inv.hedgeGateStatus}</div>
              </div>
            </div>

            <p className="text-[11px] text-[#B6C5E0] leading-snug">{inv.note}</p>
          </section>

          {/* Panel 4: Schedule & Instruments Matrix (Reference-Style Small Stat Tiles with Green Percentage / Status) */}
          <section
            aria-label="Schedule and Approved Instruments Matrix"
            className="iea-glass-card p-4 space-y-2.5"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-[#F4F7FF] flex items-center space-x-2">
                <Layers className="w-4 h-4 text-[#5EEAD4]" />
                <span>Schedule &amp; Instruments</span>
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
                const isActiveInSchedule = sched.activeInstruments.includes(sym);
                const chip = getSymbolChipSpec(sym);
                const active = selectedSymbol === sym;
                return (
                  <button
                    key={sym}
                    type="button"
                    onClick={() => setSelectedSymbol(sym)}
                    className={`p-2.5 rounded-2xl border text-left transition-all duration-150 ${
                      active
                        ? "bg-gradient-to-br from-[#B0F648]/18 to-[#223D6A]/70 border-[#B0F648]/55 shadow-[0_0_16px_rgba(176,246,72,0.14)]"
                        : "iea-glass-tile hover:border-[rgba(186,214,255,0.28)]"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span
                        className={`w-6 h-6 rounded-full text-[10px] font-extrabold inline-flex items-center justify-center ${chip.chipBg}`}
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
                    <div className="font-mono font-bold text-[#F4F7FF] mt-1.5">{sym}</div>
                    <div className="text-[10px] text-[#8496B8]">
                      {isActiveInSchedule ? "Active Session" : "Standby / Crypto"}
                    </div>
                  </button>
                );
              })}
            </div>
          </section>
        </div>
      </div>

      {/* Bottom Row of Section (e): System Health + Manual Position Adoption + Recent Trades Table */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3.5">
        {/* Panel 5: System Health (EA Heartbeat, Queue Depth, CUSUM/PSI, TCA, Error Centre Count) (4 cols) */}
        <section
          aria-label="System Health and Quantitative Drift Telemetry"
          className="lg:col-span-4 iea-glass-card p-4 space-y-3 flex flex-col justify-between"
        >
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-[#F4F7FF] flex items-center space-x-2">
                <Gauge className="w-4 h-4 text-[#B0F648]" />
                <span>System Health &amp; Drift Guards</span>
              </h3>
              <button
                type="button"
                onClick={() => onNavigate("errors")}
                className="text-[11px] text-[#B0F648] hover:text-[#C2F076] font-semibold"
              >
                Error Centre ({healthExt.activeErrorCount}) →
              </button>
            </div>

            <div className="grid grid-cols-2 gap-2.5 text-xs font-mono">
              <div className="iea-glass-tile p-3">
                <div className="text-[10px] font-sans text-[#8496B8]">EA Heartbeat Latency</div>
                <div className="text-[#B0F648] font-bold mt-1">
                  {healthExt.eaHeartbeatAgeMs} ms ({healthExt.eaHeartbeatStatus})
                </div>
              </div>

              <div className="iea-glass-tile p-3">
                <div className="text-[10px] font-sans text-[#8496B8]">ZMQ Queue Depth</div>
                <div className="text-[#F4F7FF] font-bold mt-1">
                  {healthExt.outboundQueueDepth} msgs (0 backlog)
                </div>
              </div>

              <div className="iea-glass-tile p-3">
                <div className="text-[10px] font-sans text-[#8496B8]">CUSUM / PSI Drift</div>
                <div className="text-[#5EEAD4] font-bold mt-1">
                  {healthExt.cusumDecayScore} / PSI {healthExt.psiFeatureDrift}
                </div>
              </div>

              <div className="iea-glass-tile p-3">
                <div className="text-[10px] font-sans text-[#8496B8]">TCA Slippage / Fill</div>
                <div className="text-[#B0F648] font-bold mt-1">
                  {healthExt.tcaAvgSlippageBps} bps · {healthExt.tcaFillLatencyMs} ms
                </div>
              </div>
            </div>
          </div>

          <div className="flex items-center justify-between iea-glass-tile px-3 py-2.5 text-xs">
            <span className="text-[#B6C5E0]">Error Centre Active Alerts:</span>
            <span
              className={`font-mono font-bold px-2.5 py-0.5 rounded-full ${
                healthExt.activeErrorCount === 0
                  ? "bg-[#B0F648]/20 text-[#B0F648]"
                  : "bg-[#FF5A6E]/25 text-[#FF5A6E]"
              }`}
            >
              {healthExt.activeErrorCount} ACTIVE
            </span>
          </div>
        </section>

        {/* Panel 6: Manual Position Adoption (3 cols) */}
        <section
          aria-label="Manual Position Adoption and Protection"
          className="lg:col-span-3 iea-glass-card p-4 space-y-3 flex flex-col justify-between"
        >
          <div className="space-y-2.5">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-[#F4F7FF] flex items-center space-x-2">
                <ShieldCheck className="w-4 h-4 text-[#C077FA]" />
                <span>Manual Position Adoption</span>
              </h3>
              <span className="text-[10px] font-mono text-[#E5C7FF] bg-[#C077FA]/20 border border-[#C077FA]/35 px-2 py-0.5 rounded-full">
                {dash.manualAdoptionQueue.length} Manual
              </span>
            </div>

            {dash.manualAdoptionQueue.length === 0 ? (
              <div className="py-6 text-center text-xs text-[#8496B8] iea-glass-tile px-2">
                No manual MT5 positions detected. Any discretionary trade opened in MT5 appears here for automated tighten-only SL adoption.
              </div>
            ) : (
              <div className="space-y-2">
                {dash.manualAdoptionQueue.map((mp) => {
                  const chip = getSymbolChipSpec(mp.symbol);
                  return (
                    <div
                      key={mp.ticket}
                      className="iea-glass-tile p-3 text-xs space-y-2"
                    >
                      <div className="flex items-center justify-between font-mono">
                        <div className="flex items-center space-x-2">
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
                      <div className="text-[11px] text-[#B6C5E0]">{mp.statusNote}</div>
                      <div className="flex items-center justify-between pt-1">
                        <span className="font-mono text-[10px] text-[#8496B8]">
                          SL {mp.sl > 0 ? mp.sl : mp.suggestedProtectiveSl} / TP {mp.tp > 0 ? mp.tp : mp.suggestedTp1}
                        </span>
                        <button
                          type="button"
                          onClick={() =>
                            executeControlAction(`Adopt & Protect #${mp.ticket}`, () =>
                              controlClient.modifyPosition(
                                mp.ticket,
                                mp.sl > 0 ? mp.sl : mp.suggestedProtectiveSl,
                                mp.tp > 0 ? mp.tp : mp.suggestedTp1
                              )
                            )
                          }
                          className="px-2.5 py-1 rounded-full bg-[#B0F648] hover:bg-[#C2F076] text-[#081321] text-[10px] font-extrabold transition"
                        >
                          Sync Guard SL
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div className="text-[11px] text-[#B6C5E0] iea-glass-tile px-3 py-2">
            Mode <strong className="font-mono text-[#5EEAD4]">DEMO_MANUAL_ASSIST</strong> attaches break-even &amp; trailing guards to manual tickets.
          </div>
        </section>

        {/* Panel 7: Recent Trades Table (5 cols — Reference-Style Table with Circular Coin Chips) */}
        <section
          aria-label="Recent Closed Trades Table"
          className="lg:col-span-5 iea-glass-card p-4 space-y-3"
        >
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold text-[#F4F7FF] flex items-center space-x-2">
                <History className="w-4 h-4 text-[#B0F648]" />
                <span>Recent Trades ({dash.recentTrades.length})</span>
              </h3>
              <p className="text-[11px] text-[#8496B8]">Verified DEMO execution audit log</p>
            </div>
            <button
              type="button"
              onClick={() => onNavigate("history")}
              className="iea-pill-control px-3 py-1 text-[11px] text-[#B0F648] font-semibold"
            >
              Export / Full History →
            </button>
          </div>

          <div className="overflow-x-auto rounded-xl border border-[rgba(186,214,255,0.12)]">
            <table className="w-full text-left text-xs iea-glass-table">
              <thead>
                <tr>
                  <th className="py-2.5 pl-3 pr-2">#</th>
                  <th className="py-2.5 pr-2">Instrument</th>
                  <th className="py-2.5 pr-2">Side</th>
                  <th className="py-2.5 pr-2">Entry → Exit</th>
                  <th className="py-2.5 pr-2">Net P&amp;L</th>
                  <th className="py-2.5 pr-3">Outcome</th>
                </tr>
              </thead>
              <tbody className="font-mono text-[11px]">
                {dash.recentTrades.slice(0, 6).map((t, idx) => {
                  const chip = getSymbolChipSpec(t.symbol);
                  return (
                    <tr key={t.id}>
                      <td className="py-2.5 pl-3 pr-2 text-[#8496B8]">{idx + 1}</td>
                      <td className="py-2.5 pr-2">
                        <div className="flex items-center space-x-2">
                          <span
                            className={`w-6 h-6 rounded-full text-[10px] font-extrabold inline-flex items-center justify-center shrink-0 ${chip.chipBg}`}
                          >
                            {chip.shortCode}
                          </span>
                          <div>
                            <div className="font-bold text-[#F4F7FF] leading-tight">{t.symbol}</div>
                            <div className="text-[9px] font-sans text-[#8496B8]">#{t.ticket}</div>
                          </div>
                        </div>
                      </td>
                      <td
                        className={`py-2.5 pr-2 font-bold ${
                          t.direction === "BUY" ? "text-[#B0F648]" : "text-[#FF5A6E]"
                        }`}
                      >
                        {t.direction} {t.volume.toFixed(2)}
                      </td>
                      <td className="py-2.5 pr-2 text-[#B6C5E0]">
                        {t.open_price} → {t.close_price}
                      </td>
                      <td
                        className={`py-2.5 pr-2 font-bold ${
                          t.profit >= 0 ? "text-[#B0F648]" : "text-[#FF5A6E]"
                        }`}
                      >
                        {t.profit >= 0 ? "+" : ""}${t.profit.toFixed(2)}
                      </td>
                      <td className="py-2.5 pr-3 font-sans text-[10px]">
                        <span
                          className={`px-2 py-0.5 rounded-full ${
                            t.profit >= 0
                              ? "bg-[#B0F648]/14 text-[#C2F076] border border-[#B0F648]/30"
                              : "bg-[#FF5A6E]/15 text-[#FF7A8A] border border-[#FF5A6E]/30"
                          }`}
                        >
                          {t.status}
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
          TWO-STEP CONFIRMATION MODAL (Close All Bot Positions / Emergency Flatten)
          Hard Safety Rule #5: Keep two-step confirmation for Close all / flatten
      ====================================================================== */}
      {confirmModal && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="two-step-confirm-title"
          className="fixed inset-0 z-50 bg-[#050C1A]/80 backdrop-blur-md flex items-center justify-center p-4"
        >
          <div className="iea-glass-card border-[#FF5A6E]/60 p-5 max-w-md w-full space-y-3.5 shadow-2xl">
            <div className="flex items-center space-x-2.5 text-[#FF5A6E]">
              <ShieldAlert className="w-5 h-5 shrink-0" />
              <h3 id="two-step-confirm-title" className="text-sm font-bold text-[#F4F7FF]">
                {confirmModal.type === "CLOSE_ALL_BOT"
                  ? `Two-Step Confirmation (Step ${confirmModal.step} of 2): Close All Bot Positions`
                  : `Two-Step Confirmation (Step ${confirmModal.step} of 2): Emergency Flatten & STOP.flag`}
              </h3>
            </div>

            {confirmModal.step === 1 ? (
              <p className="text-xs text-[#B6C5E0] leading-relaxed">
                Step 1 Verification: You are requesting to liquidate{" "}
                <strong className="text-[#F4F7FF]">
                  {activePositions.filter((p) => p.ownership === "BOT").length} bot-owned DEMO positions
                </strong>{" "}
                at market price via existing endpoint{" "}
                <code className="text-[#FF7A8A]">
                  {confirmModal.type === "CLOSE_ALL_BOT"
                    ? "POST /api/trades/close-all-bot"
                    : "POST /api/engine/emergency-stop"}
                </code>
                . Manual positions will remain untouched. Proceed to final confirmation?
              </p>
            ) : (
              <div className="p-3.5 rounded-xl bg-[#FF5A6E]/18 border border-[#FF5A6E]/50 text-xs text-[#FFD9DF] space-y-1">
                <div className="font-bold">Step 2 Final Authorization:</div>
                <div>
                  Click <strong>Execute Immediate Flatten</strong> below to transmit confirmed closure orders to MT5 DEMO account{" "}
                  <span className="font-mono">{dash.maskedAccount}</span>.
                </div>
              </div>
            )}

            <div className="flex items-center justify-end space-x-2.5 pt-2">
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
                className="px-4 py-1.5 rounded-full bg-gradient-to-r from-[#FF5A6E] to-[#E11D48] hover:brightness-110 text-xs font-bold text-white shadow-[0_4px_16px_rgba(255,90,110,0.4)]"
              >
                {confirmModal.step === 1
                  ? "Step 1: Verify & Continue →"
                  : "Step 2: Execute Immediate Flatten"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* =====================================================================
          TIGHTEN-ONLY STOP LOSS MODIFICATION MODAL
          Hard Safety Rule #5: Rejects widening or removing SL
      ====================================================================== */}
      {slModalPos && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="tighten-sl-modal-title"
          className="fixed inset-0 z-50 bg-[#050C1A]/80 backdrop-blur-md flex items-center justify-center p-4"
        >
          <div className="iea-glass-card p-5 max-w-md w-full space-y-3.5 shadow-2xl">
            <div className="flex items-center justify-between">
              <h3 id="tighten-sl-modal-title" className="text-sm font-bold text-[#F4F7FF]">
                Tighten-Only SL / TP — #{slModalPos.ticket} ({slModalPos.symbol} {slModalPos.direction})
              </h3>
              <span className="px-2.5 py-0.5 rounded-full bg-[#B0F648]/20 text-[#B0F648] text-[10px] font-mono font-bold">
                TIGHTEN-ONLY POLICY
              </span>
            </div>

            <div className="text-xs text-[#B6C5E0] iea-glass-tile p-3 font-mono space-y-1">
              <div>
                Entry: <strong className="text-[#F4F7FF]">{slModalPos.open_price}</strong> · Current Price:{" "}
                <strong className="text-[#F4F7FF]">{slModalPos.current_price}</strong>
              </div>
              <div>
                Current SL: <strong className="text-[#FF7A8A]">{slModalPos.sl}</strong> (Cannot be widened or set to 0)
              </div>
            </div>

            <div className="space-y-2.5 text-xs">
              <label className="block">
                <span className="text-[#B6C5E0] font-semibold">
                  Proposed Tighter Stop Loss ({slModalPos.direction === "BUY" ? `>= ${slModalPos.sl}` : `<= ${slModalPos.sl}`})
                </span>
                <input
                  type="number"
                  step="any"
                  value={proposedSlInput}
                  onChange={(e) => setProposedSlInput(e.target.value)}
                  className="w-full mt-1 bg-[#091426]/80 border border-[rgba(186,214,255,0.22)] rounded-xl px-3 py-2 text-[#F4F7FF] font-mono"
                />
              </label>

              <label className="block">
                <span className="text-[#B6C5E0] font-semibold">Take Profit Target</span>
                <input
                  type="number"
                  step="any"
                  value={proposedTpInput}
                  onChange={(e) => setProposedTpInput(e.target.value)}
                  className="w-full mt-1 bg-[#091426]/80 border border-[rgba(186,214,255,0.22)] rounded-xl px-3 py-2 text-[#F4F7FF] font-mono"
                />
              </label>
            </div>

            {!slValidation.allowed && (
              <div className="p-3 rounded-xl bg-[#FF5A6E]/20 border border-[#FF5A6E]/50 text-[11px] text-[#FFD9DF]">
                {slValidation.reason}
              </div>
            )}

            <div className="flex items-center justify-end space-x-2.5 pt-2">
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
                Apply Tightened SL
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
      onActionMessage(`${label}: ${res.message || "Completed"}`, res.success === false);
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
          <div>
            <h2 className="text-lg font-light text-[#F4F7FF] flex items-center space-x-2">
              <Cpu className="w-5 h-5 text-[#B0F648]" />
              <span>Trading Engine Lifecycle Controller</span>
            </h2>
            <p className="text-xs text-[#B6C5E0] mt-1">
              Controls the single authoritative <code>scripts/start_bot.py</code> &amp; <code>scripts/run_bridge_server.py</code> processes.
            </p>
          </div>
          <div className="flex items-center space-x-2">
            <label className="iea-pill-control flex items-center space-x-2 text-xs text-[#F4F7FF] px-3.5 py-1.5 cursor-pointer">
              <input
                type="checkbox"
                checked={dryRunChoice}
                onChange={(e) => setDryRunChoice(e.target.checked)}
                className="rounded border-[rgba(186,214,255,0.3)] accent-[#B0F648]"
              />
              <span>Dry-Run Mode</span>
            </label>
          </div>
        </div>

        <div className="flex flex-wrap gap-2.5 mt-5">
          <button
            disabled={busy || eng?.engine_running}
            onClick={() => runAction("Start Engine", () => controlClient.startEngine(dryRunChoice))}
            className="px-4 py-2 bg-[#B0F648] hover:bg-[#C2F076] disabled:opacity-40 text-[#081321] text-xs font-bold rounded-full flex items-center space-x-1.5 shadow-[0_0_16px_rgba(176,246,72,0.3)]"
          >
            <Play className="w-4 h-4" />
            <span>Start Engine</span>
          </button>

          <button
            disabled={busy}
            onClick={() =>
              runAction(
                eng?.pause_flag_active ? "Resume Entries" : "Pause Entries",
                () => (eng?.pause_flag_active ? controlClient.resumeEntries() : controlClient.pauseEntries())
              )
            }
            className="px-4 py-2 bg-[#FBBF24]/20 hover:bg-[#FBBF24]/30 border border-[#FBBF24]/55 disabled:opacity-40 text-[#FBBF24] text-xs font-semibold rounded-full flex items-center space-x-1.5"
          >
            <Pause className="w-4 h-4" />
            <span>{eng?.pause_flag_active ? "Resume Entries" : "Pause Entries"}</span>
          </button>

          <button
            disabled={busy || !eng?.engine_running}
            onClick={() => runAction("Stop Engine", () => controlClient.stopEngine())}
            className="iea-pill-control px-4 py-2 disabled:opacity-40 text-[#F4F7FF] text-xs font-semibold flex items-center space-x-1.5"
          >
            <Square className="w-4 h-4 text-[#FF5A6E]" />
            <span>Stop Engine</span>
          </button>

          <button
            disabled={busy}
            onClick={() => runAction("Restart Engine", () => controlClient.restartEngine())}
            className="iea-pill-control px-4 py-2 disabled:opacity-40 text-[#5EEAD4] text-xs font-semibold flex items-center space-x-1.5"
          >
            <RotateCcw className="w-4 h-4" />
            <span>Restart Engine</span>
          </button>

          {!eng?.stop_flag_active ? (
            <button
              disabled={busy}
              onClick={() => {
                if (window.confirm("Engage Emergency STOP.flag? This immediately halts all new order entries.")) {
                  runAction("Emergency Stop", () => controlClient.emergencyStop(false, true));
                }
              }}
              className="px-4 py-2 bg-gradient-to-r from-[#FF5A6E] to-[#E11D48] hover:brightness-110 disabled:opacity-40 text-white text-xs font-bold rounded-full flex items-center space-x-1.5 ml-auto shadow-[0_4px_16px_rgba(255,90,110,0.35)]"
            >
              <ShieldAlert className="w-4 h-4" />
              <span>Emergency Stop</span>
            </button>
          ) : (
            <button
              disabled={busy}
              onClick={() => {
                if (window.confirm("Clear STOP.flag kill switch? Ensure MT5 terminal and open positions are verified first.")) {
                  runAction("Clear STOP.flag", () => controlClient.clearEmergencyStop(true));
                }
              }}
              className="px-4 py-2 bg-[#B0F648] hover:bg-[#C2F076] disabled:opacity-40 text-[#081321] text-xs font-bold rounded-full flex items-center space-x-1.5 ml-auto"
            >
              <CheckCircle2 className="w-4 h-4" />
              <span>Clear STOP.flag</span>
            </button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5">
        <div className="iea-glass-card p-4 text-xs space-y-1.5">
          <div className="text-[#8496B8]">Process Supervision</div>
          <div>Bridge Running: <span className="font-mono text-[#F4F7FF]">{String(eng?.bridge_running ?? false)}</span> (PID {eng?.bridge_pid ?? "-"})</div>
          <div>Engine Running: <span className="font-mono text-[#F4F7FF]">{String(eng?.engine_running ?? false)}</span> (PID {eng?.engine_pid ?? "-"})</div>
        </div>
        <div className="iea-glass-card p-4 text-xs space-y-1.5">
          <div className="text-[#8496B8]">Safety Flags</div>
          <div>STOP.flag: <span className={`font-mono font-bold ${eng?.stop_flag_active ? "text-[#FF5A6E]" : "text-[#B0F648]"}`}>{eng?.stop_flag_active ? "ACTIVE" : "CLEAR"}</span></div>
          <div>state/PAUSE: <span className={`font-mono font-bold ${eng?.pause_flag_active ? "text-[#FBBF24]" : "text-[#B0F648]"}`}>{eng?.pause_flag_active ? "PAUSED" : "ACTIVE"}</span></div>
        </div>
        <div className="iea-glass-card-lime p-4 text-xs space-y-1.5">
          <div className="text-[#C2F076]">Execution Mode Lock</div>
          <div>Operating Mode: <span className="font-mono text-[#F4F7FF] font-bold">{eng?.operating_mode || "DEMO_SCALPING"}</span></div>
          <div>Live Trading: <span className="font-mono text-[#B0F648] font-bold">LOCKED (DEMO ONLY)</span></div>
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
      onActionMessage("Market Watch synchronized with MT5.");
    } catch (e: any) {
      onActionMessage(`Market sync failed: ${e.message}`, true);
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="iea-glass-card p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-light text-[#F4F7FF] flex items-center space-x-2">
            <Activity className="w-5 h-5 text-[#B0F648]" />
            <span>Live Market Watch &amp; Broker Specifications</span>
          </h2>
          <p className="text-xs text-[#8496B8] mt-0.5">Real-time MT5 symbol feed and margin contract metrics</p>
        </div>
        <button
          disabled={syncing}
          onClick={handleSync}
          className="px-4 py-1.5 bg-[#B0F648] hover:bg-[#C2F076] text-[#081321] text-xs font-bold rounded-full flex items-center space-x-1.5 shadow-[0_0_16px_rgba(176,246,72,0.28)]"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${syncing ? "animate-spin" : ""}`} />
          <span>Sync Quotes</span>
        </button>
      </div>

      <div className="overflow-x-auto rounded-2xl border border-[rgba(186,214,255,0.12)]">
        <table className="w-full text-left text-xs iea-glass-table">
          <thead>
            <tr>
              <th className="py-3 pl-4 pr-3">#</th>
              <th className="py-3 pr-3">Instrument</th>
              <th className="py-3 pr-3">Bid</th>
              <th className="py-3 pr-3">Ask</th>
              <th className="py-3 pr-3">Spread (pts)</th>
              <th className="py-3 pr-3">Digits</th>
              <th className="py-3 pr-3">Min / Max / Step Lot</th>
              <th className="py-3 pr-4">Stops Level</th>
            </tr>
          </thead>
          <tbody className="font-mono">
            {symbols.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-8 text-center text-[#8496B8] font-sans">
                  No symbol quotes cached yet. Connect MT5 terminal and click Sync Quotes.
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
        <div>
          <h2 className="text-lg font-light text-[#F4F7FF] flex items-center space-x-2">
            <Zap className="w-5 h-5 text-[#B0F648]" />
            <span>Unfiltered Signal Pipeline &amp; Risk Authorization</span>
          </h2>
          <p className="text-xs text-[#B6C5E0] mt-1">
            Strategy layer runs unfiltered (<code>LEGACY_FILTERS_ENABLED=false</code>). All entries pass directly to independent <code>PortfolioRiskEngine</code>.
          </p>
        </div>
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
                <th className="py-3 pr-3">Instrument</th>
                <th className="py-3 pr-3">Direction</th>
                <th className="py-3 pr-3">Decision</th>
                <th className="py-3 pr-3">Lot</th>
                <th className="py-3 pr-3">Risk %</th>
                <th className="py-3 pr-4">Reason</th>
              </tr>
            </thead>
            <tbody>
              {decisions.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-[#8496B8]">
                    No signal/risk authorization events recorded yet.
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
                          {d.approved ? "APPROVED" : "BLOCKED"}
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
