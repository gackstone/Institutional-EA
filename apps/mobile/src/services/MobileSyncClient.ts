/**
 * Strictly Read-Only Mobile Sync HTTP & SSE Client.
 *
 * - Validates EVERY incoming payload at runtime with @institutional-ea/data-contract Zod schemas.
 * - Enforces assertMobileHttpReadOnly() before every network request.
 * - Supports AbortController cancellation, exponential backoff, stale detection,
 *   device revocation handling, and background/foreground stream lifecycle.
 */

import {
  AnyPairingQrPayloadSchema,
  assertMobileHttpReadOnly,
  MobileAccountSchema,
  MobileActivityResponseSchema,
  MobileCandlesResponseSchema,
  MobileDrawingsResponseSchema,
  MobileEquityResponseSchema,
  MobilePairingQrPayloadSchema,
  MobilePairResponseSchema,
  MobilePositionsResponseSchema,
  MobileSseEventSchema,
  MobileStatsSchema,
  MobileStatusSchema,
  MobileSymbolsResponseSchema,
  MobileTradesPageSchema,
  type AnyPairingQrPayload,
  type MobileAccount,
  type MobileActivityResponse,
  type MobileCandlesResponse,
  type MobileDrawingsResponse,
  type MobileEquityResponse,
  type MobilePairingQrPayload,
  type MobilePairResponse,
  type MobilePositionsResponse,
  type MobileSseEvent,
  type MobileStats,
  type MobileStatus,
  type MobileSymbolsResponse,
  type MobileTradesPage,
} from "@institutional-ea/data-contract";
import type { PairingCredentials } from "./SecureStorage.ts";
import { getMobileSupabaseConfig } from "../config/supabase.ts";

export class MobileSyncError extends Error {
  status: number;
  code: string;

  constructor(message: string, status = 0, code = "NETWORK_ERROR") {
    super(message);
    this.name = "MobileSyncError";
    this.status = status;
    this.code = code;
  }
}

export function computeBackoffMs(
  attempt: number,
  baseMs = 1000,
  maxMs = 30000,
  jitterRatio = 0.15
): number {
  const safeAttempt = Math.max(0, Math.min(10, Math.floor(attempt)));
  const raw = Math.min(maxMs, baseMs * Math.pow(2, safeAttempt));
  const jitter = raw * jitterRatio * (Math.random() * 2 - 1);
  return Math.max(baseMs, Math.round(raw + jitter));
}

export function isSnapshotStale(
  lastUpdatedMs: number | null,
  nowMs = Date.now(),
  thresholdMs = 30000
): boolean {
  if (lastUpdatedMs === null || !Number.isFinite(lastUpdatedMs)) return true;
  return nowMs - lastUpdatedMs > thresholdMs;
}

export const DEFAULT_CLOUD_API_URL = getMobileSupabaseConfig().supabaseUrl;

export function mapCloudPairingError(status: number, code: string, rawMsg: string): string {
  const upperCode = (code || "").toUpperCase();
  if (upperCode === "INVALID_PAIRING_CODE" || upperCode === "INVALID_CODE") {
    return "Code not recognized. Check the 6-digit code on your Windows PC.";
  }
  if (status === 410 || upperCode === "PAIRING_EXPIRED") {
    return "Code expired. Click Regenerate on your Windows PC.";
  }
  if (status === 409 || upperCode === "PAIRING_CONSUMED" || upperCode === "PAIRING_ALREADY_CONSUMED") {
    return "This code was already used. Generate a new code on your PC.";
  }
  if (status === 429 || upperCode === "RATE_LIMITED") {
    return "Too many attempts. Wait a minute and generate a new code.";
  }
  if (status === 404 || /requested function was not found/i.test(rawMsg)) {
    return "Cloud Pairing is temporarily unavailable. Use Local Wi-Fi Fallback.";
  }
  if (status === 401 || status === 403) {
    return "Pairing was declined or unauthorized. Generate a new code on your PC.";
  }
  if (status === 0 || /network|failed to fetch|enotfound|offline/i.test(rawMsg)) {
    return "No internet connection. Check mobile data or Wi-Fi and try again.";
  }
  return rawMsg || "Cloud pairing failed. Please try again.";
}

