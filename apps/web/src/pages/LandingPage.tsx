import React, { useEffect, useState } from "react";
import {
  Activity,
  ArrowRight,
  BarChart3,
  Bell,
  Check,
  Copy,
  Cpu,
  Download,
  Layers,
  Lock,
  Monitor,
  Scale,
  Server,
  Shield,
  SlidersHorizontal,
  Terminal,
} from "lucide-react";
import { Link } from "../lib/router";
import {
  DEFAULT_APP_VERSION,
  DOWNLOAD_PLATFORMS,
  LATEST_RELEASE_API_URL,
  SITE_LINKS,
} from "../config/downloads.config";

interface ReleaseInfo {
  version: string;
  sizeFormatted?: string;
  sha256?: string;
  downloadAvailable: boolean;
  downloadUrl: string;
}

const PLATFORM_CAPABILITIES = [
  {
    icon: Layers,
    title: "Multi-Timeframe Algorithmic Trading",
    desc: "Cascading W1 → D1 → H4 → H1 → M15 → M5/M1 analysis across specialized XAUUSD, USDJPY, and BTCUSD schedules.",
  },
  {
    icon: Activity,
    title: "Market Structure & Liquidity Analysis",
    desc: "Deterministic CHoCH-warning to BOS-confirmation state machine tracking PDH/PDL, PWH/PWL, EQH/EQL, and session sweeps.",
  },
  {
    icon: BarChart3,
    title: "FVG & Order-Block Detection",
    desc: "Canonical Smart Money Concepts rulebook (R1–R9) with Fair Value Gaps, Order Blocks, Inverse FVGs, and confluence scoring.",
  },
  {
    icon: Scale,
    title: "Dynamic Position Sizing",
    desc: "Exact tick-value lot sizing with downward volume rounding, $5 micro/cent account adaptation, and minimum-lot risk floors.",
  },
  {
    icon: Shield,
    title: "Quantitative Risk Management",
    desc: "DEMO, PROP, and LIVE risk profiles, GARCH/EWMA volatility modeling, drawdown throttles, and 3-layer tighten-only SL enforcement.",
  },
  {
    icon: Cpu,
    title: "MetaTrader 5 Integration",
    desc: "Native PythonBridgeEA.mq5 running on a single MT5 chart over persistent localhost TCP sockets (ports 5555/5556).",
  },
  {
    icon: Terminal,
    title: "Automated Trade Execution",
    desc: "Pre-trade checklist gating, deterministic idempotent order IDs, server-side SL/TP enforcement, and manual position adoption.",
  },
  {
    icon: SlidersHorizontal,
    title: "Performance Monitoring & Analytics",
    desc: "Real MT5 balance snapshots, equity curves, cumulative R, drawdown tracking, trade screenshots, and candle-by-candle trade replay.",
  },
  {
    icon: Bell,
    title: "Structured Telegram Notifications",
    desc: "3-tier alert policy (LOUD, SILENT, ON_DEMAND) with live-edited trade cards, pinned status card, and chat-ID-locked remote commands.",
  },
  {
    icon: Monitor,
    title: "Windows Companion Control Centre",
    desc: "Dark institutional trading terminal with live SMC charts, versioned config rollback, allowlisted operations, and SQLite audit logs.",
  },
];

const ARCHITECTURE_NODES = [
  {
    step: "01",
    name: "MetaTrader 5",
    role: "Broker Terminal & Execution Venue",
    detail: "Authoritative broker prices, positions, orders, and margin state on your local Windows machine.",
  },
  {
    step: "02",
    name: "PythonBridgeEA",
    role: "Native MQL5 Expert Advisor",
    detail: "Single-chart EA handling 7-point warm-up, order safety gates, chart levels, and localhost TCP IPC.",
  },
  {
    step: "03",
    name: "Python Algorithmic Engine",
    role: "Quantitative SMC & Risk Core",
    detail: "Multi-timeframe analysis, SetupQualityGate, position sizing, CUSUM/PSI guards, and Telegram dispatcher.",
  },
  {
    step: "04",
    name: "Local Control Service",
    role: "Authenticated 127.0.0.1:8765 API",
    detail: "Token-protected REST + SSE bus, embedded SQLite WAL persistence, config versioning, and allowlisted ops.",
  },
  {
    step: "05",
    name: "Windows Companion App",
    role: "Electron + React Trading Terminal",
    detail: "16-screen desktop workstation with live SMC charts, emergency controls, and OS-encrypted cloud identity.",
  },
];

