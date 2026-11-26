/**
 * Strictly Read-Only Mobile Sync HTTP & SSE Client (Sync Contract v1.1.0, backward-compatible with v1.0.0).
 *
 * - Validates EVERY incoming payload at runtime with @institutional-ea/data-contract Zod schemas.
 * - Enforces assertMobileHttpReadOnly() before every network request.
 * - Supports AbortController cancellation, exponential backoff, honest producer-timestamp stale detection,
 *   server-side device revocation on unpair, and read-only Sync Diagnostics.
 */

import {
  AnyPairingQrPayloadSchema,
  assertMobileHttpReadOnly,
  checkSyncSchemaCompatibility,
  MOBILE_SYNC_SCHEMA_VERSION,
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
  normalizeDrawingsCounts,
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
  type MobileTradeRecord,
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

/**
 * Maps technical errors (including ZodError, network timeouts, HTTP errors)
 * to concise human-readable messages so raw JSON/Zod stack traces never reach the UI.
 */
export function formatSyncErrorMessage(err: unknown, fallback = "Unable to load companion data. Tap Retry."): string {
  if (!err) return fallback;
  if (err instanceof MobileSyncError) {
    if (err.status === 401) return "Device pairing expired or revoked. Re-pair in Security.";
    if (err.status === 403) return "Read-only access enforced.";
    if (err.status === 429) return "Rate limited. Please wait a moment and retry.";
    if (err.status >= 500) return "Cloud relay temporarily unavailable. Tap Retry.";
    if (err.code === "NETWORK_ERROR" || err.code === "UNREACHABLE") {
      return "Cannot reach companion. Check your network connection.";
    }
    return err.message || fallback;
  }
  const name = (err as any)?.name || "";
  const rawMsg = err instanceof Error ? err.message : String(err);
  if (name === "ZodError" || Array.isArray((err as any)?.issues) || rawMsg.includes('"invalid_type"')) {
    return "Received an incomplete data packet from companion. Tap Retry to resync.";
  }
  if (/network|failed to fetch|timed out|abort|econnrefused|offline/i.test(rawMsg)) {
    return "Network connection interrupted. Tap Retry.";
  }
  return rawMsg.length > 120 ? fallback : rawMsg;
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
  thresholdMs = 45000
): boolean {
  if (lastUpdatedMs === null || !Number.isFinite(lastUpdatedMs) || lastUpdatedMs <= 0) return true;
  return nowMs - lastUpdatedMs > thresholdMs;
}

export function parseIsoToMs(iso: string | null | undefined): number | null {
  if (!iso || typeof iso !== "string") return null;
  const ms = Date.parse(iso);
  return Number.isFinite(ms) && ms > 0 ? ms : null;
}

export function normalizeCanonicalSymbol(raw: string | null | undefined): string {
  const s = String(raw || "").trim().toUpperCase();
  if (!s) return "XAUUSD";
  return s.split(".")[0].replace(/(_SB|_RAW|_ECN|_PRO)$/i, "");
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

export interface SyncDiagnosticsState {
  schemaVersion: string;
  producerSchemaVersion: string;
  producerVersion: string;
  compatible: boolean;
  updateNeeded: boolean;
  compatibilityReason: string;
  sequenceNo: number;
  producerUpdatedAt: string | null;
  lastClientPollAt: string | null;
  queueDepth: number;
  lastErrorCode: string | null;
  lastErrorMessage: string | null;
  streamTimes: {
    status: string | null;
    account: string | null;
    positions: string | null;
    trades: string | null;
    charts: string | null;
    equity: string | null;
  };
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

const DEFAULT_UNIVERSE_SYMBOLS = [
  { symbol: "XAUUSD", brokerSymbol: "XAUUSD.m", digits: 2, point: 0.01, bid: null, ask: null, spreadPoints: null },
  { symbol: "USDJPY", brokerSymbol: "USDJPY.m", digits: 3, point: 0.001, bid: null, ask: null, spreadPoints: null },
  { symbol: "BTCUSD", brokerSymbol: "BTCUSD.m", digits: 2, point: 0.01, bid: null, ask: null, spreadPoints: null },
];

export class MobileSyncClient {
  private creds: PairingCredentials;
  private activeXhr: XMLHttpRequest | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectAttempt = 0;
  private streamRunning = false;
  private inFlightRequests = 0;

  private diagnostics: SyncDiagnosticsState = {
    schemaVersion: MOBILE_SYNC_SCHEMA_VERSION,
    producerSchemaVersion: "1.1.0",
    producerVersion: "1.3.7",
    compatible: true,
    updateNeeded: false,
    compatibilityReason: "Compatible",
    sequenceNo: 0,
    producerUpdatedAt: null,
    lastClientPollAt: null,
    queueDepth: 0,
    lastErrorCode: null,
    lastErrorMessage: null,
    streamTimes: {
      status: null,
      account: null,
      positions: null,
      trades: null,
      charts: null,
      equity: null,
    },
  };

  constructor(creds: PairingCredentials) {
    this.creds = creds;
  }

  getCredentials(): PairingCredentials {
    return this.creds;
  }

  getDiagnostics(): SyncDiagnosticsState {
    return {
      ...this.diagnostics,
      queueDepth: this.inFlightRequests,
      streamTimes: { ...this.diagnostics.streamTimes },
    };
  }

  private recordError(code: string, message: string): void {
    this.diagnostics.lastErrorCode = code;
    this.diagnostics.lastErrorMessage = formatSyncErrorMessage(new MobileSyncError(message, 0, code));
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
    this.inFlightRequests += 1;
    try {
      const resp = await fetch(`${this.baseUrl()}${path}`, {
        method,
        headers: {
          Authorization: `Bearer ${this.creds.deviceToken}`,
          Accept: "application/json",
        },
        signal,
      });

      if (resp.status === 401) {
        this.recordError("UNAUTHORIZED", "Device token revoked or unauthorized");
        throw new MobileSyncError("Device token revoked or unauthorized", 401, "UNAUTHORIZED");
      }
      if (resp.status === 403) {
        this.recordError("READ_ONLY_ENFORCED", "Read-only mode enforced");
        throw new MobileSyncError("Read-only mode enforced", 403, "READ_ONLY_ENFORCED");
      }
      if (!resp.ok) {
        this.recordError(`HTTP_${resp.status}`, `Companion returned HTTP ${resp.status}`);
        throw new MobileSyncError(`Companion returned HTTP ${resp.status}`, resp.status, "HTTP_ERROR");
      }

      const raw = await resp.json();
      this.diagnostics.lastClientPollAt = new Date().toISOString();
      this.diagnostics.lastErrorCode = null;
      this.diagnostics.lastErrorMessage = null;
      return schema.parse(raw);
    } catch (err) {
      if (!(err instanceof MobileSyncError)) {
        this.recordError(
          (err as any)?.name === "ZodError" ? "SCHEMA_PARSE_ERROR" : "NETWORK_ERROR",
          formatSyncErrorMessage(err)
        );
      }
      throw err;
    } finally {
      this.inFlightRequests = Math.max(0, this.inFlightRequests - 1);
    }
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

    this.inFlightRequests += 1;
    try {
      const resp = await fetch(`${this.creds.cloudUrl!.replace(/\/+$/, "")}${path}`, {
        method: "GET",
        headers,
        signal,
      });
      if (resp.status === 401) {
        this.recordError("UNAUTHORIZED", "Device token revoked or unauthorized");
        throw new MobileSyncError("Device token revoked or unauthorized", 401, "UNAUTHORIZED");
      }
      if (resp.status === 403) {
        this.recordError("READ_ONLY_ENFORCED", "Read-only mode enforced");
        throw new MobileSyncError("Read-only mode enforced", 403, "READ_ONLY_ENFORCED");
      }
      if (!resp.ok) {
        this.recordError(`HTTP_${resp.status}`, `Cloud sync returned HTTP ${resp.status}`);
        throw new MobileSyncError(`Cloud sync returned HTTP ${resp.status}`, resp.status, "HTTP_ERROR");
      }
      const snap = (await resp.json()) as Record<string, any>;
      this.cloudCache = snap;
      this.cloudCacheAtMs = Date.now();

      const st = (snap.status && typeof snap.status === "object" ? snap.status : {}) as Record<string, any>;
      const meta = (snap.meta && typeof snap.meta === "object"
        ? snap.meta
        : st._meta && typeof st._meta === "object"
        ? st._meta
        : {}) as Record<string, any>;
      const prodSchema = String(meta.schemaVersion || snap.schemaVersion || st.schemaVersion || "1.0.0");
      const compat = checkSyncSchemaCompatibility(prodSchema, MOBILE_SYNC_SCHEMA_VERSION);

      this.diagnostics.producerSchemaVersion = prodSchema;
      this.diagnostics.producerVersion = String(meta.producerVersion || st.appVersion || "1.3.7");
      this.diagnostics.compatible = compat.compatible;
      this.diagnostics.updateNeeded = compat.updateNeeded;
      this.diagnostics.compatibilityReason = compat.reason;
      this.diagnostics.sequenceNo = Number(snap.sequenceNo || meta.sequenceNo || 0);
      this.diagnostics.producerUpdatedAt = snap.updatedAt || st.lastHeartbeat || null;
      this.diagnostics.lastClientPollAt = new Date().toISOString();
      this.diagnostics.lastErrorCode = null;
      this.diagnostics.lastErrorMessage = null;

      return snap;
    } catch (err) {
      if (!(err instanceof MobileSyncError)) {
        this.recordError("NETWORK_ERROR", formatSyncErrorMessage(err));
      }
      throw err;
    } finally {
      this.inFlightRequests = Math.max(0, this.inFlightRequests - 1);
    }
  }

  async getStatus(signal?: AbortSignal): Promise<MobileStatus> {
    if (this.isCloudMode()) {
      const snap = await this.fetchCloudSnapshot(signal);
      const st = snap.status || {};
      const meta = snap.meta || st._meta || {};
      const res = MobileStatusSchema.parse({
        schemaVersion: String(meta.schemaVersion || snap.schemaVersion || st.schemaVersion || MOBILE_SYNC_SCHEMA_VERSION),
        appVersion: String(meta.producerVersion || st.appVersion || "1.3.7"),
        botState: st.botState || "UNKNOWN",
        mt5Connected: Boolean(st.mt5Connected),
        mt5Status: st.mt5Status || (st.mt5Connected ? "CONNECTED" : "DISCONNECTED"),
        demoMode: st.demoMode !== false,
        broker: String(st.broker || ""),
        accountMasked: String(st.accountMasked || "DEMO"),
        lastHeartbeat: st.lastHeartbeat || snap.updatedAt || null,
        serverTime: snap.updatedAt || new Date().toISOString(),
        readOnlyEnforced: true,
      });
      this.diagnostics.streamTimes.status = res.lastHeartbeat;
      return res;
    }
    const res = await this.requestJson("GET", "/api/mobile/v1/status", MobileStatusSchema, signal);
    this.diagnostics.streamTimes.status = res.lastHeartbeat;
    return res;
  }

  async getAccount(signal?: AbortSignal): Promise<MobileAccount> {
    if (this.isCloudMode()) {
      const snap = await this.fetchCloudSnapshot(signal);
      const acc = snap.account || {};
      const st = snap.status || {};
      const balance = Number(acc.balance ?? 0);
      const equity = Number(acc.equity ?? 0);
      const margin = Number(acc.margin ?? 0);
      const freeMargin = Number(acc.freeMargin ?? acc.free_margin ?? (equity - margin));
      const rawMarginLevel = Number(acc.marginLevel ?? acc.margin_level ?? 0);
      const marginLevel =
        rawMarginLevel > 0
          ? rawMarginLevel
          : margin > 0
          ? Number(((equity / margin) * 100).toFixed(2))
          : 0;
      const floatingPnl = Number(
        acc.floatingPnl !== undefined
          ? acc.floatingPnl
          : Number((equity - balance).toFixed(2))
      );

      const res = MobileAccountSchema.parse({
        balance,
        equity,
        margin,
        freeMargin,
        marginLevel,
        floatingPnl,
        currency: String(acc.currency || "USD"),
        leverage: Math.max(0, Math.round(Number(acc.leverage || 0))),
        tradeMode: String(acc.tradeMode || acc.trade_mode || (st.demoMode === false ? "LIVE" : "DEMO")),
        broker: String(acc.broker || st.broker || ""),
        accountMasked: String(acc.accountMasked || st.accountMasked || "DEMO"),
        openPositionsCount: Number(
          acc.openPositionsCount ?? (Array.isArray(snap.positions) ? snap.positions.length : 0)
        ),
        updatedAt: acc.updatedAt || snap.updatedAt || null,
      });
      this.diagnostics.streamTimes.account = res.updatedAt;
      return res;
    }
    const res = await this.requestJson("GET", "/api/mobile/v1/account", MobileAccountSchema, signal);
    this.diagnostics.streamTimes.account = res.updatedAt;
    return res;
  }

  /**
   * Filters raw snapshot trades strictly to closed deals (`status === "CLOSED"` or `Boolean(closed_at)`),
   * never counting open position snapshots (`status === "OPEN"`) as closed deals.
   */
  private extractClosedTradesFromSnapshot(snap: Record<string, any>): MobileTradeRecord[] {
    const rawTrades = Array.isArray(snap.trades) ? snap.trades : [];
    const closedOnly = rawTrades.filter((t: any) => {
      const st = String(t?.status || "").toUpperCase();
      const hasClosedAt = Boolean(t?.closedAt || t?.closed_at);
      return st === "CLOSED" || (st !== "OPEN" && hasClosedAt);
    });

    return closedOnly.map((t: any, idx: number) => {
      const sym = String(t.symbol || "XAUUSD");
      const canon = normalizeCanonicalSymbol(t.canonicalSymbol || sym);
      const openedAt = t.openedAt ? String(t.openedAt) : t.opened_at ? String(t.opened_at) : null;
      const closedAt = t.closedAt ? String(t.closedAt) : t.closed_at ? String(t.closed_at) : null;
      const openMs = parseIsoToMs(openedAt);
      const closeMs = parseIsoToMs(closedAt);
      const durationSec =
        typeof t.durationSec === "number" && t.durationSec >= 0
          ? t.durationSec
          : openMs && closeMs && closeMs >= openMs
          ? Math.round((closeMs - openMs) / 1000)
          : null;
      const entryRaw = t.entryPrice ?? t.entry_price ?? t.open_price;
      const exitRaw = t.exitPrice ?? t.exit_price ?? t.close_price;
      const slRaw = t.sl ?? t.stop_loss;
      const tpRaw = t.tp ?? t.take_profit;

      return {
        ticket: Number(t.ticket ?? idx + 1),
        symbol: sym,
        canonicalSymbol: canon,
        direction: String(t.direction || "BUY").toUpperCase() === "SELL" ? ("SELL" as const) : ("BUY" as const),
        volume: Math.max(0, Number(t.volume ?? 0)),
        entryPrice: entryRaw !== undefined && entryRaw !== null && Number(entryRaw) > 0 ? Number(entryRaw) : null,
        exitPrice: exitRaw !== undefined && exitRaw !== null && Number(exitRaw) > 0 ? Number(exitRaw) : null,
        sl: slRaw !== undefined && slRaw !== null && Number(slRaw) > 0 ? Number(slRaw) : null,
        tp: tpRaw !== undefined && tpRaw !== null && Number(tpRaw) > 0 ? Number(tpRaw) : null,
        pnl: Number(Number(t.pnl ?? t.profit ?? 0).toFixed(2)),
        openedAt,
        closedAt,
        durationSec,
        status: "CLOSED",
        strategyTag: String(t.strategyTag ?? t.strategy_tag ?? t.comment ?? ""),
        digits: Number(t.digits ?? (canon.includes("JPY") ? 3 : 2)),
      };
    });
  }

  async getStats(signal?: AbortSignal): Promise<MobileStats> {
    if (this.isCloudMode()) {
      const snap = await this.fetchCloudSnapshot(signal);
      const s = (snap.stats && typeof snap.stats === "object" ? snap.stats : {}) as Record<string, any>;
      const closedTrades = this.extractClosedTradesFromSnapshot(snap);
      const openPositionsCount = Array.isArray(snap.positions)
        ? snap.positions.length
        : Number(snap.account?.openPositionsCount || 0);
      const floatingPnl = Number(
        snap.account?.floatingPnl ??
          ((Number(snap.account?.equity || 0) - Number(snap.account?.balance || 0)) || 0)
      );

      const todayUtc = new Date().toISOString().slice(0, 10);
      const closedToday = closedTrades.filter(
        (t) => t.closedAt && t.closedAt.slice(0, 10) === todayUtc
      );
      const todayRealized = closedToday.reduce((acc, t) => acc + t.pnl, 0);
      const wins = closedTrades.filter((t) => t.pnl > 0).length;
      const losses = closedTrades.filter((t) => t.pnl < 0).length;
      const decided = wins + losses;
      const realizedTotal = closedTrades.reduce((acc, t) => acc + t.pnl, 0);

      const computedTodayPnl = Number((todayRealized + floatingPnl).toFixed(2));
      const computedTradesToday = closedToday.length + openPositionsCount;
      const computedTotalProfit =
        closedTrades.length > 0 ? Number(realizedTotal.toFixed(2)) : computedTodayPnl;
      const computedWinRate = decided > 0 ? Number(((wins / decided) * 100).toFixed(2)) : 0;

      const hasAuthoritativeStats =
        typeof s.dealsCount === "number" &&
        typeof s.tradesToday === "number" &&
        typeof s.todayPnl === "number";

      return MobileStatsSchema.parse({
        todayPnl: hasAuthoritativeStats ? Number(s.todayPnl) : computedTodayPnl,
        todayRealizedPnl:
          typeof s.todayRealizedPnl === "number"
            ? Number(s.todayRealizedPnl)
            : Number(todayRealized.toFixed(2)),
        todayClosedCount:
          typeof s.todayClosedCount === "number" ? Number(s.todayClosedCount) : closedToday.length,
        openPositionsCount:
          typeof s.openPositionsCount === "number" ? Number(s.openPositionsCount) : openPositionsCount,
        totalProfit: hasAuthoritativeStats ? Number(s.totalProfit) : computedTotalProfit,
        winRate: hasAuthoritativeStats ? Number(s.winRate) : computedWinRate,
        dealsCount: hasAuthoritativeStats ? Number(s.dealsCount) : closedTrades.length,
        tradesToday: hasAuthoritativeStats ? Number(s.tradesToday) : computedTradesToday,
        winsCount: hasAuthoritativeStats ? Number(s.winsCount) : wins,
        lossesCount: hasAuthoritativeStats ? Number(s.lossesCount) : losses,
        currency: String(s.currency || snap.account?.currency || "USD"),
        computedAt: String(s.computedAt || snap.updatedAt || new Date().toISOString()),
      });
    }
    return this.requestJson("GET", "/api/mobile/v1/stats", MobileStatsSchema, signal);
  }

  async getPositions(signal?: AbortSignal): Promise<MobilePositionsResponse> {
    if (this.isCloudMode()) {
      const snap = await this.fetchCloudSnapshot(signal);
      const rawPos = Array.isArray(snap.positions) ? snap.positions : [];
      const positions = rawPos.map((p: any, idx: number) => {
        const sym = String(p.symbol || "XAUUSD");
        const canon = normalizeCanonicalSymbol(p.canonicalSymbol || sym);
        const rawSl = Number(p.sl ?? p.stop_loss ?? 0);
        const rawTp = Number(p.tp ?? p.take_profit ?? 0);
        const sl = Number.isFinite(rawSl) && rawSl > 0 ? rawSl : null;
        const tp = Number.isFinite(rawTp) && rawTp > 0 ? rawTp : null;
        const rawOpenTime = p.openTime ?? p.open_timestamp ?? p.open_time ?? 0;
        const openTimeSec =
          typeof rawOpenTime === "number" && rawOpenTime > 0
            ? Math.floor(rawOpenTime)
            : typeof rawOpenTime === "string" && parseIsoToMs(rawOpenTime)
            ? Math.floor(parseIsoToMs(rawOpenTime)! / 1000)
            : 0;
        const rawOwner = String(p.ownership || "BOT_OWN").toUpperCase();
        const ownership =
          rawOwner === "MANUAL"
            ? ("MANUAL" as const)
            : rawOwner === "OTHER_EA"
            ? ("OTHER_EA" as const)
            : ("BOT_OWN" as const);

        return {
          ticket: Math.max(1, Number(p.ticket || idx + 1)),
          symbol: sym,
          canonicalSymbol: canon,
          type: String(p.type || p.direction || "BUY").toUpperCase() === "SELL" ? ("SELL" as const) : ("BUY" as const),
          volume: Math.max(0.001, Number(p.volume || 0.01)),
          openPrice: Number(p.openPrice ?? p.open_price ?? 0),
          currentPrice: Number(p.currentPrice ?? p.current_price ?? 0),
          sl,
          tp,
          profit: Number(p.profit ?? 0),
          swap: Number(p.swap ?? 0),
          openTime: openTimeSec,
          digits: Number(p.digits ?? (canon.includes("JPY") ? 3 : 2)),
          ownership,
          protected: sl !== null && sl > 0,
          comment: String(p.comment || ""),
        };
      });
      const res = MobilePositionsResponseSchema.parse({
        positions,
        currency: String(snap.account?.currency || "USD"),
        updatedAt: snap.updatedAt || null,
      });
      this.diagnostics.streamTimes.positions = res.updatedAt;
      return res;
    }
    const res = await this.requestJson("GET", "/api/mobile/v1/positions", MobilePositionsResponseSchema, signal);
    this.diagnostics.streamTimes.positions = res.updatedAt;
    return res;
  }

  async getSymbols(signal?: AbortSignal): Promise<MobileSymbolsResponse> {
    if (this.isCloudMode()) {
      const snap = await this.fetchCloudSnapshot(signal);
      const rawSyms = Array.isArray(snap.symbols) ? snap.symbols : [];
      const normalizedSyms =
        rawSyms.length > 0
          ? rawSyms.map((s: any) => {
              const canon = normalizeCanonicalSymbol(s.symbol || s.canonical);
              return {
                symbol: canon,
                brokerSymbol: String(s.brokerSymbol || s.broker_symbol || s.symbol || `${canon}.m`),
                digits: Number(s.digits ?? (canon.includes("JPY") ? 3 : 2)),
                point: Number(s.point ?? (canon.includes("JPY") ? 0.001 : 0.01)),
                bid: s.bid !== undefined && s.bid !== null && Number(s.bid) > 0 ? Number(s.bid) : null,
                ask: s.ask !== undefined && s.ask !== null && Number(s.ask) > 0 ? Number(s.ask) : null,
                spreadPoints:
                  s.spreadPoints !== undefined && s.spreadPoints !== null
                    ? Number(s.spreadPoints)
                    : s.spread_points !== undefined && s.spread_points !== null
                    ? Number(s.spread_points)
                    : null,
              };
            })
          : DEFAULT_UNIVERSE_SYMBOLS;

      return MobileSymbolsResponseSchema.parse({
        symbols: normalizedSyms,
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
    const canon = normalizeCanonicalSymbol(params.symbol);
    const tf = String(params.tf || "M5").toUpperCase();
    const digits = canon.includes("JPY") ? 3 : 2;
    const point = canon.includes("JPY") ? 0.001 : 0.01;

    if (this.isCloudMode()) {
      const snap = await this.fetchCloudSnapshot(signal);
      const st = (snap.status && typeof snap.status === "object" ? snap.status : {}) as Record<string, any>;
      const map = (snap.candlesByKey && typeof snap.candlesByKey === "object"
        ? snap.candlesByKey
        : st._candlesByKey && typeof st._candlesByKey === "object"
        ? st._candlesByKey
        : {}) as Record<string, any>;
      const entry = map[`${canon}:${tf}`] || map[`${params.symbol}:${tf}`] || null;

      const syms = Array.isArray(snap.symbols) ? snap.symbols : [];
      const symSpec = syms.find((s: any) => normalizeCanonicalSymbol(s.symbol) === canon) || null;

      const rawCandles = Array.isArray(entry?.candles) ? entry.candles : [];
      const limit = params.limit && params.limit > 0 ? params.limit : 160;
      const candles = rawCandles
        .map((c: any) => ({
          time: Math.floor(Number(c.time || 0)),
          open: Number(c.open || 0),
          high: Number(c.high || 0),
          low: Number(c.low || 0),
          close: Number(c.close || 0),
          volume: Math.max(0, Number(c.volume ?? c.tick_volume ?? 0)),
        }))
        .filter((c: any) => c.time > 0 && Number.isFinite(c.open) && Number.isFinite(c.close))
        .slice(-limit);

      const res = MobileCandlesResponseSchema.parse({
        symbol: canon,
        brokerSymbol: String(entry?.brokerSymbol || entry?.broker_symbol || symSpec?.brokerSymbol || `${canon}.m`),
        timeframe: tf,
        digits: Number(entry?.digits ?? symSpec?.digits ?? digits),
        point: Number(entry?.point ?? symSpec?.point ?? point),
        bid:
          entry?.bid !== undefined && entry?.bid !== null
            ? Number(entry.bid)
            : symSpec?.bid !== undefined && symSpec?.bid !== null
            ? Number(symSpec.bid)
            : null,
        ask:
          entry?.ask !== undefined && entry?.ask !== null
            ? Number(entry.ask)
            : symSpec?.ask !== undefined && symSpec?.ask !== null
            ? Number(symSpec.ask)
            : null,
        spreadPoints:
          entry?.spreadPoints !== undefined && entry?.spreadPoints !== null
            ? Number(entry.spreadPoints)
            : symSpec?.spreadPoints !== undefined && symSpec?.spreadPoints !== null
            ? Number(symSpec.spreadPoints)
            : null,
        candles,
        stale: Boolean(entry?.stale ?? false),
        marketClosed: Boolean(entry?.marketClosed ?? false),
        tickTimeUtc: entry?.tickTimeUtc || snap.updatedAt || null,
        source: String(entry?.source || "MT5"),
      });
      this.diagnostics.streamTimes.charts = snap.updatedAt || null;
      return res;
    }

    const qs = new URLSearchParams();
    qs.set("symbol", params.symbol);
    qs.set("tf", params.tf);
    if (params.limit) qs.set("limit", String(params.limit));
    if (params.from) qs.set("from", params.from);
    if (params.to) qs.set("to", params.to);
    const res = await this.requestJson(
      "GET",
      `/api/mobile/v1/candles?${qs.toString()}`,
      MobileCandlesResponseSchema,
      signal
    );
    this.diagnostics.streamTimes.charts = res.tickTimeUtc || new Date().toISOString();
    return res;
  }

  private normalizeDrawingsEnvelope(raw: any, symbol: string, tf: string): MobileDrawingsResponse {
    const canon = normalizeCanonicalSymbol(symbol);
    const rawItems = Array.isArray(raw?.items)
      ? raw.items
      : Array.isArray(raw?.drawings)
      ? raw.drawings
      : [];
    const counts = normalizeDrawingsCounts(rawItems, raw?.counts);

    return MobileDrawingsResponseSchema.parse({
      schema_version: String(raw?.schema_version || "1.1.0"),
      symbol: canon,
      broker_symbol: String(raw?.broker_symbol || `${canon}.m`),
      timeframe: tf,
      generated_at: String(raw?.generated_at || new Date().toISOString()),
      source: String(raw?.source || "BOT"),
      items: rawItems,
      drawings: rawItems,
      counts,
      mtf_levels: Array.isArray(raw?.mtf_levels) ? raw.mtf_levels : undefined,
      smc: raw?.smc && typeof raw.smc === "object" ? raw.smc : undefined,
    });
  }

  async getDrawings(
    params: { symbol: string; tf: string; count?: number },
    signal?: AbortSignal
  ): Promise<MobileDrawingsResponse> {
    const canon = normalizeCanonicalSymbol(params.symbol);
    const tf = String(params.tf || "M5").toUpperCase();

    if (this.isCloudMode()) {
      const snap = await this.fetchCloudSnapshot(signal);
      const st = (snap.status && typeof snap.status === "object" ? snap.status : {}) as Record<string, any>;
      const map = (snap.drawingsByKey && typeof snap.drawingsByKey === "object"
        ? snap.drawingsByKey
        : st._drawingsByKey && typeof st._drawingsByKey === "object"
        ? st._drawingsByKey
        : {}) as Record<string, any>;
      const entry = map[`${canon}:${tf}`] || map[`${params.symbol}:${tf}`] || {};
      return this.normalizeDrawingsEnvelope(entry, canon, tf);
    }

    const qs = new URLSearchParams();
    qs.set("symbol", params.symbol);
    qs.set("tf", params.tf);
    if (params.count) qs.set("count", String(params.count));
    const raw = await this.requestJson(
      "GET",
      `/api/mobile/v1/drawings?${qs.toString()}`,
      { parse: (v: unknown) => v as any },
      signal
    );
    return this.normalizeDrawingsEnvelope(raw, canon, tf);
  }

  async getTrades(params: TradesQueryParams = {}, signal?: AbortSignal): Promise<MobileTradesPage> {
    if (this.isCloudMode()) {
      const snap = await this.fetchCloudSnapshot(signal);
      const allClosed = this.extractClosedTradesFromSnapshot(snap);

      const symFilter = params.symbol && params.symbol !== "ALL" ? normalizeCanonicalSymbol(params.symbol) : null;
      const outcomeFilter = params.outcome && params.outcome !== "ALL" ? params.outcome : null;
      const fromMs = parseIsoToMs(params.from);
      const toMs = parseIsoToMs(params.to);
      const searchQ = (params.q || "").trim().toLowerCase();
      const sortBy = params.sort || "time_desc";

      const filtered = allClosed.filter((t) => {
        if (symFilter && t.canonicalSymbol !== symFilter) return false;
        if (outcomeFilter === "WIN" && t.pnl <= 0) return false;
        if (outcomeFilter === "LOSS" && t.pnl >= 0) return false;
        const refMs = parseIsoToMs(t.closedAt || t.openedAt);
        if (fromMs !== null && (refMs === null || refMs < fromMs)) return false;
        if (toMs !== null && (refMs === null || refMs > toMs)) return false;
        if (searchQ) {
          const hay = `${t.ticket} ${t.symbol} ${t.canonicalSymbol} ${t.direction} ${t.strategyTag}`.toLowerCase();
          if (!hay.includes(searchQ)) return false;
        }
        return true;
      });

      filtered.sort((a, b) => {
        const tsA = parseIsoToMs(a.closedAt || a.openedAt) ?? 0;
        const tsB = parseIsoToMs(b.closedAt || b.openedAt) ?? 0;
        if (sortBy === "time_asc") return tsA - tsB;
        if (sortBy === "pnl_desc") return b.pnl - a.pnl;
        if (sortBy === "pnl_asc") return a.pnl - b.pnl;
        return tsB - tsA;
      });

      const total = filtered.length;
      const wins = filtered.filter((t) => t.pnl > 0).length;
      const losses = filtered.filter((t) => t.pnl < 0).length;
      const decided = wins + losses;
      const netPnl = Number(filtered.reduce((acc, t) => acc + t.pnl, 0).toFixed(2));
      const winRate = decided > 0 ? Number(((wins / decided) * 100).toFixed(2)) : 0;

      const page = Math.max(1, Math.floor(params.page || 1));
      const limit = Math.max(1, Math.min(100, Math.floor(params.limit || 25)));
      const start = (page - 1) * limit;
      const end = start + limit;
      const items = filtered.slice(start, end);
      const hasMore = end < total;

      const res = MobileTradesPageSchema.parse({
        page,
        limit,
        total,
        hasMore,
        nextCursor: hasMore ? String(page + 1) : null,
        currency: String(snap.account?.currency || "USD"),
        summary: {
          count: total,
          netPnl,
          winRate,
          wins,
          losses,
        },
        items,
      });
      this.diagnostics.streamTimes.trades = snap.updatedAt || null;
      return res;
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
    const res = await this.requestJson("GET", `/api/mobile/v1/trades${suffix}`, MobileTradesPageSchema, signal);
    this.diagnostics.streamTimes.trades = new Date().toISOString();
    return res;
  }

  async getEquity(range: "1D" | "1W" | "1M" | "ALL" = "1W", signal?: AbortSignal): Promise<MobileEquityResponse> {
    if (this.isCloudMode()) {
      const snap = await this.fetchCloudSnapshot(signal);
      const st = (snap.status && typeof snap.status === "object" ? snap.status : {}) as Record<string, any>;
      const rawPoints = Array.isArray(snap.equityPoints)
        ? snap.equityPoints
        : Array.isArray(st._equityPoints)
        ? st._equityPoints
        : [];

      const nowSec = Math.floor(Date.now() / 1000);
      const cutoffSec =
        range === "1D"
          ? nowSec - 86400
          : range === "1W"
          ? nowSec - 7 * 86400
          : range === "1M"
          ? nowSec - 30 * 86400
          : 0;

      const filtered = rawPoints
        .map((p: any) => ({
          time: Math.floor(Number(p.time || 0)),
          balance: Number(p.balance || 0),
          equity: Number(p.equity || 0),
          pnl: Number(p.pnl || 0),
        }))
        .filter((p: any) => p.time >= cutoffSec && p.time > 0 && Number.isFinite(p.equity))
        .sort((a: any, b: any) => a.time - b.time);

      if (filtered.length > 0) {
        const baseBal = filtered[0].balance;
        for (const pt of filtered) {
          pt.pnl = Number((pt.equity - baseBal).toFixed(2));
        }
      }

      const res = MobileEquityResponseSchema.parse({
        range,
        currency: String(snap.account?.currency || "USD"),
        points: filtered,
      });
      this.diagnostics.streamTimes.equity = snap.updatedAt || null;
      return res;
    }
    const res = await this.requestJson(
      "GET",
      `/api/mobile/v1/equity?range=${range}`,
      MobileEquityResponseSchema,
      signal
    );
    this.diagnostics.streamTimes.equity = new Date().toISOString();
    return res;
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
        message: `${s.symbol || ""} ${s.direction || ""} · ${s.status || "ACTIVE"}${
          s.rr ? ` (${Number(s.rr).toFixed(2)}R)` : ""
        }`.trim(),
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
    if (this.isCloudMode() && this.creds.cloudUrl) {
      this.cloudCache = null;
      const path = "/functions/v1/mobile-pairing";
      assertMobileHttpReadOnly("POST", path);
      const anonKey = getMobileSupabaseConfig().supabaseAnonKey;
      const headers: Record<string, string> = {
        Authorization: `Bearer ${this.creds.deviceToken}`,
        "Content-Type": "application/json",
        Accept: "application/json",
      };
      if (anonKey) headers.apikey = anonKey;
      try {
        await fetch(`${this.creds.cloudUrl.replace(/\/+$/, "")}${path}`, {
          method: "POST",
          headers,
          body: JSON.stringify({
            action: "unpair_self",
            deviceToken: this.creds.deviceToken,
          }),
        });
      } catch {
        // Best-effort server-side revoke even if phone is currently offline
      }
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
