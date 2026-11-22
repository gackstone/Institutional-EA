import React, { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Clock,
  Lock,
  Pause,
  Scissors,
  Send,
  ShieldAlert,
  ShieldCheck,
  Square,
  TrendingDown,
  TrendingUp,
  Wifi,
  WifiOff,
  XCircle,
} from "lucide-react";
import { controlClient, IPC } from "../../services/ipc";
import {
  ControlPosition,
  ControlStatusPayload,
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
    trades?: TradeHistoryRecord[];
    feedStatus?: DataFeedStatus;
  }
> = ({
  status,
  onRefresh,
  onNavigate,
  onActionMessage,
  trades = [],
  feedStatus = "LIVE_SSE",
}) => {
  const [selectedSymbol, setSelectedSymbol] = useState<ChartSymbol>("XAUUSD");
  const [selectedTimeframe, setSelectedTimeframe] = useState<ChartTimeframe>("M5");
  const [utcClockText, setUtcClockText] = useState<string>(() =>
    `${new Date().toISOString().slice(11, 19)} UTC`
  );
  const [dataTick, setDataTick] = useState<number>(0);
  const [busyAction, setBusyAction] = useState<string | null>(null);

  // Two-step confirmation modal state for Close All Bot Positions
  const [confirmModal, setConfirmModal] = useState<{ step: 1 | 2 } | null>(null);

  // Tighten-Only Stop Loss modification modal state
  const [slModalPos, setSlModalPos] = useState<ControlPosition | null>(null);
  const [proposedSlInput, setProposedSlInput] = useState<string>("");
  const [proposedTpInput, setProposedTpInput] = useState<string>("");

  // Local optimistic modifications for positions (when in DEMO preview/simulation)
  const [localPositionOverrides, setLocalPositionOverrides] = useState<
    Record<number, Partial<ControlPosition> & { closed?: boolean }>
  >({});

  // Lightweight 1-second UTC clock (isolated from chart series)
  useEffect(() => {
    const timer = setInterval(() => {
      setUtcClockText(`${new Date().toISOString().slice(11, 19)} UTC`);
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

  // Build normalized dashboard state
  const dash = useMemo(
    () => buildNormalizedDashboardData(status, trades),
    [status, trades]
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
      mt5: {
        ...dash.status.mt5,
        positions: activePositions,
      },
    }),
    [dash.status, activePositions]
  );

  // Build Live Chart bundle for selected symbol & timeframe
  const chartBundle = useMemo(() => {
    const jitter = Math.sin(dataTick * 0.65) * 0.25;
    return buildSymbolChartBundle(selectedSymbol, selectedTimeframe, effectiveStatus, jitter);
  }, [selectedSymbol, selectedTimeframe, effectiveStatus, dataTick]);

  const eng = effectiveStatus.engine;
  const kpis = dash.kpis;
  const botOpenCount = activePositions.filter((p) => p.ownership === "BOT").length;

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

  // Two-step confirmation handler for Close All Bot Positions
  const handleConfirmTwoStep = async () => {
    if (!confirmModal) return;
    if (confirmModal.step === 1) {
      setConfirmModal({ step: 2 });
      return;
    }

    setConfirmModal(null);
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
          ROW 1: COMPACT TOP STATUS BAR + SAFETY CONTROLS (Pause / Stop / Close All)
      ====================================================================== */}
      <section
        aria-label="Terminal Top Status Bar"
        className="iea-glass-card flex flex-wrap items-center justify-between gap-2.5 px-4 py-2.5"
      >
        <div className="flex flex-wrap items-center gap-2 text-xs">
          {/* MT5 Connection + Masked Account */}
          <div
            title={`Connected MT5 Account ${dash.maskedAccount} (${effectiveStatus.mt5.account.broker})`}
            className="iea-pill-control inline-flex items-center space-x-1.5 px-3 py-1"
          >
            <Wifi className="w-3.5 h-3.5 text-[#B0F648]" />
            <span className="font-medium text-[#F4F7FF]">MT5</span>
            <span className="font-mono font-bold text-[#B0F648]" data-testid="masked-account-badge">
              {dash.maskedAccount}
            </span>
          </div>

          {/* Hard Safety Lock Badge */}
          <div
            data-testid="demo-lock-badge"
            title={UI_COPY.brand.demoLockTooltip}
            className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-full bg-[#B0F648]/16 border border-[#B0F648]/50 text-[#C2F076] font-mono text-[11px] font-bold"
          >
            <Lock className="w-3 h-3 text-[#B0F648] shrink-0" />
            <span>{UI_COPY.brand.demoLockChip}</span>
          </div>

          {/* ZMQ Bridge Ports 5555 / 5556 */}
          <div
            title="ZMQ/TCP Bridge Sockets: Port 5555 (EA) & Port 5556 (IPC)"
            className="iea-pill-control inline-flex items-center space-x-1.5 px-3 py-1 font-mono text-[11px]"
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
            className="iea-pill-control inline-flex items-center space-x-1.5 px-3 py-1 text-[11px] text-[#F4F7FF]"
          >
            <Send className="w-3 h-3 text-[#5EEAD4]" />
            <span className="text-[#B0F648] font-semibold">TG Ready</span>
          </button>

          {/* Live UTC Clock */}
          <div
            title="Live UTC Terminal Clock"
            className="iea-pill-control inline-flex items-center space-x-1.5 px-3 py-1 text-[11px]"
          >
            <Clock className="w-3 h-3 text-[#8496B8]" />
            <span className="font-mono text-[#F4F7FF] tabular-nums" data-testid="utc-clock">
              {utcClockText}
            </span>
          </div>
        </div>

        {/* Right: Safety-Critical Controls (Pause / Stop / Close All) */}
        <div className="flex items-center gap-2">
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
            title={
              eng.pause_flag_active
                ? "Resume automated trade entries"
                : "Pause new trade entries (existing SL/TP stay active)"
            }
            className="px-3.5 py-1.5 rounded-full bg-[#FBBF24]/20 hover:bg-[#FBBF24]/30 border border-[#FBBF24]/55 disabled:opacity-40 text-[#FBBF24] text-xs font-semibold inline-flex items-center space-x-1.5 transition duration-200"
          >
            <Pause className="w-3.5 h-3.5" />
            <span>{eng.pause_flag_active ? "Resume" : "Pause"}</span>
          </button>

          <button
            type="button"
            disabled={busyAction !== null}
            onClick={() => executeControlAction("Stop", () => controlClient.stopEngine())}
            aria-label="Stop trading engine"
            title="Stop trading engine process (open positions remain protected)"
            className="iea-pill-control px-3.5 py-1.5 disabled:opacity-40 text-[#F4F7FF] text-xs font-semibold inline-flex items-center space-x-1.5 transition duration-200"
          >
            <Square className="w-3.5 h-3.5 text-[#FF5A6E]" />
            <span>Stop</span>
          </button>

          <button
            type="button"
            disabled={busyAction !== null}
            onClick={() => setConfirmModal({ step: 1 })}
            aria-label="Close all bot-owned positions (two-step confirmation)"
            title="Close all bot-owned positions at market (2-step confirmation)"
            className="px-4 py-1.5 rounded-full bg-gradient-to-r from-[#FF5A6E] to-[#E11D48] hover:brightness-110 disabled:opacity-40 text-white text-xs font-bold inline-flex items-center space-x-1.5 shadow-[0_4px_16px_rgba(255,90,110,0.4)] transition duration-200"
          >
            <XCircle className="w-3.5 h-3.5" />
            <span>Close All</span>
          </button>
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
          title={UI_COPY.kpis.balEq.tooltip}
        >
          <div className="flex items-center justify-between text-xs text-[#B6C5E0]">
            <span className="font-medium">{UI_COPY.kpis.balEq.label}</span>
            <span
              title="Account Margin Leverage"
              className="font-mono text-[10px] text-[#B0F648] bg-[#B0F648]/14 border border-[#B0F648]/30 px-2 py-0.5 rounded-full"
            >
              Lev 1:{effectiveStatus.mt5.account.leverage}
            </span>
          </div>
          <div className="text-[clamp(1.35rem,1.8vw,1.75rem)] font-light font-mono tabular-nums tracking-tight text-[#F4F7FF] mt-2">
            ${kpis.equity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="text-[11px] font-mono tabular-nums text-[#8496B8] mt-1.5 flex items-center justify-between">
            <span>Bal ${kpis.balance.toLocaleString(undefined, { minimumFractionDigits: 0 })}</span>
            <span
              className={
                kpis.floatingPnl >= 0 ? "text-[#B0F648] font-semibold" : "text-[#FF5A6E] font-semibold"
              }
            >
              {kpis.floatingPnl >= 0 ? "+" : ""}${kpis.floatingPnl.toFixed(2)}
            </span>
          </div>
        </div>

        {/* 2. Today P&L (Primary Accent Highlight) */}
        <div
          className="iea-glass-card-lime p-4 flex flex-col justify-between min-h-[112px]"
          title={UI_COPY.kpis.todayPnl.tooltip}
        >
          <div className="flex items-center justify-between text-xs text-[#C2F076]">
            <span className="font-medium">{UI_COPY.kpis.todayPnl.label}</span>
            {kpis.todayPnlUsd >= 0 ? (
              <TrendingUp className="w-4 h-4 text-[#B0F648]" />
            ) : (
              <TrendingDown className="w-4 h-4 text-[#FF5A6E]" />
            )}
          </div>
          <div
            className={`text-[clamp(1.35rem,1.8vw,1.75rem)] font-light font-mono tabular-nums tracking-tight mt-2 ${
              kpis.todayPnlUsd >= 0 ? "text-[#B0F648]" : "text-[#FF5A6E]"
            }`}
          >
            {kpis.todayPnlUsd >= 0 ? "+" : ""}${kpis.todayPnlUsd.toFixed(2)}{" "}
            <span className="text-xs font-semibold">
              ({kpis.todayPnlR >= 0 ? "+" : ""}
              {kpis.todayPnlR.toFixed(2)}R)
            </span>
          </div>
          <div className="text-[11px] font-mono tabular-nums text-[#B6C5E0] mt-1.5">
            1R = ${(kpis.balance * 0.005).toFixed(2)} (0.5%)
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

        {/* 5. Open Exp (Simplified — no manual adoption counters) */}
        <div
          className="iea-glass-card p-4 flex flex-col justify-between min-h-[112px]"
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
            onSelectSymbol={setSelectedSymbol}
            onSelectTimeframe={setSelectedTimeframe}
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
          TWO-STEP CONFIRMATION MODAL (Close All Bot Positions)
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
                Close all bot trades? ({confirmModal.step}/2)
              </h3>
            </div>

            {confirmModal.step === 1 ? (
              <p className="text-xs text-[#B6C5E0]">
                Close{" "}
                <strong className="text-[#F4F7FF]">{botOpenCount} bot positions</strong> at market on
                DEMO <span className="font-mono">{dash.maskedAccount}</span>?
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
                {confirmModal.step === 1 ? "Next →" : "Close All"}
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
