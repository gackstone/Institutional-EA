// Supabase Edge Function: admin-manage-subscription
// Server-side administrator operations for subscription lifecycle changes & device revocation.

import { corsHeaders, createServiceClient, jsonResponse, requireAdminUser } from "../_shared/auth.ts";

interface ManageRequest {
  action: "suspend_subscription" | "activate_subscription" | "cancel_subscription" | "revoke_device";
  subscription_id?: string;
  device_id?: string;
  reason?: string;
  duration_days?: number;
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }
  if (req.method !== "POST") {
    return jsonResponse({ error: "Method not allowed" }, 405);
  }

  try {
    const adminCheck = await requireAdminUser(req);
    if (adminCheck.error || !adminCheck.profile) {
      return jsonResponse({ error: adminCheck.error }, adminCheck.status);
    }

    const body = (await req.json()) as ManageRequest;
    const service = createServiceClient();
    const reason = (body.reason || "").trim();

    if (body.action === "revoke_device") {
      if (!body.device_id) {
        return jsonResponse({ error: "device_id is required." }, 400);
      }
      const { data: device, error } = await service
        .from("devices")
        .update({ status: "revoked" })
        .eq("id", body.device_id)
        .select()
        .single();

      if (error || !device) {
        return jsonResponse({ error: error?.message || "Device not found." }, 404);
      }

      await service.from("audit_logs").insert({
        user_id: device.user_id,
        actor_id: adminCheck.profile.id,
        action: "admin.device_revoked",
        resource_type: "device",
        resource_id: device.id,
        metadata: { device_name: device.device_name, reason },
      });

      return jsonResponse({ ok: true, device });
    }

    if (!body.subscription_id) {
      return jsonResponse({ error: "subscription_id is required." }, 400);
    }

    const { data: existing, error: subErr } = await service
      .from("subscriptions")
      .select("*")
      .eq("id", body.subscription_id)
      .single();

    if (subErr || !existing) {
      return jsonResponse({ error: "Subscription not found." }, 404);
    }

    const nowIso = new Date().toISOString();
    let patch: Record<string, unknown> = {};

    if (body.action === "suspend_subscription") {
      patch = { status: "suspended" };
    } else if (body.action === "cancel_subscription") {
      patch = { status: "cancelled" };
    } else if (body.action === "activate_subscription") {
      const days = Math.max(1, Math.min(365, Number(body.duration_days || 30)));
      const expIso = new Date(Date.now() + days * 24 * 60 * 60 * 1000).toISOString();
      patch = {
        status: "active",
        started_at: existing.started_at || nowIso,
        expires_at: expIso,
      };
    } else {
      return jsonResponse({ error: "Unsupported action." }, 400);
    }

    const { data: updated, error: updErr } = await service
      .from("subscriptions")
      .update(patch)
      .eq("id", body.subscription_id)
      .select()
      .single();

    if (updErr) return jsonResponse({ error: updErr.message }, 500);

    await service.from("audit_logs").insert({
      user_id: existing.user_id,
      actor_id: adminCheck.profile.id,
      action: `admin.${body.action}`,
      resource_type: "subscription",
      resource_id: existing.id,
      metadata: { previous_status: existing.status, new_status: updated.status, reason },
    });

    return jsonResponse({ ok: true, subscription: updated });
  } catch (err) {
    return jsonResponse({ error: err instanceof Error ? err.message : "Unexpected server error" }, 500);
  }
});
