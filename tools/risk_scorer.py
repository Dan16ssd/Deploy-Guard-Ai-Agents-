"""LangChain tool: calculate a risk score (0–100) for a PR."""

from __future__ import annotations

import datetime
import re

from langchain_core.tools import tool

from shared.verdict import Verdict

# Weighted risk factors (additive, capped at 100)
_AUTH_FILES = re.compile(r"(?:auth|login|session|token|jwt|oauth|password)", re.I)
_PAYMENT_FILES = re.compile(r"(?:payment|billing|stripe|paypal|checkout|invoice)", re.I)


@tool
def calculate_risk_score(
    changed_files: list,
    additions: int,
    deletions: int,
    scan_verdict: str = "PASS",
    security_verdict: str = "PASS",
    upstream_warn_count: int = 0,
) -> dict:
    """Compute a risk score 0–100 and return a verdict + breakdown.

    Scoring:
      auth-related file touched  +30
      payment-related file touched +40
      deploy on a Friday          +15
      diff > 500 lines            +10
      each upstream WARN           +5  (capped contribution at 20)

    Verdict: PASS if score < 71, ESCALATE if score >= 71.
    """
    factors: dict[str, int] = {}
    score = 0

    auth_touched = any(_AUTH_FILES.search(f) for f in changed_files)
    payment_touched = any(_PAYMENT_FILES.search(f) for f in changed_files)

    if auth_touched:
        factors["auth_file_touched"] = 30
        score += 30
    if payment_touched:
        factors["payment_file_touched"] = 40
        score += 40

    if datetime.datetime.now(datetime.timezone.utc).weekday() == 4:  # Friday
        factors["friday_deploy"] = 15
        score += 15

    diff_size = additions + deletions
    if diff_size > 500:
        factors["large_diff"] = 10
        score += 10

    warn_contribution = min(upstream_warn_count * 5, 20)
    if warn_contribution:
        factors["upstream_warns"] = warn_contribution
        score += warn_contribution

    score = min(score, 100)
    verdict = Verdict.ESCALATE if score >= 71 else Verdict.PASS

    reasons = [f"{k.replace('_', ' ')}: +{v}" for k, v in factors.items()]
    if not reasons:
        reasons = ["No major risk factors detected"]

    return {
        "verdict": verdict.value,
        "score": score,
        "factors": factors,
        "reasons": reasons,
    }
