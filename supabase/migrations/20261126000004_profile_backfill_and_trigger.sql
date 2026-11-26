-- =============================================================================
-- Institutional EA — Profile Backfill & Sign-Up Trigger Repair (Migration 004)
-- =============================================================================
-- Additive, idempotent migration:
--   1. Backfills a default 'user' profile row for any existing auth.users row
--      that was created before migration 001 was applied (ON CONFLICT DO NOTHING).
--   2. Ensures public.handle_new_auth_user() (SECURITY DEFINER, SET search_path = public)
--      and trigger on_auth_user_created on auth.users are active and idempotent.
--   3. Preserves RLS and never grants admin roles or subscription entitlements.
-- =============================================================================

-- 1. Idempotent backfill for any auth.users missing a public.profiles row
INSERT INTO public.profiles (id, full_name, email, role, created_at)
SELECT
  u.id,
  COALESCE(
    NULLIF(trim(u.raw_user_meta_data ->> 'full_name'), ''),
    split_part(COALESCE(u.email, ''), '@', 1)
  ) AS full_name,
  lower(u.email) AS email,
  'user' AS role,
  COALESCE(u.created_at, timezone('utc', now())) AS created_at
FROM auth.users u
LEFT JOIN public.profiles p ON p.id = u.id
WHERE p.id IS NULL
  AND u.email IS NOT NULL
ON CONFLICT (id) DO NOTHING;

-- 2. Ensure sign-up trigger function is SECURITY DEFINER with safe search_path
CREATE OR REPLACE FUNCTION public.handle_new_auth_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF NEW.email IS NOT NULL THEN
    INSERT INTO public.profiles (id, full_name, email, role)
    VALUES (
      NEW.id,
      COALESCE(NULLIF(trim(NEW.raw_user_meta_data ->> 'full_name'), ''), split_part(NEW.email, '@', 1)),
      lower(NEW.email),
      'user'
    )
    ON CONFLICT (id) DO NOTHING;
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW
  EXECUTE FUNCTION public.handle_new_auth_user();

-- 3. Keep Row Level Security strictly enabled
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
