"""Pydantic payloads passed between agents through the Band chain.

Each agent emits a structured block (serialized into its @mention message) that the
next agent parses back out. Keeping these as models gives us validation + a single
source of truth for the audit trail ReportAgent reconstructs.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from .verdict import Severity, Verdict


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PRContext(BaseModel):
    """Extracted from the GitHub webhook; seeds the whole chain."""

    repo: str  # "owner/name"
    pr_number: int
    title: str = ""
    author: str
    base_branch: str = "main"
    head_branch: str
    head_sha: str = ""
    diff_url: str = ""
    changed_files: list[str] = Field(default_factory=list)
    additions: int = 0
    deletions: int = 0

    @property
    def diff_size(self) -> int:
        return self.additions + self.deletions


class Finding(BaseModel):
    """One issue located in the diff."""

    file: str
    line: int | None = None
    rule: str = ""
    message: str
    severity: Severity = Severity.LOW


class ScanFindings(BaseModel):
    verdict: Verdict
    lint_issues: list[Finding] = Field(default_factory=list)
    tests_passed: bool | None = None
    test_summary: str = ""
    cve_count: int = 0
    cves: list[str] = Field(default_factory=list)
    diff_too_large: bool = False
    notes: str = ""


class SecurityFindings(BaseModel):
    verdict: Verdict
    max_severity: Severity = Severity.LOW
    findings: list[Finding] = Field(default_factory=list)
    notes: str = ""


class RiskReport(BaseModel):
    verdict: Verdict
    score: int = 0  # 0..100
    factors: dict[str, int] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)


class DeployResult(BaseModel):
    success: bool
    run_id: int | None = None
    run_url: str = ""
    status: str = ""  # "READY" | "FAILED" | "HELD" | "TIMEOUT"
    error: str = ""
    timestamp: datetime = Field(default_factory=_utcnow)


class AuditRecord(BaseModel):
    """What ReportAgent assembles at the end of the chain."""

    pr: PRContext
    scan: ScanFindings | None = None
    security: SecurityFindings | None = None
    risk: RiskReport | None = None
    human_decision: str = ""
    deploy: DeployResult | None = None
    completed_at: datetime = Field(default_factory=_utcnow)