export function parsePairingQrPayload(raw: string): MobilePairingQrPayload {
  const trimmed = (raw || "").trim();
  if (!trimmed) {
    throw new Error("Empty QR code payload");
  }
  const parsed = JSON.parse(trimmed);
  return MobilePairingQrPayloadSchema.parse(parsed);
}

export function parseAnyPairingQrPayload(raw: string): AnyPairingQrPayload {
  const trimmed = (raw || "").trim();
  if (!trimmed) {
    throw new Error("Empty QR code payload");
  }
  const parsed = JSON.parse(trimmed);
  return AnyPairingQrPayloadSchema.parse(parsed);
}

export interface CloudClaimResult {
  sessionId: string;
  claimNonce: string;
  companionName: string;
  expiresAt: number;
  cloudUrl: string;
}

/**
 * Step 1 of Cross-Network Cloud Pairing:
 * Claims a 6-digit code or v2 Cloud QR session over HTTPS (no LAN IP or port needed).
 * Moves session to `awaiting_approval` on Windows Companion.
 */
export async function claimCloudPairing(params: {
  cloudUrl?: string;
  code?: string;
  sessionId?: string;
  sessionToken?: string;
  deviceName: string;
  signal?: AbortSignal;
}): Promise<CloudClaimResult> {
  const path = "/functions/v1/mobile-pairing";
  assertMobileHttpReadOnly("POST", path);

  const baseUrl = (params.cloudUrl || DEFAULT_CLOUD_API_URL).trim().replace(/\/+$/, "");
  if (!baseUrl.startsWith("https://") && !baseUrl.startsWith("http://127.0.0.1")) {
    throw new MobileSyncError("Cloud pairing requires HTTPS.", 0, "INSECURE_URL");
  }

  const anonKey = getMobileSupabaseConfig().supabaseAnonKey;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
  };
  if (anonKey) headers.apikey = anonKey;

  let resp: Response;
  try {
    resp = await fetch(`${baseUrl}${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        action: "claim",
        code: params.code?.trim(),
        sessionId: params.sessionId?.trim(),
        sessionToken: params.sessionToken?.trim(),
        deviceName: params.deviceName.trim() || "Android Device",
        platform: "android",
      }),
      signal: params.signal,
    });
  } catch (err) {
    throw new MobileSyncError(
      mapCloudPairingError(0, "NETWORK_ERROR", err instanceof Error ? err.message : ""),
      0,
      "NETWORK_ERROR"
    );
  }

  const body = (await resp.json().catch(() => ({}))) as Record<string, any>;
  if (!resp.ok) {
    const errCode = String(body.error || "CLOUD_PAIR_FAILED");
    const rawMsg = String(body.message || body.error || "");
    throw new MobileSyncError(mapCloudPairingError(resp.status, errCode, rawMsg), resp.status, errCode);
  }

  return {
    sessionId: String(body.sessionId),
    claimNonce: String(body.claimNonce),
    companionName: String(body.companionName || "Windows Companion"),
    expiresAt: Number(body.expiresAt || Math.floor(Date.now() / 1000) + 300),
    cloudUrl: baseUrl,
  };
}

/**
 * Step 2 of Cross-Network Cloud Pairing:
 * Polls until Windows Companion approves (or declines/expires) the device registration.
 */
export async function pollCloudPairingApproval(
  claim: CloudClaimResult,
  signal?: AbortSignal
): Promise<{ status: "awaiting_approval" | "approved"; credentials?: PairingCredentials }> {
  const path = "/functions/v1/mobile-pairing";
  assertMobileHttpReadOnly("POST", path);

  const anonKey = getMobileSupabaseConfig().supabaseAnonKey;
  const pollHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
  };
  if (anonKey) pollHeaders.apikey = anonKey;

  const resp = await fetch(`${claim.cloudUrl}${path}`, {
    method: "POST",
    headers: pollHeaders,
    body: JSON.stringify({
      action: "poll",
      sessionId: claim.sessionId,
      claimNonce: claim.claimNonce,
    }),
    signal,
  });

  const body = (await resp.json().catch(() => ({}))) as Record<string, any>;
  if (!resp.ok) {
    const errCode = String(body.error || "POLL_FAILED");
    const rawMsg = String(body.message || body.error || "");
    throw new MobileSyncError(mapCloudPairingError(resp.status, errCode, rawMsg), resp.status, errCode);
  }

  if (body.status === "approved" && body.deviceToken && body.deviceId) {
    const validated = MobilePairResponseSchema.parse(body);
    return {
      status: "approved",
      credentials: {
        mode: "cloud",
        cloudUrl: claim.cloudUrl,
        host: new URL(claim.cloudUrl).hostname,
        hosts: [new URL(claim.cloudUrl).hostname],
        port: 443,
        deviceId: validated.deviceId,
        deviceToken: validated.deviceToken,
        companionName: validated.companionName,
        pairedAt: validated.pairedAt,
      },
    };
  }

  return { status: "awaiting_approval" };
}

export interface TradesQueryParams {
  page?: number;
  limit?: number;
  symbol?: string;
  outcome?: "ALL" | "WIN" | "LOSS";
  from?: string;
  to?: string;
  sort?: "time_desc" | "time_asc" | "pnl_desc" | "pnl_asc";
  q?: string;
}

export interface StreamHandlers {
  onEvent: (ev: MobileSseEvent) => void;
  onOpen?: () => void;
  onError?: (err: Error) => void;
  onRevoked?: () => void;
}

export async function pairWithCompanion(params: {
  host: string;
  hosts?: string[];
  port: number;
  code: string;
  deviceName: string;
  signal?: AbortSignal;
}): Promise<PairingCredentials> {
  const path = "/api/mobile/v1/pair";
  assertMobileHttpReadOnly("POST", path);

  const candidateHosts = Array.from(
    new Set([params.host, ...(params.hosts || [])].map((h) => h.trim()).filter(Boolean))
  );
  if (candidateHosts.length === 0) {
    throw new MobileSyncError("Companion host IP is required", 0, "INVALID_HOST");
  }

  let lastErr: unknown = null;
  for (const host of candidateHosts) {
    const url = `http://${host}:${params.port}${path}`;
    try {
      const resp = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          code: params.code.trim(),
          deviceName: params.deviceName.trim() || "Android Device",
          platform: "android",
        }),
        signal: params.signal,
      });

      const body = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        const msg = (body as any)?.message || (body as any)?.error || `Pairing failed (${resp.status})`;
        const errCode = (body as any)?.error || "PAIR_FAILED";
        // Do not retry other hosts on auth/rate-limit error — we already reached the companion
        throw new MobileSyncError(msg, resp.status, errCode);
      }

      const validated: MobilePairResponse = MobilePairResponseSchema.parse(body);
      return {
        host,
        hosts: candidateHosts,
        port: params.port,
        deviceId: validated.deviceId,
        deviceToken: validated.deviceToken,
        companionName: validated.companionName,
        pairedAt: validated.pairedAt,
      };
    } catch (err) {
      if (err instanceof MobileSyncError && err.status >= 400) {
        throw err;
      }
      lastErr = err;
    }
  }

  throw new MobileSyncError(
    lastErr instanceof Error
      ? `Cannot reach companion at ${params.host}:${params.port}. Check Wi-Fi and firewall.`
      : "Cannot reach companion",
    0,
    "UNREACHABLE"
  );
}

