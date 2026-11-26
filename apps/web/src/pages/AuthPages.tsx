import React, { useEffect, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Eye,
  EyeOff,
  KeyRound,
  Lock,
  Mail,
  ShieldAlert,
} from "lucide-react";
import {
  validateEmail,
  validateStrongPassword,
} from "@institutional-ea/cloud-contract";
import { Link, useRouter } from "../lib/router";
import { useAuth } from "../context/AuthContext";
import { supabaseAuth } from "../lib/supabaseClient";

function getQueryParam(search: string, key: string): string {
  try {
    return new URLSearchParams(search).get(key) || "";
  } catch {
    return "";
  }
}

function isAllowedDesktopCallback(urlStr: string): boolean {
  try {
    const u = new URL(urlStr);
    if (u.protocol === "institutionalea:") return true;
    if (
      u.protocol === "http:" &&
      (u.hostname === "127.0.0.1" || u.hostname === "localhost") &&
      u.pathname === "/auth/callback"
    ) {
      return true;
    }
    return false;
  } catch {
    return false;
  }
}

const AuthShell: React.FC<{
  title: string;
  subtitle: string;
  children: React.ReactNode;
}> = ({ title, subtitle, children }) => {
  const { configured } = useAuth();
  return (
    <div className="mx-auto flex max-w-md flex-col justify-center px-4 py-14 sm:px-6">
      <div className="rounded-2xl border border-white/10 bg-[#111216] p-7 shadow-2xl sm:p-8">
        <div className="mb-6 text-center">
          <img
            src="/logo.png"
            alt="Institutional EA"
            className="mx-auto h-11 w-11 rounded-xl border border-white/10 bg-[#0D0E11] object-contain p-1.5"
          />
          <h1 className="mt-4 text-xl font-bold text-white">{title}</h1>
          <p className="mt-1.5 text-xs leading-relaxed text-[#9CA3AF]">{subtitle}</p>
        </div>

        {!configured && (
          <div className="mb-5 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3.5 text-xs text-amber-200">
            <div className="flex items-start gap-2">
              <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
              <div>
                <div className="font-semibold">Supabase Environment Required</div>
                <p className="mt-1 text-amber-200/80">
                  Configure <code className="font-mono">VITE_SUPABASE_URL</code> and{" "}
                  <code className="font-mono">VITE_SUPABASE_ANON_KEY</code> to enable live cloud
                  authentication.
                </p>
              </div>
            </div>
          </div>
        )}

        {children}
      </div>
    </div>
  );
};

