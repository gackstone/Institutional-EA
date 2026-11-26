-- Institutional EA: Cross-Network Cloud-Mediated Mobile Pairing & Read-Only Sync
-- Enables Windows Companion <-> Secure Cloud Relay <-> Android Read-Only App
-- across any network (Wi-Fi, 4G/5G, Ethernet, dynamic public IPs, different locations).

CREATE TABLE IF NOT EXISTS public.mobile_pairing_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  companion_device_id TEXT NOT NULL,
  companion_name TEXT NOT NULL DEFAULT 'Windows Companion',
  code_hash TEXT NOT NULL,
  session_token_hash TEXT NOT NULL,
  claim_nonce_hash TEXT,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'awaiting_approval', 'approved', 'rejected', 'expired', 'cancelled')),
  pending_android_name TEXT,
  pending_android_platform TEXT DEFAULT 'android',
  pending_android_fingerprint TEXT,
  approved_device_id UUID,
  issued_token_once TEXT, -- cleared immediately upon first poll retrieval
  attempt_count INTEGER NOT NULL DEFAULT 0,
  expires_at TIMESTAMPTZ NOT NULL,
  consumed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mobile_pairing_sessions_user ON public.mobile_pairing_sessions(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_mobile_pairing_sessions_code_hash ON public.mobile_pairing_sessions(code_hash) WHERE status IN ('pending', 'awaiting_approval');

CREATE TABLE IF NOT EXISTS public.mobile_paired_devices (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  companion_device_id TEXT NOT NULL,
  companion_name TEXT NOT NULL DEFAULT 'Windows Companion',
  device_name TEXT NOT NULL,
  platform TEXT NOT NULL DEFAULT 'android',
  device_fingerprint_hash TEXT,
  token_hash TEXT NOT NULL UNIQUE,
  scope TEXT NOT NULL DEFAULT 'read_only' CHECK (scope = 'read_only'),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked')),
  token_rotated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  token_expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + INTERVAL '90 days'),
  paired_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  revoked_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_mobile_paired_devices_user ON public.mobile_paired_devices(user_id, status);

CREATE TABLE IF NOT EXISTS public.companion_telemetry_snapshots (
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  companion_device_id TEXT NOT NULL,
  companion_name TEXT NOT NULL DEFAULT 'Windows Companion',
  sequence_no BIGINT NOT NULL DEFAULT 0,
  status_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  account_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  stats_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  positions_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  orders_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  trades_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  signals_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  symbols_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, companion_device_id)
);

-- Strict Row-Level Security
ALTER TABLE public.mobile_pairing_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mobile_paired_devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.companion_telemetry_snapshots ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users manage own mobile pairing sessions" ON public.mobile_pairing_sessions;
CREATE POLICY "Users manage own mobile pairing sessions"
  ON public.mobile_pairing_sessions
  FOR ALL
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users manage own paired mobile devices" ON public.mobile_paired_devices;
CREATE POLICY "Users manage own paired mobile devices"
  ON public.mobile_paired_devices
  FOR ALL
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users read own telemetry snapshots" ON public.companion_telemetry_snapshots;
CREATE POLICY "Users read own telemetry snapshots"
  ON public.companion_telemetry_snapshots
  FOR SELECT
  USING (auth.uid() = user_id);
