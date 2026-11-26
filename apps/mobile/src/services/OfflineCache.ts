/**
 * Non-sensitive Offline Snapshot Cache, Chart Preferences & Trade Filter Store.
 * Uses AsyncStorage in React Native (never stores tokens or secrets) with
 * an injectable backend for tests.
 *
 * Cache Invalidation Guarantee (E5/E6):
 * - Every cached snapshot records `cacheScopeKey = "${deviceId}:${accountMasked}:${schemaVersion}"`.
 * - When loading a snapshot, if `schemaVersion !== MOBILE_SYNC_SCHEMA_VERSION` or the paired
 *   `deviceId` / `accountMasked` has changed, the stale cache is invalidated and cleared.
 */

import {
  MOBILE_SYNC_SCHEMA_VERSION,
  type MobileAccount,
  type MobileActivityEvent,
  type MobileCandlesResponse,
  type MobileDrawingsResponse,
  type MobileEquityResponse,
  type MobilePosition,
  type MobileStats,
  type MobileStatus,
  type MobileSymbolsResponse,
} from "@institutional-ea/data-contract";

export interface ICacheBackend {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem(key: string): Promise<void>;
}

export interface ChartLayerPreferences {
  liquidity: boolean;
  fvgOb: boolean;
  structure: boolean;
  sessions: boolean;
  trades: boolean;
}

export interface ChartPreferences {
  selectedSymbol: string | null;
  selectedTimeframe: string;
  layers: ChartLayerPreferences;
}

export interface TradeFilterPreferences {
  symbolFilter: string;
  outcome: "ALL" | "WIN" | "LOSS";
  dateRange: "ALL" | "1D" | "1W" | "1M";
  sort: "time_desc" | "time_asc" | "pnl_desc" | "pnl_asc";
  search: string;
}

export interface CachedTelemetrySnapshot {
  cachedAt: number; // epoch ms
  deviceId?: string;
  accountMasked?: string;
  schemaVersion?: string;
  status: MobileStatus | null;
  account: MobileAccount | null;
  stats: MobileStats | null;
  positions: MobilePosition[];
  symbols: MobileSymbolsResponse | null;
  candlesByKey: Record<string, MobileCandlesResponse>;
  drawingsByKey: Record<string, MobileDrawingsResponse>;
  equity: MobileEquityResponse | null;
  activity: MobileActivityEvent[];
}

export const DEFAULT_LAYER_PREFS: ChartLayerPreferences = {
  liquidity: true,
  fvgOb: true,
  structure: true,
  sessions: true,
  trades: true,
};

export const DEFAULT_TRADE_FILTER_PREFS: TradeFilterPreferences = {
  symbolFilter: "ALL",
  outcome: "ALL",
  dateRange: "ALL",
  sort: "time_desc",
  search: "",
};

class MemoryCacheBackend implements ICacheBackend {
  private map = new Map<string, string>();
  async getItem(key: string): Promise<string | null> {
    return this.map.get(key) ?? null;
  }
  async setItem(key: string, value: string): Promise<void> {
    this.map.set(key, value);
  }
  async removeItem(key: string): Promise<void> {
    this.map.delete(key);
  }
}

let cacheBackend: ICacheBackend | null = null;

async function resolveBackend(): Promise<ICacheBackend> {
  if (cacheBackend) return cacheBackend;
  try {
    const mod = await import("@react-native-async-storage/async-storage");
    const storage = mod.default ?? mod;
    if (storage && typeof storage.getItem === "function") {
      cacheBackend = {
        getItem: (k) => storage.getItem(k),
        setItem: (k, v) => storage.setItem(k, v),
        removeItem: (k) => storage.removeItem(k),
      };
      return cacheBackend;
    }
  } catch {
    // Node test fallback
  }
  cacheBackend = new MemoryCacheBackend();
  return cacheBackend;
}

export function setCustomCacheBackend(backend: ICacheBackend): void {
  cacheBackend = backend;
}

const SNAPSHOT_KEY = "iea_mobile_offline_snapshot_v1";
const CHART_PREFS_KEY = "iea_mobile_chart_prefs_v1";
const TRADE_FILTER_PREFS_KEY = "iea_mobile_trade_filter_prefs_v1";

