import React, { useState } from "react";
import {
  Layers,
  ArrowUpRight,
  ArrowDownRight,
  ShieldCheck,
  ShieldAlert,
  Bot,
  User,
  XCircle,
  Sliders,
  TrendingUp,
  Clock,
  PlusCircle,
  Trash2,
  CheckCircle2,
  AlertCircle
} from "lucide-react";
import { ActivePosition, PendingOrder } from "../types";
import { IPC } from "../services/ipc";

interface PositionsTableProps {
  positions: ActivePosition[];
  pendingOrders?: PendingOrder[];
  onRefresh?: () => void;
}

export const PositionsTable: React.FC<PositionsTableProps> = ({
  positions,
  pendingOrders = [],
  onRefresh
}) => {
  const [activeTab, setActiveTab] = useState<"positions" | "pending">("positions");
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // Modals state
  const [modifyModal, setModifyModal] = useState<{
    isOpen: boolean;
    ticket: number;
    symbol: string;
    sl: number;
    tp: number;
    price?: number;
    isPending?: boolean;
  } | null>(null);

  const [closeModal, setCloseModal] = useState<{
    isOpen: boolean;
    ticket: number;
    symbol: string;
    maxVolume: number;
    volumeToClose: number;
  } | null>(null);

  const [trailModal, setTrailModal] = useState<{
    isOpen: boolean;
    ticket: number;
    symbol: string;
    points: number;
  } | null>(null);

  const [placePendingModal, setPlacePendingModal] = useState<{
    isOpen: boolean;
    symbol: string;
    type: string;
    volume: number;
    price: number;
    sl: number;
    tp: number;
  } | null>(null);

  const showFeedback = (type: "success" | "error", text: string) => {
    setFeedback({ type, text });
    setTimeout(() => setFeedback(null), 4000);
  };

  const manualPositions = positions.filter((p) => p.isManual ?? (p.magic === 0));
  const automatedPositions = positions.filter((p) => !(p.isManual ?? (p.magic === 0)));
  const protectedManual = manualPositions.filter((p) => p.sl > 0);
  const awaitingSlManual = manualPositions.filter((p) => p.sl <= 0);

  // Trade action handlers
  const handleBreakEven = async (ticket: number) => {
    setActionLoading(`be-${ticket}`);
    try {
      const res = await IPC.setBreakEven(ticket);
      showFeedback(res.success ? "success" : "error", res.message);
      if (onRefresh) onRefresh();
    } catch (e: any) {
      showFeedback("error", e.message || "Failed to set break-even.");
    } finally {
      setActionLoading(null);
    }
  };

  const handleApplyTrailing = async () => {
    if (!trailModal) return;
    setActionLoading(`trail-${trailModal.ticket}`);
    try {
      const res = await IPC.setTrailingStop(trailModal.ticket, trailModal.points);
      showFeedback(res.success ? "success" : "error", res.message);
      setTrailModal(null);
      if (onRefresh) onRefresh();
    } catch (e: any) {
      showFeedback("error", e.message || "Failed to set trailing stop.");
    } finally {
      setActionLoading(null);
    }
  };

  const handleSaveModify = async () => {
    if (!modifyModal) return;
    setActionLoading(`mod-${modifyModal.ticket}`);
    try {
      if (modifyModal.isPending) {
        const res = await IPC.modifyPendingOrder(
          modifyModal.ticket,
          modifyModal.price,
          modifyModal.sl,
          modifyModal.tp
        );
        showFeedback(res.success ? "success" : "error", res.message);
      } else {
        const res = await IPC.modifyPosition(modifyModal.ticket, modifyModal.sl, modifyModal.tp);
        showFeedback(res.success ? "success" : "error", res.message);
      }
      setModifyModal(null);
      if (onRefresh) onRefresh();
    } catch (e: any) {
      showFeedback("error", e.message || "Failed to modify order.");
    } finally {
      setActionLoading(null);
    }
  };

  const handleClosePosition = async () => {
    if (!closeModal) return;
    setActionLoading(`close-${closeModal.ticket}`);
    try {
      const isFull = closeModal.volumeToClose >= closeModal.maxVolume;
      const res = await IPC.closePosition(
        closeModal.ticket,
        isFull ? undefined : closeModal.volumeToClose
      );
      showFeedback(res.success ? "success" : "error", res.message);
      setCloseModal(null);
      if (onRefresh) onRefresh();
    } catch (e: any) {
      showFeedback("error", e.message || "Failed to close position.");
    } finally {
      setActionLoading(null);
    }
  };

  const handleCancelPending = async (ticket: number) => {
    setActionLoading(`cancel-${ticket}`);
    try {
      const res = await IPC.cancelPendingOrder(ticket);
      showFeedback(res.success ? "success" : "error", res.message);
      if (onRefresh) onRefresh();
    } catch (e: any) {
      showFeedback("error", e.message || "Failed to cancel order.");
    } finally {
      setActionLoading(null);
    }
  };

  const handleCancelAllPending = async () => {
    setActionLoading("cancel-all");
    try {
      const res = await IPC.cancelAllPendingOrders();
      showFeedback(res.success ? "success" : "error", res.message);
      if (onRefresh) onRefresh();
    } catch (e: any) {
      showFeedback("error", e.message || "Failed to cancel all pending orders.");
    } finally {
      setActionLoading(null);
    }
  };

  const handlePlacePending = async () => {
    if (!placePendingModal) return;
    setActionLoading("place-pending");
    try {
      const res = await IPC.placePendingOrder({
        symbol: placePendingModal.symbol,
        orderType: placePendingModal.type,
        volume: placePendingModal.volume,
        price: placePendingModal.price,
        sl: placePendingModal.sl > 0 ? placePendingModal.sl : undefined,
        tp: placePendingModal.tp > 0 ? placePendingModal.tp : undefined,
      });
      showFeedback(res.success ? "success" : "error", res.message);
      setPlacePendingModal(null);
      if (onRefresh) onRefresh();
    } catch (e: any) {
      showFeedback("error", e.message || "Failed to place pending order.");
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div className="p-3 sm:px-4 sm:py-3.5 bg-institutional-ea-bg transition-colors duration-150">
      {/* Header and Tab Navigation */}
      <div className="flex flex-wrap items-center justify-between gap-2.5 mb-2.5">
        <div className="flex items-center gap-2">
          {/* Two-Tab Navigation: Open Positions | Pending Orders */}
          <div className="inline-flex rounded-xl bg-institutional-ea-card p-1 border border-institutional-ea-border shadow-xs">
            <button
              type="button"
              onClick={() => setActiveTab("positions")}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-2 cursor-pointer ${
                activeTab === "positions"
                  ? "bg-institutional-ea-primary text-white shadow-xs"
                  : "text-institutional-ea-textSecondary hover:text-institutional-ea-text hover:bg-institutional-ea-secondary/60"
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              <span>Open Positions ({positions.length})</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("pending")}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-2 cursor-pointer ${
                activeTab === "pending"
                  ? "bg-institutional-ea-primary text-white shadow-xs"
                  : "text-institutional-ea-textSecondary hover:text-institutional-ea-text hover:bg-institutional-ea-secondary/60"
              }`}
            >
              <Clock className="w-3.5 h-3.5" />
              <span>Pending Orders ({pendingOrders.length})</span>
            </button>
          </div>

          {/* Manual Trade Protection Telemetry Pills */}
          {activeTab === "positions" && manualPositions.length > 0 && (
            <div className="hidden sm:flex items-center gap-1.5 ml-1">
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-bold font-mono bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/25">
                <User className="w-3 h-3" />
                Manual: {manualPositions.length}
              </span>

              {protectedManual.length > 0 && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-bold font-mono bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/25">
                  <ShieldCheck className="w-3 h-3" />
                  Protected: {protectedManual.length}
                </span>
              )}

              {awaitingSlManual.length > 0 && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-bold font-mono bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/25">
                  <ShieldAlert className="w-3 h-3" />
                  Awaiting SL: {awaitingSlManual.length}
                </span>
              )}
            </div>
          )}
        </div>

        {/* Tab Right Controls */}
        <div className="flex items-center gap-2">
          {activeTab === "pending" && (
            <>
              <button
                type="button"
                onClick={() =>
                  setPlacePendingModal({
                    isOpen: true,
                    symbol: positions[0]?.symbol || "BTCUSD.m",
                    type: "BUY_LIMIT",
                    volume: 0.01,
                    price: 0,
                    sl: 0,
                    tp: 0
                  })
                }
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-institutional-ea-primary hover:bg-institutional-ea-primaryHover active:scale-[0.98] text-white text-xs font-bold transition-all shadow-xs cursor-pointer"
              >
                <PlusCircle className="w-3.5 h-3.5" />
                <span>Place Order</span>
              </button>
              {pendingOrders.length > 0 && (
                <button
                  type="button"
                  onClick={handleCancelAllPending}
                  disabled={actionLoading === "cancel-all"}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-600 dark:text-rose-400 border border-rose-500/30 text-xs font-bold transition-colors cursor-pointer disabled:opacity-50"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  <span>Cancel All</span>
                </button>
              )}
            </>
          )}

          {activeTab === "positions" && positions.length > 0 && (
            <span className="hidden md:inline-flex text-[11px] text-institutional-ea-textMuted px-2.5 py-1 rounded-lg bg-institutional-ea-card border border-institutional-ea-border font-mono shadow-xs">
              Auto: {automatedPositions.length} | Manual: {manualPositions.length}
            </span>
          )}
        </div>
      </div>

      {/* Action Toast Feedback */}
      {feedback && (
        <div className="mb-2.5 flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium border bg-institutional-ea-surface text-institutional-ea-text border-institutional-ea-border animate-institutional-ea-slide">
          {feedback.type === "success" ? (
            <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
          ) : (
            <AlertCircle className="w-4 h-4 text-rose-500 shrink-0" />
          )}
          <span>{feedback.text}</span>
        </div>
      )}

      {/* Main Table / Empty State Container */}
      <div className="institutional-ea-card overflow-hidden shadow-xs">
        {activeTab === "positions" ? (
          /* ========================================================================= */
          /* ACTIVE POSITIONS TABLE / EMPTY STATE                                       */
          /* ========================================================================= */
          positions.length === 0 ? (
            <div className="py-12 px-4 text-center space-y-2 select-none">
              <div className="w-12 h-12 rounded-2xl bg-institutional-ea-secondary border border-institutional-ea-border flex items-center justify-center mx-auto text-institutional-ea-textMuted">
                <Layers className="w-6 h-6 stroke-[1.8]" />
              </div>
              <h3 className="text-sm font-bold text-institutional-ea-text tracking-tight font-sans">
                No active market positions
              </h3>
              <p className="text-xs text-institutional-ea-textMuted max-w-md mx-auto leading-relaxed font-sans">
                Your open positions will appear here as soon as trades are executed through MT5 or bot automation.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-institutional-ea-surfaceSecondary text-institutional-ea-textSecondary text-[10px] uppercase font-sans font-bold border-b border-institutional-ea-border select-none">
                  <tr>
                    <th className="py-2.5 px-3">Ticket</th>
                    <th className="py-2.5 px-3">Origin</th>
                    <th className="py-2.5 px-3">Symbol</th>
                    <th className="py-2.5 px-3">Type</th>
                    <th className="py-2.5 px-3">Lots</th>
                    <th className="py-2.5 px-3">Open Price</th>
                    <th className="py-2.5 px-3">Current Price</th>
                    <th className="py-2.5 px-3">Stop Loss</th>
                    <th className="py-2.5 px-3">Take Profit</th>
                    <th className="py-2.5 px-3 text-right">Profit ($)</th>
                    <th className="py-2.5 px-3 text-center">Manage</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-institutional-ea-border font-mono">
                  {positions.map((pos) => {
                    const isBuy = pos.orderType === "BUY";
                    const isProfitable = pos.profit > 0.0001;
                    const isLoss = pos.profit < -0.0001;
                    const isManual = pos.isManual ?? (pos.magic === 0);

                    return (
                      <tr
                        key={pos.ticket}
                        className="hover:bg-institutional-ea-secondary/40 transition-colors"
                      >
                        {/* Ticket */}
                        <td className="py-2.5 px-3 text-institutional-ea-textSecondary font-semibold">
                          #{pos.ticket}
                        </td>

                        {/* Origin */}
                        <td className="py-2.5 px-3 font-sans">
                          {isManual ? (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/25">
                              <User className="w-2.5 h-2.5" />
                              MANUAL
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-institutional-ea-primary/10 text-institutional-ea-primary border border-institutional-ea-primary/25">
                              <Bot className="w-2.5 h-2.5" />
                              AUTO
                            </span>
                          )}
                        </td>

                        {/* Symbol */}
                        <td className="py-2.5 px-3 font-bold text-institutional-ea-text font-sans">
                          {pos.symbol}
                        </td>

                        {/* Type (BUY / SELL) */}
                        <td className="py-2.5 px-3 font-sans">
                          <span
                            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-extrabold uppercase border ${
                              isBuy
                                ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/25"
                                : "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/25"
                            }`}
                          >
                            {isBuy ? (
                              <ArrowUpRight className="w-3 h-3 stroke-[2.5]" />
                            ) : (
                              <ArrowDownRight className="w-3 h-3 stroke-[2.5]" />
                            )}
                            <span>{pos.orderType}</span>
                          </span>
                        </td>

                        {/* Lots */}
                        <td className="py-2.5 px-3 text-institutional-ea-text font-bold">
                          {pos.volume.toFixed(2)}
                        </td>

                        {/* Open Price */}
                        <td className="py-2.5 px-3 text-institutional-ea-textSecondary">
                          {pos.openPrice.toFixed(5)}
                        </td>

                        {/* Current Price */}
                        <td className="py-2.5 px-3 text-institutional-ea-text font-bold">
                          {pos.currentPrice.toFixed(5)}
                        </td>

                        {/* Stop Loss */}
                        <td className="py-2.5 px-3">
                          {pos.sl > 0 ? (
                            <span className="text-emerald-600 dark:text-emerald-400 font-semibold inline-flex items-center gap-1">
                              <ShieldCheck className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                              <span>{pos.sl.toFixed(5)}</span>
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/25 font-sans">
                              <ShieldAlert className="w-3 h-3 shrink-0" />
                              NO SL
                            </span>
                          )}
                        </td>

                        {/* Take Profit */}
                        <td className="py-2.5 px-3 text-institutional-ea-textSecondary">
                          {pos.tp > 0 ? pos.tp.toFixed(5) : "—"}
                        </td>

                        {/* Profit */}
                        <td
                          className={`py-2.5 px-3 text-right font-bold text-sm ${
                            isProfitable
                              ? "text-emerald-600 dark:text-emerald-400"
                              : isLoss
                              ? "text-rose-600 dark:text-rose-400"
                              : "text-institutional-ea-text"
                          }`}
                        >
                          {isProfitable ? "+" : isLoss ? "-" : ""}$
                          {Math.abs(pos.profit).toFixed(2)}
                        </td>

                        {/* Manage Actions */}
                        <td className="py-2.5 px-3">
                          <div className="flex items-center justify-center gap-1 font-sans">
                            {/* Break Even */}
                            <button
                              type="button"
                              onClick={() => handleBreakEven(pos.ticket)}
                              disabled={actionLoading !== null}
                              title="Move Stop Loss to Entry Price (Break-Even)"
                              className="px-2 py-1 rounded-md bg-institutional-ea-card hover:bg-institutional-ea-secondary text-institutional-ea-text border border-institutional-ea-border text-[10px] font-bold transition-colors cursor-pointer disabled:opacity-50 shadow-xs"
                            >
                              BE
                            </button>

                            {/* Trailing Stop */}
                            <button
                              type="button"
                              onClick={() =>
                                setTrailModal({
                                  isOpen: true,
                                  ticket: pos.ticket,
                                  symbol: pos.symbol,
                                  points: 200
                                })
                              }
                              title="Set Trailing Stop"
                              className="p-1 rounded-md bg-institutional-ea-card hover:bg-institutional-ea-secondary text-institutional-ea-text border border-institutional-ea-border text-[10px] font-bold transition-colors cursor-pointer shadow-xs"
                            >
                              <TrendingUp className="w-3.5 h-3.5 text-institutional-ea-primary" />
                            </button>

                            {/* Edit SL/TP */}
                            <button
                              type="button"
                              onClick={() =>
                                setModifyModal({
                                  isOpen: true,
                                  ticket: pos.ticket,
                                  symbol: pos.symbol,
                                  sl: pos.sl,
                                  tp: pos.tp,
                                  isPending: false
                                })
                              }
                              title="Edit Stop Loss & Take Profit"
                              className="p-1 rounded-md bg-institutional-ea-card hover:bg-institutional-ea-secondary text-institutional-ea-text border border-institutional-ea-border text-[10px] font-bold transition-colors cursor-pointer shadow-xs"
                            >
                              <Sliders className="w-3.5 h-3.5 text-institutional-ea-textSecondary" />
                            </button>

                            {/* Close Position */}
                            <button
                              type="button"
                              onClick={() =>
                                setCloseModal({
                                  isOpen: true,
                                  ticket: pos.ticket,
                                  symbol: pos.symbol,
                                  maxVolume: pos.volume,
                                  volumeToClose: pos.volume
                                })
                              }
                              title="Close Position (Full or Partial)"
                              className="px-2.5 py-1 rounded-md bg-rose-500/10 hover:bg-rose-500/20 text-rose-600 dark:text-rose-400 border border-rose-500/30 text-[10px] font-bold transition-colors cursor-pointer"
                            >
                              Close
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )
        ) : (
          /* ========================================================================= */
          /* PENDING ORDERS TABLE / EMPTY STATE                                        */
          /* ========================================================================= */
          pendingOrders.length === 0 ? (
            <div className="py-12 px-4 text-center space-y-2 select-none">
              <div className="w-12 h-12 rounded-2xl bg-institutional-ea-secondary border border-institutional-ea-border flex items-center justify-center mx-auto text-institutional-ea-textMuted">
                <Clock className="w-6 h-6 stroke-[1.8]" />
              </div>
              <h3 className="text-sm font-bold text-institutional-ea-text tracking-tight font-sans">
                No pending orders
              </h3>
              <p className="text-xs text-institutional-ea-textMuted max-w-md mx-auto leading-relaxed font-sans">
                Your pending limit and stop orders submitted by bot automation or placed manually will appear here.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-institutional-ea-surfaceSecondary text-institutional-ea-textSecondary text-[10px] uppercase font-sans font-bold border-b border-institutional-ea-border select-none">
                  <tr>
                    <th className="py-2.5 px-3">Ticket</th>
                    <th className="py-2.5 px-3">Symbol</th>
                    <th className="py-2.5 px-3">Type</th>
                    <th className="py-2.5 px-3">Lots</th>
                    <th className="py-2.5 px-3">Target Price</th>
                    <th className="py-2.5 px-3">Stop Loss</th>
                    <th className="py-2.5 px-3">Take Profit</th>
                    <th className="py-2.5 px-3 text-center">Manage</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-institutional-ea-border font-mono">
                  {pendingOrders.map((ord) => (
                    <tr
                      key={ord.ticket}
                      className="hover:bg-institutional-ea-secondary/40 transition-colors"
                    >
                      <td className="py-2.5 px-3 text-institutional-ea-textSecondary font-semibold">
                        #{ord.ticket}
                      </td>
                      <td className="py-2.5 px-3 font-bold text-institutional-ea-text font-sans">
                        {ord.symbol}
                      </td>
                      <td className="py-2.5 px-3 font-sans">
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-institutional-ea-primary/10 text-institutional-ea-primary border border-institutional-ea-primary/25">
                          {ord.orderType}
                        </span>
                      </td>
                      <td className="py-2.5 px-3 text-institutional-ea-text font-bold">
                        {ord.volume.toFixed(2)}
                      </td>
                      <td className="py-2.5 px-3 text-institutional-ea-text font-bold">
                        {ord.price.toFixed(5)}
                      </td>
                      <td className="py-2.5 px-3 text-institutional-ea-textSecondary">
                        {ord.sl > 0 ? ord.sl.toFixed(5) : "—"}
                      </td>
                      <td className="py-2.5 px-3 text-institutional-ea-textSecondary">
                        {ord.tp > 0 ? ord.tp.toFixed(5) : "—"}
                      </td>
                      <td className="py-2.5 px-3 font-sans">
                        <div className="flex items-center justify-center gap-1.5">
                          {/* Modify Pending Order */}
                          <button
                            type="button"
                            onClick={() =>
                              setModifyModal({
                                isOpen: true,
                                ticket: ord.ticket,
                                symbol: ord.symbol,
                                price: ord.price,
                                sl: ord.sl,
                                tp: ord.tp,
                                isPending: true
                              })
                            }
                            title="Modify Price, SL, TP"
                            className="p-1 rounded-md bg-institutional-ea-card hover:bg-institutional-ea-secondary text-institutional-ea-text border border-institutional-ea-border text-[10px] font-bold transition-colors cursor-pointer shadow-xs"
                          >
                            <Sliders className="w-3.5 h-3.5 text-institutional-ea-textSecondary" />
                          </button>

                          {/* Cancel Order */}
                          <button
                            type="button"
                            onClick={() => handleCancelPending(ord.ticket)}
                            disabled={actionLoading !== null}
                            title="Cancel Order"
                            className="px-2.5 py-1 rounded-md bg-rose-500/10 hover:bg-rose-500/20 text-rose-600 dark:text-rose-400 border border-rose-500/30 text-[10px] font-bold transition-colors cursor-pointer disabled:opacity-50"
                          >
                            Cancel
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        )}
      </div>

      {/* MODAL: Modify SL / TP / Price */}
      {modifyModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-institutional-ea-fade">
          <div className="bg-institutional-ea-card border border-institutional-ea-border rounded-2xl shadow-2xl p-5 max-w-sm w-full text-institutional-ea-text space-y-4">
            <h3 className="text-sm font-bold flex items-center gap-2 text-institutional-ea-text font-sans">
              <Sliders className="w-4 h-4 text-institutional-ea-primary" />
              <span>Modify #{modifyModal.ticket} ({modifyModal.symbol})</span>
            </h3>

            <div className="space-y-3 text-xs font-sans">
              {modifyModal.isPending && (
                <div>
                  <label className="block text-institutional-ea-textSecondary mb-1 font-medium">Target Price</label>
                  <input
                    type="number"
                    step="any"
                    value={modifyModal.price || 0}
                    onChange={(e) =>
                      setModifyModal({ ...modifyModal, price: parseFloat(e.target.value) || 0 })
                    }
                    className="w-full px-3 py-1.5 bg-institutional-ea-surface border border-institutional-ea-border rounded-lg font-mono text-institutional-ea-text focus:border-institutional-ea-primary outline-none transition"
                  />
                </div>
              )}
              <div>
                <label className="block text-institutional-ea-textSecondary mb-1 font-medium">Stop Loss (0 to remove)</label>
                <input
                  type="number"
                  step="any"
                  value={modifyModal.sl}
                  onChange={(e) =>
                    setModifyModal({ ...modifyModal, sl: parseFloat(e.target.value) || 0 })
                  }
                  className="w-full px-3 py-1.5 bg-institutional-ea-surface border border-institutional-ea-border rounded-lg font-mono text-institutional-ea-text focus:border-institutional-ea-primary outline-none transition"
                />
              </div>
              <div>
                <label className="block text-institutional-ea-textSecondary mb-1 font-medium">Take Profit (0 to remove)</label>
                <input
                  type="number"
                  step="any"
                  value={modifyModal.tp}
                  onChange={(e) =>
                    setModifyModal({ ...modifyModal, tp: parseFloat(e.target.value) || 0 })
                  }
                  className="w-full px-3 py-1.5 bg-institutional-ea-surface border border-institutional-ea-border rounded-lg font-mono text-institutional-ea-text focus:border-institutional-ea-primary outline-none transition"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-institutional-ea-border">
              <button
                type="button"
                onClick={() => setModifyModal(null)}
                className="px-3.5 py-1.5 bg-institutional-ea-surface hover:bg-institutional-ea-secondary text-institutional-ea-text text-xs rounded-xl border border-institutional-ea-border transition cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSaveModify}
                disabled={actionLoading !== null}
                className="px-4 py-1.5 bg-institutional-ea-primary hover:bg-institutional-ea-primaryHover text-white text-xs font-bold rounded-xl transition cursor-pointer shadow-xs disabled:opacity-50"
              >
                Save Changes
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL: Close / Partial Close */}
      {closeModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-institutional-ea-fade">
          <div className="bg-institutional-ea-card border border-rose-500/40 rounded-2xl shadow-2xl p-5 max-w-sm w-full text-institutional-ea-text space-y-4">
            <div className="flex items-center gap-2.5 text-rose-500">
              <div className="w-8 h-8 rounded-lg bg-rose-500/10 border border-rose-500/20 flex items-center justify-center shrink-0">
                <XCircle className="w-4 h-4 text-rose-500" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-institutional-ea-text font-sans">
                  Close Position #{closeModal.ticket}
                </h3>
                <p className="text-[11px] text-institutional-ea-textMuted font-mono">
                  {closeModal.symbol} | Max Lots: {closeModal.maxVolume}
                </p>
              </div>
            </div>

            <div>
              <label className="block text-xs text-institutional-ea-textSecondary mb-1 font-medium font-sans">
                Volume to Close (Lots):
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  max={closeModal.maxVolume}
                  value={closeModal.volumeToClose}
                  onChange={(e) =>
                    setCloseModal({
                      ...closeModal,
                      volumeToClose: Math.min(
                        closeModal.maxVolume,
                        Math.max(0.01, parseFloat(e.target.value) || 0.01)
                      )
                    })
                  }
                  className="w-full px-3 py-1.5 bg-institutional-ea-surface border border-institutional-ea-border rounded-lg font-mono text-institutional-ea-text focus:border-institutional-ea-primary outline-none"
                />
                <button
                  type="button"
                  onClick={() =>
                    setCloseModal({ ...closeModal, volumeToClose: closeModal.maxVolume })
                  }
                  className="px-3 py-1.5 bg-institutional-ea-surface border border-institutional-ea-border text-institutional-ea-text text-xs rounded-lg hover:bg-institutional-ea-secondary font-bold font-sans transition cursor-pointer"
                >
                  Full
                </button>
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-institutional-ea-border">
              <button
                type="button"
                onClick={() => setCloseModal(null)}
                className="px-3.5 py-1.5 bg-institutional-ea-surface hover:bg-institutional-ea-secondary text-institutional-ea-text text-xs rounded-xl border border-institutional-ea-border transition cursor-pointer font-sans"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleClosePosition}
                disabled={actionLoading !== null}
                className="px-4 py-1.5 bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold rounded-xl transition cursor-pointer shadow-xs font-sans disabled:opacity-50"
              >
                Confirm Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL: Trailing Stop Setup */}
      {trailModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-institutional-ea-fade">
          <div className="bg-institutional-ea-card border border-institutional-ea-border rounded-2xl shadow-2xl p-5 max-w-sm w-full text-institutional-ea-text space-y-4">
            <h3 className="text-sm font-bold flex items-center gap-2 text-institutional-ea-text font-sans">
              <TrendingUp className="w-4 h-4 text-institutional-ea-primary" />
              <span>Trailing Stop #{trailModal.ticket} ({trailModal.symbol})</span>
            </h3>
            <p className="text-xs text-institutional-ea-textMuted font-sans">
              Set distance behind market price in broker points/pips.
            </p>

            <div>
              <label className="block text-xs text-institutional-ea-textSecondary mb-1 font-medium font-sans">
                Trailing Distance (Points):
              </label>
              <input
                type="number"
                step="50"
                min="10"
                value={trailModal.points}
                onChange={(e) =>
                  setTrailModal({ ...trailModal, points: parseInt(e.target.value, 10) || 100 })
                }
                className="w-full px-3 py-1.5 bg-institutional-ea-surface border border-institutional-ea-border rounded-lg font-mono text-institutional-ea-text focus:border-institutional-ea-primary outline-none"
              />
              <div className="flex gap-1.5 mt-2">
                {[100, 200, 300, 500].map((pts) => (
                  <button
                    key={pts}
                    type="button"
                    onClick={() => setTrailModal({ ...trailModal, points: pts })}
                    className="flex-1 py-1 rounded-lg bg-institutional-ea-surface hover:bg-institutional-ea-secondary border border-institutional-ea-border text-[10px] font-bold font-mono transition cursor-pointer"
                  >
                    {pts} pts
                  </button>
                ))}
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-institutional-ea-border">
              <button
                type="button"
                onClick={() => setTrailModal(null)}
                className="px-3.5 py-1.5 bg-institutional-ea-surface hover:bg-institutional-ea-secondary text-institutional-ea-text text-xs rounded-xl border border-institutional-ea-border transition cursor-pointer font-sans"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleApplyTrailing}
                disabled={actionLoading !== null}
                className="px-4 py-1.5 bg-institutional-ea-primary hover:bg-institutional-ea-primaryHover text-white text-xs font-bold rounded-xl transition cursor-pointer shadow-xs font-sans disabled:opacity-50"
              >
                Apply Trailing
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL: Place Pending Order */}
      {placePendingModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-institutional-ea-fade">
          <div className="bg-institutional-ea-card border border-institutional-ea-border rounded-2xl shadow-2xl p-5 max-w-md w-full text-institutional-ea-text space-y-4 font-sans">
            <h3 className="text-sm font-bold flex items-center gap-2 text-institutional-ea-text">
              <PlusCircle className="w-4 h-4 text-institutional-ea-primary" />
              <span>Place New Pending Order</span>
            </h3>

            <div className="space-y-3 text-xs">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-institutional-ea-textSecondary mb-1 font-medium">Symbol</label>
                  <input
                    type="text"
                    value={placePendingModal.symbol}
                    onChange={(e) =>
                      setPlacePendingModal({ ...placePendingModal, symbol: e.target.value.trim() })
                    }
                    className="w-full px-3 py-1.5 bg-institutional-ea-surface border border-institutional-ea-border rounded-lg font-mono text-institutional-ea-text focus:border-institutional-ea-primary outline-none"
                  />
                </div>
                <div>
                  <label className="block text-institutional-ea-textSecondary mb-1 font-medium">Order Type</label>
                  <select
                    value={placePendingModal.type}
                    onChange={(e) =>
                      setPlacePendingModal({ ...placePendingModal, type: e.target.value })
                    }
                    className="w-full px-3 py-1.5 bg-institutional-ea-surface border border-institutional-ea-border rounded-lg font-mono text-institutional-ea-text focus:border-institutional-ea-primary outline-none"
                  >
                    <option value="BUY_LIMIT">BUY LIMIT</option>
                    <option value="SELL_LIMIT">SELL LIMIT</option>
                    <option value="BUY_STOP">BUY STOP</option>
                    <option value="SELL_STOP">SELL STOP</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-institutional-ea-textSecondary mb-1 font-medium">Volume (Lots)</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0.01"
                    value={placePendingModal.volume}
                    onChange={(e) =>
                      setPlacePendingModal({
                        ...placePendingModal,
                        volume: parseFloat(e.target.value) || 0.01
                      })
                    }
                    className="w-full px-3 py-1.5 bg-institutional-ea-surface border border-institutional-ea-border rounded-lg font-mono text-institutional-ea-text focus:border-institutional-ea-primary outline-none"
                  />
                </div>
                <div>
                  <label className="block text-institutional-ea-textSecondary mb-1 font-medium">Order Price</label>
                  <input
                    type="number"
                    step="any"
                    value={placePendingModal.price}
                    onChange={(e) =>
                      setPlacePendingModal({
                        ...placePendingModal,
                        price: parseFloat(e.target.value) || 0
                      })
                    }
                    className="w-full px-3 py-1.5 bg-institutional-ea-surface border border-institutional-ea-border rounded-lg font-mono text-institutional-ea-text focus:border-institutional-ea-primary outline-none"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-institutional-ea-textSecondary mb-1 font-medium">Stop Loss (optional)</label>
                  <input
                    type="number"
                    step="any"
                    value={placePendingModal.sl}
                    onChange={(e) =>
                      setPlacePendingModal({
                        ...placePendingModal,
                        sl: parseFloat(e.target.value) || 0
                      })
                    }
                    className="w-full px-3 py-1.5 bg-institutional-ea-surface border border-institutional-ea-border rounded-lg font-mono text-institutional-ea-text focus:border-institutional-ea-primary outline-none"
                  />
                </div>
                <div>
                  <label className="block text-institutional-ea-textSecondary mb-1 font-medium">Take Profit (optional)</label>
                  <input
                    type="number"
                    step="any"
                    value={placePendingModal.tp}
                    onChange={(e) =>
                      setPlacePendingModal({
                        ...placePendingModal,
                        tp: parseFloat(e.target.value) || 0
                      })
                    }
                    className="w-full px-3 py-1.5 bg-institutional-ea-surface border border-institutional-ea-border rounded-lg font-mono text-institutional-ea-text focus:border-institutional-ea-primary outline-none"
                  />
                </div>
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-institutional-ea-border">
              <button
                type="button"
                onClick={() => setPlacePendingModal(null)}
                className="px-3.5 py-1.5 bg-institutional-ea-surface hover:bg-institutional-ea-secondary text-institutional-ea-text text-xs rounded-xl border border-institutional-ea-border transition cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handlePlacePending}
                disabled={actionLoading !== null || placePendingModal.price <= 0}
                className="px-4 py-1.5 bg-institutional-ea-primary hover:bg-institutional-ea-primaryHover text-white text-xs font-bold rounded-xl transition cursor-pointer shadow-xs disabled:opacity-50"
              >
                Submit Order
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
