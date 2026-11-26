import React, { useCallback, useEffect, useState } from "react";
import {
  CheckCircle2,
  ClipboardList,
  Laptop,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Users,
  Wallet,
  XCircle,
} from "lucide-react";
import {
  formatPaymentStatusLabel,
  formatSubscriptionStatusLabel,
  type AuditLogRecord,
  type DeviceRecord,
  type PaymentRecord,
  type ProfileRecord,
  type SubscriptionRecord,
} from "@institutional-ea/cloud-contract";
import { useAuth } from "../context/AuthContext";
import { supabaseDb, supabaseFunctions } from "../lib/supabaseClient";

type AdminTab = "payments" | "subscriptions" | "devices" | "audit";

export const AdminDashboardPage: React.FC = () => {
  const { session, isAdmin } = useAuth();
  const [tab, setTab] = useState<AdminTab>("payments");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionFeedback, setActionFeedback] = useState<string | null>(null);

  const [profiles, setProfiles] = useState<ProfileRecord[]>([]);
  const [subscriptions, setSubscriptions] = useState<SubscriptionRecord[]>([]);
  const [payments, setPayments] = useState<PaymentRecord[]>([]);
  const [devices, setDevices] = useState<DeviceRecord[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLogRecord[]>([]);
  const [rejectReasons, setRejectReasons] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);

  const loadAdminData = useCallback(async () => {
    if (!session || !isAdmin) return;
    setLoading(true);
    setError(null);
    try {
      const [profs, subs, pmts, devs, logs] = await Promise.all([
        supabaseDb.adminListProfiles(session.access_token),
        supabaseDb.adminListSubscriptions(session.access_token),
        supabaseDb.adminListPayments(session.access_token),
        supabaseDb.adminListDevices(session.access_token),
        supabaseDb.adminListAuditLogs(session.access_token),
      ]);
      setProfiles(profs);
      setSubscriptions(subs);
      setPayments(pmts);
      setDevices(devs);
      setAuditLogs(logs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load administrative records.");
    } finally {
      setLoading(false);
    }
  }, [session, isAdmin]);

  useEffect(() => {
    loadAdminData();
  }, [loadAdminData]);

  if (!session || !isAdmin) {
    return (
      <div className="mx-auto max-w-xl px-4 py-20 text-center">
        <div className="rounded-2xl border border-red-500/25 bg-[#111216] p-8">
          <ShieldAlert className="mx-auto h-10 w-10 text-red-400" />
          <h1 className="mt-4 text-xl font-bold text-white">Administrator Access Required</h1>
          <p className="mt-2 text-xs leading-relaxed text-[#9CA3AF]">
            This module is strictly restricted to server-verified Institutional EA administrators.
            All approval and subscription mutations are validated server-side via Supabase Edge
            Functions and Row Level Security.
          </p>
        </div>
      </div>
    );
  }

  const profileById = new Map(profiles.map((p) => [p.id, p]));

  const handlePaymentDecision = async (
    paymentId: string,
    decision: "under_review" | "approve" | "reject"
  ) => {
    setError(null);
    setActionFeedback(null);
    const reason = (rejectReasons[paymentId] || "").trim();
    if (decision === "reject" && reason.length < 5) {
      setError("Please enter a rejection reason (at least 5 characters) before rejecting.");
      return;
    }

    setBusyId(paymentId);
    try {
      await supabaseFunctions.adminReviewPayment(session.access_token, {
        payment_id: paymentId,
        decision,
        rejection_reason: decision === "reject" ? reason : undefined,
      });
      setActionFeedback(`Payment ${paymentId.slice(0, 8)} updated (${decision}).`);
      await loadAdminData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Payment review action failed.");
    } finally {
      setBusyId(null);
    }
  };

  const handleManageSubscription = async (
    subscriptionId: string,
    action: "suspend_subscription" | "activate_subscription" | "cancel_subscription"
  ) => {
    setError(null);
    setActionFeedback(null);
    setBusyId(subscriptionId);
    try {
      await supabaseFunctions.adminManageSubscription(session.access_token, {
        action,
        subscription_id: subscriptionId,
        duration_days: 30,
      });
      setActionFeedback(`Subscription ${subscriptionId.slice(0, 8)} updated (${action}).`);
      await loadAdminData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Subscription update failed.");
    } finally {
      setBusyId(null);
    }
  };

  const handleRevokeDevice = async (deviceId: string) => {
    setError(null);
    setBusyId(deviceId);
    try {
      await supabaseFunctions.adminManageSubscription(session.access_token, {
        action: "revoke_device",
        device_id: deviceId,
        reason: "Revoked by administrator",
      });
      setActionFeedback(`Device ${deviceId.slice(0, 8)} revoked.`);
      await loadAdminData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Device revocation failed.");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-white/[0.08] pb-6">
        <div className="flex items-center gap-3">
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-2.5 text-amber-300">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-white">Payment & Subscription Administration</h1>
            <p className="text-xs text-[#9CA3AF]">
              Server-verified admin console · Auditable payment approvals & device governance
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={loadAdminData}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-[#111216] px-3.5 py-2 text-xs font-semibold text-white hover:bg-[#16181D]"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          Reload Data
        </button>
      </div>

      {error && (
        <div className="mt-5 rounded-xl border border-red-500/30 bg-red-500/10 p-3.5 text-xs text-red-300">
          {error}
        </div>
      )}
      {actionFeedback && (
        <div className="mt-5 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3.5 text-xs text-emerald-300">
          {actionFeedback}
        </div>
      )}

      {/* Tabs */}
      <div className="mt-6 flex flex-wrap gap-2">
        {(
          [
            { id: "payments", label: `Payments (${payments.length})`, icon: Wallet },
            { id: "subscriptions", label: `Users & Subscriptions (${subscriptions.length})`, icon: Users },
            { id: "devices", label: `Devices (${devices.length})`, icon: Laptop },
            { id: "audit", label: `Audit Logs (${auditLogs.length})`, icon: ClipboardList },
          ] as const
        ).map((t) => {
          const Icon = t.icon;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`inline-flex items-center gap-2 rounded-lg border px-4 py-2 text-xs font-semibold transition ${
                tab === t.id
                  ? "border-blue-500/40 bg-blue-500/15 text-blue-300"
                  : "border-white/10 bg-[#111216] text-[#9CA3AF] hover:text-white"
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              {t.label}
            </button>
          );
        })}
      </div>

      {/* Tab Content */}
      <div className="mt-6 rounded-2xl border border-white/10 bg-[#111216] p-6">
        {tab === "payments" && (
          <div className="space-y-4">
            {payments.length === 0 ? (
              <p className="text-xs text-[#9CA3AF]">No payment submissions found.</p>
            ) : (
              payments.map((p) => {
                const userProf = profileById.get(p.user_id);
                const actionable = p.status === "submitted" || p.status === "under_review" || p.status === "pending";
                return (
                  <div
                    key={p.id}
                    className="rounded-xl border border-white/[0.08] bg-[#0D0E11] p-4 text-xs"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="font-semibold text-white">
                          {userProf?.full_name || "User"} ({userProf?.email || p.user_id})
                        </div>
                        <div className="mt-1 font-mono text-[11px] text-[#9CA3AF]">
                          {p.provider} · {p.network} · {p.amount} {p.asset} · Submitted{" "}
                          {new Date(p.submitted_at).toISOString()}
                        </div>
                        <div className="mt-1 break-all font-mono text-[11px] text-blue-300">
                          TXID: {p.transaction_reference}
                        </div>
                      </div>
                      <span className="rounded-full border border-white/15 bg-white/5 px-2.5 py-0.5 text-[11px] font-semibold text-white">
                        {formatPaymentStatusLabel(p.status)}
                      </span>
                    </div>

                    {actionable && (
                      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-white/[0.06] pt-3">
                        {p.status !== "under_review" && (
                          <button
                            type="button"
                            disabled={busyId === p.id}
                            onClick={() => handlePaymentDecision(p.id, "under_review")}
                            className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 font-semibold text-amber-300 hover:bg-amber-500/20"
                          >
                            Mark Under Review
                          </button>
                        )}
                        <button
                          type="button"
                          disabled={busyId === p.id}
                          onClick={() => handlePaymentDecision(p.id, "approve")}
                          className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 font-semibold text-white hover:bg-emerald-500"
                        >
                          <CheckCircle2 className="h-3.5 w-3.5" />
                          Approve & Activate 30d
                        </button>
                        <input
                          type="text"
                          value={rejectReasons[p.id] || ""}
                          onChange={(e) =>
                            setRejectReasons((prev) => ({ ...prev, [p.id]: e.target.value }))
                          }
                          placeholder="Rejection reason..."
                          className="min-w-[200px] flex-1 rounded-lg border border-white/10 bg-[#111216] px-3 py-1.5 text-xs text-white"
                        />
                        <button
                          type="button"
                          disabled={busyId === p.id}
                          onClick={() => handlePaymentDecision(p.id, "reject")}
                          className="inline-flex items-center gap-1.5 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-1.5 font-semibold text-red-300 hover:bg-red-500/20"
                        >
                          <XCircle className="h-3.5 w-3.5" />
                          Reject
                        </button>
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        )}

        {tab === "subscriptions" && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-white/[0.08] text-[11px] uppercase text-[#6B7280]">
                <tr>
                  <th className="py-2.5 pr-4">User</th>
                  <th className="py-2.5 pr-4">Status</th>
                  <th className="py-2.5 pr-4">Expires (UTC)</th>
                  <th className="py-2.5">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.05] text-[#D1D5DB]">
                {subscriptions.map((sub) => {
                  const userProf = profileById.get(sub.user_id);
                  return (
                    <tr key={sub.id}>
                      <td className="py-3 pr-4">
                        <div className="font-semibold text-white">{userProf?.full_name || "User"}</div>
                        <div className="text-[11px] text-[#6B7280]">{userProf?.email || sub.user_id}</div>
                      </td>
                      <td className="py-3 pr-4 font-semibold">
                        {formatSubscriptionStatusLabel(sub.status)}
                      </td>
                      <td className="py-3 pr-4 font-mono">
                        {sub.expires_at ? new Date(sub.expires_at).toISOString() : "—"}
                      </td>
                      <td className="py-3">
                        <div className="flex flex-wrap gap-2">
                          <button
                            type="button"
                            disabled={busyId === sub.id}
                            onClick={() => handleManageSubscription(sub.id, "activate_subscription")}
                            className="rounded border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-semibold text-emerald-300"
                          >
                            Activate 30d
                          </button>
                          <button
                            type="button"
                            disabled={busyId === sub.id}
                            onClick={() => handleManageSubscription(sub.id, "suspend_subscription")}
                            className="rounded border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-[11px] font-semibold text-amber-300"
                          >
                            Suspend
                          </button>
                          <button
                            type="button"
                            disabled={busyId === sub.id}
                            onClick={() => handleManageSubscription(sub.id, "cancel_subscription")}
                            className="rounded border border-red-500/30 bg-red-500/10 px-2.5 py-1 text-[11px] font-semibold text-red-300"
                          >
                            Cancel
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {tab === "devices" && (
          <div className="divide-y divide-white/[0.06] text-xs">
            {devices.map((dev) => {
              const userProf = profileById.get(dev.user_id);
              return (
                <div key={dev.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <div>
                    <div className="font-semibold text-white">
                      {dev.device_name} ({userProf?.email || dev.user_id})
                    </div>
                    <div className="font-mono text-[11px] text-[#6B7280]">
                      {dev.operating_system} · v{dev.app_version} · {dev.device_fingerprint_hash.slice(0, 14)}…
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-[11px] uppercase text-[#9CA3AF]">{dev.status}</span>
                    {dev.status === "active" && (
                      <button
                        type="button"
                        disabled={busyId === dev.id}
                        onClick={() => handleRevokeDevice(dev.id)}
                        className="rounded border border-red-500/30 bg-red-500/10 px-2.5 py-1 text-[11px] font-semibold text-red-300"
                      >
                        Revoke
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {tab === "audit" && (
          <div className="space-y-2 font-mono text-[11px]">
            {auditLogs.map((log) => (
              <div
                key={log.id}
                className="rounded-lg border border-white/[0.06] bg-[#0D0E11] p-3 text-[#D1D5DB]"
              >
                <span className="text-[#6B7280]">{new Date(log.created_at).toISOString()}</span>{" "}
                <span className="font-semibold text-blue-300">{log.action}</span>{" "}
                <span className="text-[#9CA3AF]">
                  ({log.resource_type}:{log.resource_id || "n/a"})
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