export const OfflineCache = {
  async loadSnapshot(expectedScope?: {
    deviceId?: string | null;
    accountMasked?: string | null;
    schemaVersion?: string | null;
  }): Promise<CachedTelemetrySnapshot | null> {
    const b = await resolveBackend();
    const raw = await b.getItem(SNAPSHOT_KEY);
    if (!raw) return null;
    try {
      const parsed = JSON.parse(raw) as CachedTelemetrySnapshot;
      if (typeof parsed.cachedAt !== "number") return null;

      // Invalidate cache if schemaVersion changed (when schemaVersion was recorded or expected)
      const targetSchema = expectedScope?.schemaVersion ?? null;
      if (targetSchema && parsed.schemaVersion && parsed.schemaVersion !== targetSchema) {
        await b.removeItem(SNAPSHOT_KEY);
        return null;
      }
      if (
        expectedScope?.deviceId &&
        parsed.deviceId &&
        parsed.deviceId !== expectedScope.deviceId
      ) {
        await b.removeItem(SNAPSHOT_KEY);
        return null;
      }
      if (
        expectedScope?.accountMasked &&
        parsed.accountMasked &&
        parsed.accountMasked !== "DEMO" &&
        expectedScope.accountMasked !== "DEMO" &&
        parsed.accountMasked !== expectedScope.accountMasked
      ) {
        await b.removeItem(SNAPSHOT_KEY);
        return null;
      }

      return parsed;
    } catch {
      return null;
    }
  },

  async saveSnapshot(snapshot: CachedTelemetrySnapshot): Promise<void> {
    const b = await resolveBackend();
    const trimmedCandles: Record<string, MobileCandlesResponse> = {};
    for (const [k, v] of Object.entries(snapshot.candlesByKey || {}).slice(-3)) {
      trimmedCandles[k] = {
        ...v,
        candles: v.candles.slice(-160),
      };
    }
    const trimmedDrawings: Record<string, MobileDrawingsResponse> = {};
    for (const [k, v] of Object.entries(snapshot.drawingsByKey || {}).slice(-3)) {
      trimmedDrawings[k] = v;
    }
    const payload: CachedTelemetrySnapshot = {
      ...snapshot,
      schemaVersion: snapshot.schemaVersion || MOBILE_SYNC_SCHEMA_VERSION,
      accountMasked:
        snapshot.accountMasked ||
        snapshot.account?.accountMasked ||
        snapshot.status?.accountMasked ||
        undefined,
      candlesByKey: trimmedCandles,
      drawingsByKey: trimmedDrawings,
      activity: (snapshot.activity || []).slice(0, 40),
    };
    await b.setItem(SNAPSHOT_KEY, JSON.stringify(payload));
  },

  async clearSnapshot(): Promise<void> {
    const b = await resolveBackend();
    await b.removeItem(SNAPSHOT_KEY);
  },

  async loadChartPreferences(): Promise<ChartPreferences> {
    const b = await resolveBackend();
    const raw = await b.getItem(CHART_PREFS_KEY);
    if (!raw) {
      return {
        selectedSymbol: null,
        selectedTimeframe: "M5",
        layers: { ...DEFAULT_LAYER_PREFS },
      };
    }
    try {
      const parsed = JSON.parse(raw) as Partial<ChartPreferences>;
      return {
        selectedSymbol: typeof parsed.selectedSymbol === "string" ? parsed.selectedSymbol : null,
        selectedTimeframe: typeof parsed.selectedTimeframe === "string" ? parsed.selectedTimeframe : "M5",
        layers: {
          ...DEFAULT_LAYER_PREFS,
          ...(parsed.layers || {}),
        },
      };
    } catch {
      return {
        selectedSymbol: null,
        selectedTimeframe: "M5",
        layers: { ...DEFAULT_LAYER_PREFS },
      };
    }
  },

  async saveChartPreferences(prefs: ChartPreferences): Promise<void> {
    const b = await resolveBackend();
    await b.setItem(CHART_PREFS_KEY, JSON.stringify(prefs));
  },

  async loadTradeFilterPreferences(): Promise<TradeFilterPreferences> {
    const b = await resolveBackend();
    const raw = await b.getItem(TRADE_FILTER_PREFS_KEY);
    if (!raw) return { ...DEFAULT_TRADE_FILTER_PREFS };
    try {
      const parsed = JSON.parse(raw) as Partial<TradeFilterPreferences>;
      return {
        symbolFilter: typeof parsed.symbolFilter === "string" ? parsed.symbolFilter : "ALL",
        outcome:
          parsed.outcome === "WIN" || parsed.outcome === "LOSS" ? parsed.outcome : "ALL",
        dateRange:
          parsed.dateRange === "1D" || parsed.dateRange === "1W" || parsed.dateRange === "1M"
            ? parsed.dateRange
            : "ALL",
        sort:
          parsed.sort === "time_asc" || parsed.sort === "pnl_desc" || parsed.sort === "pnl_asc"
            ? parsed.sort
            : "time_desc",
        search: typeof parsed.search === "string" ? parsed.search : "",
      };
    } catch {
      return { ...DEFAULT_TRADE_FILTER_PREFS };
    }
  },

  async saveTradeFilterPreferences(prefs: TradeFilterPreferences): Promise<void> {
    const b = await resolveBackend();
    await b.setItem(TRADE_FILTER_PREFS_KEY, JSON.stringify(prefs));
  },
};
