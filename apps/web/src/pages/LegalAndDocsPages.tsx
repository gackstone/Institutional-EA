import React from "react";
import { BookOpen, FileText, Mail, ShieldAlert } from "lucide-react";
import { SITE_LINKS } from "../config/downloads.config";
import { Link } from "../lib/router";

const DocShell: React.FC<{
  badge: string;
  title: string;
  subtitle: string;
  children: React.ReactNode;
}> = ({ badge, title, subtitle, children }) => (
  <div className="mx-auto max-w-4xl px-4 py-14 sm:px-6 lg:px-8">
    <div className="border-b border-white/[0.08] pb-6">
      <div className="font-mono text-xs font-semibold uppercase tracking-widest text-[#3B82F6]">
        {badge}
      </div>
      <h1 className="mt-2 text-3xl font-bold text-white">{title}</h1>
      <p className="mt-2 text-sm text-[#9CA3AF]">{subtitle}</p>
    </div>
    <div className="mt-8 space-y-6 text-sm leading-relaxed text-[#D1D5DB]">{children}</div>
  </div>
);

export const DocsPage: React.FC = () => (
  <DocShell
    badge="Documentation"
    title="Institutional EA Platform Documentation"
    subtitle="Architecture, Windows Companion installation, MetaTrader 5 bridge setup, and cloud account synchronization."
  >
    <section className="rounded-xl border border-white/[0.08] bg-[#111216] p-6">
      <div className="flex items-center gap-2 text-base font-bold text-white">
        <BookOpen className="h-4 w-4 text-[#3B82F6]" />
        1. End-to-End Architecture
      </div>
      <p className="mt-3 text-xs text-[#9CA3AF]">
        MetaTrader 5 → PythonBridgeEA.mq5 (TCP 5555/5556) → Python Algorithmic Engine → Local
        Control Service (127.0.0.1:8765 + SQLite WAL) → Windows Companion Application.
      </p>
      <p className="mt-2 text-xs text-[#D1D5DB]">
        All trade analysis, order validation, and risk enforcement occur locally on your Windows
        machine or VPS. Supabase handles user authentication, subscription records, manual Binance
        USDT (TRC20) payment submissions, and registered device tracking.
      </p>
    </section>

    <section className="rounded-xl border border-white/[0.08] bg-[#111216] p-6">
      <h2 className="text-base font-bold text-white">2. Windows Companion Setup</h2>
      <ol className="mt-3 list-decimal space-y-2 pl-5 text-xs text-[#D1D5DB]">
        <li>Install MetaTrader 5 (64-bit) on Windows 10/11 and enable Algo Trading.</li>
        <li>Download and install the Windows Companion App from the official Releases page.</li>
        <li>Sign in using your Institutional EA account via the integrated secure browser sign-in.</li>
        <li>Use the MT5 Terminal screen inside the Companion App to deploy and compile <code className="font-mono text-white">PythonBridgeEA.mq5</code>.</li>
        <li>Verify DEMO safety lock status before starting the local engine.</li>
      </ol>
    </section>

    <section className="rounded-xl border border-white/[0.08] bg-[#111216] p-6">
      <h2 className="text-base font-bold text-white">3. Offline Operation & Safety Guarantee</h2>
      <p className="mt-2 text-xs text-[#D1D5DB]">
        The Windows Companion App caches your verified subscription entitlement using OS-backed
        Windows DPAPI encryption for up to 72 hours during internet outages. Local emergency
        controls (Pause, Stop, Close All, Emergency Kill Switch) and open MT5 position monitoring
        remain accessible at all times regardless of subscription or network state.
      </p>
    </section>
  </DocShell>
);

export const TermsOfServicePage: React.FC = () => (
  <DocShell
    badge="Legal"
    title="Terms of Service"
    subtitle="Effective Date: November 2026 · Institutional EA Software & Subscription Terms"
  >
    <section className="space-y-3">
      <h2 className="text-base font-bold text-white">1. Software License & Scope</h2>
      <p>
        Institutional EA provides algorithmic trading software tooling, a local MetaTrader 5
        Companion Application, and cloud account management services. Institutional EA is a
        software provider—not a broker, financial advisor, portfolio manager, or investment firm.
      </p>
    </section>
    <section className="space-y-3">
      <h2 className="text-base font-bold text-white">2. Subscriptions & Binance USDT Payments</h2>
      <p>
        The Institutional EA Pro subscription is billed monthly at $50 USD (50 USDT via Binance
        TRON TRC20). Subscriptions are activated only after an authorized administrator verifies
        the submitted on-chain transaction reference. Because cryptocurrency transfers on TRON
        (TRC20) are irreversible, users are solely responsible for verifying the network and
        deposit address prior to transfer.
      </p>
    </section>
    <section className="space-y-3">
      <h2 className="text-base font-bold text-white">3. User Responsibility & Account Security</h2>
      <p>
        You are solely responsible for configuring your MetaTrader 5 terminal, verifying DEMO vs.
        LIVE broker accounts, safeguarding your account credentials, and supervising automated
        trading operations. Account sharing beyond the server-enforced active device limit is
        prohibited.
      </p>
    </section>
  </DocShell>
);

