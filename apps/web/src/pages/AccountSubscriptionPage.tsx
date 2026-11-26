import React, { useState } from "react";
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  Clock,
  Copy,
  Laptop,
  RefreshCw,
  ShieldAlert,
  Trash2,
  Upload,
  Wallet,
} from "lucide-react";
import {
  BINANCE_USDT_TRC20_CONFIG,
  INSTITUTIONAL_EA_PRO_PLAN,
  formatPaymentStatusLabel,
  formatSubscriptionStatusLabel,
  validatePaymentSubmission,
  type SubscriptionStatus,
} from "@institutional-ea/cloud-contract";
import { Link } from "../lib/router";
import { useAuth } from "../context/AuthContext";
import { supabaseDb, supabaseStorage } from "../lib/supabaseClient";

function statusTone(status: SubscriptionStatus): string {
  switch (status) {
    case "active":
      return "border-emerald-500/30 bg-emerald-500/10 text-emerald-300";
    case "payment_under_review":
    case "pending_payment":
      return "border-amber-500/30 bg-amber-500/10 text-amber-300";
    case "payment_rejected":
    case "suspended":
    case "expired":
      return "border-red-500/30 bg-red-500/10 text-red-300";
    default:
      return "border-white/15 bg-white/5 text-[#D1D5DB]";
  }
}

