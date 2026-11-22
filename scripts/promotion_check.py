"""
Stage 8: Production Promotion Gate Evaluator.
Strictly evaluates the 6 mandatory criteria from genuine recorded validation artifacts
before any model or flag is permitted to qualify, while keeping the system strictly
locked in DEMO mode (LIVE_TRADING_ENABLED=false).

1. Walk-forward Sharpe >= 1.0 (or Expectancy >= +0.25R with 95% bootstrap CI > 0)
2. Deflated Sharpe Ratio (DSR) >= 0.95
3. Probability of Backtest Overfitting (PBO) < 0.20
4. Monte Carlo Ruin Probability = 0.00% across 5,000 runs, and breach within limits
5. Shadow mode realization matching simulation within 2-sigma over >= 50 shadow trades
6. Explicit operator confirmation (and DEMO-only safety enforcement)

No hardcoded performance observations are permitted. Missing, malformed, or insufficient
validation evidence is automatically rejected (fail-closed).
"""

from __future__ import annotations
import json
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple


REQUIRED_EVIDENCE_KEYS = (
    "wf_sharpe",
    "expectancy_r",
    "ci_lower",
    "dsr",
    "pbo",
    "mc_ruin_pct",
    "mc_breach_pct",
    "shadow_trade_count",
    "shadow_z_score",
)


@dataclass(frozen=True)
class GateCriterionResult:
    name: str
    required_threshold: str
    observed_value: str
    passed: bool
    details: str


def _is_valid_number(val: Any) -> bool:
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        return False
    return math.isfinite(float(val))


def evaluate_promotion_gate(
    wf_sharpe: float,
    expectancy_r: float,
    ci_lower: float,
    dsr: float,
    pbo: float,
    mc_ruin_pct: float,
    mc_breach_pct: float,
    breach_limit_pct: float,
    shadow_trade_count: int,
    shadow_z_score: float,
    operator_confirmed: bool,
) -> Tuple[bool, List[GateCriterionResult], str]:
    """
    Evaluates each criterion and returns overall verdict.
    Note: Even if statistically qualified, the bot remains in DEMO mode unless manually reconfigured.
    """
    results: List[GateCriterionResult] = []

    # Criterion 1: Walk-forward Sharpe >= 1.0 OR (Expectancy >= +0.25R and CI_lower > 0)
    c1_passed = (wf_sharpe >= 1.0) or (expectancy_r >= 0.25 and ci_lower > 0.0)
    results.append(
        GateCriterionResult(
            name="1. Walk-Forward Edge",
            required_threshold="Sharpe >= 1.0 OR (E >= +0.25R & 95% CI > 0)",
            observed_value=f"Sharpe={wf_sharpe:.2f}, E={expectancy_r:+.2f}R [95% CI: {ci_lower:+.2f}R]",
            passed=c1_passed,
            details="Out-of-sample forward expectancy test.",
        )
    )

    # Criterion 2: Deflated Sharpe Ratio >= 0.95
    c2_passed = dsr >= 0.95
    results.append(
        GateCriterionResult(
            name="2. Deflated Sharpe Ratio (DSR)",
            required_threshold="DSR >= 0.95 (95% confidence against false discovery)",
            observed_value=f"DSR = {dsr:.4f}",
            passed=c2_passed,
            details="Bailey & Lopez de Prado (2014) multiple testing correction.",
        )
    )

    # Criterion 3: Probability of Backtest Overfitting < 0.20
    c3_passed = 0.0 <= pbo < 0.20
    results.append(
        GateCriterionResult(
            name="3. Probability of Overfitting (PBO)",
            required_threshold="PBO < 0.20 (CSCV combinatorial testing)",
            observed_value=f"PBO = {pbo:.3f}",
            passed=c3_passed,
            details="Combinatorial Symmetric Cross-Validation overfit likelihood.",
        )
    )

    # Criterion 4: Monte Carlo Ruin & Drawdown Breach
    c4_passed = (mc_ruin_pct == 0.0) and (0.0 <= mc_breach_pct <= breach_limit_pct)
    results.append(
        GateCriterionResult(
            name="4. Monte Carlo Ruin & Breach",
            required_threshold=f"Ruin = 0.00%, Breach <= {breach_limit_pct:.1f}%",
            observed_value=f"Ruin = {mc_ruin_pct:.2f}%, Breach = {mc_breach_pct:.2f}%",
            passed=c4_passed,
            details="5,000-permutation trade order resampling.",
        )
    )

    # Criterion 5: Shadow Mode Realization
    c5_passed = (shadow_trade_count >= 50) and (abs(shadow_z_score) <= 2.0)
    results.append(
        GateCriterionResult(
            name="5. Shadow Mode Audit Realization",
            required_threshold="Count >= 50 trades AND |Z-Score| <= 2.0 sigma",
            observed_value=f"Count = {shadow_trade_count}, Z = {shadow_z_score:.2f} sigma",
            passed=c5_passed,
            details="Live DEMO/paper audit matching simulated expectation.",
        )
    )

    # Criterion 6: Operator Confirmation
    c6_passed = bool(operator_confirmed)
    results.append(
        GateCriterionResult(
            name="6. Operator Explicit Approval",
            required_threshold="Explicit confirmation ('APPROVED')",
            observed_value="CONFIRMED" if c6_passed else "PENDING_OPERATOR_APPROVAL",
            passed=c6_passed,
            details="Human-in-the-loop sign-off required; system remains locked in DEMO mode.",
        )
    )

    all_stat_passed = all(r.passed for r in results[:5])
    overall_approved = all_stat_passed and c6_passed

    if not all_stat_passed:
        verdict = "REJECTED: edge not demonstrated. System remains strictly in DEMO mode (LIVE_TRADING_ENABLED=false)."
    elif not c6_passed:
        verdict = "STATISTICALLY QUALIFIED: Awaiting explicit operator confirmation. System remains in DEMO mode."
    else:
        verdict = "QUALIFIED_EVIDENCE_VERIFIED: Statistical and operator criteria met. System remains in DEMO mode by safety policy."

    return overall_approved, results, verdict