export const PrivacyPolicyPage: React.FC = () => (
  <DocShell
    badge="Legal"
    title="Privacy Policy"
    subtitle="How Institutional EA collects, secures, and minimizes account and device data."
  >
    <section className="space-y-3">
      <h2 className="text-base font-bold text-white">1. Data We Collect</h2>
      <p>
        We collect only the information required to operate your account and verify subscriptions:
        your name, email address, subscription lifecycle timestamps, submitted Binance USDT
        transaction references (and optional payment receipts), and a privacy-conscious SHA-256
        hashed device fingerprint for registered Windows Companion installations.
      </p>
    </section>
    <section className="space-y-3">
      <h2 className="text-base font-bold text-white">2. Data We Never Collect</h2>
      <p>
        Institutional EA never requests or stores your MetaTrader 5 broker password, Binance
        account password, exchange API withdrawal keys, or cryptocurrency wallet private keys or
        seed phrases.
      </p>
    </section>
    <section className="space-y-3">
      <h2 className="text-base font-bold text-white">3. Security Controls</h2>
      <p>
        Cloud records are stored in Supabase PostgreSQL with Row Level Security (RLS) enabled on
        every table. Desktop authentication tokens are encrypted using Windows OS-backed secure
        storage (DPAPI) and are never written in plaintext to SQLite, localStorage, or log files.
      </p>
    </section>
  </DocShell>
);

export const RiskDisclosurePage: React.FC = () => (
  <DocShell
    badge="Risk Disclosure"
    title="High-Risk Investment & Algorithmic Trading Disclosure"
    subtitle="Mandatory risk notice for all users of MetaTrader 5 automated trading systems."
  >
    <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-5 text-amber-100">
      <div className="flex items-center gap-2 font-bold text-amber-300">
        <ShieldAlert className="h-5 w-5" />
        Important Financial Risk Notice
      </div>
      <p className="mt-2 text-xs leading-relaxed">
        Trading foreign exchange (Forex), spot metals (XAUUSD), cryptocurrencies (BTCUSD), and
        Contracts for Difference (CFDs) on margin carries a high level of risk and may not be
        suitable for all investors. Leverage can amplify both gains and losses, and you may lose
        more than your initial deposit depending on your broker terms.
      </p>
    </div>
    <p>
      Past performance, historical backtests, walk-forward simulations, or DEMO account results are
      not indicative of future live trading results. No algorithm, indicator, or software system
      can guarantee profits or eliminate the risk of financial loss.
    </p>
    <p>
      Always validate strategies thoroughly in DEMO mode before considering any live capital
      deployment. Never trade with borrowed funds or capital you cannot afford to lose.
    </p>
  </DocShell>
);

export const ContactPage: React.FC = () => (
  <DocShell
    badge="Support & Contact"
    title="Contact Institutional EA"
    subtitle="Technical support, subscription verification inquiries, and security disclosures."
  >
    <div className="grid gap-4 sm:grid-cols-2">
      <div className="rounded-xl border border-white/[0.08] bg-[#111216] p-6">
        <Mail className="h-5 w-5 text-[#3B82F6]" />
        <h2 className="mt-3 text-base font-bold text-white">Support & Billing</h2>
        <p className="mt-2 text-xs text-[#9CA3AF]">
          For account, subscription verification, or Windows Companion technical support:
        </p>
        <a
          href={`mailto:${SITE_LINKS.contactEmail}`}
          className="mt-3 inline-block font-mono text-xs font-semibold text-[#3B82F6] hover:underline"
        >
          {SITE_LINKS.contactEmail}
        </a>
      </div>

      <div className="rounded-xl border border-white/[0.08] bg-[#111216] p-6">
        <FileText className="h-5 w-5 text-emerald-400" />
        <h2 className="mt-3 text-base font-bold text-white">Issue Tracker & Releases</h2>
        <p className="mt-2 text-xs text-[#9CA3AF]">
          Report Companion bugs or verify release checksums on the official repository:
        </p>
        <a
          href={SITE_LINKS.issues}
          target="_blank"
          rel="noreferrer"
          className="mt-3 inline-block font-mono text-xs font-semibold text-emerald-400 hover:underline"
        >
          {SITE_LINKS.github}
        </a>
      </div>
    </div>

    <div className="pt-2 text-xs text-[#9CA3AF]">
      Looking to manage your subscription or submit a payment? Visit{" "}
      <Link to="/account/subscription" className="text-[#3B82F6] hover:underline">
        Account & Subscription
      </Link>
      .
    </div>
  </DocShell>
);
