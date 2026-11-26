import React from "react";
import { ArrowRight, CheckCircle2, Clock, ShieldCheck, Wallet } from "lucide-react";
import {
  BINANCE_USDT_TRC20_CONFIG,
  INSTITUTIONAL_EA_PRO_PLAN,
  PRO_PLAN_BENEFITS,
} from "@institutional-ea/cloud-contract";
import { Link } from "../lib/router";
import { useAuth } from "../context/AuthContext";

const LIFECYCLE_STEPS = [
  { label: "1. Create Account", desc: "Register and verify your email address." },
  { label: "2. Send 50 USDT (TRC20)", desc: "Transfer via Binance TRON (TRC20) using the verified deposit address." },
  { label: "3. Submit TXID", desc: "Submit your transaction reference and optional receipt for review." },
  { label: "4. Admin Verification", desc: "An authorized administrator verifies the deposit and activates 30 days UTC." },
];

export const PricingPage: React.FC = () => {
  const { session } = useAuth();
  const subscribeTarget = session ? "/account/subscription" : "/auth/sign-up?next=/account/subscription";

  return (
    <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-3xl text-center">
        <div className="font-mono text-xs font-semibold uppercase tracking-widest text-[#3B82F6]">
          Transparent Institutional Pricing
        </div>
        <h1 className="mt-3 text-3xl font-extrabold tracking-tight text-white sm:text-4xl">
          One Complete Plan. Zero Hidden Tiers.
        </h1>
        <p className="mt-4 text-sm leading-relaxed text-[#9CA3AF] sm:text-base">
          Full access to the Institutional EA Windows Companion Application, MT5 integration
          tooling, quantitative risk interface, and cloud account synchronization.
        </p>
      </div>

      {/* Main Plan Card */}
      <div className="mx-auto mt-12 max-w-3xl rounded-2xl border border-blue-500/30 bg-[#111216] p-8 shadow-2xl sm:p-10">
        <div className="flex flex-col justify-between gap-6 border-b border-white/[0.08] pb-8 sm:flex-row sm:items-end">
          <div>
            <span className="inline-flex items-center gap-1.5 rounded-full border border-blue-500/30 bg-blue-500/10 px-3 py-1 text-xs font-semibold text-blue-300">
              Monthly Subscription
            </span>
            <h2 className="mt-3 text-2xl font-bold text-white">
              {INSTITUTIONAL_EA_PRO_PLAN.name}
            </h2>
            <p className="mt-2 max-w-md text-sm text-[#9CA3AF]">
              {INSTITUTIONAL_EA_PRO_PLAN.description}
            </p>
          </div>
          <div className="sm:text-right">
            <div className="flex items-baseline gap-1 sm:justify-end">
              <span className="font-mono text-5xl font-extrabold text-white">
                ${INSTITUTIONAL_EA_PRO_PLAN.price}
              </span>
              <span className="text-sm font-medium text-[#9CA3AF]">USD / month</span>
            </div>
            <div className="mt-1.5 font-mono text-xs text-emerald-400">
              Payable via {BINANCE_USDT_TRC20_CONFIG.provider} · {BINANCE_USDT_TRC20_CONFIG.amountUsdt}{" "}
              {BINANCE_USDT_TRC20_CONFIG.asset} ({BINANCE_USDT_TRC20_CONFIG.network})
            </div>
          </div>
        </div>

        <div className="mt-8">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-[#9CA3AF]">
            Verified Capabilities Included
          </h3>
          <ul className="mt-4 grid gap-3 sm:grid-cols-2">
            {PRO_PLAN_BENEFITS.map((benefit) => (
              <li key={benefit} className="flex items-start gap-2.5 text-sm text-[#E5E7EB]">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
                <span>{benefit}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="mt-8 flex flex-col gap-3 border-t border-white/[0.08] pt-8 sm:flex-row sm:items-center sm:justify-between">
          <Link
            to={subscribeTarget}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-[#3B82F6] px-6 py-3.5 text-sm font-semibold text-white transition hover:bg-[#2563EB]"
          >
            {session ? "Subscribe / Manage Billing" : "Get Started & Subscribe"}
            <ArrowRight className="h-4 w-4" />
          </Link>
          <div className="flex items-center gap-2 text-xs text-[#9CA3AF]">
            <ShieldCheck className="h-4 w-4 text-emerald-400" />
            Manual administrator verification · UTC billing window
          </div>
        </div>
      </div>

      {/* Payment & Activation Workflow */}
      <div className="mx-auto mt-14 max-w-5xl">
        <h2 className="text-center text-lg font-bold text-white">
          How Binance USDT (TRC20) Activation Works
        </h2>
        <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {LIFECYCLE_STEPS.map((s) => (
            <div
              key={s.label}
              className="rounded-xl border border-white/[0.07] bg-[#111216] p-5"
            >
              <div className="text-sm font-semibold text-white">{s.label}</div>
              <p className="mt-2 text-xs leading-relaxed text-[#9CA3AF]">{s.desc}</p>
            </div>
          ))}
        </div>

        <div className="mt-8 grid gap-4 md:grid-cols-2">
          <div className="rounded-xl border border-white/[0.07] bg-[#111216] p-5">
            <div className="flex items-center gap-2 text-sm font-semibold text-white">
              <Wallet className="h-4 w-4 text-[#3B82F6]" />
              Zero Exchange Credentials Required
            </div>
            <p className="mt-2 text-xs leading-relaxed text-[#9CA3AF]">
              Institutional EA never requests Binance passwords, API keys, withdrawal permissions,
              or wallet seed phrases. You transfer 50 USDT directly to our published TRC20 deposit
              address and submit the TXID for verification.
            </p>
          </div>
          <div className="rounded-xl border border-white/[0.07] bg-[#111216] p-5">
            <div className="flex items-center gap-2 text-sm font-semibold text-white">
              <Clock className="h-4 w-4 text-emerald-400" />
              Trading Safety Independence
            </div>
            <p className="mt-2 text-xs leading-relaxed text-[#9CA3AF]">
              Subscription status is completely isolated from MT5 trading execution. If a
              subscription expires, Institutional EA will never automatically close open positions,
              alter your stop losses, or lock you out of local emergency controls.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
