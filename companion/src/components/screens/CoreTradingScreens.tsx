import React, { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertOctagon,
  AlertTriangle,
  ArrowUpDown,
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
  Radio,
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

  // Partial Close 50% using existing IPC.closePosition(ticket, volume * 0.5) or controlClient.closePosition
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
    <div className="space-y-3 text-slate-100">
      {/* Connection / Stale-Data / Emergency Banner States */}
      {feedStatus === "DISCONNECTED" && (
        <div
          role="alert"
          className="flex items-center justify-between px-3.5 py-2 rounded-xl bg-rose-950/75 border border-rose-500/50 text-xs text-rose-100"
        >
          <div className="flex items-center space-x-2">
            <WifiOff className="w-4 h-4 text-rose-400 shrink-0" />
            <span>
              <strong>Control Service Disconnected (127.0.0.1:8765)</strong> — Displaying cached DEMO state. Verify Python Control Service daemon.
            </span>
          </div>
          <button
            type="button"
            onClick={() => onRefresh()}
            className="px-2.5 py-1 rounded bg-rose-600 hover:bg-rose-500 text-white font-semibold"
          >
            Retry Reconnect
          </button>
        </div>
      )}

      {feedStatus === "STALE" && (
        <div
          role="alert"
          className="flex items-center justify-between px-3.5 py-2 rounded-xl bg-amber-950/75 border border-amber-500/50 text-xs text-amber-100"
        >
          <div className="flex items-center space-x-2">
            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
            <span>
              <strong>Stale Telemetry Warning</strong> — Last MT5 sync heartbeat exceeded 15s threshold.
            </span>
          </div>
          <button
            type="button"
            onClick={() => onRefresh()}
            className="px-2.5 py-1 rounded bg-amber-600 hover:bg-amber-500 text-white font-semibold"
          >
            Force Sync
          </button>
        </div>
      )}

      {eng.stop_flag_active && (
        <div
          role="alert"
          className="flex items-center justify-between px-3.5 py-2 rounded-xl bg-rose-950/85 border border-rose-500/60 text-xs"
        >
          <div className="flex items-center space-x-2.5">
            <ShieldAlert className="w-4 h-4 text-rose-400 shrink-0" />
            <div>
              <span className="font-bold text-rose-200">EMERGENCY STOP.flag ENGAGED</span>
              <span className="text-rose-300 ml-2">All new order entries are hard-blocked until cleared.</span>
            </div>
          </div>
          <button
            type="button"
            onClick={() =>
              executeControlAction("Clear STOP.flag", () => controlClient.clearEmergencyStop(true))
            }
            className="px-2.5 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-semibold"
          >
            Clear STOP.flag
          </button>
        </div>
      )}

      {/* =====================================================================
          SECTION (a): TOP STATUS BAR
          MT5 connection (masked account ****0001), DEMO + LIVE_TRADING_ENABLED=false badge,
          active schedule mode (WEEKDAY_GOLD_MODE / WEEKEND_BTC_MODE), session + UTC clock,
          bridge ports 5555/5556, Telegram status, Pause / Stop / Close all.
      ====================================================================== */}
      <section
        aria-label="Terminal Top Status Bar"
        className="flex flex-wrap items-center justify-between gap-2 px-3.5 py-2.5 bg-[#0b1017] border border-slate-800/90 rounded-xl shadow-sm"
      >
        {/* Left telemetry badges */}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          {/* MT5 Connection + Masked Account ****0001 */}
          <div className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-lg bg-slate-900 border border-slate-800">
            <Wifi className="w-3.5 h-3.5 text-emerald-400" />
            <span className="font-semibold text-slate-200">MT5</span>
            <span className="font-mono font-bold text-emerald-300" data-testid="masked-account-badge">
              {dash.maskedAccount}
            </span>
            <span className="text-slate-400 text-[11px]">({effectiveStatus.mt5.account.broker})</span>
          </div>

          {/* Hard Safety Lock Badge: DEMO • LIVE_TRADING_ENABLED=false */}
          <div
            data-testid="demo-lock-badge"
            className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-lg bg-emerald-950/80 border border-emerald-500/50 text-emerald-200 font-mono text-[11px] font-bold"
            title="Hard Safety Rule: execution_mode=DEMO and LIVE_TRADING_ENABLED=false are permanently locked"
          >
            <Lock className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
            <span>DEMO</span>
            <span className="text-emerald-400">·</span>
            <span>LIVE_TRADING_ENABLED=false</span>
          </div>

          {/* Active Schedule Mode Badge (WEEKDAY_GOLD_MODE / WEEKEND_BTC_MODE) */}
          <div
            data-testid="schedule-mode-badge"
            className={`inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-lg border font-mono text-[11px] font-bold ${
              sched.scheduleMode === "WEEKDAY_GOLD_MODE"
                ? "bg-amber-950/60 border-amber-500/45 text-amber-200"
                : "bg-sky-950/60 border-sky-500/45 text-sky-200"
            }`}
          >
            <Clock className="w-3.5 h-3.5 shrink-0" />
            <span>{sched.scheduleMode}</span>
          </div>

          {/* Session + Live UTC Clock */}
          <div className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-lg bg-slate-900 border border-slate-800 text-[11px]">
            <span className="text-sky-300 font-semibold">{sched.sessionName}</span>
            <span className="text-slate-600">|</span>
            <span className="font-mono text-slate-200" data-testid="utc-clock">
              {sched.utcClockText}
            </span>
          </div>

          {/* Bridge Ports 5555 / 5556 */}
          <div className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-lg bg-slate-900 border border-slate-800 font-mono text-[11px]">
            <span className="w-2 h-2 rounded-full bg-emerald-400" />
            <span className="text-slate-300">ZMQ Bridge</span>
            <span className="text-emerald-300 font-bold">5555/5556</span>
          </div>

          {/* Telegram Status */}
          <button
            type="button"
            onClick={() =>
              executeControlAction("Test Telegram", () => controlClient.testTelegram(false))
            }
            aria-label="Telegram status and quick connectivity test"
            className="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 text-[11px] text-slate-200 transition"
          >
            <Send className="w-3 h-3 text-sky-400" />
            <span>Telegram:</span>
            <span className="text-emerald-300 font-semibold">READY</span>
          </button>
        </div>

        {/* Right: Quick Action Controls (Pause / Stop / Close All with Two-Step Confirmation) */}
        <div className="flex items-center gap-1.5">
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
            className="px-2.5 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 disabled:opacity-40 text-white text-xs font-semibold inline-flex items-center space-x-1 transition"
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
            className="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 disabled:opacity-40 text-slate-100 text-xs font-semibold inline-flex items-center space-x-1 transition"
          >
            <Square className="w-3.5 h-3.5 text-rose-400" />
            <span>Stop</span>
          </button>

          <button
            type="button"
            disabled={busyAction !== null}
            onClick={() => setConfirmModal({ type: "CLOSE_ALL_BOT", step: 1 })}
            aria-label="Close all bot-owned positions (two-step confirmation)"
            className="px-3 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-500 disabled:opacity-40 text-white text-xs font-bold inline-flex items-center space-x-1.5 shadow-xs transition"
          >
            <XCircle className="w-3.5 h-3.5" />
            <span>Close All</span>
          </button>
        </div>
      </section>

      {/* =====================================================================
          SECTION (b): KPI ROW (6 CARDS)
          1. Balance / Equity
          2. Today P&L (+R)
          3. Daily Loss Used vs Limit
          4. Total Drawdown vs Cap
          5. Open Positions (Bot / Manual / Pending)
          6. Next Schedule Switch
      ====================================================================== */}
      <section aria-label="Account and Risk Key Performance Indicators" className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-2.5">
        {/* 1. Balance / Equity */}
        <div className="bg-[#0b1017] border border-slate-800/90 rounded-xl p-3">
          <div className="flex items-center justify-between text-[11px] text-slate-400 uppercase tracking-wider">
            <span>Balance / Equity</span>
            <span className="font-mono text-[10px] text-emerald-300 bg-emerald-500/10 px-1.5 py-0.5 rounded">
              1:{effectiveStatus.mt5.account.leverage}
            </span>
          </div>
          <div className="text-lg font-mono font-bold text-slate-100 mt-1">
            ${kpis.equity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="text-[11px] font-mono text-slate-300 mt-0.5 flex items-center justify-between">
            <span>Bal: ${kpis.balance.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
            <span className={kpis.floatingPnl >= 0 ? "text-emerald-400" : "text-rose-400"}>
              {kpis.floatingPnl >= 0 ? "+" : ""}${kpis.floatingPnl.toFixed(2)}
            </span>
          </div>
        </div>

        {/* 2. Today P&L (+R) */}
        <div className="bg-[#0b1017] border border-slate-800/90 rounded-xl p-3">
          <div className="flex items-center justify-between text-[11px] text-slate-400 uppercase tracking-wider">
            <span>Today P&amp;L (+R)</span>
            {kpis.todayPnlUsd >= 0 ? (
              <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
            ) : (
              <TrendingDown className="w-3.5 h-3.5 text-rose-400" />
            )}
          </div>
          <div
            className={`text-lg font-mono font-bold mt-1 ${
              kpis.todayPnlUsd >= 0 ? "text-emerald-400" : "text-rose-400"
            }`}
          >
            {kpis.todayPnlUsd >= 0 ? "+" : ""}${kpis.todayPnlUsd.toFixed(2)}{" "}
            <span className="text-sm">
              ({kpis.todayPnlR >= 0 ? "+" : ""}
              {kpis.todayPnlR.toFixed(2)}R)
            </span>
          </div>
          <div className="text-[11px] text-slate-300 mt-0.5">
            1R Unit Risk = ${(kpis.balance * 0.005).toFixed(2)} (0.50%)
          </div>
        </div>

        {/* 3. Daily Loss Used vs Limit */}
        <div className="bg-[#0b1017] border border-slate-800/90 rounded-xl p-3">
          <div className="flex items-center justify-between text-[11px] text-slate-400 uppercase tracking-wider">
            <span>Daily Loss vs Limit</span>
            <span className="font-mono text-slate-200">
              {kpis.dailyLossUsedPct.toFixed(2)}% / {kpis.dailyLossLimitPct.toFixed(1)}%
            </span>
          </div>
          <div className="text-base font-mono font-bold text-slate-100 mt-1">
            ${kpis.dailyLossUsedUsd.toFixed(2)}{" "}
            <span className="text-xs text-slate-400 font-normal">
              of ${kpis.dailyLossLimitUsd.toFixed(2)}
            </span>
          </div>
          <div className="w-full h-1.5 bg-slate-900 rounded-full overflow-hidden mt-1.5 border border-slate-800">
            <div
              className="h-full bg-emerald-500 rounded-full"
              style={{
                width: `${Math.min(100, (kpis.dailyLossUsedPct / kpis.dailyLossLimitPct) * 100)}%`,
              }}
            />
          </div>
        </div>

        {/* 4. Total Drawdown vs Cap */}
        <div className="bg-[#0b1017] border border-slate-800/90 rounded-xl p-3">
          <div className="flex items-center justify-between text-[11px] text-slate-400 uppercase tracking-wider">
            <span>Total DD vs Cap</span>
            <span className="font-mono text-emerald-300">SAFE</span>
          </div>
          <div className="text-lg font-mono font-bold text-slate-100 mt-1">
            {kpis.totalDrawdownUsedPct.toFixed(2)}%{" "}
            <span className="text-xs text-slate-400 font-normal">
              / {kpis.totalDrawdownCapPct.toFixed(1)}% Cap
            </span>
          </div>
          <div className="w-full h-1.5 bg-slate-900 rounded-full overflow-hidden mt-1.5 border border-slate-800">
            <div
              className="h-full bg-sky-500 rounded-full"
              style={{
                width: `${Math.min(100, (kpis.totalDrawdownUsedPct / kpis.totalDrawdownCapPct) * 100)}%`,
              }}
            />
          </div>
        </div>

        {/* 5. Open Positions (Bot / Manual / Pending) */}
        <div className="bg-[#0b1017] border border-slate-800/90 rounded-xl p-3">
          <div className="flex items-center justify-between text-[11px] text-slate-400 uppercase tracking-wider">
            <span>Open Exposure</span>
            <span className="font-mono text-sky-300">{activePositions.length} Active</span>
          </div>
          <div className="text-lg font-mono font-bold text-slate-100 mt-1">
            Bot {activePositions.filter((p) => p.ownership === "BOT").length} · Man{" "}
            {activePositions.filter((p) => p.ownership === "MANUAL").length} · Pend{" "}
            {kpis.pendingOrdersCount}
          </div>
          <div className="text-[11px] text-slate-300 mt-0.5">
            Other EA: {kpis.otherEaPositionsCount} · Magic #202601
          </div>
        </div>

        {/* 6. Next Schedule Switch */}
        <div className="bg-[#0b1017] border border-slate-800/90 rounded-xl p-3">
          <div className="flex items-center justify-between text-[11px] text-slate-400 uppercase tracking-wider">
            <span>Next Schedule Switch</span>
            <Clock className="w-3.5 h-3.5 text-amber-400" />
          </div>
          <div className="text-lg font-mono font-bold text-amber-300 mt-1" data-testid="schedule-countdown">
            {sched.nextSwitchCountdown}
          </div>
          <div className="text-[11px] text-slate-300 truncate mt-0.5" title={sched.nextSwitchLabel}>
            → {sched.nextSwitchLabel}
          </div>
        </div>
      </section>

      {/* =====================================================================
          MAIN TERMINAL WORKSPACE:
          SECTION (c) LIVE CHART (Center-Left, 8 cols) + SECTION (d) RIGHT COLUMN (4 cols)
      ====================================================================== */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-3 items-stretch">
        {/* SECTION (c): LIVE CHART (Main Feature) — stretches to fill 100% of column height */}
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

        {/* SECTION (d): RIGHT COLUMN — Engine Control + Open Positions & Orders */}
        <div className="xl:col-span-4 flex flex-col gap-3">
          {/* d.1: Engine Control Card */}
          <section
            aria-label="Engine Control and Supervisor Status"
            className="bg-[#0b1017] border border-slate-800/90 rounded-xl p-3.5 space-y-3"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Cpu className="w-4 h-4 text-sky-400" />
                <h2 className="text-xs font-bold uppercase tracking-wider text-slate-100">
                  Engine Control &amp; Supervisor
                </h2>
              </div>
              <span
                className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold ${
                  eng.engine_state === "RUNNING"
                    ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                    : eng.engine_state === "PAUSED"
                    ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                    : "bg-slate-800 text-slate-300"
                }`}
              >
                {eng.engine_state}
              </span>
            </div>

            {/* State / Supervisor / Warm-up telemetry strip */}
            <div className="grid grid-cols-3 gap-2 text-[11px] font-mono">
              <div className="bg-slate-950/80 border border-slate-800/90 rounded-lg p-2">
                <div className="text-slate-400 font-sans text-[10px]">Supervisor</div>
                <div className="text-slate-100 font-bold mt-0.5">
                  PID {eng.engine_pid ?? 15204}
                </div>
              </div>
              <div className="bg-slate-950/80 border border-slate-800/90 rounded-lg p-2">
                <div className="text-slate-400 font-sans text-[10px]">Bridge IPC</div>
                <div className="text-emerald-300 font-bold mt-0.5">
                  PID {eng.bridge_pid ?? 14820}
                </div>
              </div>
              <div className="bg-slate-950/80 border border-slate-800/90 rounded-lg p-2">
                <div className="text-slate-400 font-sans text-[10px]">Warm-Up Bars</div>
                <div className="text-emerald-300 font-bold mt-0.5">
                  {healthExt.warmupBarsLoaded}/{healthExt.warmupBarsRequired} READY
                </div>
              </div>
            </div>

            {/* Operating Mode Selector (OBSERVE, DRY_RUN, DEMO_SCALPING, DEMO_FAST, DEMO_MANUAL_ASSIST) */}
            <div>
              <div className="flex items-center justify-between text-[11px] text-slate-300 mb-1.5">
                <span className="font-semibold">Operating Mode (DEMO-Locked)</span>
                <span className="font-mono text-[10px] text-emerald-300">LIVE_TRADING=false</span>
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
                      className={`flex items-center justify-between px-2.5 py-1.5 rounded-lg border text-left transition ${
                        active
                          ? "bg-sky-950/80 border-sky-400 text-slate-100"
                          : "bg-slate-950/70 border-slate-800/90 text-slate-300 hover:border-slate-700"
                      }`}
                    >
                      <div>
                        <div className="text-[11px] font-mono font-bold">{m.short}</div>
                        <div className="text-[10px] text-slate-300">{m.desc}</div>
                      </div>
                      <span
                        className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                          active
                            ? "bg-sky-500 text-slate-950 font-bold"
                            : "bg-slate-900 text-slate-400"
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
            <div className="grid grid-cols-4 gap-1.5 pt-1">
              <button
                type="button"
                disabled={busyAction !== null}
                onClick={() =>
                  executeControlAction("Start Engine", () =>
                    controlClient.startEngine(eng.operating_mode === "DRY_RUN")
                  )
                }
                className="px-2 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-[11px] font-semibold inline-flex items-center justify-center space-x-1"
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
                className="px-2 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-500 text-white text-[11px] font-semibold inline-flex items-center justify-center space-x-1"
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
                className="px-2 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-[11px] font-semibold inline-flex items-center justify-center space-x-1"
              >
                <RotateCcw className="w-3 h-3" />
                <span>Restart</span>
              </button>

              <button
                type="button"
                disabled={busyAction !== null}
                onClick={() => setConfirmModal({ type: "EMERGENCY_FLATTEN", step: 1 })}
                className="px-2 py-1.5 rounded-lg bg-rose-700 hover:bg-rose-600 text-white text-[11px] font-bold inline-flex items-center justify-center space-x-1"
                title="Engage STOP.flag and flatten all bot positions (Two-Step Confirmation)"
              >
                <ShieldAlert className="w-3 h-3" />
                <span>Flatten</span>
              </button>
            </div>
          </section>

          {/* d.2: Open Positions & Orders Card */}
          <section
            aria-label="Open Positions and Pending Orders"
            className="flex-1 bg-[#0b1017] border border-slate-800/90 rounded-xl p-3.5 flex flex-col justify-between space-y-2.5"
          >
            <div className="space-y-2.5">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-xs font-bold uppercase tracking-wider text-slate-100">
                    Open Positions &amp; Orders ({activePositions.length})
                  </h2>
                  <p className="text-[11px] text-slate-300">
                    Tighten-only stop policy enforced · Click symbol to focus chart
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => onNavigate("positions")}
                  className="text-[11px] text-sky-400 hover:text-sky-300 font-semibold"
                >
                  Full Table →
                </button>
              </div>

              {activePositions.length === 0 ? (
                <div className="py-8 text-center text-xs text-slate-400 bg-slate-950/60 border border-slate-800/80 rounded-lg">
                  No open positions on MT5. Waiting for next risk-authorized setup.
                </div>
              ) : (
                <div className="space-y-2 max-h-[320px] overflow-y-auto pr-0.5">
                  {activePositions.map((pos) => {
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

                    return (
                      <div
                        key={pos.ticket}
                        className="bg-slate-950/90 border border-slate-800/90 rounded-lg p-2.5 text-xs space-y-2"
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center space-x-1.5">
                            <button
                              type="button"
                              onClick={() => setSelectedSymbol(symClean)}
                              className="font-mono font-bold text-slate-100 hover:text-sky-300 underline decoration-slate-700"
                            >
                              {pos.symbol}
                            </button>
                            <span
                              className={`px-1.5 py-0.5 rounded font-mono font-bold text-[10px] ${
                                dir === "BUY"
                                  ? "bg-emerald-500/20 text-emerald-300"
                                  : "bg-rose-500/20 text-rose-300"
                              }`}
                            >
                              {dir} {pos.volume.toFixed(2)}L
                            </span>
                            <span
                              className={`px-1.5 py-0.5 rounded font-mono text-[10px] font-bold ${
                                ownerLabel === "BOT_OWN"
                                  ? "bg-sky-500/20 text-sky-300 border border-sky-500/30"
                                  : ownerLabel === "MANUAL"
                                  ? "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                                  : "bg-slate-800 text-slate-300"
                              }`}
                            >
                              {ownerLabel}
                            </span>
                          </div>

                          <div
                            className={`font-mono font-bold ${
                              pos.profit >= 0 ? "text-emerald-400" : "text-rose-400"
                            }`}
                          >
                            {pos.profit >= 0 ? "+" : ""}${pos.profit.toFixed(2)} (
                            {m.floatingR >= 0 ? "+" : ""}
                            {m.floatingR.toFixed(2)}R)
                          </div>
                        </div>

                        <div className="grid grid-cols-3 gap-1.5 font-mono text-[11px] bg-slate-900/70 rounded px-2 py-1 border border-slate-800/70">
                          <div>
                            <span className="text-slate-400">Entry:</span>{" "}
                            <span className="text-slate-100">{pos.open_price.toFixed(digits)}</span>
                          </div>
                          <div>
                            <span className="text-slate-400">SL:</span>{" "}
                            <span className="text-rose-300 font-semibold">
                              {pos.sl > 0 ? pos.sl.toFixed(digits) : "NONE"}
                            </span>
                          </div>
                          <div>
                            <span className="text-slate-400">TP:</span>{" "}
                            <span className="text-emerald-300 font-semibold">
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
                              className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-[10px] font-semibold inline-flex items-center space-x-1"
                            >
                              <Scissors className="w-3 h-3 text-sky-400" />
                              <span>Partial 50%</span>
                            </button>

                            <button
                              type="button"
                              onClick={() => handleMoveToBreakEven(pos)}
                              aria-label={`Move stop loss to break-even for ticket ${pos.ticket}`}
                              className="px-2 py-1 rounded bg-sky-950/90 hover:bg-sky-900 border border-sky-500/40 text-sky-200 text-[10px] font-semibold"
                            >
                              BE+ Lock
                            </button>

                            <button
                              type="button"
                              onClick={() => openTightenSlModal(pos)}
                              aria-label={`Tighten stop loss for ticket ${pos.ticket}`}
                              className="px-2 py-1 rounded bg-emerald-950/90 hover:bg-emerald-900 border border-emerald-500/40 text-emerald-200 text-[10px] font-semibold"
                            >
                              Tighten SL
                            </button>

                            {/* Explicitly Disabled Widen / Remove SL per Hard Safety Rule #5 */}
                            <button
                              type="button"
                              disabled
                              aria-disabled="true"
                              title="Hard Safety Rule #5: Tighten-Only Stop Policy blocks widening or removing Stop Loss"
                              className="px-2 py-1 rounded bg-slate-900/80 border border-slate-800 text-slate-400 text-[10px] font-medium cursor-not-allowed opacity-60 inline-flex items-center space-x-1"
                            >
                              <Lock className="w-2.5 h-2.5" />
                              <span>Widen/Remove SL</span>
                            </button>
                          </div>

                          <button
                            type="button"
                            onClick={() => handleCloseSinglePosition(pos)}
                            aria-label={`Close position ticket ${pos.ticket}`}
                            className="px-2 py-1 rounded bg-rose-600/90 hover:bg-rose-500 text-white text-[10px] font-bold"
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
            <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between text-[11px]">
              <span className="text-slate-300">
                Pending Limit/Stop Orders:{" "}
                <strong className="font-mono text-slate-100">{kpis.pendingOrdersCount}</strong>
              </span>
              <span className="inline-flex items-center space-x-1 text-emerald-300 font-mono text-[10px]">
                <ShieldCheck className="w-3.5 h-3.5" />
                <span>100% SL Protected</span>
              </span>
            </div>
          </section>
        </div>
      </div>

      {/* =====================================================================
          SECTION (e): ANALYTICAL & OPERATIONAL PANELS (7 PANELS)
          1. Live Trade Timeline
          2. Risk Manager (DEMO / LIVE / PROP Profile Limits)
          3. Gold–USDJPY Inverse Coordination
          4. Schedule & Instruments
          5. System Health (EA Heartbeat, Queue Depth, CUSUM/PSI, TCA, Error Centre Count)
          6. Manual Position Adoption
          7. Recent Trades Table
      ====================================================================== */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
        {/* Panel 1: Live Trade Timeline (4 cols) */}
        <section
          aria-label="Live Trade Lifecycle Timeline"
          className="lg:col-span-4 bg-[#0b1017] border border-slate-800/90 rounded-xl p-3.5 space-y-2.5"
        >
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-100 flex items-center space-x-1.5">
              <Activity className="w-3.5 h-3.5 text-sky-400" />
              <span>Live Trade Timeline</span>
            </h3>
            <span className="text-[10px] font-mono text-slate-300 bg-slate-900 px-2 py-0.5 rounded border border-slate-800">
              SSE Stream
            </span>
          </div>

          <div className="space-y-2 max-h-[235px] overflow-y-auto pr-1">
            {dash.timelineEvents.map((ev) => {
              const badgeStyles: Record<typeof ev.tone, string> = {
                emerald: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
                sky: "bg-sky-500/20 text-sky-300 border-sky-500/40",
                amber: "bg-amber-500/20 text-amber-300 border-amber-500/40",
                rose: "bg-rose-500/20 text-rose-300 border-rose-500/40",
                slate: "bg-slate-800 text-slate-300 border-slate-700",
              };
              return (
                <div
                  key={ev.id}
                  className="bg-slate-950/80 border border-slate-800/90 rounded-lg p-2.5 text-xs space-y-1"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-slate-100">{ev.title}</span>
                    {ev.rMultiple && (
                      <span
                        className={`px-1.5 py-0.5 rounded border font-mono text-[10px] font-bold ${
                          badgeStyles[ev.tone]
                        }`}
                      >
                        {ev.rMultiple}
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-slate-300 leading-snug">{ev.detail}</p>
                  <div className="flex items-center justify-between text-[10px] font-mono text-slate-400">
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
          className="lg:col-span-4 bg-[#0b1017] border border-slate-800/90 rounded-xl p-3.5 space-y-2.5"
        >
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-100 flex items-center space-x-1.5">
              <Shield className="w-3.5 h-3.5 text-emerald-400" />
              <span>Risk Manager (DEMO / PROP / LIVE Profiles)</span>
            </h3>
            <button
              type="button"
              onClick={() => onNavigate("risk")}
              className="text-[11px] text-sky-400 hover:text-sky-300 font-semibold"
            >
              Details →
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-slate-300 border-b border-slate-800 text-[11px]">
                <tr>
                  <th className="py-1.5 pr-2">Profile</th>
                  <th className="py-1.5 pr-2">Risk/Trade</th>
                  <th className="py-1.5 pr-2">Daily Limit</th>
                  <th className="py-1.5 pr-2">Max DD</th>
                  <th className="py-1.5">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/70 font-mono text-[11px]">
                {dash.riskProfiles.map((rp) => (
                  <tr key={rp.profile} className={rp.active ? "bg-emerald-950/30" : ""}>
                    <td className="py-2 pr-2 font-bold text-slate-100">{rp.profile}</td>
                    <td className="py-2 pr-2 text-slate-200">{rp.riskPerTradePct.toFixed(2)}%</td>
                    <td className="py-2 pr-2 text-slate-200">{rp.dailyLossLimitPct.toFixed(1)}%</td>
                    <td className="py-2 pr-2 text-slate-200">{rp.maxTotalDrawdownPct.toFixed(1)}%</td>
                    <td className="py-2 font-sans">
                      {rp.active ? (
                        <span className="px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 text-[10px] font-bold">
                          ACTIVE
                        </span>
                      ) : rp.locked ? (
                        <span className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700 text-[10px] font-semibold inline-flex items-center space-x-1">
                          <Lock className="w-2.5 h-2.5 text-amber-400" />
                          <span>LOCKED</span>
                        </span>
                      ) : (
                        <span className="px-1.5 py-0.5 rounded bg-slate-900 text-slate-300 text-[10px]">
                          STANDBY
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="bg-slate-950/80 border border-slate-800/90 rounded-lg p-2.5 text-[11px] flex items-center justify-between">
            <span className="text-slate-300">Portfolio Risk Budget Used:</span>
            <span className="font-mono font-bold text-emerald-300">
              1.15% / 6.00% (Cap Available: 4.85%)
            </span>
          </div>
        </section>

        {/* Panel 3: Gold–USDJPY Inverse Coordination + Panel 4: Schedule & Instruments (4 cols) */}
        <div className="lg:col-span-4 flex flex-col gap-3">
          {/* Panel 3: Gold–USDJPY Inverse Coordination */}
          <section
            aria-label="Gold and USDJPY Inverse Correlation Coordination"
            className="bg-[#0b1017] border border-slate-800/90 rounded-xl p-3.5 space-y-2"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-100 flex items-center space-x-1.5">
                <GitCompare className="w-3.5 h-3.5 text-amber-400" />
                <span>Gold–USDJPY Inverse Coordination</span>
              </h3>
              <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-mono text-[10px] font-bold">
                {inv.coherenceState}
              </span>
            </div>

            <div className="grid grid-cols-3 gap-2 font-mono text-xs">
              <div className="bg-slate-950/80 border border-slate-800 rounded-lg p-2">
                <div className="text-[10px] font-sans text-slate-400">60m Rolling r</div>
                <div className="text-emerald-300 font-bold mt-0.5">{inv.rollingCorrelation60m}</div>
              </div>
              <div className="bg-slate-950/80 border border-slate-800 rounded-lg p-2">
                <div className="text-[10px] font-sans text-slate-400">XAU / JPY Bias</div>
                <div className="text-slate-100 font-bold mt-0.5">
                  {inv.goldBias === "BULLISH" ? "XAU↑" : "XAU↓"} /{" "}
                  {inv.usdjpyBias === "BEARISH" ? "JPY↓" : "JPY↑"}
                </div>
              </div>
              <div className="bg-slate-950/80 border border-slate-800 rounded-lg p-2">
                <div className="text-[10px] font-sans text-slate-400">Hedge Gate</div>
                <div className="text-sky-300 font-bold mt-0.5">{inv.hedgeGateStatus}</div>
              </div>
            </div>

            <p className="text-[11px] text-slate-300 leading-snug">{inv.note}</p>
          </section>

          {/* Panel 4: Schedule & Instruments Matrix */}
          <section
            aria-label="Schedule and Approved Instruments Matrix"
            className="bg-[#0b1017] border border-slate-800/90 rounded-xl p-3.5 space-y-2"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-100 flex items-center space-x-1.5">
                <Layers className="w-3.5 h-3.5 text-sky-400" />
                <span>Schedule &amp; Instruments</span>
              </h3>
              <button
                type="button"
                onClick={() => onNavigate("instruments")}
                className="text-[11px] text-sky-400 hover:text-sky-300 font-semibold"
              >
                Specs →
              </button>
            </div>

            <div className="grid grid-cols-3 gap-2 text-xs font-mono">
              {(["XAUUSD", "USDJPY", "BTCUSD"] as ChartSymbol[]).map((sym) => {
                const isActiveInSchedule = sched.activeInstruments.includes(sym);
                return (
                  <button
                    key={sym}
                    type="button"
                    onClick={() => setSelectedSymbol(sym)}
                    className={`p-2 rounded-lg border text-left transition ${
                      selectedSymbol === sym
                        ? "bg-sky-950/70 border-sky-400"
                        : "bg-slate-950/80 border-slate-800 hover:border-slate-700"
                    }`}
                  >
                    <div className="font-bold text-slate-100 flex items-center justify-between">
                      <span>{sym}</span>
                      <span
                        className={`w-2 h-2 rounded-full ${
                          isActiveInSchedule ? "bg-emerald-400" : "bg-amber-400"
                        }`}
                      />
                    </div>
                    <div className="text-[10px] font-sans text-slate-300 mt-0.5">
                      {isActiveInSchedule ? "ACTIVE SESSION" : "STANDBY / 24-7"}
                    </div>
                  </button>
                );
              })}
            </div>
          </section>
        </div>
      </div>

      {/* Bottom Row of Section (e): System Health + Manual Position Adoption + Recent Trades Table */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
        {/* Panel 5: System Health (EA Heartbeat, Queue Depth, CUSUM/PSI, TCA, Error Centre Count) (4 cols) */}
        <section
          aria-label="System Health and Quantitative Drift Telemetry"
          className="lg:col-span-4 bg-[#0b1017] border border-slate-800/90 rounded-xl p-3.5 space-y-2.5"
        >
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-100 flex items-center space-x-1.5">
              <Gauge className="w-3.5 h-3.5 text-emerald-400" />
              <span>System Health &amp; Drift Guards</span>
            </h3>
            <button
              type="button"
              onClick={() => onNavigate("errors")}
              className="text-[11px] text-sky-400 hover:text-sky-300 font-semibold"
            >
              Error Centre ({healthExt.activeErrorCount}) →
            </button>
          </div>

          <div className="grid grid-cols-2 gap-2 text-xs font-mono">
            <div className="bg-slate-950/80 border border-slate-800 rounded-lg p-2.5">
              <div className="text-[10px] font-sans text-slate-400">EA Heartbeat Latency</div>
              <div className="text-emerald-300 font-bold mt-0.5">
                {healthExt.eaHeartbeatAgeMs} ms ({healthExt.eaHeartbeatStatus})
              </div>
            </div>

            <div className="bg-slate-950/80 border border-slate-800 rounded-lg p-2.5">
              <div className="text-[10px] font-sans text-slate-400">ZMQ Queue Depth</div>
              <div className="text-slate-100 font-bold mt-0.5">
                {healthExt.outboundQueueDepth} msgs (0 backlog)
              </div>
            </div>

            <div className="bg-slate-950/80 border border-slate-800 rounded-lg p-2.5">
              <div className="text-[10px] font-sans text-slate-400">CUSUM / PSI Drift</div>
              <div className="text-sky-300 font-bold mt-0.5">
                {healthExt.cusumDecayScore} / PSI {healthExt.psiFeatureDrift}
              </div>
            </div>

            <div className="bg-slate-950/80 border border-slate-800 rounded-lg p-2.5">
              <div className="text-[10px] font-sans text-slate-400">TCA Slippage / Fill</div>
              <div className="text-emerald-300 font-bold mt-0.5">
                {healthExt.tcaAvgSlippageBps} bps · {healthExt.tcaFillLatencyMs} ms
              </div>
            </div>
          </div>

          <div className="flex items-center justify-between bg-slate-950/80 border border-slate-800 rounded-lg px-2.5 py-2 text-xs">
            <span className="text-slate-300">Error Centre Active Alerts:</span>
            <span
              className={`font-mono font-bold px-2 py-0.5 rounded ${
                healthExt.activeErrorCount === 0
                  ? "bg-emerald-500/20 text-emerald-300"
                  : "bg-rose-500/20 text-rose-300"
              }`}
            >
              {healthExt.activeErrorCount} ACTIVE
            </span>
          </div>
        </section>

        {/* Panel 6: Manual Position Adoption (3 cols) */}
        <section
          aria-label="Manual Position Adoption and Protection"
          className="lg:col-span-3 bg-[#0b1017] border border-slate-800/90 rounded-xl p-3.5 space-y-2.5 flex flex-col justify-between"
        >
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-100 flex items-center space-x-1.5">
                <ShieldCheck className="w-3.5 h-3.5 text-amber-400" />
                <span>Manual Position Adoption</span>
              </h3>
              <span className="text-[10px] font-mono text-amber-300 bg-amber-500/15 px-1.5 py-0.5 rounded">
                {dash.manualAdoptionQueue.length} Manual
              </span>
            </div>

            {dash.manualAdoptionQueue.length === 0 ? (
              <div className="py-6 text-center text-xs text-slate-400 bg-slate-950/70 border border-slate-800 rounded-lg">
                No manual MT5 positions detected. Any discretionary trade opened in MT5 appears here for automated tighten-only SL adoption.
              </div>
            ) : (
              <div className="space-y-2">
                {dash.manualAdoptionQueue.map((mp) => (
                  <div
                    key={mp.ticket}
                    className="bg-slate-950/90 border border-slate-800 rounded-lg p-2.5 text-xs space-y-1.5"
                  >
                    <div className="flex items-center justify-between font-mono">
                      <span className="font-bold text-slate-100">
                        #{mp.ticket} {mp.symbol} {mp.direction} {mp.volume}L
                      </span>
                      <span className="text-emerald-400 font-bold">+${mp.profit.toFixed(2)}</span>
                    </div>
                    <div className="text-[11px] text-slate-300">{mp.statusNote}</div>
                    <div className="flex items-center justify-between pt-1">
                      <span className="font-mono text-[10px] text-slate-400">
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
                        className="px-2 py-1 rounded bg-amber-600 hover:bg-amber-500 text-white text-[10px] font-bold"
                      >
                        Sync Guard SL
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="text-[11px] text-slate-300 bg-slate-950/70 border border-slate-800 rounded-lg px-2.5 py-1.5">
            Mode <strong className="font-mono text-sky-300">DEMO_MANUAL_ASSIST</strong> attaches break-even &amp; trailing guards to manual tickets.
          </div>
        </section>

        {/* Panel 7: Recent Trades Table (5 cols) */}
        <section
          aria-label="Recent Closed Trades Table"
          className="lg:col-span-5 bg-[#0b1017] border border-slate-800/90 rounded-xl p-3.5 space-y-2.5"
        >
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-100 flex items-center space-x-1.5">
              <History className="w-3.5 h-3.5 text-sky-400" />
              <span>Recent Trades ({dash.recentTrades.length})</span>
            </h3>
            <button
              type="button"
              onClick={() => onNavigate("history")}
              className="text-[11px] text-sky-400 hover:text-sky-300 font-semibold"
            >
              Export / Full History →
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-slate-300 border-b border-slate-800 text-[11px]">
                <tr>
                  <th className="py-1.5 pr-2">Ticket</th>
                  <th className="py-1.5 pr-2">Symbol</th>
                  <th className="py-1.5 pr-2">Side</th>
                  <th className="py-1.5 pr-2">Entry → Exit</th>
                  <th className="py-1.5 pr-2">Net P&amp;L</th>
                  <th className="py-1.5">Outcome</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/70 font-mono text-[11px]">
                {dash.recentTrades.slice(0, 6).map((t) => (
                  <tr key={t.id} className="hover:bg-slate-900/60">
                    <td className="py-2 pr-2 text-slate-300">#{t.ticket}</td>
                    <td className="py-2 pr-2 font-bold text-slate-100">{t.symbol}</td>
                    <td
                      className={`py-2 pr-2 font-bold ${
                        t.direction === "BUY" ? "text-emerald-400" : "text-rose-400"
                      }`}
                    >
                      {t.direction} {t.volume.toFixed(2)}
                    </td>
                    <td className="py-2 pr-2 text-slate-200">
                      {t.open_price} → {t.close_price}
                    </td>
                    <td
                      className={`py-2 pr-2 font-bold ${
                        t.profit >= 0 ? "text-emerald-400" : "text-rose-400"
                      }`}
                    >
                      {t.profit >= 0 ? "+" : ""}${t.profit.toFixed(2)}
                    </td>
                    <td className="py-2 font-sans text-[10px] text-slate-200">{t.status}</td>
                  </tr>
                ))}
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
          className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-4"
        >
          <div className="bg-slate-900 border border-rose-500/60 rounded-xl p-5 max-w-md w-full space-y-3 shadow-2xl">
            <div className="flex items-center space-x-2.5 text-rose-400">
              <ShieldAlert className="w-5 h-5 shrink-0" />
              <h3 id="two-step-confirm-title" className="text-sm font-bold text-slate-100">
                {confirmModal.type === "CLOSE_ALL_BOT"
                  ? `Two-Step Confirmation (Step ${confirmModal.step} of 2): Close All Bot Positions`
                  : `Two-Step Confirmation (Step ${confirmModal.step} of 2): Emergency Flatten & STOP.flag`}
              </h3>
            </div>

            {confirmModal.step === 1 ? (
              <p className="text-xs text-slate-200 leading-relaxed">
                Step 1 Verification: You are requesting to liquidate{" "}
                <strong>{activePositions.filter((p) => p.ownership === "BOT").length} bot-owned DEMO positions</strong>{" "}
                at market price via existing endpoint{" "}
                <code className="text-rose-300">
                  {confirmModal.type === "CLOSE_ALL_BOT"
                    ? "POST /api/trades/close-all-bot"
                    : "POST /api/engine/emergency-stop"}
                </code>
                . Manual positions will remain untouched. Proceed to final confirmation?
              </p>
            ) : (
              <div className="p-3 rounded-lg bg-rose-950/70 border border-rose-500/50 text-xs text-rose-100 space-y-1">
                <div className="font-bold">Step 2 Final Authorization:</div>
                <div>
                  Click <strong>Execute Immediate Flatten</strong> below to transmit confirmed closure orders to MT5 DEMO account{" "}
                  <span className="font-mono">{dash.maskedAccount}</span>.
                </div>
              </div>
            )}

            <div className="flex items-center justify-end space-x-2 pt-2">
              <button
                type="button"
                onClick={() => setConfirmModal(null)}
                className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs text-slate-200"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmTwoStep}
                className="px-3.5 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-500 text-xs font-bold text-white"
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
          className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-4"
        >
          <div className="bg-slate-900 border border-slate-700 rounded-xl p-5 max-w-md w-full space-y-3 shadow-2xl">
            <div className="flex items-center justify-between">
              <h3 id="tighten-sl-modal-title" className="text-sm font-bold text-slate-100">
                Tighten-Only SL / TP — #{slModalPos.ticket} ({slModalPos.symbol} {slModalPos.direction})
              </h3>
              <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 text-[10px] font-mono font-bold">
                TIGHTEN-ONLY POLICY
              </span>
            </div>

            <div className="text-xs text-slate-300 bg-slate-950 border border-slate-800 rounded-lg p-2.5 font-mono space-y-1">
              <div>
                Entry: <strong>{slModalPos.open_price}</strong> · Current Price:{" "}
                <strong>{slModalPos.current_price}</strong>
              </div>
              <div>
                Current SL: <strong className="text-rose-300">{slModalPos.sl}</strong> (Cannot be widened or set to 0)
              </div>
            </div>

            <div className="space-y-2 text-xs">
              <label className="block">
                <span className="text-slate-300 font-semibold">
                  Proposed Tighter Stop Loss ({slModalPos.direction === "BUY" ? `>= ${slModalPos.sl}` : `<= ${slModalPos.sl}`})
                </span>
                <input
                  type="number"
                  step="any"
                  value={proposedSlInput}
                  onChange={(e) => setProposedSlInput(e.target.value)}
                  className="w-full mt-1 bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-slate-100 font-mono"
                />
              </label>

              <label className="block">
                <span className="text-slate-300 font-semibold">Take Profit Target</span>
                <input
                  type="number"
                  step="any"
                  value={proposedTpInput}
                  onChange={(e) => setProposedTpInput(e.target.value)}
                  className="w-full mt-1 bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-slate-100 font-mono"
                />
              </label>
            </div>

            {!slValidation.allowed && (
              <div className="p-2.5 rounded-lg bg-rose-950/80 border border-rose-500/50 text-[11px] text-rose-200">
                {slValidation.reason}
              </div>
            )}

            <div className="flex items-center justify-end space-x-2 pt-2">
              <button
                type="button"
                onClick={() => setSlModalPos(null)}
                className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs text-slate-200"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={!slValidation.allowed || busyAction !== null}
                onClick={handleApplyTightenSl}
                className="px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-xs font-bold text-white"
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
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-base font-bold text-slate-100 flex items-center space-x-2">
              <Cpu className="w-5 h-5 text-sky-400" />
              <span>Trading Engine Lifecycle Controller</span>
            </h2>
            <p className="text-xs text-slate-400 mt-1">
              Controls the single authoritative <code>scripts/start_bot.py</code> &amp; <code>scripts/run_bridge_server.py</code> processes.
            </p>
          </div>
          <div className="flex items-center space-x-2">
            <label className="flex items-center space-x-2 text-xs text-slate-300 bg-slate-950 px-3 py-1.5 rounded-lg border border-slate-800">
              <input
                type="checkbox"
                checked={dryRunChoice}
                onChange={(e) => setDryRunChoice(e.target.checked)}
                className="rounded border-slate-700"
              />
              <span>Dry-Run Mode</span>
            </label>
          </div>
        </div>

        <div className="flex flex-wrap gap-2.5 mt-5">
          <button
            disabled={busy || eng?.engine_running}
            onClick={() => runAction("Start Engine", () => controlClient.startEngine(dryRunChoice))}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white text-xs font-semibold rounded-lg flex items-center space-x-1.5"
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
            className="px-4 py-2 bg-amber-600 hover:bg-amber-500 disabled:opacity-40 text-white text-xs font-semibold rounded-lg flex items-center space-x-1.5"
          >
            <Pause className="w-4 h-4" />
            <span>{eng?.pause_flag_active ? "Resume Entries" : "Pause Entries"}</span>
          </button>

          <button
            disabled={busy || !eng?.engine_running}
            onClick={() => runAction("Stop Engine", () => controlClient.stopEngine())}
            className="px-4 py-2 bg-slate-700 hover:bg-slate-600 disabled:opacity-40 text-white text-xs font-semibold rounded-lg flex items-center space-x-1.5"
          >
            <Square className="w-4 h-4" />
            <span>Stop Engine</span>
          </button>

          <button
            disabled={busy}
            onClick={() => runAction("Restart Engine", () => controlClient.restartEngine())}
            className="px-4 py-2 bg-sky-600 hover:bg-sky-500 disabled:opacity-40 text-white text-xs font-semibold rounded-lg flex items-center space-x-1.5"
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
              className="px-4 py-2 bg-rose-600 hover:bg-rose-500 disabled:opacity-40 text-white text-xs font-semibold rounded-lg flex items-center space-x-1.5 ml-auto"
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
              className="px-4 py-2 bg-emerald-700 hover:bg-emerald-600 disabled:opacity-40 text-white text-xs font-semibold rounded-lg flex items-center space-x-1.5 ml-auto"
            >
              <CheckCircle2 className="w-4 h-4" />
              <span>Clear STOP.flag</span>
            </button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 text-xs space-y-1.5">
          <div className="text-slate-400">Process Supervision</div>
          <div>Bridge Running: <span className="font-mono text-slate-100">{String(eng?.bridge_running ?? false)}</span> (PID {eng?.bridge_pid ?? "-"})</div>
          <div>Engine Running: <span className="font-mono text-slate-100">{String(eng?.engine_running ?? false)}</span> (PID {eng?.engine_pid ?? "-"})</div>
        </div>
        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 text-xs space-y-1.5">
          <div className="text-slate-400">Safety Flags</div>
          <div>STOP.flag: <span className={`font-mono font-bold ${eng?.stop_flag_active ? "text-rose-400" : "text-emerald-400"}`}>{eng?.stop_flag_active ? "ACTIVE" : "CLEAR"}</span></div>
          <div>state/PAUSE: <span className={`font-mono font-bold ${eng?.pause_flag_active ? "text-amber-400" : "text-emerald-400"}`}>{eng?.pause_flag_active ? "PAUSED" : "ACTIVE"}</span></div>
        </div>
        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 text-xs space-y-1.5">
          <div className="text-slate-400">Execution Mode Lock</div>
          <div>Operating Mode: <span className="font-mono text-sky-400">{eng?.operating_mode || "DEMO_SCALPING"}</span></div>
          <div>Live Trading: <span className="font-mono text-emerald-400 font-bold">LOCKED (DEMO ONLY)</span></div>
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
    <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-bold text-slate-100 flex items-center space-x-2">
          <Activity className="w-4 h-4 text-sky-400" />
          <span>Live Market Watch &amp; Broker Specifications</span>
        </h2>
        <button
          disabled={syncing}
          onClick={handleSync}
          className="px-3 py-1.5 bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold rounded-lg flex items-center space-x-1.5"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${syncing ? "animate-spin" : ""}`} />
          <span>Sync Quotes</span>
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="text-slate-400 border-b border-slate-800">
            <tr>
              <th className="py-2 pr-3">Symbol</th>
              <th className="py-2 pr-3">Bid</th>
              <th className="py-2 pr-3">Ask</th>
              <th className="py-2 pr-3">Spread (pts)</th>
              <th className="py-2 pr-3">Digits</th>
              <th className="py-2 pr-3">Min / Max / Step Lot</th>
              <th className="py-2">Stops Level</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/70 font-mono">
            {symbols.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-8 text-center text-slate-500 font-sans">
                  No symbol quotes cached yet. Connect MT5 terminal and click Sync Quotes.
                </td>
              </tr>
            ) : (
              symbols.map((s) => (
                <tr key={s.symbol} className="hover:bg-slate-800/40">
                  <td className="py-2.5 pr-3 font-bold text-slate-100">{s.symbol}</td>
                  <td className="py-2.5 pr-3 text-emerald-400">{s.bid.toFixed(s.digits)}</td>
                  <td className="py-2.5 pr-3 text-rose-400">{s.ask.toFixed(s.digits)}</td>
                  <td className="py-2.5 pr-3 text-amber-300">{s.spread_points}</td>
                  <td className="py-2.5 pr-3 text-slate-300">{s.digits}</td>
                  <td className="py-2.5 pr-3 text-slate-300">{s.volume_min} / {s.volume_max} / {s.volume_step}</td>
                  <td className="py-2.5 text-slate-300">{s.stops_level}</td>
                </tr>
              ))
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
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-bold text-slate-100 flex items-center space-x-2">
            <Zap className="w-4 h-4 text-amber-400" />
            <span>Unfiltered Signal Pipeline &amp; Risk Authorization</span>
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Strategy layer runs unfiltered (<code>LEGACY_FILTERS_ENABLED=false</code>). All entries pass directly to independent <code>PortfolioRiskEngine</code>.
          </p>
        </div>
        <button onClick={() => onReload()} className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-xs text-slate-200 rounded-lg">
          Refresh
        </button>
      </div>

      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="text-slate-400 border-b border-slate-800">
            <tr>
              <th className="py-2 pr-3">Time</th>
              <th className="py-2 pr-3">Symbol</th>
              <th className="py-2 pr-3">Direction</th>
              <th className="py-2 pr-3">Decision</th>
              <th className="py-2 pr-3">Lot</th>
              <th className="py-2 pr-3">Risk %</th>
              <th className="py-2">Reason</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/70">
            {decisions.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-8 text-center text-slate-500">
                  No signal/risk authorization events recorded yet.
                </td>
              </tr>
            ) : (
              decisions.map((d) => (
                <tr key={d.id}>
                  <td className="py-2 pr-3 font-mono text-slate-400">{new Date(d.created_at).toLocaleTimeString()}</td>
                  <td className="py-2 pr-3 font-mono font-bold text-slate-100">{d.symbol}</td>
                  <td className="py-2 pr-3 font-mono text-slate-200">{d.direction}</td>
                  <td className="py-2 pr-3">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${d.approved ? "bg-emerald-500/20 text-emerald-300" : "bg-rose-500/20 text-rose-300"}`}>
                      {d.approved ? "APPROVED" : "BLOCKED"}
                    </span>
                  </td>
                  <td className="py-2 pr-3 font-mono">{d.lot_size.toFixed(2)}</td>
                  <td className="py-2 pr-3 font-mono">{d.risk_pct.toFixed(2)}%</td>
                  <td className="py-2 text-slate-300">{d.reason}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