export const LandingPage: React.FC = () => {
  const [release, setRelease] = useState<ReleaseInfo>({
    version: DEFAULT_APP_VERSION,
    sizeFormatted: DOWNLOAD_PLATFORMS.windows.fallbackSize,
    downloadAvailable: false,
    downloadUrl: SITE_LINKS.releases,
  });
  const [copiedHash, setCopiedHash] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function checkRelease() {
      try {
        const res = await fetch(LATEST_RELEASE_API_URL, {
          headers: { Accept: "application/vnd.github+json" },
        });
        if (!res.ok) return;
        const json = await res.json();
        const tag = typeof json.tag_name === "string" ? json.tag_name.replace(/^v/, "") : DEFAULT_APP_VERSION;
        const winAsset = Array.isArray(json.assets)
          ? json.assets.find((a: { name?: string }) =>
              String(a?.name || "").toLowerCase().endsWith(".exe")
            )
          : null;

        if (!cancelled && winAsset?.browser_download_url) {
          const mb = Number(winAsset.size) > 0 ? `${(Number(winAsset.size) / (1024 * 1024)).toFixed(1)} MB` : DOWNLOAD_PLATFORMS.windows.fallbackSize;
          setRelease({
            version: tag,
            sizeFormatted: mb,
            downloadAvailable: true,
            downloadUrl: winAsset.browser_download_url,
          });
        }
      } catch {
        // Keep safe release-page fallback without exposing broken links
      }
    }
    checkRelease();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div>
      {/* 1. HERO SECTION */}
      <section className="relative border-b border-white/[0.06] bg-[#0A0A0C]">
        <div className="mx-auto grid max-w-7xl items-center gap-12 px-4 py-20 sm:px-6 lg:grid-cols-12 lg:px-8 lg:py-28">
          <div className="lg:col-span-7">
            <div className="inline-flex items-center gap-2 rounded-full border border-blue-500/30 bg-blue-500/10 px-3.5 py-1 text-xs font-semibold text-blue-300">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              MetaTrader 5 · Local Execution · Institutional Architecture
            </div>

            <h1 className="mt-6 text-4xl font-extrabold tracking-tight text-white sm:text-5xl lg:text-[3.35rem] lg:leading-[1.1]">
              Intelligent Algorithmic Trading.{" "}
              <span className="text-[#3B82F6]">Institutional-Level Execution.</span>
            </h1>

            <p className="mt-6 max-w-2xl text-base leading-relaxed text-[#9CA3AF] sm:text-lg">
              An advanced MT5 algorithmic trading ecosystem combining quantitative intelligence,
              multi-timeframe market analysis, precision risk management, and automated execution in
              one integrated platform.
            </p>

            <div className="mt-8 flex flex-wrap items-center gap-4">
              <Link
                to="/auth/sign-up"
                className="inline-flex items-center gap-2 rounded-lg bg-[#3B82F6] px-6 py-3 text-sm font-semibold text-white transition hover:bg-[#2563EB]"
              >
                Get Started
                <ArrowRight className="h-4 w-4" />
              </Link>
              <Link
                to="/#platform"
                className="inline-flex items-center gap-2 rounded-lg border border-white/15 bg-[#111216] px-6 py-3 text-sm font-semibold text-[#F3F4F6] transition hover:border-white/25 hover:bg-[#16181D]"
              >
                Explore Platform
              </Link>
              <Link
                to="/pricing"
                className="px-2 py-2 text-sm font-medium text-[#9CA3AF] transition hover:text-white"
              >
                View Pricing ($50/mo)
              </Link>
            </div>

            <div className="mt-10 grid grid-cols-3 gap-4 border-t border-white/[0.07] pt-6 sm:max-w-lg">
              <div>
                <div className="font-mono text-lg font-bold text-white">XAU · JPY · BTC</div>
                <div className="mt-0.5 text-xs text-[#6B7280]">Specialized 3-Asset Engine</div>
              </div>
              <div>
                <div className="font-mono text-lg font-bold text-white">127.0.0.1</div>
                <div className="mt-0.5 text-xs text-[#6B7280]">Localhost Execution Only</div>
              </div>
              <div>
                <div className="font-mono text-lg font-bold text-emerald-400">DEMO Lock</div>
                <div className="mt-0.5 text-xs text-[#6B7280]">Hard Safety Guardrails</div>
              </div>
            </div>
          </div>

          {/* Ecosystem Visual Card using real brand assets */}
          <div className="lg:col-span-5">
            <div className="rounded-2xl border border-white/10 bg-[#111216] p-6 shadow-2xl">
              <div className="flex items-center justify-between border-b border-white/[0.07] pb-4">
                <div className="flex items-center gap-3">
                  <img
                    src="/logo.png"
                    alt="Institutional EA Brand"
                    className="h-10 w-10 rounded-xl border border-white/10 bg-[#0D0E11] object-contain p-1.5"
                  />
                  <div>
                    <div className="text-sm font-bold text-white">Institutional EA Companion</div>
                    <div className="font-mono text-[11px] text-[#6B7280]">
                      Windows Desktop Workstation · v{release.version}
                    </div>
                  </div>
                </div>
                <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-0.5 font-mono text-[11px] font-semibold text-emerald-400">
                  LOCAL IPC
                </span>
              </div>

              <div className="mt-5 space-y-3 font-mono text-xs">
                <div className="flex items-center justify-between rounded-lg border border-white/[0.06] bg-[#0D0E11] px-3.5 py-2.5">
                  <span className="text-[#9CA3AF]">Execution Pipeline</span>
                  <span className="text-white">MT5 ⇄ PythonBridgeEA ⇄ Engine</span>
                </div>
                <div className="flex items-center justify-between rounded-lg border border-white/[0.06] bg-[#0D0E11] px-3.5 py-2.5">
                  <span className="text-[#9CA3AF]">Control Service</span>
                  <span className="text-blue-400">127.0.0.1:8765 · SQLite WAL</span>
                </div>
                <div className="flex items-center justify-between rounded-lg border border-white/[0.06] bg-[#0D0E11] px-3.5 py-2.5">
                  <span className="text-[#9CA3AF]">Risk Guardrails</span>
                  <span className="text-emerald-400">Tighten-Only SL · R9 Cap</span>
                </div>
                <div className="flex items-center justify-between rounded-lg border border-white/[0.06] bg-[#0D0E11] px-3.5 py-2.5">
                  <span className="text-[#9CA3AF]">Cloud Identity</span>
                  <span className="text-amber-300">Supabase Auth · OS Encrypted</span>
                </div>
              </div>

              <div className="mt-5 rounded-xl border border-blue-500/20 bg-blue-500/[0.06] p-4">
                <div className="flex items-start gap-3">
                  <Lock className="mt-0.5 h-4 w-4 shrink-0 text-[#3B82F6]" />
                  <p className="text-xs leading-relaxed text-[#D1D5DB]">
                    Broker credentials and MT5 order execution never leave your Windows machine.
                    Cloud services handle only account authentication, subscription entitlements,
                    and device registration.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 2. PLATFORM OVERVIEW */}
      <section id="platform" className="border-b border-white/[0.06] bg-[#0D0E11] py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="max-w-3xl">
            <div className="font-mono text-xs font-semibold uppercase tracking-widest text-[#3B82F6]">
              Platform Overview
            </div>
            <h2 className="mt-2 text-3xl font-bold tracking-tight text-white">
              Engineered for Deterministic Execution & Risk Discipline
            </h2>
            <p className="mt-4 text-sm leading-relaxed text-[#9CA3AF] sm:text-base">
              Every module in Institutional EA is built around verifiable quantitative rules,
              real MetaTrader 5 broker feeds, and strict operational safety locks — zero synthetic
              placeholders and zero unverified claims.
            </p>
          </div>

          <div id="features" className="mt-12 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {PLATFORM_CAPABILITIES.map((cap) => {
              const Icon = cap.icon;
              return (
                <div
                  key={cap.title}
                  className="rounded-xl border border-white/[0.07] bg-[#111216] p-6 transition hover:border-white/15"
                >
                  <div className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-blue-500/25 bg-blue-500/10 text-[#3B82F6]">
                    <Icon className="h-5 w-5" />
                  </div>
                  <h3 className="mt-4 text-base font-semibold text-white">{cap.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-[#9CA3AF]">{cap.desc}</p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* 3. SYSTEM ARCHITECTURE */}
      <section id="architecture" className="border-b border-white/[0.06] bg-[#0A0A0C] py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="max-w-3xl">
            <div className="font-mono text-xs font-semibold uppercase tracking-widest text-[#3B82F6]">
              System Architecture
            </div>
            <h2 className="mt-2 text-3xl font-bold tracking-tight text-white">
              Strict Separation: Local Execution vs. Cloud Account Layer
            </h2>
            <p className="mt-4 text-sm leading-relaxed text-[#9CA3AF] sm:text-base">
              Your trading engine runs locally alongside MetaTrader 5 with zero external inbound
              ports. Cloud connectivity is strictly scoped to identity, subscription verification,
              and registered device management.
            </p>
          </div>

          {/* 5-Stage Local Execution Pipeline */}
          <div className="mt-10 rounded-2xl border border-white/[0.08] bg-[#111216] p-6 sm:p-8">
            <div className="mb-6 flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-sm font-semibold text-white">
                <Server className="h-4 w-4 text-emerald-400" />
                Local Execution Plane (Your Windows Machine / VPS)
              </div>
              <span className="rounded-md border border-emerald-500/25 bg-emerald-500/10 px-2.5 py-1 font-mono text-[11px] text-emerald-300">
                127.0.0.1 · SQLite WAL · Local Safety Locks
              </span>
            </div>

            <div className="grid gap-4 md:grid-cols-5">
              {ARCHITECTURE_NODES.map((node, idx) => (
                <div
                  key={node.name}
                  className="relative rounded-xl border border-white/[0.07] bg-[#0D0E11] p-4"
                >
                  <div className="font-mono text-[11px] font-bold text-[#3B82F6]">
                    STAGE {node.step}
                  </div>
                  <div className="mt-1 text-sm font-bold text-white">{node.name}</div>
                  <div className="mt-0.5 text-xs font-medium text-[#9CA3AF]">{node.role}</div>
                  <p className="mt-2.5 text-xs leading-relaxed text-[#6B7280]">{node.detail}</p>
                  {idx < ARCHITECTURE_NODES.length - 1 && (
                    <div className="mt-3 font-mono text-xs text-[#3B82F6] md:hidden">↓</div>
                  )}
                </div>
              ))}
            </div>

            <div className="mt-6 grid gap-4 border-t border-white/[0.07] pt-6 md:grid-cols-2">
              <div className="rounded-xl border border-white/[0.07] bg-[#0D0E11] p-5">
                <div className="text-xs font-semibold uppercase tracking-wider text-emerald-400">
                  Local Execution Guarantees
                </div>
                <ul className="mt-3 space-y-2 text-xs text-[#D1D5DB]">
                  <li>• Local SQLite WAL database preserves trade history, config versions, and audit logs.</li>
                  <li>• Emergency controls (Pause, Stop, Close All, Kill Switch) remain locally operable at all times.</li>
                  <li>• Subscription expiration never forcibly closes open MT5 positions or alters local risk limits.</li>
                </ul>
              </div>
              <div className="rounded-xl border border-blue-500/20 bg-blue-500/[0.05] p-5">
                <div className="text-xs font-semibold uppercase tracking-wider text-blue-300">
                  Cloud Identity & Subscription Plane (Supabase)
                </div>
                <ul className="mt-3 space-y-2 text-xs text-[#D1D5DB]">
                  <li>• Supabase Auth (email verification + desktop PKCE sign-in) with Windows DPAPI token storage.</li>
                  <li>• Row Level Security (RLS) enforced on profiles, subscriptions, payments, devices, and audit logs.</li>
                  <li>• 72-hour offline grace cache so brief internet outages never interrupt local operations.</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 4. WINDOWS COMPANION DOWNLOAD SECTION */}
      <section id="download" className="border-b border-white/[0.06] bg-[#0D0E11] py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="grid items-center gap-8 rounded-2xl border border-white/10 bg-[#111216] p-8 lg:grid-cols-12">
            <div className="lg:col-span-7">
              <div className="font-mono text-xs font-semibold uppercase tracking-widest text-[#3B82F6]">
                Windows Companion Application
              </div>
              <h2 className="mt-2 text-2xl font-bold text-white sm:text-3xl">
                Download Institutional EA for Windows
              </h2>
              <p className="mt-3 text-sm leading-relaxed text-[#9CA3AF]">
                Built for Windows 10 and Windows 11 (64-bit) alongside MetaTrader 5. Release
                installers are published exclusively through official versioned releases with
                SHA-256 verification.
              </p>

              <div className="mt-5 grid gap-3 text-xs text-[#D1D5DB] sm:grid-cols-3">
                <div className="rounded-lg border border-white/[0.06] bg-[#0D0E11] p-3">
                  <div className="text-[#6B7280]">Current Version</div>
                  <div className="mt-1 font-mono font-semibold text-white">v{release.version}</div>
                </div>
                <div className="rounded-lg border border-white/[0.06] bg-[#0D0E11] p-3">
                  <div className="text-[#6B7280]">Platform</div>
                  <div className="mt-1 font-mono font-semibold text-white">Windows 10/11 x64</div>
                </div>
                <div className="rounded-lg border border-white/[0.06] bg-[#0D0E11] p-3">
                  <div className="text-[#6B7280]">Installer</div>
                  <div className="mt-1 font-mono font-semibold text-white">
                    {release.sizeFormatted}
                  </div>
                </div>
              </div>
            </div>

            <div className="flex flex-col gap-3 lg:col-span-5">
              {release.downloadAvailable ? (
                <a
                  href={release.downloadUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-[#3B82F6] px-6 py-3.5 text-sm font-semibold text-white transition hover:bg-[#2563EB]"
                >
                  <Download className="h-4 w-4" />
                  Download Windows Installer (v{release.version})
                </a>
              ) : (
                <a
                  href={SITE_LINKS.releases}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-[#3B82F6] px-6 py-3.5 text-sm font-semibold text-white transition hover:bg-[#2563EB]"
                >
                  <Download className="h-4 w-4" />
                  View Official Releases on GitHub
                </a>
              )}

              <Link
                to="/pricing"
                className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/15 bg-[#0D0E11] px-6 py-3 text-sm font-semibold text-white transition hover:bg-[#16181D]"
              >
                Subscribe — Institutional EA Pro ($50/mo)
              </Link>

              {release.sha256 && (
                <button
                  type="button"
                  onClick={() => {
                    navigator.clipboard?.writeText(release.sha256 || "");
                    setCopiedHash(true);
                    setTimeout(() => setCopiedHash(false), 1800);
                  }}
                  className="inline-flex items-center justify-center gap-2 rounded-lg border border-white/[0.07] bg-[#0D0E11] px-3 py-2 font-mono text-[11px] text-[#9CA3AF] hover:text-white"
                >
                  {copiedHash ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                  {copiedHash ? "SHA-256 Copied" : `SHA-256: ${release.sha256.slice(0, 18)}…`}
                </button>
              )}

              <p className="text-center text-[11px] text-[#6B7280]">
                Active Institutional EA Pro subscription required for full cloud-connected Companion access.
              </p>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};
