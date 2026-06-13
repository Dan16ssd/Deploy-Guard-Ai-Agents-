"""LangChain tool: run pip-audit and return CVE findings."""

from __future__ import annotations

import json
import subprocess

from langchain_core.tools import tool


@tool
def audit_dependencies(requirements_file: str = "requirements.txt") -> dict:
    """Run pip-audit on a requirements file and return CVE findings.

    Returns: {"cve_count": int, "cves": list[str], "summary": str}
    """
    result = subprocess.run(
        [
            "pip-audit",
            "-r",
            requirements_file,
            "--format=json",
            "--progress-spinner=off",
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    cves: list[str] = []
    summary = ""
    try:
        data = json.loads(result.stdout or "[]")
        for dep in data:
            for vuln in dep.get("vulns", []):
                vid = vuln.get("id", "")
                desc = vuln.get("description", "")[:120]
                cves.append(
                    f"{dep.get('name', '?')} {dep.get('version', '?')}: {vid} — {desc}"
                )
    except (json.JSONDecodeError, TypeError):
        summary = (result.stdout + result.stderr).strip()[-300:]

    return {
        "cve_count": len(cves),
        "cves": cves,
        "summary": summary or f"{len(cves)} CVE(s) found",
    }
