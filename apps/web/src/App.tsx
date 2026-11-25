import React, { useEffect, useMemo, useState } from "react";
import {
  Apple,
  Check,
  Copy,
  Download,
  ExternalLink,
  Globe,
  Lock,
  Mail,
  Monitor,
  Moon,
  ShieldAlert,
  ShieldCheck,
  Smartphone,
  Sun,
} from "lucide-react";
import {
  DEFAULT_APP_VERSION,
  DOWNLOAD_PLATFORMS,
  LATEST_RELEASE_API_URL,
  PLATFORM_ORDER,
  SECURITY_AND_DISCLAIMER,
  SITE_LINKS,
  type PlatformId,
} from "./config/downloads.config";
import { PhoneMockup } from "./components/PhoneMockup";

interface LiveReleaseAsset {
  sizeFormatted: string;
  sha256?: string;
}

interface LiveReleaseData {
  version: string;
  assets: Record<string, LiveReleaseAsset>;
}

function detectVisitorOS(): PlatformId {
  if (typeof navigator === "undefined") return "windows";
  const ua = navigator.userAgent || "";
  if (/android/i.test(ua)) return "android";
  if (/iPad|iPhone|iPod/i.test(ua)) return "ios";
  if (/Macintosh|Mac OS X/i.test(ua)) return "macos";
  return "windows";
}

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return "";
  const mb = bytes / (1024 * 1024);
  return `${mb.toFixed(1)} MB`;
}

const HOW_IT_WORKS_STEPS = [
  {
    step: "01",
    title: "Install Desktop Companion",
    body: "Run Institutional EA on Windows or macOS alongside your MetaTrader 5 terminal.",
  },
  {
    step: "02",
    title: "Pair Your Phone Safely",
    body: "Scan a one-time read-only pairing token. Zero broker passwords or MT5 keys ever leave your PC.",
  },
  {
    step: "03",
    title: "Inspect Exact SMC Charts",
    body: "View the same TradingView-style candles, FVG, OB, IFVG, BOS/CHoCH, and SL/TP zones on mobile.",
  },
  {
    step: "04",
    title: "Track Live Equity & P/L",
    body: "Monitor open positions, today's P/L, and total profits in real time with read-only peace of mind.",
  },
];

