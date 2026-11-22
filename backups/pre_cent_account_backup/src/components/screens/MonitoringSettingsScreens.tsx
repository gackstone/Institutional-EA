import React, { useState } from "react";
import { BarChart3, CheckCircle2, Database, FileText, Lock, Settings as SettingsIcon, Trash2 } from "lucide-react";
import { controlClient } from "../../services/ipc";
import {
  AuditLogRecord,
  ControlLogEntry,
  ControlStatusPayload,
  OperatingMode,
  TradeHistoryRecord,
} from "../../types";

const OPERATING_MODES: Array<{ mode: OperatingMode; label: string; desc: string }> = [
  { mode: "OBSERVE", label: "Observe Only", desc: "Stream MT5 telemetry & signals without order placement." },
  { mode: "DRY_RUN", label: "Dry Run", desc: "Run full strategy + risk evaluation without broker submission." },
  { mode: "DEMO_SCALPING", label: "Demo Scalping", desc: "Balanced Gold & BTC DEMO scalping execution." },
  { mode: "DEMO_FAST", label: "Demo Fast Execution", desc: "High-responsiveness DEMO scalping profile." },
  { mode: "DEMO_MANUAL_ASSIST", label: "Demo Manual Assist", desc: "Monitor & protect manual/assistant DEMO positions." },
  { mode: "BTCUSD_DEMO_SAMPLE_MODE", label: "BTCUSD Sample Trading", desc: "Single-position DEMO sample trading for BTCUSD with Telegram alerts." },
];

