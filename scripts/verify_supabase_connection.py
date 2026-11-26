r"""
Institutional EA — Supabase & PostgreSQL Connectivity Verifier + Safe Migration Runner.

Usage:
  .\.venv\Scripts\python.exe scripts\verify_supabase_connection.py
  .\.venv\Scripts\python.exe scripts\verify_supabase_connection.py --apply-migrations

Security:
  Never prints passwords, API keys, service-role keys, or JWT secrets.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from companion.database.supabase_pg import (  # noqa: E402
    SupabaseApiClient,
    SupabasePostgresClient,
    load_supabase_config,
)

EXPECTED_TABLES = [
    "audit_logs",
    "devices",
    "payments",
    "plans",
    "profiles",
    "subscriptions",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Supabase API & PostgreSQL connectivity")
    parser.add_argument(
        "--apply-migrations",
        action="store_true",
        help="Apply version-controlled SQL migrations in supabase/migrations/ if tables are missing",
    )
    args = parser.parse_args()

    cfg = load_supabase_config()
    report: dict = {
        "config": cfg.sanitized_summary(),
        "postgres": {"ok": False},
        "supabase_rest_api": {"ok": False},
        "supabase_auth_api": {"ok": False},
        "supabase_plans_endpoint": {"ok": False},
        "public_tables": [],
        "migrations_applied": [],
    }

    # 1. PostgreSQL Transaction Pooler Verification
    try:
        with SupabasePostgresClient(cfg) as pg:
            health = pg.health_check()
            tables = pg.list_public_tables()
            report["postgres"] = health
            report["public_tables"] = tables

            if args.apply_migrations:
                mig_dir = PROJECT_ROOT / "supabase" / "migrations"
                for sql_file in sorted(mig_dir.glob("*.sql")):
                    pg.apply_sql_file(sql_file)
                    report["migrations_applied"].append(sql_file.name)
                report["public_tables"] = pg.list_public_tables()
    except Exception as exc:
        report["postgres"] = {"ok": False, "error": str(exc)}

    # 2. Supabase REST & Auth API Verification
    api = SupabaseApiClient(cfg)
    try:
        report["supabase_rest_api"] = api.check_rest_api()
    except Exception as exc:
        report["supabase_rest_api"] = {"ok": False, "error": str(exc)}

    try:
        report["supabase_auth_api"] = api.check_auth_api()
    except Exception as exc:
        report["supabase_auth_api"] = {"ok": False, "error": str(exc)}

    try:
        report["supabase_plans_endpoint"] = api.check_plans_endpoint()
    except Exception as exc:
        report["supabase_plans_endpoint"] = {"ok": False, "error": str(exc)}

    report["schema_ready"] = all(t in report["public_tables"] for t in EXPECTED_TABLES)
    print(json.dumps(report, indent=2))

    ok = (
        report["postgres"].get("ok")
        and report["supabase_rest_api"].get("ok")
        and report["supabase_auth_api"].get("ok")
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
