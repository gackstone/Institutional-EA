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
  LogOut,
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

  const consecutivePollErrorsRef = useRef<number>(0);

  const refreshStatus = useCallback(async () => {
    try {
      const st = await controlClient.getStatus();
      consecutivePollErrorsRef.current = 0;
      setRawStatus(st);
      setFeedStatus((prev) => (prev === "LIVE_SSE" ? "LIVE_SSE" : "POLLING"));
    } catch {
      consecutivePollErrorsRef.current += 1;
      if (consecutivePollErrorsRef.current >= 2) {
        setFeedStatus("DISCONNECTED");
      } else {
        setFeedStatus((prev) => (prev === "LIVE_SSE" ? "LIVE_SSE" : "POLLING"));
      }
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
          setActionToast((toast) =>
            toast && /offline|retrying/i.test(toast.message) ? null : toast
          );
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
    let sseReconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let sseBackoffMs = 2500;
    let cancelled = false;

    const scheduleSseReconnect = () => {
      if (cancelled || sseReconnectTimer) return;
      const delay = sseBackoffMs;
      sseBackoffMs = Math.min(15000, Math.round(sseBackoffMs * 1.6));
      sseReconnectTimer = setTimeout(() => {
        sseReconnectTimer = null;
        if (!cancelled) {
          connectSse();
        }
      }, delay);
    };

    const connectSse = async () => {
      if (cancelled) return;
      if (es) {
        try {
          es.close();
        } catch {
          // ignore
        }
        es = null;
      }
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
          if (!cancelled) {
            sseBackoffMs = 2500;
            consecutivePollErrorsRef.current = 0;
            setFeedStatus("LIVE_SSE");
          }
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
          if (es) {
            try {
              es.close();
            } catch {
              // ignore
            }
            es = null;
          }
          if (!cancelled) {
            setFeedStatus((prev) => (prev === "DISCONNECTED" ? "DISCONNECTED" : "POLLING"));
            scheduleSseReconnect();
          }
        };
      } catch {
        if (!cancelled) {
          setFeedStatus((prev) => (prev === "DISCONNECTED" ? "DISCONNECTED" : "POLLING"));
          scheduleSseReconnect();
        }
      }
    };

    connectSse();
    const interval = setInterval(() => {
      refreshStatus();
    }, 4000);

    return () => {
      cancelled = true;
      clearInterval(interval);
      if (sseReconnectTimer) clearTimeout(sseReconnectTimer);
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

  // Sidebar Structure: Dashboard top-level, collapsible MONITOR / CONTROL / DIAGNOSE groups, Settings + Sign Out pinned at bottom
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
  const mainLeftOffsetPx = DESIGN_TOKENS.sidebar.collapsedWidthPx;

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

  const handleSignOutClick = useCallback(async () => {
    if (pairing.isPaired) {
      const res = await IPC.disconnectPairing().catch(() => ({
        success: false,
        message: "Unable to disconnect cloud pairing",
      }));
      if (res.success) {
        setPairing((p) => ({ ...p, isPaired: false, instanceId: null, deviceTokenMasked: null }));
        handleActionMessage("Signed out of Institutional EA Cloud pairing.", false);
      } else {
        handleActionMessage(res.message || "Sign out failed", true);
      }
    } else {
      setIsPairingOpen(true);
    }
  }, [pairing.isPaired, handleActionMessage]);

  const renderBadgePill = (badge?: number, tone: "mint" | "peach" = "mint") => {
    if (badge === undefined) return null;
    return (
      <span
        data-testid={`sidebar-badge-${tone}`}
        className={`min-w-[22px] h-[20px] px-1.5 rounded-[6px] text-[10px] font-mono font-bold tabular-nums inline-flex items-center justify-center shrink-0 ${
          tone === "peach"
            ? "bg-iea-dangerSoft text-iea-danger border border-iea-dangerBorder"
            : "bg-iea-accentSoft text-iea-accent border border-iea-accentBorder"
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
        className={`absolute top-1.5 right-1.5 w-2 h-2 rounded-full ring-2 ring-[var(--iea-sidebar-rail-bg)] ${
          tone === "peach" ? "bg-iea-danger" : "bg-iea-accent"
        }`}
      />
    );
  };

  return (
    <div
      style={{ "--iea-titlebar-h": `${titlebarHeightPx}px` } as React.CSSProperties}
      className="relative flex h-screen w-screen overflow-hidden iea-shell-bg text-iea-textPrimary antialiased font-sans select-none"
    >
      {/* Electron-Only Native Title Bar Drag Strip (36px) paired with Windows titleBarOverlay */}
      {isElectron && (
        <div
          data-testid="electron-titlebar-strip"
          style={{
            height: "36px",
            paddingRight: "max(144px, calc(100% - env(titlebar-area-width, 100%)))",
          }}
          className="iea-drag-region fixed top-0 left-0 right-0 z-50 bg-iea-titlebar border-b border-iea-borderSubtle flex items-center justify-between px-3.5"
        >
          <div className="flex items-center space-x-2 min-w-0">
            <div className="w-5 h-5 rounded-[6px] bg-iea-accent flex items-center justify-center shrink-0">
              <span className="w-2.5 h-2.5 rounded-full border-[2px] border-white flex items-center justify-center">
                <span className="w-1 h-1 rounded-full bg-white" />
              </span>
            </div>
            <span className="text-[11px] font-bold tracking-tight text-iea-textPrimary truncate">
              INSTITUTIONAL <span className="text-iea-accent">EA</span>
            </span>
            <span className="text-[10px] font-mono text-iea-textMuted">
              {UI_COPY.brand.subtitle}
            </span>
          </div>
          <span className="text-[10px] font-mono text-iea-textMuted hidden sm:inline">
            DEMO · LIVE_TRADING_ENABLED=false
          </span>
        </div>
      )}

      {/* =====================================================================
          BM FOREX HUB DOCKED FULL-HEIGHT OVERLAY SIDEBAR
          Collapsed: ~72px icon rail | Expanded: ~256px overlay with labels
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
          bottom: 0,
          left: 0,
          width: isSidebarExpanded
            ? `${DESIGN_TOKENS.sidebar.expandedWidthPx}px`
            : `${DESIGN_TOKENS.sidebar.collapsedWidthPx}px`,
        }}
        className="iea-no-drag hidden md:flex fixed z-40 iea-sidebar-rail flex-col justify-between overflow-hidden"
      >
        {/* Top Brand Block + Navigation */}
        <div className="flex flex-col min-h-0 flex-1">
          {/* Brand Logo Tile + "INSTITUTIONAL EA" with blue accent word */}
          <div className="h-[68px] px-4 border-b border-iea-borderSubtle flex items-center justify-between gap-2 shrink-0">
            <div className="flex items-center space-x-3 min-w-0 flex-1">
              <div
                className="w-10 h-10 rounded-[12px] bg-iea-accent text-white flex items-center justify-center shrink-0"
                aria-hidden="true"
              >
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
                  <rect
                    x="4"
                    y="4"
                    width="16"
                    height="16"
                    rx="5"
                    stroke="currentColor"
                    strokeWidth="2.2"
                  />
                  <circle cx="12" cy="12" r="3" fill="currentColor" />
                </svg>
              </div>

              <div
                className={`iea-sidebar-label min-w-0 flex-1 whitespace-nowrap ${
                  isSidebarExpanded ? "" : "w-0 overflow-hidden"
                }`}
              >
                <div className="text-[13px] font-bold tracking-tight text-iea-textPrimary leading-tight truncate">
                  INSTITUTIONAL <span className="text-iea-accent">EA</span>
                </div>
                <div className="text-[10px] font-mono text-iea-textMuted mt-0.5 truncate">
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
                className={`p-1.5 rounded-[8px] text-xs transition shrink-0 ${
                  isSidebarTouchPinned
                    ? "bg-iea-accentSoft text-iea-accent border border-iea-accentBorder"
                    : "text-iea-textSecondary hover:text-iea-textPrimary hover:bg-[var(--iea-hover-bg)]"
                }`}
              >
                <PanelLeft className="w-4 h-4" />
              </button>
            )}
          </div>

          {/* Navigation Body */}
          <nav
            aria-label="Screen Navigation"
            className="flex-1 px-3 py-2 overflow-y-auto overflow-x-hidden space-y-0.5"
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
                  className={`group relative w-full flex items-center rounded-[11px] transition-all duration-200 ${
                    isSidebarExpanded
                      ? "h-10 px-3 justify-between"
                      : "h-9 justify-center"
                  } ${
                    active
                      ? isSidebarExpanded
                        ? "bg-iea-accentSoft text-iea-accent font-semibold border border-iea-accentBorder"
                        : "text-iea-accent"
                      : "text-iea-textSecondary hover:text-iea-textPrimary hover:bg-[var(--iea-hover-bg)] border border-transparent"
                  }`}
                >
                  {isSidebarExpanded ? (
                    <div className="flex items-center space-x-3 min-w-0">
                      <Icon
                        className={`w-[18px] h-[18px] shrink-0 transition-colors ${
                          active
                            ? "text-iea-accent"
                            : "text-iea-textSecondary group-hover:text-iea-textPrimary"
                        }`}
                      />
                      <span className="iea-sidebar-label text-[13px] whitespace-nowrap truncate">
                        {dashboardItem.label}
                      </span>
                    </div>
                  ) : (
                    <div
                      className={`w-9 h-9 rounded-[10px] flex items-center justify-center transition-colors ${
                        active
                          ? "bg-iea-accentSoft text-iea-accent border border-iea-accentBorder"
                          : "text-iea-textSecondary group-hover:text-iea-textPrimary group-hover:bg-[var(--iea-hover-bg)]"
                      }`}
                    >
                      <Icon className="w-[17px] h-[17px]" />
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
                  <div key={grp.group} className="pt-1 space-y-0.5">
                    <div
                      className="w-6 h-px mx-auto bg-iea-borderSubtle mb-1"
                      aria-hidden="true"
                    />
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
                          className="group relative w-full h-9 flex items-center justify-center rounded-[10px] transition"
                        >
                          <div
                            className={`relative w-9 h-9 rounded-[10px] flex items-center justify-center transition-colors ${
                              active
                                ? "bg-iea-accentSoft text-iea-accent border border-iea-accentBorder"
                                : "text-iea-textSecondary group-hover:text-iea-textPrimary group-hover:bg-[var(--iea-hover-bg)]"
                            }`}
                          >
                            <Icon className="w-[17px] h-[17px]" />
                            {renderCollapsedBadgeDot(item.badge, item.badgeTone)}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                );
              }

              // Expanded State: Collapsible group header + icons with labels
              return (
                <div key={grp.group} className="pt-1">
                  <button
                    type="button"
                    data-testid={`sidebar-group-${grp.group.toLowerCase()}`}
                    aria-expanded={isOpen}
                    onClick={() => toggleGroup(grp.group)}
                    className={`w-full h-10 px-3 rounded-[10px] flex items-center justify-between transition-all duration-200 border ${
                      hasActiveChild
                        ? "text-iea-textPrimary font-semibold border-transparent"
                        : "text-iea-textMuted hover:text-iea-textPrimary hover:bg-[var(--iea-hover-bg)] font-semibold border-transparent"
                    }`}
                  >
                    <div className="flex items-center space-x-2.5 min-w-0">
                      <GroupIcon
                        className={`w-4 h-4 shrink-0 ${
                          hasActiveChild ? "text-iea-accent" : "text-iea-textMuted"
                        }`}
                      />
                      <span className="iea-sidebar-label text-[11px] uppercase tracking-wider whitespace-nowrap truncate">
                        {grp.label}
                      </span>
                    </div>
                    <ChevronDown
                      className={`w-3.5 h-3.5 shrink-0 transition-transform duration-200 ${
                        isOpen ? "rotate-180 text-iea-textSecondary" : "text-iea-textMuted"
                      }`}
                    />
                  </button>

                  {/* Smooth Collapsible Children (Icons + Labels) */}
                  <div
                    className={`grid transition-[grid-template-rows,opacity] duration-200 ease-out ${
                      isOpen
                        ? "grid-rows-[1fr] opacity-100 mt-0.5"
                        : "grid-rows-[0fr] opacity-0 pointer-events-none"
                    }`}
                  >
                    <div className="overflow-hidden min-h-0">
                      <div className={`space-y-0.5 ${isOpen ? "py-0.5" : "py-0"}`}>
                        {grp.items.map((item) => {
                          const ItemIcon = item.icon;
                          const active = activeScreen === item.id;
                          return (
                            <button
                              key={item.id}
                              type="button"
                              onClick={(e) => handleSelectNavItem(item.id, e)}
                              aria-current={active ? "page" : undefined}
                              aria-label={item.label}
                              title={`${item.label} — ${item.tooltip}`}
                              className={`group w-full h-10 px-3 rounded-[10px] flex items-center justify-between text-[13px] transition-all duration-150 ${
                                active
                                  ? "bg-iea-accentSoft text-iea-accent font-semibold border border-iea-accentBorder"
                                  : "text-iea-textSecondary hover:text-iea-textPrimary hover:bg-[var(--iea-hover-bg)] font-normal border border-transparent"
                              }`}
                            >
                              <div className="flex items-center space-x-3 min-w-0">
                                <ItemIcon
                                  className={`w-4 h-4 shrink-0 transition-colors ${
                                    active
                                      ? "text-iea-accent"
                                      : "text-iea-textSecondary group-hover:text-iea-textPrimary"
                                  }`}
                                />
                                <span className="iea-sidebar-label whitespace-nowrap truncate">
                                  {item.label}
                                </span>
                              </div>
                              <div className="flex items-center space-x-1.5 shrink-0">
                                {renderBadgePill(item.badge, item.badgeTone)}
                                {active && <ChevronRight className="w-3.5 h-3.5 text-iea-accent" />}
                              </div>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </nav>
        </div>

        {/* Bottom Group Pinned Behind a Divider: Settings, Sign Out & DEMO Safety Lock */}
        <div className="px-3 py-3 border-t border-iea-borderSubtle space-y-1 shrink-0">
          {/* Settings Item */}
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
                className={`group relative w-full flex items-center rounded-[11px] transition-all duration-200 ${
                  isSidebarExpanded ? "h-10 px-3 justify-between" : "h-10 justify-center"
                } ${
                  active
                    ? isSidebarExpanded
                      ? "bg-iea-accentSoft text-iea-accent font-semibold border border-iea-accentBorder"
                      : "text-iea-accent"
                    : "text-iea-textSecondary hover:text-iea-textPrimary hover:bg-[var(--iea-hover-bg)] border border-transparent"
                }`}
              >
                {isSidebarExpanded ? (
                  <div className="flex items-center space-x-3 min-w-0">
                    <Icon
                      className={`w-[18px] h-[18px] shrink-0 ${
                        active
                          ? "text-iea-accent"
                          : "text-iea-textSecondary group-hover:text-iea-textPrimary"
                      }`}
                    />
                    <span className="iea-sidebar-label text-[13px] whitespace-nowrap truncate">
                      {settingsItem.label}
                    </span>
                  </div>
                ) : (
                  <div
                    className={`w-10 h-10 rounded-[11px] flex items-center justify-center transition-colors ${
                      active
                        ? "bg-iea-accentSoft text-iea-accent border border-iea-accentBorder"
                        : "text-iea-textSecondary group-hover:text-iea-textPrimary group-hover:bg-[var(--iea-hover-bg)]"
                    }`}
                  >
                    <Icon className="w-[18px] h-[18px]" />
                  </div>
                )}
              </button>
            );
          })()}

          {/* Sign Out / Cloud Pairing Action */}
          <button
            type="button"
            onClick={handleSignOutClick}
            aria-label="Sign out or manage cloud pairing"
            title={
              pairing.isPaired
                ? `Sign out from Institutional EA Cloud (${pairing.instanceId || "Paired"})`
                : "Sign Out / Cloud Pairing"
            }
            className={`group relative w-full flex items-center rounded-[11px] transition-all duration-200 text-iea-textSecondary hover:text-iea-danger hover:bg-iea-dangerSoft/60 border border-transparent ${
              isSidebarExpanded ? "h-10 px-3 justify-between" : "h-10 justify-center"
            }`}
          >
            {isSidebarExpanded ? (
              <div className="flex items-center space-x-3 min-w-0">
                <LogOut className="w-[18px] h-[18px] shrink-0 text-iea-textSecondary group-hover:text-iea-danger" />
                <span className="iea-sidebar-label text-[13px] whitespace-nowrap truncate">
                  Sign Out
                </span>
              </div>
            ) : (
              <div className="w-10 h-10 rounded-[11px] flex items-center justify-center transition-colors">
                <LogOut className="w-[18px] h-[18px]" />
              </div>
            )}
          </button>

          {/* Compact DEMO Lock Status Row */}
          {isSidebarExpanded ? (
            <div className="iea-sidebar-label pt-2 mt-1 border-t border-iea-borderSubtle space-y-1.5 whitespace-nowrap px-1">
              <div className="flex items-center justify-between text-[10px] font-mono">
                <span
                  className="inline-flex items-center space-x-1.5 text-iea-profit font-semibold"
                  title={UI_COPY.brand.demoLockTooltip}
                >
                  <Lock className="w-3 h-3" />
                  <span>{UI_COPY.brand.demoLockShort}</span>
                </span>
                <span className="text-iea-textMuted">
                  {serviceStatus
                    ? `${serviceStatus.host}:${serviceStatus.port}`
                    : "127.0.0.1:8765"}
                </span>
              </div>
              <div className="text-[10px] text-iea-textMuted flex items-center justify-between">
                <span className="font-mono">{feedStatus}</span>
                <div className="flex items-center space-x-2.5">
                  <button
                    type="button"
                    onClick={() => setActiveScreen("settings")}
                    title="Open Short-Form Glossary (Settings > Glossary)"
                    className="text-iea-textSecondary hover:text-iea-textPrimary font-mono transition"
                  >
                    ? Glossary
                  </button>
                  <button
                    type="button"
                    onClick={() => refreshStatus()}
                    aria-label="Refresh terminal telemetry"
                    className="text-iea-accent hover:text-iea-textPrimary inline-flex items-center space-x-1 font-medium transition"
                  >
                    <RefreshCw className="w-3 h-3" />
                    <span>Sync</span>
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div
              className="flex justify-center pt-1"
              title="DEMO Lock Active (LIVE_TRADING_ENABLED=false)"
            >
              <div className="w-9 h-9 rounded-[10px] bg-iea-card border border-iea-borderSubtle flex items-center justify-center">
                <Lock className="w-3.5 h-3.5 text-iea-profit" />
              </div>
            </div>
          )}
        </div>
      </aside>

      {/* =====================================================================
          MAIN CONTENT AREA — FULL-BLEED NEAR-BLACK CANVAS (~24px PAGE PADDING)
      ====================================================================== */}
      <div
        style={{
          paddingLeft: isMobileViewport ? "0px" : `${mainLeftOffsetPx}px`,
          paddingTop: `${titlebarHeightPx}px`,
        }}
        className="iea-no-drag relative z-10 flex-1 min-w-0 flex flex-col h-screen overflow-hidden"
      >
        <div className="iea-main-panel flex-1 min-h-0 flex flex-col overflow-hidden">
          {/* Sub-screen Navigation Header Bar (when viewing any sub-screen) */}
          {activeScreen !== "dashboard" && (
            <header className="h-14 px-6 border-b border-iea-borderSubtle flex items-center justify-between shrink-0">
              <div className="flex items-center space-x-3.5">
                <button
                  type="button"
                  onClick={() => setActiveScreen("dashboard")}
                  className="iea-pill-control px-3.5 py-1.5 text-xs font-medium inline-flex items-center space-x-1.5"
                >
                  <span>← Dashboard</span>
                </button>
                <h1 className="text-[18px] font-bold tracking-tight text-iea-textPrimary">
                  {allScreenItems.find((i) => i.id === activeScreen)?.label || activeScreen}
                </h1>
              </div>

              <div className="flex items-center space-x-2 text-xs font-mono">
                <span className="px-3 py-1 rounded-full bg-iea-accentSoft border border-iea-accentBorder text-iea-accent font-semibold">
                  {UI_COPY.brand.demoLockChip}
                </span>
                <span className="iea-pill-control px-3 py-1 text-iea-textSecondary">
                  MT5 {normalized.maskedAccount}
                </span>
                <span className="iea-pill-control px-3 py-1 text-iea-accent inline-flex items-center space-x-1.5">
                  <Radio className="w-3 h-3 text-iea-profit" />
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
              className={`mx-6 mt-4 px-4 py-2.5 rounded-[14px] border text-xs flex items-center justify-between shrink-0 ${
                actionToast.isError
                  ? "bg-iea-dangerSoft border-iea-dangerBorder text-iea-textPrimary"
                  : "bg-iea-profitSoft border-iea-profitBorder text-iea-textPrimary"
              }`}
            >
              <div className="flex items-center space-x-2.5">
                {actionToast.isError ? (
                  <AlertOctagon className="w-4 h-4 text-iea-danger shrink-0" />
                ) : (
                  <CheckCircle2 className="w-4 h-4 text-iea-profit shrink-0" />
                )}
                <span className="font-medium">{actionToast.message}</span>
              </div>
              <button
                type="button"
                onClick={() => setActionToast(null)}
                aria-label="Dismiss notification"
                className="p-1 rounded-lg text-iea-textSecondary hover:text-iea-textPrimary hover:bg-[var(--iea-hover-bg)]"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          )}

          {/* Scrollable Screen Viewport (~24px Page Padding) */}
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
        className="md:hidden fixed bottom-0 left-0 right-0 z-40 h-16 bg-iea-card border-t border-iea-borderSubtle grid grid-cols-4 px-2"
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
                active ? "text-iea-accent" : "text-iea-textSecondary"
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
