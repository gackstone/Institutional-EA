import React, { useEffect, useMemo, useState } from "react";
import { Bell, CheckCircle2, RefreshCw, Send, Zap } from "lucide-react";
import { controlClient } from "../../services/ipc";
import { AlertEventRecord, AlertSettings, SignalRecord } from "../../types";
import { ChartSymbol } from "../../services/dashboardDataAdapter";
import { getSymbolChipSpec } from "../../styles/designTokens";

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
    <div className="iea-glass-card p-5 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-light text-[#F4F7FF] flex items-center space-x-2">
            <Zap className="w-5 h-5 text-[#B0F648]" />
            <span>Live Signal Grid ({combinedRows.length})</span>
          </h2>
          <p className="text-[11px] font-mono text-[#8496B8] mt-0.5">
            Source: BOT · {fetchedAt ? `Updated ${new Date(fetchedAt).toLocaleTimeString()}` : "Waiting for bot"}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs">
          <select
            value={symbolFilter}
            onChange={(e) => setSymbolFilter(e.target.value)}
            aria-label="Filter signals by symbol"
            className="iea-pill-control px-3 py-1.5 text-[#F4F7FF] focus:outline-none"
          >
            <option value="ALL" className="bg-[#0A152B]">All Symbols</option>
            <option value="XAU" className="bg-[#0A152B]">XAUUSD</option>
            <option value="JPY" className="bg-[#0A152B]">USDJPY</option>
            <option value="BTC" className="bg-[#0A152B]">BTCUSD</option>
          </select>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            aria-label="Filter signals by status"
            className="iea-pill-control px-3 py-1.5 text-[#F4F7FF] focus:outline-none"
          >
            <option value="ALL" className="bg-[#0A152B]">All Status</option>
            <option value="WATCHING" className="bg-[#0A152B]">Watching</option>
            <option value="TAKEN" className="bg-[#0A152B]">Taken</option>
            <option value="REJECTED" className="bg-[#0A152B]">Rejected</option>
          </select>

          <button
            type="button"
            disabled={loading}
            onClick={reload}
            className="iea-pill-control px-3.5 py-1.5 text-[#F4F7FF] font-semibold inline-flex items-center space-x-1.5"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      <div className="overflow-x-auto rounded-2xl border border-[rgba(186,214,255,0.12)]">
        <table className="w-full text-left text-xs iea-glass-table">
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
                <td colSpan={8} className="py-10 text-center text-[#8496B8] font-sans">
                  No signals yet. Real bot setups will appear here as MT5 candles close.
                </td>
              </tr>
            ) : (
              combinedRows.map((s) => {
                const chip = getSymbolChipSpec(s.symbol);
                const statusClass =
                  s.status === "TAKEN"
                    ? "bg-[#B0F648]/20 text-[#B0F648] border border-[#B0F648]/40"
                    : s.status === "WATCHING"
                    ? "bg-[#5EEAD4]/20 text-[#5EEAD4] border border-[#5EEAD4]/40"
                    : "bg-[#FF5A6E]/20 text-[#FF7A8A] border border-[#FF5A6E]/40";
                return (
                  <tr
                    key={`${s.id}-${s.signal_id}`}
                    onClick={() => onJumpToChart(toChartSymbol(s.symbol))}
                    className="cursor-pointer"
                    title="Click to jump to this symbol on the Dashboard chart"
                  >
                    <td className="py-2.5 pl-4 pr-3 text-[#8496B8]">
                      {s.created_at ? new Date(s.created_at).toISOString().slice(11, 19) : "—"}
                    </td>
                    <td className="py-2.5 pr-3">
                      <div className="flex items-center space-x-2">
                        <span className={`w-6 h-6 rounded-full text-[10px] font-extrabold inline-flex items-center justify-center ${chip.chipBg}`}>
                          {chip.shortCode}
                        </span>
                        <span className="font-bold text-[#F4F7FF]">{s.symbol}</span>
                      </div>
                    </td>
                    <td className={`py-2.5 pr-3 font-bold ${s.direction === "BUY" ? "text-[#B0F648]" : "text-[#FF5A6E]"}`}>
                      {s.direction || "—"}
                    </td>
                    <td className="py-2.5 pr-3 text-[#F4F7FF]">{s.score > 0 ? s.score.toFixed(0) : "—"}</td>
                    <td className="py-2.5 pr-3 text-[#B6C5E0]">
                      {s.entry_price > 0 ? `${s.entry_price} / ${s.stop_loss || "—"} / ${s.take_profit || "—"}` : "—"}
                    </td>
                    <td className="py-2.5 pr-3 text-[#5EEAD4]">{s.rr > 0 ? `${s.rr.toFixed(2)}R` : "—"}</td>
                    <td className="py-2.5 pr-3 font-sans">
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${statusClass}`}>
                        {s.status}
                      </span>
                    </td>
                    <td className="py-2.5 pr-4 font-sans text-[#B6C5E0]">{s.rejection_reason || "—"}</td>
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
      <div className="lg:col-span-7 iea-glass-card p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-lg font-light text-[#F4F7FF] flex items-center space-x-2">
              <Bell className="w-5 h-5 text-[#B0F648]" />
              <span>Alert Centre ({alerts.length})</span>
            </h2>
            <p className="text-[11px] font-mono text-[#8496B8] mt-0.5">
              Source: BOT Event Log &amp; Telegram Delivery Status
            </p>
          </div>

          <div className="flex items-center space-x-2">
            <button
              type="button"
              onClick={loadAll}
              className="iea-pill-control px-3 py-1.5 text-xs text-[#F4F7FF]"
            >
              Refresh
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={handleSendTest}
              className="px-3.5 py-1.5 rounded-full bg-[#B0F648] hover:bg-[#C2F076] text-[#081321] text-xs font-extrabold inline-flex items-center space-x-1.5"
            >
              <Send className="w-3.5 h-3.5" />
              <span>Send Test Message</span>
            </button>
          </div>
        </div>

        <div className="space-y-2 max-h-[500px] overflow-y-auto">
          {alerts.length === 0 ? (
            <div className="iea-glass-tile py-10 text-center text-xs text-[#8496B8]">
              No alerts recorded yet. Real bot and MT5 freshness alerts will appear here.
            </div>
          ) : (
            alerts.map((al) => (
              <div key={al.id} className="iea-glass-tile p-3.5 text-xs space-y-1">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-2 font-mono">
                    <span className="px-2 py-0.5 rounded-full bg-[#B0F648]/18 text-[#B0F648] text-[10px] font-bold">
                      {al.alert_type.toUpperCase()}
                    </span>
                    {al.symbol && <span className="text-[#5EEAD4] font-bold">{al.symbol}</span>}
                  </div>
                  <div className="flex items-center space-x-2 font-mono text-[10px]">
                    <span
                      className={`px-2 py-0.5 rounded-full font-bold ${
                        al.telegram_status === "DELIVERED"
                          ? "bg-[#B0F648]/18 text-[#B0F648]"
                          : al.telegram_status === "FAILED"
                          ? "bg-[#FF5A6E]/20 text-[#FF7A8A]"
                          : "bg-white/10 text-[#8496B8]"
                      }`}
                    >
                      TG: {al.telegram_status}
                    </span>
                    <span className="text-[#8496B8]">{new Date(al.created_at).toLocaleTimeString()}</span>
                  </div>
                </div>
                <div className="text-[#F4F7FF]">{al.message}</div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Right: Per-Type Toggles, Quiet Hours & Rate-Limit Settings (5 cols) */}
      <div className="lg:col-span-5 iea-glass-card p-5 space-y-4">
        <h3 className="text-sm font-semibold text-[#F4F7FF] flex items-center space-x-2">
          <CheckCircle2 className="w-4 h-4 text-[#B0F648]" />
          <span>Notification Rules &amp; Telegram Delivery</span>
        </h3>

        {!settings ? (
          <div className="text-xs text-[#8496B8]">Waiting for Control Service alert settings...</div>
        ) : (
          <div className="space-y-4 text-xs">
            <div className="space-y-1.5">
              <div className="text-[11px] font-semibold text-[#B6C5E0]">Event Toggles</div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                {ALERT_TYPE_LABELS.map((t) => (
                  <label
                    key={t.key}
                    className="iea-glass-tile px-3 py-2 flex items-center justify-between cursor-pointer"
                  >
                    <span className="text-[#F4F7FF]">{t.label}</span>
                    <input
                      type="checkbox"
                      checked={Boolean(settings.enabled_types[t.key])}
                      onChange={() => toggleAlertType(t.key)}
                      className="accent-[#B0F648]"
                    />
                  </label>
                ))}
              </div>
            </div>

            <div className="iea-glass-tile p-3 space-y-2.5">
              <label className="flex items-center justify-between cursor-pointer">
                <span className="font-semibold text-[#F4F7FF]">Quiet Hours (UTC)</span>
                <input
                  type="checkbox"
                  checked={settings.quiet_hours_enabled}
                  onChange={(e) => updateSettings({ quiet_hours_enabled: e.target.checked })}
                  className="accent-[#B0F648]"
                />
              </label>
              <div className="grid grid-cols-2 gap-2 font-mono">
                <input
                  type="time"
                  value={settings.quiet_start_utc}
                  onChange={(e) => updateSettings({ quiet_start_utc: e.target.value })}
                  className="bg-[#091426]/80 border border-[rgba(186,214,255,0.2)] rounded-xl px-2.5 py-1.5 text-[#F4F7FF]"
                />
                <input
                  type="time"
                  value={settings.quiet_end_utc}
                  onChange={(e) => updateSettings({ quiet_end_utc: e.target.value })}
                  className="bg-[#091426]/80 border border-[rgba(186,214,255,0.2)] rounded-xl px-2.5 py-1.5 text-[#F4F7FF]"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2.5">
              <label className="iea-glass-tile p-3 block">
                <span className="text-[11px] text-[#B6C5E0]">Rate Limit / Min</span>
                <input
                  type="number"
                  min={1}
                  max={60}
                  value={settings.rate_limit_per_min}
                  onChange={(e) => updateSettings({ rate_limit_per_min: Number(e.target.value) })}
                  className="w-full mt-1 bg-[#091426]/80 border border-[rgba(186,214,255,0.2)] rounded-xl px-2.5 py-1 text-[#F4F7FF] font-mono"
                />
              </label>
              <label className="iea-glass-tile p-3 block">
                <span className="text-[11px] text-[#B6C5E0]">Dedup Window (s)</span>
                <input
                  type="number"
                  min={10}
                  max={3600}
                  value={settings.dedup_window_sec}
                  onChange={(e) => updateSettings({ dedup_window_sec: Number(e.target.value) })}
                  className="w-full mt-1 bg-[#091426]/80 border border-[rgba(186,214,255,0.2)] rounded-xl px-2.5 py-1 text-[#F4F7FF] font-mono"
                />
              </label>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
