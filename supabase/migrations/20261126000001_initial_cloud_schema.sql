-- =============================================================================
-- Institutional EA — Cloud Backend Initial Schema (Migration 001)
-- =============================================================================
-- Preserves local SQLite database for MT5 trading operations & companion logs.
-- Supabase PostgreSQL is strictly the authoritative cloud store for:
--   - User profiles & roles
--   - Subscription plans & lifecycle records (UTC timestamps)
--   - Manual Binance USDT (TRON / TRC20) payment submissions & verification
--   - Registered desktop devices (privacy-conscious SHA-256 fingerprint hashes)
--   - Immutable security & payment audit logs
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- -----------------------------------------------------------------------------
-- 1. Helper Trigger Function: updated_at UTC timestamp
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.set_updated_at_utc()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at := timezone('utc', now());
  RETURN NEW;
END;
$$;

-- -----------------------------------------------------------------------------
-- 2. Profiles Table (references auth.users)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.profiles (
  id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  full_name text NOT NULL DEFAULT '',
  email text NOT NULL UNIQUE,
  role text NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE INDEX IF NOT EXISTS idx_profiles_role ON public.profiles(role);
CREATE INDEX IF NOT EXISTS idx_profiles_email ON public.profiles(lower(email));

DROP TRIGGER IF EXISTS trg_profiles_updated_at ON public.profiles;
CREATE TRIGGER trg_profiles_updated_at
  BEFORE UPDATE ON public.profiles
  FOR EACH ROW
  EXECUTE FUNCTION public.set_updated_at_utc();

-- Automatically provision a 'user' profile when a new auth.users account is created.
-- Role is ALWAYS hardcoded to 'user' here; admin roles must be granted server-side.
CREATE OR REPLACE FUNCTION public.handle_new_auth_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  INSERT INTO public.profiles (id, full_name, email, role)
  VALUES (
    NEW.id,
    COALESCE(NULLIF(trim(NEW.raw_user_meta_data ->> 'full_name'), ''), split_part(NEW.email, '@', 1)),
    lower(NEW.email),
    'user'
  )
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW
  EXECUTE FUNCTION public.handle_new_auth_user();

-- -----------------------------------------------------------------------------
-- 3. Plans Table
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.plans (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug text NOT NULL UNIQUE,
  name text NOT NULL,
  price numeric(12, 2) NOT NULL CHECK (price > 0),
  currency text NOT NULL DEFAULT 'USD' CHECK (currency IN ('USD', 'USDT')),
  billing_interval text NOT NULL DEFAULT 'monthly' CHECK (billing_interval IN ('monthly')),
  duration_days integer NOT NULL DEFAULT 30 CHECK (duration_days > 0),
  description text NOT NULL DEFAULT '',
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

DROP TRIGGER IF EXISTS trg_plans_updated_at ON public.plans;
CREATE TRIGGER trg_plans_updated_at
  BEFORE UPDATE ON public.plans
  FOR EACH ROW
  EXECUTE FUNCTION public.set_updated_at_utc();

-- Seed Institutional EA Pro ($50 USD / month)
INSERT INTO public.plans (id, slug, name, price, currency, billing_interval, duration_days, description, is_active)
VALUES (
  '00000000-0000-4000-8000-000000000001',
  'institutional-ea-pro-monthly',
  'Institutional EA Pro',
  50.00,
  'USD',
  'monthly',
  30,
  'Full access to the Institutional EA Windows Companion Application, secure cloud account synchronization, MT5 Companion connectivity, trading analytics, configuration management, risk interface, and ongoing updates.',
  true
)
ON CONFLICT (id) DO UPDATE SET
  name = EXCLUDED.name,
  price = EXCLUDED.price,
  currency = EXCLUDED.currency,
  billing_interval = EXCLUDED.billing_interval,
  duration_days = EXCLUDED.duration_days,
  description = EXCLUDED.description,
  is_active = EXCLUDED.is_active;

-- -----------------------------------------------------------------------------
-- 4. Subscriptions Table
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.subscriptions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  plan_id uuid NOT NULL REFERENCES public.plans(id) ON DELETE RESTRICT,
  status text NOT NULL DEFAULT 'no_subscription' CHECK (
    status IN (
      'no_subscription',
      'pending_payment',
      'payment_under_review',
      'active',
      'expired',
      'cancelled',
      'suspended',
      'payment_rejected'
    )
  ),
  amount numeric(12, 2) NOT NULL CHECK (amount >= 0),
  currency text NOT NULL DEFAULT 'USD' CHECK (currency IN ('USD', 'USDT')),
  billing_interval text NOT NULL DEFAULT 'monthly' CHECK (billing_interval IN ('monthly')),
  started_at timestamptz,
  expires_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT chk_subscriptions_dates CHECK (
    expires_at IS NULL OR started_at IS NULL OR expires_at >= started_at
  )
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON public.subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON public.subscriptions(status);
CREATE INDEX IF NOT EXISTS idx_subscriptions_expires_at ON public.subscriptions(expires_at);

DROP TRIGGER IF EXISTS trg_subscriptions_updated_at ON public.subscriptions;
CREATE TRIGGER trg_subscriptions_updated_at
  BEFORE UPDATE ON public.subscriptions
  FOR EACH ROW
  EXECUTE FUNCTION public.set_updated_at_utc();

-- -----------------------------------------------------------------------------
-- 5. Payments Table (Manual Binance USDT TRC20 + Future Automated Verification)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.payments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  subscription_id uuid REFERENCES public.subscriptions(id) ON DELETE SET NULL,
  provider text NOT NULL DEFAULT 'Binance' CHECK (provider IN ('Binance')),
  network text NOT NULL DEFAULT 'TRON (TRC20)' CHECK (network IN ('TRON (TRC20)')),
  asset text NOT NULL DEFAULT 'USDT' CHECK (asset IN ('USDT')),
  amount numeric(12, 2) NOT NULL CHECK (amount >= 50.00),
  transaction_reference text NOT NULL CHECK (char_length(trim(transaction_reference)) >= 16 AND char_length(trim(transaction_reference)) <= 128),
  payment_date timestamptz NOT NULL DEFAULT timezone('utc', now()),
  proof_file_path text,
  status text NOT NULL DEFAULT 'submitted' CHECK (
    status IN ('pending', 'submitted', 'under_review', 'approved', 'rejected')
  ),
  submitted_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  reviewed_at timestamptz,
  reviewed_by uuid REFERENCES public.profiles(id) ON DELETE SET NULL,
  rejection_reason text,
  activation_applied boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

-- Prevent duplicate TXID submissions across non-rejected payments (ensures each TXID activates once)
CREATE UNIQUE INDEX IF NOT EXISTS uq_payments_tx_ref_active
  ON public.payments (lower(trim(transaction_reference)))
  WHERE status IN ('pending', 'submitted', 'under_review', 'approved');

CREATE INDEX IF NOT EXISTS idx_payments_user_id ON public.payments(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_status ON public.payments(status);
CREATE INDEX IF NOT EXISTS idx_payments_submitted_at ON public.payments(submitted_at DESC);

DROP TRIGGER IF EXISTS trg_payments_updated_at ON public.payments;
CREATE TRIGGER trg_payments_updated_at
  BEFORE UPDATE ON public.payments
  FOR EACH ROW
  EXECUTE FUNCTION public.set_updated_at_utc();

-- Enforce that client-inserted payments ALWAYS start as 'submitted' without review metadata
-- and automatically transition or create the user's subscription into 'payment_under_review'.
CREATE OR REPLACE FUNCTION public.enforce_payment_submission_invariants()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_sub_id uuid;
  v_plan public.plans%ROWTYPE;
BEGIN
  NEW.transaction_reference := trim(NEW.transaction_reference);
  NEW.status := 'submitted';
  NEW.reviewed_at := NULL;
  NEW.reviewed_by := NULL;
  NEW.rejection_reason := NULL;
  NEW.activation_applied := false;
  NEW.submitted_at := timezone('utc', now());

  IF NEW.subscription_id IS NULL THEN
    SELECT * INTO v_plan FROM public.plans WHERE id = '00000000-0000-4000-8000-000000000001' LIMIT 1;

    SELECT id INTO v_sub_id
    FROM public.subscriptions
    WHERE user_id = NEW.user_id
    ORDER BY created_at DESC
    LIMIT 1;

    IF v_sub_id IS NULL THEN
      INSERT INTO public.subscriptions (user_id, plan_id, status, amount, currency, billing_interval)
      VALUES (
        NEW.user_id,
        COALESCE(v_plan.id, '00000000-0000-4000-8000-000000000001'),
        'payment_under_review',
        COALESCE(v_plan.price, 50.00),
        COALESCE(v_plan.currency, 'USD'),
        COALESCE(v_plan.billing_interval, 'monthly')
      )
      RETURNING id INTO v_sub_id;
    ELSE
      UPDATE public.subscriptions
      SET status = CASE WHEN status = 'active' THEN 'active' ELSE 'payment_under_review' END
      WHERE id = v_sub_id;
    END IF;

    NEW.subscription_id := v_sub_id;
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_payments_enforce_submission ON public.payments;
CREATE TRIGGER trg_payments_enforce_submission
  BEFORE INSERT ON public.payments
  FOR EACH ROW
  EXECUTE FUNCTION public.enforce_payment_submission_invariants();

-- -----------------------------------------------------------------------------
-- 6. Devices Table (Privacy-Conscious Fingerprinting + Server-Side Limit)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.devices (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  device_name text NOT NULL CHECK (char_length(trim(device_name)) BETWEEN 1 AND 120),
  device_fingerprint_hash text NOT NULL CHECK (device_fingerprint_hash ~ '^[a-fA-F0-9]{64}$'),
  operating_system text NOT NULL DEFAULT 'Windows',
  app_version text NOT NULL DEFAULT '1.3.4',
  last_seen_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked')),
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  UNIQUE (user_id, device_fingerprint_hash)
);

CREATE INDEX IF NOT EXISTS idx_devices_user_status ON public.devices(user_id, status);

-- Enforce server-side active device limit (max 3 active devices per user)
CREATE OR REPLACE FUNCTION public.enforce_device_limit()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
  v_active_count integer;
BEGIN
  IF NEW.status = 'active' THEN
    SELECT count(*) INTO v_active_count
    FROM public.devices
    WHERE user_id = NEW.user_id
      AND status = 'active'
      AND id <> COALESCE(NEW.id, '00000000-0000-0000-0000-000000000000'::uuid);

    IF v_active_count >= 3 THEN
      RAISE EXCEPTION 'Device limit exceeded: maximum 3 active devices per account. Revoke an existing device first.';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_devices_limit ON public.devices;
CREATE TRIGGER trg_devices_limit
  BEFORE INSERT OR UPDATE OF status ON public.devices
  FOR EACH ROW
  EXECUTE FUNCTION public.enforce_device_limit();

-- -----------------------------------------------------------------------------
-- 7. Audit Logs Table (Immutable Append-Only)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.audit_logs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES public.profiles(id) ON DELETE SET NULL,
  actor_id uuid REFERENCES public.profiles(id) ON DELETE SET NULL,
  action text NOT NULL,
  resource_type text NOT NULL,
  resource_id text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON public.audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor_id ON public.audit_logs(actor_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON public.audit_logs(created_at DESC);
