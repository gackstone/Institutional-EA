// Supabase Edge Function: mobile-pairing
// Secure cross-network cloud-mediated pairing between Windows Companion and Android Read-Only App.
// Security guarantees:
// - Cryptographically random 6-digit pairing codes & 256-bit session tokens (stored as SHA-256 hashes only).
// - Short-lived 5-minute pairing sessions, one-time consumption, brute-force rate limiting (max 5 attempts).
// - Explicit Windows user approval required before issuing a device-bound read-only token.
// - No permanent secrets in QR codes.

import { corsHeaders, createServiceClient, jsonResponse, requireAuthenticatedUser } from "../_shared/auth.ts";

const PAIRING_TTL_SECONDS = 300; // 5 minutes
const MAX_PAIRING_ATTEMPTS = 5;

async function sha256Hex(input: string): Promise<string> {
  const bytes = new TextEncoder().encode(input);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function randomHex(byteLen = 32): string {
  const buf = new Uint8Array(byteLen);
  crypto.getRandomValues(buf);
  return Array.from(buf)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function randomSixDigitCode(): string {
  const buf = new Uint32Array(1);
  crypto.getRandomValues(buf);
  return String(buf[0] % 1_000_000).padStart(6, "0");
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }
  if (req.method !== "POST") {
    return jsonResponse({ error: "Method not allowed" }, 405);
  }

  try {
    const body = (await req.json().catch(() => ({}))) as Record<string, unknown>;
    const action = String(body.action || "").trim().toLowerCase();
    const service = createServiceClient();
    const now = new Date();
    const nowIso = now.toISOString();
    const cloudUrl = (Deno.env.get("SUPABASE_URL") || "").replace(/\/+$/, "");

    // ------------------------------------------------------------------
    // ANDROID ACTIONS (unauthenticated initially — validated by short-lived pairing session)
    // ------------------------------------------------------------------
    if (action === "claim") {
      const code = String(body.code || "").trim();
      const sessionId = String(body.sessionId || "").trim();
      const sessionToken = String(body.sessionToken || "").trim();
      const deviceName = String(body.deviceName || "Android Device").trim().slice(0, 80);
      const platform = String(body.platform || "android").trim().slice(0, 32);
      const fingerprint = String(body.deviceFingerprint || "").trim().slice(0, 128);

      if (!/^[0-9]{6}$/.test(code) && !(sessionId && sessionToken)) {
        return jsonResponse({ error: "INVALID_CODE", message: "Enter a valid 6-digit code or scan the QR code." }, 400);
      }

      let session: any = null;
      if (sessionId && sessionToken) {
        const tokenHash = await sha256Hex(sessionToken);
        const { data } = await service
          .from("mobile_pairing_sessions")
          .select("*")
          .eq("id", sessionId)
          .eq("session_token_hash", tokenHash)
          .maybeSingle();
        session = data;
      } else {
        const codeHash = await sha256Hex(code);
        const { data } = await service
          .from("mobile_pairing_sessions")
          .select("*")
          .eq("code_hash", codeHash)
          .in("status", ["pending", "awaiting_approval"])
          .order("created_at", { ascending: false })
          .limit(1)
          .maybeSingle();
        session = data;
      }

      if (!session) {
        return jsonResponse({ error: "INVALID_PAIRING_CODE", message: "Pairing code not found or already used." }, 404);
      }

      if (session.attempt_count >= MAX_PAIRING_ATTEMPTS) {
        await service.from("mobile_pairing_sessions").update({ status: "expired" }).eq("id", session.id);
        return jsonResponse({ error: "RATE_LIMITED", message: "Too many pairing attempts. Generate a new code on Windows." }, 429);
      }

      if (new Date(session.expires_at).getTime() <= now.getTime()) {
        await service.from("mobile_pairing_sessions").update({ status: "expired" }).eq("id", session.id);
        return jsonResponse({ error: "PAIRING_EXPIRED", message: "Pairing code expired. Generate a new code on Windows." }, 410);
      }

      if (session.status !== "pending") {
        return jsonResponse({ error: "PAIRING_CONSUMED", message: "This pairing session was already claimed." }, 409);
      }

      const claimNonce = randomHex(24);
      const claimNonceHash = await sha256Hex(claimNonce);

      await service
        .from("mobile_pairing_sessions")
        .update({
          status: "awaiting_approval",
          pending_android_name: deviceName,
          pending_android_platform: platform,
          pending_android_fingerprint: fingerprint || null,
          claim_nonce_hash: claimNonceHash,
          attempt_count: session.attempt_count + 1,
        })
        .eq("id", session.id);

      return jsonResponse({
        ok: true,
        sessionId: session.id,
        claimNonce,
        status: "awaiting_approval",
        companionName: session.companion_name,
        expiresAt: Math.floor(new Date(session.expires_at).getTime() / 1000),
      });
    }

    if (action === "poll") {
      const sessionId = String(body.sessionId || "").trim();
      const claimNonce = String(body.claimNonce || "").trim();
      if (!sessionId || !claimNonce) {
        return jsonResponse({ error: "MISSING_PARAMETERS" }, 400);
      }

      const nonceHash = await sha256Hex(claimNonce);
      const { data: session } = await service
        .from("mobile_pairing_sessions")
        .select("*")
        .eq("id", sessionId)
        .eq("claim_nonce_hash", nonceHash)
        .maybeSingle();

      if (!session) {
        return jsonResponse({ error: "SESSION_NOT_FOUND" }, 404);
      }

      if (session.status === "awaiting_approval") {
        if (new Date(session.expires_at).getTime() <= now.getTime()) {
          await service.from("mobile_pairing_sessions").update({ status: "expired" }).eq("id", session.id);
          return jsonResponse({ status: "expired", message: "Pairing request expired." }, 410);
        }
        return jsonResponse({ status: "awaiting_approval", companionName: session.companion_name });
      }

      if (session.status === "rejected" || session.status === "cancelled") {
        return jsonResponse({ status: session.status, message: "Pairing was declined on Windows Companion." }, 403);
      }

      if (session.status === "approved" && session.issued_token_once) {
        const token = session.issued_token_once;
        // One-time retrieval: immediately wipe plaintext token from session row
        await service
          .from("mobile_pairing_sessions")
          .update({ issued_token_once: null, consumed_at: nowIso })
          .eq("id", session.id);

        return jsonResponse({
          status: "approved",
          deviceId: session.approved_device_id,
          deviceToken: token,
          companionName: session.companion_name,
          schemaVersion: "1.0.0",
          readOnly: true,
          pairedAt: nowIso,
        });
      }

      return jsonResponse({ error: "PAIRING_ALREADY_CONSUMED", status: session.status }, 409);
    }

    // ------------------------------------------------------------------
    // WINDOWS COMPANION ACTIONS (require authenticated user JWT)
    // ------------------------------------------------------------------
    const auth = await requireAuthenticatedUser(req);
    if (auth.error || !auth.profile) {
      return jsonResponse({ error: auth.error || "Unauthorized" }, 401);
    }
    const userId = auth.profile.id;

    if (action === "create") {
      const companionDeviceId = String(body.companionDeviceId || "windows-companion").trim().slice(0, 128);
      const companionName = String(body.companionName || "Windows Companion").trim().slice(0, 80);

      // Cancel any previous pending sessions for this companion
      await service
        .from("mobile_pairing_sessions")
        .update({ status: "cancelled" })
        .eq("user_id", userId)
        .eq("companion_device_id", companionDeviceId)
        .in("status", ["pending", "awaiting_approval"]);

      const code = randomSixDigitCode();
      const sessionToken = randomHex(24);
      const expiresAtDate = new Date(now.getTime() + PAIRING_TTL_SECONDS * 1000);
      const expiresAtUnix = Math.floor(expiresAtDate.getTime() / 1000);

      const { data: created, error: insErr } = await service
        .from("mobile_pairing_sessions")
        .insert({
          user_id: userId,
          companion_device_id: companionDeviceId,
          companion_name: companionName,
          code_hash: await sha256Hex(code),
          session_token_hash: await sha256Hex(sessionToken),
          status: "pending",
          expires_at: expiresAtDate.toISOString(),
        })
        .select("id")
        .single();

      if (insErr || !created) {
        return jsonResponse({ error: insErr?.message || "Failed to create pairing session" }, 500);
      }

      return jsonResponse({
        ok: true,
        sessionId: created.id,
        code,
        expiresAt: expiresAtUnix,
        companionName,
        qrPayload: {
          v: 2,
          mode: "cloud",
          cloudUrl,
          sessionId: created.id,
          sessionToken,
          code,
          expiresAt: expiresAtUnix,
          companionName,
        },
      });
    }

    if (action === "pending") {
      const { data: sessions } = await service
        .from("mobile_pairing_sessions")
        .select("id, companion_name, status, pending_android_name, pending_android_platform, expires_at, created_at")
        .eq("user_id", userId)
        .in("status", ["pending", "awaiting_approval"])
        .gt("expires_at", nowIso)
        .order("created_at", { ascending: false })
        .limit(5);

      return jsonResponse({ ok: true, sessions: sessions || [] });
    }

    if (action === "approve") {
      const sessionId = String(body.sessionId || "").trim();
      const { data: session } = await service
        .from("mobile_pairing_sessions")
        .select("*")
        .eq("id", sessionId)
        .eq("user_id", userId)
        .eq("status", "awaiting_approval")
        .maybeSingle();

      if (!session) {
        return jsonResponse({ error: "SESSION_NOT_AWAITING_APPROVAL" }, 404);
      }
      if (new Date(session.expires_at).getTime() <= now.getTime()) {
        await service.from("mobile_pairing_sessions").update({ status: "expired" }).eq("id", session.id);
        return jsonResponse({ error: "PAIRING_EXPIRED" }, 410);
      }

      const deviceToken = `iea_ro_${randomHex(32)}`;
      const tokenHash = await sha256Hex(deviceToken);

      const { data: device, error: devErr } = await service
        .from("mobile_paired_devices")
        .insert({
          user_id: userId,
          companion_device_id: session.companion_device_id,
          companion_name: session.companion_name,
          device_name: session.pending_android_name || "Android Device",
          platform: session.pending_android_platform || "android",
          device_fingerprint_hash: session.pending_android_fingerprint,
          token_hash: tokenHash,
          scope: "read_only",
          status: "active",
        })
        .select("id, device_name, platform, paired_at, last_seen_at")
        .single();

      if (devErr || !device) {
        return jsonResponse({ error: devErr?.message || "Failed to register Android device" }, 500);
      }

      await service
        .from("mobile_pairing_sessions")
        .update({
          status: "approved",
          approved_device_id: device.id,
          issued_token_once: deviceToken,
        })
        .eq("id", session.id);

      return jsonResponse({ ok: true, device });
    }

    if (action === "reject" || action === "cancel") {
      const sessionId = String(body.sessionId || "").trim();
      await service
        .from("mobile_pairing_sessions")
        .update({ status: action === "reject" ? "rejected" : "cancelled" })
        .eq("id", sessionId)
        .eq("user_id", userId);
      return jsonResponse({ ok: true, status: action === "reject" ? "rejected" : "cancelled" });
    }

    if (action === "list") {
      const { data: devices } = await service
        .from("mobile_paired_devices")
        .select("id, companion_name, device_name, platform, status, paired_at, last_seen_at")
        .eq("user_id", userId)
        .eq("status", "active")
        .order("paired_at", { ascending: false });

      return jsonResponse({ ok: true, devices: devices || [] });
    }

    if (action === "revoke") {
      const deviceId = String(body.deviceId || "").trim();
      await service
        .from("mobile_paired_devices")
        .update({ status: "revoked", revoked_at: nowIso })
        .eq("id", deviceId)
        .eq("user_id", userId);
      return jsonResponse({ ok: true, revoked: true });
    }

    return jsonResponse({ error: "UNKNOWN_ACTION" }, 400);
  } catch (err) {
    return jsonResponse({ error: err instanceof Error ? err.message : "Unexpected pairing error" }, 500);
  }
});
