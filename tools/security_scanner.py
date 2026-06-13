"""LangChain tool: regex + LLM security scan of a PR diff.

Regex pass catches OWASP-top-10 patterns and secrets with file+line attribution.
LLM pass does a deeper read of the full diff for anything the regex misses.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from langchain_core.tools import tool

from shared.context_schema import Finding
from shared.verdict import SEVERITY_TO_VERDICT, Severity, Verdict

if TYPE_CHECKING:
    pass

# (pattern, description, severity)
_PATTERNS: list[tuple[str, str, Severity]] = [
    # SQL injection — string concatenation
    (
        r'"[^"\n]*(?:SELECT|UPDATE|DELETE|INSERT|WHERE|FROM)[^"\n]*"\s*\+',
        "SQL injection: SQL string built via concatenation",
        Severity.CRIT,
    ),
    # SQL injection — Python %-formatting with 'quoted %s'
    (
        r"\"[^\"]*'%s'[^\"]*\"",
        "SQL injection: SQL string uses '%s' string-format style (not parameterized)",
        Severity.CRIT,
    ),
    # SQL injection — f-string
    (
        r'f["\'][^"\']*(?:SELECT|UPDATE|DELETE|INSERT|WHERE|FROM)[^"\']*\{',
        "SQL injection: SQL f-string with interpolated variable",
        Severity.CRIT,
    ),
    # execute() called with a plain variable (not a literal tuple)
    (
        r'\.execute\s*\(\s*(?:query|sql|stmt|cmd|q)\b',
        "SQL execute() called with a variable — verify parameterization",
        Severity.HIGH,
    ),
    # Hardcoded secret-looking assignments
    (
        r'(?:password|passwd|pwd|secret|api_key|apikey|auth_token)\s*=\s*["\'][^"\']{6,}["\']',
        "Hardcoded credential or secret",
        Severity.HIGH,
    ),
    # AWS access key
    (r"AKIA[0-9A-Z]{16}", "Hardcoded AWS access key", Severity.CRIT),
    # Private key header
    (
        r"-----BEGIN (?:RSA|EC|DSA|OPENSSH) PRIVATE KEY-----",
        "Hardcoded private key",
        Severity.CRIT,
    ),
    # Command injection via string concat
    (
        r'(?:os\.system|subprocess\.(?:call|run|Popen))\s*\([^)]*\+',
        "Command injection: shell call built via string concatenation",
        Severity.HIGH,
    ),
    # Path traversal — user input in open()
    (
        r'open\s*\([^)]*(?:request\.|form\[|args\[|params\[|user)',
        "Path traversal: user-controlled input passed to open()",
        Severity.HIGH,
    ),
]


def scan_diff_regex(diff: str) -> list[Finding]:
    """Apply regex patterns to added lines in a unified diff."""
    findings: list[Finding] = []
    current_file: str | None = None
    current_line = 0

    for raw_line in diff.splitlines():
        if raw_line.startswith("+++ b/"):
            current_file = raw_line[6:]
            current_line = 0
        elif raw_line.startswith("@@ "):
            m = re.search(r"\+(\d+)", raw_line)
            current_line = int(m.group(1)) - 1 if m else 0
        elif raw_line.startswith("+") and not raw_line.startswith("+++"):
            current_line += 1
            content = raw_line[1:]
            for pattern, desc, sev in _PATTERNS:
                if re.search(pattern, content):
                    findings.append(
                        Finding(
                            file=current_file or "unknown",
                            line=current_line,
                            rule=pattern[:40],
                            message=desc,
                            severity=sev,
                        )
                    )
        elif not raw_line.startswith("-"):
            current_line += 1

    return findings


def _max_severity(findings: list[Finding]) -> Severity:
    if not findings:
        return Severity.LOW
    return max(findings, key=lambda f: f.severity.rank).severity


@tool
def scan_for_vulnerabilities(diff: str, use_llm: bool = False, agent_key: str = "security") -> dict:
    """Scan a PR diff for security vulnerabilities.

    Runs regex patterns for OWASP top-10 + secrets (always), then optionally an
    LLM deep-scan pass (set use_llm=True when running inside SecurityAgent).

    Returns: {"verdict": str, "max_severity": str, "findings": list, "notes": str}
    """
    findings = scan_diff_regex(diff)

    llm_notes = ""
    if use_llm and diff.strip():
        llm_notes = _llm_scan(diff, agent_key)

    max_sev = _max_severity(findings)
    verdict = SEVERITY_TO_VERDICT.get(max_sev, Verdict.PASS)

    return {
        "verdict": verdict.value,
        "max_severity": max_sev.value,
        "findings": [f.model_dump() for f in findings],
        "notes": llm_notes,
    }


def _llm_scan(diff: str, agent_key: str) -> str:
    """Ask an LLM to review the diff for security issues not caught by regex."""
    try:
        from shared.llm_factory import build_llm
        llm = build_llm(agent_key)
        prompt = (
            "You are a security code reviewer. Analyse this git diff for security "
            "vulnerabilities (OWASP Top 10, secrets, injection, broken auth, etc.). "
            "Be concise. List only HIGH or CRITICAL issues with file:line and explanation.\n\n"
            f"```diff\n{diff[:6000]}\n```"
        )
        response = llm.invoke(prompt)
        return response.content if hasattr(response, "content") else str(response)
    except Exception as exc:
        return f"LLM scan skipped: {exc}"
