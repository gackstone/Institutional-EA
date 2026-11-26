# Institutional EA — Public Website, Subscription, Binance USDT & Supabase Deployment Guide

## 1. Architecture Overview

Institutional EA maintains a strict architectural separation between **Local Trading Execution** and **Cloud Account / Subscription Management**:

```
MetaTrader 5 → PythonBridgeEA.mq5 (TCP 5555/5556) → Python Algorithmic Engine
                                                              ↓
                                              Local Control Service (127.0.0.1:8765 + SQLite WAL)
                                                              ↓
                                              Windows Companion Application (Electron + React)
                                                              ↕ (HTTPS, OS-Encrypted DPAPI Tokens)
                                              Supabase Cloud (Auth · PostgreSQL RLS · Storage · Edge Functions)
                                                              ↕
                                              Public Website & Admin Portal (apps/web — Vercel-ready)
```

### Non-Negotiable Safety & Preservation Invariants
- Local SQLite (`data/companion_control.db`) remains the authoritative local persistence store for companion operations, config versions, and audit logs.
- Subscription status **never** closes open MT5 positions, stops the trading engine, modifies trading configs, or locks out local emergency controls (`Pause`, `Stop`, `Close All`, `Emergency Kill Switch`).
- `SUPABASE_SERVICE_ROLE_KEY` is **never** bundled in `apps/web` or `companion` binaries.

---

## 2. Supabase Project Setup

### Step 1: Create a Supabase Project & Run Migrations
Using the Supabase CLI:
```bash
supabase link --project-ref <your-project-ref>
supabase db push
```
This applies:
1. `supabase/migrations/20261126000001_initial_cloud_schema.sql` — Creates `profiles`, `plans` (seeded with `Institutional EA Pro` at `$50.00 USD / monthly`), `subscriptions`, `payments` (with unique active TXID index), `devices` (with server-side 3-device limit trigger), and `audit_logs`.
2. `supabase/migrations/20261126000002_rls_and_storage.sql` — Enables Row Level Security on all 6 tables, prevents profile role self-escalation, restricts payment approval to server-side admins, and creates the private `payment-proofs` storage bucket.

### Step 2: Deploy Supabase Edge Functions
```bash
supabase functions deploy admin-review-payment
supabase functions deploy admin-manage-subscription
supabase functions deploy device-heartbeat
```
Supabase automatically injects `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` into the Edge Function runtime.

### Step 3: Configure Auth Redirect URLs
In **Supabase Dashboard → Authentication → URL Configuration**, add:
- Site URL: `https://your-institutional-ea-domain.com`
- Additional Redirect URLs:
  - `https://your-institutional-ea-domain.com/auth/callback`
  - `http://localhost:5173/auth/callback`
  - `institutionalea://auth/callback`

### Step 4: Promote an Administrator Account (Server-Side Only)
Run in the Supabase SQL Editor (using `postgres` / `service_role`):
```sql
UPDATE public.profiles
SET role = 'admin'
WHERE email = 'admin@yourdomain.com';
```
Ordinary users cannot assign themselves `admin` due to both the RLS `WITH CHECK` policy and the `prevent_profile_role_escalation` trigger.

---

## 3. Centralized Binance USDT (TRC20) Payment Configuration

Defined once in `packages/cloud-contract/src/index.ts`:
- **Plan**: Institutional EA Pro (`$50 USD / month`)
- **Provider**: Binance
- **Asset**: USDT
- **Network**: TRON (TRC20)
- **Deposit Address**: `TPP26iUrsJmstHVGh38rHYBipo6drZvj9D`
- **Official QR Asset**: `apps/web/public/assets/binance-usdt-trc20-qr.jpg` & `companion/public/assets/binance-usdt-trc20-qr.jpg`

### Verification Workflow
`Pending Payment → Submitted for Verification → Under Review → Approved / Rejected → Subscription Activated`
- Submissions never auto-activate subscriptions.
- Administrators review TXIDs at `/admin` and invoke `admin-review-payment` (idempotent; guarded by `activation_applied = false`).
- Approval activates or extends `subscriptions.expires_at` by 30 days in UTC and writes an immutable entry to `audit_logs`.

---

## 4. Environment Configuration

Copy `.env.example` to `.env` (never commit `.env`):
- **Public Website (`apps/web` / Vercel)**:
  - `VITE_SUPABASE_URL`
  - `VITE_SUPABASE_ANON_KEY`
  - `VITE_PUBLIC_SITE_URL`
- **Windows Companion App**:
  - `SUPABASE_URL`
  - `SUPABASE_ANON_KEY`
  - `INSTITUTIONAL_EA_WEB_URL`

---

## 5. Offline Entitlement Caching Policy (Windows Companion)

- Session tokens and entitlement snapshots are stored in `%LOCALAPPDATA%\InstitutionalEA\Institutional EA Companion\credentials\cloud_session.dpapi.bin` encrypted with Electron `safeStorage` (Windows DPAPI).
- When offline, a previously verified active subscription remains valid for up to **72 hours** provided `expires_at` (UTC) has not passed (`OFFLINE (72H GRACE)`).
- After 72 hours without re-verification, status transitions to `VERIFICATION UNAVAILABLE` rather than assuming active indefinitely.
