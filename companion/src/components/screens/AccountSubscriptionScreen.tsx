import React, { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  Copy,
  ExternalLink,
  Laptop,
  Lock,
  LogOut,
  RefreshCw,
  ShieldCheck,
  Trash2,
  User,
  Wallet,
  Wifi,
  WifiOff,
} from "lucide-react";
import {
  BINANCE_USDT_TRC20_CONFIG,
  INSTITUTIONAL_EA_PRO_PLAN,
  formatPaymentStatusLabel,
  formatSubscriptionStatusLabel,
  validateEmail,
  validatePaymentSubmission,
  validateStrongPassword,
  type CloudConnectivityState,
  type DeviceRecord,
  type EffectiveEntitlement,
  type PaymentRecord,
  type ProfileRecord,
  type SubscriptionRecord,
} from "@institutional-ea/cloud-contract";

export interface CompanionCloudState {
  configured: boolean;
  webPortalUrl: string;
  authenticated: boolean;
  user: {
    id: string;
    email: string;
    emailConfirmed: boolean;
  } | null;
  profile: ProfileRecord | null;
  subscription: SubscriptionRecord | null;
  entitlement: EffectiveEntitlement;
  connectivity: CloudConnectivityState;
  lastVerifiedAtUtc: string | null;
  deviceName: string;
  deviceFingerprintShort: string;
}

interface AccountSubscriptionScreenProps {
  onActionMessage: (msg: string, isError?: boolean) => void;
}

function formatUtc(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return `${d.toISOString().replace("T", " ").slice(0, 19)} UTC`;
}

function connectivityBadge(state: CloudConnectivityState): { label: string; cls: string } {
  switch (state) {
    case "online":
      return { label: "ONLINE", cls: "bg-iea-profitSoft border-iea-profitBorder text-iea-profit" };
    case "offline":
      return { label: "OFFLINE (72H GRACE)", cls: "bg-amber-500/15 border-amber-500/30 text-amber-300" };
    case "reconnecting":
      return { label: "RECONNECTING", cls: "bg-blue-500/15 border-blue-500/30 text-blue-300" };
    case "auth_expired":
      return { label: "AUTH EXPIRED", cls: "bg-iea-dangerSoft border-iea-dangerBorder text-iea-danger" };
    case "verification_unavailable":
      return { label: "VERIFICATION UNAVAILABLE", cls: "bg-iea-dangerSoft border-iea-dangerBorder text-iea-danger" };
    default:
      return { label: "SYNC PENDING", cls: "bg-amber-500/15 border-amber-500/30 text-amber-300" };
  }
}

