import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertOctagon,
  BarChart3,
  CheckCircle2,
  Database,
  FileText,
  History,
  Layers,
  LayoutDashboard,
  Link2,
  Lock,
  PanelLeft,
  Radio,
  RefreshCw,
  Settings as SettingsIcon,
  Terminal,
  X,
} from "lucide-react";
import { DashboardScreen } from "./components/screens/CoreTradingScreens";
import {
  PositionsScreen,
  TradeHistoryScreen,
} from "./components/screens/ExecutionRiskScreens";
import {
  MT5ConnectionScreen,
  OperationsCentreScreen,
} from "./components/screens/OperationsSystemScreens";
import {
  AnalyticsScreen,
  LogsScreen,
  SettingsScreen,
  SystemHealthScreen,
} from "./components/screens/MonitoringSettingsScreens";
import { PairingModal } from "./components/PairingModal";
import { TelegramPairingModal } from "./components/TelegramPairingModal";
import { DiagnosticsModal } from "./components/DiagnosticsModal";

import {
  AuditLogRecord,
  ControlLogEntry,
  ControlStatusPayload,
  PairingStatus,
  ScreenId,
  TradeHistoryRecord,
} from "./types";
import { controlClient, IPC } from "./services/ipc";
import {
  buildNormalizedDashboardData,
  DataFeedStatus,
  normalizeLogEntries,
} from "./services/dashboardDataAdapter";
import { DESIGN_TOKENS } from "./styles/designTokens";
import { UI_COPY } from "./constants/uiCopy";

interface NavScreenItem {
  id: ScreenId;
  label: string;
  tooltip: string;
  badge?: string | number;
  icon: React.ComponentType<{ className?: string }>;
}

interface NavGroupSpec {
  group: "Monitor" | "Control" | "Diagnose";
  items: NavScreenItem[];
}

const VALID_SCREENS = new Set<ScreenId>([
  "dashboard",
  "positions",
  "history",
  "analytics",
  "mt5",
  "operations",
  "logs",
  "health",
  "settings",
]);