function formatUtc(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${d.toISOString().replace("T", " ").slice(0, 19)} UTC`;
}

export const AccountSubscriptionPage: React.FC = () => {
  const {
    session,
    profile,
    subscription,
    entitlement,
    payments,
    devices,
    loading,
    refreshAccount,
  } = useAuth();

  const [copiedAddress, setCopiedAddress] = useState(false);
  const [amountSent, setAmountSent] = useState<string>(String(BINANCE_USDT_TRC20_CONFIG.amountUsdt));
  const [txid, setTxid] = useState("");
  const [paymentDate, setPaymentDate] = useState(() => new Date().toISOString().slice(0, 16));
  const [proofFile, setProofFile] = useState<File | null>(null);
  const [networkConfirmed, setNetworkConfirmed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null);
  const [revokingId, setRevokingId] = useState<string | null>(null);

  if (!session) {
    return (
      <div className="mx-auto max-w-xl px-4 py-20 text-center">
        <div className="rounded-2xl border border-white/10 bg-[#111216] p-8">
          <h1 className="text-xl font-bold text-white">Sign In Required</h1>
          <p className="mt-2 text-sm text-[#9CA3AF]">
            Sign in to view your Institutional EA Pro subscription, submit a Binance USDT (TRC20)
            payment, or manage registered Windows devices.
          </p>
          <div className="mt-6 flex justify-center gap-3">
            <Link
              to="/auth/sign-in?next=/account/subscription"
              className="rounded-lg bg-[#3B82F6] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#2563EB]"
            >
              Sign In
            </Link>
            <Link
              to="/auth/sign-up?next=/account/subscription"
              className="rounded-lg border border-white/15 bg-[#0D0E11] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#16181D]"
            >
              Create Account
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const handleCopyAddress = () => {
    navigator.clipboard?.writeText(BINANCE_USDT_TRC20_CONFIG.depositAddress).then(() => {
      setCopiedAddress(true);
      setTimeout(() => setCopiedAddress(false), 2000);
    });
  };

  const handlePaymentSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitError(null);
    setSubmitSuccess(null);

    const trimmedTxid = txid.trim();
    const numericAmount = Number(amountSent);
    const isoDate = paymentDate ? new Date(paymentDate).toISOString() : "";

    const check = validatePaymentSubmission({
      amountSent: numericAmount,
      transactionReference: trimmedTxid,
      paymentDate: isoDate,
      networkConfirmed,
    });
    if (!check.valid) {
      setSubmitError(check.errors.join(" "));
      return;
    }

    // Client-side duplicate TXID pre-check (also enforced by PostgreSQL unique partial index)
    const duplicateLocal = payments.some(
      (p) =>
        p.transaction_reference.trim().toLowerCase() === trimmedTxid.toLowerCase() &&
        p.status !== "rejected"
    );
    if (duplicateLocal) {
      setSubmitError("This Transaction ID (TXID) has already been submitted.");
      return;
    }

    setSubmitting(true);
    try {
      let proofPath: string | null = null;
      if (proofFile) {
        proofPath = await supabaseStorage.uploadPaymentProof(
          session.access_token,
          session.user.id,
          proofFile
        );
      }

      await supabaseDb.submitBinancePayment(session.access_token, {
        user_id: session.user.id,
        subscription_id: subscription?.id ?? null,
        amount: numericAmount,
        transaction_reference: trimmedTxid,
        payment_date: isoDate,
        proof_file_path: proofPath,
      });

      setTxid("");
      setProofFile(null);
      setNetworkConfirmed(false);
      setSubmitSuccess(
        "Payment submitted for administrator verification. Your subscription will activate once the TRC20 deposit is verified."
      );
      await refreshAccount();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Payment submission failed.";
      if (msg.toLowerCase().includes("duplicate") || msg.toLowerCase().includes("uq_payments_tx_ref")) {
        setSubmitError("Duplicate Transaction ID: this TXID has already been recorded.");
      } else {
        setSubmitError(msg);
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleRevokeDevice = async (deviceId: string) => {
    setRevokingId(deviceId);
    try {
      await supabaseDb.revokeOwnDevice(session.access_token, deviceId);
      await refreshAccount();
    } finally {
      setRevokingId(null);
    }
  };

  return (
    <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-white/[0.08] pb-6">
        <div>
          <h1 className="text-2xl font-bold text-white">Account & Subscription</h1>
          <p className="mt-1 text-sm text-[#9CA3AF]">
            {profile?.full_name || "Account Holder"} · {session.user.email}
          </p>
        </div>
        <button
          type="button"
          onClick={() => refreshAccount()}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-[#111216] px-3.5 py-2 text-xs font-semibold text-[#D1D5DB] hover:bg-[#16181D] hover:text-white"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          Refresh Status
        </button>
      </div>

      {/* Subscription Summary Cards */}
      <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-white/[0.08] bg-[#111216] p-5">
          <div className="text-xs text-[#6B7280]">Current Plan</div>
          <div className="mt-1.5 text-base font-bold text-white">
            {subscription?.plan?.name || INSTITUTIONAL_EA_PRO_PLAN.name}
          </div>
          <div className="mt-1 font-mono text-xs text-[#9CA3AF]">
            ${subscription?.amount ?? INSTITUTIONAL_EA_PRO_PLAN.price} USD / month
          </div>
        </div>

        <div className="rounded-xl border border-white/[0.08] bg-[#111216] p-5">
          <div className="text-xs text-[#6B7280]">Subscription Status</div>
          <div className="mt-2">
            <span
              className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${statusTone(
                entitlement.status
              )}`}
            >
              {formatSubscriptionStatusLabel(entitlement.status)}
            </span>
          </div>
          <div className="mt-2 text-[11px] text-[#9CA3AF]">{entitlement.reason}</div>
        </div>

        <div className="rounded-xl border border-white/[0.08] bg-[#111216] p-5">
          <div className="text-xs text-[#6B7280]">Activation Date (UTC)</div>
          <div className="mt-1.5 font-mono text-xs font-semibold text-white">
            {formatUtc(subscription?.started_at)}
          </div>
        </div>

        <div className="rounded-xl border border-white/[0.08] bg-[#111216] p-5">
          <div className="text-xs text-[#6B7280]">Expiration Date (UTC)</div>
          <div className="mt-1.5 font-mono text-xs font-semibold text-white">
            {formatUtc(subscription?.expires_at)}
          </div>
          {entitlement.isActive && entitlement.daysRemaining !== null && (
            <div className="mt-1 font-mono text-[11px] text-emerald-400">
              {entitlement.daysRemaining} day{entitlement.daysRemaining === 1 ? "" : "s"} remaining
            </div>
          )}
        </div>
      </div>

      {/* Binance USDT TRC20 Checkout & Submission Section */}
      <div className="mt-10 grid gap-8 lg:grid-cols-12">
        {/* Left: Official Binance Deposit Instructions & QR Code */}
        <div className="rounded-2xl border border-white/10 bg-[#111216] p-6 lg:col-span-6">
          <div className="flex items-center justify-between border-b border-white/[0.07] pb-4">
            <div className="flex items-center gap-2.5">
              <Wallet className="h-5 w-5 text-amber-400" />
              <div>
                <h2 className="text-base font-bold text-white">
                  Binance USDT (TRC20) Payment
                </h2>
                <p className="text-xs text-[#9CA3AF]">
                  {INSTITUTIONAL_EA_PRO_PLAN.name} · {BINANCE_USDT_TRC20_CONFIG.amountUsdt} USDT / month
                </p>
              </div>
            </div>
            <span className="rounded-md border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 font-mono text-xs font-semibold text-amber-300">
              {BINANCE_USDT_TRC20_CONFIG.network}
            </span>
          </div>

          {/* Supplied Official Binance QR Code Image */}
          <div className="mt-5 flex flex-col items-center rounded-xl border border-white/10 bg-[#0D0E11] p-4">
            <img
              src={BINANCE_USDT_TRC20_CONFIG.qrImagePath}
              alt="Official Binance USDT TRON (TRC20) Deposit QR Code"
              className="w-full max-w-[260px] rounded-xl border border-white/10 bg-white object-contain shadow-lg"
            />
            <div className="mt-3 text-center text-[11px] text-[#9CA3AF]">
              Verify QR address matches:{" "}
              <span className="font-mono text-white">
                {BINANCE_USDT_TRC20_CONFIG.depositAddress}
              </span>
            </div>
          </div>

          {/* Deposit Metadata & Copy Address */}
          <div className="mt-5 space-y-3 text-xs">
            <div className="grid grid-cols-3 gap-2 rounded-lg border border-white/[0.07] bg-[#0D0E11] p-3">
              <div>
                <div className="text-[#6B7280]">Provider</div>
                <div className="mt-0.5 font-semibold text-white">
                  {BINANCE_USDT_TRC20_CONFIG.provider}
                </div>
              </div>
              <div>
                <div className="text-[#6B7280]">Amount Payable</div>
                <div className="mt-0.5 font-mono font-semibold text-emerald-400">
                  {BINANCE_USDT_TRC20_CONFIG.amountUsdt} {BINANCE_USDT_TRC20_CONFIG.asset}
                </div>
              </div>
              <div>
                <div className="text-[#6B7280]">Required Network</div>
                <div className="mt-0.5 font-semibold text-amber-300">
                  {BINANCE_USDT_TRC20_CONFIG.network}
                </div>
              </div>
            </div>

            <div className="rounded-lg border border-white/10 bg-[#0D0E11] p-3.5">
              <div className="text-[11px] font-medium text-[#9CA3AF]">TRC20 Deposit Address</div>
              <div className="mt-1.5 flex items-center justify-between gap-2">
                <code className="break-all font-mono text-xs font-semibold text-white">
                  {BINANCE_USDT_TRC20_CONFIG.depositAddress}
                </code>
                <button
                  type="button"
                  onClick={handleCopyAddress}
                  className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-blue-500/30 bg-blue-500/15 px-3 py-1.5 text-xs font-semibold text-blue-300 transition hover:bg-blue-500/25"
                >
                  {copiedAddress ? (
                    <>
                      <Check className="h-3.5 w-3.5 text-emerald-400" />
                      Copied
                    </>
                  ) : (
                    <>
                      <Copy className="h-3.5 w-3.5" />
                      Copy Address
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>

          {/* Warnings */}
          <div className="mt-5 rounded-xl border border-amber-500/25 bg-amber-500/[0.07] p-4">
            <div className="flex items-center gap-2 text-xs font-semibold text-amber-300">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              Critical Network & Asset Warnings
            </div>
            <ul className="mt-2 space-y-1.5 text-[11px] leading-relaxed text-amber-100/85">
              {BINANCE_USDT_TRC20_CONFIG.warnings.map((w) => (
                <li key={w}>• {w}</li>
              ))}
            </ul>
          </div>
        </div>

        {/* Right: Payment Submission Form */}
        <div className="rounded-2xl border border-white/10 bg-[#111216] p-6 lg:col-span-6">
          <div className="border-b border-white/[0.07] pb-4">
            <h2 className="text-base font-bold text-white">Submit Payment for Verification</h2>
            <p className="mt-1 text-xs text-[#9CA3AF]">
              Workflow: Pending Payment → Submitted for Verification → Under Review → Approved /
              Rejected → Subscription Activated
            </p>
          </div>

          <ol className="mt-4 space-y-1.5 rounded-xl border border-white/[0.06] bg-[#0D0E11] p-4 text-xs text-[#D1D5DB]">
            {BINANCE_USDT_TRC20_CONFIG.instructions.map((step, i) => (
              <li key={step}>
                <span className="font-mono font-semibold text-[#3B82F6]">{i + 1}.</span> {step}
              </li>
            ))}
          </ol>

          <form onSubmit={handlePaymentSubmit} className="mt-5 space-y-4">
            {submitError && (
              <div className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
                <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{submitError}</span>
              </div>
            )}

            {submitSuccess && (
              <div className="flex items-start gap-2 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-300">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{submitSuccess}</span>
              </div>
            )}

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="block text-xs font-medium text-[#D1D5DB]">
                  Amount Sent (USDT)
                </label>
                <input
                  type="number"
                  step="0.01"
                  min={BINANCE_USDT_TRC20_CONFIG.amountUsdt}
                  required
                  value={amountSent}
                  onChange={(e) => setAmountSent(e.target.value)}
                  className="mt-1.5 w-full rounded-lg border border-white/10 bg-[#0D0E11] px-3 py-2.5 font-mono text-sm text-white focus:border-[#3B82F6] focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-[#D1D5DB]">
                  Payment Date & Time (UTC)
                </label>
                <input
                  type="datetime-local"
                  required
                  value={paymentDate}
                  onChange={(e) => setPaymentDate(e.target.value)}
                  className="mt-1.5 w-full rounded-lg border border-white/10 bg-[#0D0E11] px-3 py-2.5 font-mono text-xs text-white focus:border-[#3B82F6] focus:outline-none"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-[#D1D5DB]">
                Transaction ID / TXID (TRON TRC20 Hash)
              </label>
              <input
                type="text"
                required
                value={txid}
                onChange={(e) => setTxid(e.target.value)}
                placeholder="Paste your 64-character TRON TXID or Binance transfer ID"
                className="mt-1.5 w-full rounded-lg border border-white/10 bg-[#0D0E11] px-3 py-2.5 font-mono text-xs text-white placeholder-[#6B7280] focus:border-[#3B82F6] focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-[#D1D5DB]">
                Optional Receipt Screenshot (PNG/JPG/PDF, max 5 MB)
              </label>
              <label className="mt-1.5 flex cursor-pointer items-center justify-between rounded-lg border border-dashed border-white/15 bg-[#0D0E11] px-3.5 py-2.5 text-xs text-[#9CA3AF] hover:border-white/30">
                <span className="truncate">
                  {proofFile ? proofFile.name : "Select receipt screenshot (optional)"}
                </span>
                <Upload className="h-4 w-4 shrink-0 text-[#3B82F6]" />
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp,application/pdf"
                  className="hidden"
                  onChange={(e) => setProofFile(e.target.files?.[0] ?? null)}
                />
              </label>
              <p className="mt-1 text-[11px] text-[#6B7280]">
                Note: A screenshot assists review but is not proof of an on-chain transaction.
              </p>
            </div>

            <label className="flex items-start gap-2.5 rounded-lg border border-white/[0.07] bg-[#0D0E11] p-3 text-xs text-[#D1D5DB]">
              <input
                type="checkbox"
                checked={networkConfirmed}
                onChange={(e) => setNetworkConfirmed(e.target.checked)}
                className="mt-0.5 h-3.5 w-3.5 rounded border-white/20 bg-[#111216] text-[#3B82F6]"
              />
              <span>
                I confirm that I sent <strong>USDT</strong> via the{" "}
                <strong>{BINANCE_USDT_TRC20_CONFIG.network}</strong> network to{" "}
                <code className="font-mono text-white">
                  {BINANCE_USDT_TRC20_CONFIG.depositAddress}
                </code>
                .
              </span>
            </label>

            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-xl bg-[#3B82F6] py-3 text-sm font-semibold text-white transition hover:bg-[#2563EB] disabled:opacity-60"
            >
              {submitting ? "Submitting Payment..." : "Submit Payment for Verification"}
            </button>
          </form>
        </div>
      </div>

      {/* Transaction History */}
      <div className="mt-10 rounded-2xl border border-white/10 bg-[#111216] p-6">
        <div className="flex items-center gap-2">
          <Clock className="h-4 w-4 text-[#3B82F6]" />
          <h2 className="text-base font-bold text-white">Payment & Transaction History</h2>
        </div>

        {payments.length === 0 ? (
          <p className="mt-4 text-xs text-[#9CA3AF]">
            No payment submissions recorded yet. Submit your Binance USDT TRC20 transaction above
            to activate Institutional EA Pro.
          </p>
        ) : (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-white/[0.08] text-[11px] uppercase text-[#6B7280]">
                <tr>
                  <th className="py-2.5 pr-4">Submitted (UTC)</th>
                  <th className="py-2.5 pr-4">Provider / Network</th>
                  <th className="py-2.5 pr-4">Amount</th>
                  <th className="py-2.5 pr-4">TXID</th>
                  <th className="py-2.5 pr-4">Status</th>
                  <th className="py-2.5">Notes</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.05] text-[#D1D5DB]">
                {payments.map((p) => (
                  <tr key={p.id}>
                    <td className="py-3 pr-4 font-mono">{formatUtc(p.submitted_at)}</td>
                    <td className="py-3 pr-4">
                      {p.provider} · {p.network}
                    </td>
                    <td className="py-3 pr-4 font-mono font-semibold text-white">
                      {p.amount} {p.asset}
                    </td>
                    <td className="py-3 pr-4 font-mono text-[11px]">
                      {p.transaction_reference.slice(0, 22)}
                      {p.transaction_reference.length > 22 ? "…" : ""}
                    </td>
                    <td className="py-3 pr-4">
                      <span className="rounded-full border border-white/15 bg-white/5 px-2.5 py-0.5 text-[11px] font-semibold">
                        {formatPaymentStatusLabel(p.status)}
                      </span>
                    </td>
                    <td className="py-3 text-[11px] text-[#9CA3AF]">
                      {p.rejection_reason || (p.reviewed_at ? `Reviewed ${formatUtc(p.reviewed_at)}` : "Awaiting admin review")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Registered Windows Devices */}
      <div className="mt-8 rounded-2xl border border-white/10 bg-[#111216] p-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Laptop className="h-4 w-4 text-[#3B82F6]" />
            <h2 className="text-base font-bold text-white">Registered Companion Devices</h2>
          </div>
          <span className="font-mono text-[11px] text-[#6B7280]">
            Max 3 active devices (enforced server-side)
          </span>
        </div>

        {devices.length === 0 ? (
          <p className="mt-4 text-xs text-[#9CA3AF]">
            No Windows Companion devices registered yet. Sign in from the Windows Companion App to
            automatically register your workstation using a privacy-conscious hashed fingerprint.
          </p>
        ) : (
          <div className="mt-4 divide-y divide-white/[0.06]">
            {devices.map((dev) => (
              <div
                key={dev.id}
                className="flex flex-wrap items-center justify-between gap-3 py-3 text-xs"
              >
                <div>
                  <div className="font-semibold text-white">{dev.device_name}</div>
                  <div className="mt-0.5 font-mono text-[11px] text-[#6B7280]">
                    {dev.operating_system} · v{dev.app_version} · Hash:{" "}
                    {dev.device_fingerprint_hash.slice(0, 12)}… · Last seen{" "}
                    {formatUtc(dev.last_seen_at)}
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
                      dev.status === "active"
                        ? "bg-emerald-500/15 text-emerald-300"
                        : "bg-red-500/15 text-red-300"
                    }`}
                  >
                    {dev.status.toUpperCase()}
                  </span>
                  {dev.status === "active" && (
                    <button
                      type="button"
                      disabled={revokingId === dev.id}
                      onClick={() => handleRevokeDevice(dev.id)}
                      className="inline-flex items-center gap-1 rounded-lg border border-red-500/30 bg-red-500/10 px-2.5 py-1 text-[11px] font-semibold text-red-300 hover:bg-red-500/20"
                    >
                      <Trash2 className="h-3 w-3" />
                      Revoke
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