export const AccountSubscriptionScreen: React.FC<AccountSubscriptionScreenProps> = ({
  onActionMessage,
}) => {
  const api = (window as any).electronAPI;

  const [cloudState, setCloudState] = useState<CompanionCloudState | null>(null);
  const [payments, setPayments] = useState<PaymentRecord[]>([]);
  const [devices, setDevices] = useState<DeviceRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  // Auth form state
  const [authMode, setAuthMode] = useState<"sign_in" | "sign_up">("sign_in");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  // Payment form state
  const [copiedAddress, setCopiedAddress] = useState(false);
  const [amountSent, setAmountSent] = useState(String(BINANCE_USDT_TRC20_CONFIG.amountUsdt));
  const [txid, setTxid] = useState("");
  const [paymentDate, setPaymentDate] = useState(() => new Date().toISOString().slice(0, 16));
  const [networkConfirmed, setNetworkConfirmed] = useState(false);

  const loadAll = useCallback(async (forceRefresh = false) => {
    if (!api?.cloudGetState) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const nextState: CompanionCloudState = forceRefresh
        ? (await api.cloudRefresh())?.state || (await api.cloudGetState())
        : await api.cloudGetState();
      setCloudState(nextState);

      if (nextState?.authenticated) {
        const [pmtRes, devRes] = await Promise.all([
          api.cloudGetPayments().catch(() => ({ ok: false, payments: [] })),
          api.cloudGetDevices().catch(() => ({ ok: false, devices: [] })),
        ]);
        setPayments(Array.isArray(pmtRes?.payments) ? pmtRes.payments : []);
        setDevices(Array.isArray(devRes?.devices) ? devRes.devices : []);
      } else {
        setPayments([]);
        setDevices([]);
      }
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    loadAll(false);
    if (!api?.onCloudStateChanged) return;
    const unsub = api.onCloudStateChanged((next: CompanionCloudState) => {
      setCloudState(next);
      if (next?.authenticated) {
        loadAll(false);
      }
    });
    return () => unsub?.();
  }, [api, loadAll]);

  const handleBrowserSignIn = async () => {
    if (!api?.cloudSignInBrowser) return;
    setBusy(true);
    try {
      const res = await api.cloudSignInBrowser();
      if (res?.ok) {
        onActionMessage("System browser opened for secure Institutional EA sign-in.", false);
      } else {
        onActionMessage(res?.error || "Unable to launch browser sign-in.", true);
      }
    } finally {
      setBusy(false);
    }
  };

  const handleDirectAuthSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validateEmail(email)) {
      onActionMessage("Please enter a valid email address.", true);
      return;
    }
    if (authMode === "sign_up") {
      if (fullName.trim().length < 2) {
        onActionMessage("Please enter your full name.", true);
        return;
      }
      const pw = validateStrongPassword(password);
      if (!pw.valid) {
        onActionMessage(pw.errors[0], true);
        return;
      }
    }

    setBusy(true);
    try {
      if (authMode === "sign_in") {
        const res = await api.cloudSignInPassword(email, password);
        if (res?.ok) {
          setCloudState(res.state);
          setPassword("");
          onActionMessage("Signed in securely (credentials encrypted with Windows DPAPI).", false);
          await loadAll(false);
        } else {
          onActionMessage(res?.error || "Sign in failed.", true);
        }
      } else {
        const res = await api.cloudSignUp(fullName, email, password);
        if (res?.ok) {
          setPassword("");
          onActionMessage(
            res.needsEmailVerification
              ? "Account created! Please verify your email address before signing in."
              : "Account created and signed in.",
            false
          );
          await loadAll(false);
        } else {
          onActionMessage(res?.error || "Registration failed.", true);
        }
      }
    } finally {
      setBusy(false);
    }
  };

  const handleSignOut = async () => {
    if (!api?.cloudSignOut) return;
    setBusy(true);
    try {
      const res = await api.cloudSignOut();
      setCloudState(res?.state || null);
      setPayments([]);
      setDevices([]);
      onActionMessage("Signed out of Institutional EA cloud account.", false);
    } finally {
      setBusy(false);
    }
  };

  const handleCopyAddress = () => {
    navigator.clipboard?.writeText(BINANCE_USDT_TRC20_CONFIG.depositAddress).then(() => {
      setCopiedAddress(true);
      setTimeout(() => setCopiedAddress(false), 1800);
    });
  };

  const handlePaymentSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const numericAmount = Number(amountSent);
    const isoDate = paymentDate ? new Date(paymentDate).toISOString() : "";
    const check = validatePaymentSubmission({
      amountSent: numericAmount,
      transactionReference: txid.trim(),
      paymentDate: isoDate,
      networkConfirmed,
    });
    if (!check.valid) {
      onActionMessage(check.errors[0], true);
      return;
    }

    setBusy(true);
    try {
      const res = await api.cloudSubmitPayment({
        amount: numericAmount,
        transactionReference: txid.trim(),
        paymentDate: isoDate,
      });
      if (res?.ok) {
        setTxid("");
        setNetworkConfirmed(false);
        onActionMessage(
          "Binance USDT (TRC20) payment submitted for administrator verification.",
          false
        );
        await loadAll(true);
      } else {
        onActionMessage(res?.error || "Payment submission failed.", true);
      }
    } finally {
      setBusy(false);
    }
  };

  const handleRevokeDevice = async (deviceId: string) => {
    setBusy(true);
    try {
      const res = await api.cloudRevokeDevice(deviceId);
      if (res?.ok) {
        setDevices(res.devices || []);
        onActionMessage("Device revoked.", false);
      } else {
        onActionMessage(res?.error || "Failed to revoke device.", true);
      }
    } finally {
      setBusy(false);
    }
  };

  if (!api?.cloudGetState) {
    return (
      <div className="rounded-[18px] border border-iea-borderDefault bg-iea-card p-6 text-xs text-iea-textSecondary">
        Cloud account and OS-encrypted credential storage are available in the Windows Companion
        Desktop Application.
      </div>
    );
  }

  const connBadge = connectivityBadge(cloudState?.connectivity || "offline");

  return (
    <div className="space-y-6">
      {/* Safety Guarantee Banner */}
      <div className="rounded-[16px] border border-iea-borderDefault bg-iea-card p-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center space-x-3 text-xs">
          <ShieldCheck className="w-4 h-4 text-iea-profit shrink-0" />
          <span className="text-iea-textSecondary">
            <strong className="text-iea-textPrimary">Trading Safety Isolation:</strong> Subscription
            status never closes open MT5 positions, stops the trading engine, or blocks local
            emergency controls.
          </span>
        </div>
        <div className="flex items-center space-x-2">
          <span className={`px-2.5 py-1 rounded-full border font-mono text-[10px] font-semibold ${connBadge.cls}`}>
            {cloudState?.connectivity === "online" ? (
              <Wifi className="w-3 h-3 inline mr-1" />
            ) : (
              <WifiOff className="w-3 h-3 inline mr-1" />
            )}
            {connBadge.label}
          </span>
          <button
            type="button"
            disabled={loading || busy}
            onClick={() => loadAll(true)}
            className="iea-pill-control px-3 py-1 text-xs inline-flex items-center space-x-1.5 text-iea-textPrimary hover:border-iea-accentBorder"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            <span>Sync Cloud</span>
          </button>
        </div>
      </div>

      {/* Supabase Not Configured Notice */}
      {cloudState && !cloudState.configured && (
        <div className="rounded-[16px] border border-amber-500/30 bg-amber-500/10 p-4 text-xs text-amber-200">
          <strong>Supabase Not Configured:</strong> Add <code className="font-mono">SUPABASE_URL</code>{" "}
          and <code className="font-mono">SUPABASE_ANON_KEY</code> to your <code className="font-mono">.env</code>{" "}
          file to enable cloud authentication and subscription sync. Local MT5 trading operations
          continue unaffected.
        </div>
      )}

      {/* Unauthenticated View */}
      {!cloudState?.authenticated ? (
        <div className="grid gap-6 lg:grid-cols-12">
          <div className="lg:col-span-6 rounded-[18px] border border-iea-borderDefault bg-iea-card p-6 space-y-5">
            <div className="flex items-center space-x-3">
              <div className="w-10 h-10 rounded-[12px] bg-iea-accentSoft border border-iea-accentBorder flex items-center justify-center">
                <User className="w-5 h-5 text-iea-accent" />
              </div>
              <div>
                <h2 className="text-base font-bold text-iea-textPrimary">
                  Institutional EA Cloud Account
                </h2>
                <p className="text-xs text-iea-textSecondary">
                  Tokens are stored strictly in Windows DPAPI encrypted storage (never in SQLite or
                  plaintext).
                </p>
              </div>
            </div>

            <button
              type="button"
              disabled={busy || !cloudState?.configured}
              onClick={handleBrowserSignIn}
              className="w-full rounded-[10px] bg-iea-accent hover:bg-blue-600 py-2.5 px-4 text-xs font-semibold text-white inline-flex items-center justify-center space-x-2 transition disabled:opacity-50"
            >
              <ExternalLink className="w-4 h-4" />
              <span>Sign In with System Browser (Recommended)</span>
            </button>

            <div className="relative flex items-center py-1">
              <div className="flex-grow border-t border-iea-borderSubtle" />
              <span className="px-3 text-[11px] font-mono text-iea-textMuted">OR DIRECT SIGN-IN</span>
              <div className="flex-grow border-t border-iea-borderSubtle" />
            </div>

            <div className="flex space-x-2">
              <button
                type="button"
                onClick={() => setAuthMode("sign_in")}
                className={`flex-1 py-1.5 rounded-lg text-xs font-semibold border ${
                  authMode === "sign_in"
                    ? "bg-iea-accentSoft border-iea-accentBorder text-iea-accent"
                    : "border-iea-borderSubtle text-iea-textSecondary"
                }`}
              >
                Sign In
              </button>
              <button
                type="button"
                onClick={() => setAuthMode("sign_up")}
                className={`flex-1 py-1.5 rounded-lg text-xs font-semibold border ${
                  authMode === "sign_up"
                    ? "bg-iea-accentSoft border-iea-accentBorder text-iea-accent"
                    : "border-iea-borderSubtle text-iea-textSecondary"
                }`}
              >
                Create Account
              </button>
            </div>

            <form onSubmit={handleDirectAuthSubmit} className="space-y-3">
              {authMode === "sign_up" && (
                <input
                  type="text"
                  required
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="Full Name"
                  className="w-full rounded-lg border border-iea-borderDefault bg-iea-inset px-3 py-2 text-xs text-iea-textPrimary"
                />
              )}
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Email Address"
                className="w-full rounded-lg border border-iea-borderDefault bg-iea-inset px-3 py-2 text-xs text-iea-textPrimary"
              />
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Password"
                className="w-full rounded-lg border border-iea-borderDefault bg-iea-inset px-3 py-2 text-xs text-iea-textPrimary"
              />
              <button
                type="submit"
                disabled={busy || !cloudState?.configured}
                className="w-full rounded-[10px] border border-iea-accentBorder bg-iea-accentSoft py-2.5 text-xs font-semibold text-iea-accent hover:bg-iea-accent hover:text-white transition disabled:opacity-50"
              >
                {busy
                  ? "Processing..."
                  : authMode === "sign_in"
                  ? "Sign In"
                  : "Create Account"}
              </button>
            </form>
          </div>

          <div className="lg:col-span-6 rounded-[18px] border border-iea-borderDefault bg-iea-card p-6 space-y-4">
            <h3 className="text-sm font-bold text-iea-textPrimary">
              {INSTITUTIONAL_EA_PRO_PLAN.name} — ${INSTITUTIONAL_EA_PRO_PLAN.price} USD / month
            </h3>
            <p className="text-xs leading-relaxed text-iea-textSecondary">
              {INSTITUTIONAL_EA_PRO_PLAN.description}
            </p>
            <div className="rounded-xl border border-iea-borderSubtle bg-iea-inset p-4 space-y-2 text-xs font-mono">
              <div className="flex justify-between">
                <span className="text-iea-textMuted">This Workstation</span>
                <span className="text-iea-textPrimary">{cloudState?.deviceName || "Windows PC"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-iea-textMuted">Hashed Device ID</span>
                <span className="text-iea-textPrimary">{cloudState?.deviceFingerprintShort}…</span>
              </div>
              <div className="flex justify-between">
                <span className="text-iea-textMuted">Credential Storage</span>
                <span className="text-iea-profit">Windows DPAPI Encrypted</span>
              </div>
            </div>
            <button
              type="button"
              onClick={() => api.cloudOpenExternalPortal("/pricing")}
              className="inline-flex items-center space-x-1.5 text-xs font-semibold text-iea-accent hover:underline"
            >
              <span>Open Public Pricing & Web Portal</span>
              <ExternalLink className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      ) : (
        /* Authenticated Account, Subscription, Binance Payment & Devices View */
        <div className="space-y-6">
          {/* Account + Subscription Overview */}
          <div className="grid gap-4 md:grid-cols-4">
            <div className="rounded-[16px] border border-iea-borderDefault bg-iea-card p-4">
              <div className="text-[11px] text-iea-textMuted">Account Holder</div>
              <div className="mt-1 text-sm font-bold text-iea-textPrimary truncate">
                {cloudState.profile?.full_name || "Subscriber"}
              </div>
              <div className="mt-0.5 text-xs text-iea-textSecondary truncate">
                {cloudState.user?.email}
              </div>
              <div className="mt-2 inline-flex items-center space-x-1 text-[10px] font-mono text-iea-profit">
                <CheckCircle2 className="w-3 h-3" />
                <span>{cloudState.user?.emailConfirmed ? "Email Verified" : "Verification Pending"}</span>
              </div>
            </div>

            <div className="rounded-[16px] border border-iea-borderDefault bg-iea-card p-4">
              <div className="text-[11px] text-iea-textMuted">Subscription Status</div>
              <div className="mt-1 text-sm font-bold text-iea-textPrimary">
                {formatSubscriptionStatusLabel(cloudState.entitlement.status)}
              </div>
              <div className="mt-1 text-[11px] text-iea-textSecondary">
                {cloudState.entitlement.reason}
              </div>
            </div>

            <div className="rounded-[16px] border border-iea-borderDefault bg-iea-card p-4">
              <div className="text-[11px] text-iea-textMuted">Plan & Expiration (UTC)</div>
              <div className="mt-1 text-sm font-bold text-iea-textPrimary">
                {INSTITUTIONAL_EA_PRO_PLAN.name} ($50/mo)
              </div>
              <div className="mt-1 font-mono text-[11px] text-iea-textSecondary">
                Exp: {formatUtc(cloudState.subscription?.expires_at)}
              </div>
            </div>

            <div className="rounded-[16px] border border-iea-borderDefault bg-iea-card p-4 flex flex-col justify-between">
              <div>
                <div className="text-[11px] text-iea-textMuted">Device Identity</div>
                <div className="mt-1 text-xs font-semibold text-iea-textPrimary truncate">
                  {cloudState.deviceName}
                </div>
                <div className="font-mono text-[10px] text-iea-textMuted">
                  Hash: {cloudState.deviceFingerprintShort}…
                </div>
              </div>
              <button
                type="button"
                disabled={busy}
                onClick={handleSignOut}
                className="mt-3 inline-flex items-center justify-center space-x-1.5 rounded-lg border border-iea-dangerBorder bg-iea-dangerSoft py-1.5 text-xs font-semibold text-iea-danger hover:bg-red-500/20"
              >
                <LogOut className="w-3.5 h-3.5" />
                <span>Sign Out</span>
              </button>
            </div>
          </div>

          {/* Binance USDT TRC20 Payment & Renewal */}
          <div className="grid gap-6 lg:grid-cols-12">
            <div className="lg:col-span-5 rounded-[18px] border border-iea-borderDefault bg-iea-card p-5 space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <Wallet className="w-4 h-4 text-amber-400" />
                  <h3 className="text-sm font-bold text-iea-textPrimary">
                    Binance USDT (TRC20) Deposit
                  </h3>
                </div>
                <span className="font-mono text-xs font-semibold text-iea-profit">50 USDT</span>
              </div>

              <div className="flex flex-col items-center rounded-xl border border-iea-borderSubtle bg-iea-inset p-3">
                <img
                  src="./assets/binance-usdt-trc20-qr.jpg"
                  alt="Binance USDT TRC20 QR Code"
                  className="w-48 rounded-lg bg-white p-1"
                />
              </div>

              <div className="rounded-lg border border-iea-borderDefault bg-iea-inset p-3">
                <div className="text-[10px] uppercase text-iea-textMuted">
                  TRON (TRC20) Deposit Address
                </div>
                <div className="mt-1 flex items-center justify-between gap-2">
                  <code className="break-all font-mono text-[11px] text-iea-textPrimary">
                    {BINANCE_USDT_TRC20_CONFIG.depositAddress}
                  </code>
                  <button
                    type="button"
                    onClick={handleCopyAddress}
                    className="shrink-0 rounded-md border border-iea-accentBorder bg-iea-accentSoft px-2.5 py-1 text-[11px] font-semibold text-iea-accent"
                  >
                    {copiedAddress ? (
                      <Check className="w-3.5 h-3.5 text-iea-profit" />
                    ) : (
                      <Copy className="w-3.5 h-3.5" />
                    )}
                  </button>
                </div>
              </div>

              <div className="rounded-lg border border-amber-500/25 bg-amber-500/10 p-3 text-[11px] text-amber-200 space-y-1">
                <div className="font-semibold flex items-center space-x-1.5">
                  <AlertTriangle className="w-3.5 h-3.5" />
                  <span>Network Warning</span>
                </div>
                <p>
                  Send only USDT on TRON (TRC20). Do not send NFTs or other networks. Admin
                  verification is required before activation.
                </p>
              </div>
            </div>

            <div className="lg:col-span-7 rounded-[18px] border border-iea-borderDefault bg-iea-card p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-bold text-iea-textPrimary">
                  Submit Payment Verification
                </h3>
                <button
                  type="button"
                  onClick={() => api.cloudOpenExternalPortal("/account/subscription")}
                  className="text-[11px] font-semibold text-iea-accent hover:underline inline-flex items-center space-x-1"
                >
                  <span>Upload Receipt on Web Portal</span>
                  <ExternalLink className="w-3 h-3" />
                </button>
              </div>

              <form onSubmit={handlePaymentSubmit} className="space-y-3">
                <div className="grid gap-3 sm:grid-cols-2">
                  <div>
                    <label className="block text-[11px] text-iea-textSecondary">
                      Amount Sent (USDT)
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      min={50}
                      required
                      value={amountSent}
                      onChange={(e) => setAmountSent(e.target.value)}
                      className="mt-1 w-full rounded-lg border border-iea-borderDefault bg-iea-inset px-3 py-2 font-mono text-xs text-iea-textPrimary"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] text-iea-textSecondary">
                      Payment Date (UTC)
                    </label>
                    <input
                      type="datetime-local"
                      required
                      value={paymentDate}
                      onChange={(e) => setPaymentDate(e.target.value)}
                      className="mt-1 w-full rounded-lg border border-iea-borderDefault bg-iea-inset px-3 py-2 font-mono text-xs text-iea-textPrimary"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-[11px] text-iea-textSecondary">
                    Transaction ID / TXID
                  </label>
                  <input
                    type="text"
                    required
                    value={txid}
                    onChange={(e) => setTxid(e.target.value)}
                    placeholder="64-character TRON TRC20 TXID"
                    className="mt-1 w-full rounded-lg border border-iea-borderDefault bg-iea-inset px-3 py-2 font-mono text-xs text-iea-textPrimary"
                  />
                </div>

                <label className="flex items-start space-x-2 text-[11px] text-iea-textSecondary">
                  <input
                    type="checkbox"
                    checked={networkConfirmed}
                    onChange={(e) => setNetworkConfirmed(e.target.checked)}
                    className="mt-0.5"
                  />
                  <span>
                    I confirm I sent USDT via TRON (TRC20) to{" "}
                    <code className="font-mono text-iea-textPrimary">
                      {BINANCE_USDT_TRC20_CONFIG.depositAddress}
                    </code>
                    .
                  </span>
                </label>

                <button
                  type="submit"
                  disabled={busy}
                  className="w-full rounded-[10px] bg-iea-accent hover:bg-blue-600 py-2.5 text-xs font-semibold text-white transition disabled:opacity-50"
                >
                  {busy ? "Submitting..." : "Submit Payment for Admin Review"}
                </button>
              </form>

              {/* Transaction History */}
              <div className="pt-3 border-t border-iea-borderSubtle">
                <h4 className="text-xs font-semibold text-iea-textPrimary mb-2">
                  Recent Payment Submissions
                </h4>
                {payments.length === 0 ? (
                  <p className="text-[11px] text-iea-textMuted">No payments submitted yet.</p>
                ) : (
                  <div className="space-y-2 max-h-44 overflow-y-auto">
                    {payments.map((p) => (
                      <div
                        key={p.id}
                        className="rounded-lg border border-iea-borderSubtle bg-iea-inset p-2.5 flex items-center justify-between text-[11px]"
                      >
                        <div className="min-w-0">
                          <div className="font-mono text-iea-textPrimary truncate">
                            {p.amount} {p.asset} · {p.transaction_reference.slice(0, 20)}…
                          </div>
                          <div className="text-iea-textMuted">
                            {formatUtc(p.submitted_at)}
                            {p.rejection_reason ? ` · Rejected: ${p.rejection_reason}` : ""}
                          </div>
                        </div>
                        <span className="ml-2 shrink-0 rounded-full border border-iea-borderDefault px-2 py-0.5 font-mono text-[10px] text-iea-textPrimary">
                          {formatPaymentStatusLabel(p.status)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Registered Devices */}
          <div className="rounded-[18px] border border-iea-borderDefault bg-iea-card p-5">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center space-x-2">
                <Laptop className="w-4 h-4 text-iea-accent" />
                <h3 className="text-sm font-bold text-iea-textPrimary">Registered Devices</h3>
              </div>
              <span className="font-mono text-[11px] text-iea-textMuted">
                <Lock className="w-3 h-3 inline mr-1" />
                Hashed fingerprints only · Max 3 active
              </span>
            </div>
            {devices.length === 0 ? (
              <p className="text-xs text-iea-textMuted">
                No registered devices returned yet. Click Sync Cloud above to register this machine.
              </p>
            ) : (
              <div className="divide-y divide-iea-borderSubtle text-xs">
                {devices.map((d) => (
                  <div key={d.id} className="py-2.5 flex items-center justify-between gap-3">
                    <div>
                      <div className="font-semibold text-iea-textPrimary">{d.device_name}</div>
                      <div className="font-mono text-[10px] text-iea-textMuted">
                        {d.operating_system} · v{d.app_version} · {d.device_fingerprint_hash.slice(0, 12)}… · Last seen{" "}
                        {formatUtc(d.last_seen_at)}
                      </div>
                    </div>
                    <div className="flex items-center space-x-2">
                      <span
                        className={`px-2 py-0.5 rounded-full font-mono text-[10px] ${
                          d.status === "active"
                            ? "bg-iea-profitSoft text-iea-profit"
                            : "bg-iea-dangerSoft text-iea-danger"
                        }`}
                      >
                        {d.status.toUpperCase()}
                      </span>
                      {d.status === "active" && (
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => handleRevokeDevice(d.id)}
                          className="inline-flex items-center space-x-1 rounded-md border border-iea-dangerBorder bg-iea-dangerSoft px-2 py-1 text-[10px] text-iea-danger"
                        >
                          <Trash2 className="w-3 h-3" />
                          <span>Revoke</span>
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
