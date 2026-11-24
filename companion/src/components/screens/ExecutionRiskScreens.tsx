import React, { useState } from "react";
import { Edit3, Play, Trash2, XCircle } from "lucide-react";
import { controlClient } from "../../services/ipc";
import { ControlPosition, ControlStatusPayload, TradeHistoryRecord } from "../../types";
import { getNeutralSymbolChipSpec } from "../../styles/designTokens";

export const PositionsScreen: React.FC<{
  status: ControlStatusPayload | null;
  onRefresh: () => Promise<void>;
  onActionMessage: (msg: string, isError?: boolean) => void;
  readOnly?: boolean;
}> = ({ status, onRefresh, onActionMessage, readOnly = false }) => {
  const positions = status?.mt5.positions || [];
  const pendingOrders = status?.mt5.pending_orders || [];
  const [editing, setEditing] = useState<ControlPosition | null>(null);
  const [slInput, setSlInput] = useState("");
  const [tpInput, setTpInput] = useState("");
  const [busy, setBusy] = useState(false);

  const openModify = (p: ControlPosition) => {
    setEditing(p);
    setSlInput(String(p.sl || 0));
    setTpInput(String(p.tp || 0));
  };

  const submitModify = async () => {
    if (!editing) return;
    setBusy(true);
    try {
      const res = await controlClient.modifyPosition(editing.ticket, Number(slInput), Number(tpInput));
      onActionMessage(res.message, !res.success);
      setEditing(null);
      await onRefresh();
    } catch (e: any) {
      onActionMessage(`Modify failed: ${e.message}`, true);
    } finally {
      setBusy(false);
    }
  };

  const handleClose = async (ticket: number) => {
    if (!window.confirm(`Close position #${ticket} at market?`)) return;
    setBusy(true);
    try {
      const res = await controlClient.closePosition(ticket, true);
      onActionMessage(res.message, !res.success);
      await onRefresh();
    } catch (e: any) {
      onActionMessage(`Close failed: ${e.message}`, true);
    } finally {
      setBusy(false);
    }
  };

  const handleCloseAllBot = async () => {
    if (!window.confirm("Close all bot trades? Manual trades stay untouched.")) return;
    setBusy(true);
    try {
      const res = await controlClient.closeAllBotPositions(true);
      onActionMessage(res.message, !res.success);
      await onRefresh();
    } catch (e: any) {
      onActionMessage(`Close all failed: ${e.message}`, true);
    } finally {
      setBusy(false);
    }
  };

  const handleCancelOrder = async (ticket: number) => {
    if (!window.confirm(`Cancel order #${ticket}?`)) return;
    setBusy(true);
    try {
      const res = await controlClient.cancelPendingOrder(ticket, true);
      onActionMessage(res.message, !res.success);
      await onRefresh();
    } catch (e: any) {
      onActionMessage(`Cancel failed: ${e.message}`, true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="iea-card p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold text-iea-textPrimary" title="MT5 positions reconciled by Magic Number">
            Open Pos ({positions.length})
          </h2>
          {!readOnly && (
            <button
              disabled={busy || positions.filter((p) => p.ownership === "BOT").length === 0}
              onClick={handleCloseAllBot}
              className="px-4 py-1.5 bg-iea-danger hover:opacity-90 disabled:opacity-40 text-white text-xs font-bold rounded-full transition"
            >
              Close Bot Pos
            </button>
          )}
        </div>

        <div className="overflow-x-auto rounded-2xl border border-iea-borderSubtle">
          <table className="w-full text-left text-xs iea-table">
            <thead>
              <tr>
                <th className="py-3 pl-4 pr-3">#</th>
                <th className="py-3 pr-3">Instr</th>
                <th className="py-3 pr-3">Owner</th>
                <th className="py-3 pr-3">Side</th>
                <th className="py-3 pr-3">Lot</th>
                <th className="py-3 pr-3">In → Now</th>
                <th className="py-3 pr-3">SL / TP</th>
                <th className="py-3 pr-3">P&amp;L</th>
                <th className="py-3 pr-4 text-right">Cmd</th>
              </tr>
            </thead>
            <tbody className="font-mono">
              {positions.length === 0 ? (
                <tr>
                  <td colSpan={9} className="py-8 text-center text-iea-textMuted font-sans">
                    0 open positions.
                  </td>
                </tr>
              ) : (
                positions.map((p, idx) => {
                  const chip = getNeutralSymbolChipSpec(p.symbol);
                  return (
                    <tr key={p.ticket}>
                      <td className="py-3 pl-4 pr-3 text-iea-textMuted">{idx + 1}</td>
                      <td className="py-3 pr-3">
                        <div className="flex items-center space-x-2.5">
                          <span
                            className={`w-7 h-7 rounded-full text-[11px] font-extrabold inline-flex items-center justify-center ${chip.chipBg} ${chip.chipRing}`}
                          >
                            {chip.shortCode}
                          </span>
                          <div>
                            <div className="font-bold text-iea-textPrimary">{p.symbol}</div>
                            <div className="text-[10px] font-sans text-iea-textMuted">#{p.ticket}</div>
                          </div>
                        </div>
                      </td>
                      <td className="py-3 pr-3 font-sans">
                        <span
                          className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold ${
                            p.ownership === "BOT"
                              ? "bg-iea-accentSoft text-iea-accent border border-iea-accentBorder"
                              : p.ownership === "MANUAL"
                              ? "bg-iea-elevated text-iea-textPrimary border border-iea-borderDefault"
                              : "bg-iea-inset text-iea-textSecondary"
                          }`}
                        >
                          {p.ownership}
                        </span>
                      </td>
                      <td className={`py-3 pr-3 font-bold ${p.direction === "BUY" ? "text-iea-profit" : "text-iea-danger"}`}>{p.direction}</td>
                      <td className="py-3 pr-3 text-iea-textPrimary">{p.volume.toFixed(2)}</td>
                      <td className="py-3 pr-3 text-iea-textSecondary">{p.open_price.toFixed(2)} → {p.current_price.toFixed(2)}</td>
                      <td className="py-3 pr-3">
                        <span className={p.protected ? "text-iea-danger" : "text-iea-danger font-bold"}>
                          {p.sl > 0 ? p.sl.toFixed(2) : "NO SL"}
                        </span>{" "}
                        / <span className="text-iea-profit">{p.tp > 0 ? p.tp.toFixed(2) : "-"}</span>
                      </td>
                      <td className={`py-3 pr-3 font-bold ${p.profit >= 0 ? "text-iea-profit" : "text-iea-danger"}`}>
                        {p.profit >= 0 ? "+" : ""}${p.profit.toFixed(2)}
                      </td>
                      <td className="py-3 pr-4 text-right space-x-1.5 font-sans">
                        {readOnly ? (
                          <span className="text-[10px] text-iea-textMuted font-mono">READ-ONLY</span>
                        ) : (
                          <>
                            <button
                              onClick={() => openModify(p)}
                              className="iea-pill-control px-2.5 py-1 text-iea-textPrimary inline-flex items-center space-x-1"
                            >
                              <Edit3 className="w-3 h-3 text-iea-accent" />
                              <span>SL/TP</span>
                            </button>
                            <button
                              disabled={busy}
                              onClick={() => handleClose(p.ticket)}
                              className="px-2.5 py-1 bg-iea-danger hover:opacity-90 text-white rounded-full inline-flex items-center space-x-1 font-semibold"
                            >
                              <XCircle className="w-3 h-3" />
                              <span>Close</span>
                            </button>
                          </>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pending Orders */}
      <div className="iea-card p-5">
        <h3 className="text-sm font-bold text-iea-textPrimary mb-3">Pending Ord ({pendingOrders.length})</h3>
        {pendingOrders.length === 0 ? (
          <div className="text-xs text-iea-textMuted py-3">0 pending orders.</div>
        ) : (
          <div className="space-y-2">
            {pendingOrders.map((o: any) => {
              const chip = getNeutralSymbolChipSpec(o.symbol);
              return (
                <div key={o.ticket} className="iea-inset flex items-center justify-between px-3.5 py-2.5 text-xs font-mono">
                  <div className="flex items-center space-x-2.5">
                    <span
                      className={`w-6 h-6 rounded-full text-[10px] font-extrabold inline-flex items-center justify-center ${chip.chipBg}`}
                    >
                      {chip.shortCode}
                    </span>
                    <span className="text-iea-textPrimary">
                      #{o.ticket} · <strong>{o.symbol}</strong> · {o.volume}L @ {o.price} (SL {o.sl} / TP {o.tp})
                    </span>
                  </div>
                  <button
                    onClick={() => handleCancelOrder(o.ticket)}
                    className="px-3 py-1 bg-iea-danger hover:opacity-90 text-white rounded-full font-sans font-semibold inline-flex items-center space-x-1"
                  >
                    <Trash2 className="w-3 h-3" />
                    <span>Cancel</span>
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {editing && (
        <div className="fixed inset-0 bg-[var(--overlay-bg)] backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="iea-card p-5 w-full max-w-sm space-y-3.5 shadow-2xl">
            <h3 className="text-sm font-bold text-iea-textPrimary">SL/TP · #{editing.ticket} ({editing.symbol})</h3>
            <div className="space-y-2.5 text-xs">
              <label className="block">
                <span className="text-iea-textSecondary">SL</span>
                <input
                  type="number"
                  step="any"
                  value={slInput}
                  onChange={(e) => setSlInput(e.target.value)}
                  className="w-full mt-1 iea-input px-3 py-2 font-mono"
                />
              </label>
              <label className="block">
                <span className="text-iea-textSecondary">TP</span>
                <input
                  type="number"
                  step="any"
                  value={tpInput}
                  onChange={(e) => setTpInput(e.target.value)}
                  className="w-full mt-1 iea-input px-3 py-2 font-mono"
                />
              </label>
            </div>
            <div className="flex justify-end space-x-2.5 pt-2">
              <button onClick={() => setEditing(null)} className="iea-pill-control px-4 py-1.5 text-xs text-iea-textPrimary">
                Cancel
              </button>
              <button disabled={busy} onClick={submitModify} className="px-4 py-1.5 bg-iea-profit hover:opacity-90 text-white text-xs font-extrabold rounded-full">
                Apply
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export const TradeHistoryScreen: React.FC<{
  trades: TradeHistoryRecord[];
  onReload: () => Promise<void>;
  onReplayTrade?: (ticket: number) => void;
}> = ({ trades, onReload, onReplayTrade }) => {
  const [symbolFilter, setSymbolFilter] = useState("ALL");
  const filtered = trades.filter((t) => symbolFilter === "ALL" || t.symbol.includes(symbolFilter));

  return (
    <div className="iea-card p-5 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-bold text-iea-textPrimary" title="Closed trades persisted in SQLite">
          Trade Hist ({filtered.length})
        </h2>
        <div className="flex items-center space-x-2">
          <div className="iea-pill-control px-3 py-1 flex items-center space-x-1.5 text-xs">
            <span className="text-iea-textMuted">Instr:</span>
            <select
              value={symbolFilter}
              onChange={(e) => setSymbolFilter(e.target.value)}
              className="bg-transparent text-xs text-iea-textPrimary font-semibold focus:outline-none"
            >
              <option value="ALL" className="bg-iea-card">All</option>
              <option value="XAU" className="bg-iea-card">XAUUSD</option>
              <option value="JPY" className="bg-iea-card">USDJPY</option>
              <option value="BTC" className="bg-iea-card">BTCUSD</option>
            </select>
          </div>
          <button onClick={() => onReload()} className="iea-pill-control px-4 py-1.5 text-xs text-iea-textPrimary font-semibold">
            Refresh
          </button>
        </div>
      </div>

      <div className="overflow-x-auto rounded-2xl border border-iea-borderSubtle">
        <table className="w-full text-left text-xs iea-table">
          <thead>
            <tr>
              <th className="py-3 pl-4 pr-3">#</th>
              <th className="py-3 pr-3">Instr</th>
              <th className="py-3 pr-3">Side</th>
              <th className="py-3 pr-3">Lot</th>
              <th className="py-3 pr-3">In</th>
              <th className="py-3 pr-3">Out</th>
              <th className="py-3 pr-3">P&amp;L</th>
              <th className="py-3 pr-3">Result</th>
              <th className="py-3 pr-4 text-right">Replay</th>
            </tr>
          </thead>
          <tbody className="font-mono">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={9} className="py-8 text-center text-iea-textMuted font-sans">
                  No closed trades yet.
                </td>
              </tr>
            ) : (
              filtered.map((t, idx) => {
                const chip = getNeutralSymbolChipSpec(t.symbol);
                return (
                  <tr key={t.id}>
                    <td className="py-3 pl-4 pr-3 text-iea-textMuted">{idx + 1}</td>
                    <td className="py-3 pr-3">
                      <div className="flex items-center space-x-2.5">
                        <span
                          className={`w-7 h-7 rounded-full text-[11px] font-extrabold inline-flex items-center justify-center ${chip.chipBg} ${chip.chipRing}`}
                        >
                          {chip.shortCode}
                        </span>
                        <div>
                          <div className="font-bold text-iea-textPrimary">{t.symbol}</div>
                          <div className="text-[10px] font-sans text-iea-textMuted">#{t.ticket}</div>
                        </div>
                      </div>
                    </td>
                    <td className={`py-3 pr-3 font-bold ${t.direction === "BUY" ? "text-iea-profit" : "text-iea-danger"}`}>{t.direction}</td>
                    <td className="py-3 pr-3 text-iea-textPrimary">{t.volume.toFixed(2)}</td>
                    <td className="py-3 pr-3 text-iea-textSecondary">{t.open_price.toFixed(2)}</td>
                    <td className="py-3 pr-3 text-iea-textSecondary">{t.close_price ? t.close_price.toFixed(2) : "-"}</td>
                    <td className={`py-3 pr-3 font-bold ${t.profit >= 0 ? "text-iea-profit" : "text-iea-danger"}`}>
                      {t.profit >= 0 ? "+" : ""}${t.profit.toFixed(2)}
                    </td>
                    <td className="py-3 pr-3 font-sans">
                      <span
                        className={`px-2.5 py-0.5 rounded-full text-[10px] font-semibold ${
                          t.profit >= 0
                            ? "bg-iea-profitSoft text-iea-profit border border-iea-profitBorder"
                            : "bg-iea-dangerSoft text-iea-danger border border-iea-dangerBorder"
                        }`}
                      >
                        {t.status}
                      </span>
                    </td>
                    <td className="py-3 pr-4 text-right font-sans">
                      {onReplayTrade && (
                        <button
                          type="button"
                          onClick={() => onReplayTrade(t.ticket)}
                          className="iea-pill-control px-2.5 py-1 text-[11px] text-iea-accent hover:text-iea-textPrimary inline-flex items-center space-x-1 font-semibold"
                        >
                          <Play className="w-3 h-3" />
                          <span>Replay</span>
                        </button>
                      )}
                    </td>
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
