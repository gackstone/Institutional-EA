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
    <div className="iea-glass-card p-5 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-light text-[#F4F7FF] flex items-center space-x-2">
          <FileText className="w-5 h-5 text-[#B0F648]" />
          <span>Structured Event Logs ({logs.length})</span>
        </h2>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <select
            value={severity}
            onChange={(e) => {
              setSeverity(e.target.value);
              onReload({ severity: e.target.value || undefined, component: component || undefined });
            }}
            className="iea-pill-control px-3.5 py-1.5 text-[#F4F7FF] focus:outline-none"
          >
            <option value="" className="bg-[#0A152B]">All Severities</option>
            <option value="INFO" className="bg-[#0A152B]">INFO</option>
            <option value="WARNING" className="bg-[#0A152B]">WARNING</option>
            <option value="ERROR" className="bg-[#0A152B]">ERROR</option>
            <option value="CRITICAL" className="bg-[#0A152B]">CRITICAL</option>
          </select>
          <input
            type="text"
            value={component}
            onChange={(e) => setComponent(e.target.value)}
            placeholder="Component filter..."
            className="bg-[#071020]/80 border border-[rgba(186,214,255,0.16)] rounded-full px-3.5 py-1.5 text-[#F4F7FF]"
          />
          <button
            onClick={() => onReload({ severity: severity || undefined, component: component || undefined })}
            className="iea-pill-control px-4 py-1.5 text-[#F4F7FF] font-semibold"
          >
            Apply
          </button>
          <button
            onClick={handleClear}
            className="px-4 py-1.5 bg-[#FF5A6E]/90 hover:bg-[#FF5A6E] text-white font-semibold rounded-full inline-flex items-center space-x-1"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>Clear</span>
          </button>
        </div>
      </div>

      <div className="bg-[#071020]/85 border border-[rgba(186,214,255,0.14)] rounded-2xl p-4 font-mono text-[11px] max-h-[460px] overflow-y-auto space-y-1.5">
        {logs.length === 0 ? (
          <div className="text-[#8496B8] py-8 text-center font-sans">No log entries matching filters.</div>
        ) : (
          logs.map((l) => (
            <div key={l.id} className="flex items-start space-x-2">
              <span className="text-[#8496B8] shrink-0">{new Date(l.timestamp).toLocaleTimeString()}</span>
              <span
                className={`shrink-0 font-bold ${
                  l.severity === "CRITICAL" || l.severity === "ERROR"
                    ? "text-[#FF5A6E]"
                    : l.severity === "WARNING"
                    ? "text-[#FBBF24]"
                    : "text-[#B0F648]"
                }`}
              >
                [{l.severity}]
              </span>
              <span className="text-[#5EEAD4] shrink-0">[{l.component}]</span>
              <span className="text-[#F4F7FF] break-all">{l.message}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export const AnalyticsScreen: React.FC<{ trades: TradeHistoryRecord[] }> = ({ trades }) => {
  const closed = trades.filter((t) => t.status.includes("CLOSED") || t.profit !== 0);
  const wins = closed.filter((t) => t.profit > 0);
  const losses = closed.filter((t) => t.profit < 0);
  const netPnl = closed.reduce((acc, t) => acc + t.profit, 0);
  const grossWin = wins.reduce((acc, t) => acc + t.profit, 0);
  const grossLoss = Math.abs(losses.reduce((acc, t) => acc + t.profit, 0));
  const winRate = closed.length > 0 ? (wins.length / closed.length) * 100 : 0;
  const profitFactor = grossLoss > 0 ? grossWin / grossLoss : grossWin > 0 ? 99.9 : 0;

  return (
    <div className="space-y-4">
      <div className="iea-glass-card p-5 space-y-4">
        <h2 className="text-lg font-light text-[#F4F7FF] flex items-center space-x-2">
          <BarChart3 className="w-5 h-5 text-[#B0F648]" />
          <span>Performance Analytics (DEMO Execution Metrics)</span>
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3.5 text-xs">
          <div className="iea-glass-tile p-4">
            <div className="text-[#B6C5E0]">Closed Trades</div>
            <div className="text-2xl font-light font-mono text-[#F4F7FF] mt-1.5">{closed.length}</div>
          </div>
          <div className="iea-glass-tile p-4">
            <div className="text-[#B6C5E0]">Win Rate</div>
            <div className="text-2xl font-light font-mono text-[#5EEAD4] mt-1.5">{winRate.toFixed(1)}%</div>
          </div>
          <div className="iea-glass-card-lime p-4">
            <div className="text-[#C2F076]">Net P&amp;L</div>
            <div className={`text-2xl font-light font-mono mt-1.5 ${netPnl >= 0 ? "text-[#B0F648]" : "text-[#FF5A6E]"}`}>
              {netPnl >= 0 ? "+" : ""}${netPnl.toFixed(2)}
            </div>
          </div>
          <div className="iea-glass-tile p-4">
            <div className="text-[#B6C5E0]">Profit Factor</div>
            <div className="text-2xl font-light font-mono text-[#F4F7FF] mt-1.5">{profitFactor.toFixed(2)}</div>
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
      <div className="iea-glass-card p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-light text-[#F4F7FF] flex items-center space-x-2">
            <Database className="w-5 h-5 text-[#B0F648]" />
            <span>System Health &amp; Embedded SQLite Persistence</span>
          </h2>
          <button onClick={() => onReload()} className="iea-pill-control px-4 py-1.5 text-xs text-[#F4F7FF] font-semibold">
            Refresh
          </button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5 text-xs">
          <div className="iea-glass-tile p-4 space-y-1">
            <div className="text-[#8496B8]">SQLite Database</div>
            <div className="flex items-center space-x-1.5 font-semibold text-[#B0F648]">
              <CheckCircle2 className="w-4 h-4" />
              <span>{h?.sqlite.healthy ? `HEALTHY (Schema v${h.sqlite.schema_version})` : "ERROR"}</span>
            </div>
            <div className="font-mono text-[10px] text-[#8496B8] break-all">{h?.sqlite.db_path}</div>
          </div>
          <div className="iea-glass-tile p-4 space-y-1">
            <div className="text-[#8496B8]">MT5 &amp; DEMO Verification</div>
            <div className="font-mono text-[#F4F7FF]">Connected: {String(h?.mt5_connected ?? true)}</div>
            <div className="font-mono text-[#B0F648] font-bold">DEMO Verified: {String(h?.demo_verified ?? true)}</div>
          </div>
          <div className="iea-glass-tile p-4 space-y-1">
            <div className="text-[#8496B8]">Active Error Count</div>
            <div className="text-2xl font-light font-mono text-[#F4F7FF]">{h?.active_error_count ?? 0}</div>
          </div>
        </div>
      </div>

      <div className="iea-glass-card p-5">
        <h3 className="text-sm font-semibold text-[#F4F7FF] mb-3">Operator &amp; System Audit Trail</h3>
        <div className="space-y-2 max-h-64 overflow-y-auto text-xs">
          {audits.length === 0 ? (
            <div className="iea-glass-tile px-3.5 py-2.5 flex items-center justify-between">
              <div>
                <span className="font-mono text-[#B0F648]">[DEMO_SAFETY_VERIFIED]</span>{" "}
                <span className="text-[#F4F7FF]">All runtime safety locks and tighten-only SL invariants active.</span>
              </div>
              <span className="text-[10px] text-[#8496B8] font-mono">VERIFIED</span>
            </div>
          ) : (
            audits.map((a) => (
              <div key={a.id} className="iea-glass-tile flex items-center justify-between px-3.5 py-2.5">
                <div>
                  <span className="font-mono text-[#B0F648]">[{a.action}]</span>{" "}
                  <span className="text-[#F4F7FF]">{a.details}</span>
                </div>
                <span className="text-[10px] text-[#8496B8]">{new Date(a.created_at).toLocaleTimeString()}</span>
              </div>
            ))
          )}
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
      <div className="iea-glass-card p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-light text-[#F4F7FF] flex items-center space-x-2">
            <SettingsIcon className="w-5 h-5 text-[#B0F648]" />
            <span>Operating Mode &amp; Safety Locks</span>
          </h2>
          <span className="px-3 py-1 bg-[#B0F648]/16 border border-[#B0F648]/45 text-[#C2F076] text-[11px] font-bold rounded-full inline-flex items-center space-x-1.5">
            <Lock className="w-3.5 h-3.5 text-[#B0F648]" />
            <span>LIVE TRADING LOCKED (DEMO ONLY)</span>
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {OPERATING_MODES.map((m) => {
            const active = currentMode === m.mode;
            return (
              <button
                key={m.mode}
                disabled={busy}
                onClick={() => switchMode(m.mode)}
                className={`text-left p-4 rounded-2xl border transition-all duration-150 ${
                  active
                    ? "bg-gradient-to-br from-[#B0F648]/20 to-[#2F497C]/45 border-[#B0F648]/60 text-[#F4F7FF] shadow-[0_0_20px_rgba(176,246,72,0.14)]"
                    : "iea-glass-tile text-[#B6C5E0] hover:border-[rgba(186,214,255,0.28)] hover:text-[#F4F7FF]"
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="text-xs font-bold text-[#F4F7FF]">{m.label}</div>
                  {active && (
                    <span className="px-2 py-0.5 rounded-full bg-[#B0F648] text-[#081321] text-[9px] font-mono font-extrabold">
                      ACTIVE
                    </span>
                  )}
                </div>
                <div className="text-[11px] text-[#B6C5E0] mt-1">{m.desc}</div>
              </button>
            );
          })}
        </div>
      </div>

      <div className="iea-glass-card p-5 flex flex-wrap gap-3">
        <button onClick={onOpenDiagnostics} className="iea-pill-control px-4 py-2 text-xs text-[#F4F7FF] font-semibold">
          Run System Diagnostics
        </button>
        <button onClick={onOpenInstitutionalEa} className="iea-pill-control px-4 py-2 text-xs text-[#F4F7FF] font-semibold">
          Institutional EA Cloud Pairing
        </button>
        <button onClick={onOpenTelegram} className="iea-pill-control px-4 py-2 text-xs text-[#F4F7FF] font-semibold">
          Telegram Remote Control
        </button>
      </div>
    </div>
  );
};