def load_and_evaluate_promotion_evidence(
    report_path: str = "reports/validation_report.json",
    config_dir: str = "config",
) -> Tuple[bool, List[GateCriterionResult], str]:
    """
    Loads genuine validation evidence from `report_path`, validates schema and sample sufficiency,
    and evaluates promotion criteria without any hardcoded metrics.
    Also enforces that `config/settings.json` remains in DEMO mode (`LIVE_TRADING_ENABLED=false`).
    """
    # Enforce DEMO safety lock in settings.json if present
    settings_path = Path(config_dir) / "settings.json"
    if settings_path.exists():
        try:
            settings_data = json.loads(settings_path.read_text(encoding="utf-8"))
            if isinstance(settings_data, dict):
                if settings_data.get("LIVE_TRADING_ENABLED", False) is True or str(settings_data.get("execution_mode", "DEMO")).upper() != "DEMO":
                    return (
                        False,
                        [
                            GateCriterionResult(
                                name="0. DEMO Safety Lock",
                                required_threshold="execution_mode='DEMO' and LIVE_TRADING_ENABLED=false",
                                observed_value=f"execution_mode={settings_data.get('execution_mode')}, LIVE_TRADING_ENABLED={settings_data.get('LIVE_TRADING_ENABLED')}",
                                passed=False,
                                details="Promotion check refuses to run when LIVE_TRADING_ENABLED is true or execution_mode is not DEMO.",
                            )
                        ],
                        "REJECTED: DEMO safety lock violated in config/settings.json.",
                    )
        except Exception as exc:
            return (
                False,
                [
                    GateCriterionResult(
                        name="0. Configuration Integrity",
                        required_threshold="Valid JSON in config/settings.json",
                        observed_value=f"Error: {exc}",
                        passed=False,
                        details="Malformed settings.json.",
                    )
                ],
                f"REJECTED: Malformed configuration ({exc}).",
            )

    rpath = Path(report_path)
    if not rpath.exists():
        return (
            False,
            [
                GateCriterionResult(
                    name="0. Validation Report Evidence",
                    required_threshold=f"Existing JSON artifact at {report_path}",
                    observed_value="MISSING",
                    passed=False,
                    details="No recorded validation report found. Run scripts/run_validation.py first.",
                )
            ],
            f"REJECTED: Missing validation evidence artifact ({report_path}). System remains in DEMO mode.",
        )

    try:
        raw = json.loads(rpath.read_text(encoding="utf-8"))
    except Exception as exc:
        return (
            False,
            [
                GateCriterionResult(
                    name="0. Validation Report Evidence",
                    required_threshold="Valid JSON object",
                    observed_value=f"MALFORMED ({exc})",
                    passed=False,
                    details="Validation artifact could not be parsed as JSON.",
                )
            ],
            f"REJECTED: Malformed validation evidence JSON ({exc}). System remains in DEMO mode.",
        )

    if not isinstance(raw, dict):
        return (
            False,
            [
                GateCriterionResult(
                    name="0. Validation Report Evidence",
                    required_threshold="JSON object with validation metrics",
                    observed_value=f"Invalid root type: {type(raw).__name__}",
                    passed=False,
                    details="Validation report root must be a JSON dictionary.",
                )
            ],
            "REJECTED: Validation evidence root is not a JSON object. System remains in DEMO mode.",
        )

    missing_or_invalid: List[str] = []
    for k in REQUIRED_EVIDENCE_KEYS:
        if k not in raw or not _is_valid_number(raw[k]):
            missing_or_invalid.append(k)

    if missing_or_invalid:
        return (
            False,
            [
                GateCriterionResult(
                    name="0. Validation Schema Completeness",
                    required_threshold="All 9 statistical fields present and finite",
                    observed_value=f"Missing/invalid: {', '.join(missing_or_invalid)}",
                    passed=False,
                    details="Validation report lacks required empirical metrics.",
                )
            ],
            f"REJECTED: Insufficient or malformed validation metrics ({', '.join(missing_or_invalid)}). System remains in DEMO mode.",
        )

    return evaluate_promotion_gate(
        wf_sharpe=float(raw["wf_sharpe"]),
        expectancy_r=float(raw["expectancy_r"]),
        ci_lower=float(raw["ci_lower"]),
        dsr=float(raw["dsr"]),
        pbo=float(raw["pbo"]),
        mc_ruin_pct=float(raw["mc_ruin_pct"]),
        mc_breach_pct=float(raw["mc_breach_pct"]),
        breach_limit_pct=float(raw.get("breach_limit_pct", 10.0)),
        shadow_trade_count=int(raw["shadow_trade_count"]),
        shadow_z_score=float(raw["shadow_z_score"]),
        operator_confirmed=bool(raw.get("operator_confirmed", False)),
    )