export const App: React.FC = () => {
  const [activeScreen, setActiveScreenState] = useState<ScreenId>("dashboard");
  const [feedStatus, setFeedStatus] = useState<DataFeedStatus>("LOADING");

  // Safe navigation: redirect any unknown/removed route to Dashboard
  const setActiveScreen = useCallback((screen: ScreenId | string) => {
    if (VALID_SCREENS.has(screen as ScreenId)) {
      setActiveScreenState(screen as ScreenId);
    } else {
      setActiveScreenState("dashboard");
    }
  }, []);

  // Supabase-Style Hover + Focus-Within Overlay Sidebar State
  const [isSidebarHovered, setIsSidebarHovered] = useState<boolean>(false);
  const [isSidebarFocused, setIsSidebarFocused] = useState<boolean>(false);
  const [isSidebarTouchPinned, setIsSidebarTouchPinned] = useState<boolean>(false);
  const collapseTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sidebarRef = useRef<HTMLElement | null>(null);

  const isSidebarExpanded = isSidebarHovered || isSidebarFocused || isSidebarTouchPinned;

  const handleSidebarMouseEnter = useCallback(() => {
    if (collapseTimerRef.current) {
      clearTimeout(collapseTimerRef.current);
      collapseTimerRef.current = null;
    }
    setIsSidebarHovered(true);
  }, []);

  const handleSidebarMouseLeave = useCallback(() => {
    if (collapseTimerRef.current) {
      clearTimeout(collapseTimerRef.current);
    }
    collapseTimerRef.current = setTimeout(() => {
      setIsSidebarHovered(false);
    }, DESIGN_TOKENS.sidebar.collapseDelayMs);
  }, []);

  const handleSidebarFocusIn = useCallback(() => {
    if (collapseTimerRef.current) {
      clearTimeout(collapseTimerRef.current);
      collapseTimerRef.current = null;
    }
    setIsSidebarFocused(true);
  }, []);

  const handleSidebarFocusOut = useCallback((e: React.FocusEvent<HTMLElement>) => {
    if (sidebarRef.current && !sidebarRef.current.contains(e.relatedTarget as Node)) {
      setIsSidebarFocused(false);
    }
  }, []);

  useEffect(() => {
    return () => {
      if (collapseTimerRef.current) clearTimeout(collapseTimerRef.current);
    };
  }, []);

  // Authoritative Control Service state (kept screens only)
  const [rawStatus, setRawStatus] = useState<ControlStatusPayload | null>(null);
  const [trades, setTrades] = useState<TradeHistoryRecord[]>([]);
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

  const [isPairingOpen, setIsPairingOpen] = useState<boolean>(false);
  const [isTelegramOpen, setIsTelegramOpen] = useState<boolean>(false);
  const [isDiagnosticsOpen, setIsDiagnosticsOpen] = useState<boolean>(false);

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

  const reloadTrades = useCallback(async () => {
    try {
      const res = await controlClient.getTradeHistory();
      setTrades(res.trades || []);
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

  // Initial load + SSE connection to /api/events + periodic polling backup
  useEffect(() => {
    refreshStatus();
    reloadTrades();
    reloadLogs();
    reloadAudits();

    IPC.getPairingStatus().then(setPairing).catch(() => {});

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
        const sseUrl = token
          ? `${baseUrl}/api/events?token=${encodeURIComponent(token)}`
          : `${baseUrl}/api/events`;
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
              setRawStatus((prev) => (prev ? { ...prev, mt5: parsed.payload } : prev));
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
  }, [refreshStatus, reloadTrades, reloadLogs, reloadAudits]);

  const normalized = useMemo(
    () => buildNormalizedDashboardData(rawStatus, trades),
    [rawStatus, trades]
  );

  const effectiveStatus = normalized.status;
  const openPosCount = effectiveStatus.mt5.positions.length;

  // 9 kept screens grouped cleanly under MONITOR / CONTROL / DIAGNOSE
  const navGroups: NavGroupSpec[] = useMemo(
    () => [
      {
        group: "Monitor",
        items: [
          { id: "dashboard", ...UI_COPY.nav.screens.dashboard, icon: LayoutDashboard, badge: "LIVE" },
          { id: "positions", ...UI_COPY.nav.screens.positions, icon: Layers, badge: openPosCount },
          { id: "history", ...UI_COPY.nav.screens.history, icon: History, badge: normalized.recentTrades.length },
          { id: "analytics", ...UI_COPY.nav.screens.analytics, icon: BarChart3 },
        ],
      },
      {
        group: "Control",
        items: [
          { id: "mt5", ...UI_COPY.nav.screens.mt5, icon: Link2 },
          { id: "operations", ...UI_COPY.nav.screens.operations, icon: Terminal },
        ],
      },
      {
        group: "Diagnose",
        items: [
          { id: "logs", ...UI_COPY.nav.screens.logs, icon: FileText },
          { id: "health", ...UI_COPY.nav.screens.health, icon: Database },
          { id: "settings", ...UI_COPY.nav.screens.settings, icon: SettingsIcon },
        ],
      },
    ],
    [openPosCount, normalized.recentTrades.length]
  );

  const isElectron = useMemo(() => IPC.isElectron(), []);
  const titlebarHeightPx = isElectron ? 36 : 0;

  return (
    <div
      style={{ "--iea-titlebar-h": `${titlebarHeightPx}px` } as React.CSSProperties}
      className="relative flex h-screen w-screen overflow-hidden iea-bg-atmosphere text-[#F4F7FF] antialiased font-sans select-none"
    >
      {/* Electron-Only Native Title Bar Drag Strip (36px) paired with Windows titleBarOverlay */}
      {isElectron && (
        <div
          data-testid="electron-titlebar-strip"
          style={{
            height: "36px",
            paddingRight: "max(144px, calc(100% - env(titlebar-area-width, 100%)))",
          }}
          className="iea-drag-region fixed top-0 left-0 right-0 z-50 bg-[#0A152B]/95 backdrop-blur-xl border-b border-[rgba(186,214,255,0.14)] flex items-center justify-between px-3"
        >
          <div className="flex items-center space-x-2 min-w-0">
            <div className="w-5 h-5 rounded-md bg-gradient-to-br from-[#B0F648]/30 via-[#2F497C]/50 to-[#112B42]/80 border border-[#B0F648]/45 flex items-center justify-center shrink-0">
              <Activity className="w-3 h-3 text-[#B0F648]" />
            </div>
            <span className="text-[11px] font-bold tracking-wide text-[#F4F7FF] truncate">
              {UI_COPY.brand.title}
            </span>
            <span className="text-[10px] font-mono text-[#B0F648] opacity-90">
              {UI_COPY.brand.subtitle}
            </span>
          </div>
          <span className="text-[10px] font-mono text-[#8496B8] hidden sm:inline">
            DEMO · LIVE_TRADING_ENABLED=false
          </span>
        </div>
      )}

      {/* Ambient Blurred Light Orbs (Deep Navy-to-Royal-Blue + Lime Sheen) */}
      <div aria-hidden="true" className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
        <div className="absolute -left-24 top-1/4 w-[420px] h-[420px] rounded-full bg-[#7196CB]/20 blur-[120px]" />
        <div className="absolute right-12 -top-20 w-[380px] h-[380px] rounded-full bg-[#B0F648]/10 blur-[130px]" />
        <div className="absolute left-1/3 -bottom-28 w-[520px] h-[420px] rounded-full bg-[#2F497C]/30 blur-[130px]" />
      </div>

      {/* =====================================================================
          SUPABASE-STYLE HOVER-EXPAND OVERLAY SIDEBAR (9 SCREENS, 3 GROUPS)
      ====================================================================== */}
      <aside
        ref={sidebarRef}
        aria-label="Primary Terminal Navigation"
        data-testid="supabase-hover-sidebar"
        data-expanded={isSidebarExpanded ? "true" : "false"}
        onMouseEnter={handleSidebarMouseEnter}
        onMouseLeave={handleSidebarMouseLeave}
        onFocusCapture={handleSidebarFocusIn}
        onBlurCapture={handleSidebarFocusOut}
        style={{
          top: `${titlebarHeightPx}px`,
          width: isSidebarExpanded
            ? `${DESIGN_TOKENS.sidebar.expandedWidthPx}px`
            : `${DESIGN_TOKENS.sidebar.collapsedWidthPx}px`,
        }}
        className="iea-no-drag fixed bottom-0 left-0 z-40 iea-sidebar-rail flex flex-col justify-between overflow-hidden"
      >
        {/* Top Brand Block + Navigation */}
        <div className="flex flex-col min-h-0 flex-1">
          <div className="h-14 px-3 border-b border-[rgba(186,214,255,0.12)] flex items-center justify-between shrink-0">
            <div className="flex items-center space-x-3 min-w-0">
              <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-[#B0F648]/25 via-[#2F497C]/50 to-[#112B42]/80 border border-[#B0F648]/45 shadow-[0_0_16px_rgba(176,246,72,0.22)] flex items-center justify-center shrink-0">
                <Activity className="w-4 h-4 text-[#B0F648]" />
              </div>

              <div
                className={`min-w-0 whitespace-nowrap transition-all duration-200 ease-out ${
                  isSidebarExpanded
                    ? "opacity-100 translate-x-0"
                    : "opacity-0 -translate-x-2 pointer-events-none w-0 overflow-hidden"
                }`}
              >
                <div className="text-xs font-bold tracking-tight text-[#F4F7FF] leading-none">
                  {UI_COPY.brand.title}
                </div>
                <div className="text-[10px] font-mono text-[#B0F648] mt-1">
                  {UI_COPY.brand.subtitle}
                </div>
              </div>
            </div>

            {isSidebarExpanded && (
              <button
                type="button"
                onClick={() => setIsSidebarTouchPinned((v) => !v)}
                aria-label={
                  isSidebarTouchPinned
                    ? "Unpin navigation sidebar"
                    : "Pin navigation sidebar open"
                }
                title={isSidebarTouchPinned ? "Unpin sidebar" : "Pin sidebar"}
                className={`p-1.5 rounded-lg text-xs transition shrink-0 ${
                  isSidebarTouchPinned
                    ? "bg-[#B0F648]/20 text-[#B0F648] border border-[#B0F648]/40"
                    : "text-[#8496B8] hover:text-[#F4F7FF] hover:bg-white/5"
                }`}
              >
                <PanelLeft className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          {/* Grouped Navigation Items (MONITOR / CONTROL / DIAGNOSE) */}
          <nav
            aria-label="Screen Groups"
            className="flex-1 px-2 py-4 space-y-5 overflow-y-auto overflow-x-hidden"
          >
            {navGroups.map((grp) => (
              <div key={grp.group} className="space-y-1.5">
                <div className="h-5 px-2.5 flex items-center">
                  {isSidebarExpanded ? (
                    <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#8496B8] whitespace-nowrap transition-opacity duration-200">
                      {UI_COPY.nav.groups[grp.group]}
                    </span>
                  ) : (
                    <span className="w-4 h-[1px] mx-auto bg-[rgba(186,214,255,0.18)] rounded-full" />
                  )}
                </div>

                {grp.items.map((item) => {
                  const Icon = item.icon;
                  const active = activeScreen === item.id;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={(e) => {
                        setActiveScreen(item.id);
                        if (!isSidebarTouchPinned) {
                          (e.currentTarget as HTMLButtonElement).blur();
                          setIsSidebarFocused(false);
                        }
                      }}
                      aria-current={active ? "page" : undefined}
                      aria-label={item.label}
                      title={`${item.label} — ${item.tooltip}`}
                      className={`group relative w-full h-10 flex items-center rounded-xl text-xs transition-all duration-200 ${
                        isSidebarExpanded ? "px-3 justify-between" : "px-0 justify-center"
                      } ${
                        active
                          ? "bg-gradient-to-r from-[#B0F648]/20 to-[#2F497C]/30 text-[#F4F7FF] font-semibold border border-[#B0F648]/40 shadow-[0_4px_16px_rgba(176,246,72,0.12)]"
                          : "text-[#B6C5E0] hover:text-[#F4F7FF] hover:bg-[rgba(47,73,124,0.32)] border border-transparent"
                      }`}
                    >
                      {active && (
                        <span
                          aria-hidden="true"
                          className="absolute left-0 top-2 bottom-2 w-[3px] rounded-r-full bg-[#B0F648] shadow-[0_0_10px_#B0F648]"
                        />
                      )}

                      <div
                        className={`flex items-center min-w-0 ${
                          isSidebarExpanded ? "space-x-2.5" : "justify-center"
                        }`}
                      >
                        <Icon
                          className={`w-4 h-4 shrink-0 transition-colors ${
                            active
                              ? "text-[#B0F648]"
                              : "text-[#8496B8] group-hover:text-[#F4F7FF]"
                          }`}
                        />
                        <span
                          className={`whitespace-nowrap truncate transition-all duration-200 ease-out ${
                            isSidebarExpanded
                              ? "opacity-100 translate-x-0"
                              : "opacity-0 -translate-x-2 pointer-events-none w-0 overflow-hidden"
                          }`}
                        >
                          {item.label}
                        </span>
                      </div>

                      {isSidebarExpanded && item.badge !== undefined && (
                        <span
                          className={`px-1.5 py-0.5 rounded-full text-[10px] font-mono font-bold whitespace-nowrap transition-opacity duration-150 ${
                            active
                              ? "bg-[#B0F648] text-[#081321]"
                              : "bg-[#192E58]/80 text-[#B6C5E0] border border-[rgba(186,214,255,0.14)]"
                          }`}
                        >
                          {item.badge}
                        </span>
                      )}

                      {!isSidebarExpanded && item.badge !== undefined && (
                        <span
                          aria-hidden="true"
                          className="absolute top-2 right-2 w-1.5 h-1.5 rounded-full bg-[#B0F648]"
                        />
                      )}
                    </button>
                  );
                })}
              </div>
            ))}
          </nav>
        </div>

        {/* Sidebar Footer: Hard DEMO Safety Lock Indicator */}
        <div className="p-3 border-t border-[rgba(186,214,255,0.12)] bg-[#071020]/70 shrink-0">
          {isSidebarExpanded ? (
            <div className="space-y-1.5 whitespace-nowrap">
              <div className="flex items-center justify-between text-[10px] font-mono">
                <span
                  className="inline-flex items-center space-x-1 text-[#B0F648] font-bold"
                  title={UI_COPY.brand.demoLockTooltip}
                >
                  <Lock className="w-3 h-3" />
                  <span>{UI_COPY.brand.demoLockShort}</span>
                </span>
                <span className="text-[#8496B8]">127.0.0.1:8765</span>
              </div>
              <div className="text-[10px] text-[#B6C5E0] flex items-center justify-between">
                <span>{feedStatus}</span>
                <div className="flex items-center space-x-2">
                  <button
                    type="button"
                    onClick={() => setActiveScreen("settings")}
                    title="Open Short-Form Glossary (Settings > Glossary)"
                    className="text-[#5EEAD4] hover:underline font-mono font-bold"
                  >
                    ? Glossary
                  </button>
                  <button
                    type="button"
                    onClick={() => refreshStatus()}
                    aria-label="Refresh terminal telemetry"
                    className="text-[#B0F648] hover:text-[#C2F076] inline-flex items-center space-x-1 font-medium"
                  >
                    <RefreshCw className="w-3 h-3" />
                    <span>Sync</span>
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div
              className="flex justify-center py-1"
              title="DEMO Lock Active (LIVE_TRADING_ENABLED=false)"
            >
              <div className="w-7 h-7 rounded-lg bg-[#B0F648]/15 border border-[#B0F648]/35 flex items-center justify-center">
                <Lock className="w-3.5 h-3.5 text-[#B0F648]" />
              </div>
            </div>
          )}
        </div>
      </aside>

      {/* =====================================================================
          MAIN CONTENT AREA
      ====================================================================== */}
      <div
        style={{
          paddingLeft: `${DESIGN_TOKENS.sidebar.collapsedWidthPx}px`,
          paddingTop: `${titlebarHeightPx}px`,
        }}
        className="iea-no-drag relative z-10 flex-1 min-w-0 flex flex-col h-screen overflow-hidden"
      >
        {/* Consistent Glass Navigation Header Bar (when viewing any sub-screen) */}
        {activeScreen !== "dashboard" && (
          <header className="h-14 px-5 bg-[#0A152B]/75 backdrop-blur-xl border-b border-[rgba(186,214,255,0.14)] flex items-center justify-between shrink-0">
            <div className="flex items-center space-x-3.5">
              <button
                type="button"
                onClick={() => setActiveScreen("dashboard")}
                className="iea-pill-control px-3.5 py-1.5 text-xs text-[#F4F7FF] font-medium inline-flex items-center space-x-1.5"
              >
                <span>← Dashboard</span>
              </button>
              <h1 className="text-lg font-light tracking-tight text-[#F4F7FF]">
                {navGroups.flatMap((g) => g.items).find((i) => i.id === activeScreen)?.label ||
                  activeScreen}
              </h1>
            </div>

            <div className="flex items-center space-x-2.5 text-xs font-mono">
              <span className="px-3 py-1 rounded-full bg-[#B0F648]/15 border border-[#B0F648]/40 text-[#B0F648] font-bold">
                {UI_COPY.brand.demoLockChip}
              </span>
              <span className="iea-pill-control px-3 py-1 text-[#B6C5E0]">
                MT5 {normalized.maskedAccount}
              </span>
              <span className="iea-pill-control px-3 py-1 text-[#5EEAD4] inline-flex items-center space-x-1.5">
                <Radio className="w-3 h-3 text-[#B0F648]" />
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
            className={`mx-4 mt-2.5 px-4 py-2.5 rounded-2xl border backdrop-blur-xl text-xs flex items-center justify-between shrink-0 shadow-lg ${
              actionToast.isError
                ? "bg-[#FF5A6E]/20 border-[#FF5A6E]/50 text-[#F4F7FF]"
                : "bg-[#B0F648]/18 border-[#B0F648]/45 text-[#F4F7FF]"
            }`}
          >
            <div className="flex items-center space-x-2.5">
              {actionToast.isError ? (
                <AlertOctagon className="w-4 h-4 text-[#FF5A6E] shrink-0" />
              ) : (
                <CheckCircle2 className="w-4 h-4 text-[#B0F648] shrink-0" />
              )}
              <span className="font-medium">{actionToast.message}</span>
            </div>
            <button
              type="button"
              onClick={() => setActionToast(null)}
              aria-label="Dismiss notification"
              className="p-1 rounded-lg text-[#B6C5E0] hover:text-white hover:bg-white/10"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* Scrollable Screen Viewport */}
        <main className="flex-1 min-h-0 overflow-y-auto p-3.5 md:p-4">
          <div className="max-w-[1920px] mx-auto">
            {activeScreen === "dashboard" && (
              <DashboardScreen
                status={effectiveStatus}
                onRefresh={refreshStatus}
                onNavigate={setActiveScreen}
                onActionMessage={handleActionMessage}
                trades={normalized.recentTrades}
                feedStatus={feedStatus}
              />
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

            {activeScreen === "analytics" && (
              <AnalyticsScreen trades={normalized.recentTrades} />
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

            {activeScreen === "logs" && (
              <LogsScreen
                logs={normalizeLogEntries(controlLogs)}
                onReload={reloadLogs}
                onActionMessage={handleActionMessage}
              />
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
                onOpenDiagnostics={() => setIsDiagnosticsOpen(true)}
                onOpenInstitutionalEa={() => setIsPairingOpen(true)}
                onOpenTelegram={() => setIsTelegramOpen(true)}
              />
            )}
          </div>
        </main>
      </div>

      {/* Existing Modal Dialogs */}
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
          await IPC.getTelegramStatus().catch(() => {});
        }}
      />

      <DiagnosticsModal
        isOpen={isDiagnosticsOpen}
        onClose={() => setIsDiagnosticsOpen(false)}
      />
    </div>
  );
};

export default App;
