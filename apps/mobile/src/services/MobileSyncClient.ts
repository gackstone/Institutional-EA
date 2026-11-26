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

export const DEFAULT_CLOUD_API_URL = (
  (typeof process !== "undefined" && process.env?.EXPO_PUBLIC_SUPABASE_URL) ||
  "https://arcadefx.live"
).replace(/\/+$/, "");

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

  const resp = await fetch(`${baseUrl}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
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

  const body = (await resp.json().catch(() => ({}))) as Record<string, any>;
  if (!resp.ok) {
    const rawMsg = String(body.message || body.error || "");
    let friendly = rawMsg || `Cloud pairing failed (${resp.status})`;
    if (resp.status === 404 || /requested function was not found/i.test(rawMsg)) {
      friendly =
        "Cloud Pairing is not deployed on the server yet. Deploy mobile-pairing or use Local Wi-Fi Fallback below.";
    } else if (resp.status === 401) {
      friendly = "Cloud pairing authentication failed. Regenerate the code on Windows or use Local Wi-Fi Fallback.";
    } else if (resp.status === 429) {
      friendly = "Too many pairing attempts. Wait a minute and generate a new code on Windows.";
    }
    throw new MobileSyncError(friendly, resp.status, body.error || "CLOUD_PAIR_FAILED");
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

  const resp = await fetch(`${claim.cloudUrl}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({
      action: "poll",
      sessionId: claim.sessionId,
      claimNonce: claim.claimNonce,
    }),
    signal,
  });

  const body = (await resp.json().catch(() => ({}))) as Record<string, any>;
  if (!resp.ok) {
    throw new MobileSyncError(
      body.message || body.error || `Approval check failed (${resp.status})`,
      resp.status,
      body.error || "POLL_FAILED"
    );
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

  async getStatus(signal?: AbortSignal): Promise<MobileStatus> {
    return this.requestJson("GET", "/api/mobile/v1/status", MobileStatusSchema, signal);
  }

  async getAccount(signal?: AbortSignal): Promise<MobileAccount> {
    return this.requestJson("GET", "/api/mobile/v1/account", MobileAccountSchema, signal);
  }

  async getStats(signal?: AbortSignal): Promise<MobileStats> {
    return this.requestJson("GET", "/api/mobile/v1/stats", MobileStatsSchema, signal);
  }

  async getPositions(signal?: AbortSignal): Promise<MobilePositionsResponse> {
    return this.requestJson("GET", "/api/mobile/v1/positions", MobilePositionsResponseSchema, signal);
  }

  async getSymbols(signal?: AbortSignal): Promise<MobileSymbolsResponse> {
    return this.requestJson("GET", "/api/mobile/v1/symbols", MobileSymbolsResponseSchema, signal);
  }

  async getCandles(
    params: { symbol: string; tf: string; limit?: number; from?: string; to?: string },
    signal?: AbortSignal
  ): Promise<MobileCandlesResponse> {
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
    return this.requestJson(
      "GET",
      `/api/mobile/v1/equity?range=${range}`,
      MobileEquityResponseSchema,
      signal
    );
  }

  async getActivity(limit = 40, signal?: AbortSignal): Promise<MobileActivityResponse> {
    return this.requestJson(
      "GET",
      `/api/mobile/v1/activity?limit=${limit}`,
      MobileActivityResponseSchema,
      signal
    );
  }

  async unpair(): Promise<void> {
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
      const resp = await fetch(`${this.creds.cloudUrl.replace(/\/+$/, "")}${path}`, {
        method: "GET",
        headers: {
          Authorization: `Bearer ${this.creds.deviceToken}`,
          Accept: "application/json",
        },
      });
      if (resp.status === 401 || resp.status === 403) {
        this.stopStream();
        handlers.onRevoked?.();
        return;
      }
      if (!resp.ok) {
        throw new Error(`Cloud sync HTTP ${resp.status}`);
      }
      const snap = (await resp.json()) as Record<string, any>;
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