def main(report_path: str = "reports/validation_report.json") -> int:
    print("=" * 80)
    print("STAGE 8: PRODUCTION PROMOTION GATE AUDIT (EMPIRICAL ARTIFACT VERIFICATION)")
    print("=" * 80)

    approved, criteria, verdict = load_and_evaluate_promotion_evidence(report_path=report_path)

    for c in criteria:
        status_sym = "[PASS]" if c.passed else "[FAIL]"
        print(f"{status_sym} {c.name}")
        print(f"       Required: {c.required_threshold}")
        print(f"       Observed: {c.observed_value}")
        print(f"       Details:  {c.details}")
        print()

    print("-" * 80)
    print(f"GATE VERDICT: {verdict}")
    print("-" * 80)

    os.makedirs("reports", exist_ok=True)
    with open("reports/promotion_gate_verdict.md", "w", encoding="utf-8") as f:
        f.write("# Stage 8 Promotion Gate Audit Report\n\n")
        f.write(f"**Overall Gate Status:** `{verdict}`\n\n")
        f.write("## Criteria Evaluation Matrix\n\n")
        f.write("| # | Criterion | Required Threshold | Observed Value | Status |\n")
        f.write("|---|:---|:---|:---|:---|\n")
        for c in criteria:
            st = "PASS" if c.passed else "FAIL"
            f.write(f"| {c.name[:2]} | {c.name[3:]} | `{c.required_threshold}` | `{c.observed_value}` | {st} |\n")
        f.write("\n### Safety Policy\n")
        f.write("- The system remains strictly in **DEMO** mode (`execution_mode = DEMO`, `LIVE_TRADING_ENABLED = false`).\n")
        f.write("- Hardcoded performance metrics are prohibited; only genuine empirical artifacts are evaluated.\n")

    return 0 if approved else 1


if __name__ == "__main__":
    target_report = sys.argv[1] if len(sys.argv) > 1 else "reports/validation_report.json"
    sys.exit(main(report_path=target_report))