export const SignInPage: React.FC = () => {
  const { navigate, search } = useRouter();
  const { setSessionDirect, refreshAccount } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [remember, setRemember] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const nextUrl = getQueryParam(search, "next");
  const desktopCallback = getQueryParam(search, "desktop_callback");
  const desktopState = getQueryParam(search, "state");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!validateEmail(email)) {
      setError("Please enter a valid email address.");
      return;
    }
    if (!password) {
      setError("Please enter your password.");
      return;
    }

    setSubmitting(true);
    try {
      const session = await supabaseAuth.signInWithPassword({ email, password, remember });
      setSessionDirect(session, remember);

      // If initiated by Windows Companion Desktop App via validated loopback/custom protocol callback
      if (desktopCallback && isAllowedDesktopCallback(desktopCallback)) {
        const cb = new URL(desktopCallback);
        cb.searchParams.set("access_token", session.access_token);
        cb.searchParams.set("refresh_token", session.refresh_token);
        cb.searchParams.set("expires_at", String(session.expires_at));
        if (desktopState) cb.searchParams.set("state", desktopState);
        window.location.href = cb.toString();
        return;
      }

      await refreshAccount();
      navigate(nextUrl && nextUrl.startsWith("/") ? nextUrl : "/account");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Sign in failed.";
      if (msg.toLowerCase().includes("email not confirmed")) {
        setError("Your email is not verified yet. Check your inbox or request a new verification link.");
      } else {
        setError(msg);
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell
      title="Sign In to Institutional EA"
      subtitle={
        desktopCallback
          ? "Authenticate your account to connect the Windows Companion Application."
          : "Access your account, subscription status, and Binance USDT billing."
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <div>
          <label className="block text-xs font-medium text-[#D1D5DB]">Email Address</label>
          <div className="relative mt-1.5">
            <Mail className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-[#6B7280]" />
            <input
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="trader@institutionalea.com"
              className="w-full rounded-lg border border-white/10 bg-[#0D0E11] py-2.5 pl-9 pr-3 text-sm text-white placeholder-[#6B7280] focus:border-[#3B82F6] focus:outline-none"
            />
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between">
            <label className="block text-xs font-medium text-[#D1D5DB]">Password</label>
            <Link
              to="/auth/forgot-password"
              className="text-xs font-medium text-[#3B82F6] hover:text-blue-400"
            >
              Forgot password?
            </Link>
          </div>
          <div className="relative mt-1.5">
            <Lock className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-[#6B7280]" />
            <input
              type={showPassword ? "text" : "password"}
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter your password"
              className="w-full rounded-lg border border-white/10 bg-[#0D0E11] py-2.5 pl-9 pr-10 text-sm text-white placeholder-[#6B7280] focus:border-[#3B82F6] focus:outline-none"
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? "Hide password" : "Show password"}
              className="absolute right-2.5 top-2.5 text-[#6B7280] hover:text-white"
            >
              {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
        </div>

        <label className="flex items-center gap-2 text-xs text-[#9CA3AF]">
          <input
            type="checkbox"
            checked={remember}
            onChange={(e) => setRemember(e.target.checked)}
            className="h-3.5 w-3.5 rounded border-white/20 bg-[#0D0E11] text-[#3B82F6]"
          />
          Keep me signed in on this browser
        </label>

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-lg bg-[#3B82F6] py-2.5 text-sm font-semibold text-white transition hover:bg-[#2563EB] disabled:opacity-60"
        >
          {submitting ? "Signing In..." : "Sign In"}
        </button>
      </form>

      <div className="mt-6 border-t border-white/[0.07] pt-4 text-center text-xs text-[#9CA3AF]">
        Need an account?{" "}
        <Link to="/auth/sign-up" className="font-semibold text-[#3B82F6] hover:text-blue-400">
          Create Account
        </Link>
      </div>
    </AuthShell>
  );
};

export const SignUpPage: React.FC = () => {
  const { navigate, search } = useRouter();
  const { setSessionDirect } = useAuth();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [acceptedLegal, setAcceptedLegal] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const nextUrl = getQueryParam(search, "next");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (fullName.trim().length < 2) {
      setError("Please enter your full name.");
      return;
    }
    if (!validateEmail(email)) {
      setError("Please enter a valid email address.");
      return;
    }
    const pwCheck = validateStrongPassword(password);
    if (!pwCheck.valid) {
      setError(pwCheck.errors[0]);
      return;
    }
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    if (!acceptedLegal) {
      setError("You must accept the Terms of Service and Privacy Policy to register.");
      return;
    }

    setSubmitting(true);
    try {
      const res = await supabaseAuth.signUp({ email, password, fullName });
      if (res.session && !res.needsEmailVerification) {
        setSessionDirect(res.session, true);
        navigate(nextUrl && nextUrl.startsWith("/") ? nextUrl : "/account/subscription");
      } else {
        navigate(`/auth/verify-email?email=${encodeURIComponent(email.trim().toLowerCase())}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell
      title="Create Your Account"
      subtitle="Register for Institutional EA Pro ($50 USD/month) and connect your Windows Companion."
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <div>
          <label className="block text-xs font-medium text-[#D1D5DB]">Full Name</label>
          <input
            type="text"
            required
            autoComplete="name"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder="Alex Morgan"
            className="mt-1.5 w-full rounded-lg border border-white/10 bg-[#0D0E11] px-3 py-2.5 text-sm text-white placeholder-[#6B7280] focus:border-[#3B82F6] focus:outline-none"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-[#D1D5DB]">Email Address</label>
          <input
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="trader@institutionalea.com"
            className="mt-1.5 w-full rounded-lg border border-white/10 bg-[#0D0E11] px-3 py-2.5 text-sm text-white placeholder-[#6B7280] focus:border-[#3B82F6] focus:outline-none"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-[#D1D5DB]">Password</label>
          <div className="relative mt-1.5">
            <input
              type={showPassword ? "text" : "password"}
              required
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Min 10 chars, upper/lower, number & symbol"
              className="w-full rounded-lg border border-white/10 bg-[#0D0E11] py-2.5 pl-3 pr-10 text-sm text-white placeholder-[#6B7280] focus:border-[#3B82F6] focus:outline-none"
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? "Hide password" : "Show password"}
              className="absolute right-2.5 top-2.5 text-[#6B7280] hover:text-white"
            >
              {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
        </div>

        <div>
          <label className="block text-xs font-medium text-[#D1D5DB]">Confirm Password</label>
          <input
            type={showPassword ? "text" : "password"}
            required
            autoComplete="new-password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            placeholder="Re-enter your password"
            className="mt-1.5 w-full rounded-lg border border-white/10 bg-[#0D0E11] px-3 py-2.5 text-sm text-white placeholder-[#6B7280] focus:border-[#3B82F6] focus:outline-none"
          />
        </div>

        <label className="flex items-start gap-2.5 text-xs leading-relaxed text-[#9CA3AF]">
          <input
            type="checkbox"
            checked={acceptedLegal}
            onChange={(e) => setAcceptedLegal(e.target.checked)}
            className="mt-0.5 h-3.5 w-3.5 rounded border-white/20 bg-[#0D0E11] text-[#3B82F6]"
          />
          <span>
            I accept the{" "}
            <Link to="/legal/terms" className="text-[#3B82F6] hover:underline">
              Terms of Service
            </Link>
            ,{" "}
            <Link to="/legal/privacy" className="text-[#3B82F6] hover:underline">
              Privacy Policy
            </Link>
            , and{" "}
            <Link to="/legal/risk-disclosure" className="text-[#3B82F6] hover:underline">
              Risk Disclosure
            </Link>
            .
          </span>
        </label>

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-lg bg-[#3B82F6] py-2.5 text-sm font-semibold text-white transition hover:bg-[#2563EB] disabled:opacity-60"
        >
          {submitting ? "Creating Account..." : "Create Account"}
        </button>
      </form>

      <div className="mt-6 border-t border-white/[0.07] pt-4 text-center text-xs text-[#9CA3AF]">
        Already have an account?{" "}
        <Link to="/auth/sign-in" className="font-semibold text-[#3B82F6] hover:text-blue-400">
          Sign In
        </Link>
      </div>
    </AuthShell>
  );
};

export const ForgotPasswordPage: React.FC = () => {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!validateEmail(email)) {
      setError("Please enter a valid email address.");
      return;
    }
    setSubmitting(true);
    try {
      await supabaseAuth.recoverPassword(email);
      setSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send password reset email.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell
      title="Reset Password"
      subtitle="Enter your account email and we will send a password recovery link."
    >
      {sent ? (
        <div className="space-y-4 text-center">
          <CheckCircle2 className="mx-auto h-10 w-10 text-emerald-400" />
          <p className="text-sm text-[#E5E7EB]">
            If an account exists for <span className="font-semibold text-white">{email}</span>, a
            password recovery link has been sent.
          </p>
          <Link
            to="/auth/sign-in"
            className="inline-block rounded-lg bg-[#3B82F6] px-5 py-2.5 text-xs font-semibold text-white"
          >
            Return to Sign In
          </Link>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}
          <div>
            <label className="block text-xs font-medium text-[#D1D5DB]">Email Address</label>
            <div className="relative mt-1.5">
              <KeyRound className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-[#6B7280]" />
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="trader@institutionalea.com"
                className="w-full rounded-lg border border-white/10 bg-[#0D0E11] py-2.5 pl-9 pr-3 text-sm text-white placeholder-[#6B7280] focus:border-[#3B82F6] focus:outline-none"
              />
            </div>
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-lg bg-[#3B82F6] py-2.5 text-sm font-semibold text-white transition hover:bg-[#2563EB] disabled:opacity-60"
          >
            {submitting ? "Sending..." : "Send Recovery Link"}
          </button>
          <div className="text-center text-xs">
            <Link to="/auth/sign-in" className="text-[#9CA3AF] hover:text-white">
              Back to Sign In
            </Link>
          </div>
        </form>
      )}
    </AuthShell>
  );
};

export const VerifyEmailPage: React.FC = () => {
  const { search } = useRouter();
  const initialEmail = getQueryParam(search, "email");
  const [email, setEmail] = useState(initialEmail);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  const handleResend = async () => {
    setError(null);
    setStatusMsg(null);
    if (!validateEmail(email)) {
      setError("Enter a valid email address to resend verification.");
      return;
    }
    setSending(true);
    try {
      await supabaseAuth.resendVerificationEmail(email);
      setStatusMsg("Verification email resent. Check your inbox and spam folder.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to resend verification email.");
    } finally {
      setSending(false);
    }
  };

  return (
    <AuthShell
      title="Verify Your Email"
      subtitle="We sent a confirmation link to activate your Institutional EA account."
    >
      <div className="space-y-4 text-center">
        <Mail className="mx-auto h-10 w-10 text-[#3B82F6]" />
        <p className="text-xs leading-relaxed text-[#D1D5DB]">
          Open the verification email and click the confirmation link before signing in.
        </p>

        {statusMsg && (
          <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-300">
            {statusMsg}
          </div>
        )}
        {error && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
            {error}
          </div>
        )}

        <div className="space-y-2 text-left">
          <label className="block text-xs font-medium text-[#9CA3AF]">Email Address</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="trader@institutionalea.com"
            className="w-full rounded-lg border border-white/10 bg-[#0D0E11] px-3 py-2 text-sm text-white"
          />
          <button
            type="button"
            disabled={sending}
            onClick={handleResend}
            className="w-full rounded-lg border border-white/15 bg-[#16181D] py-2 text-xs font-semibold text-white hover:bg-white/10 disabled:opacity-60"
          >
            {sending ? "Resending..." : "Resend Verification Email"}
          </button>
        </div>

        <Link
          to="/auth/sign-in"
          className="inline-block pt-2 text-xs font-semibold text-[#3B82F6] hover:underline"
        >
          Proceed to Sign In
        </Link>
      </div>
    </AuthShell>
  );
};

export const AuthCallbackPage: React.FC = () => {
  const { navigate } = useRouter();
  const { setSessionDirect, refreshAccount } = useAuth();
  const [message, setMessage] = useState("Completing authentication...");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function handleCallback() {
      try {
        const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, ""));
        const accessToken = hashParams.get("access_token");
        const refreshToken = hashParams.get("refresh_token");
        const expiresIn = Number(hashParams.get("expires_in") || 3600);

        if (accessToken && refreshToken) {
          const user = await supabaseAuth.getUser(accessToken);
          setSessionDirect(
            {
              access_token: accessToken,
              refresh_token: refreshToken,
              expires_at: Math.floor(Date.now() / 1000) + expiresIn,
              token_type: "bearer",
              user,
            },
            true
          );
          await refreshAccount();
          setMessage("Email verified and signed in. Redirecting to your account...");
          setTimeout(() => navigate("/account/subscription"), 1000);
        } else {
          setMessage("Verification complete. You may now sign in with your email and password.");
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Authentication callback failed.");
      }
    }
    handleCallback();
  }, [navigate, refreshAccount, setSessionDirect]);

  return (
    <AuthShell title="Authentication Callback" subtitle="Verifying your credentials securely.">
      <div className="space-y-4 text-center text-xs">
        {error ? (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-red-300">
            {error}
          </div>
        ) : (
          <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-emerald-300">
            {message}
          </div>
        )}
        <Link to="/auth/sign-in" className="inline-block font-semibold text-[#3B82F6] hover:underline">
          Go to Sign In
        </Link>
      </div>
    </AuthShell>
  );
};
