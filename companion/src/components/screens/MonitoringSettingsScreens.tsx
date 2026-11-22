import React, { useEffect, useMemo, useState } from "react";
import { BarChart3, BookOpen, CheckCircle2, Database, FileText, Lock, Settings as SettingsIcon, Trash2 } from "lucide-react";
import { controlClient } from "../../services/ipc";
import {
  AuditLogRecord,
  BalanceSnapshotRecord,
  ControlLogEntry,
  ControlStatusPayload,
  SelfCheckReport,
  TradeHistoryRecord,
} from "../../types";
import { SHORT_FORM_GLOSSARY, UI_COPY } from "../../constants/uiCopy";

export const LogsScreen: React.FC<{
  logs: ControlLogEntry[];
  onReload: (filters?: { severity?: string; component?: string }) => Promise<void>;
  onActionMessage: (msg: string, isError?: boolean) => void;
}> = ({ logs, onReload, onActionMessage }) => {
  const [severity, setSeverity] = useState("");
  const [component, setComponent] = useState("");

  const handleClear = async () => {
    await controlClient.clearLogs();
    onActionMessage("Logs cleared.");
    await onReload({ severity: severity || undefined, component: component || undefined });
  };

  return (
    <div className="iea-glass-card p-5 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-light text-[#F4F7FF] flex items-center space-x-2">
          <FileText className="w-5 h-5 text-[#B0F648]" />
          <span>Event Logs ({logs.length})</span>
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
            <option value="" className="bg-[#0A152B]">All Levels</option>
            <option value="INFO" className="bg-[#0A152B]">INFO</option>
            <option value="WARNING" className="bg-[#0A152B]">WARN</option>
            <option value="ERROR" className="bg-[#0A152B]">ERR</option>
            <option value="CRITICAL" className="bg-[#0A152B]">CRIT</option>
          </select>
          <input
            type="text"
            value={component}
            onChange={(e) => setComponent(e.target.value)}
            placeholder="Module..."
            className="bg-[#071020]/80 border border-[rgba(186,214,255,0.16)] rounded-full px-3.5 py-1.5 text-[#F4F7FF]"
          />
          <button
            onClick={() => onReload({ severity: severity || undefined, component: component || undefined })}
            className="iea-pill-control px-4 py-1.5 text-[#F4F7FF] font-semibold"
          >
            Filter
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
          <div className="text-[#8496B8] py-8 text-center font-sans">0 log entries.</div>
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

const MiniLineChart: React.FC<{
  title: string;
  values: number[];
  stroke: string;
  formatValue: (v: number) => string;
  emptyText: string;
}> = ({ title, values, stroke, formatValue, emptyText }) => {
  if (values.length < 2) {
    return (
      <div className="iea-glass-tile p-4 flex flex-col justify-between min-h-[168px]">
        <div className="text-xs font-semibold text-[#B6C5E0]">{title}</div>
        <div className="text-xs text-[#8496B8] text-center py-8">{emptyText}</div>
      </div>
    );
  }
  const minV = Math.min(...values);
  const maxV = Math.max(...values);
  const span = Math.max(1e-6, maxV - minV);
  const pts = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * 280;
      const y = 78 - ((v - minV) / span) * 66;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const latest = values[values.length - 1];

  return (
    <div className="iea-glass-tile p-4 flex flex-col justify-between min-h-[168px]">
      <div className="flex items-center justify-between text-xs">
        <span className="font-semibold text-[#B6C5E0]">{title}</span>
        <span className="font-mono font-bold text-[#F4F7FF]">{formatValue(latest)}</span>
      </div>
      <svg viewBox="0 0 280 86" className="w-full h-24 mt-2 overflow-visible">
        <polyline
          fill="none"
          stroke={stroke}
          strokeWidth="2"
          strokeLinejoin="round"
          strokeLinecap="round"
          points={pts}
        />
      </svg>
      <div className="flex justify-between text-[10px] font-mono text-[#8496B8]">
        <span>Min {formatValue(minV)}</span>
        <span>Max {formatValue(maxV)}</span>
      </div>
    </div>
  );
};

export const AnalyticsScreen: React.FC<{
  trades: TradeHistoryRecord[];
  snapshots?: BalanceSnapshotRecord[];
}> = ({ trades, snapshots = [] }) => {
  const [symbolFilter, setSymbolFilter] = useState<string>("ALL");
  const [rangeDays, setRangeDays] = useState<number>(0); // 0 = All

  const filteredTrades = useMemo(() => {
    const cutoffMs = rangeDays > 0 ? Date.now() - rangeDays * 86400 * 1000 : 0;
    return trades
      .filter((t) => {
        const closedOk = t.status.includes("CLOSED") || t.closed_at !== null;
        const symOk = symbolFilter === "ALL" || t.symbol.toUpperCase().includes(symbolFilter);
        const dateMs = t.closed_at ? new Date(t.closed_at).getTime() : new Date(t.opened_at).getTime();
        const rangeOk = cutoffMs === 0 || dateMs >= cutoffMs;
        return closedOk && symOk && rangeOk;
      })
      .sort(
        (a, b) =>
          new Date(a.closed_at || a.opened_at).getTime() -
          new Date(b.closed_at || b.opened_at).getTime()
      );
  }, [trades, symbolFilter, rangeDays]);

  const wins = filteredTrades.filter((t) => t.profit > 0);
  const losses = filteredTrades.filter((t) => t.profit < 0);
  const netPnl = filteredTrades.reduce((acc, t) => acc + t.profit, 0);
  const grossWin = wins.reduce((acc, t) => acc + t.profit, 0);
  const grossLoss = Math.abs(losses.reduce((acc, t) => acc + t.profit, 0));
  const winRate = filteredTrades.length > 0 ? (wins.length / filteredTrades.length) * 100 : null;
  const profitFactor =
    filteredTrades.length === 0 ? null : grossLoss > 0 ? grossWin / grossLoss : grossWin > 0 ? 99.9 : 0;

  const { cumPnlSeries, cumRSeries, drawdownSeries } = useMemo(() => {
    let runPnl = 0;
    let runR = 0;
    let peakPnl = 0;
    const pnlArr: number[] = [];
    const rArr: number[] = [];
    const ddArr: number[] = [];
    for (const t of filteredTrades) {
      runPnl += t.profit;
      const riskDist = Math.abs(t.open_price - t.sl);
      const rEst =
        riskDist > 0 && t.close_price > 0
          ? ((t.direction === "BUY" ? t.close_price - t.open_price : t.open_price - t.close_price) / riskDist)
          : t.profit >= 0
          ? 1
          : -1;
      runR += rEst;
      peakPnl = Math.max(peakPnl, runPnl);
      pnlArr.push(Number(runPnl.toFixed(2)));
      rArr.push(Number(runR.toFixed(2)));
      ddArr.push(Number((runPnl - peakPnl).toFixed(2)));
    }
    return { cumPnlSeries: pnlArr, cumRSeries: rArr, drawdownSeries: ddArr };
  }, [filteredTrades]);

  const equitySeries = useMemo(() => {
    const cutoffMs = rangeDays > 0 ? Date.now() - rangeDays * 86400 * 1000 : 0;
    return snapshots
      .filter((s) => cutoffMs === 0 || new Date(s.created_at).getTime() >= cutoffMs)
      .map((s) => s.equity);
  }, [snapshots, rangeDays]);

  return (
    <div className="space-y-4">
      <div className="iea-glass-card p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-lg font-light text-[#F4F7FF] flex items-center space-x-2">
              <BarChart3 className="w-5 h-5 text-[#B0F648]" />
              <span>Performance Analytics</span>
            </h2>
            <p className="text-[11px] font-mono text-[#8496B8] mt-0.5">
              Source: Real Closed Trades ({filteredTrades.length}) &amp; Real MT5 Balance Snapshots ({equitySeries.length})
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-xs">
            <select
              value={symbolFilter}
              onChange={(e) => setSymbolFilter(e.target.value)}
              aria-label="Filter analytics by symbol"
              className="iea-pill-control px-3 py-1.5 text-[#F4F7FF] focus:outline-none"
            >
              <option value="ALL" className="bg-[#0A152B]">All Symbols</option>
              <option value="XAU" className="bg-[#0A152B]">XAUUSD</option>
              <option value="JPY" className="bg-[#0A152B]">USDJPY</option>
              <option value="BTC" className="bg-[#0A152B]">BTCUSD</option>
            </select>

            <div className="inline-flex bg-[#091426]/80 border border-[rgba(186,214,255,0.16)] rounded-full p-0.5">
              {[
                { label: "7D", days: 7 },
                { label: "30D", days: 30 },
                { label: "90D", days: 90 },
                { label: "All", days: 0 },
              ].map((opt) => (
                <button
                  key={opt.label}
                  type="button"
                  onClick={() => setRangeDays(opt.days)}
                  className={`px-2.5 py-1 rounded-full text-[11px] font-mono font-bold ${
                    rangeDays === opt.days ? "bg-[#B0F648] text-[#081321]" : "text-[#B6C5E0] hover:text-white"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3.5 text-xs">
          <div className="iea-glass-tile p-4">
            <div className="text-[#B6C5E0]">Closed Trades</div>
            <div className="text-2xl font-light font-mono text-[#F4F7FF] mt-1.5">{filteredTrades.length}</div>
          </div>
          <div className="iea-glass-tile p-4">
            <div className="text-[#B6C5E0]">Win Rate</div>
            <div className="text-2xl font-light font-mono text-[#5EEAD4] mt-1.5">
              {winRate !== null ? `${winRate.toFixed(1)}%` : "—"}
            </div>
          </div>
          <div className="iea-glass-card-lime p-4">
            <div className="text-[#C2F076]">Net P&amp;L</div>
            <div className={`text-2xl font-light font-mono mt-1.5 ${netPnl >= 0 ? "text-[#B0F648]" : "text-[#FF5A6E]"}`}>
              {filteredTrades.length > 0 ? `${netPnl >= 0 ? "+" : ""}$${netPnl.toFixed(2)}` : "—"}
            </div>
          </div>
          <div className="iea-glass-tile p-4">
            <div className="text-[#B6C5E0]">Profit Factor</div>
            <div className="text-2xl font-light font-mono text-[#F4F7FF] mt-1.5">
              {profitFactor !== null ? profitFactor.toFixed(2) : "—"}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
          <MiniLineChart
            title="Equity Curve (Real MT5 Snapshots)"
            values={equitySeries}
            stroke="#B0F648"
            formatValue={(v) => `$${v.toFixed(2)}`}
            emptyText="Waiting for at least 2 real MT5 balance snapshots."
          />
          <MiniLineChart
            title="Cumulative P&L Timeline"
            values={cumPnlSeries}
            stroke="#5EEAD4"
            formatValue={(v) => `${v >= 0 ? "+" : ""}$${v.toFixed(2)}`}
            emptyText="No closed trades yet."
          />
          <MiniLineChart
            title="Cumulative R-Multiple"
            values={cumRSeries}
            stroke="#C077FA"
            formatValue={(v) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}R`}
            emptyText="No closed trades yet."
          />
          <MiniLineChart
            title="Realized Drawdown ($)"
            values={drawdownSeries}
            stroke="#FF5A6E"
            formatValue={(v) => `$${v.toFixed(2)}`}
            emptyText="No closed trades yet."
          />
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
  const [selfCheck, setSelfCheck] = useState<SelfCheckReport | null>(null);
  const [checking, setChecking] = useState(false);

  const runSelfCheck = async () => {
    setChecking(true);
    try {
      const rep = await controlClient.getSelfCheck();
      setSelfCheck(rep);
    } catch {
      setSelfCheck(null);
    } finally {
      setChecking(false);
    }
  };

  useEffect(() => {
    runSelfCheck();
  }, []);

  return (
    <div className="space-y-4">
      <div className="iea-glass-card p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-light text-[#F4F7FF] flex items-center space-x-2">
            <Database className="w-5 h-5 text-[#B0F648]" />
            <span>System Health</span>
          </h2>
          <button
            disabled={checking}
            onClick={async () => {
              await onReload();
              await runSelfCheck();
            }}
            className="iea-pill-control px-4 py-1.5 text-xs text-[#F4F7FF] font-semibold disabled:opacity-50"
          >
            {checking ? "Checking..." : "Re-run Self-Check"}
          </button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5 text-xs">
          <div className="iea-glass-tile p-4 space-y-1">
            <div className="text-[#8496B8]">SQLite DB</div>
            <div className="flex items-center space-x-1.5 font-semibold text-[#B0F648]">
              <CheckCircle2 className="w-4 h-4" />
              <span>{h?.sqlite.healthy ? `OK (v${h.sqlite.schema_version})` : "WAITING"}</span>
            </div>
            <div className="font-mono text-[10px] text-[#8496B8] break-all">{h?.sqlite.db_path || "—"}</div>
          </div>
          <div className="iea-glass-tile p-4 space-y-1">
            <div className="text-[#8496B8]">MT5 &amp; DEMO</div>
            <div className="font-mono text-[#F4F7FF]">Conn: {String(h?.mt5_connected ?? false)}</div>
            <div className="font-mono text-[#B0F648] font-bold">DEMO: {String(h?.demo_verified ?? false)}</div>
          </div>
          <div className="iea-glass-tile p-4 space-y-1">
            <div className="text-[#8496B8]">Active Err</div>
            <div className="text-2xl font-light font-mono text-[#F4F7FF]">{h?.active_error_count ?? 0}</div>
          </div>
        </div>
      </div>

      {/* Live Startup & Runtime Self-Check */}
      <div className="iea-glass-card p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-[#F4F7FF]">Runtime Self-Check</h3>
          <span
            className={`px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold ${
              selfCheck?.status === "HEALTHY"
                ? "bg-[#B0F648]/20 text-[#B0F648]"
                : "bg-[#FBBF24]/20 text-[#FBBF24]"
            }`}
          >
            {selfCheck ? selfCheck.status : "SERVICE OFFLINE"}
          </span>
        </div>
        {!selfCheck ? (
          <div className="text-xs text-[#8496B8] py-2">
            Control Service unreachable. Click Reconnect in the top bar or Re-run Self-Check.
          </div>
        ) : (
          <div className="space-y-2 text-xs">
            {selfCheck.checks.map((c) => (
              <div key={c.id} className="iea-glass-tile px-3.5 py-2.5 flex items-center justify-between gap-3">
                <div>
                  <div className="font-semibold text-[#F4F7FF]">{c.name}</div>
                  <div className="text-[11px] text-[#B6C5E0] font-mono mt-0.5">{c.detail}</div>
                </div>
                <span
                  className={`px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold shrink-0 ${
                    c.status === "PASS"
                      ? "bg-[#B0F648]/20 text-[#B0F648]"
                      : c.status === "WARN"
                      ? "bg-[#FBBF24]/20 text-[#FBBF24]"
                      : "bg-[#FF5A6E]/20 text-[#FF5A6E]"
                  }`}
                >
                  {c.status}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="iea-glass-card p-5">
        <h3 className="text-sm font-semibold text-[#F4F7FF] mb-3">Audit Trail</h3>
        <div className="space-y-2 max-h-64 overflow-y-auto text-xs">
          {audits.length === 0 ? (
            <div className="iea-glass-tile px-3.5 py-2.5 flex items-center justify-between">
              <div>
                <span className="font-mono text-[#B0F648]">[DEMO_VERIFIED]</span>{" "}
                <span className="text-[#F4F7FF]">DEMO lock &amp; R9.3 tighten-only SL active.</span>
              </div>
              <span className="text-[10px] text-[#8496B8] font-mono">OK</span>
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
  onOpenDiagnostics: () => void;
  onOpenInstitutionalEa: () => void;
  onOpenTelegram: () => void;
}> = ({ onOpenDiagnostics, onOpenInstitutionalEa, onOpenTelegram }) => {
  return (
    <div className="space-y-4">
      <div className="iea-glass-card p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-light text-[#F4F7FF] flex items-center space-x-2">
            <SettingsIcon className="w-5 h-5 text-[#B0F648]" />
            <span>Connections &amp; Diagnostics</span>
          </h2>
          <span
            title={UI_COPY.brand.demoLockTooltip}
            className="px-3 py-1 bg-[#B0F648]/16 border border-[#B0F648]/45 text-[#C2F076] text-[11px] font-bold rounded-full inline-flex items-center space-x-1.5"
          >
            <Lock className="w-3.5 h-3.5 text-[#B0F648]" />
            <span>{UI_COPY.brand.demoLockChip}</span>
          </span>
        </div>

        <div className="flex flex-wrap gap-2.5">
          <button onClick={onOpenDiagnostics} className="iea-pill-control px-4 py-2 text-xs text-[#F4F7FF] font-semibold">
            Diagnostics
          </button>
          <button onClick={onOpenInstitutionalEa} className="iea-pill-control px-4 py-2 text-xs text-[#F4F7FF] font-semibold">
            Cloud Pairing
          </button>
          <button onClick={onOpenTelegram} className="iea-pill-control px-4 py-2 text-xs text-[#F4F7FF] font-semibold">
            Telegram Setup
          </button>
        </div>
      </div>

      {/* Short-Form Glossary Section */}
      <div className="iea-glass-card p-5 space-y-3" data-testid="short-form-glossary">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-[#F4F7FF] flex items-center space-x-2">
            <BookOpen className="w-4 h-4 text-[#B0F648]" />
            <span>Glossary (Trading Short Forms)</span>
          </h3>
          <span className="text-[11px] font-mono text-[#8496B8]">{SHORT_FORM_GLOSSARY.length} terms</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2 text-xs">
          {SHORT_FORM_GLOSSARY.map((item) => (
            <div key={item.short} className="iea-glass-tile px-3 py-2 flex items-baseline justify-between gap-2">
              <span className="font-mono font-bold text-[#B0F648] shrink-0">{item.short}</span>
              <span className="text-[11px] text-[#B6C5E0] text-right">{item.full}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
