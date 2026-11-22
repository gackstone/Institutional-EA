import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertOctagon,
  BarChart3,
  Bell,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
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
  ShieldCheck,
  SlidersHorizontal,
  Terminal,
  X,
  Zap,
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
import {
  AlertCentreScreen,
  SignalsGridScreen,
} from "./components/screens/SignalsAlertsScreens";
import { PairingModal } from "./components/PairingModal";
import { TelegramPairingModal } from "./components/TelegramPairingModal";
import { DiagnosticsModal } from "./components/DiagnosticsModal";
import { TradeReplayModal } from "./components/TradeReplayModal";

import {
  AuditLogRecord,
  BalanceSnapshotRecord,
  ControlLogEntry,
  ControlServiceStatus,
  ControlStatusPayload,
  PairingStatus,
  ScreenId,
  TradeHistoryRecord,
} from "./types";
import { controlClient, IPC } from "./services/ipc";
import {
  buildNormalizedDashboardData,
  ChartSymbol,
  DataFeedStatus,
  normalizeLogEntries,
} from "./services/dashboardDataAdapter";
import { DESIGN_TOKENS } from "./styles/designTokens";
import { UI_COPY } from "./constants/uiCopy";
import { readVersionedState, writeVersionedState } from "./utils/persistedState";

type SidebarGroupKey = "Monitor" | "Control" | "Diagnose";

interface NavScreenItem {
  id: ScreenId;
  label: string;
  tooltip: string;
  badge?: number;
  badgeTone?: "mint" | "peach";
  icon: React.ComponentType<{ className?: string }>;
}

interface NavGroupSpec {
  group: SidebarGroupKey;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  items: NavScreenItem[];
}

type OpenGroupsMap = Record<SidebarGroupKey, boolean>;

const SIDEBAR_GROUPS_STORAGE_KEY = "iea_sidebar_groups_v1";
const DEFAULT_OPEN_GROUPS: OpenGroupsMap = {
  Monitor: true,
  Control: true,
  Diagnose: true,
};

function isValidOpenGroups(v: unknown): v is OpenGroupsMap {
  if (!v || typeof v !== "object") return false;
  const o = v as Record<string, unknown>;
  return (
    typeof o.Monitor === "boolean" &&
    typeof o.Control === "boolean" &&
    typeof o.Diagnose === "boolean"
  );
}

const VALID_SCREENS = new Set<ScreenId>([
  "dashboard",
  "positions",
  "signals",
  "alerts",
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
  const [chartJumpSymbol, setChartJumpSymbol] = useState<ChartSymbol>("XAUUSD");
  const [replayTicket, setReplayTicket] = useState<number | null>(null);
  const [balanceSnapshots, setBalanceSnapshots] = useState<BalanceSnapshotRecord[]>([]);
  const [isMobileViewport, setIsMobileViewport] = useState<boolean>(() =>
    typeof window !== "undefined" ? window.innerWidth < 768 : false
  );

  // Persisted collapsible sidebar group open/close state (all open by default)
  const [openGroups, setOpenGroups] = useState<OpenGroupsMap>(
    () =>
      readVersionedState<OpenGroupsMap>({
        key: SIDEBAR_GROUPS_STORAGE_KEY,
        defaultValue: DEFAULT_OPEN_GROUPS,
        validate: isValidOpenGroups,
      }).value
  );

  useEffect(() => {
    writeVersionedState(SIDEBAR_GROUPS_STORAGE_KEY, openGroups);
  }, [openGroups]);

  useEffect(() => {
    const onResize = () => setIsMobileViewport(window.innerWidth < 768);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  // Disarm main-process startup watchdog once React shell mounts + install global error handlers
  useEffect(() => {
    try {
      (window as any).electronAPI?.notifyAppReady?.();
    } catch {
      // ignore in browser mode
    }

    const onError = (event: ErrorEvent) => {
      const msg = String(event?.message || "Unexpected runtime error").slice(0, 140);
      try {
        (window as any).electronAPI?.reportRendererError?.({
          source: "window.error",
          message: msg,
        });
      } catch {
        // ignore
      }
      setActionToast({ message: `Notice: ${msg}`, isError: true, ts: Date.now() });
    };

    const onRejection = (event: PromiseRejectionEvent) => {
      const reason =
        event?.reason instanceof Error
          ? event.reason.message
          : String(event?.reason || "Unhandled async error");
      const msg = reason.slice(0, 140);
      try {
        (window as any).electronAPI?.reportRendererError?.({
          source: "window.unhandledrejection",
          message: msg,
        });
      } catch {
        // ignore
      }
    };

    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onRejection);
    return () => {
      window.removeEventListener("error", onError);
      window.removeEventListener("unhandledrejection", onRejection);
    };
  }, []);

  // Safe navigation: redirect any unknown/removed route to Dashboard
  const setActiveScreen = useCallback((screen: ScreenId | string) => {
    if (VALID_SCREENS.has(screen as ScreenId)) {
      setActiveScreenState(screen as ScreenId);
    } else {
      setActiveScreenState("dashboard");
    }
  }, []);

  // Hover + Focus-Within Overlay Sidebar State (never shifts main content)
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

  // Authoritative Control Service state
  const [rawStatus, setRawStatus] = useState<ControlStatusPayload | null>(null);
  const [serviceStatus, setServiceStatus] = useState<ControlServiceStatus | null>(null);
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
    setActionToast((prev) => {
      if (prev && prev.message === message && prev.isError === isError) {
        return prev;
      }
      return { message, isError, ts: Date.now() };
    });
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
      setFeedStatus((prev) => (prev === "LIVE_SSE" ? "LIVE_SSE" : "POLLING"));
    }
  }, []);

  const reloadTrades = useCallback(async () => {
    try {
      const res = await controlClient.getAnalyticsEquity();
      setTrades(res.trades || []);
      setBalanceSnapshots(res.snapshots || []);
    } catch {
      try {
        const res = await controlClient.getTradeHistory();
        setTrades(res.trades || []);
      } catch {
        setTrades([]);
      }
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

  const handleReconnectService = useCallback(async () => {
    handleActionMessage("Reconnecting Control Service...", false);
    try {
      const next = await IPC.reconnectControlService();
      setServiceStatus(next);
      if (next.status === "ONLINE") {
        setActionToast(null);
        await refreshStatus();
      } else {
        handleActionMessage(next.lastError || "Control Service still starting...", true);
      }
    } catch (e: any) {
      handleActionMessage(`Reconnect failed: ${e?.message || e}`, true);
    }
  }, [handleActionMessage, refreshStatus]);

  useEffect(() => {
    IPC.getControlServiceStatus().then(setServiceStatus).catch(() => {});
    const unsub = IPC.onControlServiceStatus((next) => {
      setServiceStatus((prev) => {
        if (prev?.status !== "ONLINE" && next.status === "ONLINE") {
          setActionToast((toast) => (toast && /offline|retrying/i.test(toast.message) ? null : toast));
          refreshStatus();
        }
        return next;
      });
    });
    return () => unsub();
  }, [refreshStatus]);

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
              const snap = parsed.payload;
              if (snap && typeof snap === "object" && snap.engine && snap.mt5) {
                setRawStatus(snap);
              } else if (snap && typeof snap === "object") {
                setRawStatus((prev) =>
                  prev ? { ...prev, engine: { ...prev.engine, ...snap } } : prev
                );
              }
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
  const recentTradeCount = normalized.recentTrades.length;

  // Existing error/warning count from controlLogs for peach attention badge
  const warningErrorLogCount = useMemo(
    () =>
      controlLogs.filter((l) => {
        const sev = String(l.severity || "").toUpperCase();
        return sev === "ERROR" || sev === "CRITICAL" || sev === "WARN" || sev === "WARNING";
      }).length,
    [controlLogs]
  );

  // IMAGE 2 Sidebar Structure: Dashboard top-level, collapsible MONITOR / CONTROL / DIAGNOSE groups, Settings at bottom
  const dashboardItem: NavScreenItem = useMemo(
    () => ({
      id: "dashboard",
      ...UI_COPY.nav.screens.dashboard,
      icon: LayoutDashboard,
    }),
    []
  );

  const settingsItem: NavScreenItem = useMemo(
    () => ({
      id: "settings",
      ...UI_COPY.nav.screens.settings,
      icon: SettingsIcon,
    }),
    []
  );

  const navGroups: NavGroupSpec[] = useMemo(
    () => [
      {
        group: "Monitor",
        label: UI_COPY.nav.groups.Monitor,
        icon: Activity,
        items: [
          {
            id: "positions",
            ...UI_COPY.nav.screens.positions,
            icon: Layers,
            badge: openPosCount > 0 ? openPosCount : undefined,
            badgeTone: "mint",
          },
          { id: "signals", ...UI_COPY.nav.screens.signals, icon: Zap },
          { id: "alerts", ...UI_COPY.nav.screens.alerts, icon: Bell },
          {
            id: "history",
            ...UI_COPY.nav.screens.history,
            icon: History,
            badge: recentTradeCount > 0 ? recentTradeCount : undefined,
            badgeTone: "mint",
          },
          { id: "analytics", ...UI_COPY.nav.screens.analytics, icon: BarChart3 },
        ],
      },
      {
        group: "Control",
        label: UI_COPY.nav.groups.Control,
        icon: SlidersHorizontal,
        items: [
          { id: "mt5", ...UI_COPY.nav.screens.mt5, icon: Link2 },
          { id: "operations", ...UI_COPY.nav.screens.operations, icon: Terminal },
        ],
      },
      {
        group: "Diagnose",
        label: UI_COPY.nav.groups.Diagnose,
        icon: ShieldCheck,
        items: [
          {
            id: "logs",
            ...UI_COPY.nav.screens.logs,
            icon: FileText,
            badge: warningErrorLogCount > 0 ? warningErrorLogCount : undefined,
            badgeTone: "peach",
          },
          { id: "health", ...UI_COPY.nav.screens.health, icon: Database },
        ],
      },
    ],
    [openPosCount, recentTradeCount, warningErrorLogCount]
  );

  // Auto-open the group containing the active route
  useEffect(() => {
    const parentGroup = navGroups.find((g) => g.items.some((i) => i.id === activeScreen));
    if (parentGroup) {
      setOpenGroups((prev) =>
        prev[parentGroup.group] ? prev : { ...prev, [parentGroup.group]: true }
      );
    }
  }, [activeScreen, navGroups]);

  const toggleGroup = useCallback((group: SidebarGroupKey) => {
    setOpenGroups((prev) => ({ ...prev, [group]: !prev[group] }));
  }, []);

  const allScreenItems = useMemo(
    () => [dashboardItem, ...navGroups.flatMap((g) => g.items), settingsItem],
    [dashboardItem, navGroups, settingsItem]
  );

  const isElectron = useMemo(() => IPC.isElectron(), []);
  const titlebarHeightPx = isElectron ? 36 : 0;
  const sidebarInsetPx = 8;
  const mainLeftOffsetPx = DESIGN_TOKENS.sidebar.collapsedWidthPx + sidebarInsetPx * 2;

  const handleJumpToChart = useCallback(
    (sym: ChartSymbol) => {
      setChartJumpSymbol(sym);
      setActiveScreen("dashboard");
    },
    [setActiveScreen]
  );

  const handleSelectNavItem = useCallback(
    (id: ScreenId, e: React.MouseEvent<HTMLButtonElement>) => {
      setActiveScreen(id);
      if (!isSidebarTouchPinned) {
        e.currentTarget.blur();
        setIsSidebarFocused(false);
      }
    },
    [setActiveScreen, isSidebarTouchPinned]
  );

  const renderBadgePill = (badge?: number, tone: "mint" | "peach" = "mint") => {
    if (badge === undefined) return null;
    return (
      <span
        data-testid={`sidebar-badge-${tone}`}
        className={`min-w-[24px] h-[22px] px-1.5 rounded-[7px] text-[11px] font-mono font-bold tabular-nums inline-flex items-center justify-center shrink-0 ${
          tone === "peach"
            ? "bg-[#F5C59F] text-[#1F140B]"
            : "bg-[#A9ECDA] text-[#0E1A16]"
        }`}
      >
        {badge}
      </span>
    );
  };

  const renderCollapsedBadgeDot = (badge?: number, tone: "mint" | "peach" = "mint") => {
    if (badge === undefined) return null;
    return (
      <span
        aria-hidden="true"
        className={`absolute top-1.5 right-1.5 w-2 h-2 rounded-full ring-2 ring-[#17181A] ${
          tone === "peach" ? "bg-[#F5C59F]" : "bg-[#A9ECDA]"
        }`}
      />
    );
  };

  return (
    <div
      style={{ "--iea-titlebar-h": `${titlebarHeightPx}px` } as React.CSSProperties}
      className="relative flex h-screen w-screen overflow-hidden iea-shell-bg text-[#F5F5F2] antialiased font-sans select-none"
    >
      {/* Electron-Only Native Title Bar Drag Strip (36px) paired with Windows titleBarOverlay */}
      {isElectron && (
        <div
          data-testid="electron-titlebar-strip"
          style={{
            height: "36px",
            paddingRight: "max(144px, calc(100% - env(titlebar-area-width, 100%)))",
          }}
          className="iea-drag-region fixed top-0 left-0 right-0 z-50 bg-[#12110F] border-b border-[rgba(255,255,253,0.06)] flex items-center justify-between px-3.5"
        >
          <div className="flex items-center space-x-2 min-w-0">
            <div className="w-5 h-5 rounded-[6px] bg-[#F8F8FA] flex items-center justify-center shrink-0">
              <span className="w-2.5 h-2.5 rounded-full border-[2.5px] border-[#191D20] flex items-center justify-center">
                <span className="w-1 h-1 rounded-full bg-[#191D20]" />
              </span>
            </div>
            <span className="text-[11px] font-semibold tracking-tight text-[#F5F5F2] truncate">
              {UI_COPY.brand.title}
            </span>
            <span className="text-[10px] font-mono text-[#8A8986]">
              {UI_COPY.brand.subtitle}
            </span>
          </div>
          <span className="text-[10px] font-mono text-[#8A8986] hidden sm:inline">
            DEMO · LIVE_TRADING_ENABLED=false
          </span>
        </div>
      )}

      {/* =====================================================================
          IMAGE 2 HOVER-EXPAND OVERLAY SIDEBAR (11 SCREENS, COLLAPSIBLE GROUPS)
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
          top: `${titlebarHeightPx + sidebarInsetPx}px`,
          bottom: `${sidebarInsetPx}px`,
          left: `${sidebarInsetPx}px`,
          width: isSidebarExpanded
            ? `${DESIGN_TOKENS.sidebar.expandedWidthPx}px`
            : `${DESIGN_TOKENS.sidebar.collapsedWidthPx}px`,
        }}
        className="iea-no-drag hidden md:flex fixed z-40 iea-sidebar-rail flex-col justify-between overflow-hidden"
      >
        {/* Top Brand Block + Navigation */}
        <div className="flex flex-col min-h-0 flex-1">
          {/* Brand Logo Tile (White Rounded-Square Mark per IMAGE 2) */}
          <div className="h-[72px] px-4 flex items-center justify-between gap-2 shrink-0">
            <div className="flex items-center space-x-3 min-w-0 flex-1">
              <div
                className="w-11 h-11 rounded-[13px] bg-[#F8F8FA] shadow-xs flex items-center justify-center shrink-0"
                aria-hidden="true"
              >
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                  <rect x="4" y="4" width="16" height="16" rx="6" fill="#191D20" />
                  <circle cx="12" cy="12" r="3" fill="#F8F8FA" />
                </svg>
              </div>

              <div
                className={`min-w-0 flex-1 whitespace-nowrap transition-all duration-200 ease-out ${
                  isSidebarExpanded
                    ? "opacity-100 translate-x-0"
                    : "opacity-0 -translate-x-2 pointer-events-none w-0 overflow-hidden"
                }`}
              >
                <div className="text-[12px] font-semibold tracking-tight text-white leading-tight truncate">
                  {UI_COPY.brand.title}
                </div>
                <div className="text-[10px] font-mono text-[#9CA1A6] mt-0.5 truncate">
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
                    ? "bg-[#272A2F] text-white border border-white/10"
                    : "text-[#9CA1A6] hover:text-white hover:bg-white/5"
                }`}
              >
                <PanelLeft className="w-4 h-4" />
              </button>
            )}
          </div>

          {/* Navigation Body */}
          <nav
            aria-label="Screen Navigation"
            className="flex-1 px-3 py-2 overflow-y-auto overflow-x-hidden space-y-1.5"
          >
            {/* Top-Level: Dashboard */}
            {(() => {
              const Icon = dashboardItem.icon;
              const active = activeScreen === dashboardItem.id;
              return (
                <button
                  type="button"
                  onClick={(e) => handleSelectNavItem(dashboardItem.id, e)}
                  aria-current={active ? "page" : undefined}
                  aria-label={dashboardItem.label}
                  title={`${dashboardItem.label} — ${dashboardItem.tooltip}`}
                  className={`group relative w-full flex items-center rounded-[12px] transition-all duration-200 ${
                    isSidebarExpanded
                      ? "h-12 px-3.5 justify-between"
                      : "h-12 justify-center"
                  } ${
                    active
                      ? isSidebarExpanded
                        ? "bg-[#272A2F] text-white font-semibold border border-white/[0.06]"
                        : "text-white"
                      : "text-[#9CA1A6] hover:text-white hover:bg-white/[0.04] border border-transparent"
                  }`}
                >
                  {isSidebarExpanded ? (
                    <div className="flex items-center space-x-3 min-w-0">
                      <Icon
                        className={`w-5 h-5 shrink-0 transition-colors ${
                          active ? "text-white" : "text-[#9CA1A6] group-hover:text-white"
                        }`}
                      />
                      <span className="text-[14px] whitespace-nowrap truncate">
                        {dashboardItem.label}
                      </span>
                    </div>
                  ) : (
                    <div
                      className={`w-11 h-11 rounded-[12px] flex items-center justify-center transition-colors ${
                        active
                          ? "bg-[#303135] text-white"
                          : "text-[#9CA1A6] group-hover:text-white group-hover:bg-white/[0.05]"
                      }`}
                    >
                      <Icon className="w-5 h-5" />
                    </div>
                  )}
                </button>
              );
            })()}

            {/* Collapsible Groups: MONITOR, CONTROL, DIAGNOSE */}
            {navGroups.map((grp) => {
              const GroupIcon = grp.icon;
              const isOpen = openGroups[grp.group];
              const hasActiveChild = grp.items.some((i) => i.id === activeScreen);

              if (!isSidebarExpanded) {
                // Collapsed Rail: Continuous icon list with subtle divider between groups
                return (
                  <div key={grp.group} className="pt-1.5 space-y-1">
                    <div className="w-6 h-px mx-auto bg-white/[0.08] mb-2" aria-hidden="true" />
                    {grp.items.map((item) => {
                      const Icon = item.icon;
                      const active = activeScreen === item.id;
                      return (
                        <button
                          key={item.id}
                          type="button"
                          onClick={(e) => handleSelectNavItem(item.id, e)}
                          aria-current={active ? "page" : undefined}
                          aria-label={item.label}
                          title={`${item.label} — ${item.tooltip}`}
                          className="group relative w-full h-11 flex items-center justify-center rounded-[12px] transition"
                        >
                          <div
                            className={`relative w-11 h-11 rounded-[12px] flex items-center justify-center transition-colors ${
                              active
                                ? "bg-[#303135] text-white"
                                : "text-[#9CA1A6] group-hover:text-white group-hover:bg-white/[0.05]"
                            }`}
                          >
                            <Icon className="w-5 h-5" />
                            {renderCollapsedBadgeDot(item.badge, item.badgeTone)}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                );
              }

              // Expanded State: Collapsible group header + tree-indented children (IMAGE 2)
              return (
                <div key={grp.group} className="pt-1">
                  <button
                    type="button"
                    data-testid={`sidebar-group-${grp.group.toLowerCase()}`}
                    aria-expanded={isOpen}
                    onClick={() => toggleGroup(grp.group)}
                    className={`w-full h-12 px-3.5 rounded-[12px] flex items-center justify-between transition-all duration-200 border ${
                      isOpen || hasActiveChild
                        ? "bg-[#272A2F] text-white font-semibold border-white/[0.06]"
                        : "text-[#9CA1A6] hover:text-white hover:bg-white/[0.04] font-medium border-transparent"
                    }`}
                  >
                    <div className="flex items-center space-x-3 min-w-0">
                      <GroupIcon
                        className={`w-5 h-5 shrink-0 ${
                          isOpen || hasActiveChild ? "text-white" : "text-[#9CA1A6]"
                        }`}
                      />
                      <span className="text-[14px] whitespace-nowrap truncate">{grp.label}</span>
                    </div>
                    <ChevronDown
                      className={`w-4 h-4 shrink-0 transition-transform duration-200 ${
                        isOpen ? "rotate-180 text-white" : "text-[#9CA1A6]"
                      }`}
                    />
                  </button>

                  {/* Smooth Collapsible Tree Children */}
                  <div
                    className={`grid transition-[grid-template-rows,opacity] duration-200 ease-out ${
                      isOpen ? "grid-rows-[1fr] opacity-100 mt-1" : "grid-rows-[0fr] opacity-0 pointer-events-none"
                    }`}
                  >
                    <div className="overflow-hidden min-h-0">
                      <div className={`iea-tree-children space-y-0.5 ${isOpen ? "py-0.5" : "py-0"}`}>
                        {grp.items.map((item) => {
                          const active = activeScreen === item.id;
                          return (
                            <div key={item.id} className="iea-tree-child-row">
                              <button
                                type="button"
                                onClick={(e) => handleSelectNavItem(item.id, e)}
                                aria-current={active ? "page" : undefined}
                                aria-label={item.label}
                                title={`${item.label} — ${item.tooltip}`}
                                className={`w-full h-10 px-3 rounded-[10px] flex items-center justify-between text-[13px] transition-all duration-150 ${
                                  active
                                    ? "bg-[#272A2F] text-white font-medium border border-white/[0.06]"
                                    : "text-[#9CA1A6] hover:text-white hover:bg-white/[0.04] font-normal border border-transparent"
                                }`}
                              >
                                <span className="whitespace-nowrap truncate">{item.label}</span>
                                <div className="flex items-center space-x-1.5 shrink-0">
                                  {renderBadgePill(item.badge, item.badgeTone)}
                                  {active && <ChevronRight className="w-4 h-4 text-white" />}
                                </div>
                              </button>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}

            {/* Bottom Standalone Item: Settings */}
            <div className="pt-1.5">
              {!isSidebarExpanded && (
                <div className="w-6 h-px mx-auto bg-white/[0.08] mb-2" aria-hidden="true" />
              )}
              {(() => {
                const Icon = settingsItem.icon;
                const active = activeScreen === settingsItem.id;
                return (
                  <button
                    type="button"
                    onClick={(e) => handleSelectNavItem(settingsItem.id, e)}
                    aria-current={active ? "page" : undefined}
                    aria-label={settingsItem.label}
                    title={`${settingsItem.label} — ${settingsItem.tooltip}`}
                    className={`group relative w-full flex items-center rounded-[12px] transition-all duration-200 ${
                      isSidebarExpanded
                        ? "h-12 px-3.5 justify-between"
                        : "h-11 justify-center"
                    } ${
                      active
                        ? isSidebarExpanded
                          ? "bg-[#272A2F] text-white font-semibold border border-white/[0.06]"
                          : "text-white"
                        : "text-[#9CA1A6] hover:text-white hover:bg-white/[0.04] border border-transparent"
                    }`}
                  >
                    {isSidebarExpanded ? (
                      <div className="flex items-center space-x-3 min-w-0">
                        <Icon
                          className={`w-5 h-5 shrink-0 ${
                            active ? "text-white" : "text-[#9CA1A6] group-hover:text-white"
                          }`}
                        />
                        <span className="text-[14px] whitespace-nowrap truncate">
                          {settingsItem.label}
                        </span>
                      </div>
                    ) : (
                      <div
                        className={`w-11 h-11 rounded-[12px] flex items-center justify-center transition-colors ${
                          active
                            ? "bg-[#303135] text-white"
                            : "text-[#9CA1A6] group-hover:text-white group-hover:bg-white/[0.05]"
                        }`}
                      >
                        <Icon className="w-5 h-5" />
                      </div>
                    )}
                  </button>
                );
              })()}
            </div>
          </nav>
        </div>

        {/* Sidebar Footer: Hard DEMO Safety Lock Indicator */}
        <div className="p-3 border-t border-white/[0.07] shrink-0">
          {isSidebarExpanded ? (
            <div className="space-y-2 whitespace-nowrap px-1">
              <div className="flex items-center justify-between text-[11px] font-mono">
                <span
                  className="inline-flex items-center space-x-1.5 text-[#6EE7B7] font-semibold"
                  title={UI_COPY.brand.demoLockTooltip}
                >
                  <Lock className="w-3.5 h-3.5" />
                  <span>{UI_COPY.brand.demoLockShort}</span>
                </span>
                <span className="text-[#9CA1A6] text-[10px]">
                  {serviceStatus ? `${serviceStatus.host}:${serviceStatus.port}` : "127.0.0.1:8765"}
                </span>
              </div>
              <div className="text-[11px] text-[#9CA1A6] flex items-center justify-between">
                <span className="font-mono text-[10px]">{feedStatus}</span>
                <div className="flex items-center space-x-2.5">
                  <button
                    type="button"
                    onClick={() => setActiveScreen("settings")}
                    title="Open Short-Form Glossary (Settings > Glossary)"
                    className="text-[#9CA1A6] hover:text-white font-mono text-[10px] transition"
                  >
                    ? Glossary
                  </button>
                  <button
                    type="button"
                    onClick={() => refreshStatus()}
                    aria-label="Refresh terminal telemetry"
                    className="text-white/90 hover:text-white inline-flex items-center space-x-1 text-[11px] font-medium transition"
                  >
                    <RefreshCw className="w-3 h-3" />
                    <span>Sync</span>
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div
              className="flex justify-center py-0.5"
              title="DEMO Lock Active (LIVE_TRADING_ENABLED=false)"
            >
              <div className="w-10 h-10 rounded-[12px] bg-[#272A2F] border border-white/[0.06] flex items-center justify-center">
                <Lock className="w-4 h-4 text-[#6EE7B7]" />
              </div>
            </div>
          )}
        </div>
      </aside>

      {/* =====================================================================
          MAIN CONTENT AREA — IMAGE 1 RAISED ROUNDED PANEL
      ====================================================================== */}
      <div
        style={{
          paddingLeft: isMobileViewport ? "8px" : `${mainLeftOffsetPx}px`,
          paddingTop: `${titlebarHeightPx + 8}px`,
          paddingRight: "8px",
          paddingBottom: "8px",
        }}
        className="iea-no-drag relative z-10 flex-1 min-w-0 flex flex-col h-screen overflow-hidden"
      >
        <div className="iea-main-panel flex-1 min-h-0 flex flex-col overflow-hidden">
          {/* Consistent Neutral Navigation Header Bar (when viewing any sub-screen) */}
          {activeScreen !== "dashboard" && (
            <header className="h-14 px-6 border-b border-[rgba(255,255,253,0.07)] flex items-center justify-between shrink-0">
              <div className="flex items-center space-x-3.5">
                <button
                  type="button"
                  onClick={() => setActiveScreen("dashboard")}
                  className="iea-pill-control px-3.5 py-1.5 text-xs font-medium inline-flex items-center space-x-1.5"
                >
                  <span>← Dashboard</span>
                </button>
                <h1 className="text-[18px] font-semibold tracking-tight text-[#F5F5F2]">
                  {allScreenItems.find((i) => i.id === activeScreen)?.label || activeScreen}
                </h1>
              </div>

              <div className="flex items-center space-x-2 text-xs font-mono">
                <span className="px-3 py-1 rounded-full bg-[#36B37E]/15 border border-[#6EE7B7]/30 text-[#6EE7B7] font-semibold">
                  {UI_COPY.brand.demoLockChip}
                </span>
                <span className="iea-pill-control px-3 py-1 text-[#B4B3B0]">
                  MT5 {normalized.maskedAccount}
                </span>
                <span className="iea-pill-control px-3 py-1 text-[#5EC2C6] inline-flex items-center space-x-1.5">
                  <Radio className="w-3 h-3 text-[#6EE7B7]" />
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
              className={`mx-6 mt-4 px-4 py-2.5 rounded-2xl border text-xs flex items-center justify-between shrink-0 ${
                actionToast.isError
                  ? "bg-[#D94854]/15 border-[#F07178]/35 text-[#F5F5F2]"
                  : "bg-[#36B37E]/15 border-[#6EE7B7]/30 text-[#F5F5F2]"
              }`}
            >
              <div className="flex items-center space-x-2.5">
                {actionToast.isError ? (
                  <AlertOctagon className="w-4 h-4 text-[#F07178] shrink-0" />
                ) : (
                  <CheckCircle2 className="w-4 h-4 text-[#6EE7B7] shrink-0" />
                )}
                <span className="font-medium">{actionToast.message}</span>
              </div>
              <button
                type="button"
                onClick={() => setActionToast(null)}
                aria-label="Dismiss notification"
                className="p-1 rounded-lg text-[#B4B3B0] hover:text-[#F5F5F2] hover:bg-white/10"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          )}

          {/* Scrollable Screen Viewport */}
          <main
            className={`flex-1 min-h-0 overflow-y-auto p-4 md:p-6 ${
              isMobileViewport ? "pb-20" : ""
            }`}
          >
            <div className="max-w-[1920px] mx-auto">
              {activeScreen === "dashboard" && (
                <DashboardScreen
                  status={effectiveStatus}
                  onRefresh={refreshStatus}
                  onNavigate={setActiveScreen}
                  onActionMessage={handleActionMessage}
                  trades={normalized.recentTrades}
                  feedStatus={feedStatus}
                  initialSymbol={chartJumpSymbol}
                  readOnlyMobile={isMobileViewport}
                  serviceStatus={serviceStatus}
                  onReconnectService={handleReconnectService}
                />
              )}

              {activeScreen === "positions" && (
                <PositionsScreen
                  status={effectiveStatus}
                  onRefresh={refreshStatus}
                  onActionMessage={handleActionMessage}
                  readOnly={isMobileViewport}
                />
              )}

              {activeScreen === "signals" && (
                <SignalsGridScreen onJumpToChart={handleJumpToChart} />
              )}

              {activeScreen === "alerts" && (
                <AlertCentreScreen onActionMessage={handleActionMessage} />
              )}

              {activeScreen === "history" && (
                <TradeHistoryScreen
                  trades={normalized.recentTrades}
                  onReload={reloadTrades}
                  onReplayTrade={(ticket) => setReplayTicket(ticket)}
                />
              )}

              {activeScreen === "analytics" && (
                <AnalyticsScreen
                  trades={normalized.recentTrades}
                  snapshots={balanceSnapshots}
                />
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
      </div>

      {/* Responsive Read-Only Mobile Companion Bottom Navigation (< 768px) */}
      <nav
        aria-label="Mobile Companion Navigation"
        className="md:hidden fixed bottom-0 left-0 right-0 z-40 h-16 bg-[#17181A] border-t border-white/[0.08] grid grid-cols-4 px-2"
      >
        {(
          [
            { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
            { id: "positions", label: "Positions", icon: Layers },
            { id: "signals", label: "Signals", icon: Zap },
            { id: "alerts", label: "Alerts", icon: Bell },
          ] as const
        ).map((tab) => {
          const Icon = tab.icon;
          const active = activeScreen === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveScreen(tab.id)}
              className={`flex flex-col items-center justify-center space-y-1 text-[11px] font-medium transition ${
                active ? "text-white" : "text-[#9CA1A6]"
              }`}
            >
              <Icon className="w-4 h-4" />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </nav>

      {/* Trade Replay Modal */}
      <TradeReplayModal ticket={replayTicket} onClose={() => setReplayTicket(null)} />

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
