// Supabase Edge Function: device-heartbeat
// Registers or updates the authenticated user's Windows Companion device using a
// privacy-conscious SHA-256 fingerprint hash, enforces server-side device limits,
// and returns the authoritative UTC subscription entitlement snapshot.

import { corsHeaders, createServiceClient, jsonResponse, requireAuthenticatedUser } from "../_shared/auth.ts";

interface HeartbeatRequest {
  device_name: string;
  device_fingerprint_hash: string;
  operating_system?: string;
  app_version?: string;
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }
  if (req.method !== "POST") {
    return jsonResponse({ error: "Method not allowed" }, 405);
  }

  try {
    const auth = await requireAuthenticatedUser(req);
    if (auth.error || !auth.profile) {
      return jsonResponse({ error: auth.error || "Unauthorized" }, 401);
    }

    const body = (await req.json()) as HeartbeatRequest;
    const fpHash = (body?.device_fingerprint_hash || "").trim().toLowerCase();
    const deviceName = (body?.device_name || "Windows Companion").trim().slice(0, 120);

    if (!/^[a-f0-9]{64}$/.test(fpHash)) {
      return jsonResponse({ error: "device_fingerprint_hash must be a valid 64-character SHA-256 hex digest." }, 400);
    }

    const service = createServiceClient();
    const nowIso = new Date().toISOString();

    const { data: existingDevice } = await service
      .from("devices")
      .select("*")
      .eq("user_id", auth.profile.id)
      .eq("device_fingerprint_hash", fpHash)
      .maybeSingle();

    let deviceRecord = existingDevice;

    if (existingDevice) {
      if (existingDevice.status === "revoked") {
        return jsonResponse(
          { error: "This device has been revoked. Sign in again or contact your account administrator.", revoked: true },
          403
        );
      }
      const { data: updated } = await service
        .from("devices")
        .update({
          device_name: deviceName,
          operating_system: (body.operating_system || existingDevice.operating_system).slice(0, 64),
          app_version: (body.app_version || existingDevice.app_version).slice(0, 32),
          last_seen_at: nowIso,
        })
        .eq("id", existingDevice.id)
        .select()
        .single();
      deviceRecord = updated;
    } else {
      const { data: inserted, error: insErr } = await service
        .from("devices")
        .insert({
          user_id: auth.profile.id,
          device_name: deviceName,
          device_fingerprint_hash: fpHash,
          operating_system: (body.operating_system || "Windows").slice(0, 64),
          app_version: (body.app_version || "1.3.4").slice(0, 32),
          last_seen_at: nowIso,
          status: "active",
        })
        .select()
        .single();

      if (insErr) {
        return jsonResponse({ error: insErr.message }, 409);
      }
      deviceRecord = inserted;
    }

    const { data: subscription } = await service
      .from("subscriptions")
      .select("*, plan:plans(*)")
      .eq("user_id", auth.profile.id)
      .order("created_at", { ascending: false })
      .limit(1)
      .maybeSingle();

    return jsonResponse({
      ok: true,
      verified_at_utc: nowIso,
      profile: auth.profile,
      device: deviceRecord,
      subscription: subscription ?? null,
    });
  } catch (err) {
    return jsonResponse({ error: err instanceof Error ? err.message : "Unexpected server error" }, 500);
  }
});