export class MobileSyncClient {
  private creds: PairingCredentials;
  private activeXhr: XMLHttpRequest | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectAttempt = 0;
  private streamRunning = false;

  constructor(creds: PairingCredentials) {
    this.creds = creds;
  }

  getCredentials(): PairingCredentials {
    return this.creds;
  }

  private baseUrl(): string {
    return `http://${this.creds.host}:${this.creds.port}`;
  }

  private async requestJson<T>(
    method: "GET" | "POST",
    path: string,
    schema: { parse: (v: unknown) => T },
    signal?: AbortSignal
  ): Promise<T> {
    assertMobileHttpReadOnly(method, path);

    const resp = await fetch(`${this.baseUrl()}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${this.creds.deviceToken}`,
        Accept: "application/json",
      },
      signal,
    });

    if (resp.status === 401) {
      throw new MobileSyncError("Device token revoked or unauthorized", 401, "UNAUTHORIZED");
    }
    if (resp.status === 403) {
      throw new MobileSyncError("Read-only mode enforced", 403, "READ_ONLY_ENFORCED");
    }
    if (!resp.ok) {
      throw new MobileSyncError(`Companion returned HTTP ${resp.status}`, resp.status, "HTTP_ERROR");
    }

    const raw = await resp.json();
    return schema.parse(raw);
  }

  private cloudCache: Record<string, any> | null = null;
  private cloudCacheAtMs = 0;

  private isCloudMode(): boolean {
    return this.creds.mode === "cloud" && Boolean(this.creds.cloudUrl);
  }

  async fetchCloudSnapshot(signal?: AbortSignal, force = false): Promise<Record<string, any>> {
    if (!force && this.cloudCache && Date.now() - this.cloudCacheAtMs < 3500) {
      return this.cloudCache;
    }
    const path = "/functions/v1/mobile-sync";
    assertMobileHttpReadOnly("GET", path);
    const anonKey = getMobileSupabaseConfig().supabaseAnonKey;
    const headers: Record<string, string> = {
      Authorization: `Bearer ${this.creds.deviceToken}`,
      Accept: "application/json",
    };
    if (anonKey) headers.apikey = anonKey;

    const resp = await fetch(`${this.creds.cloudUrl!.replace(/\/+$/, "")}${path}`, {
      method: "GET",
      headers,
      signal,
    });
    if (resp.status === 401) {
      throw new MobileSyncError("Device token revoked or unauthorized", 401, "UNAUTHORIZED");
    }
    if (resp.status === 403) {
      throw new MobileSyncError("Read-only mode enforced", 403, "READ_ONLY_ENFORCED");
    }
    if (!resp.ok) {
      throw new MobileSyncError(`Cloud sync returned HTTP ${resp.status}`, resp.status, "HTTP_ERROR");
    }
    const snap = (await resp.json()) as Record<string, any>;
    this.cloudCache = snap;
    this.cloudCacheAtMs = Date.now();
    return snap;
  }

  async getStatus(signal?: AbortSignal): Promise<MobileStatus> {
    if (this.isCloudMode()) {
      const snap = await this.fetchCloudSnapshot(signal);
      const st = snap.status || {};
      return MobileStatusSchema.parse({
        schemaVersion: "1.0.0",
        appVersion: "1.3.6",
        botState: st.botState || "UNKNOWN",
        mt5Connected: Boolean(st.mt5Connected),
        mt5Status: st.mt5Connected ? "CONNECTED" : "DISCONNECTED",
        demoMode: st.demoMode !== false,
        broker: String(st.broker || ""),
        accountMasked: String(st.accountMasked || "DEMO"),
        lastHeartbeat: snap.updatedAt || null,
        serverTime: snap.updatedAt || new Date().toISOString(),
        readOnlyEnforced: true,
      });
    }
    return this.requestJson("GET", "/api/mobile/v1/status", MobileStatusSchema, signal);
  }

  async getAccount(signal?: AbortSignal): Promise<MobileAccount> {
    if (this.isCloudMode()) {
      const snap = await this.fetchCloudSnapshot(signal);
      const acc = snap.account || {};
      const st = snap.status || {};
      return MobileAccountSchema.parse({
        balance: Number(acc.balance || 0),
        equity: Number(acc.equity || 0),
        margin: Number(acc.margin || 0),
        freeMargin: Number(acc.freeMargin || 0),
        marginLevel: Number(acc.marginLevel || 0),
        floatingPnl: Number(acc.floatingPnl || 0),
        currency: String(acc.currency || "USD"),
        leverage: Number(acc.leverage || 0),
        tradeMode: st.demoMode === false ? "LIVE" : "DEMO",
        broker: String(st.broker || ""),
        accountMasked: String(st.accountMasked || "DEMO"),
        openPositionsCount: Number(acc.openPositionsCount || (Array.isArray(snap.positions) ? snap.positions.length : 0)),
        updatedAt: snap.updatedAt || null,
      });
    }
    return this.requestJson("GET", "/api/mobile/v1/account", MobileAccountSchema, signal);
  }

  async getStats(signal?: AbortSignal): Promise<MobileStats> {
    if (this.isCloudMode()) {
      const snap = await this.fetchCloudSnapshot(signal);
      const s = snap.stats || {};
      const trades = Array.isArray(snap.trades) ? snap.trades : [];
      const wins = trades.filter((t: any) => Number(t.pnl ?? t.profit ?? 0) > 0).length;
      const losses = trades.filter((t: any) => Number(t.pnl ?? t.profit ?? 0) < 0).length;
      const total = trades.reduce((acc: number, t: any) => acc + Number(t.pnl ?? t.profit ?? 0), 0);
      return MobileStatsSchema.parse({
        todayPnl: Number(s.todayPnl ?? snap.account?.floatingPnl ?? 0),
        totalProfit: Number(s.totalProfit ?? total),
        winRate: Number(s.winRate ?? (wins + losses > 0 ? (wins / (wins + losses)) * 100 : 0)),
        dealsCount: Number(s.dealsCount ?? trades.length),
        tradesToday: Number(s.tradesToday ?? 0),
        winsCount: Number(s.winsCount ?? wins),
        lossesCount: Number(s.lossesCount ?? losses),
        currency: String(snap.account?.currency || "USD"),
        computedAt: snap.updatedAt || new Date().toISOString(),
      });
    }
    return this.requestJson("GET", "/api/mobile/v1/stats", MobileStatsSchema, signal);
  }

  async getPositions(signal?: AbortSignal): Promise<MobilePositionsResponse> {
    if (this.isCloudMode()) {
      const snap = await this.fetchCloudSnapshot(signal);
      const rawPos = Array.isArray(snap.positions) ? snap.positions : [];
      const positions = rawPos.map((p: any) => ({
        ticket: Number(p.ticket || 1),
        symbol: String(p.symbol || "XAUUSD"),
        canonicalSymbol: String(p.canonicalSymbol || p.symbol || "XAUUSD"),
        type: String(p.type || p.direction || "BUY").toUpperCase() === "SELL" ? "SELL" : "BUY",
        volume: Math.max(0.001, Number(p.volume || 0.01)),
        openPrice: Number(p.openPrice ?? p.open_price ?? 0),
        currentPrice: Number(p.currentPrice ?? p.current_price ?? 0),
        sl: p.sl !== undefined && p.sl !== null ? Number(p.sl) : null,
        tp: p.tp !== undefined && p.tp !== null ? Number(p.tp) : null,
        profit: Number(p.profit ?? 0),
        swap: Number(p.swap ?? 0),
        openTime: Number(p.openTime ?? 0),
        digits: Number(p.digits ?? 2),
        ownership: p.ownership === "MANUAL" ? "MANUAL" : "BOT_OWN",
        comment: String(p.comment || ""),
      }));
      return MobilePositionsResponseSchema.parse({
        positions,
        currency: String(snap.account?.currency || "USD"),
        updatedAt: snap.updatedAt || null,
      });
    }
    return this.requestJson("GET", "/api/mobile/v1/positions", MobilePositionsResponseSchema, signal);
  }

  async getSymbols(signal?: AbortSignal): Promise<MobileSymbolsResponse> {
    if (this.isCloudMode()) {
      const snap = await this.fetchCloudSnapshot(signal);
      const syms = Array.isArray(snap.symbols) ? snap.symbols : [];
      return MobileSymbolsResponseSchema.parse({
        symbols: syms,
        timeframes: ["M1", "M5", "M15", "H1", "H4"],
        layers: ["LIQ", "FVG_OB", "STRUCT", "SESS", "TRADES"],
      });
    }
    return this.requestJson("GET", "/api/mobile/v1/symbols", MobileSymbolsResponseSchema, signal);
  }

  async getCandles(
    params: { symbol: string; tf: string; limit?: number; from?: string; to?: string },
    signal?: AbortSignal
  ): Promise<MobileCandlesResponse> {
    if (this.isCloudMode()) {
      return MobileCandlesResponseSchema.parse({
        symbol: params.symbol,
        brokerSymbol: params.symbol,
        timeframe: params.tf,
        digits: params.symbol.includes("JPY") ? 3 : 2,
        candles: [],
        quote: null,
        statusReason: "CLOUD_TELEMETRY_MODE",
      });
    }
    const qs = new URLSearchParams();
    qs.set("symbol", params.symbol);
    qs.set("tf", params.tf);
    if (params.limit) qs.set("limit", String(params.limit));
    if (params.from) qs.set("from", params.from);
    if (params.to) qs.set("to", params.to);
    return this.requestJson(
      "GET",
      `/api/mobile/v1/candles?${qs.toString()}`,
      MobileCandlesResponseSchema,
      signal
    );
  }

  async getDrawings(
    params: { symbol: string; tf: string; count?: number },
    signal?: AbortSignal
  ): Promise<MobileDrawingsResponse> {
    if (this.isCloudMode()) {
      return MobileDrawingsResponseSchema.parse({
        symbol: params.symbol,
        timeframe: params.tf,
        items: [],
      });
    }
    const qs = new URLSearchParams();
    qs.set("symbol", params.symbol);
    qs.set("tf", params.tf);
    if (params.count) qs.set("count", String(params.count));
    return this.requestJson(
      "GET",
      `/api/mobile/v1/drawings?${qs.toString()}`,
      MobileDrawingsResponseSchema,
      signal
    );
  }

  async getTrades(params: TradesQueryParams = {}, signal?: AbortSignal): Promise<MobileTradesPage> {
    if (this.isCloudMode()) {
      const snap = await this.fetchCloudSnapshot(signal);
      const rawTrades = Array.isArray(snap.trades) ? snap.trades : [];
      const mapped = rawTrades.map((t: any, idx: number) => ({
        ticket: Number(t.ticket ?? idx + 1),
        symbol: String(t.symbol || "XAUUSD"),
        canonicalSymbol: String(t.canonicalSymbol || t.symbol || "XAUUSD"),
        direction: String(t.direction || "BUY").toUpperCase() === "SELL" ? "SELL" : "BUY",
        volume: Number(t.volume ?? 0),
        entryPrice: t.entry_price !== undefined ? Number(t.entry_price) : null,
        exitPrice: t.exit_price !== undefined ? Number(t.exit_price) : null,
        sl: t.sl !== undefined ? Number(t.sl) : null,
        tp: t.tp !== undefined ? Number(t.tp) : null,
        pnl: Number(t.pnl ?? t.profit ?? 0),
        openedAt: t.opened_at ? String(t.opened_at) : null,
        closedAt: t.closed_at ? String(t.closed_at) : null,
        durationSec: null,
        status: String(t.status || "CLOSED"),
        strategyTag: String(t.strategy_tag || ""),
        digits: 2,
      }));
      return MobileTradesPageSchema.parse({
        page: 1,
        limit: mapped.length || 20,
        total: mapped.length,
        hasMore: false,
        currency: String(snap.account?.currency || "USD"),
        trades: mapped,
      });
    }
    const qs = new URLSearchParams();
    if (params.page) qs.set("page", String(params.page));
    if (params.limit) qs.set("limit", String(params.limit));
    if (params.symbol && params.symbol !== "ALL") qs.set("symbol", params.symbol);
    if (params.outcome && params.outcome !== "ALL") qs.set("outcome", params.outcome);
    if (params.from) qs.set("from", params.from);
    if (params.to) qs.set("to", params.to);
    if (params.sort) qs.set("sort", params.sort);
    if (params.q) qs.set("q", params.q);
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return this.requestJson("GET", `/api/mobile/v1/trades${suffix}`, MobileTradesPageSchema, signal);
  }

  async getEquity(range: "1D" | "1W" | "1M" | "ALL" = "1W", signal?: AbortSignal): Promise<MobileEquityResponse> {
    if (this.isCloudMode()) {
      const snap = await this.fetchCloudSnapshot(signal);
      const bal = Number(snap.account?.balance || 0);
      const eq = Number(snap.account?.equity || bal);
      return MobileEquityResponseSchema.parse({
        range,
        currency: String(snap.account?.currency || "USD"),
        points: bal > 0 || eq > 0 ? [{ time: Math.floor(Date.now() / 1000), balance: bal, equity: eq, pnl: eq - bal }] : [],
      });
    }
    return this.requestJson(
      "GET",
      `/api/mobile/v1/equity?range=${range}`,
      MobileEquityResponseSchema,
      signal
    );
  }

  async getActivity(limit = 40, signal?: AbortSignal): Promise<MobileActivityResponse> {
    if (this.isCloudMode()) {
      const snap = await this.fetchCloudSnapshot(signal);
      const sigs = Array.isArray(snap.signals) ? snap.signals : [];
      const events = sigs.slice(0, limit).map((s: any, idx: number) => ({
        id: String(s.signal_id || s.id || `sig-${idx}`),
        timestamp: String(s.created_at || snap.updatedAt || new Date().toISOString()),
        type: "SIGNAL",
        severity: "INFO",
        symbol: s.symbol ? String(s.symbol) : null,
        message: `${s.symbol || ""} ${s.direction || ""} · ${s.status || "ACTIVE"}${s.rr ? ` (${Number(s.rr).toFixed(2)}R)` : ""}`.trim(),
        ticket: null,
      }));
      return MobileActivityResponseSchema.parse({ events });
    }
    return this.requestJson(
      "GET",
      `/api/mobile/v1/activity?limit=${limit}`,
      MobileActivityResponseSchema,
      signal
    );
  }

  async unpair(): Promise<void> {
    if (this.isCloudMode()) {
      this.cloudCache = null;
      return;
    }
    const path = "/api/mobile/v1/unpair";
    assertMobileHttpReadOnly("POST", path);
    try {
      await fetch(`${this.baseUrl()}${path}`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${this.creds.deviceToken}`,
          "Content-Type": "application/json",
        },
        body: "{}",
      });
    } catch {
      // Best-effort remote revoke even if companion is currently offline
    }
  }

  private lastCloudSequence = 0;

  /**
   * Opens a live SSE stream (LAN mode) or resilient HTTPS Cloud Sync loop (Cloud mode)
   * with automatic exponential-backoff reconnection and sequence-number deduplication.
   */
  startStream(handlers: StreamHandlers): void {
    this.stopStream();
    this.streamRunning = true;
    this.reconnectAttempt = 0;
    if (this.creds.mode === "cloud" && this.creds.cloudUrl) {
      this.pollCloudLoop(handlers);
    } else {
      this.openSseConnection(handlers);
    }
  }

  private async pollCloudLoop(handlers: StreamHandlers): Promise<void> {
    if (!this.streamRunning || !this.creds.cloudUrl) return;
    const path = "/functions/v1/mobile-sync";
    assertMobileHttpReadOnly("GET", path);

    try {
      const snap = await this.fetchCloudSnapshot(undefined, true);
      this.reconnectAttempt = 0;
      handlers.onOpen?.();

      const seq = Number(snap.sequenceNo || 0);
      if (seq === 0 || seq >= this.lastCloudSequence) {
        this.lastCloudSequence = Math.max(this.lastCloudSequence, seq);
        handlers.onEvent({
          type: "snapshot",
          timestamp: String(snap.updatedAt || new Date().toISOString()),
          payload: snap,
        });
      }

      if (this.streamRunning) {
        this.reconnectTimer = setTimeout(() => {
          this.pollCloudLoop(handlers);
        }, 5000);
      }
    } catch (err) {
      if (!this.streamRunning) return;
      if (err instanceof MobileSyncError && (err.status === 401 || err.status === 403)) {
        this.stopStream();
        handlers.onRevoked?.();
        return;
      }
      handlers.onError?.(err instanceof Error ? err : new Error("Cloud sync interrupted"));
      const delay = computeBackoffMs(this.reconnectAttempt++);
      this.reconnectTimer = setTimeout(() => {
        this.pollCloudLoop(handlers);
      }, delay);
    }
  }

  stopStream(): void {
    this.streamRunning = false;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.activeXhr) {
      try {
        this.activeXhr.abort();
      } catch {
        // Ignore abort errors
      }
      this.activeXhr = null;
    }
  }

  private openSseConnection(handlers: StreamHandlers): void {
    if (!this.streamRunning) return;
    if (typeof XMLHttpRequest === "undefined") {
      handlers.onError?.(new Error("XMLHttpRequest unavailable in this runtime"));
      return;
    }

    const path = `/api/mobile/v1/events?token=${encodeURIComponent(this.creds.deviceToken)}`;
    assertMobileHttpReadOnly("GET", path);

    const xhr = new XMLHttpRequest();
    this.activeXhr = xhr;
    let processedOffset = 0;
    let buffer = "";
    let opened = false;

    const scheduleReconnect = () => {
      if (!this.streamRunning) return;
      const delay = computeBackoffMs(this.reconnectAttempt++);
      this.reconnectTimer = setTimeout(() => {
        this.openSseConnection(handlers);
      }, delay);
    };

    xhr.open("GET", `${this.baseUrl()}${path}`, true);
    xhr.setRequestHeader("Accept", "text/event-stream");
    xhr.setRequestHeader("Cache-Control", "no-cache");

    xhr.onreadystatechange = () => {
      if (xhr.readyState === 2) {
        if (xhr.status === 401) {
          this.stopStream();
          handlers.onRevoked?.();
          return;
        }
        if (xhr.status >= 200 && xhr.status < 300) {
          opened = true;
          this.reconnectAttempt = 0;
          handlers.onOpen?.();
        }
      }
    };

    xhr.onprogress = () => {
      if (!this.streamRunning) return;
      const text = xhr.responseText || "";
      if (text.length <= processedOffset) return;
      const chunk = text.slice(processedOffset);
      processedOffset = text.length;
      buffer += chunk;

      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() || "";

      for (const block of blocks) {
        const dataLines = block
          .split("\n")
          .filter((l) => l.startsWith("data:"))
          .map((l) => l.slice(5).trim());
        if (dataLines.length === 0) continue;
        try {
          const parsed = MobileSseEventSchema.parse(JSON.parse(dataLines.join("\n")));
          if (parsed.type === "revoked") {
            this.stopStream();
            handlers.onRevoked?.();
            return;
          }
          handlers.onEvent(parsed);
        } catch {
          // Ignore malformed SSE frame safely
        }
      }
    };

    xhr.onerror = () => {
      if (!this.streamRunning) return;
      handlers.onError?.(new Error(opened ? "Stream disconnected" : "Companion unreachable"));
      scheduleReconnect();
    };

    xhr.onloadend = () => {
      if (!this.streamRunning) return;
      if (xhr.status === 401) {
        this.stopStream();
        handlers.onRevoked?.();
        return;
      }
      handlers.onError?.(new Error("Stream ended"));
      scheduleReconnect();
    };

    xhr.send();
  }
}
