"""LangChain tool: calculate a risk score (0–100) for a PR."""

from __future__ import annotations

import datetime
import re

from langchain_core.tools import tool

from shared.verdict import Verdict

# Weighted risk factors (additive, capped at 100)
_AUTH_FILES = re.compile(r"(?:auth|login|session|token|jwt|oauth|password)", re.I)
_PAYMENT_FILES = re.compile(r"(?:payment|billing|stripe|paypal|checkout|invoice)", re.I)


def _compute_risk(
    changed_files: list,
    additions: int,
    deletions: int,
    scan_verdict: str,
    security_verdict: str,
    upstream_warn_count: int,
) -> dict:
    """Pure scoring logic shared by the calculate_risk_score and assess_risk tools."""
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

    Scoring: auth file +30 · payment file +40 · Friday +15 · diff > 500 lines +10 ·
    each upstream WARN +5 (capped at 20). Verdict: PASS if < 71, ESCALATE if >= 71.
    """
    return _compute_risk(
        changed_files,
        additions,
        deletions,
        scan_verdict,
        security_verdict,
        upstream_warn_count,
    )


@tool
def assess_risk(
    repo: str,
    pr_number: int,
    scan_verdict: str = "PASS",
    security_verdict: str = "PASS",
) -> dict:
    """Score a PR's deployment risk in ONE deterministic call.

    RiskAgent should call THIS and nothing else. It fetches the PR's changed files + size
    itself (so the agent never has to dig them out of chat history), counts upstream WARNs
    from the two verdicts, computes the 0–100 score, and returns the exact next hand-off
    handle. Returns {score, verdict, factors, reasons, handoff} — DeployAgent on PASS, the
    on-call engineer on ESCALATE.

    Peer review: also returns `cross_check`. If the PR touches security-sensitive files
    (auth/payment) yet SecurityAgent only returned PASS/WARN, RiskAgent should NOT just trust
    it — `cross_check` is "challenge" and `challenge_handle` is SecurityAgent, so RiskAgent
    sends it back for a deeper re-scan (consensus required before deploy). Otherwise
    `cross_check` is "endorsed".
    """
    from shared.band_handles import agent_handle, engineer_handle
    from tools.github_api import _resolve_target, get_pr_metadata

    repo, pr_number = _resolve_target(repo, pr_number)
    meta = get_pr_metadata.invoke({"repo": repo, "pr_number": pr_number})
    if isinstance(meta, dict) and "error" not in meta:
        changed_files = meta.get("changed_files", []) or []
        additions = int(meta.get("additions", 0) or 0)
        deletions = int(meta.get("deletions", 0) or 0)
    else:
        changed_files, additions, deletions = [], 0, 0

    warns = sum(
        1 for v in (scan_verdict, security_verdict) if str(v).strip().upper() == "WARN"
    )
    result = _compute_risk(
        changed_files, additions, deletions, scan_verdict, security_verdict, warns
    )
    result["handoff"] = (
        agent_handle("DeployAgent")
        if result["verdict"] == Verdict.PASS.value
        else engineer_handle()
    )

    # Peer-review cross-check: a security-sensitive change that Security only PASSed/WARNed
    # warrants a second look — RiskAgent challenges SecurityAgent to re-scan (consensus gate).
    sensitive = any(
        _AUTH_FILES.search(f) or _PAYMENT_FILES.search(f) for f in changed_files
    )
    sv = str(security_verdict).strip().upper()
    result["cross_check"] = (
        "challenge" if (sensitive and sv in ("PASS", "WARN")) else "endorsed"
    )
    result["challenge_handle"] = agent_handle("SecurityAgent")
    return result
