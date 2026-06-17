"""Tests for tools/ — no network, no Band, no LLM credentials required."""

from __future__ import annotations

from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


# ── security_scanner ─────────────────────────────────────────────────────────


def test_security_scanner_flags_vuln_diff():
    from shared.verdict import Severity
    from tools.security_scanner import scan_diff_regex

    diff = (FIXTURES / "vuln_pr_diff.txt").read_text()
    findings = scan_diff_regex(diff)
    severities = {f.severity for f in findings}
    assert (
        Severity.CRIT in severities
    ), f"Expected CRIT finding in vuln diff, got: {[f.message for f in findings]}"


def test_security_scanner_passes_clean_diff():
    from shared.verdict import Severity
    from tools.security_scanner import scan_diff_regex

    diff = (FIXTURES / "clean_pr_diff.txt").read_text()
    findings = scan_diff_regex(diff)
    crit_findings = [f for f in findings if f.severity == Severity.CRIT]
    assert crit_findings == [], f"Unexpected CRIT in clean diff: {crit_findings}"


def test_scan_for_vulnerabilities_tool_vuln():
    from tools.security_scanner import scan_for_vulnerabilities

    diff = (FIXTURES / "vuln_pr_diff.txt").read_text()
    result = scan_for_vulnerabilities.invoke({"diff": diff, "use_llm": False})
    assert result["verdict"] == "BLOCK"
    assert result["max_severity"] == "CRIT"
    assert len(result["findings"]) > 0


def test_scan_for_vulnerabilities_tool_clean():
    from tools.security_scanner import scan_for_vulnerabilities

    diff = (FIXTURES / "clean_pr_diff.txt").read_text()
    result = scan_for_vulnerabilities.invoke({"diff": diff, "use_llm": False})
    assert result["verdict"] in ("PASS", "WARN")
    assert result["max_severity"] != "CRIT"


def test_security_review_blocks_and_autoposts(monkeypatch):
    """The deterministic review tool must auto-post the CRIT comment + escalate, with no
    dependence on the LLM. This locks the demo's hero visual."""
    import os

    os.environ.setdefault("BAND_USERNAME", "danny.ssd7")
    monkeypatch.setenv(
        "TARGET_REPO", ""
    )  # keep the test offline/hermetic (blocks load_dotenv re-inject)
    from langchain_core.tools import tool

    import tools.github_api as gh

    posted: list[str] = []

    @tool
    def _diff(repo: str, pr_number: int) -> str:
        """fake"""
        return (FIXTURES / "vuln_pr_diff.txt").read_text()

    @tool
    def _post(repo: str, pr_number: int, body: str) -> str:
        """fake"""
        posted.append(body)
        return "https://github.com/x/y/pull/1#comment-1"

    monkeypatch.setattr(gh, "get_pr_diff", _diff)
    monkeypatch.setattr(gh, "post_pr_comment", _post)

    from tools.security_scanner import security_review

    r = security_review.invoke({"repo": "x/y", "pr_number": 1})
    assert r["verdict"] == "BLOCK"
    assert len(posted) == 1, "must auto-post exactly one CRIT comment"
    assert r["handoff"].endswith("danny.ssd7"), "BLOCK escalates to the engineer"


def test_security_review_clean_routes_to_risk(monkeypatch):
    import os

    os.environ.setdefault("BAND_USERNAME", "danny.ssd7")
    monkeypatch.setenv(
        "TARGET_REPO", ""
    )  # keep the test offline/hermetic (blocks load_dotenv re-inject)
    from langchain_core.tools import tool

    import tools.github_api as gh

    posted: list[str] = []

    @tool
    def _diff(repo: str, pr_number: int) -> str:
        """fake"""
        return (FIXTURES / "clean_pr_diff.txt").read_text()

    @tool
    def _post(repo: str, pr_number: int, body: str) -> str:
        """fake"""
        posted.append(body)
        return "url"

    monkeypatch.setattr(gh, "get_pr_diff", _diff)
    monkeypatch.setattr(gh, "post_pr_comment", _post)

    from tools.security_scanner import security_review

    r = security_review.invoke({"repo": "x/y", "pr_number": 2})
    assert r["verdict"] == "PASS"
    assert posted == [], "clean diff must NOT post a comment"
    assert "riskagent" in r["handoff"], "PASS hands off to RiskAgent"


# ── risk_scorer ──────────────────────────────────────────────────────────────


def test_risk_scorer_auth_file_scores_high():
    from tools.risk_scorer import calculate_risk_score

    result = calculate_risk_score.invoke(
        {
            "changed_files": ["app/auth.py"],
            "additions": 100,
            "deletions": 10,
            "scan_verdict": "PASS",
            "security_verdict": "PASS",
            "upstream_warn_count": 0,
        }
    )
    assert result["score"] >= 30
    assert "auth_file_touched" in result["factors"]


def test_risk_scorer_payment_escalates():
    from tools.risk_scorer import calculate_risk_score

    result = calculate_risk_score.invoke(
        {
            "changed_files": ["app/billing.py"],
            "additions": 200,
            "deletions": 50,
            "scan_verdict": "PASS",
            "security_verdict": "PASS",
            "upstream_warn_count": 0,
        }
    )
    assert result["score"] >= 40
    assert result["verdict"] in ("PASS", "ESCALATE")


def test_risk_scorer_large_diff_adds_points():
    from tools.risk_scorer import calculate_risk_score

    result = calculate_risk_score.invoke(
        {
            "changed_files": ["app/utils.py"],
            "additions": 400,
            "deletions": 200,
            "scan_verdict": "PASS",
            "security_verdict": "PASS",
            "upstream_warn_count": 0,
        }
    )
    assert result["factors"].get("large_diff") == 10


def test_risk_scorer_score_capped_at_100():
    from tools.risk_scorer import calculate_risk_score

    result = calculate_risk_score.invoke(
        {
            "changed_files": ["app/auth.py", "app/billing.py"],
            "additions": 600,
            "deletions": 100,
            "scan_verdict": "WARN",
            "security_verdict": "WARN",
            "upstream_warn_count": 4,
        }
    )
    assert result["score"] <= 100


def _mock_meta(monkeypatch, changed_files):
    """Point assess_risk's get_pr_metadata at a fake (no network)."""
    import os

    os.environ.setdefault("BAND_USERNAME", "danny.ssd7")
    monkeypatch.setenv("TARGET_REPO", "")
    from langchain_core.tools import tool

    import tools.github_api as gh

    @tool
    def _meta(repo: str, pr_number: int) -> dict:
        """fake"""
        return {"changed_files": changed_files, "additions": 10, "deletions": 0}

    monkeypatch.setattr(gh, "get_pr_metadata", _meta)


def test_assess_risk_challenges_sensitive_passed_change(monkeypatch):
    """A security-sensitive change SecurityAgent only PASSed must trigger a peer-review
    challenge back to SecurityAgent (the agent-reviews-agent consensus gate)."""
    _mock_meta(monkeypatch, ["app/auth.py"])
    from tools.risk_scorer import assess_risk

    r = assess_risk.invoke(
        {
            "repo": "x/y",
            "pr_number": 1,
            "scan_verdict": "PASS",
            "security_verdict": "PASS",
        }
    )
    assert r["cross_check"] == "challenge"
    assert "securityagent" in r["challenge_handle"].lower()


def test_assess_risk_endorses_nonsensitive_change(monkeypatch):
    _mock_meta(monkeypatch, ["app/utils.py"])
    from tools.risk_scorer import assess_risk

    r = assess_risk.invoke(
        {
            "repo": "x/y",
            "pr_number": 2,
            "scan_verdict": "PASS",
            "security_verdict": "PASS",
        }
    )
    assert r["cross_check"] == "endorsed"


# ── dep_auditor ──────────────────────────────────────────────────────────────


