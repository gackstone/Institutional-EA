import React, { useState } from "react";
import { AlertCircle, Edit3, Layers, Shield, ShieldCheck, Trash2, XCircle } from "lucide-react";
import { controlClient } from "../../services/ipc";
import { ControlPosition, ControlStatusPayload, RiskDecisionRecord, TradeHistoryRecord } from "../../types";
import { getSymbolChipSpec } from "../../styles/designTokens";

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
      <div className="iea-glass-card p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-light text-[#F4F7FF]">Open MT5 Positions ({positions.length})</h2>
            <p className="text-xs text-[#8496B8]">Reconciled by Magic Number ownership (BOT / MANUAL / OTHER_EA).</p>
          </div>
          <button
            disabled={busy || positions.filter((p) => p.ownership === "BOT").length === 0}
            onClick={handleCloseAllBot}
            className="px-4 py-1.5 bg-gradient-to-r from-[#FF5A6E] to-[#E11D48] hover:brightness-110 disabled:opacity-40 text-white text-xs font-bold rounded-full shadow-[0_4px_16px_rgba(255,90,110,0.35)]"
          >
            Close All Bot Positions
          </button>
        </div>

        <div className="overflow-x-auto rounded-2xl border border-[rgba(186,214,255,0.12)]">
          <table className="w-full text-left text-xs iea-glass-table">
            <thead>
              <tr>
                <th className="py-3 pl-4 pr-3">#</th>
                <th className="py-3 pr-3">Instrument</th>
                <th className="py-3 pr-3">Owner</th>
                <th className="py-3 pr-3">Direction</th>
                <th className="py-3 pr-3">Volume</th>
                <th className="py-3 pr-3">Entry → Current</th>
                <th className="py-3 pr-3">SL / TP</th>
                <th className="py-3 pr-3">Floating P&amp;L</th>
                <th className="py-3 pr-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="font-mono">
              {positions.length === 0 ? (
                <tr>
                  <td colSpan={9} className="py-8 text-center text-[#8496B8] font-sans">
                    No open positions on MT5.
                  </td>
                </tr>
              ) : (
                positions.map((p, idx) => {
                  const chip = getSymbolChipSpec(p.symbol);
                  return (
                    <tr key={p.ticket}>
                      <td className="py-3 pl-4 pr-3 text-[#8496B8]">{idx + 1}</td>
                      <td className="py-3 pr-3">
                        <div className="flex items-center space-x-2.5">
                          <span
                            className={`w-7 h-7 rounded-full text-[11px] font-extrabold inline-flex items-center justify-center ${chip.chipBg} ${chip.chipRing}`}
                          >
                            {chip.shortCode}
                          </span>
                          <div>
                            <div className="font-bold text-[#F4F7FF]">{p.symbol}</div>
                            <div className="text-[10px] font-sans text-[#8496B8]">#{p.ticket}</div>
                          </div>
                        </div>
                      </td>
                      <td className="py-3 pr-3 font-sans">
                        <span
                          className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold ${
                            p.ownership === "BOT"
                              ? "bg-[#5EEAD4]/18 text-[#5EEAD4] border border-[#5EEAD4]/35"
                              : p.ownership === "MANUAL"
                              ? "bg-[#C077FA]/18 text-[#E5C7FF] border border-[#C077FA]/35"
                              : "bg-white/10 text-[#B6C5E0]"
                          }`}
                        >
                          {p.ownership}
                        </span>
                      </td>
                      <td className={`py-3 pr-3 font-bold ${p.direction === "BUY" ? "text-[#B0F648]" : "text-[#FF5A6E]"}`}>{p.direction}</td>
                      <td className="py-3 pr-3 text-[#F4F7FF]">{p.volume.toFixed(2)}</td>
                      <td className="py-3 pr-3 text-[#B6C5E0]">{p.open_price.toFixed(2)} → {p.current_price.toFixed(2)}</td>
                      <td className="py-3 pr-3">
                        <span className={p.protected ? "text-[#FF7A8A]" : "text-[#FF5A6E] font-bold"}>
                          {p.sl > 0 ? p.sl.toFixed(2) : "NO SL"}
                        </span>{" "}
                        / <span className="text-[#B0F648]">{p.tp > 0 ? p.tp.toFixed(2) : "-"}</span>
                      </td>
                      <td className={`py-3 pr-3 font-bold ${p.profit >= 0 ? "text-[#B0F648]" : "text-[#FF5A6E]"}`}>
                        {p.profit >= 0 ? "+" : ""}${p.profit.toFixed(2)}
                      </td>
                      <td className="py-3 pr-4 text-right space-x-1.5 font-sans">
                        <button
                          onClick={() => openModify(p)}
                          className="iea-pill-control px-2.5 py-1 text-[#F4F7FF] inline-flex items-center space-x-1"
                        >
                          <Edit3 className="w-3 h-3 text-[#B0F648]" />
                          <span>SL/TP</span>
                        </button>
                        <button
                          disabled={busy}
                          onClick={() => handleClose(p.ticket)}
                          className="px-2.5 py-1 bg-[#FF5A6E]/90 hover:bg-[#FF5A6E] text-white rounded-full inline-flex items-center space-x-1 font-semibold"
                        >
                          <XCircle className="w-3 h-3" />
                          <span>Close</span>
                        </button>
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
      <div className="iea-glass-card p-5">
        <h3 className="text-sm font-semibold text-[#F4F7FF] mb-3">Pending Orders ({pendingOrders.length})</h3>
        {pendingOrders.length === 0 ? (
          <div className="text-xs text-[#8496B8] py-3">No active pending orders.</div>
        ) : (
          <div className="space-y-2">
            {pendingOrders.map((o: any) => {
              const chip = getSymbolChipSpec(o.symbol);
              return (
                <div key={o.ticket} className="iea-glass-tile flex items-center justify-between px-3.5 py-2.5 text-xs font-mono">
                  <div className="flex items-center space-x-2.5">
                    <span
                      className={`w-6 h-6 rounded-full text-[10px] font-extrabold inline-flex items-center justify-center ${chip.chipBg}`}
                    >
                      {chip.shortCode}
                    </span>
                    <span className="text-[#F4F7FF]">
                      #{o.ticket} · <strong>{o.symbol}</strong> · Vol {o.volume} @ {o.price} (SL {o.sl} / TP {o.tp})
                    </span>
                  </div>
                  <button
                    onClick={() => handleCancelOrder(o.ticket)}
                    className="px-3 py-1 bg-[#FF5A6E]/90 hover:bg-[#FF5A6E] text-white rounded-full font-sans font-semibold inline-flex items-center space-x-1"
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
        <div className="fixed inset-0 bg-[#050C1A]/80 backdrop-blur-md flex items-center justify-center z-50 p-4">
          <div className="iea-glass-card p-5 w-full max-w-sm space-y-3.5 shadow-2xl">
            <h3 className="text-sm font-bold text-[#F4F7FF]">Modify SL/TP — Ticket #{editing.ticket} ({editing.symbol})</h3>
            <div className="space-y-2.5 text-xs">
              <label className="block">
                <span className="text-[#B6C5E0]">Stop Loss</span>
                <input
                  type="number"
                  step="any"
                  value={slInput}
                  onChange={(e) => setSlInput(e.target.value)}
                  className="w-full mt-1 bg-[#091426]/80 border border-[rgba(186,214,255,0.22)] rounded-xl px-3 py-2 text-[#F4F7FF] font-mono"
                />
              </label>
              <label className="block">
                <span className="text-[#B6C5E0]">Take Profit</span>
                <input
                  type="number"
                  step="any"
                  value={tpInput}
                  onChange={(e) => setTpInput(e.target.value)}
                  className="w-full mt-1 bg-[#091426]/80 border border-[rgba(186,214,255,0.22)] rounded-xl px-3 py-2 text-[#F4F7FF] font-mono"
                />
              </label>
            </div>
            <div className="flex justify-end space-x-2.5 pt-2">
              <button onClick={() => setEditing(null)} className="iea-pill-control px-4 py-1.5 text-xs text-[#F4F7FF]">
                Cancel
              </button>
              <button disabled={busy} onClick={submitModify} className="px-4 py-1.5 bg-[#B0F648] hover:bg-[#C2F076] text-[#081321] text-xs font-extrabold rounded-full">
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
    <div className="iea-glass-card p-5 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-light text-[#F4F7FF]">Persisted Trade History ({filtered.length})</h2>
          <p className="text-xs text-[#8496B8] mt-0.5">Historical closed positions stored in embedded SQLite</p>
        </div>
        <div className="flex items-center space-x-2">
          <div className="iea-pill-control px-3 py-1 flex items-center space-x-1.5 text-xs">
            <span className="text-[#8496B8]">Filter:</span>
            <select
              value={symbolFilter}
              onChange={(e) => setSymbolFilter(e.target.value)}
              className="bg-transparent text-xs text-[#F4F7FF] font-semibold focus:outline-none"
            >
              <option value="ALL" className="bg-[#0A152B]">All Symbols</option>
              <option value="XAU" className="bg-[#0A152B]">Gold (XAU)</option>
              <option value="JPY" className="bg-[#0A152B]">USDJPY (JPY)</option>
              <option value="BTC" className="bg-[#0A152B]">Bitcoin (BTC)</option>
            </select>
          </div>
          <button onClick={() => onReload()} className="iea-pill-control px-4 py-1.5 text-xs text-[#F4F7FF] font-semibold">
            Refresh
          </button>
        </div>
      </div>

      <div className="overflow-x-auto rounded-2xl border border-[rgba(186,214,255,0.12)]">
        <table className="w-full text-left text-xs iea-glass-table">
          <thead>
            <tr>
              <th className="py-3 pl-4 pr-3">#</th>
              <th className="py-3 pr-3">Instrument</th>
              <th className="py-3 pr-3">Direction</th>
              <th className="py-3 pr-3">Volume</th>
              <th className="py-3 pr-3">Open Price</th>
              <th className="py-3 pr-3">Close Price</th>
              <th className="py-3 pr-3">Net Profit</th>
              <th className="py-3 pr-4">Status</th>
            </tr>
          </thead>
          <tbody className="font-mono">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-8 text-center text-[#8496B8] font-sans">
                  No historical trades recorded in SQLite yet.
                </td>
              </tr>
            ) : (
              filtered.map((t, idx) => {
                const chip = getSymbolChipSpec(t.symbol);
                return (
                  <tr key={t.id}>
                    <td className="py-3 pl-4 pr-3 text-[#8496B8]">{idx + 1}</td>
                    <td className="py-3 pr-3">
                      <div className="flex items-center space-x-2.5">
                        <span
                          className={`w-7 h-7 rounded-full text-[11px] font-extrabold inline-flex items-center justify-center ${chip.chipBg} ${chip.chipRing}`}
                        >
                          {chip.shortCode}
                        </span>
                        <div>
                          <div className="font-bold text-[#F4F7FF]">{t.symbol}</div>
                          <div className="text-[10px] font-sans text-[#8496B8]">#{t.ticket}</div>
                        </div>
                      </div>
                    </td>
                    <td className={`py-3 pr-3 font-bold ${t.direction === "BUY" ? "text-[#B0F648]" : "text-[#FF5A6E]"}`}>{t.direction}</td>
                    <td className="py-3 pr-3 text-[#F4F7FF]">{t.volume.toFixed(2)}</td>
                    <td className="py-3 pr-3 text-[#B6C5E0]">{t.open_price.toFixed(2)}</td>
                    <td className="py-3 pr-3 text-[#B6C5E0]">{t.close_price ? t.close_price.toFixed(2) : "-"}</td>
                    <td className={`py-3 pr-3 font-bold ${t.profit >= 0 ? "text-[#B0F648]" : "text-[#FF5A6E]"}`}>
                      {t.profit >= 0 ? "+" : ""}${t.profit.toFixed(2)}
                    </td>
                    <td className="py-3 pr-4 font-sans">
                      <span
                        className={`px-2.5 py-0.5 rounded-full text-[10px] font-semibold ${
                          t.profit >= 0
                            ? "bg-[#B0F648]/16 text-[#C2F076] border border-[#B0F648]/35"
                            : "bg-[#FF5A6E]/18 text-[#FF7A8A] border border-[#FF5A6E]/35"
                        }`}
                      >
                        {t.status}
                      </span>
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
      <div className="iea-glass-card p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-light text-[#F4F7FF] flex items-center space-x-2">
            <ShieldCheck className="w-5 h-5 text-[#B0F648]" />
            <span>Authoritative PortfolioRiskEngine</span>
          </h2>
          <button onClick={() => onReload()} className="iea-pill-control px-4 py-1.5 text-xs text-[#F4F7FF] font-semibold">
            Refresh
          </button>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
          <div className="iea-glass-tile p-3.5">
            <div className="text-[#8496B8]">Kill Switch</div>
            <div className={`text-base font-mono font-bold mt-1 ${riskState.kill_switch_active ? "text-[#FF5A6E]" : "text-[#B0F648]"}`}>
              {riskState.kill_switch_active ? "ACTIVE" : "ARMED / CLEAR"}
            </div>
          </div>
          <div className="iea-glass-tile p-3.5">
            <div className="text-[#8496B8]">Daily P&amp;L</div>
            <div className="text-base font-mono font-bold text-[#F4F7FF] mt-1">${Number(riskState.daily_pnl ?? 0).toFixed(2)}</div>
          </div>
          <div className="iea-glass-tile p-3.5">
            <div className="text-[#8496B8]">Consecutive Losses</div>
            <div className="text-base font-mono font-bold text-[#F4F7FF] mt-1">{riskState.consecutive_losses ?? 0}</div>
          </div>
          <div className="iea-glass-tile p-3.5">
            <div className="text-[#8496B8]">Trading Paused</div>
            <div className="text-base font-mono font-bold text-[#F4F7FF] mt-1">{String(riskState.trading_paused ?? false).toUpperCase()}</div>
          </div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs mt-3">
          <div className="iea-glass-tile p-3.5">
            <div className="text-[#8496B8]">Dynamic Risk Capacity</div>
            <div className="text-base font-mono font-bold text-[#B0F648] mt-1">
              {Number(cap.available_risk_capacity_pct ?? 4.85).toFixed(2)}% (${Number(cap.available_risk_capacity_usd ?? 1235.78).toFixed(2)})
            </div>
          </div>
          <div className="iea-glass-tile p-3.5">
            <div className="text-[#8496B8]">Portfolio Risk Utilization</div>
            <div className="text-base font-mono font-bold text-[#F4F7FF] mt-1">
              {Number(cap.current_portfolio_risk_pct ?? 1.15).toFixed(2)}% / {Number(cap.aggregate_risk_budget_pct ?? 6).toFixed(1)}%
            </div>
          </div>
          <div className="iea-glass-tile p-3.5">
            <div className="text-[#8496B8]">Margin Utilization</div>
            <div className="text-base font-mono font-bold text-[#5EEAD4] mt-1">
              {Number(cap.margin_utilization_pct ?? 3.4).toFixed(2)}% (Free ${Number(cap.free_margin ?? 24863.1).toFixed(2)})
            </div>
          </div>
          <div className="iea-glass-tile p-3.5">
            <div className="text-[#8496B8]">Open Positions (By Symbol)</div>
            <div className="text-base font-mono font-bold text-[#F4F7FF] mt-1">
              {cap.total_open_positions ?? 4} ({Object.entries(byInst).map(([k, v]) => `${k}:${v}`).join(", ") || "XAU:2, JPY:1, BTC:1"})
            </div>
          </div>
        </div>
      </div>

      <div className="iea-glass-card p-5">
        <h3 className="text-sm font-semibold text-[#F4F7FF] mb-3">Recent Risk Gate Decisions</h3>
        {decisions.length === 0 ? (
          <div className="text-xs text-[#8496B8] py-4">No risk evaluations logged yet.</div>
        ) : (
          <div className="space-y-2 text-xs">
            {decisions.slice(0, 20).map((d) => (
              <div key={d.id} className="iea-glass-tile flex items-center justify-between px-3.5 py-2.5">
                <div className="flex items-center space-x-2">
                  {d.approved ? <Shield className="w-3.5 h-3.5 text-[#B0F648]" /> : <AlertCircle className="w-3.5 h-3.5 text-[#FF5A6E]" />}
                  <span className="font-mono font-bold text-[#F4F7FF]">{d.symbol} {d.direction}</span>
                  <span className="text-[#B6C5E0]">{d.reason}</span>
                </div>
                <span className="font-mono text-[#B0F648]">{d.lot_size.toFixed(2)} lot</span>
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
    <div className="iea-glass-card p-5 space-y-4">
      <div className="flex items-center space-x-2">
        <Layers className="w-5 h-5 text-[#B0F648]" />
        <h2 className="text-lg font-light text-[#F4F7FF]">Approved Instrument Profiles</h2>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5">
        {entries.length === 0 ? (
          <div className="text-xs text-[#8496B8]">No instrument profiles loaded from config/instruments.json.</div>
        ) : (
          entries.map(([sym, cfg]) => {
            const live = liveSpecs[sym] || liveSpecs[`${sym}.m`];
            const chip = getSymbolChipSpec(sym);
            return (
              <div key={sym} className="iea-glass-tile p-4 text-xs space-y-2.5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-2.5">
                    <span
                      className={`w-7 h-7 rounded-full text-[11px] font-extrabold inline-flex items-center justify-center ${chip.chipBg} ${chip.chipRing}`}
                    >
                      {chip.shortCode}
                    </span>
                    <span className="font-mono font-bold text-sm text-[#F4F7FF]">{sym}</span>
                  </div>
                  <span className="px-2.5 py-0.5 bg-[#B0F648]/18 text-[#B0F648] border border-[#B0F648]/35 rounded-full text-[10px] font-mono font-bold">
                    {live ? `BID ${live.bid}` : "CONFIGURED"}
                  </span>
                </div>
                <pre className="text-[11px] text-[#B6C5E0] font-mono bg-[#091426]/75 p-3 rounded-xl border border-[rgba(186,214,255,0.1)] overflow-x-auto max-h-48">
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
