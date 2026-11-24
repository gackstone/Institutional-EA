import React, { useEffect, useMemo, useState } from "react";
import { Bell, CheckCircle2, RefreshCw, Send, Zap } from "lucide-react";
import { controlClient } from "../../services/ipc";
import { AlertEventRecord, AlertSettings, SignalRecord } from "../../types";
import { ChartSymbol } from "../../services/dashboardDataAdapter";
import { getNeutralSymbolChipSpec } from "../../styles/designTokens";

export const SignalsGridScreen: React.FC<{
  onJumpToChart: (symbol: ChartSymbol) => void;
}> = ({ onJumpToChart }) => {
  const [signals, setSignals] = useState<SignalRecord[]>([]);
  const [decisions, setDecisions] = useState<Array<Record<string, any>>>([]);
  const [fetchedAt, setFetchedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [symbolFilter, setSymbolFilter] = useState<string>("ALL");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");

  const reload = async () => {
    setLoading(true);
    try {
      const res = await controlClient.getSignals();
      setSignals(res.signals || []);
      setDecisions(res.decisions || []);
      setFetchedAt(res.fetched_at || new Date().toISOString());
    } catch {
      setSignals([]);
      setDecisions([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    reload();
  }, []);

  // Merge real bot signals + real risk gate decisions (zero mock rows)
  const combinedRows = useMemo(() => {
    const rows: SignalRecord[] = [...signals];
    for (const d of decisions) {
      const sigId = String(d.signal_id || `dec-${d.id}`);
      if (rows.some((r) => r.signal_id === sigId)) continue;
      rows.push({
        id: Number(d.id) + 100000,
        signal_id: sigId,
        symbol: String(d.symbol || ""),
        direction: String(d.direction || ""),
        score: Number(d.score || 0),
        entry_price: Number(d.entry_price || 0),
        stop_loss: Number(d.stop_loss || 0),
        take_profit: Number(d.take_profit || 0),
        rr: Number(d.rr || 0),
        status: d.approved ? "TAKEN" : "REJECTED",
        rejection_reason: String(d.reason || ""),
        created_at: String(d.created_at || ""),
      });
    }
    return rows.filter((r) => {
      const symOk = symbolFilter === "ALL" || r.symbol.toUpperCase().includes(symbolFilter);
      const stOk = statusFilter === "ALL" || r.status.toUpperCase() === statusFilter;
      return symOk && stOk;
    });
  }, [signals, decisions, symbolFilter, statusFilter]);

  const toChartSymbol = (sym: string): ChartSymbol => {
    const u = sym.toUpperCase();
    if (u.includes("JPY")) return "USDJPY";
    if (u.includes("BTC")) return "BTCUSD";
    return "XAUUSD";
  };

  return (
    <div className="iea-card p-5 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-bold text-iea-textPrimary flex items-center space-x-2">
            <Zap className="w-5 h-5 text-iea-accent" />
            <span>Live Signal Grid ({combinedRows.length})</span>
          </h2>
          <p className="text-[11px] font-mono text-iea-textMuted mt-0.5">
            Source: BOT · {fetchedAt ? `Updated ${new Date(fetchedAt).toLocaleTimeString()}` : "Waiting for bot"}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs">
          <select
            value={symbolFilter}
            onChange={(e) => setSymbolFilter(e.target.value)}
            aria-label="Filter signals by symbol"
            className="iea-pill-control px-3 py-1.5 text-iea-textPrimary focus:outline-none"
          >
            <option value="ALL" className="bg-iea-card">All Symbols</option>
            <option value="XAU" className="bg-iea-card">XAUUSD</option>
            <option value="JPY" className="bg-iea-card">USDJPY</option>
            <option value="BTC" className="bg-iea-card">BTCUSD</option>
          </select>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            aria-label="Filter signals by status"
            className="iea-pill-control px-3 py-1.5 text-iea-textPrimary focus:outline-none"
          >
            <option value="ALL" className="bg-iea-card">All Status</option>
            <option value="WATCHING" className="bg-iea-card">Watching</option>
            <option value="TAKEN" className="bg-iea-card">Taken</option>
            <option value="REJECTED" className="bg-iea-card">Rejected</option>
          </select>

          <button
            type="button"
            disabled={loading}
            onClick={reload}
            className="iea-pill-control px-3.5 py-1.5 text-iea-textPrimary font-semibold inline-flex items-center space-x-1.5"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      <div className="overflow-x-auto rounded-2xl border border-iea-borderSubtle">
        <table className="w-full text-left text-xs iea-table">
          <thead>
            <tr>
              <th className="py-3 pl-4 pr-3">Time (UTC)</th>
              <th className="py-3 pr-3">Symbol</th>
              <th className="py-3 pr-3">Side</th>
              <th className="py-3 pr-3">Score</th>
              <th className="py-3 pr-3">Entry / SL / TP</th>
              <th className="py-3 pr-3">R:R</th>
              <th className="py-3 pr-3">Status</th>
              <th className="py-3 pr-4">Reason</th>
            </tr>
          </thead>
          <tbody className="font-mono tabular-nums">
            {combinedRows.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-10 text-center text-iea-textMuted font-sans">
                  No signals yet. Real bot setups will appear here as MT5 candles close.
                </td>
              </tr>
            ) : (
              combinedRows.map((s) => {
                const chip = getNeutralSymbolChipSpec(s.symbol);
                const statusClass =
                  s.status === "TAKEN"
                    ? "bg-iea-profitSoft text-iea-profit border border-iea-profitBorder"
                    : s.status === "WATCHING"
                    ? "bg-iea-accentSoft text-iea-accent border border-iea-accentBorder"
                    : "bg-iea-dangerSoft text-iea-danger border border-iea-dangerBorder";
                return (
                  <tr
                    key={`${s.id}-${s.signal_id}`}
                    onClick={() => onJumpToChart(toChartSymbol(s.symbol))}
                    className="cursor-pointer"
                    title="Click to jump to this symbol on the Dashboard chart"
                  >
                    <td className="py-2.5 pl-4 pr-3 text-iea-textMuted">
                      {s.created_at ? new Date(s.created_at).toISOString().slice(11, 19) : "—"}
                    </td>
                    <td className="py-2.5 pr-3">
                      <div className="flex items-center space-x-2">
                        <span className={`w-6 h-6 rounded-full text-[10px] font-extrabold inline-flex items-center justify-center ${chip.chipBg}`}>
                          {chip.shortCode}
                        </span>
                        <span className="font-bold text-iea-textPrimary">{s.symbol}</span>
                      </div>
                    </td>
                    <td className={`py-2.5 pr-3 font-bold ${s.direction === "BUY" ? "text-iea-profit" : "text-iea-danger"}`}>
                      {s.direction || "—"}
                    </td>
                    <td className="py-2.5 pr-3 text-iea-textPrimary">{s.score > 0 ? s.score.toFixed(0) : "—"}</td>
                    <td className="py-2.5 pr-3 text-iea-textSecondary">
                      {s.entry_price > 0 ? `${s.entry_price} / ${s.stop_loss || "—"} / ${s.take_profit || "—"}` : "—"}
                    </td>
                    <td className="py-2.5 pr-3 text-iea-accent">{s.rr > 0 ? `${s.rr.toFixed(2)}R` : "—"}</td>
                    <td className="py-2.5 pr-3 font-sans">
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${statusClass}`}>
                        {s.status}
                      </span>
                    </td>
                    <td className="py-2.5 pr-4 font-sans text-iea-textSecondary">{s.rejection_reason || "—"}</td>
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

const ALERT_TYPE_LABELS: Array<{ key: string; label: string }> = [
  { key: "signal", label: "Signal Detected" },
  { key: "trade_open", label: "Trade Opened" },
  { key: "trade_close", label: "Trade Closed" },
  { key: "be_moved", label: "Break-Even Moved" },
  { key: "sl_tp_hit", label: "SL / TP Hit" },
  { key: "daily_loss_warn", label: "Daily Loss Warning" },
  { key: "bridge_down", label: "Bridge Down" },
  { key: "heartbeat_lost", label: "Heartbeat Lost" },
  { key: "stale_data", label: "Stale / Closed Market Data" },
];

export const AlertCentreScreen: React.FC<{
  onActionMessage: (msg: string, isError?: boolean) => void;
}> = ({ onActionMessage }) => {
  const [alerts, setAlerts] = useState<AlertEventRecord[]>([]);
  const [settings, setSettings] = useState<AlertSettings | null>(null);
  const [busy, setBusy] = useState(false);

  const loadAll = async () => {
    try {
      const res = await controlClient.getAlerts();
      setAlerts(res.alerts || []);
      setSettings(res.settings || null);
    } catch {
      setAlerts([]);
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  const updateSettings = async (patch: Partial<AlertSettings>) => {
    if (!settings) return;
    const merged = { ...settings, ...patch };
    setSettings(merged);
    try {
      const res = await controlClient.saveAlertSettings(merged);
      setSettings(res.settings);
      onActionMessage("Alert settings saved.");
    } catch (e: any) {
      onActionMessage(`Save alert settings failed: ${e.message}`, true);
    }
  };

  const toggleAlertType = (key: string) => {
    if (!settings) return;
    updateSettings({
      enabled_types: {
        ...settings.enabled_types,
        [key]: !settings.enabled_types[key],
      },
    });
  };

  const handleSendTest = async () => {
    setBusy(true);
    try {
      const res = await controlClient.sendTestAlert();
      onActionMessage(`Test alert logged (Telegram: ${res.telegram_status}).`);
      await loadAll();
    } catch (e: any) {
      onActionMessage(`Test alert failed: ${e.message}`, true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
      {/* Left: In-App Real Alert Log (7 cols) */}
      <div className="lg:col-span-7 iea-card p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-lg font-bold text-iea-textPrimary flex items-center space-x-2">
              <Bell className="w-5 h-5 text-iea-accent" />
              <span>Alert Centre ({alerts.length})</span>
            </h2>
            <p className="text-[11px] font-mono text-iea-textMuted mt-0.5">
              Source: BOT Event Log &amp; Telegram Delivery Status
            </p>
          </div>

          <div className="flex items-center space-x-2">
            <button
              type="button"
              onClick={loadAll}
              className="iea-pill-control px-3 py-1.5 text-xs text-iea-textPrimary"
            >
              Refresh
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={handleSendTest}
              className="px-3.5 py-1.5 rounded-full bg-iea-accent hover:bg-iea-accentHover text-white text-xs font-extrabold inline-flex items-center space-x-1.5 transition"
            >
              <Send className="w-3.5 h-3.5" />
              <span>Send Test Message</span>
            </button>
          </div>
        </div>

        <div className="space-y-2 max-h-[500px] overflow-y-auto">
          {alerts.length === 0 ? (
            <div className="iea-inset py-10 text-center text-xs text-iea-textMuted">
              No alerts recorded yet. Real bot and MT5 freshness alerts will appear here.
            </div>
          ) : (
            alerts.map((al) => (
              <div key={al.id} className="iea-inset p-3.5 text-xs space-y-1">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-2 font-mono">
                    <span className="px-2 py-0.5 rounded-full bg-iea-accentSoft text-iea-accent text-[10px] font-bold">
                      {al.alert_type.toUpperCase()}
                    </span>
                    {al.symbol && <span className="text-iea-accent font-bold">{al.symbol}</span>}
                  </div>
                  <div className="flex items-center space-x-2 font-mono text-[10px]">
                    <span
                      className={`px-2 py-0.5 rounded-full font-bold ${
                        al.telegram_status === "DELIVERED"
                          ? "bg-iea-profitSoft text-iea-profit"
                          : al.telegram_status === "FAILED"
                          ? "bg-iea-dangerSoft text-iea-danger"
                          : "bg-iea-elevated text-iea-textMuted"
                      }`}
                    >
                      TG: {al.telegram_status}
                    </span>
                    <span className="text-iea-textMuted">{new Date(al.created_at).toLocaleTimeString()}</span>
                  </div>
                </div>
                <div className="text-iea-textPrimary">{al.message}</div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Right: Per-Type Toggles, Quiet Hours & Rate-Limit Settings (5 cols) */}
      <div className="lg:col-span-5 iea-card p-5 space-y-4">
        <h3 className="text-sm font-bold text-iea-textPrimary flex items-center space-x-2">
          <CheckCircle2 className="w-4 h-4 text-iea-profit" />
          <span>Notification Rules &amp; Telegram Delivery</span>
        </h3>

        {!settings ? (
          <div className="text-xs text-iea-textMuted">Waiting for Control Service alert settings...</div>
        ) : (
          <div className="space-y-4 text-xs">
            <div className="space-y-1.5">
              <div className="text-[11px] font-semibold text-iea-textSecondary">Event Toggles</div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                {ALERT_TYPE_LABELS.map((t) => (
                  <label
                    key={t.key}
                    className="iea-inset px-3 py-2 flex items-center justify-between cursor-pointer"
                  >
                    <span className="text-iea-textPrimary">{t.label}</span>
                    <input
                      type="checkbox"
                      checked={Boolean(settings.enabled_types[t.key])}
                      onChange={() => toggleAlertType(t.key)}
                      className="accent-[var(--iea-accent-primary)]"
                    />
                  </label>
                ))}
              </div>
            </div>

            <div className="iea-inset p-3 space-y-2.5">
              <label className="flex items-center justify-between cursor-pointer">
                <span className="font-semibold text-iea-textPrimary">Quiet Hours (UTC)</span>
                <input
                  type="checkbox"
                  checked={settings.quiet_hours_enabled}
                  onChange={(e) => updateSettings({ quiet_hours_enabled: e.target.checked })}
                  className="accent-[var(--iea-accent-primary)]"
                />
              </label>
              <div className="grid grid-cols-2 gap-2 font-mono">
                <input
                  type="time"
                  value={settings.quiet_start_utc}
                  onChange={(e) => updateSettings({ quiet_start_utc: e.target.value })}
                  className="iea-input px-2.5 py-1.5"
                />
                <input
                  type="time"
                  value={settings.quiet_end_utc}
                  onChange={(e) => updateSettings({ quiet_end_utc: e.target.value })}
                  className="iea-input px-2.5 py-1.5"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2.5">
              <label className="iea-inset p-3 block">
                <span className="text-[11px] text-iea-textSecondary">Rate Limit / Min</span>
                <input
                  type="number"
                  min={1}
                  max={60}
                  value={settings.rate_limit_per_min}
                  onChange={(e) => updateSettings({ rate_limit_per_min: Number(e.target.value) })}
                  className="w-full mt-1 iea-input px-2.5 py-1 font-mono"
                />
              </label>
              <label className="iea-inset p-3 block">
                <span className="text-[11px] text-iea-textSecondary">Dedup Window (s)</span>
                <input
                  type="number"
                  min={10}
                  max={3600}
                  value={settings.dedup_window_sec}
                  onChange={(e) => updateSettings({ dedup_window_sec: Number(e.target.value) })}
                  className="w-full mt-1 iea-input px-2.5 py-1 font-mono"
                />
              </label>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
