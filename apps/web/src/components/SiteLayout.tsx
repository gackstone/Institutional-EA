import React, { useState } from "react";
import { Menu, ShieldCheck, User, X } from "lucide-react";
import { Link, useRouter } from "../lib/router";
import { useAuth } from "../context/AuthContext";

export const SiteHeader: React.FC = () => {
  const { pathname, navigate } = useRouter();
  const { session, profile, isAdmin, signOut } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);

  const handleSignOut = async () => {
    if (signingOut) return;
    setSigningOut(true);
    try {
      await signOut();
      setMobileOpen(false);
      navigate("/");
    } finally {
      setSigningOut(false);
    }
  };

  const navItems = [
    { label: "Home", to: "/" },
    { label: "Platform", to: "/#platform" },
    { label: "Features", to: "/#features" },
    { label: "Architecture", to: "/#architecture" },
    { label: "Pricing", to: "/pricing" },
    { label: "Documentation", to: "/docs" },
  ];

  return (
    <header className="sticky top-0 z-40 border-b border-white/[0.07] bg-[#0A0A0C]/90 backdrop-blur-md">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3.5 sm:px-6 lg:px-8">
        <Link to="/" className="flex items-center gap-3">
          <img
            src="/logo.png"
            alt="Institutional EA Logo"
            className="h-9 w-9 rounded-lg border border-white/10 bg-[#111216] object-contain p-1"
          />
          <div className="leading-tight">
            <div className="text-sm font-bold tracking-wide text-[#F3F4F6]">
              INSTITUTIONAL EA
            </div>
            <div className="font-mono text-[10px] uppercase tracking-wider text-[#6B7280]">
              MT5 Algorithmic Ecosystem
            </div>
          </div>
        </Link>

        {/* Desktop Nav */}
        <nav className="hidden items-center gap-6 lg:flex" aria-label="Main navigation">
          {navItems.map((item) => {
            const active =
              item.to === "/"
                ? pathname === "/"
                : !item.to.includes("#") && pathname.startsWith(item.to);
            return (
              <Link
                key={item.label}
                to={item.to}
                className={`text-sm font-medium transition-colors ${
                  active ? "text-white" : "text-[#9CA3AF] hover:text-white"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        {/* Desktop Auth Actions */}
        <div className="hidden items-center gap-3 lg:flex">
          {session ? (
            <>
              {isAdmin && (
                <Link
                  to="/admin"
                  className="inline-flex items-center gap-1.5 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-xs font-semibold text-amber-300 transition hover:bg-amber-500/20"
                >
                  <ShieldCheck className="h-3.5 w-3.5" />
                  Admin
                </Link>
              )}
              <Link
                to="/account"
                className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-[#111216] px-3.5 py-2 text-xs font-semibold text-[#F3F4F6] transition hover:border-white/20 hover:bg-[#16181D]"
              >
                <User className="h-3.5 w-3.5 text-[#3B82F6]" />
                {profile?.full_name || session.user.email}
              </Link>
              <button
                type="button"
                disabled={signingOut}
                onClick={handleSignOut}
                className="rounded-lg px-3 py-2 text-xs font-medium text-[#9CA3AF] transition hover:text-white disabled:opacity-50"
              >
                {signingOut ? "Signing Out..." : "Sign Out"}
              </button>
            </>
          ) : (
            <>
              <Link
                to="/auth/sign-in"
                className="rounded-lg px-3.5 py-2 text-sm font-medium text-[#9CA3AF] transition hover:text-white"
              >
                Sign In
              </Link>
              <Link
                to="/auth/sign-up"
                className="rounded-lg bg-[#3B82F6] px-4 py-2 text-sm font-semibold text-white transition hover:bg-[#2563EB]"
              >
                Get Started
              </Link>
            </>
          )}
        </div>

        {/* Mobile menu button */}
        <button
          type="button"
          onClick={() => setMobileOpen((v) => !v)}
          className="inline-flex items-center justify-center rounded-lg border border-white/10 bg-[#111216] p-2 text-[#9CA3AF] hover:text-white lg:hidden"
          aria-label="Toggle navigation menu"
        >
          {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </div>

      {/* Mobile Nav Drawer */}
      {mobileOpen && (
        <div className="border-t border-white/[0.07] bg-[#0D0E11] px-4 pb-5 pt-3 lg:hidden">
          <div className="flex flex-col space-y-2">
            {navItems.map((item) => (
              <Link
                key={item.label}
                to={item.to}
                onClick={() => setMobileOpen(false)}
                className="rounded-lg px-3 py-2 text-sm font-medium text-[#D1D5DB] hover:bg-white/5 hover:text-white"
              >
                {item.label}
              </Link>
            ))}
            <div className="my-2 border-t border-white/[0.07]" />
            {session ? (
              <>
                <Link
                  to="/account"
                  onClick={() => setMobileOpen(false)}
                  className="rounded-lg bg-[#16181D] px-3 py-2.5 text-sm font-semibold text-white"
                >
                  Account & Subscription
                </Link>
                {isAdmin && (
                  <Link
                    to="/admin"
                    onClick={() => setMobileOpen(false)}
                    className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2.5 text-sm font-semibold text-amber-300"
                  >
                    Admin Panel
                  </Link>
                )}
                <button
                  type="button"
                  disabled={signingOut}
                  onClick={handleSignOut}
                  className="rounded-lg px-3 py-2 text-left text-sm font-medium text-red-400 hover:bg-red-500/10 disabled:opacity-50"
                >
                  {signingOut ? "Signing Out..." : "Sign Out"}
                </button>
              </>
            ) : (
              <div className="flex flex-col gap-2 pt-1">
                <Link
                  to="/auth/sign-in"
                  onClick={() => setMobileOpen(false)}
                  className="rounded-lg border border-white/10 bg-[#111216] px-4 py-2.5 text-center text-sm font-semibold text-white"
                >
                  Sign In
                </Link>
                <Link
                  to="/auth/sign-up"
                  onClick={() => setMobileOpen(false)}
                  className="rounded-lg bg-[#3B82F6] px-4 py-2.5 text-center text-sm font-semibold text-white"
                >
                  Get Started
                </Link>
              </div>
            )}
          </div>
        </div>
      )}
    </header>
  );
};

export const SiteFooter: React.FC = () => {
  return (
    <footer className="border-t border-white/[0.07] bg-[#0D0E11]">
      <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="grid gap-8 md:grid-cols-4">
          <div className="md:col-span-2">
            <div className="flex items-center gap-3">
              <img
                src="/logo.png"
                alt="Institutional EA"
                className="h-8 w-8 rounded-lg border border-white/10 bg-[#111216] object-contain p-1"
              />
              <span className="text-sm font-bold tracking-wide text-white">
                INSTITUTIONAL EA
              </span>
            </div>
            <p className="mt-3 max-w-md text-sm leading-relaxed text-[#9CA3AF]">
              Institutional-grade multi-timeframe MetaTrader 5 algorithmic trading ecosystem
              combining local Python quantitative execution, strict risk controls, and a dedicated
              Windows Companion Control Centre.
            </p>
            <p className="mt-4 max-w-lg text-xs leading-relaxed text-[#6B7280]">
              Risk Disclosure: Algorithmic trading in Forex, commodities, and CFDs carries
              substantial risk of loss and is not suitable for every investor. Past performance does
              not guarantee future results.
            </p>
          </div>

          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[#9CA3AF]">
              Platform
            </h3>
            <ul className="mt-3 space-y-2.5 text-sm text-[#D1D5DB]">
              <li>
                <Link to="/#platform" className="hover:text-white">
                  About Institutional EA
                </Link>
              </li>
              <li>
                <Link to="/pricing" className="hover:text-white">
                  Pricing ($50 / mo)
                </Link>
              </li>
              <li>
                <Link to="/docs" className="hover:text-white">
                  Documentation
                </Link>
              </li>
              <li>
                <Link to="/auth/sign-in" className="hover:text-white">
                  Sign In
                </Link>
              </li>
            </ul>
          </div>

          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-[#9CA3AF]">
              Legal & Support
            </h3>
            <ul className="mt-3 space-y-2.5 text-sm text-[#D1D5DB]">
              <li>
                <Link to="/legal/terms" className="hover:text-white">
                  Terms of Service
                </Link>
              </li>
              <li>
                <Link to="/legal/privacy" className="hover:text-white">
                  Privacy Policy
                </Link>
              </li>
              <li>
                <Link to="/legal/risk-disclosure" className="hover:text-white">
                  Risk Disclosure
                </Link>
              </li>
              <li>
                <Link to="/contact" className="hover:text-white">
                  Contact
                </Link>
              </li>
            </ul>
          </div>
        </div>

        <div className="mt-10 flex flex-col items-center justify-between gap-4 border-t border-white/[0.06] pt-6 text-xs text-[#6B7280] sm:flex-row">
          <div>© {new Date().getFullYear()} Institutional EA. All rights reserved.</div>
          <div className="font-mono">
            Local Execution Engine · Supabase Cloud Identity · Windows Companion
          </div>
        </div>
      </div>
    </footer>
  );
};

export const SiteLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  return (
    <div className="flex min-h-screen flex-col bg-[#0A0A0C] text-[#F3F4F6]">
      <SiteHeader />
      <main className="flex-1">{children}</main>
      <SiteFooter />
    </div>
  );
};
