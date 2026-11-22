"""
Hardcoded Market / Account Data Guard Scanner (REAL DATA ONLY policy).
Scans production directories (src/, engine/, agent/, companion/src/, config/) and exits
non-zero if any forbidden literal market/account values, mock generators, or reference
screenshot numbers are present.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SCAN_ROOTS = [
    "src",
    "engine",
    "agent",
    "companion/src",
    "config",
]

ALLOWED_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".yaml", ".yml"}

# Paths excluded from production scanning (tests & test fixtures only)
EXCLUDED_SEGMENTS = {"__tests__", "tests", "__pycache__", "node_modules", "dist"}

# Forbidden literal market/account values and synthetic/mock generator markers
FORBIDDEN_PATTERNS: List[Tuple[str, str]] = [
    (r"\b25728\.30?\b", "Legacy mockup equity figure ($25,728.30)"),
    (r"\b25480(?:\.00?)?\b", "Legacy mockup balance figure ($25,480)"),
    (r"\b50420\.50?\b", "Legacy browser-mock equity figure ($50,420.50)"),
    (r"\b50198422\b", "Hardcoded mock account number (50198422)"),
    (r"\b88412091\b", "Hardcoded fake position ticket (88412091)"),
    (r"\b2668\.40?\b", "Legacy hardcoded XAUUSD price (2668.40)"),
    (r"\b91420(?:\.00?)?\b", "Legacy hardcoded BTCUSD price (91420.0)"),
    (r"\b60863\.21\b", "Reference screenshot BTCUSD price (60863.21)"),
    (r"\b3539\.80?\b", "Reference screenshot XAUUSD price (3539.80)"),
    (r"\b158\.537\b", "Reference screenshot USDJPY bid (158.537)"),
    (r"\b158\.553\b", "Reference screenshot USDJPY ask (158.553)"),
    (r"\b1845\.67\b", "Reference screenshot account balance/equity (1845.67)"),
    (r"\bseededNoise\b", "Synthetic candle noise generator in production code"),
    (r"DEMO Simulation Fallback", "Simulated order execution fallback in production code"),
    (r"\bfaker\b", "Faker mock data library reference in production code"),
]


def scan_repository(root: Path = PROJECT_ROOT) -> List[str]:
    violations: List[str] = []
    compiled = [(re.compile(pat), desc) for pat, desc in FORBIDDEN_PATTERNS]

    for rel_dir in SCAN_ROOTS:
        base = root / rel_dir
        if not base.exists():
            continue
        for file_path in base.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in ALLOWED_EXTENSIONS:
                continue
            if any(part in EXCLUDED_SEGMENTS for part in file_path.parts):
                continue
            try:
                text = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for line_no, line in enumerate(text.splitlines(), start=1):
                for regex, desc in compiled:
                    if regex.search(line):
                        rel = file_path.relative_to(root).as_posix()
                        violations.append(f"{rel}:{line_no} — {desc} -> {line.strip()[:120]}")
    return violations


def main() -> int:
    violations = scan_repository(PROJECT_ROOT)
    if violations:
        print(f"HARDCODED DATA GUARD FAILED ({len(violations)} violation(s)):", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1
    print("HARDCODED DATA GUARD PASSED: 0 violations in production code.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
