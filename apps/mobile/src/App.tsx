import React, { useCallback, useEffect, useRef, useState } from "react";
import { AppState, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";
import * as LocalAuthentication from "expo-local-authentication";
import { MobileErrorBoundary } from "./components/ErrorBoundary.tsx";
import { RootNavigator, type MobileTab } from "./navigation/RootNavigator.tsx";
import { type ThemeMode, getThemeTokens } from "./theme/themeTokens.ts";
import {
  SecureStorage,
  type PairingCredentials,
} from "./services/SecureStorage.ts";
import {
  DEFAULT_LAYER_PREFS,
  OfflineCache,
  type ChartLayerPreferences,
} from "./services/OfflineCache.ts";
import {
  MobileSyncClient,
  MobileSyncError,
  isSnapshotStale,
  parseIsoToMs,
  type SyncDiagnosticsState,
} from "./services/MobileSyncClient.ts";
import type { ConnectionState } from "./components/ConnectionBanner.tsx";
import type { EquityRange } from "./components/EquityCurveCard.tsx";
import {
  MOBILE_SYNC_SCHEMA_VERSION,
  MobileAccountSchema,
  MobilePositionSchema,
  MobileStatsSchema,
  MobileStatusSchema,
  MobileSymbolsResponseSchema,
  type MobileAccount,
  type MobileActivityEvent,
  type MobileCandlesResponse,
  type MobileDrawingsResponse,
  type MobileEquityResponse,
  type MobilePosition,
  type MobileStats,
  type MobileStatus,
  type MobileSymbolsResponse,
  type MobileTradeRecord,
} from "@institutional-ea/data-contract";
import { z } from "zod";

export default function App(): React.ReactElement {
  const [theme, setTheme] = useState<ThemeMode>("dark");
  const [currentTab, setCurrentTab] = useState<MobileTab>("OVERVIEW");
  const [chartFullscreen, setChartFullscreen] = useState(false);

  // Security & Pairing
  const [credentials, setCredentials] = useState<PairingCredentials | null>(null);
  const [biometricEnabled, setBiometricEnabled] = useState(false);
  const [locked, setLocked] = useState(false);

  // Live & Cached Telemetry (ZERO hardcoded values)
  const [status, setStatus] = useState<MobileStatus | null>(null);
  const [account, setAccount] = useState<MobileAccount | null>(null);
  const [stats, setStats] = useState<MobileStats | null>(null);
  const [positions, setPositions] = useState<MobilePosition[]>([]);
  const [symbolsData, setSymbolsData] = useState<MobileSymbolsResponse | null>(null);
  const [equityRange, setEquityRange] = useState<EquityRange>("1W");
  const [equity, setEquity] = useState<MobileEquityResponse | null>(null);
  const [activity, setActivity] = useState<MobileActivityEvent[]>([]);

  // Chart state
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [selectedTimeframe, setSelectedTimeframe] = useState<string>("M5");
  const [layers, setLayers] = useState<ChartLayerPreferences>(DEFAULT_LAYER_PREFS);
  const [candlesData, setCandlesData] = useState<MobileCandlesResponse | null>(null);
  const [drawings, setDrawings] = useState<MobileDrawingsResponse | null>(null);
  const [focusChartTime, setFocusChartTime] = useState<number | null>(null);

  // Connectivity & Honest Freshness state (E10)
  const [streamConnected, setStreamConnected] = useState(false);
  const [streamError, setStreamError] = useState(false);
  const [lastSyncedMs, setLastSyncedMs] = useState<number | null>(null);
  const [producerUpdatedMs, setProducerUpdatedMs] = useState<number | null>(null);
  const [syncDiagnostics, setSyncDiagnostics] = useState<SyncDiagnosticsState | null>(null);
  const [isShowingCache, setIsShowingCache] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [staleTick, setStaleTick] = useState(0);

  const clientRef = useRef<MobileSyncClient | null>(null);
  const chartAbortRef = useRef<AbortController | null>(null);
  const candlesCacheRef = useRef<Record<string, MobileCandlesResponse>>({});
  const drawingsCacheRef = useRef<Record<string, MobileDrawingsResponse>>({});

  // 1. Cold-start bootstrap: load theme, biometric setting, credentials, chart prefs & offline cache
  useEffect(() => {
    let active = true;
    (async () => {
      const [storedTheme, bioEnabled, storedCreds, prefs] = await Promise.all([
        SecureStorage.getStoredTheme(),
        SecureStorage.getBiometricLockEnabled(),
        SecureStorage.getPairingCredentials(),
        OfflineCache.loadChartPreferences(),
      ]);
      if (!active) return;

      const cached = await OfflineCache.loadSnapshot({
        deviceId: storedCreds?.deviceId ?? null,
        schemaVersion: MOBILE_SYNC_SCHEMA_VERSION,
      });
      if (!active) return;

      if (storedTheme === "light" || storedTheme === "dark") {
        setTheme(storedTheme);
      }
      setBiometricEnabled(bioEnabled);
      if (bioEnabled) {
        setLocked(true);
        LocalAuthentication.authenticateAsync({
          promptMessage: "Unlock Institutional EA",
        })
          .then((res) => {
            if (active && res.success) setLocked(false);
          })
          .catch(() => {});
      }

      setLayers(prefs.layers);
      setSelectedTimeframe(prefs.selectedTimeframe || "M5");
      if (prefs.selectedSymbol) {
        setSelectedSymbol(prefs.selectedSymbol);
      }

      if (cached) {
        setStatus(cached.status);
        setAccount(cached.account);
        setStats(cached.stats);
        setPositions(cached.positions || []);
        setSymbolsData(cached.symbols);
        setEquity(cached.equity);
        setActivity(cached.activity || []);
        candlesCacheRef.current = cached.candlesByKey || {};
        drawingsCacheRef.current = cached.drawingsByKey || {};
        setLastSyncedMs(cached.cachedAt);
        setProducerUpdatedMs(
          parseIsoToMs(cached.status?.lastHeartbeat || cached.account?.updatedAt) ??
            cached.cachedAt
        );
        setIsShowingCache(true);

        const sym =
          prefs.selectedSymbol || cached.symbols?.symbols?.[0]?.symbol || null;
        if (sym) {
          setSelectedSymbol(sym);
          const key = `${sym}:${prefs.selectedTimeframe || "M5"}`;
          if (candlesCacheRef.current[key]) setCandlesData(candlesCacheRef.current[key]);
          if (drawingsCacheRef.current[key]) setDrawings(drawingsCacheRef.current[key]);
        }
      }

      if (storedCreds) {
        clientRef.current = new MobileSyncClient(storedCreds);
        setCredentials(storedCreds);
        setSyncDiagnostics(clientRef.current.getDiagnostics());
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const persistSnapshot = useCallback(
    (overrides?: Partial<{
      status: MobileStatus | null;
      account: MobileAccount | null;
      stats: MobileStats | null;
      positions: MobilePosition[];
      symbols: MobileSymbolsResponse | null;
      equity: MobileEquityResponse | null;
      activity: MobileActivityEvent[];
    }>) => {
      const nextStatus = overrides?.status !== undefined ? overrides.status : status;
      const nextAccount = overrides?.account !== undefined ? overrides.account : account;
      const prodMs =
        parseIsoToMs(nextStatus?.lastHeartbeat || nextAccount?.updatedAt) ?? Date.now();
      setLastSyncedMs(prodMs);
      setProducerUpdatedMs(prodMs);
      setIsShowingCache(false);
      if (clientRef.current) {
        setSyncDiagnostics(clientRef.current.getDiagnostics());
      }
      OfflineCache.saveSnapshot({
        cachedAt: prodMs,
        deviceId: credentials?.deviceId,
        accountMasked: nextAccount?.accountMasked || nextStatus?.accountMasked,
        schemaVersion: MOBILE_SYNC_SCHEMA_VERSION,
        status: nextStatus,
        account: nextAccount,
        stats: overrides?.stats !== undefined ? overrides.stats : stats,
        positions: overrides?.positions !== undefined ? overrides.positions : positions,
        symbols: overrides?.symbols !== undefined ? overrides.symbols : symbolsData,
        candlesByKey: candlesCacheRef.current,
        drawingsByKey: drawingsCacheRef.current,
        equity: overrides?.equity !== undefined ? overrides.equity : equity,
        activity: overrides?.activity !== undefined ? overrides.activity : activity,
      }).catch(() => {});
    },
    [credentials?.deviceId, status, account, stats, positions, symbolsData, equity, activity]
  );

  const handleRevoked = useCallback(async () => {
    clientRef.current?.stopStream();
    clientRef.current = null;
    await SecureStorage.clearPairingCredentials();
    setCredentials(null);
    setStreamConnected(false);
    setStreamError(false);
    setCurrentTab("SECURITY");
  }, []);

  // Fetch chart candles & drawings for active symbol/timeframe
  const fetchChartData = useCallback(
    async (sym: string, tf: string, preserveOld = false) => {
      const client = clientRef.current;
      if (!client || !sym) return;
      if (chartAbortRef.current) chartAbortRef.current.abort();
      const ctrl = new AbortController();
      chartAbortRef.current = ctrl;

      try {
        const [cRes, dRes] = await Promise.all([
          client.getCandles({ symbol: sym, tf, limit: 160 }, ctrl.signal),
          client.getDrawings({ symbol: sym, tf, count: 160 }, ctrl.signal),
        ]);
        const key = `${sym}:${tf}`;
        candlesCacheRef.current[key] = cRes;
        drawingsCacheRef.current[key] = dRes;
        setCandlesData(cRes);
        setDrawings(dRes);
        setSyncDiagnostics(client.getDiagnostics());
      } catch (err: any) {
        if (err?.name === "AbortError") return;
        if (err instanceof MobileSyncError && err.status === 401) {
          handleRevoked();
          return;
        }
        setSyncDiagnostics(client.getDiagnostics());
        if (!preserveOld) {
          const key = `${sym}:${tf}`;
          setCandlesData(candlesCacheRef.current[key] ?? null);
          setDrawings(drawingsCacheRef.current[key] ?? null);
        }
      }
    },
    [handleRevoked]
  );

  // Full snapshot refresh (initial sync, pull-to-refresh, or foreground resume)
  const fetchFullSnapshot = useCallback(
    async (isPull = false) => {
      const client = clientRef.current;
      if (!client) return;
      if (isPull) setIsRefreshing(true);
      else setIsLoading(true);

      try {
        const [st, acc, stStats, posRes, symRes, eqRes, actRes] = await Promise.all([
          client.getStatus(),
          client.getAccount(),
          client.getStats(),
          client.getPositions(),
          client.getSymbols(),
          client.getEquity(equityRange),
          client.getActivity(40),
        ]);

        // If account changed, invalidate old cached charts
        if (
          account?.accountMasked &&
          acc.accountMasked &&
          account.accountMasked !== "DEMO" &&
          acc.accountMasked !== "DEMO" &&
          account.accountMasked !== acc.accountMasked
        ) {
          candlesCacheRef.current = {};
          drawingsCacheRef.current = {};
          await OfflineCache.clearSnapshot();
        }

        setStatus(st);
        setAccount(acc);
        setStats(stStats);
        setPositions(posRes.positions);
        setSymbolsData(symRes);
        setEquity(eqRes);
        setActivity(actRes.events);
        setStreamError(false);

        const nextSym =
          selectedSymbol && symRes.symbols.some((s) => s.symbol === selectedSymbol)
            ? selectedSymbol
            : symRes.symbols[0]?.symbol ?? "XAUUSD";
        if (nextSym && nextSym !== selectedSymbol) {
          setSelectedSymbol(nextSym);
        }
        if (nextSym) {
          await fetchChartData(nextSym, selectedTimeframe, true);
        }

        persistSnapshot({
          status: st,
          account: acc,
          stats: stStats,
          positions: posRes.positions,
          symbols: symRes,
          equity: eqRes,
          activity: actRes.events,
        });
      } catch (err: unknown) {
        if (err instanceof MobileSyncError && err.status === 401) {
          await handleRevoked();
          return;
        }
        setStreamError(true);
        setSyncDiagnostics(client.getDiagnostics());
      } finally {
        setIsLoading(false);
        setIsRefreshing(false);
      }
    },
    [
      account?.accountMasked,
      equityRange,
      selectedSymbol,
      selectedTimeframe,
      fetchChartData,
      handleRevoked,
      persistSnapshot,
    ]
  );

  // Start / stop live SSE / Cloud Sync stream when credentials change or AppState transitions
  const startLiveSync = useCallback(() => {
    const client = clientRef.current;
    if (!client) return;

    fetchFullSnapshot(false);
    client.startStream({
      onOpen: () => {
        setStreamConnected(true);
        setStreamError(false);
        setSyncDiagnostics(client.getDiagnostics());
      },
      onEvent: (ev) => {
        setIsShowingCache(false);
        setStreamConnected(true);
        setStreamError(false);
        setSyncDiagnostics(client.getDiagnostics());

        if (ev.type === "snapshot" && ev.payload && typeof ev.payload === "object") {
          const p = ev.payload as any;
          const prodTs = parseIsoToMs(p.updatedAt || p.status?.lastHeartbeat || ev.timestamp);
          if (prodTs) {
            setProducerUpdatedMs(prodTs);
            setLastSyncedMs(prodTs);
          }

          if (client.getCredentials().mode === "cloud") {
            fetchFullSnapshot(false);
            return;
          }

          try {
            if (p.status) setStatus(MobileStatusSchema.parse(p.status));
            if (p.account) setAccount(MobileAccountSchema.parse(p.account));
            if (p.stats) setStats(MobileStatsSchema.parse(p.stats));
            if (Array.isArray(p.positions)) {
              setPositions(z.array(MobilePositionSchema).parse(p.positions));
            }
            if (p.symbols) {
              const parsedSyms = MobileSymbolsResponseSchema.parse(p.symbols);
              setSymbolsData(parsedSyms);
              if (!selectedSymbol && parsedSyms.symbols[0]) {
                setSelectedSymbol(parsedSyms.symbols[0].symbol);
              }
            }
          } catch {
            // Ignore partial/malformed frame safely
          }
        } else if (ev.type === "status" && ev.payload) {
          try {
            const st = MobileStatusSchema.parse(ev.payload);
            setStatus(st);
            const hbMs = parseIsoToMs(st.lastHeartbeat);
            if (hbMs) {
              setProducerUpdatedMs(hbMs);
              setLastSyncedMs(hbMs);
            }
          } catch {}
        }
      },
      onError: () => {
        setStreamConnected(false);
        setStreamError(true);
        setSyncDiagnostics(client.getDiagnostics());
      },
      onRevoked: () => {
        handleRevoked();
      },
    });
  }, [fetchFullSnapshot, handleRevoked, selectedSymbol]);

  useEffect(() => {
    if (!credentials) return;
    startLiveSync();

    const sub = AppState.addEventListener("change", (nextState) => {
      if (nextState === "active") {
        startLiveSync();
      } else {
        clientRef.current?.stopStream();
        setStreamConnected(false);
      }
    });

    return () => {
      sub.remove();
      clientRef.current?.stopStream();
      chartAbortRef.current?.abort();
    };
  }, [credentials]);

  // Refresh chart candles + drawings when symbol or timeframe changes
  useEffect(() => {
    if (!credentials || !selectedSymbol) return;
    fetchChartData(selectedSymbol, selectedTimeframe, false);
    OfflineCache.saveChartPreferences({
      selectedSymbol,
      selectedTimeframe,
      layers,
    }).catch(() => {});
  }, [credentials, selectedSymbol, selectedTimeframe]);

  // Refresh equity curve when range changes
  useEffect(() => {
    const client = clientRef.current;
    if (!client) return;
    client
      .getEquity(equityRange)
      .then((res) => setEquity(res))
      .catch(() => {});
  }, [equityRange]);

  // Heartbeat / stale watchdog timer (checks every 10s, zero network polling)
  useEffect(() => {
    const iv = setInterval(() => setStaleTick((n) => n + 1), 10_000);
    return () => clearInterval(iv);
  }, []);

  // Derive honest connection banner state tied strictly to producer data freshness (E10 Fix)
  const deriveConnectionState = (): ConnectionState => {
    void staleTick;
    if (!credentials) return "NOT_PAIRED";
    if (syncDiagnostics?.updateNeeded) return "UPDATE_NEEDED";
    if (streamError && !streamConnected) {
      return lastSyncedMs ? "RECONNECTING" : "COMPANION_OFFLINE";
    }
    if (!streamConnected && isLoading) return "CONNECTING";
    const freshnessMs = producerUpdatedMs ?? lastSyncedMs;
    if (!freshnessMs || isSnapshotStale(freshnessMs, Date.now(), 45_000)) {
      return streamConnected ? "STALE" : "CONNECTING";
    }
    if (status && !status.mt5Connected) return "MT5_DISCONNECTED";
    if (status?.botState === "PAUSED") return "BOT_PAUSED";
    if (status?.botState === "STOPPED") return "BOT_STOPPED";
    return streamConnected ? "LIVE" : "CONNECTING";
  };

  const handleToggleTheme = () => {
    const next: ThemeMode = theme === "dark" ? "light" : "dark";
    setTheme(next);
    SecureStorage.setStoredTheme(next).catch(() => {});
  };

  const handleToggleLayer = useCallback(
    (key: keyof ChartLayerPreferences) => {
      setLayers((prev) => {
        const next = { ...prev, [key]: !prev[key] };
        OfflineCache.saveChartPreferences({
          selectedSymbol,
          selectedTimeframe,
          layers: next,
        }).catch(() => {});
        return next;
      });
    },
    [selectedSymbol, selectedTimeframe]
  );

  const handleLoadMoreHistory = useCallback(
    async (beforeTime: number) => {
      const client = clientRef.current;
      if (!client || !selectedSymbol || !candlesData) return;
      try {
        const older = await client.getCandles({
          symbol: selectedSymbol,
          tf: selectedTimeframe,
          limit: 120,
          to: new Date((beforeTime - 1) * 1000).toISOString(),
        });
        if (older.candles.length > 0) {
          const merged = [...older.candles, ...candlesData.candles].sort(
            (a, b) => a.time - b.time
          );
          setCandlesData({ ...candlesData, candles: merged });
        }
      } catch {
        // Ignore lazy-load error silently
      }
    },
    [selectedSymbol, selectedTimeframe, candlesData]
  );

  const handleShowPositionOnChart = useCallback((pos: MobilePosition) => {
    setSelectedSymbol(pos.canonicalSymbol);
    setFocusChartTime(pos.openTime > 0 ? pos.openTime : null);
    setCurrentTab("CHARTS");
  }, []);

  const handleShowTradeOnChart = useCallback((trade: MobileTradeRecord) => {
    setSelectedSymbol(trade.canonicalSymbol);
    const ts = trade.openedAt ? Math.floor(new Date(trade.openedAt).getTime() / 1000) : null;
    setFocusChartTime(ts && Number.isFinite(ts) ? ts : null);
    setCurrentTab("CHARTS");
  }, []);

  const handlePaired = useCallback(async (creds: PairingCredentials) => {
    await OfflineCache.clearSnapshot();
    candlesCacheRef.current = {};
    drawingsCacheRef.current = {};
    await SecureStorage.setPairingCredentials(creds);
    clientRef.current = new MobileSyncClient(creds);
    setCredentials(creds);
    setSyncDiagnostics(clientRef.current.getDiagnostics());
    setCurrentTab("OVERVIEW");
  }, []);

  const handleUnpair = useCallback(async () => {
    if (clientRef.current) {
      clientRef.current.stopStream();
      await clientRef.current.unpair();
      clientRef.current = null;
    }
    await SecureStorage.clearPairingCredentials();
    await OfflineCache.clearSnapshot();
    setCredentials(null);
    setStatus(null);
    setAccount(null);
    setStats(null);
    setPositions([]);
    setSymbolsData(null);
    setCandlesData(null);
    setDrawings(null);
    setEquity(null);
    setActivity([]);
    setLastSyncedMs(null);
    setProducerUpdatedMs(null);
    setSyncDiagnostics(null);
    setStreamConnected(false);
    setStreamError(false);
  }, []);

  const handleClearCache = useCallback(async () => {
    await OfflineCache.clearSnapshot();
    candlesCacheRef.current = {};
    drawingsCacheRef.current = {};
    if (!streamConnected) {
      setLastSyncedMs(null);
      setProducerUpdatedMs(null);
      setIsShowingCache(false);
    }
  }, [streamConnected]);

  const handleToggleBiometric = useCallback((enabled: boolean) => {
    setBiometricEnabled(enabled);
    SecureStorage.setBiometricLockEnabled(enabled).catch(() => {});
  }, []);

  const tokens = getThemeTokens(theme);

  return (
    <SafeAreaProvider>
      <MobileErrorBoundary>
        <StatusBar style={theme === "dark" ? "light" : "dark"} />
        {locked ? (
          <View style={[styles.lockScreen, { backgroundColor: tokens.background }]}>
            <Text style={[styles.lockTitle, { color: tokens.text }]}>
              Institutional EA Locked
            </Text>
            <Text style={[styles.lockSub, { color: tokens.textMuted }]}>
              Authenticate to access read-only monitoring
            </Text>
            <TouchableOpacity
              onPress={async () => {
                const res = await LocalAuthentication.authenticateAsync({
                  promptMessage: "Unlock Institutional EA",
                });
                if (res.success) setLocked(false);
              }}
              style={[styles.unlockBtn, { backgroundColor: tokens.accent }]}
            >
              <Text style={[styles.unlockText, { color: tokens.accentText }]}>Unlock</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <RootNavigator
            theme={theme}
            onToggleTheme={handleToggleTheme}
            currentTab={currentTab}
            onSelectTab={(tab) => {
              setChartFullscreen(false);
              setCurrentTab(tab);
            }}
            connectionState={deriveConnectionState()}
            botState={status?.botState ?? null}
            lastSyncedMs={producerUpdatedMs ?? lastSyncedMs}
            syncDiagnostics={syncDiagnostics}
            isShowingCache={isShowingCache}
            onRetryConnection={startLiveSync}
            credentials={credentials}
            client={clientRef.current}
            account={account}
            stats={stats}
            positions={positions}
            equity={equity}
            equityRange={equityRange}
            onSelectEquityRange={setEquityRange}
            symbols={symbolsData?.symbols ?? []}
            timeframes={symbolsData?.timeframes ?? ["M1", "M5", "M15", "H1", "H4"]}
            selectedSymbol={selectedSymbol}
            selectedTimeframe={selectedTimeframe}
            onSelectSymbol={setSelectedSymbol}
            onSelectTimeframe={setSelectedTimeframe}
            candlesData={candlesData}
            drawings={drawings}
            layers={layers}
            onToggleLayer={handleToggleLayer}
            activity={activity}
            isLoading={isLoading}
            isRefreshing={isRefreshing}
            onRefresh={() => fetchFullSnapshot(true)}
            chartFullscreen={chartFullscreen}
            onToggleChartFullscreen={() => setChartFullscreen((f) => !f)}
            focusChartTime={focusChartTime}
            onShowPositionOnChart={handleShowPositionOnChart}
            onShowTradeOnChart={handleShowTradeOnChart}
            onLoadMoreHistory={handleLoadMoreHistory}
            biometricEnabled={biometricEnabled}
            onToggleBiometric={handleToggleBiometric}
            onPaired={handlePaired}
            onUnpair={handleUnpair}
            onClearCache={handleClearCache}
          />
        )}
      </MobileErrorBoundary>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  lockScreen: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
    gap: 12,
  },
  lockTitle: {
    fontSize: 20,
    fontWeight: "800",
  },
  lockSub: {
    fontSize: 13,
    textAlign: "center",
  },
  unlockBtn: {
    marginTop: 8,
    paddingHorizontal: 28,
    paddingVertical: 13,
    borderRadius: 12,
    minHeight: 48,
  },
  unlockText: {
    fontSize: 15,
    fontWeight: "800",
  },
});
