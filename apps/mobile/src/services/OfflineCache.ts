/**
 * Non-sensitive Offline Snapshot Cache & Chart Preferences Store.
 * Uses AsyncStorage in React Native (never stores tokens or secrets) with
 * an injectable backend for tests.
 *
 * Every cached snapshot records `cachedAt` so UI always labels offline/cached
 * views as "Last synced <time>" and never presents stale cache as live.
 */

import type {
  MobileAccount,
  MobileActivityEvent,
  MobileCandlesResponse,
  MobileDrawingsResponse,
  MobileEquityResponse,
  MobilePosition,
  MobileStats,
  MobileStatus,
  MobileSymbolsResponse,
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

export interface CachedTelemetrySnapshot {
  cachedAt: number; // epoch ms
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

export const OfflineCache = {
  async loadSnapshot(): Promise<CachedTelemetrySnapshot | null> {
    const b = await resolveBackend();
    const raw = await b.getItem(SNAPSHOT_KEY);
    if (!raw) return null;
    try {
      const parsed = JSON.parse(raw) as CachedTelemetrySnapshot;
      if (typeof parsed.cachedAt !== "number") return null;
      return parsed;
    } catch {
      return null;
    }
  },

  async saveSnapshot(snapshot: CachedTelemetrySnapshot): Promise<void> {
    const b = await resolveBackend();
    // Keep cache compact: at most 3 recent symbol/tf candle caches
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
};
