"""LangChain tool: run pytest and return pass/fail summary."""

from __future__ import annotations

import subprocess

from langchain_core.tools import tool


@tool
def run_tests(test_dir: str = "tests") -> dict:
    """Run pytest against test_dir and return summary.

    Returns: {"passed": int, "failed": int, "errors": int, "summary": str, "ok": bool}
    """
    result = subprocess.run(
        ["pytest", test_dir, "-q", "--tb=no", "--no-header"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    stdout = result.stdout + result.stderr
    passed, failed, errors = _parse_pytest_output(stdout)
    return {
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "summary": stdout.strip()[-500:],
        "ok": failed == 0 and errors == 0,
    }


def _parse_pytest_output(output: str) -> tuple[int, int, int]:
    import re

    passed = failed = errors = 0
    for line in output.splitlines():
        m = re.search(r"(\d+) passed", line)
        if m:
            passed = int(m.group(1))
        m = re.search(r"(\d+) failed", line)
        if m:
            failed = int(m.group(1))
        m = re.search(r"(\d+) error", line)
        if m:
            errors = int(m.group(1))
    return passed, failed, errors
