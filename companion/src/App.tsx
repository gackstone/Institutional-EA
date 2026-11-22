import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertOctagon,
  BarChart3,
  CheckCircle2,
  Cpu,
  Database,
  FileText,
  FolderCog,
  History,
  Layers,
  LayoutDashboard,
  Link2,
  Lock,
  Menu,
  Radio,
  RefreshCw,
  Settings as SettingsIcon,
  Shield,
  Terminal,
  TrendingUp,
  X,
  Zap,
} from "lucide-react";
import {
  DashboardScreen,
  EngineScreen,
  MarketWatchScreen,
  SignalsScreen,
} from "./components/screens/CoreTradingScreens";
import {
  InstrumentsScreen,
  PositionsScreen,
  RiskManagerScreen,
  TradeHistoryScreen,
} from "./components/screens/ExecutionRiskScreens";
import {
  ConfigurationScreen,
  ErrorCentreScreen,
  MT5ConnectionScreen,
  OperationsCentreScreen,
} from "./components/screens/OperationsSystemScreens";
import {
  AnalyticsScreen,
  LogsScreen,
  SettingsScreen,
  SystemHealthScreen,
} from "./components/screens/MonitoringSettingsScreens";
import { MT5SetupWizard } from "./components/MT5SetupWizard";
import { PairingModal } from "./components/PairingModal";
import { TelegramPairingModal } from "./components/TelegramPairingModal";
import { OnboardingWizard } from "./components/OnboardingWizard";
import { DiagnosticsModal } from "./components/DiagnosticsModal";
import { SettingsModal } from "./components/SettingsModal";

import {
  AuditLogRecord,
  BTCUSDSampleStatus,
  ControlErrorEvent,
  ControlLogEntry,
  ControlStatusPayload,
  PairingStatus,
  RiskDecisionRecord,
  ScreenId,
  TelegramStatus,
  TradeHistoryRecord,
} from "./types";
import { controlClient, IPC } from "./services/ipc";
import {
  buildNormalizedDashboardData,
  DataFeedStatus,
  normalizeLogEntries,
} from "./services/dashboardDataAdapter";

interface NavScreenItem {
  id: ScreenId;
  label: string;
  badge?: string | number;
  icon: React.ComponentType<{ className?: string }>;
}

interface NavGroupSpec {
  group: "Monitor" | "Control" | "Diagnose";
  items: NavScreenItem[];
}

export const App: React.FC = () => {
  const [activeScreen, setActiveScreen] = useState<ScreenId>("dashboard");
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(true);
  const [feedStatus, setFeedStatus] = useState<DataFeedStatus>("LOADING");

  // Authoritative Control Service state
  const [rawStatus, setRawStatus] = useState<ControlStatusPayload | null>(null);
  const [btcStatus, setBtcStatus] = useState<BTCUSDSampleStatus | null>(null);
  const [trades, setTrades] = useState<TradeHistoryRecord[]>([]);
  const [decisions, setDecisions] = useState<RiskDecisionRecord[]>([]);
  const [riskState, setRiskState] = useState<Record<string, any>>({});
  const [instrumentsConfig, setInstrumentsConfig] = useState<Record<string, any>>({});
  const [errors, setErrors] = useState<ControlErrorEvent[]>([]);
  const [controlLogs, setControlLogs] = useState<ControlLogEntry[]>([]);
  const [audits, setAudits] = useState<AuditLogRecord[]>([]);

  // Action feedback toast banner
  const [actionToast, setActionToast] = useState<{
    message: string;
    isError: boolean;
    ts: number;
  } | null>(null);

  // Pairing & Modal Dialogs
  const [pairing, setPairing] = useState<PairingStatus>({
    isPaired: false,
    instanceId: null,
    deviceTokenMasked: null,
    pairedAt: null,
    apiUrl: "https://arcadefx.live/api/v1",
  });
  const [telegram, setTelegram] = useState<TelegramStatus>({
    isPaired: false,
    botTokenMasked: null,
    chatIdMasked: null,
    botUsername: null,
    enabled: true,
  });

  const [isMT5WizardOpen, setIsMT5WizardOpen] = useState<boolean>(false);
  const [isPairingOpen, setIsPairingOpen] = useState<boolean>(false);
  const [isTelegramOpen, setIsTelegramOpen] = useState<boolean>(false);
  const [isOnboardingOpen, setIsOnboardingOpen] = useState<boolean>(false);
  const [isDiagnosticsOpen, setIsDiagnosticsOpen] = useState<boolean>(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState<boolean>(false);

  const handleActionMessage = useCallback((message: string, isError = false) => {
    setActionToast({ message, isError, ts: Date.now() });
  }, []);

  // Auto-dismiss toast after 6 seconds
  useEffect(() => {
    if (!actionToast) return;
    const t = setTimeout(() => setActionToast(null), 6000);
    return () => clearTimeout(t);
  }, [actionToast]);

  const refreshStatus = useCallback(async () => {
    try {
      const st = await controlClient.getStatus();
      setRawStatus(st);
      setFeedStatus((prev) => (prev === "LIVE_SSE" ? "LIVE_SSE" : "POLLING"));
    } catch {
      // Fallback to normalized DEMO state when local Control Service daemon is not active
      setFeedStatus((prev) => (prev === "LIVE_SSE" ? "LIVE_SSE" : "POLLING"));
    }
  }, []);

  const refreshBtcStatus = useCallback(async () => {
    try {
      const b = await controlClient.getBtcSampleStatus();
      setBtcStatus(b);
    } catch {
      // ignore offline
    }
  }, []);

  const reloadTrades = useCallback(async () => {
    try {
      const res = await controlClient.getTradeHistory();
      setTrades(res.trades || []);
    } catch {
      // fallback handled by normalized data
    }
  }, []);

  const reloadDecisions = useCallback(async () => {
    try {
      const res = await controlClient.getRiskDecisions();
      setDecisions(res.decisions || []);
      setRiskState(res.risk_state || {});
    } catch {
      // fallback handled by normalized data
    }
  }, []);

  const reloadErrors = useCallback(async () => {
    try {
      const res = await controlClient.getErrors();
      setErrors(res.errors || []);
    } catch {
      // fallback handled by normalized data
    }
  }, []);

  const reloadLogs = useCallback(
    async (filters?: { severity?: string; component?: string }) => {
      try {
        const res = await controlClient.getLogs({
          limit: 200,
          severity: filters?.severity,
          component: filters?.component,
        });
        setControlLogs(res.logs || []);
      } catch {
        setControlLogs(normalizeLogEntries([]));
      }
    },
    []
  );

  const reloadAudits = useCallback(async () => {
    try {
      const res = await controlClient.getAudit();
      setAudits(res.audits || []);
    } catch {
      // ignore offline
    }
  }, []);

  const reloadConfigInstruments = useCallback(async () => {
    try {
      const cfg = await controlClient.getConfig();
      setInstrumentsConfig(cfg.instruments || {});
    } catch {
      setInstrumentsConfig({
        XAUUSD: { canonical: "XAUUSD", broker_symbol: "XAUUSD.m", schedule: "WEEKDAY_GOLD_MODE", digits: 2 },
        USDJPY: { canonical: "USDJPY", broker_symbol: "USDJPY.m", schedule: "WEEKDAY_GOLD_MODE", digits: 3 },
        BTCUSD: { canonical: "BTCUSD", broker_symbol: "BTCUSD.m", schedule: "WEEKEND_BTC_MODE", digits: 2 },
      });
    }
  }, []);

  // Initial load + SSE connection to /api/events + periodic polling backup
  useEffect(() => {
    refreshStatus();
    refreshBtcStatus();
    reloadTrades();
    reloadDecisions();
    reloadErrors();
    reloadLogs();
    reloadAudits();
    reloadConfigInstruments();

    IPC.getPairingStatus().then(setPairing).catch(() => {});
    IPC.getTelegramStatus().then(setTelegram).catch(() => {});

    let es: EventSource | null = null;
    let cancelled = false;

    const connectSse = async () => {
      try {
        let baseUrl = "http://127.0.0.1:8765";
        let token = "";
        if (window.electronAPI?.getControlConnectionInfo) {
          const info = await window.electronAPI.getControlConnectionInfo();
          baseUrl = info.baseUrl || baseUrl;
          token = info.token || "";
        }
        if (cancelled) return;
        const sseUrl = token ? `${baseUrl}/api/events?token=${encodeURIComponent(token)}` : `${baseUrl}/api/events`;
        es = new EventSource(sseUrl);

        es.onopen = () => {
          if (!cancelled) setFeedStatus("LIVE_SSE");
        };

        es.onmessage = (evt) => {
          if (cancelled) return;
          try {
            const parsed = JSON.parse(evt.data);
            setFeedStatus("LIVE_SSE");
            if (parsed.type === "snapshot" && parsed.payload) {
              setRawStatus(parsed.payload);
            } else if (parsed.type === "mt5_sync" && parsed.payload) {
              setRawStatus((prev) =>
                prev ? { ...prev, mt5: parsed.payload } : prev
              );
            } else if (parsed.type === "engine_state" && parsed.payload) {
              setRawStatus((prev) =>
                prev ? { ...prev, engine: { ...prev.engine, ...parsed.payload } } : prev
              );
            } else if (parsed.type === "log" && parsed.payload) {
              setControlLogs((prev) => [parsed.payload, ...prev.slice(0, 199)]);
            }
          } catch {
            // ignore malformed event
          }
        };

        es.onerror = () => {
          if (!cancelled) {
            setFeedStatus("POLLING");
          }
        };
      } catch {
        if (!cancelled) setFeedStatus("POLLING");
      }
    };

    connectSse();
    const interval = setInterval(() => {
      refreshStatus();
    }, 4000);

    return () => {
      cancelled = true;
      clearInterval(interval);
      if (es) es.close();
    };
  }, [
    refreshStatus,
    refreshBtcStatus,
    reloadTrades,
    reloadDecisions,
    reloadErrors,
    reloadLogs,
    reloadAudits,
    reloadConfigInstruments,
  ]);

  const normalized = useMemo(
    () => buildNormalizedDashboardData(rawStatus, trades, decisions, errors),
    [rawStatus, trades, decisions, errors]
  );

  const effectiveStatus = normalized.status;
  const activeErrorCount = effectiveStatus.health.active_error_count;
  const openPosCount = effectiveStatus.mt5.positions.length;

  // All 16 screens grouped under Monitor / Control / Diagnose
  const navGroups: NavGroupSpec[] = useMemo(
    () => [
      {
        group: "Monitor",
        items: [
          { id: "dashboard", label: "Dashboard", icon: LayoutDashboard, badge: "LIVE" },
          { id: "market", label: "Market Watch", icon: TrendingUp, badge: 3 },
          { id: "signals", label: "Signals Pipeline", icon: Zap },
          { id: "positions", label: "Positions & Orders", icon: Layers, badge: openPosCount },
          { id: "history", label: "Trade History", icon: History, badge: normalized.recentTrades.length },
          { id: "analytics", label: "Analytics", icon: BarChart3 },
        ],
      },
      {
        group: "Control",
        items: [
          { id: "engine", label: "Engine Control", icon: Cpu },
          { id: "risk", label: "Risk Manager", icon: Shield },
          { id: "instruments", label: "Instruments", icon: Activity },
          { id: "configuration", label: "Configuration", icon: FolderCog },
          { id: "mt5", label: "MT5 Terminal", icon: Link2 },
          { id: "operations", label: "Operations", icon: Terminal },
        ],
      },
      {
        group: "Diagnose",
        items: [
          {
            id: "errors",
            label: "Error Centre",
            icon: AlertOctagon,
            badge: activeErrorCount > 0 ? activeErrorCount : undefined,
          },
          { id: "logs", label: "Event Logs", icon: FileText },
          { id: "health", label: "System Health", icon: Database },
          { id: "settings", label: "Settings", icon: SettingsIcon },
        ],
      },
    ],
    [openPosCount, normalized.recentTrades.length, activeErrorCount]
  );

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-[#06080c] text-slate-100 antialiased font-sans select-none">
      {/* =====================================================================
          LEFT NAVIGATION SIDEBAR (16 Screens grouped Monitor / Control / Diagnose)
      ====================================================================== */}
      <aside
        aria-label="Primary Terminal Navigation"
        className={`${
          sidebarOpen ? "w-56" : "w-14"
        } shrink-0 bg-[#090d13] border-r border-slate-800/90 flex flex-col justify-between transition-all duration-150`}
      >
        {/* Brand Header */}
        <div>
          <div className="h-12 px-3 border-b border-slate-800/90 flex items-center justify-between">
            {sidebarOpen ? (
              <div className="flex items-center space-x-2 min-w-0">
                <div className="w-7 h-7 rounded-lg bg-sky-600/20 border border-sky-500/40 flex items-center justify-center shrink-0">
                  <Activity className="w-4 h-4 text-sky-400" />
                </div>
                <div className="truncate">
                  <div className="text-xs font-extrabold tracking-tight text-slate-100 leading-none">
                    INSTITUTIONAL EA
                  </div>
                  <div className="text-[10px] font-mono text-emerald-400 mt-0.5">
                    TERMINAL v1.2 · DEMO
                  </div>
                </div>
              </div>
            ) : (
              <div className="w-7 h-7 mx-auto rounded-lg bg-sky-600/20 border border-sky-500/40 flex items-center justify-center">
                <Activity className="w-4 h-4 text-sky-400" />
              </div>
            )}

            <button
              type="button"
              onClick={() => setSidebarOpen((v) => !v)}
              aria-label={sidebarOpen ? "Collapse navigation sidebar" : "Expand navigation sidebar"}
              className="p-1 rounded-md text-slate-400 hover:text-slate-100 hover:bg-slate-800/70"
            >
              <Menu className="w-4 h-4" />
            </button>
          </div>

          {/* Grouped Screen Links (Monitor / Control / Diagnose) */}
          <nav aria-label="Screen Groups" className="p-2 space-y-3 overflow-y-auto max-h-[calc(100vh-120px)]">
            {navGroups.map((grp) => (
              <div key={grp.group} className="space-y-0.5">
                {sidebarOpen && (
                  <div className="px-2 py-1 text-[10px] font-bold uppercase tracking-widest text-slate-400">
                    {grp.group}
                  </div>
                )}
                {grp.items.map((item) => {
                  const Icon = item.icon;
                  const active = activeScreen === item.id;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => setActiveScreen(item.id)}
                      aria-current={active ? "page" : undefined}
                      aria-label={item.label}
                      title={item.label}
                      className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs font-medium transition ${
                        active
                          ? "bg-sky-600/20 text-sky-200 border border-sky-500/40 font-semibold"
                          : "text-slate-300 hover:text-white hover:bg-slate-800/60 border border-transparent"
                      }`}
                    >
                      <div className="flex items-center space-x-2.5 min-w-0">
                        <Icon
                          className={`w-4 h-4 shrink-0 ${
                            active ? "text-sky-400" : "text-slate-400"
                          }`}
                        />
                        {sidebarOpen && <span className="truncate">{item.label}</span>}
                      </div>
                      {sidebarOpen && item.badge !== undefined && (
                        <span
                          className={`px-1.5 py-0.2 rounded text-[10px] font-mono font-bold ${
                            item.id === "errors" && Number(item.badge) > 0
                              ? "bg-rose-500/25 text-rose-300"
                              : active
                              ? "bg-sky-500/30 text-sky-200"
                              : "bg-slate-800 text-slate-300"
                          }`}
                        >
                          {item.badge}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            ))}
          </nav>
        </div>

        {/* Sidebar Footer: Hard DEMO Safety Lock Indicator */}
        <div className="p-2.5 border-t border-slate-800/90 bg-slate-950/80">
          {sidebarOpen ? (
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-[10px] font-mono">
                <span className="inline-flex items-center space-x-1 text-emerald-300 font-bold">
                  <Lock className="w-3 h-3" />
                  <span>DEMO LOCK ACTIVE</span>
                </span>
                <span className="text-slate-400">127.0.0.1:8765</span>
              </div>
              <div className="text-[10px] text-slate-400 flex items-center justify-between">
                <span>Feed: {feedStatus}</span>
                <button
                  type="button"
                  onClick={() => refreshStatus()}
                  aria-label="Refresh terminal telemetry"
                  className="text-sky-400 hover:text-sky-300 inline-flex items-center space-x-0.5"
                >
                  <RefreshCw className="w-3 h-3" />
                  <span>Sync</span>
                </button>
              </div>
            </div>
          ) : (
            <div className="flex justify-center" title="DEMO Lock Active (LIVE_TRADING_ENABLED=false)">
              <Lock className="w-4 h-4 text-emerald-400" />
            </div>
          )}
        </div>
      </aside>

      {/* =====================================================================
          MAIN CONTENT AREA (Renders Active Screen + Action Feedback Toast)
      ====================================================================== */}
      <div className="flex-1 min-w-0 flex flex-col h-screen overflow-hidden">
        {/* Non-Dashboard Screen Header Bar (when viewing one of the other 15 screens) */}
        {activeScreen !== "dashboard" && (
          <header className="h-12 px-4 bg-[#090d13] border-b border-slate-800/90 flex items-center justify-between shrink-0">
            <div className="flex items-center space-x-3">
              <button
                type="button"
                onClick={() => setActiveScreen("dashboard")}
                className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs text-slate-200 font-semibold"
              >
                ← Back to Dashboard
              </button>
              <h1 className="text-sm font-bold text-slate-100 uppercase tracking-wider">
                {navGroups.flatMap((g) => g.items).find((i) => i.id === activeScreen)?.label ||
                  activeScreen}
              </h1>
            </div>

            <div className="flex items-center space-x-2 text-xs font-mono">
              <span className="px-2 py-0.5 rounded bg-emerald-950/80 border border-emerald-500/40 text-emerald-300 font-bold">
                DEMO · LIVE_TRADING_ENABLED=false
              </span>
              <span className="px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-slate-300">
                MT5 {normalized.maskedAccount}
              </span>
              <span className="px-2 py-0.5 rounded bg-slate-900 border border-slate-800 text-sky-300 inline-flex items-center space-x-1">
                <Radio className="w-3 h-3 text-emerald-400" />
                <span>{feedStatus}</span>
              </span>
            </div>
          </header>
        )}

        {/* Action Toast Notification Banner */}
        {actionToast && (
          <div
            role="status"
            aria-live="polite"
            className={`mx-3 mt-2 px-3.5 py-2 rounded-xl border text-xs flex items-center justify-between shrink-0 ${
              actionToast.isError
                ? "bg-rose-950/90 border-rose-500/60 text-rose-100"
                : "bg-emerald-950/90 border-emerald-500/60 text-emerald-100"
            }`}
          >
            <div className="flex items-center space-x-2">
              {actionToast.isError ? (
                <AlertOctagon className="w-4 h-4 text-rose-400 shrink-0" />
              ) : (
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
              )}
              <span>{actionToast.message}</span>
            </div>
            <button
              type="button"
              onClick={() => setActionToast(null)}
              aria-label="Dismiss notification"
              className="p-0.5 text-slate-300 hover:text-white"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* Scrollable Screen Viewport */}
        <main className="flex-1 min-h-0 overflow-y-auto p-3">
          {activeScreen === "dashboard" && (
            <DashboardScreen
              status={effectiveStatus}
              onRefresh={refreshStatus}
              onNavigate={setActiveScreen}
              onActionMessage={handleActionMessage}
              btcStatus={btcStatus}
              onRefreshBtc={refreshBtcStatus}
              trades={normalized.recentTrades}
              decisions={decisions}
              errors={errors}
              feedStatus={feedStatus}
              telegramEnabled={telegram.enabled}
            />
          )}

          {activeScreen === "engine" && (
            <EngineScreen
              status={effectiveStatus}
              onRefresh={refreshStatus}
              onActionMessage={handleActionMessage}
            />
          )}

          {activeScreen === "market" && (
            <MarketWatchScreen
              status={effectiveStatus}
              onRefresh={refreshStatus}
              onActionMessage={handleActionMessage}
            />
          )}

          {activeScreen === "signals" && (
            <SignalsScreen decisions={decisions} onReload={reloadDecisions} />
          )}

          {activeScreen === "positions" && (
            <PositionsScreen
              status={effectiveStatus}
              onRefresh={refreshStatus}
              onActionMessage={handleActionMessage}
            />
          )}

          {activeScreen === "history" && (
            <TradeHistoryScreen trades={normalized.recentTrades} onReload={reloadTrades} />
          )}

          {activeScreen === "risk" && (
            <RiskManagerScreen
              riskState={riskState}
              decisions={decisions}
              portfolioCapacity={effectiveStatus.engine.portfolio_capacity}
              onReload={reloadDecisions}
            />
          )}

          {activeScreen === "instruments" && (
            <InstrumentsScreen
              instrumentsConfig={instrumentsConfig}
              status={effectiveStatus}
            />
          )}

          {activeScreen === "configuration" && (
            <ConfigurationScreen onActionMessage={handleActionMessage} />
          )}

          {activeScreen === "mt5" && (
            <MT5ConnectionScreen
              status={effectiveStatus}
              onRefresh={refreshStatus}
              onActionMessage={handleActionMessage}
            />
          )}

          {activeScreen === "operations" && (
            <OperationsCentreScreen onActionMessage={handleActionMessage} />
          )}

          {activeScreen === "errors" && (
            <ErrorCentreScreen
              errors={errors}
              onReload={reloadErrors}
              onActionMessage={handleActionMessage}
            />
          )}

          {activeScreen === "logs" && (
            <LogsScreen
              logs={normalizeLogEntries(controlLogs)}
              onReload={reloadLogs}
              onActionMessage={handleActionMessage}
            />
          )}

          {activeScreen === "analytics" && (
            <AnalyticsScreen trades={normalized.recentTrades} />
          )}

          {activeScreen === "health" && (
            <SystemHealthScreen
              status={effectiveStatus}
              audits={audits}
              onReload={reloadAudits}
            />
          )}

          {activeScreen === "settings" && (
            <SettingsScreen
              status={effectiveStatus}
              onRefresh={refreshStatus}
              onActionMessage={handleActionMessage}
              onOpenDiagnostics={() => setIsDiagnosticsOpen(true)}
              onOpenInstitutionalEa={() => setIsPairingOpen(true)}
              onOpenTelegram={() => setIsTelegramOpen(true)}
            />
          )}
        </main>
      </div>

      {/* Existing Modal Dialogs */}
      <OnboardingWizard
        isOpen={isOnboardingOpen}
        onFinish={() => setIsOnboardingOpen(false)}
      />

      <MT5SetupWizard
        isOpen={isMT5WizardOpen}
        onClose={() => setIsMT5WizardOpen(false)}
      />

      <PairingModal
        isOpen={isPairingOpen}
        onClose={() => setIsPairingOpen(false)}
        pairing={pairing}
        onPairingUpdated={setPairing}
      />

      <TelegramPairingModal
        isOpen={isTelegramOpen}
        onClose={() => setIsTelegramOpen(false)}
        onStatusUpdated={async () => {
          const t = await IPC.getTelegramStatus();
          setTelegram(t);
        }}
      />

      <DiagnosticsModal
        isOpen={isDiagnosticsOpen}
        onClose={() => setIsDiagnosticsOpen(false)}
      />

      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
      />
    </div>
  );
};

export default App;
