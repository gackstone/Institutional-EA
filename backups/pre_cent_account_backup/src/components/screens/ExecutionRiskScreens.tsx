import React, { useState } from "react";
import { AlertCircle, Edit3, Layers, Shield, ShieldCheck, Trash2, XCircle } from "lucide-react";
import { controlClient } from "../../services/ipc";
import { ControlPosition, ControlStatusPayload, RiskDecisionRecord, TradeHistoryRecord } from "../../types";

export const PositionsScreen: React.FC<{
  status: ControlStatusPayload | null;
  onRefresh: () => Promise<void>;
  onActionMessage: (msg: string, isError?: boolean) => void;
}> = ({ status, onRefresh, onActionMessage }) => {
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
    if (!window.confirm(`Close position #${ticket} at market price?`)) return;
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
    if (!window.confirm("Close ALL bot-owned positions on MT5? Manual/Other EA positions will NOT be touched.")) return;
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
    if (!window.confirm(`Cancel pending order #${ticket}?`)) return;
    setBusy(true);
    try {
      const res = await controlClient.cancelPendingOrder(ticket, true);
      onActionMessage(res.message, !res.success);
      await onRefresh();
    } catch (e: any) {
      onActionMessage(`Cancel order failed: ${e.message}`, true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="text-sm font-bold text-slate-100">Open MT5 Positions ({positions.length})</h2>
            <p className="text-xs text-slate-400">Reconciled by Magic Number ownership (BOT / MANUAL / OTHER_EA).</p>
          </div>
          <button
            disabled={busy || positions.filter((p) => p.ownership === "BOT").length === 0}
            onClick={handleCloseAllBot}
            className="px-3 py-1.5 bg-rose-600 hover:bg-rose-500 disabled:opacity-40 text-white text-xs font-semibold rounded-lg"
          >
            Close All Bot Positions
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-slate-400 border-b border-slate-800">
              <tr>
                <th className="py-2 pr-3">Ticket</th>
                <th className="py-2 pr-3">Owner</th>
                <th className="py-2 pr-3">Symbol</th>
                <th className="py-2 pr-3">Dir</th>
                <th className="py-2 pr-3">Vol</th>
                <th className="py-2 pr-3">Entry / Current</th>
                <th className="py-2 pr-3">SL / TP</th>
                <th className="py-2 pr-3">P&amp;L</th>
                <th className="py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/70 font-mono">
              {positions.length === 0 ? (
                <tr>
                  <td colSpan={9} className="py-8 text-center text-slate-500 font-sans">
                    No open positions on MT5.
                  </td>
                </tr>
              ) : (
                positions.map((p) => (
                  <tr key={p.ticket} className="hover:bg-slate-800/40">
                    <td className="py-2 pr-3 text-slate-200">#{p.ticket}</td>
                    <td className="py-2 pr-3 font-sans">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          p.ownership === "BOT"
                            ? "bg-sky-500/20 text-sky-300"
                            : p.ownership === "MANUAL"
                            ? "bg-amber-500/20 text-amber-300"
                            : "bg-slate-700 text-slate-300"
                        }`}
                      >
                        {p.ownership}
                      </span>
                    </td>
                    <td className="py-2 pr-3 font-bold text-slate-100">{p.symbol}</td>
                    <td className={`py-2 pr-3 font-bold ${p.direction === "BUY" ? "text-emerald-400" : "text-rose-400"}`}>{p.direction}</td>
                    <td className="py-2 pr-3">{p.volume.toFixed(2)}</td>
                    <td className="py-2 pr-3">{p.open_price.toFixed(2)} → {p.current_price.toFixed(2)}</td>
                    <td className="py-2 pr-3">
                      <span className={p.protected ? "text-slate-200" : "text-rose-400 font-bold"}>
                        {p.sl > 0 ? p.sl.toFixed(2) : "NO SL"}
                      </span>{" "}
                      / {p.tp > 0 ? p.tp.toFixed(2) : "-"}
                    </td>
                    <td className={`py-2 pr-3 font-bold ${p.profit >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {p.profit >= 0 ? "+" : ""}${p.profit.toFixed(2)}
                    </td>
                    <td className="py-2 text-right space-x-1.5 font-sans">
                      <button
                        onClick={() => openModify(p)}
                        className="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded inline-flex items-center space-x-1"
                      >
                        <Edit3 className="w-3 h-3" />
                        <span>SL/TP</span>
                      </button>
                      <button
                        disabled={busy}
                        onClick={() => handleClose(p.ticket)}
                        className="px-2 py-1 bg-rose-600/80 hover:bg-rose-600 text-white rounded inline-flex items-center space-x-1"
                      >
                        <XCircle className="w-3 h-3" />
                        <span>Close</span>
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pending Orders */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4">
        <h3 className="text-sm font-bold text-slate-100 mb-2">Pending Orders ({pendingOrders.length})</h3>
        {pendingOrders.length === 0 ? (
          <div className="text-xs text-slate-500 py-3">No active pending orders.</div>
        ) : (
          <div className="space-y-1.5">
            {pendingOrders.map((o: any) => (
              <div key={o.ticket} className="flex items-center justify-between bg-slate-950/70 border border-slate-800 rounded-lg px-3 py-2 text-xs font-mono">
                <div>
                  #{o.ticket} · {o.symbol} · Vol {o.volume} @ {o.price} (SL {o.sl} / TP {o.tp})
                </div>
                <button
                  onClick={() => handleCancelOrder(o.ticket)}
                  className="px-2.5 py-1 bg-rose-700 hover:bg-rose-600 text-white rounded font-sans inline-flex items-center space-x-1"
                >
                  <Trash2 className="w-3 h-3" />
                  <span>Cancel</span>
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {editing && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl p-5 w-full max-w-sm space-y-3">
            <h3 className="text-sm font-bold text-slate-100">Modify SL/TP — Ticket #{editing.ticket} ({editing.symbol})</h3>
            <div className="space-y-2 text-xs">
              <label className="block">
                <span className="text-slate-400">Stop Loss</span>
                <input
                  type="number"
                  step="any"
                  value={slInput}
                  onChange={(e) => setSlInput(e.target.value)}
                  className="w-full mt-1 bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 text-slate-100 font-mono"
                />
              </label>
              <label className="block">
                <span className="text-slate-400">Take Profit</span>
                <input
                  type="number"
                  step="any"
                  value={tpInput}
                  onChange={(e) => setTpInput(e.target.value)}
                  className="w-full mt-1 bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 text-slate-100 font-mono"
                />
              </label>
            </div>
            <div className="flex justify-end space-x-2 pt-2">
              <button onClick={() => setEditing(null)} className="px-3 py-1.5 bg-slate-800 text-slate-300 text-xs rounded-lg">
                Cancel
              </button>
              <button disabled={busy} onClick={submitModify} className="px-3 py-1.5 bg-sky-600 text-white text-xs font-semibold rounded-lg">
                Apply SL/TP
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export const TradeHistoryScreen: React.FC<{ trades: TradeHistoryRecord[]; onReload: () => Promise<void> }> = ({
  trades,
  onReload,
}) => {
  const [symbolFilter, setSymbolFilter] = useState("ALL");
  const filtered = trades.filter((t) => symbolFilter === "ALL" || t.symbol.includes(symbolFilter));

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-bold text-slate-100">Persisted Trade History ({filtered.length})</h2>
        <div className="flex items-center space-x-2">
          <select
            value={symbolFilter}
            onChange={(e) => setSymbolFilter(e.target.value)}
            className="bg-slate-950 border border-slate-800 text-xs text-slate-200 rounded-lg px-2.5 py-1.5"
          >
            <option value="ALL">All Symbols</option>
            <option value="XAU">Gold (XAU)</option>
            <option value="BTC">Bitcoin (BTC)</option>
          </select>
          <button onClick={() => onReload()} className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-xs text-slate-200 rounded-lg">
            Refresh
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="text-slate-400 border-b border-slate-800">
            <tr>
              <th className="py-2 pr-3">Ticket</th>
              <th className="py-2 pr-3">Symbol</th>
              <th className="py-2 pr-3">Dir</th>
              <th className="py-2 pr-3">Vol</th>
              <th className="py-2 pr-3">Open</th>
              <th className="py-2 pr-3">Close</th>
              <th className="py-2 pr-3">Profit</th>
              <th className="py-2">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/70 font-mono">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-8 text-center text-slate-500 font-sans">
                  No historical trades recorded in SQLite yet.
                </td>
              </tr>
            ) : (
              filtered.map((t) => (
                <tr key={t.id}>
                  <td className="py-2 pr-3">#{t.ticket}</td>
                  <td className="py-2 pr-3 font-bold text-slate-100">{t.symbol}</td>
                  <td className="py-2 pr-3">{t.direction}</td>
                  <td className="py-2 pr-3">{t.volume.toFixed(2)}</td>
                  <td className="py-2 pr-3">{t.open_price.toFixed(2)}</td>
                  <td className="py-2 pr-3">{t.close_price ? t.close_price.toFixed(2) : "-"}</td>
                  <td className={`py-2 pr-3 font-bold ${t.profit >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                    {t.profit >= 0 ? "+" : ""}${t.profit.toFixed(2)}
                  </td>
                  <td className="py-2 font-sans text-slate-300">{t.status}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export const RiskManagerScreen: React.FC<{
  riskState: Record<string, any>;
  decisions: RiskDecisionRecord[];
  portfolioCapacity?: Record<string, any>;
  onReload: () => Promise<void>;
}> = ({ riskState, decisions, portfolioCapacity, onReload }) => {
  const cap = portfolioCapacity || {};
  const byInst = (cap.open_positions_by_instrument || {}) as Record<string, number>;
  return (
    <div className="space-y-4">
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-bold text-slate-100 flex items-center space-x-2">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <span>Authoritative PortfolioRiskEngine</span>
          </h2>
          <button onClick={() => onReload()} className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-xs text-slate-200 rounded-lg">
            Refresh
          </button>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
          <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-3">
            <div className="text-slate-400">Kill Switch</div>
            <div className={`font-mono font-bold mt-1 ${riskState.kill_switch_active ? "text-rose-400" : "text-emerald-400"}`}>
              {riskState.kill_switch_active ? "ACTIVE" : "ARMED / CLEAR"}
            </div>
          </div>
          <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-3">
            <div className="text-slate-400">Daily P&amp;L</div>
            <div className="font-mono font-bold text-slate-100 mt-1">${Number(riskState.daily_pnl ?? 0).toFixed(2)}</div>
          </div>
          <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-3">
            <div className="text-slate-400">Consecutive Losses</div>
            <div className="font-mono font-bold text-slate-100 mt-1">{riskState.consecutive_losses ?? 0}</div>
          </div>
          <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-3">
            <div className="text-slate-400">Trading Paused</div>
            <div className="font-mono font-bold text-slate-100 mt-1">{String(riskState.trading_paused ?? false).toUpperCase()}</div>
          </div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs mt-3">
          <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-3">
            <div className="text-slate-400">Dynamic Risk Capacity</div>
            <div className="font-mono font-bold text-sky-400 mt-1">
              {Number(cap.available_risk_capacity_pct ?? 0).toFixed(2)}% (${Number(cap.available_risk_capacity_usd ?? 0).toFixed(2)})
            </div>
          </div>
          <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-3">
            <div className="text-slate-400">Portfolio Risk Utilization</div>
            <div className="font-mono font-bold text-slate-100 mt-1">
              {Number(cap.current_portfolio_risk_pct ?? 0).toFixed(2)}% / {Number(cap.aggregate_risk_budget_pct ?? 6).toFixed(1)}%
            </div>
          </div>
          <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-3">
            <div className="text-slate-400">Margin Utilization</div>
            <div className="font-mono font-bold text-slate-100 mt-1">
              {Number(cap.margin_utilization_pct ?? 0).toFixed(2)}% (Free ${Number(cap.free_margin ?? 0).toFixed(2)})
            </div>
          </div>
          <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-3">
            <div className="text-slate-400">Open Positions (By Symbol)</div>
            <div className="font-mono font-bold text-slate-100 mt-1">
              {cap.total_open_positions ?? 0} ({Object.entries(byInst).map(([k, v]) => `${k}:${v}`).join(", ") || "None"})
            </div>
          </div>
        </div>
      </div>

      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Recent Risk Gate Decisions</h3>
        {decisions.length === 0 ? (
          <div className="text-xs text-slate-500 py-4">No risk evaluations logged yet.</div>
        ) : (
          <div className="space-y-1.5 text-xs">
            {decisions.slice(0, 20).map((d) => (
              <div key={d.id} className="flex items-center justify-between bg-slate-950/70 border border-slate-800 rounded px-3 py-2">
                <div className="flex items-center space-x-2">
                  {d.approved ? <Shield className="w-3.5 h-3.5 text-emerald-400" /> : <AlertCircle className="w-3.5 h-3.5 text-rose-400" />}
                  <span className="font-mono font-bold text-slate-100">{d.symbol} {d.direction}</span>
                  <span className="text-slate-400">{d.reason}</span>
                </div>
                <span className="font-mono text-slate-400">{d.lot_size.toFixed(2)} lot</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export const InstrumentsScreen: React.FC<{
  instrumentsConfig: Record<string, any>;
  status: ControlStatusPayload | null;
}> = ({ instrumentsConfig, status }) => {
  const entries = Object.entries(instrumentsConfig || {});
  const liveSpecs = status?.mt5.symbols || {};

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 space-y-3">
      <div className="flex items-center space-x-2">
        <Layers className="w-4 h-4 text-sky-400" />
        <h2 className="text-sm font-bold text-slate-100">Gold &amp; BTC Instrument Profiles</h2>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {entries.length === 0 ? (
          <div className="text-xs text-slate-500">No instrument profiles loaded from config/instruments.json.</div>
        ) : (
          entries.map(([sym, cfg]) => {
            const live = liveSpecs[sym];
            return (
              <div key={sym} className="bg-slate-950/70 border border-slate-800 rounded-xl p-3.5 text-xs space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="font-mono font-bold text-sm text-slate-100">{sym}</span>
                  <span className="px-2 py-0.5 bg-sky-500/20 text-sky-300 rounded text-[10px]">
                    {live ? `LIVE BID ${live.bid}` : "CONFIGURED"}
                  </span>
                </div>
                <pre className="text-[11px] text-slate-300 font-mono bg-slate-900/80 p-2 rounded overflow-x-auto max-h-48">
                  {JSON.stringify(cfg, null, 2)}
                </pre>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
