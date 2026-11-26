// Supabase Edge Function: admin-review-payment
// Strictly server-side administrator payment approval / rejection with idempotency,
// UTC subscription activation/extension (+30 days), and immutable audit logging.

import { corsHeaders, createServiceClient, jsonResponse, requireAdminUser } from "../_shared/auth.ts";

interface ReviewPaymentRequest {
  payment_id: string;
  decision: "under_review" | "approve" | "reject";
  rejection_reason?: string;
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

    const body = (await req.json()) as ReviewPaymentRequest;
    const paymentId = (body?.payment_id || "").trim();
    const decision = body?.decision;
    const rejectionReason = (body?.rejection_reason || "").trim();

    if (!paymentId || !["under_review", "approve", "reject"].includes(decision)) {
      return jsonResponse({ error: "Valid payment_id and decision ('under_review' | 'approve' | 'reject') are required." }, 400);
    }
    if (decision === "reject" && rejectionReason.length < 5) {
      return jsonResponse({ error: "A clear rejection_reason (at least 5 characters) is required when rejecting a payment." }, 400);
    }

    const service = createServiceClient();
    const { data: payment, error: fetchErr } = await service
      .from("payments")
      .select("*")
      .eq("id", paymentId)
      .single();

    if (fetchErr || !payment) {
      return jsonResponse({ error: "Payment record not found." }, 404);
    }

    const nowIso = new Date().toISOString();

    if (decision === "under_review") {
      if (payment.status !== "submitted" && payment.status !== "pending") {
        return jsonResponse({ error: `Cannot mark payment in status '${payment.status}' as under_review.` }, 409);
      }

      const { data: updated, error: updErr } = await service
        .from("payments")
        .update({ status: "under_review" })
        .eq("id", paymentId)
        .select()
        .single();

      if (updErr) return jsonResponse({ error: updErr.message }, 500);

      await service.from("audit_logs").insert({
        user_id: payment.user_id,
        actor_id: adminCheck.profile.id,
        action: "payment.marked_under_review",
        resource_type: "payment",
        resource_id: paymentId,
        metadata: { txid: payment.transaction_reference },
      });

      return jsonResponse({ ok: true, payment: updated });
    }

    // Idempotency guard: prevent double activation or modifying finalized payments
    if (payment.status === "approved" || payment.activation_applied) {
      return jsonResponse({ error: "Payment has already been approved and applied." }, 409);
    }
    if (payment.status === "rejected") {
      return jsonResponse({ error: "Payment has already been rejected." }, 409);
    }

    if (decision === "reject") {
      const { data: rejectedPayment, error: rejErr } = await service
        .from("payments")
        .update({
          status: "rejected",
          reviewed_at: nowIso,
          reviewed_by: adminCheck.profile.id,
          rejection_reason: rejectionReason,
        })
        .eq("id", paymentId)
        .select()
        .single();

      if (rejErr) return jsonResponse({ error: rejErr.message }, 500);

      if (payment.subscription_id) {
        await service
          .from("subscriptions")
          .update({ status: "payment_rejected" })
          .eq("id", payment.subscription_id)
          .neq("status", "active");
      }

      await service.from("audit_logs").insert({
        user_id: payment.user_id,
        actor_id: adminCheck.profile.id,
        action: "payment.rejected",
        resource_type: "payment",
        resource_id: paymentId,
        metadata: {
          txid: payment.transaction_reference,
          rejection_reason: rejectionReason,
        },
      });

      return jsonResponse({ ok: true, payment: rejectedPayment });
    }

    // decision === "approve": Atomically mark payment approved (guarded by activation_applied = false)
    const { data: approvedPayment, error: appErr } = await service
      .from("payments")
      .update({
        status: "approved",
        reviewed_at: nowIso,
        reviewed_by: adminCheck.profile.id,
        rejection_reason: null,
        activation_applied: true,
      })
      .eq("id", paymentId)
      .eq("activation_applied", false)
      .select()
      .single();

    if (appErr || !approvedPayment) {
      return jsonResponse({ error: "Payment approval failed or was already processed concurrently." }, 409);
    }

    // Compute new UTC subscription window: extend from existing expires_at if still active in future, else from now
    const nowMs = Date.now();
    const durationMs = 30 * 24 * 60 * 60 * 1000;
    let baseStartMs = nowMs;
    let startedAtIso = nowIso;

    let targetSubId = payment.subscription_id;
    if (targetSubId) {
      const { data: existingSub } = await service
        .from("subscriptions")
        .select("*")
        .eq("id", targetSubId)
        .single();

      if (existingSub?.status === "active" && existingSub.expires_at) {
        const expMs = Date.parse(existingSub.expires_at);
        if (Number.isFinite(expMs) && expMs > nowMs) {
          baseStartMs = expMs;
          startedAtIso = existingSub.started_at || nowIso;
        }
      }
    }

    const newExpiresAtIso = new Date(baseStartMs + durationMs).toISOString();
    let updatedSub = null;

    if (targetSubId) {
      const { data: subData } = await service
        .from("subscriptions")
        .update({
          status: "active",
          started_at: startedAtIso,
          expires_at: newExpiresAtIso,
          amount: 50.0,
          currency: "USD",
          billing_interval: "monthly",
        })
        .eq("id", targetSubId)
        .select()
        .single();
      updatedSub = subData;
    } else {
      const { data: subData } = await service
        .from("subscriptions")
        .insert({
          user_id: payment.user_id,
          plan_id: "00000000-0000-4000-8000-000000000001",
          status: "active",
          amount: 50.0,
          currency: "USD",
          billing_interval: "monthly",
          started_at: startedAtIso,
          expires_at: newExpiresAtIso,
        })
        .select()
        .single();
      updatedSub = subData;
    }

    await service.from("audit_logs").insert({
      user_id: payment.user_id,
      actor_id: adminCheck.profile.id,
      action: "payment.approved_and_subscription_activated",
      resource_type: "payment",
      resource_id: paymentId,
      metadata: {
        txid: payment.transaction_reference,
        amount: payment.amount,
        asset: payment.asset,
        network: payment.network,
        subscription_id: updatedSub?.id ?? targetSubId,
        expires_at_utc: newExpiresAtIso,
      },
    });

    return jsonResponse({ ok: true, payment: approvedPayment, subscription: updatedSub });
  } catch (err) {
    return jsonResponse({ error: err instanceof Error ? err.message : "Unexpected server error" }, 500);
  }
});
