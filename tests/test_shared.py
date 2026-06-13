"""Unit tests for dependency-light shared logic (no Band/LLM/network required)."""

from __future__ import annotations

from shared.band_helpers import (
    compose_handoff,
    detect_human_decision,
    extract_json_payload,
    extract_mentions,
)
from shared.context_schema import PRContext, ScanFindings
from shared.verdict import SEVERITY_TO_VERDICT, HumanDecision, Severity, Verdict


def test_severity_ranking_is_ordered():
    assert (
        Severity.LOW.rank < Severity.MED.rank < Severity.HIGH.rank < Severity.CRIT.rank
    )


def test_severity_to_verdict_mapping():
    assert SEVERITY_TO_VERDICT[Severity.LOW] is Verdict.PASS
    assert SEVERITY_TO_VERDICT[Severity.MED] is Verdict.PASS
    assert SEVERITY_TO_VERDICT[Severity.HIGH] is Verdict.WARN
    assert SEVERITY_TO_VERDICT[Severity.CRIT] is Verdict.BLOCK


def test_compose_and_roundtrip_handoff():
    payload = {"verdict": "PASS", "cve_count": 0, "cves": []}
    msg = compose_handoff("SecurityAgent", "scan complete", payload)
    assert extract_mentions(msg) == ["SecurityAgent"]
    assert extract_json_payload(msg) == payload


def test_extract_mentions_multiple():
    assert extract_mentions("@RiskAgent and @dan please review") == ["RiskAgent", "dan"]


def test_detect_human_decision():
    assert detect_human_decision("Looks fine, APPROVE") is HumanDecision.APPROVE
    assert detect_human_decision("no, REJECT this") is HumanDecision.REJECT
    assert detect_human_decision("just override it") is HumanDecision.OVERRIDE
    assert detect_human_decision("please fix") is HumanDecision.FIX
    assert detect_human_decision("hello there") is None


def test_pr_context_diff_size():
    pr = PRContext(
        repo="o/r",
        pr_number=47,
        author="dan",
        head_branch="feat",
        additions=600,
        deletions=12,
    )
    assert pr.diff_size == 612


def test_scan_findings_defaults():
    sf = ScanFindings(verdict=Verdict.PASS)
    assert sf.tests_passed is None
    assert sf.cve_count == 0
    assert sf.lint_issues == []
