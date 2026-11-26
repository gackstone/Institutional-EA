import React, { useState } from "react";
import {
  Activity,
  AlertCircle,
  AlertOctagon,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Cpu,
  ExternalLink,
  Eye,
  EyeOff,
  KeyRound,
  Layers,
  Lock,
  Mail,
  Pause,
  Shield,
  ShieldCheck,
  Square,
  Wallet,
} from "lucide-react";
import {
  BINANCE_USDT_TRC20_CONFIG,
  INSTITUTIONAL_EA_PRO_PLAN,
  PRO_PLAN_BENEFITS,
  validateEmail,
  validateStrongPassword,
} from "@institutional-ea/cloud-contract";
import type { CompanionCloudState } from "./screens/AccountSubscriptionScreen";

export type DesktopPublicView = "landing" | "pricing" | "sign-in" | "sign-up" | "forgot-password";

interface DesktopPublicEntryProps {
  cloudState: CompanionCloudState | null;
  initialView?: DesktopPublicView;
  notice?: { message: string; isError?: boolean } | null;
  onDismissNotice?: () => void;
  onAuthenticated: (nextState: CompanionCloudState) => void;
  // Local safety visibility: never lock operator out of emergency controls when signed out
  openPositionsCount?: number;
  engineRunning?: boolean;
  onEmergencyPause?: () => Promise<void>;
  onEmergencyStop?: () => Promise<void>;
  onEmergencyCloseAll?: () => Promise<void>;
}

const CAPABILITIES = [
  {
    icon: Layers,
    title: "Multi-Timeframe SMC Engine",
    desc: "Cascading W1 → D1 → H4 → H1 → M15 → M5/M1 market structure, liquidity sweeps, FVG & Order Block analysis.",
  },
  {
    icon: Shield,
    title: "Quantitative Risk Guardrails",
    desc: "Exact tick-value sizing ($5 floor & Cent support), DEMO safety lock, and 3-layer tighten-only Stop Loss.",
  },
  {
    icon: Cpu,
    title: "Local MT5 Execution Plane",
    desc: "MetaTrader 5 ⇄ PythonBridgeEA ⇄ Python Engine ⇄ Local Control Service (127.0.0.1:8765) + SQLite WAL.",
  },
  {
    icon: BarChart3,
    title: "Real-Time Workstation",
    desc: "Live SMC charts, trade screenshots, candle-by-candle trade replay, equity curves, and Telegram commands.",
  },
];