export const LogsScreen: React.FC<{
  logs: ControlLogEntry[];
  onReload: (filters?: { severity?: string; component?: string }) => Promise<void>;
  onActionMessage: (msg: string, isError?: boolean) => void;
}> = ({ logs, onReload, onActionMessage }) => {
  const [severity, setSeverity] = useState("");
  const [component, setComponent] = useState("");

  const handleClear = async () => {
    await controlClient.clearLogs();
    onActionMessage("In-memory control log buffer cleared.");
    await onReload({ severity: severity || undefined, component: component || undefined });
  };

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-bold text-slate-100 flex items-center space-x-2">
          <FileText className="w-4 h-4 text-sky-400" />
          <span>Structured Event Logs ({logs.length})</span>
        </h2>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <select
            value={severity}
            onChange={(e) => {
              setSeverity(e.target.value);
              onReload({ severity: e.target.value || undefined, component: component || undefined });
            }}
            className="bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-slate-200"
          >
            <option value="">All Severities</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="ERROR">ERROR</option>
            <option value="CRITICAL">CRITICAL</option>
          </select>
          <input
            type="text"
            value={component}
            onChange={(e) => setComponent(e.target.value)}
            placeholder="Component filter..."
            className="bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-slate-200"
          />
          <button
            onClick={() => onReload({ severity: severity || undefined, component: component || undefined })}
            className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg"
          >
            Apply
          </button>
          <button onClick={handleClear} className="px-3 py-1.5 bg-rose-700/80 hover:bg-rose-600 text-white rounded-lg inline-flex items-center space-x-1">
            <Trash2 className="w-3.5 h-3.5" />
            <span>Clear</span>
          </button>
        </div>
      </div>

      <div className="bg-slate-950 border border-slate-800 rounded-lg p-3 font-mono text-[11px] max-h-[460px] overflow-y-auto space-y-1">
        {logs.length === 0 ? (
          <div className="text-slate-500 py-8 text-center font-sans">No log entries matching filters.</div>
        ) : (
          logs.map((l) => (
            <div key={l.id} className="flex items-start space-x-2">
              <span className="text-slate-500 shrink-0">{new Date(l.timestamp).toLocaleTimeString()}</span>
              <span
                className={`shrink-0 font-bold ${
                  l.severity === "CRITICAL" || l.severity === "ERROR"
                    ? "text-rose-400"
                    : l.severity === "WARNING"
                    ? "text-amber-400"
                    : "text-emerald-400"
                }`}
              >
                [{l.severity}]
              </span>
              <span className="text-sky-400 shrink-0">[{l.component}]</span>
              <span className="text-slate-200 break-all">{l.message}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export const AnalyticsScreen: React.FC<{ trades: TradeHistoryRecord[] }> = ({ trades }) => {
  const closed = trades.filter((t) => t.status === "CLOSED");
  const wins = closed.filter((t) => t.profit > 0);
  const losses = closed.filter((t) => t.profit < 0);
  const netPnl = closed.reduce((acc, t) => acc + t.profit, 0);
  const grossWin = wins.reduce((acc, t) => acc + t.profit, 0);
  const grossLoss = Math.abs(losses.reduce((acc, t) => acc + t.profit, 0));
  const winRate = closed.length > 0 ? (wins.length / closed.length) * 100 : 0;
  const profitFactor = grossLoss > 0 ? grossWin / grossLoss : grossWin > 0 ? 99.9 : 0;

  return (
    <div className="space-y-4">
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4">
        <h2 className="text-sm font-bold text-slate-100 flex items-center space-x-2 mb-3">
          <BarChart3 className="w-4 h-4 text-sky-400" />
          <span>Performance Analytics (DEMO Execution Metrics)</span>
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
          <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-3">
            <div className="text-slate-400">Closed Trades</div>
            <div className="text-xl font-mono font-bold text-slate-100 mt-1">{closed.length}</div>
          </div>
          <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-3">
            <div className="text-slate-400">Win Rate</div>
            <div className="text-xl font-mono font-bold text-sky-400 mt-1">{winRate.toFixed(1)}%</div>
          </div>
          <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-3">
            <div className="text-slate-400">Net P&amp;L</div>
            <div className={`text-xl font-mono font-bold mt-1 ${netPnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
              ${netPnl.toFixed(2)}
            </div>
          </div>
          <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-3">
            <div className="text-slate-400">Profit Factor</div>
            <div className="text-xl font-mono font-bold text-slate-100 mt-1">{profitFactor.toFixed(2)}</div>
          </div>
        </div>
      </div>
    </div>
  );
};

export const SystemHealthScreen: React.FC<{
  status: ControlStatusPayload | null;
  audits: AuditLogRecord[];
  onReload: () => Promise<void>;
}> = ({ status, audits, onReload }) => {
  const h = status?.health;
  return (
    <div className="space-y-4">
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-bold text-slate-100 flex items-center space-x-2">
            <Database className="w-4 h-4 text-emerald-400" />
            <span>System Health &amp; Embedded SQLite Persistence</span>
          </h2>
          <button onClick={() => onReload()} className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-xs text-slate-200 rounded-lg">
            Refresh
          </button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
          <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-3 space-y-1">
            <div className="text-slate-400">SQLite Database</div>
            <div className="flex items-center space-x-1.5 font-semibold text-emerald-400">
              <CheckCircle2 className="w-4 h-4" />
              <span>{h?.sqlite.healthy ? `HEALTHY (Schema v${h.sqlite.schema_version})` : "ERROR"}</span>
            </div>
            <div className="font-mono text-[10px] text-slate-500 break-all">{h?.sqlite.db_path}</div>
          </div>
          <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-3 space-y-1">
            <div className="text-slate-400">MT5 &amp; DEMO Verification</div>
            <div className="font-mono text-slate-100">Connected: {String(h?.mt5_connected ?? false)}</div>
            <div className="font-mono text-emerald-400">DEMO Verified: {String(h?.demo_verified ?? false)}</div>
          </div>
          <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-3 space-y-1">
            <div className="text-slate-400">Active Error Count</div>
            <div className="text-lg font-mono font-bold text-slate-100">{h?.active_error_count ?? 0}</div>
          </div>
        </div>
      </div>

      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">Operator &amp; System Audit Trail</h3>
        <div className="space-y-1.5 max-h-64 overflow-y-auto text-xs">
          {audits.map((a) => (
            <div key={a.id} className="flex items-center justify-between bg-slate-950/70 border border-slate-800 rounded px-3 py-1.5">
              <div>
                <span className="font-mono text-sky-400">[{a.action}]</span>{" "}
                <span className="text-slate-200">{a.details}</span>
              </div>
              <span className="text-[10px] text-slate-500">{new Date(a.created_at).toLocaleTimeString()}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export const SettingsScreen: React.FC<{
  status: ControlStatusPayload | null;
  onRefresh: () => Promise<void>;
  onActionMessage: (msg: string, isError?: boolean) => void;
  onOpenDiagnostics: () => void;
  onOpenInstitutionalEa: () => void;
  onOpenTelegram: () => void;
}> = ({ status, onRefresh, onActionMessage, onOpenDiagnostics, onOpenInstitutionalEa, onOpenTelegram }) => {
  const [busy, setBusy] = useState(false);
  const currentMode = status?.engine.operating_mode || "DEMO_SCALPING";

  const switchMode = async (mode: OperatingMode) => {
    setBusy(true);
    try {
      await controlClient.applyConfig({ operating_mode: mode }, `Switched operating mode to ${mode}`);
      onActionMessage(`Operating mode updated to ${mode}.`);
      await onRefresh();
    } catch (e: any) {
      onActionMessage(`Failed to switch mode: ${e.message}`, true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold text-slate-100 flex items-center space-x-2">
            <SettingsIcon className="w-4 h-4 text-sky-400" />
            <span>Operating Mode &amp; Safety Locks</span>
          </h2>
          <span className="px-2.5 py-1 bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 text-[11px] font-bold rounded-full inline-flex items-center space-x-1">
            <Lock className="w-3 h-3" />
            <span>LIVE TRADING LOCKED (DEMO ONLY)</span>
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2.5">
          {OPERATING_MODES.map((m) => (
            <button
              key={m.mode}
              disabled={busy}
              onClick={() => switchMode(m.mode)}
              className={`text-left p-3 rounded-xl border transition ${
                currentMode === m.mode
                  ? "bg-sky-950/60 border-sky-500 text-slate-100"
                  : "bg-slate-950/70 border-slate-800 text-slate-300 hover:border-slate-700"
              }`}
            >
              <div className="text-xs font-bold">{m.label}</div>
              <div className="text-[11px] text-slate-400 mt-0.5">{m.desc}</div>
            </button>
          ))}
        </div>
      </div>

      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 flex flex-wrap gap-2.5">
        <button onClick={onOpenDiagnostics} className="px-3.5 py-2 bg-slate-800 hover:bg-slate-700 text-xs text-slate-100 rounded-lg">
          Run System Diagnostics
        </button>
        <button onClick={onOpenInstitutionalEa} className="px-3.5 py-2 bg-slate-800 hover:bg-slate-700 text-xs text-slate-100 rounded-lg">
          Institutional EA Cloud Pairing
        </button>
        <button onClick={onOpenTelegram} className="px-3.5 py-2 bg-slate-800 hover:bg-slate-700 text-xs text-slate-100 rounded-lg">
          Telegram Remote Control
        </button>
      </div>
    </div>
  );
};
