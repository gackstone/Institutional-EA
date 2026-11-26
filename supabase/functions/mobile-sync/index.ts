// Supabase Edge Function: mobile-sync
// Cross-network cloud telemetry & live-signal relay:
// - POST (Windows Companion user JWT, action="push"): publishes latest MT5 account, positions,
//   orders, trade history, live bot signals, and engine status with monotonic sequence numbers.
// - GET (Android Read-Only device bearer token): returns authorized read-only snapshot.
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

    return jsonResponse({
      ok: true,
      readOnlyEnforced: true,
      companionName: snap?.companion_name || device.companion_name,
      sequenceNo: snap?.sequence_no || 0,
      updatedAt: snap?.updated_at || null,
      status: snap?.status_json || null,
      account: snap?.account_json || null,
      stats: snap?.stats_json || null,
      positions: snap?.positions_json || [],
      orders: snap?.orders_json || [],
      trades: snap?.trades_json || [],
      signals: snap?.signals_json || [],
      symbols: snap?.symbols_json || [],
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

  const { error: upErr } = await service
    .from("companion_telemetry_snapshots")
    .upsert(
      {
        user_id: auth.profile.id,
        companion_device_id: companionDeviceId,
        companion_name: companionName,
        sequence_no: nextSeq,
        status_json: body.status ?? {},
        account_json: body.account ?? {},
        stats_json: body.stats ?? {},
        positions_json: Array.isArray(body.positions) ? body.positions : [],
        orders_json: Array.isArray(body.orders) ? body.orders : [],
        trades_json: Array.isArray(body.trades) ? body.trades : [],
        signals_json: Array.isArray(body.signals) ? body.signals : [],
        symbols_json: Array.isArray(body.symbols) ? body.symbols : [],
        updated_at: nowIso,
      },
      { onConflict: "user_id,companion_device_id" }
    );

  if (upErr) {
    return jsonResponse({ error: upErr.message }, 500);
  }

  return jsonResponse({ ok: true, sequenceNo: nextSeq, updatedAt: nowIso });
});