export const DesktopPublicEntry: React.FC<DesktopPublicEntryProps> = ({
  cloudState,
  initialView = "landing",
  notice,
  onDismissNotice,
  onAuthenticated,
  openPositionsCount = 0,
  engineRunning = false,
  onEmergencyPause,
  onEmergencyStop,
  onEmergencyCloseAll,
}) => {
  const api = (window as any).electronAPI;
  const [view, setView] = useState<DesktopPublicView>(initialView);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);

  // Sign In / Sign Up / Forgot Password fields
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [needsVerifyEmail, setNeedsVerifyEmail] = useState(false);
  const [confirmCloseAll, setConfirmCloseAll] = useState(false);

  const switchView = (next: DesktopPublicView) => {
    setFormError(null);
    setFormSuccess(null);
    setNeedsVerifyEmail(false);
    setView(next);
  };

  const handleBrowserSignIn = async () => {
    if (!api?.cloudSignInBrowser) return;
    setFormError(null);
    setBusy(true);
    try {
      const res = await api.cloudSignInBrowser();
      if (res?.ok) {
        setFormSuccess("System browser opened. Complete sign-in there to return automatically.");
      } else {
        setFormError(res?.error || "Unable to open browser sign-in.");
      }
    } finally {
      setBusy(false);
    }
  };

  const handleSignInSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setFormSuccess(null);
    setNeedsVerifyEmail(false);

    if (!validateEmail(email)) {
      setFormError("Please enter a valid email address.");
      return;
    }
    if (!password) {
      setFormError("Please enter your password.");
      return;
    }

    setBusy(true);
    try {
      const res = await api.cloudSignInPassword(email, password);
      if (res?.ok && res?.state?.authenticated) {
        setPassword("");
        onAuthenticated(res.state);
      } else {
        const msg = String(res?.error || "Invalid email or password.");
        if (msg.toLowerCase().includes("email not confirmed")) {
          setNeedsVerifyEmail(true);
          setFormError("Your email address is not verified yet. Verify your inbox or resend the link below.");
        } else {
          setFormError(msg);
        }
      }
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Sign in failed.");
    } finally {
      setBusy(false);
    }
  };

  const handleSignUpSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setFormSuccess(null);

    if (fullName.trim().length < 2) {
      setFormError("Please enter your full name.");
      return;
    }
    if (!validateEmail(email)) {
      setFormError("Please enter a valid email address.");
      return;
    }
    const pwCheck = validateStrongPassword(password);
    if (!pwCheck.valid) {
      setFormError(pwCheck.errors[0]);
      return;
    }
    if (password !== confirmPassword) {
      setFormError("Passwords do not match.");
      return;
    }
    if (!acceptedTerms) {
      setFormError("You must accept the Terms of Service and Privacy Policy to create an account.");
      return;
    }

    setBusy(true);
    try {
      const res = await api.cloudSignUp(fullName, email, password);
      if (res?.ok) {
        setPassword("");
        setConfirmPassword("");
        if (res.state?.authenticated && !res.needsEmailVerification) {
          onAuthenticated(res.state);
        } else {
          setNeedsVerifyEmail(true);
          setFormSuccess(
            "Account created! Check your email to verify your address, then sign in."
          );
        }
      } else {
        setFormError(res?.error || "Registration failed.");
      }
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Registration failed.");
    } finally {
      setBusy(false);
    }
  };

  const handleRecoverSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setFormSuccess(null);
    if (!validateEmail(email)) {
      setFormError("Enter a valid email address.");
      return;
    }
    setBusy(true);
    try {
      const res = await api.cloudRecoverPassword(email);
      if (res?.ok) {
        setFormSuccess("Password recovery email sent if an account exists for that address.");
      } else {
        setFormError(res?.error || "Unable to send password recovery email.");
      }
    } finally {
      setBusy(false);
    }
  };

  const handleResendVerification = async () => {
    if (!validateEmail(email) || !api?.cloudResendVerification) return;
    setBusy(true);
    setFormError(null);
    try {
      const res = await api.cloudResendVerification(email);
      if (res?.ok) {
        setFormSuccess("Verification email resent. Check your inbox and spam folder.");
      } else {
        setFormError(res?.error || "Could not resend verification email.");
      }
    } finally {
      setBusy(false);
    }
  };

  const showEmergencyStrip = openPositionsCount > 0 || engineRunning;

  return (
    <div className="flex flex-col h-full min-h-0 bg-[#0A0A0C] text-[#F3F4F6] overflow-y-auto">
      {/* Top Navigation Header */}
      <header className="sticky top-0 z-20 border-b border-white/[0.07] bg-[#0A0A0C]/95 backdrop-blur-md px-6 py-3.5 flex flex-wrap items-center justify-between gap-4">
        <button
          type="button"
          onClick={() => switchView("landing")}
          className="flex items-center space-x-3 text-left"
        >
          <img
            src="./institutional-ea-logo.png"
            alt="Institutional EA"
            className="w-8 h-8 rounded-lg border border-white/10 bg-[#111216] object-contain p-1"
          />
          <div>
            <div className="text-xs font-bold tracking-wider text-white">INSTITUTIONAL EA</div>
            <div className="text-[10px] font-mono text-[#6B7280]">Windows Companion Workstation</div>
          </div>
        </button>

        <nav className="flex items-center space-x-5 text-xs font-medium">
          <button
            type="button"
            onClick={() => switchView("landing")}
            className={view === "landing" ? "text-white font-semibold" : "text-[#9CA3AF] hover:text-white"}
          >
            Platform
          </button>
          <button
            type="button"
            onClick={() => switchView("pricing")}
            className={view === "pricing" ? "text-white font-semibold" : "text-[#9CA3AF] hover:text-white"}
          >
            Pricing ($50/mo)
          </button>
          <button
            type="button"
            onClick={() => api?.cloudOpenExternalPortal?.("/docs")}
            className="text-[#9CA3AF] hover:text-white inline-flex items-center space-x-1"
          >
            <span>Docs</span>
            <ExternalLink className="w-3 h-3" />
          </button>
        </nav>

        <div className="flex items-center space-x-2.5">
          <button
            type="button"
            data-testid="desktop-nav-signin"
            onClick={() => switchView("sign-in")}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition ${
              view === "sign-in"
                ? "bg-white/10 text-white border border-white/15"
                : "text-[#D1D5DB] hover:text-white"
            }`}
          >
            Sign In
          </button>
          <button
            type="button"
            data-testid="desktop-nav-signup"
            onClick={() => switchView("sign-up")}
            className="px-4 py-1.5 rounded-lg bg-[#3B82F6] hover:bg-[#2563EB] text-xs font-semibold text-white transition"
          >
            Get Started
          </button>
        </div>
      </header>

      {/* Local Emergency Controls Strip (Preserves trading safety even when signed out) */}
      {showEmergencyStrip && (
        <div className="mx-6 mt-4 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-2.5 flex flex-wrap items-center justify-between gap-3 text-xs">
          <div className="flex items-center space-x-2 text-amber-200">
            <AlertOctagon className="w-4 h-4 text-amber-400 shrink-0" />
            <span>
              <strong>Local Safety Access Active:</strong>{" "}
              {engineRunning ? "Local trading engine is running" : "Engine idle"}
              {openPositionsCount > 0 ? ` · ${openPositionsCount} open MT5 position(s)` : ""}. Signing out never closes positions or stops the engine.
            </span>
          </div>
          <div className="flex items-center space-x-2">
            {engineRunning && onEmergencyPause && (
              <button
                type="button"
                onClick={onEmergencyPause}
                className="px-2.5 py-1 rounded-md border border-amber-400/40 bg-amber-500/20 text-amber-200 font-semibold inline-flex items-center space-x-1"
              >
                <Pause className="w-3 h-3" />
                <span>Pause</span>
              </button>
            )}
            {engineRunning && onEmergencyStop && (
              <button
                type="button"
                onClick={onEmergencyStop}
                className="px-2.5 py-1 rounded-md border border-red-400/40 bg-red-500/20 text-red-200 font-semibold inline-flex items-center space-x-1"
              >
                <Square className="w-3 h-3" />
                <span>Stop</span>
              </button>
            )}
            {openPositionsCount > 0 && onEmergencyCloseAll && (
              confirmCloseAll ? (
                <button
                  type="button"
                  onClick={async () => {
                    setConfirmCloseAll(false);
                    await onEmergencyCloseAll();
                  }}
                  className="px-2.5 py-1 rounded-md bg-red-600 text-white font-semibold"
                >
                  Confirm Close All
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => setConfirmCloseAll(true)}
                  className="px-2.5 py-1 rounded-md border border-red-400/40 bg-red-500/15 text-red-300 font-semibold"
                >
                  Emergency Close All
                </button>
              )
            )}
          </div>
        </div>
      )}

      {/* Logout / Status Notice Banner */}
      {notice && (
        <div
          role="status"
          className={`mx-6 mt-4 rounded-xl border px-4 py-2.5 text-xs flex items-center justify-between ${
            notice.isError
              ? "border-red-500/30 bg-red-500/10 text-red-200"
              : "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
          }`}
        >
          <span>{notice.message}</span>
          {onDismissNotice && (
            <button
              type="button"
              onClick={onDismissNotice}
              className="ml-3 text-white/70 hover:text-white font-semibold"
            >
              Dismiss
            </button>
          )}
        </div>
      )}

      {/* MAIN VIEW AREA */}
      <div className="flex-1 px-6 py-10 max-w-6xl w-full mx-auto">
        {view === "landing" && (
          <div className="space-y-10">
            {/* Hero */}
            <div className="grid gap-8 lg:grid-cols-12 items-center">
              <div className="lg:col-span-7 space-y-5">
                <div className="inline-flex items-center space-x-2 rounded-full border border-blue-500/30 bg-blue-500/10 px-3 py-1 text-[11px] font-semibold text-blue-300">
                  <Activity className="w-3.5 h-3.5" />
                  <span>MetaTrader 5 · Local Execution · Institutional Architecture</span>
                </div>
                <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-white leading-tight">
                  Intelligent Algorithmic Trading.{" "}
                  <span className="text-[#3B82F6]">Institutional-Level Execution.</span>
                </h1>
                <p className="text-sm leading-relaxed text-[#9CA3AF] max-w-xl">
                  An advanced MT5 algorithmic trading ecosystem combining quantitative intelligence,
                  multi-timeframe market analysis, precision risk management, and automated execution
                  in one integrated Windows Companion platform.
                </p>
                <div className="flex flex-wrap items-center gap-3 pt-1">
                  <button
                    type="button"
                    data-testid="landing-get-started"
                    onClick={() => switchView("sign-up")}
                    className="inline-flex items-center space-x-2 rounded-lg bg-[#3B82F6] hover:bg-[#2563EB] px-5 py-2.5 text-xs font-semibold text-white transition"
                  >
                    <span>Get Started</span>
                    <ArrowRight className="w-4 h-4" />
                  </button>
                  <button
                    type="button"
                    data-testid="landing-sign-in"
                    onClick={() => switchView("sign-in")}
                    className="inline-flex items-center space-x-2 rounded-lg border border-white/15 bg-[#111216] hover:bg-[#16181D] px-5 py-2.5 text-xs font-semibold text-white transition"
                  >
                    <span>Sign In</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => switchView("pricing")}
                    className="px-3 py-2 text-xs font-medium text-[#9CA3AF] hover:text-white"
                  >
                    View Pricing ($50/mo)
                  </button>
                </div>
              </div>

              <div className="lg:col-span-5 rounded-2xl border border-white/10 bg-[#111216] p-5 space-y-4">
                <div className="flex items-center justify-between border-b border-white/[0.07] pb-3">
                  <div className="text-xs font-bold text-white">Verified Execution Pipeline</div>
                  <span className="font-mono text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                    LOCALHOST ONLY
                  </span>
                </div>
                <div className="space-y-2 font-mono text-[11px]">
                  <div className="rounded-lg bg-[#0D0E11] border border-white/[0.06] px-3 py-2 flex justify-between">
                    <span className="text-[#9CA3AF]">Execution</span>
                    <span className="text-white">MT5 → PythonBridgeEA → Engine</span>
                  </div>
                  <div className="rounded-lg bg-[#0D0E11] border border-white/[0.06] px-3 py-2 flex justify-between">
                    <span className="text-[#9CA3AF]">Local Service</span>
                    <span className="text-blue-400">127.0.0.1:8765 · SQLite WAL</span>
                  </div>
                  <div className="rounded-lg bg-[#0D0E11] border border-white/[0.06] px-3 py-2 flex justify-between">
                    <span className="text-[#9CA3AF]">Cloud Auth</span>
                    <span className="text-emerald-400">Supabase · Windows DPAPI</span>
                  </div>
                </div>
                <div className="rounded-lg border border-blue-500/20 bg-blue-500/[0.06] p-3 flex items-start space-x-2 text-[11px] text-[#D1D5DB]">
                  <ShieldCheck className="w-4 h-4 text-[#3B82F6] shrink-0 mt-0.5" />
                  <span>
                    Sign in to unlock your Companion dashboard, manage your Institutional EA Pro
                    subscription, and sync registered devices.
                  </span>
                </div>
              </div>
            </div>

            {/* Platform Capabilities */}
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {CAPABILITIES.map((c) => {
                const Icon = c.icon;
                return (
                  <div
                    key={c.title}
                    className="rounded-xl border border-white/[0.08] bg-[#111216] p-4 space-y-2"
                  >
                    <Icon className="w-4 h-4 text-[#3B82F6]" />
                    <div className="text-xs font-bold text-white">{c.title}</div>
                    <p className="text-[11px] leading-relaxed text-[#9CA3AF]">{c.desc}</p>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {view === "pricing" && (
          <div className="max-w-3xl mx-auto space-y-6">
            <div className="text-center space-y-2">
              <div className="font-mono text-[11px] uppercase tracking-widest text-[#3B82F6]">
                Institutional EA Pro
              </div>
              <h2 className="text-2xl font-bold text-white">$50 USD / month</h2>
              <p className="text-xs text-[#9CA3AF]">
                Payable via {BINANCE_USDT_TRC20_CONFIG.provider} ({BINANCE_USDT_TRC20_CONFIG.amountUsdt}{" "}
                {BINANCE_USDT_TRC20_CONFIG.asset} · {BINANCE_USDT_TRC20_CONFIG.network}) with
                administrator verification.
              </p>
            </div>

            <div className="rounded-2xl border border-blue-500/30 bg-[#111216] p-6 space-y-5">
              <div className="flex items-center justify-between border-b border-white/[0.07] pb-4">
                <div>
                  <div className="text-base font-bold text-white">{INSTITUTIONAL_EA_PRO_PLAN.name}</div>
                  <div className="text-xs text-[#9CA3AF]">Monthly UTC Subscription</div>
                </div>
                <div className="text-right font-mono">
                  <div className="text-2xl font-extrabold text-white">$50</div>
                  <div className="text-[11px] text-emerald-400">50 USDT (TRC20)</div>
                </div>
              </div>

              <ul className="grid gap-2.5 sm:grid-cols-2 text-xs text-[#E5E7EB]">
                {PRO_PLAN_BENEFITS.map((b) => (
                  <li key={b} className="flex items-start space-x-2">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
                    <span>{b}</span>
                  </li>
                ))}
              </ul>

              <div className="pt-4 border-t border-white/[0.07] flex flex-wrap items-center justify-between gap-3">
                <button
                  type="button"
                  onClick={() => switchView("sign-up")}
                  className="rounded-lg bg-[#3B82F6] hover:bg-[#2563EB] px-5 py-2.5 text-xs font-semibold text-white inline-flex items-center space-x-2"
                >
                  <Wallet className="w-4 h-4" />
                  <span>Create Account & Subscribe</span>
                </button>
                <button
                  type="button"
                  onClick={() => switchView("sign-in")}
                  className="text-xs font-semibold text-[#3B82F6] hover:underline"
                >
                  Already have an account? Sign In
                </button>
              </div>
            </div>
          </div>
        )}

        {(view === "sign-in" || view === "sign-up" || view === "forgot-password") && (
          <div className="max-w-md mx-auto rounded-2xl border border-white/10 bg-[#111216] p-7 space-y-5 shadow-2xl">
            <div className="text-center space-y-1.5">
              <img
                src="./institutional-ea-logo.png"
                alt="Institutional EA"
                className="mx-auto w-10 h-10 rounded-xl border border-white/10 bg-[#0D0E11] object-contain p-1.5"
              />
              <h2 className="text-lg font-bold text-white">
                {view === "sign-in"
                  ? "Sign In to Institutional EA"
                  : view === "sign-up"
                  ? "Create Your Account"
                  : "Reset Your Password"}
              </h2>
              <p className="text-xs text-[#9CA3AF]">
                {view === "sign-in"
                  ? "Credentials are encrypted locally via Windows DPAPI."
                  : view === "sign-up"
                  ? "Register for Institutional EA Pro ($50 USD/month)."
                  : "We will email you a password recovery link."}
              </p>
            </div>

            {cloudState && !cloudState.configured && (
              <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-200">
                Cloud sign-in is not configured in this build. Install the latest Institutional EA release or add{" "}
                <code className="font-mono">supabaseUrl</code> and <code className="font-mono">supabaseAnonKey</code> to{" "}
                <code className="font-mono">%APPDATA%\Institutional EA\config.json</code>.
              </div>
            )}

            {formError &&
              !(cloudState && !cloudState.configured && /not configured/i.test(formError)) && (
                <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300 flex items-start space-x-2">
                  <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                  <span>{formError}</span>
                </div>
              )}

            {formSuccess && (
              <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-300 flex items-start space-x-2">
                <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" />
                <span>{formSuccess}</span>
              </div>
            )}

            {view === "sign-in" && (
              <form onSubmit={handleSignInSubmit} className="space-y-3.5">
                <div>
                  <label className="block text-xs font-medium text-[#D1D5DB]">Email Address</label>
                  <div className="relative mt-1">
                    <Mail className="w-4 h-4 text-[#6B7280] absolute left-3 top-2.5 pointer-events-none" />
                    <input
                      type="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="trader@institutionalea.com"
                      className="w-full rounded-lg border border-white/10 bg-[#0D0E11] py-2 pl-9 pr-3 text-xs text-white focus:border-[#3B82F6] focus:outline-none"
                    />
                  </div>
                </div>

                <div>
                  <div className="flex justify-between items-center">
                    <label className="block text-xs font-medium text-[#D1D5DB]">Password</label>
                    <button
                      type="button"
                      onClick={() => switchView("forgot-password")}
                      className="text-[11px] text-[#3B82F6] hover:underline"
                    >
                      Forgot password?
                    </button>
                  </div>
                  <div className="relative mt-1">
                    <Lock className="w-4 h-4 text-[#6B7280] absolute left-3 top-2.5 pointer-events-none" />
                    <input
                      type={showPassword ? "text" : "password"}
                      required
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="Enter your password"
                      className="w-full rounded-lg border border-white/10 bg-[#0D0E11] py-2 pl-9 pr-9 text-xs text-white focus:border-[#3B82F6] focus:outline-none"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((v) => !v)}
                      aria-label={showPassword ? "Hide password" : "Show password"}
                      className="absolute right-2.5 top-2.5 text-[#6B7280] hover:text-white"
                    >
                      {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={busy}
                  className="w-full rounded-lg bg-[#3B82F6] hover:bg-[#2563EB] py-2.5 text-xs font-semibold text-white transition disabled:opacity-50"
                >
                  {busy ? "Signing In..." : "Sign In"}
                </button>

                {needsVerifyEmail && (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={handleResendVerification}
                    className="w-full rounded-lg border border-white/15 bg-[#16181D] py-2 text-xs font-semibold text-white hover:bg-white/10"
                  >
                    Resend Verification Email
                  </button>
                )}

                <div className="relative flex items-center py-1">
                  <div className="flex-grow border-t border-white/[0.07]" />
                  <span className="px-3 text-[10px] font-mono text-[#6B7280]">OR</span>
                  <div className="flex-grow border-t border-white/[0.07]" />
                </div>

                <button
                  type="button"
                  disabled={busy}
                  onClick={handleBrowserSignIn}
                  className="w-full rounded-lg border border-white/15 bg-[#0D0E11] hover:bg-[#16181D] py-2 text-xs font-semibold text-[#D1D5DB] inline-flex items-center justify-center space-x-1.5"
                >
                  <ExternalLink className="w-3.5 h-3.5 text-[#3B82F6]" />
                  <span>Sign In via System Browser</span>
                </button>

                <div className="text-center text-xs text-[#9CA3AF] pt-2">
                  Need an account?{" "}
                  <button
                    type="button"
                    onClick={() => switchView("sign-up")}
                    className="font-semibold text-[#3B82F6] hover:underline"
                  >
                    Sign Up
                  </button>
                </div>
              </form>
            )}

            {view === "sign-up" && (
              <form onSubmit={handleSignUpSubmit} className="space-y-3.5">
                <div>
                  <label className="block text-xs font-medium text-[#D1D5DB]">Full Name</label>
                  <input
                    type="text"
                    required
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    placeholder="Alex Morgan"
                    className="mt-1 w-full rounded-lg border border-white/10 bg-[#0D0E11] px-3 py-2 text-xs text-white focus:border-[#3B82F6] focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-[#D1D5DB]">Email Address</label>
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="trader@institutionalea.com"
                    className="mt-1 w-full rounded-lg border border-white/10 bg-[#0D0E11] px-3 py-2 text-xs text-white focus:border-[#3B82F6] focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-[#D1D5DB]">Password</label>
                  <div className="relative mt-1">
                    <input
                      type={showPassword ? "text" : "password"}
                      required
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="Min 10 chars, upper/lower, number & symbol"
                      className="w-full rounded-lg border border-white/10 bg-[#0D0E11] py-2 pl-3 pr-9 text-xs text-white focus:border-[#3B82F6] focus:outline-none"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((v) => !v)}
                      className="absolute right-2.5 top-2.5 text-[#6B7280] hover:text-white"
                    >
                      {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-medium text-[#D1D5DB]">Confirm Password</label>
                  <input
                    type={showPassword ? "text" : "password"}
                    required
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="Re-enter your password"
                    className="mt-1 w-full rounded-lg border border-white/10 bg-[#0D0E11] px-3 py-2 text-xs text-white focus:border-[#3B82F6] focus:outline-none"
                  />
                </div>

                <label className="flex items-start space-x-2 text-[11px] text-[#9CA3AF]">
                  <input
                    type="checkbox"
                    checked={acceptedTerms}
                    onChange={(e) => setAcceptedTerms(e.target.checked)}
                    className="mt-0.5"
                  />
                  <span>
                    I accept the Terms of Service, Privacy Policy, and Algorithmic Trading Risk
                    Disclosure.
                  </span>
                </label>

                <button
                  type="submit"
                  disabled={busy}
                  className="w-full rounded-lg bg-[#3B82F6] hover:bg-[#2563EB] py-2.5 text-xs font-semibold text-white transition disabled:opacity-50"
                >
                  {busy ? "Creating Account..." : "Create Account"}
                </button>

                {needsVerifyEmail && (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={handleResendVerification}
                    className="w-full rounded-lg border border-white/15 bg-[#16181D] py-2 text-xs font-semibold text-white"
                  >
                    Resend Verification Email
                  </button>
                )}

                <div className="text-center text-xs text-[#9CA3AF] pt-1">
                  Already have an account?{" "}
                  <button
                    type="button"
                    onClick={() => switchView("sign-in")}
                    className="font-semibold text-[#3B82F6] hover:underline"
                  >
                    Sign In
                  </button>
                </div>
              </form>
            )}

            {view === "forgot-password" && (
              <form onSubmit={handleRecoverSubmit} className="space-y-3.5">
                <div>
                  <label className="block text-xs font-medium text-[#D1D5DB]">Email Address</label>
                  <div className="relative mt-1">
                    <KeyRound className="w-4 h-4 text-[#6B7280] absolute left-3 top-2.5 pointer-events-none" />
                    <input
                      type="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="trader@institutionalea.com"
                      className="w-full rounded-lg border border-white/10 bg-[#0D0E11] py-2 pl-9 pr-3 text-xs text-white focus:border-[#3B82F6] focus:outline-none"
                    />
                  </div>
                </div>
                <button
                  type="submit"
                  disabled={busy}
                  className="w-full rounded-lg bg-[#3B82F6] hover:bg-[#2563EB] py-2.5 text-xs font-semibold text-white transition disabled:opacity-50"
                >
                  {busy ? "Sending..." : "Send Recovery Link"}
                </button>
                <div className="text-center text-xs">
                  <button
                    type="button"
                    onClick={() => switchView("sign-in")}
                    className="text-[#9CA3AF] hover:text-white"
                  >
                    Back to Sign In
                  </button>
                </div>
              </form>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
