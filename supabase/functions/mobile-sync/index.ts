// Supabase Edge Function: mobile-sync
// Cross-network cloud telemetry & live-signal relay (Sync Schema v1.1.0, backward-compatible with v1.0.0):
// - POST (Windows Companion user JWT, action="push"): publishes latest MT5 account, positions,
//   orders, trade history, live bot signals, symbols, candles, SMC overlays/drawings,
//   equity snapshots, and engine status with monotonic sequence numbers.
// - GET (Android Read-Only device bearer token `iea_ro_*`): returns authorized read-only snapshot.
// - STRICT READ-ONLY ENFORCEMENT: Any mutation or trading command from a mobile device token
//   is unconditionally rejected with HTTP 403 READ_ONLY_VIOLATION.

import { corsHeaders, createServiceClient, jsonResponse, requireAuthenticatedUser } from "../_shared/auth.ts";

async function sha256Hex(input: string): Promise<string> {
  const bytes = new TextEncoder().encode(input);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  const service = createServiceClient();
  const authHeader = req.headers.get("Authorization") || "";
  const bearer = authHeader.startsWith("Bearer ") ? authHeader.slice(7).trim() : "";

  // ------------------------------------------------------------------
  // STRICT READ-ONLY GUARD FOR MOBILE DEVICE TOKENS (`iea_ro_*`)
  // ------------------------------------------------------------------
  if (bearer.startsWith("iea_ro_")) {
    if (req.method !== "GET") {
      return jsonResponse(
        {
          error: "READ_ONLY_VIOLATION",
          message: "Paired mobile devices are strictly read-only and cannot invoke write or trading endpoints.",
        },
        403
      );
    }

    const tokenHash = await sha256Hex(bearer);
    const { data: device } = await service
      .from("mobile_paired_devices")
      .select("id, user_id, companion_device_id, companion_name, scope, status, token_expires_at")
      .eq("token_hash", tokenHash)
      .maybeSingle();

    if (!device || device.status !== "active" || device.scope !== "read_only") {
      return jsonResponse({ error: "DEVICE_REVOKED", message: "This device pairing has been revoked." }, 401);
    }

    if (new Date(device.token_expires_at).getTime() <= Date.now()) {
      return jsonResponse({ error: "TOKEN_EXPIRED", message: "Device token expired. Please re-pair." }, 401);
    }

    await service
      .from("mobile_paired_devices")
      .update({ last_seen_at: new Date().toISOString() })
      .eq("id", device.id);

    const { data: snap } = await service
      .from("companion_telemetry_snapshots")
      .select("*")
      .eq("user_id", device.user_id)
      .eq("companion_device_id", device.companion_device_id)
      .maybeSingle();

    const statusJson = (snap?.status_json && typeof snap.status_json === "object" ? snap.status_json : {}) as Record<string, unknown>;
    const metaJson = (snap?.meta_json && typeof snap.meta_json === "object"
      ? snap.meta_json
      : (statusJson._meta && typeof statusJson._meta === "object" ? statusJson._meta : {})) as Record<string, unknown>;
    const candlesJson = (snap?.candles_json && typeof snap.candles_json === "object"
      ? snap.candles_json
      : (statusJson._candlesByKey && typeof statusJson._candlesByKey === "object" ? statusJson._candlesByKey : {})) as Record<string, unknown>;
    const drawingsJson = (snap?.drawings_json && typeof snap.drawings_json === "object"
      ? snap.drawings_json
      : (statusJson._drawingsByKey && typeof statusJson._drawingsByKey === "object" ? statusJson._drawingsByKey : {})) as Record<string, unknown>;
    const equityJson = Array.isArray(snap?.equity_json)
      ? snap.equity_json
      : (Array.isArray(statusJson._equityPoints) ? statusJson._equityPoints : []);

    return jsonResponse({
      ok: true,
      readOnlyEnforced: true,
      schemaVersion: String(metaJson.schemaVersion || "1.1.0"),
      supportedVersions: ["1.0.0", "1.1.0"],
      companionName: snap?.companion_name || device.companion_name,
      sequenceNo: snap?.sequence_no || 0,
      updatedAt: snap?.updated_at || null,
      meta: {
        schemaVersion: String(metaJson.schemaVersion || "1.1.0"),
        minClientSchemaVersion: "1.0.0",
        supportedVersions: ["1.0.0", "1.1.0"],
        producerVersion: String(metaJson.producerVersion || "1.3.7"),
        generatedAt: String(metaJson.generatedAt || snap?.updated_at || new Date().toISOString()),
        sequenceNo: Number(snap?.sequence_no || 0),
        timezoneRule: "UTC_00_00",
        brokerUtcOffsetHours: Number(metaJson.brokerUtcOffsetHours || 0),
      },
      status: snap?.status_json || null,
      account: snap?.account_json || null,
      stats: snap?.stats_json || null,
      positions: snap?.positions_json || [],
      orders: snap?.orders_json || [],
      trades: snap?.trades_json || [],
      signals: snap?.signals_json || [],
      symbols: snap?.symbols_json || [],
      candlesByKey: candlesJson,
      drawingsByKey: drawingsJson,
      equityPoints: equityJson,
    });
  }

  // ------------------------------------------------------------------
  // WINDOWS COMPANION TELEMETRY PUBLISH (POST with authenticated user JWT)
  // ------------------------------------------------------------------
  if (req.method !== "POST") {
    return jsonResponse({ error: "Method not allowed" }, 405);
  }

  const auth = await requireAuthenticatedUser(req);
  if (auth.error || !auth.profile) {
    return jsonResponse({ error: auth.error || "Unauthorized" }, 401);
  }

  const body = (await req.json().catch(() => ({}))) as Record<string, unknown>;
  const companionDeviceId = String(body.companionDeviceId || "windows-companion").trim().slice(0, 128);
  const companionName = String(body.companionName || "Windows Companion").trim().slice(0, 80);
  const incomingSeq = Number(body.sequenceNo || 0);

  // Enforce monotonic sequence ordering so stale/out-of-order pushes never overwrite newer state
  const { data: existing } = await service
    .from("companion_telemetry_snapshots")
    .select("sequence_no")
    .eq("user_id", auth.profile.id)
    .eq("companion_device_id", companionDeviceId)
    .maybeSingle();

  if (existing && incomingSeq > 0 && incomingSeq < Number(existing.sequence_no)) {
    return jsonResponse({ ok: true, ignoredStale: true, sequenceNo: existing.sequence_no });
  }

  const nextSeq = incomingSeq > 0 ? incomingSeq : (Number(existing?.sequence_no || 0) + 1);
  const nowIso = new Date().toISOString();

  // Embed fallback v1.1.0 envelopes inside status_json as well so an unmigrated v1.0.0 table still works
  const baseStatus = (body.status && typeof body.status === "object" ? body.status : {}) as Record<string, unknown>;
  const enrichedStatus = {
    ...baseStatus,
    _meta: body.meta ?? { schemaVersion: "1.1.0", generatedAt: nowIso, sequenceNo: nextSeq },
    _candlesByKey: body.candlesByKey ?? {},
    _drawingsByKey: body.drawingsByKey ?? {},
    _equityPoints: Array.isArray(body.equityPoints) ? body.equityPoints : [],
  };

  const fullRow: Record<string, unknown> = {
    user_id: auth.profile.id,
    companion_device_id: companionDeviceId,
    companion_name: companionName,
    sequence_no: nextSeq,
    meta_json: body.meta ?? { schemaVersion: "1.1.0", generatedAt: nowIso, sequenceNo: nextSeq },
    status_json: enrichedStatus,
    account_json: body.account ?? {},
    stats_json: body.stats ?? {},
    positions_json: Array.isArray(body.positions) ? body.positions : [],
    orders_json: Array.isArray(body.orders) ? body.orders : [],
    trades_json: Array.isArray(body.trades) ? body.trades : [],
    signals_json: Array.isArray(body.signals) ? body.signals : [],
    symbols_json: Array.isArray(body.symbols) ? body.symbols : [],
    candles_json: body.candlesByKey && typeof body.candlesByKey === "object" ? body.candlesByKey : {},
    drawings_json: body.drawingsByKey && typeof body.drawingsByKey === "object" ? body.drawingsByKey : {},
    equity_json: Array.isArray(body.equityPoints) ? body.equityPoints : [],
    updated_at: nowIso,
  };

  let { error: upErr } = await service
    .from("companion_telemetry_snapshots")
    .upsert(fullRow, { onConflict: "user_id,companion_device_id" });

  // Graceful backward-compatible fallback if migration 20261127000005 has not been applied to DB yet
  if (upErr && /column .* does not exist/i.test(upErr.message)) {
    const legacyRow = {
      user_id: auth.profile.id,
      companion_device_id: companionDeviceId,
      companion_name: companionName,
      sequence_no: nextSeq,
      status_json: enrichedStatus,
      account_json: body.account ?? {},
      stats_json: body.stats ?? {},
      positions_json: Array.isArray(body.positions) ? body.positions : [],
      orders_json: Array.isArray(body.orders) ? body.orders : [],
      trades_json: Array.isArray(body.trades) ? body.trades : [],
      signals_json: Array.isArray(body.signals) ? body.signals : [],
      symbols_json: Array.isArray(body.symbols) ? body.symbols : [],
      updated_at: nowIso,
    };
    const retry = await service
      .from("companion_telemetry_snapshots")
      .upsert(legacyRow, { onConflict: "user_id,companion_device_id" });
    upErr = retry.error;
  }

  if (upErr) {
    return jsonResponse({ error: upErr.message }, 500);
  }

  return jsonResponse({ ok: true, sequenceNo: nextSeq, updatedAt: nowIso, schemaVersion: "1.1.0" });
});
