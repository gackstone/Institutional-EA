-- Institutional EA: Sync Contract v1.1.0 Cloud Telemetry Extension
-- Additive, backwards-compatible migration adding multi-timeframe candles,
-- SMC chart drawings/overlays, equity curve snapshots, and sync metadata
-- to public.companion_telemetry_snapshots.
-- Preserves strict read-only enforcement (CHECK (scope = 'read_only')) and RLS.

ALTER TABLE public.companion_telemetry_snapshots
  ADD COLUMN IF NOT EXISTS meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS candles_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS drawings_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS equity_json JSONB NOT NULL DEFAULT '[]'::jsonb;
