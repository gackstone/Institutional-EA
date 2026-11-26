"""
Unit and integration tests for Institutional EA Supabase PostgreSQL & API connectivity.
Never prints or asserts literal secret values.
"""

from __future__ import annotations

import json
import unittest

from companion.database.supabase_pg import (
    SupabaseApiClient,
    SupabasePostgresClient,
    _ensure_sslmode_require,
    load_supabase_config,
)


class TestSupabasePostgresIntegration(unittest.TestCase):
    def test_ensure_sslmode_require(self) -> None:
        dsn = "postgresql://user:pass%21@aws-1-eu-west-1.pooler.supabase.com:6543/postgres"
        secured = _ensure_sslmode_require(dsn)
        self.assertIn("sslmode=require", secured)
        self.assertEqual(_ensure_sslmode_require(secured), secured)

    def test_sanitized_summary_never_exposes_secrets(self) -> None:
        cfg = load_supabase_config()
        summary_json = json.dumps(cfg.sanitized_summary())
        if cfg.service_role_key:
            self.assertNotIn(cfg.service_role_key, summary_json)
        if cfg.jwt_secret:
            self.assertNotIn(cfg.jwt_secret, summary_json)
        if cfg.anon_key:
            self.assertNotIn(cfg.anon_key, summary_json)
        from urllib.parse import urlsplit
        parsed = urlsplit(cfg.database_url)
        if parsed.password:
            self.assertNotIn(parsed.password, summary_json)

    def test_live_postgres_and_supabase_api_connectivity(self) -> None:
        cfg = load_supabase_config()
        if not cfg.has_db_config or not cfg.has_api_config:
            self.skipTest("Supabase environment variables not configured in this environment")

        with SupabasePostgresClient(cfg) as pg:
            health = pg.health_check()
            self.assertTrue(health["ok"])
            self.assertEqual(health["db_name"], "postgres")
            self.assertIsNotNone(health["server_time_utc"])

            tables = pg.list_public_tables()
            for expected in ("profiles", "plans", "subscriptions", "payments", "devices", "audit_logs"):
                self.assertIn(expected, tables)

        api = SupabaseApiClient(cfg)
        self.assertTrue(api.check_rest_api()["ok"])
        self.assertTrue(api.check_auth_api()["ok"])
        plans = api.check_plans_endpoint()
        self.assertTrue(plans["ok"])
        self.assertGreaterEqual(plans["plans_count"], 1)


if __name__ == "__main__":
    unittest.main()
