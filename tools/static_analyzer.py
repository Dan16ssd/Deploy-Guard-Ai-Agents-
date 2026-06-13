"""LangChain tool: run ruff on PR diff files and return structured findings."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from langchain_core.tools import tool

from shared.context_schema import Finding
from shared.verdict import Severity


@tool
def run_static_analysis(diff: str) -> dict:
    """Run ruff on added/modified Python content from a unified diff.

    Returns a dict with keys: findings (list), error_count, warning_count.
    """
    added_files = _extract_added_content(diff)
    if not added_files:
        return {"findings": [], "error_count": 0, "warning_count": 0}

    findings: list[Finding] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for filename, content in added_files.items():
            if not filename.endswith(".py"):
                continue
            fpath = Path(tmpdir) / Path(filename).name
            fpath.write_text(content, encoding="utf-8")
            result = subprocess.run(
                ["ruff", "check", "--output-format=json", str(fpath)],
                capture_output=True,
                text=True,
            )
            if result.stdout.strip():
                try:
                    issues = json.loads(result.stdout)
                except json.JSONDecodeError:
                    issues = []
                for issue in issues:
                    sev = (
                        Severity.HIGH
                        if issue.get("code", "").startswith("E")
                        else Severity.LOW
                    )
                    findings.append(
                        Finding(
                            file=filename,
                            line=issue.get("location", {}).get("row"),
                            rule=issue.get("code", ""),
                            message=issue.get("message", ""),
                            severity=sev,
                        )
                    )

    errors = sum(1 for f in findings if f.severity in (Severity.HIGH, Severity.CRIT))
    warnings = len(findings) - errors
    return {
        "findings": [f.model_dump() for f in findings],
        "error_count": errors,
        "warning_count": warnings,
    }


def _extract_added_content(diff: str) -> dict[str, str]:
    """Parse a unified diff and return {filename: added_lines_content}."""
    files: dict[str, list[str]] = {}
    current: str | None = None
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
            files.setdefault(current, [])
        elif current and line.startswith("+") and not line.startswith("+++"):
            files[current].append(line[1:])
    return {k: "\n".join(v) for k, v in files.items() if v}
