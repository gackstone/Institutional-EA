import React, { useEffect, useMemo, useState } from "react";
import {
  BarChart3,
  BookOpen,
  Bot,
  CheckCircle2,
  Database,
  FileText,
  Lock,
  LogOut,
  Moon,
  RefreshCw,
  Settings as SettingsIcon,
  Smartphone,
  Sun,
  Trash2,
  Wifi,
} from "lucide-react";
import { useTheme } from "../../context/ThemeContext";
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
import { DESIGN_TOKENS } from "../../styles/designTokens";

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
    <div className="iea-card p-5 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-bold text-iea-textPrimary flex items-center space-x-2">
          <FileText className="w-5 h-5 text-iea-accent" />
          <span>Event Logs ({logs.length})</span>
        </h2>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <select
            value={severity}
            onChange={(e) => {
              setSeverity(e.target.value);
              onReload({ severity: e.target.value || undefined, component: component || undefined });
            }}
            className="iea-pill-control px-3.5 py-1.5 text-iea-textPrimary focus:outline-none"
          >
            <option value="" className="bg-iea-card">All Levels</option>
            <option value="INFO" className="bg-iea-card">INFO</option>
            <option value="WARNING" className="bg-iea-card">WARN</option>
            <option value="ERROR" className="bg-iea-card">ERR</option>
            <option value="CRITICAL" className="bg-iea-card">CRIT</option>
          </select>
          <input
            type="text"
            value={component}
            onChange={(e) => setComponent(e.target.value)}
            placeholder="Module..."
            className="iea-input rounded-full px-3.5 py-1.5 text-iea-textPrimary"
          />
          <button
            onClick={() => onReload({ severity: severity || undefined, component: component || undefined })}
            className="iea-pill-control px-4 py-1.5 text-iea-textPrimary font-semibold"
          >
            Filter
          </button>
          <button
            onClick={handleClear}
            className="px-4 py-1.5 bg-iea-danger hover:opacity-90 text-white font-semibold rounded-full inline-flex items-center space-x-1"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>Clear</span>
          </button>
        </div>
      </div>

      <div className="iea-inset rounded-2xl p-4 font-mono text-[11px] max-h-[460px] overflow-y-auto space-y-1.5">
        {logs.length === 0 ? (
          <div className="text-iea-textMuted py-8 text-center font-sans">0 log entries.</div>
        ) : (
          logs.map((l) => (
            <div key={l.id} className="flex items-start space-x-2">
              <span className="text-iea-textMuted shrink-0">
                {new Date(l.timestamp).toLocaleTimeString()}
              </span>
              <span
                className={`shrink-0 font-bold ${
                  l.severity === "CRITICAL" || l.severity === "ERROR"
                    ? "text-iea-danger"
                    : l.severity === "WARNING"
                    ? "text-iea-warning"
                    : "text-iea-profit"
                }`}
              >
                [{l.severity}]
              </span>
              <span className="text-iea-accent shrink-0">[{l.component}]</span>
              <span className="text-iea-textPrimary break-all">{l.message}</span>
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
      <div className="iea-inset p-4 flex flex-col justify-between min-h-[168px]">
        <div className="iea-label-caps">{title}</div>
        <div className="text-xs text-iea-textMuted text-center py-8">{emptyText}</div>
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
    <div className="iea-inset p-4 flex flex-col justify-between min-h-[168px]">
      <div className="flex items-center justify-between text-xs">
        <span className="iea-label-caps">{title}</span>
        <span className="font-mono font-bold text-iea-textPrimary">{formatValue(latest)}</span>
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
      <div className="flex justify-between text-[10px] font-mono text-iea-textMuted">
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
      <div className="iea-card p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-lg font-bold text-iea-textPrimary flex items-center space-x-2">
              <BarChart3 className="w-5 h-5 text-iea-accent" />
              <span>Performance Analytics</span>
            </h2>
            <p className="text-[11px] font-mono text-iea-textMuted mt-0.5">
              Source: Real Closed Trades ({filteredTrades.length}) &amp; Real MT5 Balance Snapshots ({equitySeries.length})
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-xs">
            <select
              value={symbolFilter}
              onChange={(e) => setSymbolFilter(e.target.value)}
              aria-label="Filter analytics by symbol"
              className="iea-pill-control px-3 py-1.5 text-iea-textPrimary focus:outline-none"
            >
              <option value="ALL" className="bg-iea-card">All Symbols</option>
              <option value="XAU" className="bg-iea-card">XAUUSD</option>
              <option value="JPY" className="bg-iea-card">USDJPY</option>
              <option value="BTC" className="bg-iea-card">BTCUSD</option>
            </select>

            <div className="inline-flex bg-iea-inset border border-iea-borderSubtle rounded-[10px] p-1">
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
                  className={`px-2.5 py-1 rounded-[7px] text-[11px] font-mono font-bold transition ${
                    rangeDays === opt.days
                      ? "bg-iea-accent text-white"
                      : "text-iea-textSecondary hover:text-iea-textPrimary"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3.5 text-xs">
          <div className="iea-inset p-4">
            <div className="iea-label-caps">Closed Trades</div>
            <div className="text-2xl font-bold font-mono text-iea-textPrimary mt-1.5">
              {filteredTrades.length}
            </div>
          </div>
          <div className="iea-inset p-4">
            <div className="iea-label-caps">Win Rate</div>
            <div className="text-2xl font-bold font-mono text-iea-accent mt-1.5">
              {winRate !== null ? `${winRate.toFixed(1)}%` : "—"}
            </div>
          </div>
          <div className="iea-card p-4">
            <div className="iea-label-caps">Net Realized P/L</div>
            <div
              className={`text-2xl font-bold font-mono mt-1.5 ${
                netPnl >= 0 ? "text-iea-profit" : "text-iea-danger"
              }`}
            >
              {filteredTrades.length > 0 ? `${netPnl >= 0 ? "+" : ""}$${netPnl.toFixed(2)}` : "—"}
            </div>
          </div>
          <div className="iea-inset p-4">
            <div className="iea-label-caps">Profit Factor</div>
            <div className="text-2xl font-bold font-mono text-iea-textPrimary mt-1.5">
              {profitFactor !== null ? profitFactor.toFixed(2) : "—"}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
          <MiniLineChart
            title="Equity Curve (Real MT5 Snapshots)"
            values={equitySeries}
            stroke={DESIGN_TOKENS.colors.accent.primary}
            formatValue={(v) => `$${v.toFixed(2)}`}
            emptyText="Waiting for at least 2 real MT5 balance snapshots."
          />
          <MiniLineChart
            title="Cumulative P&L Timeline"
            values={cumPnlSeries}
            stroke={DESIGN_TOKENS.colors.semantic.profit}
            formatValue={(v) => `${v >= 0 ? "+" : ""}$${v.toFixed(2)}`}
            emptyText="No closed trades yet."
          />
          <MiniLineChart
            title="Cumulative R-Multiple"
            values={cumRSeries}
            stroke={DESIGN_TOKENS.colors.accent.primary}
            formatValue={(v) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}R`}
            emptyText="No closed trades yet."
          />
          <MiniLineChart
            title="Realized Drawdown ($)"
            values={drawdownSeries}
            stroke={DESIGN_TOKENS.colors.semantic.danger}
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
      <div className="iea-card p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-iea-textPrimary flex items-center space-x-2">
            <Database className="w-5 h-5 text-iea-accent" />
            <span>System Health</span>
          </h2>
          <button
            disabled={checking}
            onClick={async () => {
              await onReload();
              await runSelfCheck();
            }}
            className="iea-pill-control px-4 py-1.5 text-xs text-iea-textPrimary font-semibold disabled:opacity-50"
          >
            {checking ? "Checking..." : "Re-run Self-Check"}
          </button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5 text-xs">
          <div className="iea-inset p-4 space-y-1">
            <div className="iea-label-caps">SQLite DB</div>
            <div className="flex items-center space-x-1.5 font-semibold text-iea-profit">
              <CheckCircle2 className="w-4 h-4" />
              <span>{h?.sqlite.healthy ? `OK (v${h.sqlite.schema_version})` : "WAITING"}</span>
            </div>
            <div className="font-mono text-[10px] text-iea-textMuted break-all">
              {h?.sqlite.db_path || "—"}
            </div>
          </div>
          <div className="iea-inset p-4 space-y-1">
            <div className="iea-label-caps">MT5 &amp; DEMO</div>
            <div className="font-mono text-iea-textPrimary">
              Conn: {String(h?.mt5_connected ?? false)}
            </div>
            <div className="font-mono text-iea-profit font-bold">
              DEMO: {String(h?.demo_verified ?? false)}
            </div>
          </div>
          <div className="iea-inset p-4 space-y-1">
            <div className="iea-label-caps">Active Err</div>
            <div className="text-2xl font-bold font-mono text-iea-textPrimary">
              {h?.active_error_count ?? 0}
            </div>
          </div>
        </div>
      </div>

      {/* Live Startup & Runtime Self-Check */}
      <div className="iea-card p-5 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-iea-textPrimary">Runtime Self-Check</h3>
          <span
            className={`px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold ${
              selfCheck?.status === "HEALTHY"
                ? "bg-iea-profitSoft text-iea-profit"
                : "bg-iea-warningSoft text-iea-warning"
            }`}
          >
            {selfCheck ? selfCheck.status : "SERVICE OFFLINE"}
          </span>
        </div>
        {!selfCheck ? (
          <div className="text-xs text-iea-textMuted py-2">
            Control Service unreachable. Click Reconnect in the top bar or Re-run Self-Check.
          </div>
        ) : (
          <div className="space-y-2 text-xs">
            {selfCheck.checks.map((c) => (
              <div key={c.id} className="iea-inset px-3.5 py-2.5 flex items-center justify-between gap-3">
                <div>
                  <div className="font-semibold text-iea-textPrimary">{c.name}</div>
                  <div className="text-[11px] text-iea-textSecondary font-mono mt-0.5">
                    {c.detail}
                  </div>
                </div>
                <span
                  className={`px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold shrink-0 ${
                    c.status === "PASS"
                      ? "bg-iea-profitSoft text-iea-profit"
                      : c.status === "WARN"
                      ? "bg-iea-warningSoft text-iea-warning"
                      : "bg-iea-dangerSoft text-iea-danger"
                  }`}
                >
                  {c.status}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="iea-card p-5">
        <h3 className="text-sm font-bold text-iea-textPrimary mb-3">Audit Trail</h3>
        <div className="space-y-2 max-h-64 overflow-y-auto text-xs">
          {audits.length === 0 ? (
            <div className="iea-inset px-3.5 py-2.5 flex items-center justify-between">
              <div>
                <span className="font-mono text-iea-profit">[DEMO_VERIFIED]</span>{" "}
                <span className="text-iea-textPrimary">
                  DEMO lock &amp; R9.3 tighten-only SL active.
                </span>
              </div>
              <span className="text-[10px] text-iea-textMuted font-mono">OK</span>
            </div>
          ) : (
            audits.map((a) => (
              <div key={a.id} className="iea-inset flex items-center justify-between px-3.5 py-2.5">
                <div>
                  <span className="font-mono text-iea-accent">[{a.action}]</span>{" "}
                  <span className="text-iea-textPrimary">{a.details}</span>
                </div>
                <span className="text-[10px] text-iea-textMuted">
                  {new Date(a.created_at).toLocaleTimeString()}
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};

const SETTINGS_PREFS_KEY = "iea_companion_user_prefs_v1";

interface CompanionUserPrefs {
  desktopNotifications: boolean;
  signalSoundAlerts: boolean;
  autoConnectMt5: boolean;
  startMinimized: boolean;
}

const DEFAULT_USER_PREFS: CompanionUserPrefs = {
  desktopNotifications: true,
  signalSoundAlerts: false,
  autoConnectMt5: true,
  startMinimized: false,
};

function loadUserPrefs(): CompanionUserPrefs {
  try {
    const raw = localStorage.getItem(SETTINGS_PREFS_KEY);
    if (!raw) return DEFAULT_USER_PREFS;
    return { ...DEFAULT_USER_PREFS, ...JSON.parse(raw) };
  } catch {
    return DEFAULT_USER_PREFS;
  }
}

export const SettingsScreen: React.FC<{
  status?: ControlStatusPayload | null;
  cloudEmail?: string | null;
  cloudConnected?: boolean;
  onOpenDiagnostics: () => void;
  onOpenInstitutionalEa: () => void;
  onOpenTelegram: () => void;
  onOpenMobileSync?: () => void;
  onReconnectService?: () => Promise<void>;
  onSignOut?: () => Promise<void>;
}> = ({
  status = null,
  cloudEmail = null,
  cloudConnected = false,
  onOpenDiagnostics,
  onOpenInstitutionalEa,
  onOpenTelegram,
  onOpenMobileSync,
  onReconnectService,
  onSignOut,
}) => {
  const { theme, toggleTheme } = useTheme();
  const [prefs, setPrefs] = useState<CompanionUserPrefs>(() => loadUserPrefs());
  const [reconnecting, setReconnecting] = useState(false);

  const updatePref = <K extends keyof CompanionUserPrefs>(key: K, val: CompanionUserPrefs[K]) => {
    setPrefs((prev) => {
      const next = { ...prev, [key]: val };
      try {
        localStorage.setItem(SETTINGS_PREFS_KEY, JSON.stringify(next));
      } catch {
        // ignore storage quota errors
      }
      return next;
    });
  };

  const mt5Connected = status?.mt5?.connection_status === "CONNECTED";
  const maskedAcct = status?.mt5?.account?.account_number
    ? `****${String(status.mt5.account.account_number).slice(-4)}`
    : "Not connected";
  const engineState = status?.engine?.state || "STOPPED";
  const engineMode = status?.engine?.operating_mode || "DEMO";

  return (
    <div className="space-y-4">
      {/* Header & Android Pairing CTA */}
      <div className="iea-card p-5 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-lg font-bold text-iea-textPrimary flex items-center space-x-2">
              <SettingsIcon className="w-5 h-5 text-iea-accent" />
              <span>Settings</span>
            </h2>
            <p className="text-xs text-iea-textSecondary mt-0.5">
              Manage appearance, notifications, MT5 connection, and Android companion pairing.
            </p>
          </div>
          <div className="flex items-center gap-2">
            {onOpenMobileSync && (
              <button
                type="button"
                onClick={onOpenMobileSync}
                data-testid="btn-pair-new-android"
                className="px-4 py-2 rounded-xl bg-iea-accent hover:bg-iea-accentHover text-white text-xs font-bold inline-flex items-center gap-1.5 transition"
              >
                <Smartphone className="w-3.5 h-3.5" />
                <span>PAIR NEW ANDROID DEVICE</span>
              </button>
            )}
            <span
              title={UI_COPY.brand.demoLockTooltip}
              className="px-3 py-1 bg-iea-accentSoft border border-iea-accentBorder text-iea-accent text-[11px] font-bold rounded-full inline-flex items-center space-x-1.5"
            >
              <Lock className="w-3.5 h-3.5 text-iea-accent" />
              <span>{UI_COPY.brand.demoLockChip}</span>
            </span>
          </div>
        </div>
      </div>

      {/* Section A: Application Settings */}
      <div className="iea-card p-5 space-y-3" data-testid="settings-section-application">
        <h3 className="text-sm font-bold text-iea-textPrimary">Application Settings</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
          <div className="iea-inset p-3.5 rounded-xl flex items-center justify-between">
            <div>
              <div className="font-semibold text-iea-textPrimary">Appearance Theme</div>
              <div className="text-[11px] text-iea-textSecondary">Switch between Dark and Light mode</div>
            </div>
            <button
              type="button"
              onClick={toggleTheme}
              className="iea-pill-control px-3 py-1.5 font-semibold inline-flex items-center gap-1.5 text-iea-textPrimary"
            >
              {theme === "dark" ? <Moon className="w-3.5 h-3.5" /> : <Sun className="w-3.5 h-3.5" />}
              <span>{theme === "dark" ? "Dark" : "Light"}</span>
            </button>
          </div>

          <div className="iea-inset p-3.5 rounded-xl flex items-center justify-between">
            <div>
              <div className="font-semibold text-iea-textPrimary">Desktop Notifications</div>
              <div className="text-[11px] text-iea-textSecondary">Alert when new bot signals or trades occur</div>
            </div>
            <input
              type="checkbox"
              checked={prefs.desktopNotifications}
              onChange={(e) => updatePref("desktopNotifications", e.target.checked)}
              aria-label="Desktop Notifications"
              className="w-4 h-4 accent-emerald-500 cursor-pointer"
            />
          </div>

          <div className="iea-inset p-3.5 rounded-xl flex items-center justify-between">
            <div>
              <div className="font-semibold text-iea-textPrimary">Auto-Connect MT5 on Startup</div>
              <div className="text-[11px] text-iea-textSecondary">Reconnect to your MetaTrader 5 terminal automatically</div>
            </div>
            <input
              type="checkbox"
              checked={prefs.autoConnectMt5}
              onChange={(e) => updatePref("autoConnectMt5", e.target.checked)}
              aria-label="Auto-Connect MT5 on Startup"
              className="w-4 h-4 accent-emerald-500 cursor-pointer"
            />
          </div>

          <div className="iea-inset p-3.5 rounded-xl flex items-center justify-between">
            <div>
              <div className="font-semibold text-iea-textPrimary">Application Version &amp; Cloud Session</div>
              <div className="text-[11px] text-iea-textSecondary">
                v1.3.5 · {cloudConnected ? `Signed in (${cloudEmail || "Cloud Active"})` : "Cloud session offline"}
              </div>
            </div>
            {onSignOut && (
              <button
                type="button"
                onClick={() => onSignOut()}
                data-testid="settings-logout-btn"
                className="px-3 py-1.5 rounded-lg bg-iea-dangerSoft border border-iea-dangerBorder text-iea-danger font-semibold inline-flex items-center gap-1.5 hover:opacity-90 transition"
              >
                <LogOut className="w-3.5 h-3.5" />
                <span>Log Out</span>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Section B: Trading Bot Settings */}
      <div className="iea-card p-5 space-y-3" data-testid="settings-section-bot">
        <h3 className="text-sm font-bold text-iea-textPrimary flex items-center gap-2">
          <Bot className="w-4 h-4 text-iea-accent" />
          <span>Trading Bot Status &amp; Monitoring</span>
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
          <div className="iea-inset p-3.5 rounded-xl space-y-1">
            <div className="iea-label-caps">Trading Engine</div>
            <div className="font-mono font-bold text-iea-textPrimary">{engineState}</div>
            <div className="text-[11px] text-iea-textSecondary">Mode: {engineMode}</div>
          </div>
          <div className="iea-inset p-3.5 rounded-xl space-y-1">
            <div className="iea-label-caps">Account Sync</div>
            <div className={`font-semibold ${mt5Connected ? "text-iea-profit" : "text-iea-textMuted"}`}>
              {mt5Connected ? "Synchronized" : "Waiting for MT5"}
            </div>
            <div className="text-[11px] text-iea-textSecondary">Safety: DEMO &amp; R9.3 Locked</div>
          </div>
          <div className="iea-inset p-3.5 rounded-xl flex items-center justify-between">
            <div>
              <div className="font-semibold text-iea-textPrimary">Signal Sound Alerts</div>
              <div className="text-[11px] text-iea-textSecondary">Play chime on new Live Signals</div>
            </div>
            <input
              type="checkbox"
              checked={prefs.signalSoundAlerts}
              onChange={(e) => updatePref("signalSoundAlerts", e.target.checked)}
              aria-label="Signal Sound Alerts"
              className="w-4 h-4 accent-emerald-500 cursor-pointer"
            />
          </div>
        </div>
      </div>

      {/* Section C: MT5 Connection Settings (Zero Credentials Exposed) */}
      <div className="iea-card p-5 space-y-3" data-testid="settings-section-mt5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-bold text-iea-textPrimary flex items-center gap-2">
            <Wifi className="w-4 h-4 text-iea-accent" />
            <span>MT5 Connection &amp; Diagnostics</span>
          </h3>
          <div className="flex flex-wrap gap-2">
            {onReconnectService && (
              <button
                type="button"
                disabled={reconnecting}
                onClick={async () => {
                  setReconnecting(true);
                  try {
                    await onReconnectService();
                  } finally {
                    setReconnecting(false);
                  }
                }}
                className="iea-pill-control px-3.5 py-1.5 text-xs text-iea-textPrimary font-semibold inline-flex items-center gap-1.5"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${reconnecting ? "animate-spin" : ""}`} />
                <span>{reconnecting ? "Reconnecting..." : "Reconnect"}</span>
              </button>
            )}
            <button
              type="button"
              onClick={onOpenDiagnostics}
              className="iea-pill-control px-3.5 py-1.5 text-xs text-iea-textPrimary font-semibold"
            >
              Diagnostics
            </button>
            <button
              type="button"
              onClick={onOpenTelegram}
              className="iea-pill-control px-3.5 py-1.5 text-xs text-iea-textPrimary font-semibold"
            >
              Telegram Setup
            </button>
            <button
              type="button"
              onClick={onOpenInstitutionalEa}
              className="iea-pill-control px-3.5 py-1.5 text-xs text-iea-textPrimary font-semibold"
            >
              Agent Cloud Pairing
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs">
          <div className="iea-inset p-3.5 rounded-xl space-y-1">
            <div className="iea-label-caps">MT5 Terminal</div>
            <div className={`font-bold ${mt5Connected ? "text-iea-profit" : "text-iea-danger"}`}>
              {mt5Connected ? "Connected" : "Disconnected"}
            </div>
          </div>
          <div className="iea-inset p-3.5 rounded-xl space-y-1">
            <div className="iea-label-caps">Connected Account</div>
            <div className="font-mono font-bold text-iea-textPrimary">{maskedAcct}</div>
            <div className="text-[11px] text-iea-textSecondary truncate">
              {status?.mt5?.account?.broker || "No broker"}
            </div>
          </div>
          <div className="iea-inset p-3.5 rounded-xl space-y-1">
            <div className="iea-label-caps">Local Bridge</div>
            <div className="font-mono text-iea-textPrimary">127.0.0.1:8765</div>
            <div className="text-[11px] text-iea-textSecondary">Credentials never exposed</div>
          </div>
          <div className="iea-inset p-3.5 rounded-xl space-y-1">
            <div className="iea-label-caps">Last Sync</div>
            <div className="font-mono text-iea-textPrimary">
              {status?.mt5?.last_sync_at ? new Date(status.mt5.last_sync_at).toLocaleTimeString() : "—"}
            </div>
          </div>
        </div>
      </div>

      {/* Short-Form Glossary Section */}
      <div className="iea-card p-5 space-y-3" data-testid="short-form-glossary">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-iea-textPrimary flex items-center space-x-2">
            <BookOpen className="w-4 h-4 text-iea-accent" />
            <span>Glossary (Trading Short Forms)</span>
          </h3>
          <span className="text-[11px] font-mono text-iea-textMuted">
            {SHORT_FORM_GLOSSARY.length} terms
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2 text-xs">
          {SHORT_FORM_GLOSSARY.map((item) => (
            <div key={item.short} className="iea-inset px-3 py-2 flex items-baseline justify-between gap-2">
              <span className="font-mono font-bold text-iea-accent shrink-0">{item.short}</span>
              <span className="text-[11px] text-iea-textSecondary text-right">{item.full}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
