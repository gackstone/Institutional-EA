"""
Institutional EA — Centralized Supabase PostgreSQL & API Connectivity Layer.

Architecture & Security Guarantees:
- Preserves local SQLite (`companion/database/migrations.py` & `repository.py`) untouched.
- Uses `psycopg` v3 + `psycopg_pool.ConnectionPool` configured for Supabase Transaction Pooler
  (port 6543): `sslmode=require` and `prepare_threshold=None` (disables incompatible server-side
  prepared statements under PgBouncer/Supavisor transaction pooling).
- All SQL execution uses parameterized statements.
- Never logs or prints database passwords, JWT secrets, or service-role keys.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from dotenv import load_dotenv

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
except ImportError:  # pragma: no cover - handled gracefully if driver not installed
    psycopg = None  # type: ignore[assignment]
    dict_row = None  # type: ignore[assignment]
    ConnectionPool = None  # type: ignore[assignment]

logger = logging.getLogger("institutional_ea.supabase_pg")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _ensure_sslmode_require(dsn: str) -> str:
    """Ensures `sslmode=require` is present on PostgreSQL connection strings without logging secrets."""
    raw = (dsn or "").strip().strip('"').strip("'")
    if not raw:
        return ""
    parts = urlsplit(raw)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if "sslmode" not in query:
        query["sslmode"] = "require"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


@dataclass(frozen=True)
class SupabaseConfig:
    supabase_url: str
    anon_key: str
    service_role_key: str
    database_url: str
    jwt_secret: str

    @property
    def has_api_config(self) -> bool:
        return bool(self.supabase_url and self.anon_key)

    @property
    def has_db_config(self) -> bool:
        return bool(self.database_url)

    def sanitized_summary(self) -> dict[str, Any]:
        """Returns a safe diagnostics dict with zero secrets."""
        parsed = urlsplit(self.database_url) if self.database_url else None
        return {
            "supabase_url": self.supabase_url,
            "anon_key_configured": bool(self.anon_key),
            "service_role_key_configured": bool(self.service_role_key),
            "jwt_secret_configured": bool(self.jwt_secret),
            "database_configured": bool(self.database_url),
            "db_host": parsed.hostname if parsed else None,
            "db_port": parsed.port if parsed else None,
            "db_name": parsed.path.lstrip("/") if parsed else None,
            "db_ssl_required": "sslmode=require" in (self.database_url or ""),
        }


def load_supabase_config(env_path: Optional[Path | str] = None) -> SupabaseConfig:
    """Loads Supabase & PostgreSQL environment configuration from `.env` and process env."""
    target_env = Path(env_path) if env_path else (PROJECT_ROOT / ".env")
    if target_env.exists():
        load_dotenv(dotenv_path=target_env, override=False)

    supabase_url = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    if supabase_url.endswith("/rest/v1"):
        supabase_url = supabase_url[: -len("/rest/v1")]

    anon_key = (os.environ.get("SUPABASE_ANON_KEY") or "").strip()
    service_role_key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    jwt_secret = (os.environ.get("SUPABASE_JWT_SECRET") or "").strip()
    raw_db_url = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("SUPABASE_DB_URL")
        or ""
    ).strip()

    return SupabaseConfig(
        supabase_url=supabase_url,
        anon_key=anon_key,
        service_role_key=service_role_key,
        database_url=_ensure_sslmode_require(raw_db_url),
        jwt_secret=jwt_secret,
    )


class SupabasePostgresClient:
    """
    Pooled PostgreSQL client tuned for Supabase Transaction Pooler (port 6543).
    Disables prepared statements (`prepare_threshold=None`) so pooled connections
    never hit `DuplicatePreparedStatement` errors under Supavisor/PgBouncer.
    """

    def __init__(
        self,
        config: Optional[SupabaseConfig] = None,
        *,
        min_size: int = 1,
        max_size: int = 5,
        connect_timeout: int = 10,
    ):
        self.config = config or load_supabase_config()
        self._min_size = min_size
        self._max_size = max_size
        self._connect_timeout = connect_timeout
        self._pool: Optional[Any] = None

    def open(self) -> None:
        if self._pool is not None:
            return
        if psycopg is None or ConnectionPool is None:
            raise RuntimeError("psycopg / psycopg_pool is not installed. Run: pip install 'psycopg[binary]' psycopg-pool")
        if not self.config.has_db_config:
            raise RuntimeError("DATABASE_URL / SUPABASE_DB_URL is not configured in environment.")

        self._pool = ConnectionPool(
            conninfo=self.config.database_url,
            min_size=self._min_size,
            max_size=self._max_size,
            timeout=self._connect_timeout,
            open=True,
            kwargs={
                "autocommit": False,
                "prepare_threshold": None,  # Required for Supabase Transaction Pooler
                "row_factory": dict_row,
                "connect_timeout": self._connect_timeout,
            },
        )

    def close(self) -> None:
        if self._pool is not None:
            try:
                self._pool.close()
            finally:
                self._pool = None

    def __enter__(self) -> "SupabasePostgresClient":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _require_pool(self) -> Any:
        if self._pool is None:
            self.open()
        return self._pool

    def fetch_one(self, sql: str, params: Optional[Iterable[Any]] = None) -> Optional[dict[str, Any]]:
        pool = self._require_pool()
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchone()

    def fetch_all(self, sql: str, params: Optional[Iterable[Any]] = None) -> list[dict[str, Any]]:
        pool = self._require_pool()
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return list(cur.fetchall())

    def execute(self, sql: str, params: Optional[Iterable[Any]] = None) -> int:
        pool = self._require_pool()
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rowcount = cur.rowcount
            conn.commit()
            return rowcount

    def health_check(self) -> dict[str, Any]:
        """Executes `SELECT NOW() AS server_time_utc, current_database() AS db_name`."""
        row = self.fetch_one("SELECT NOW() AS server_time_utc, current_database() AS db_name;")
        return {
            "ok": bool(row),
            "server_time_utc": str(row["server_time_utc"]) if row else None,
            "db_name": row["db_name"] if row else None,
        }

    def list_public_tables(self) -> list[str]:
        rows = self.fetch_all(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' ORDER BY table_name;"
        )
        return [str(r["table_name"]) for r in rows]

    def apply_sql_file(self, sql_file: Path) -> None:
        """Applies a version-controlled SQL migration file inside a transaction."""
        sql_text = Path(sql_file).read_text(encoding="utf-8")
        pool = self._require_pool()
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql_text)
            conn.commit()


class SupabaseApiClient:
    """Centralized server-side HTTP client for Supabase REST & Auth health checks."""

    def __init__(self, config: Optional[SupabaseConfig] = None, timeout: int = 10):
        self.config = config or load_supabase_config()
        self.timeout = timeout

    def check_rest_api(self) -> dict[str, Any]:
        if not self.config.has_api_config:
            return {"ok": False, "error": "SUPABASE_URL or SUPABASE_ANON_KEY not configured"}
        url = f"{self.config.supabase_url}/rest/v1/plans?select=id&limit=1"
        resp = requests.get(
            url,
            headers={"apikey": self.config.anon_key, "Accept": "application/json"},
            timeout=self.timeout,
        )
        return {"ok": resp.status_code == 200, "status_code": resp.status_code, "url": url}

    def check_auth_api(self) -> dict[str, Any]:
        if not self.config.has_api_config:
            return {"ok": False, "error": "SUPABASE_URL or SUPABASE_ANON_KEY not configured"}
        url = f"{self.config.supabase_url}/auth/v1/health"
        resp = requests.get(
            url,
            headers={"apikey": self.config.anon_key},
            timeout=self.timeout,
        )
        return {"ok": resp.status_code == 200, "status_code": resp.status_code, "url": url}

    def check_plans_endpoint(self) -> dict[str, Any]:
        if not self.config.has_api_config:
            return {"ok": False, "error": "SUPABASE_URL or SUPABASE_ANON_KEY not configured"}
        url = f"{self.config.supabase_url}/rest/v1/plans?is_active=eq.true&select=id,name,price,currency,billing_interval"
        resp = requests.get(
            url,
            headers={"apikey": self.config.anon_key},
            timeout=self.timeout,
        )
        data = resp.json() if resp.ok else None
        return {"ok": resp.status_code == 200, "status_code": resp.status_code, "plans_count": len(data) if isinstance(data, list) else 0}