export default function App(): React.ReactElement {
  const [darkMode, setDarkMode] = useState(false);
  const [detectedOS] = useState<PlatformId>(() => detectVisitorOS());
  const [activeTab, setActiveTab] = useState<"desktop" | "mobile">(
    detectedOS === "android" || detectedOS === "ios" ? "mobile" : "desktop"
  );
  const [liveRelease, setLiveRelease] = useState<LiveReleaseData | null>(null);
  const [releaseFetchFailed, setReleaseFetchFailed] = useState(false);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", darkMode);
  }, [darkMode]);

  // Fetch latest GitHub Release metadata (version, asset sizes, SHA256SUMS.txt) with 15-min localStorage cache
  useEffect(() => {
    let cancelled = false;
    const CACHE_KEY = "iea_latest_release_cache_v1";
    const CACHE_TTL_MS = 15 * 60 * 1000;

    try {
      const raw = localStorage.getItem(CACHE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed?.ts && Date.now() - parsed.ts < CACHE_TTL_MS && parsed?.data) {
          setLiveRelease(parsed.data as LiveReleaseData);
          return;
        }
      }
    } catch {
      // Ignore storage errors
    }

    async function loadLatestRelease() {
      try {
        const res = await fetch(LATEST_RELEASE_API_URL, {
          headers: { Accept: "application/vnd.github+json" },
        });
        if (!res.ok) {
          if (!cancelled) setReleaseFetchFailed(true);
          return;
        }
        const json = await res.json();
        const tag = typeof json.tag_name === "string" ? json.tag_name.replace(/^v/, "") : DEFAULT_APP_VERSION;
        const assetsMap: Record<string, LiveReleaseAsset> = {};
        let sumsUrl: string | null = null;

        if (Array.isArray(json.assets)) {
          for (const a of json.assets) {
            if (typeof a?.name === "string") {
              assetsMap[a.name] = { sizeFormatted: formatBytes(a.size) };
              if (a.name === "SHA256SUMS.txt" && typeof a.browser_download_url === "string") {
                sumsUrl = a.browser_download_url;
              }
            }
          }
        }

        if (sumsUrl) {
          try {
            const sumsRes = await fetch(sumsUrl);
            if (sumsRes.ok) {
              const txt = await sumsRes.text();
              for (const line of txt.split(/\r?\n/)) {
                const match = line.trim().match(/^([a-fA-F0-9]{64})\s+(.+)$/);
                if (match) {
                  const [, hash, filename] = match;
                  assetsMap[filename] = {
                    ...(assetsMap[filename] || { sizeFormatted: "" }),
                    sha256: hash,
                  };
                }
              }
            }
          } catch {
            // Optional checksum fetch; ignore CORS/network errors gracefully
          }
        }

        if (!cancelled) {
          const payload: LiveReleaseData = { version: tag, assets: assetsMap };
          setLiveRelease(payload);
          setReleaseFetchFailed(false);
          try {
            localStorage.setItem(CACHE_KEY, JSON.stringify({ ts: Date.now(), data: payload }));
          } catch {
            // Ignore quota errors
          }
        }
      } catch {
        if (!cancelled) setReleaseFetchFailed(true);
      }
    }
    loadLatestRelease();
    return () => {
      cancelled = true;
    };
  }, []);

  const displayVersion = liveRelease?.version ?? DEFAULT_APP_VERSION;
  const primaryPlatform = DOWNLOAD_PLATFORMS[detectedOS];
  const orderedPlatforms = useMemo(() => {
    return [detectedOS, ...PLATFORM_ORDER.filter((id) => id !== detectedOS)].map(
      (id) => DOWNLOAD_PLATFORMS[id]
    );
  }, [detectedOS]);

  const tabPlatforms = useMemo(
    () => PLATFORM_ORDER.map((id) => DOWNLOAD_PLATFORMS[id]).filter((p) => p.category === activeTab),
    [activeTab]
  );

  const handleCopy = (key: string, value: string) => {
    navigator.clipboard?.writeText(value).then(() => {
      setCopiedKey(key);
      setTimeout(() => setCopiedKey(null), 1800);
    });
  };

  const renderPlatformIcon = (id: PlatformId) => {
    if (id === "macos" || id === "ios") return <Apple className="h-4 w-4" />;
    if (id === "android") return <Smartphone className="h-4 w-4" />;
    return <Monitor className="h-4 w-4" />;
  };

  const renderDownloadButton = (id: PlatformId, emphasizePrimary = false) => {
    const cfg = DOWNLOAD_PLATFORMS[id];
    const isComingSoon = !cfg.downloadUrl;
    const isPrimary = emphasizePrimary && id === detectedOS;
    const liveSize = liveRelease?.assets[cfg.assetName]?.sizeFormatted || cfg.fallbackSize;

    if (isComingSoon) {
      return (
        <span
          key={id}
          aria-disabled="true"
          className="inline-flex cursor-not-allowed items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-100 px-4 py-3 text-left text-sm font-semibold text-slate-400 dark:border-slate-800 dark:bg-slate-900/60 dark:text-slate-500"
        >
          <span className="flex items-center gap-2.5">
            {renderPlatformIcon(id)}
            <span>
              <span className="block leading-tight">{cfg.name}</span>
              <span className="block text-[11px] font-normal">Coming soon</span>
            </span>
          </span>
          <span className="rounded-full bg-slate-200 px-2 py-0.5 text-[10px] font-semibold uppercase text-slate-500 dark:bg-slate-800">
            Soon
          </span>
        </span>
      );
    }

    return (
      <a
        key={id}
        href={cfg.downloadUrl}
        className={`group inline-flex items-center justify-between gap-3 rounded-xl px-4 py-3 text-left text-sm font-semibold transition-all ${
          isPrimary
            ? "bg-emerald-600 text-white shadow-lg shadow-emerald-600/25 hover:bg-emerald-700"
            : "border border-slate-200 bg-white text-slate-900 hover:border-emerald-500 hover:bg-emerald-50/40 dark:border-slate-800 dark:bg-slate-900 dark:text-white dark:hover:border-emerald-500"
        }`}
      >
        <span className="flex items-center gap-2.5">
          {renderPlatformIcon(id)}
          <span>
            <span className="block leading-tight">{cfg.ctaLabel}</span>
            <span
              className={`block text-[11px] font-normal ${
                isPrimary ? "text-emerald-100" : "text-slate-500 dark:text-slate-400"
              }`}
            >
              v{displayVersion} · {liveSize}
            </span>
          </span>
        </span>
        <Download className="h-4 w-4 shrink-0 transition-transform group-hover:translate-y-0.5" />
      </a>
    );
  };

  return (
    <div className="min-h-screen bg-white text-slate-900 transition-colors dark:bg-[#0D0E11] dark:text-slate-100">
      {/* Sticky Top Navigation */}
      <header className="sticky top-0 z-40 border-b border-slate-100 bg-white/90 backdrop-blur-md dark:border-slate-800/80 dark:bg-[#0D0E11]/90">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3.5 sm:px-6">
          <a href="#" className="flex items-center gap-2.5">
            <img
              src="/logo.png"
              alt="Institutional EA Logo"
              className="h-9 w-9 rounded-xl bg-black object-contain p-0.5 shadow-sm ring-1 ring-slate-200/80 dark:ring-white/15"
            />
            <span className="text-base font-extrabold tracking-tight">Institutional EA</span>
          </a>

          <nav className="hidden items-center gap-7 text-sm font-medium text-slate-600 md:flex dark:text-slate-300">
            <a href="#how-it-works" className="hover:text-emerald-600 dark:hover:text-emerald-400">
              How it works
            </a>
            <a href="#platforms" className="hover:text-emerald-600 dark:hover:text-emerald-400">
              Desktop & Mobile
            </a>
            <a href="#security" className="hover:text-emerald-600 dark:hover:text-emerald-400">
              Security
            </a>
          </nav>

          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={() => setDarkMode((v) => !v)}
              aria-label="Toggle light and dark theme"
              className="flex h-9 w-9 items-center justify-center rounded-full border border-slate-200 text-slate-600 hover:bg-slate-100 dark:border-slate-800 dark:text-slate-300 dark:hover:bg-slate-800"
            >
              {darkMode ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
            <a
              href="#download-banner"
              className="inline-flex items-center gap-1.5 rounded-full bg-emerald-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700"
            >
              Get the app
            </a>
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section className="relative overflow-hidden py-14 sm:py-20">
        <div className="mx-auto grid max-w-6xl items-center gap-12 px-4 sm:px-6 lg:grid-cols-2">
          <div>
            <span className="inline-flex items-center gap-2 rounded-full bg-emerald-50 px-3.5 py-1.5 text-xs font-semibold text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400">
              <ShieldCheck className="h-3.5 w-3.5" />
              Version {displayVersion} · Detected {primaryPlatform.name}
            </span>

            <h1 className="mt-5 text-4xl font-extrabold tracking-tight text-slate-900 sm:text-5xl lg:text-6xl dark:text-white">
              Monitor your bot.{" "}
              <span className="text-emerald-600 dark:text-emerald-400">Anywhere.</span>
            </h1>

            <p className="mt-5 max-w-xl text-base leading-relaxed text-slate-600 sm:text-lg dark:text-slate-300">
              Run the Institutional EA desktop companion on Windows or macOS, and track the exact same
              TradingView-style Smart Money Concepts charts, FVG/OB zones, and live positions from your
              phone — strictly read-only.
            </p>

            {/* Primary + Secondary Download Buttons */}
            <div className="mt-8 grid gap-3 sm:grid-cols-2">
              {orderedPlatforms.map((p) => renderDownloadButton(p.id, true))}
            </div>

            <p className="mt-4 text-xs text-slate-500 dark:text-slate-400">
              Recommended for your device:{" "}
              <strong className="text-slate-700 dark:text-slate-200">{primaryPlatform.shortLabel}</strong>{" "}
              ({primaryPlatform.systemRequirements}).{" "}
              <a
                href={SITE_LINKS.releases}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 font-medium text-emerald-600 hover:underline dark:text-emerald-400"
              >
                {releaseFetchFailed ? "View all downloads on GitHub" : "All releases & checksums"}{" "}
                <ExternalLink className="h-3 w-3" />
              </a>
            </p>
          </div>

          <div className="relative flex justify-center">
            <div className="absolute -inset-6 -z-10 rounded-full bg-emerald-500/10 blur-3xl dark:bg-emerald-500/15" />
            <PhoneMockup />
          </div>
        </div>
      </section>

      {/* How It Works — 4 Steps with Centered Phone on Green Circle */}
      <section id="how-it-works" className="bg-slate-50/80 py-16 sm:py-24 dark:bg-slate-900/40">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <div className="mx-auto max-w-2xl text-center">
            <p className="text-xs font-bold uppercase tracking-widest text-emerald-600 dark:text-emerald-400">
              How it works
            </p>
            <h2 className="mt-2 text-3xl font-extrabold tracking-tight sm:text-4xl">
              From MT5 desktop to mobile in four simple steps
            </h2>
          </div>

          <div className="mt-14 grid items-center gap-10 lg:grid-cols-3">
            {/* Left 2 steps */}
            <div className="space-y-8">
              {HOW_IT_WORKS_STEPS.slice(0, 2).map((item) => (
                <div
                  key={item.step}
                  className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-[#13151A]"
                >
                  <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-emerald-100 font-mono text-xs font-bold text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400">
                    {item.step}
                  </span>
                  <h3 className="mt-3 text-lg font-bold">{item.title}</h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-slate-600 dark:text-slate-400">
                    {item.body}
                  </p>
                </div>
              ))}
            </div>

            {/* Centered Phone Mockup over Emerald Circle */}
            <div className="relative flex items-center justify-center py-6">
              <div
                aria-hidden="true"
                className="absolute h-72 w-72 rounded-full bg-emerald-500 shadow-2xl shadow-emerald-500/30 sm:h-80 sm:w-80"
              />
              <div className="relative z-10">
                <PhoneMockup compact />
              </div>
            </div>

            {/* Right 2 steps */}
            <div className="space-y-8">
              {HOW_IT_WORKS_STEPS.slice(2, 4).map((item) => (
                <div
                  key={item.step}
                  className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-[#13151A]"
                >
                  <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-emerald-100 font-mono text-xs font-bold text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400">
                    {item.step}
                  </span>
                  <h3 className="mt-3 text-lg font-bold">{item.title}</h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-slate-600 dark:text-slate-400">
                    {item.body}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Desktop | Mobile Switcher Section */}
      <section id="platforms" className="py-16 sm:py-24">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <div className="flex flex-col items-center justify-between gap-6 sm:flex-row">
            <div>
              <p className="text-xs font-bold uppercase tracking-widest text-emerald-600 dark:text-emerald-400">
                Built for every screen
              </p>
              <h2 className="mt-1 text-3xl font-extrabold tracking-tight">
                System requirements & verification
              </h2>
            </div>

            {/* Passenger/Driver-style Pill Switcher */}
            <div
              role="tablist"
              aria-label="Select platform category"
              className="inline-flex rounded-full bg-slate-100 p-1 dark:bg-slate-800"
            >
              <button
                role="tab"
                type="button"
                aria-selected={activeTab === "desktop"}
                onClick={() => setActiveTab("desktop")}
                className={`inline-flex items-center gap-2 rounded-full px-5 py-2 text-sm font-semibold transition ${
                  activeTab === "desktop"
                    ? "bg-emerald-600 text-white shadow-sm"
                    : "text-slate-600 hover:text-slate-900 dark:text-slate-300 dark:hover:text-white"
                }`}
              >
                <Monitor className="h-4 w-4" /> Desktop
              </button>
              <button
                role="tab"
                type="button"
                aria-selected={activeTab === "mobile"}
                onClick={() => setActiveTab("mobile")}
                className={`inline-flex items-center gap-2 rounded-full px-5 py-2 text-sm font-semibold transition ${
                  activeTab === "mobile"
                    ? "bg-emerald-600 text-white shadow-sm"
                    : "text-slate-600 hover:text-slate-900 dark:text-slate-300 dark:hover:text-white"
                }`}
              >
                <Smartphone className="h-4 w-4" /> Mobile
              </button>
            </div>
          </div>

          <div className="mt-10 grid gap-6 md:grid-cols-2">
            {tabPlatforms.map((cfg) => {
              const live = liveRelease?.assets[cfg.assetName];
              const sizeText = live?.sizeFormatted || cfg.fallbackSize;
              const sha256 = live?.sha256;

              return (
                <div
                  key={cfg.id}
                  className="flex flex-col justify-between rounded-2xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-[#13151A]"
                >
                  <div>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-emerald-50 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-400">
                          {renderPlatformIcon(cfg.id)}
                        </span>
                        <div>
                          <h3 className="text-lg font-bold">{cfg.name}</h3>
                          <p className="text-xs text-slate-500 dark:text-slate-400">
                            {cfg.architecture}
                          </p>
                        </div>
                      </div>
                      <span className="rounded-full bg-slate-100 px-3 py-1 font-mono text-xs font-semibold text-slate-700 dark:bg-slate-800 dark:text-slate-300">
                        v{displayVersion}
                      </span>
                    </div>

                    <dl className="mt-5 space-y-2.5 text-sm">
                      <div className="flex justify-between gap-4 border-b border-slate-100 pb-2 dark:border-slate-800">
                        <dt className="text-slate-500 dark:text-slate-400">Requirements</dt>
                        <dd className="font-medium text-right">{cfg.systemRequirements}</dd>
                      </div>
                      <div className="flex justify-between gap-4 border-b border-slate-100 pb-2 dark:border-slate-800">
                        <dt className="text-slate-500 dark:text-slate-400">Download size</dt>
                        <dd className="font-mono font-medium">{sizeText}</dd>
                      </div>
                      <div className="flex justify-between gap-4 pb-1">
                        <dt className="text-slate-500 dark:text-slate-400">SHA-256</dt>
                        <dd className="flex items-center gap-1.5 font-mono text-xs">
                          {sha256 ? (
                            <>
                              <span title={sha256}>
                                {sha256.slice(0, 12)}…{sha256.slice(-8)}
                              </span>
                              <button
                                type="button"
                                onClick={() => handleCopy(cfg.id, sha256)}
                                aria-label={`Copy ${cfg.name} SHA-256 checksum`}
                                className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-emerald-600 dark:hover:bg-slate-800"
                              >
                                {copiedKey === cfg.id ? (
                                  <Check className="h-3.5 w-3.5 text-emerald-500" />
                                ) : (
                                  <Copy className="h-3.5 w-3.5" />
                                )}
                              </button>
                            </>
                          ) : (
                            <span className="text-slate-400">Published with release</span>
                          )}
                        </dd>
                      </div>
                    </dl>

                    <p className="mt-4 rounded-xl bg-slate-50 p-3 text-xs leading-relaxed text-slate-600 dark:bg-slate-900 dark:text-slate-400">
                      {cfg.installNote}
                    </p>
                  </div>

                  <div className="mt-5">{renderDownloadButton(cfg.id, true)}</div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Green Rounded Download Banner */}
      <section id="download-banner" className="px-4 py-8 sm:px-6">
        <div className="mx-auto max-w-6xl rounded-3xl bg-emerald-600 px-6 py-12 text-white shadow-xl shadow-emerald-600/20 sm:px-12 sm:py-16">
          <div className="mx-auto max-w-2xl text-center">
            <h2 className="text-3xl font-extrabold tracking-tight sm:text-4xl">
              Download Institutional EA
            </h2>
            <p className="mt-3 text-sm text-emerald-50 sm:text-base">
              Always up-to-date stable links for Windows, macOS, Android, and iOS. Verify every download
              with published SHA-256 checksums.
            </p>
          </div>

          <div className="mx-auto mt-8 grid max-w-3xl gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {PLATFORM_ORDER.map((id) => {
              const cfg = DOWNLOAD_PLATFORMS[id];
              const isSoon = !cfg.downloadUrl;
              return isSoon ? (
                <span
                  key={id}
                  className="inline-flex cursor-not-allowed items-center justify-center gap-2 rounded-xl bg-emerald-700/60 px-4 py-3 text-sm font-semibold text-emerald-200"
                >
                  {renderPlatformIcon(id)} {cfg.name} (Soon)
                </span>
              ) : (
                <a
                  key={id}
                  href={cfg.downloadUrl}
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-white px-4 py-3 text-sm font-bold text-emerald-700 shadow-sm transition hover:bg-emerald-50"
                >
                  {renderPlatformIcon(id)} {cfg.name}
                </a>
              );
            })}
          </div>
        </div>
      </section>

      {/* Security Note & Financial Disclaimer */}
      <section id="security" className="py-12">
        <div className="mx-auto max-w-6xl space-y-4 px-4 sm:px-6">
          <div className="flex flex-col gap-3 rounded-2xl border border-emerald-200 bg-emerald-50/70 p-6 sm:flex-row sm:items-start dark:border-emerald-900/60 dark:bg-emerald-950/30">
            <Lock className="h-5 w-5 shrink-0 text-emerald-600 dark:text-emerald-400" />
            <div>
              <h3 className="text-sm font-bold text-emerald-950 dark:text-emerald-300">
                {SECURITY_AND_DISCLAIMER.readOnlyTitle}
              </h3>
              <p className="mt-1 text-xs leading-relaxed text-emerald-900/80 dark:text-emerald-200/80">
                {SECURITY_AND_DISCLAIMER.readOnlyBody}
              </p>
            </div>
          </div>

          <div className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-slate-50 p-5 sm:flex-row sm:items-start dark:border-slate-800 dark:bg-slate-900/50">
            <ShieldAlert className="h-5 w-5 shrink-0 text-slate-500" />
            <p className="text-xs leading-relaxed text-slate-600 dark:text-slate-400">
              {SECURITY_AND_DISCLAIMER.disclaimer}
            </p>
          </div>
        </div>
      </section>

      {/* Dark Footer */}
      <footer className="bg-[#0B0D10] py-14 text-slate-300">
        <div className="mx-auto grid max-w-6xl gap-10 px-4 sm:grid-cols-2 sm:px-6 lg:grid-cols-4">
          <div>
            <div className="flex items-center gap-2.5">
              <img
                src="/logo.png"
                alt="Institutional EA Logo"
                className="h-8 w-8 rounded-lg bg-black object-contain p-0.5 ring-1 ring-white/15"
              />
              <span className="text-base font-bold text-white">Institutional EA</span>
            </div>
            <p className="mt-3 text-xs leading-relaxed text-slate-400">
              Institutional-grade Smart Money Concepts companion for MetaTrader 5 with cross-platform
              read-only mobile monitoring.
            </p>
          </div>

          <div>
            <h4 className="text-xs font-bold uppercase tracking-wider text-white">Quick Links</h4>
            <ul className="mt-3 space-y-2 text-sm text-slate-400">
              <li>
                <a href="#how-it-works" className="hover:text-emerald-400">
                  How it works
                </a>
              </li>
              <li>
                <a href="#platforms" className="hover:text-emerald-400">
                  System requirements
                </a>
              </li>
              <li>
                <a href="#security" className="hover:text-emerald-400">
                  Read-only security
                </a>
              </li>
            </ul>
          </div>

          <div>
            <h4 className="text-xs font-bold uppercase tracking-wider text-white">About</h4>
            <ul className="mt-3 space-y-2 text-sm text-slate-400">
              <li>
                <a href={SITE_LINKS.releases} target="_blank" rel="noreferrer" className="hover:text-emerald-400">
                  Release Notes & SHA-256
                </a>
              </li>
              <li>
                <a href={SITE_LINKS.issues} target="_blank" rel="noreferrer" className="hover:text-emerald-400">
                  Report an Issue
                </a>
              </li>
            </ul>
          </div>

          <div>
            <h4 className="text-xs font-bold uppercase tracking-wider text-white">Contact</h4>
            <div className="mt-3 flex items-center gap-3">
              <a
                href={SITE_LINKS.github}
                target="_blank"
                rel="noreferrer"
                aria-label="GitHub Repository"
                className="flex h-9 w-9 items-center justify-center rounded-full bg-white/10 text-white hover:bg-emerald-600"
              >
                <Globe className="h-4 w-4" />
              </a>
              <a
                href={`mailto:${SITE_LINKS.contactEmail}`}
                aria-label="Email Support"
                className="flex h-9 w-9 items-center justify-center rounded-full bg-white/10 text-white hover:bg-emerald-600"
              >
                <Mail className="h-4 w-4" />
              </a>
            </div>
            <p className="mt-3 text-xs text-slate-500">{SITE_LINKS.contactEmail}</p>
          </div>
        </div>

        <div className="mx-auto mt-10 max-w-6xl border-t border-white/10 px-4 pt-6 text-center text-xs text-slate-500 sm:px-6">
          © {new Date().getFullYear()} Institutional EA. All rights reserved.
        </div>
      </footer>
    </div>
  );
}
