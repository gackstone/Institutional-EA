"""
Security and authentication utilities for the MT5-001 Local Control Service.
Enforces localhost-only binding, session token authentication, origin checks,
and secret redaction in logs/outputs.
"""

from __future__ import annotations
import hmac
import os
import re
import secrets
from pathlib import Path
from typing import Mapping, Optional


SECRET_PATTERNS = [
    re.compile(r"(TELEGRAM_BOT_TOKEN\s*=\s*)([^\s\"']+)", re.IGNORECASE),
    re.compile(r"(MT5_PASSWORD\s*=\s*)([^\s\"']+)", re.IGNORECASE),
    re.compile(r"(ARCADEFX_DEVICE_TOKEN\s*=\s*)([^\s\"']+)", re.IGNORECASE),
    re.compile(r"(Authorization:\s*Bearer\s+)([^\s]+)", re.IGNORECASE),
    re.compile(r"(bot[0-9]{6,}:[A-Za-z0-9_-]{20,})"),
]


def redact_secrets(text: str) -> str:
    """Redacts tokens, passwords, and bearer credentials from log/output strings."""
    if not text:
        return text
    masked = text
    for pat in SECRET_PATTERNS:
        if pat.groups >= 2:
            masked = pat.sub(r"\1***REDACTED***", masked)
        else:
            masked = pat.sub("***REDACTED***", masked)
    return masked


class LocalAuthManager:
    """Manages cryptographically random session tokens for localhost IPC."""

    def __init__(self, token: Optional[str] = None, token_file: Optional[Path] = None):
        self.token = token or os.environ.get("MT5_COMPANION_TOKEN") or secrets.token_urlsafe(32)
        self.token_file = token_file
        if self.token_file:
            self.token_file.parent.mkdir(parents=True, exist_ok=True)
            self.token_file.write_text(self.token, encoding="utf-8")

    def verify_request(self, headers: Mapping[str, str], query_token: Optional[str] = None) -> bool:
        """Verifies Bearer token or X-Companion-Token header (or query token for SSE)."""
        # Origin check: only allow missing origin (Electron/local client) or localhost
        origin = headers.get("Origin") or headers.get("origin") or ""
        if origin and not (
            origin.startswith("http://127.0.0.1")
            or origin.startswith("http://localhost")
            or origin.startswith("file://")
            or origin.startswith("app://")
        ):
            return False

        auth_header = headers.get("Authorization") or headers.get("authorization") or ""
        supplied = ""
        if auth_header.lower().startswith("bearer "):
            supplied = auth_header[7:].strip()
        elif headers.get("X-Companion-Token") or headers.get("x-companion-token"):
            supplied = (headers.get("X-Companion-Token") or headers.get("x-companion-token") or "").strip()
        elif query_token:
            supplied = query_token.strip()

        if not supplied:
            return False
        return hmac.compare_digest(supplied, self.token)

    @staticmethod
    def validate_bind_host(host: str) -> str:
        """Refuses non-localhost binding by default."""
        normalized = (host or "127.0.0.1").strip().lower()
        if normalized not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError(f"Refusing non-localhost bind address '{host}'. Localhost-only binding is enforced.")
        return normalized
