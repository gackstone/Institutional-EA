-- =============================================================================
-- Institutional EA — Row Level Security (RLS) & Storage Policies (Migration 002)
-- =============================================================================
-- Security Guarantees:
--   1. RLS enabled on ALL public tables.
--   2. Users can ONLY view/update their own permitted profile fields (never role).
--   3. Users can ONLY view their own subscriptions (never insert/update status/expiry).
--   4. Users can ONLY view their own payments and insert new 'submitted' payments
--      (never approve, reject, or alter submitted/approved payments).
--   5. Users can ONLY manage their own devices (subject to server-side 3-device limit).
--   6. Audit logs are strictly append-only; users can read own logs, admins read all.
--   7. Service-role / verified admin Edge Functions perform privileged mutations.
-- =============================================================================

-- Helper: check if current authenticated user is a verified admin
CREATE OR REPLACE FUNCTION public.is_admin()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM public.profiles
    WHERE id = auth.uid()
      AND role = 'admin'
  );
$$;

-- Prevent non-service-role users from escalating their own role in profiles
CREATE OR REPLACE FUNCTION public.prevent_profile_role_escalation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.role IS DISTINCT FROM OLD.role AND current_setting('role', true) <> 'service_role' THEN
    RAISE EXCEPTION 'Forbidden: profile role can only be modified by a trusted server-side administrator.';
  END IF;
  IF NEW.email IS DISTINCT FROM OLD.email AND current_setting('role', true) <> 'service_role' THEN
    RAISE EXCEPTION 'Forbidden: profile email must be updated through Supabase Auth.';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_profiles_prevent_role_escalation ON public.profiles;
CREATE TRIGGER trg_profiles_prevent_role_escalation
  BEFORE UPDATE ON public.profiles
  FOR EACH ROW
  EXECUTE FUNCTION public.prevent_profile_role_escalation();

-- -----------------------------------------------------------------------------
-- Enable RLS on all tables
-- -----------------------------------------------------------------------------
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY;

-- -----------------------------------------------------------------------------
-- 1. profiles policies
-- -----------------------------------------------------------------------------
DROP POLICY IF EXISTS "profiles_select_own_or_admin" ON public.profiles;
CREATE POLICY "profiles_select_own_or_admin"
  ON public.profiles
  FOR SELECT
  USING (auth.uid() = id OR public.is_admin());

DROP POLICY IF EXISTS "profiles_update_own_safe_fields" ON public.profiles;
CREATE POLICY "profiles_update_own_safe_fields"
  ON public.profiles
  FOR UPDATE
  USING (auth.uid() = id)
  WITH CHECK (
    auth.uid() = id
    AND role = (SELECT p.role FROM public.profiles p WHERE p.id = auth.uid())
  );

-- -----------------------------------------------------------------------------
-- 2. plans policies
-- -----------------------------------------------------------------------------
DROP POLICY IF EXISTS "plans_select_active_public" ON public.plans;
CREATE POLICY "plans_select_active_public"
  ON public.plans
  FOR SELECT
  USING (is_active = true OR public.is_admin());

-- -----------------------------------------------------------------------------
-- 3. subscriptions policies
-- -----------------------------------------------------------------------------
DROP POLICY IF EXISTS "subscriptions_select_own_or_admin" ON public.subscriptions;
CREATE POLICY "subscriptions_select_own_or_admin"
  ON public.subscriptions
  FOR SELECT
  USING (auth.uid() = user_id OR public.is_admin());

-- Intentionally NO INSERT / UPDATE / DELETE policies for authenticated users on subscriptions.
-- Only service_role (Edge Functions) or DB triggers can create/update subscriptions.

-- -----------------------------------------------------------------------------
-- 4. payments policies
-- -----------------------------------------------------------------------------
DROP POLICY IF EXISTS "payments_select_own_or_admin" ON public.payments;
CREATE POLICY "payments_select_own_or_admin"
  ON public.payments
  FOR SELECT
  USING (auth.uid() = user_id OR public.is_admin());

DROP POLICY IF EXISTS "payments_insert_own_submitted_only" ON public.payments;
CREATE POLICY "payments_insert_own_submitted_only"
  ON public.payments
  FOR INSERT
  WITH CHECK (
    auth.uid() = user_id
    AND status = 'submitted'
    AND reviewed_by IS NULL
    AND reviewed_at IS NULL
    AND activation_applied = false
  );

-- Intentionally NO UPDATE or DELETE policies for ordinary users on payments.
-- Users cannot approve their own payments or modify submitted/approved records.

-- -----------------------------------------------------------------------------
-- 5. devices policies
-- -----------------------------------------------------------------------------
DROP POLICY IF EXISTS "devices_select_own_or_admin" ON public.devices;
CREATE POLICY "devices_select_own_or_admin"
  ON public.devices
  FOR SELECT
  USING (auth.uid() = user_id OR public.is_admin());

DROP POLICY IF EXISTS "devices_insert_own" ON public.devices;
CREATE POLICY "devices_insert_own"
  ON public.devices
  FOR INSERT
  WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "devices_update_own_or_admin" ON public.devices;
CREATE POLICY "devices_update_own_or_admin"
  ON public.devices
  FOR UPDATE
  USING (auth.uid() = user_id OR public.is_admin())
  WITH CHECK (auth.uid() = user_id OR public.is_admin());

-- -----------------------------------------------------------------------------
-- 6. audit_logs policies (Strictly Append-Only)
-- -----------------------------------------------------------------------------
DROP POLICY IF EXISTS "audit_logs_select_own_or_admin" ON public.audit_logs;
CREATE POLICY "audit_logs_select_own_or_admin"
  ON public.audit_logs
  FOR SELECT
  USING (auth.uid() = user_id OR public.is_admin());

-- Intentionally NO INSERT / UPDATE / DELETE policies for ordinary users on audit_logs.

-- -----------------------------------------------------------------------------
-- 7. Supabase Storage: Private Payment Proofs Bucket
-- -----------------------------------------------------------------------------
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'payment-proofs',
  'payment-proofs',
  false,
  5242880,
  ARRAY['image/jpeg', 'image/png', 'image/webp', 'application/pdf']
)
ON CONFLICT (id) DO NOTHING;

DROP POLICY IF EXISTS "payment_proofs_upload_own_folder" ON storage.objects;
CREATE POLICY "payment_proofs_upload_own_folder"
  ON storage.objects
  FOR INSERT
  TO authenticated
  WITH CHECK (
    bucket_id = 'payment-proofs'
    AND (storage.foldername(name))[1] = auth.uid()::text
  );

DROP POLICY IF EXISTS "payment_proofs_read_own_or_admin" ON storage.objects;
CREATE POLICY "payment_proofs_read_own_or_admin"
  ON storage.objects
  FOR SELECT
  TO authenticated
  USING (
    bucket_id = 'payment-proofs'
    AND ((storage.foldername(name))[1] = auth.uid()::text OR public.is_admin())
  );