def test_dep_audit_skips_host_manifest_cleanly(tmp_path):
    """An agent-runtime manifest (contains band-sdk/langgraph) must skip instantly with a
    clean, professional message — never run pip-audit, never surface a TimeoutError."""
    from tools.dep_auditor import audit_dependencies

    req = tmp_path / "requirements.txt"
    req.write_text("band-sdk[langgraph]==1.0.0\nlangchain-core>=0.3\nfastapi>=0.110\n")
    result = audit_dependencies.invoke({"requirements_file": str(req)})
    assert result["cve_count"] == 0
    assert "not required" in result["summary"]
    assert (
        "TimeoutError" not in result["summary"] and "skipped:" not in result["summary"]
    )


def test_dep_audit_missing_file_is_clean(tmp_path):
    from tools.dep_auditor import audit_dependencies

    result = audit_dependencies.invoke(
        {"requirements_file": str(tmp_path / "nope.txt")}
    )
    assert result["cve_count"] == 0
    assert "skipped" in result["summary"]


# ── static_analyzer ──────────────────────────────────────────────────────────


def test_static_analyzer_on_clean_python():
    from tools.static_analyzer import _extract_added_content

    diff = (FIXTURES / "clean_pr_diff.txt").read_text()
    content = _extract_added_content(diff)
    assert isinstance(content, dict)


# ── webhook parser + verifier ─────────────────────────────────────────────────


def test_webhook_parser_accepts_main_pr():
    import json

    from webhook.parser import parse_pr_payload

    payload = json.loads((FIXTURES / "sample_pr_payload.json").read_text())
    pr = parse_pr_payload(payload)
    assert pr is not None
    assert pr.pr_number == 42
    assert pr.author == "contributor"


def test_webhook_parser_ignores_non_main():
    from webhook.parser import parse_pr_payload

    payload = {
        "action": "opened",
        "pull_request": {
            "number": 1,
            "title": "t",
            "user": {"login": "u"},
            "base": {"ref": "dev", "sha": "x"},
            "head": {"ref": "f", "sha": "y"},
            "diff_url": "",
            "additions": 0,
            "deletions": 0,
        },
        "repository": {"full_name": "o/r"},
    }
    assert parse_pr_payload(payload) is None


def test_webhook_verifier_accepts_valid_signature():
    import hashlib
    import hmac
    import os

    os.environ["GITHUB_WEBHOOK_SECRET"] = "test-secret"
    from webhook.verifier import verify_signature

    body = b'{"action":"opened"}'
    sig = "sha256=" + hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
    assert verify_signature(body, sig) is True


def test_webhook_verifier_rejects_bad_signature():
    import os

    os.environ["GITHUB_WEBHOOK_SECRET"] = "test-secret"
    from webhook.verifier import verify_signature

    assert verify_signature(b"body", "sha256=badhash") is False


# ── llm_factory: multi-key Featherless ────────────────────────────────────────


def test_featherless_key_pool_round_robin(monkeypatch):
    """A key pool spreads agents across keys so no single key is hit twice per run."""
    from shared.llm_factory import _resolve_api_key

    provider = {"api_key_env": "FEATHERLESS_API_KEY"}
    monkeypatch.delenv("FEATHERLESS_API_KEY_SCAN", raising=False)
    monkeypatch.setenv("FEATHERLESS_API_KEYS", "k1,k2,k3")
    # config agent order: scan, security, risk, deploy, report
    assert _resolve_api_key(provider, "scan") == "k1"
    assert _resolve_api_key(provider, "security") == "k2"
    assert _resolve_api_key(provider, "risk") == "k3"
    assert _resolve_api_key(provider, "deploy") == "k1"  # wraps


def test_featherless_per_agent_override(monkeypatch):
    from shared.llm_factory import _resolve_api_key

    provider = {"api_key_env": "FEATHERLESS_API_KEY"}
    monkeypatch.setenv("FEATHERLESS_API_KEY_SCAN", "special")
    assert _resolve_api_key(provider, "scan") == "special"
