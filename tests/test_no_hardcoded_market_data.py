"""
Guard test enforcing REAL DATA ONLY across production directories.
Fails if any hardcoded market/account values, mock generators, or reference screenshot
numbers appear under src/, engine/, agent/, companion/src/, or config/.
"""

from __future__ import annotations

from pathlib import Path

from tools.scan_hardcoded_data import scan_repository


def test_no_hardcoded_market_or_account_data_in_production_code():
    root = Path(__file__).resolve().parent.parent
    violations = scan_repository(root)
    assert violations == [], (
        "Hardcoded market/account data or mock generators found in production code:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )
