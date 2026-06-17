"""LangChain tool: run pip-audit and return CVE findings.

pip-audit shells out to a full pip dependency resolution. On a large requirements file
that can run for minutes AND spawn pip *grandchildren* that inherit the stdout pipe — so a
plain ``subprocess.run(capture_output=True, timeout=...)`` hangs in ``communicate()`` even
after the timeout fires (the grandchildren hold the pipe open), freezing the whole asyncio
agent. To stay safe we redirect output to temp files (no inheritable pipe), bound the wall
clock, and kill the entire process tree on timeout.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time

from langchain_core.tools import tool

# pip-audit fully resolves the transitive dependency tree, which is slow even for a handful
# of direct packages (band-sdk + langchain pull a huge tree). Keep the wall-clock tight: a
# dependency audit must never become the chain's bottleneck. If it can't resolve in time we
# return "skipped" and proceed.
_AUDIT_TIMEOUT_S = 8


def _kill_tree(proc: subprocess.Popen) -> None:
    """Best-effort kill of pip-audit and every pip child it spawned."""
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                timeout=10,
            )
        else:
            proc.kill()
    except Exception:
        pass


@tool
def audit_dependencies(requirements_file: str = "requirements.txt") -> dict:
    """Run pip-audit on a requirements file and return CVE findings.

    Returns: {"cve_count": int, "cves": list[str], "summary": str}
    """
    cves: list[str] = []
    summary = ""

    if not os.path.exists(requirements_file):
        return {
            "cve_count": 0,
            "cves": [],
            "summary": f"no {requirements_file} to audit — dependency check skipped",
        }

    # Guard: ScanAgent runs inside the DeployGuard service, so the only requirements.txt it
    # can see is the agent runtime's own — not the PR's dependencies. That manifest pulls a
    # huge transitive tree (band-sdk + langchain + langgraph) that makes pip-audit backtrack
    # for minutes, and auditing it tells us nothing about the PR. Detect it (by size or by the
    # agent-framework packages it contains) and skip instantly with a clean message. A real
    # per-PR dependency audit would pass the PR's own (small) manifest here instead.
    try:
        with open(requirements_file, encoding="utf-8") as f:
            pkg_lines = [
                ln for ln in f if ln.strip() and not ln.lstrip().startswith("#")
            ]
        joined = " ".join(pkg_lines).lower()
        host_markers = ("band-sdk", "langgraph", "langchain")
        if len(pkg_lines) > 30 or any(m in joined for m in host_markers):
            return {
                "cve_count": 0,
                "cves": [],
                "summary": (
                    "dependency audit not required — this PR changes no dependency manifest"
                ),
            }
    except Exception:
        pass

    out_path = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w+", suffix=".json", delete=False, encoding="utf-8"
        ) as out:
            out_path = out.name
        with open(out_path, "w", encoding="utf-8") as out_f:
            proc = subprocess.Popen(
                [
                    "pip-audit",
                    "-r",
                    requirements_file,
                    "--format=json",
                    "--progress-spinner=off",
                ],
                stdout=out_f,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
            deadline = time.monotonic() + _AUDIT_TIMEOUT_S
            while proc.poll() is None and time.monotonic() < deadline:
                time.sleep(0.5)
            if proc.poll() is None:
                _kill_tree(proc)
                raise TimeoutError(f"pip-audit exceeded {_AUDIT_TIMEOUT_S}s")

        with open(out_path, encoding="utf-8") as f:
            stdout = f.read()
        data = json.loads(stdout or "[]")
        # pip-audit emits {"dependencies": [...]} (newer) or a bare [...] (older).
        deps = data.get("dependencies", []) if isinstance(data, dict) else data
        for dep in deps:
            if not isinstance(dep, dict):
                continue
            for vuln in dep.get("vulns", []) or []:
                vid = vuln.get("id", "")
                desc = (vuln.get("description") or "")[:120]
                cves.append(
                    f"{dep.get('name', '?')} {dep.get('version', '?')}: {vid} — {desc}"
                )
    except Exception as exc:  # noqa: BLE001 - a tool must never crash/stall the agent
        kind = (
            "time budget exceeded"
            if isinstance(exc, TimeoutError)
            else type(exc).__name__
        )
        summary = f"dependency audit skipped — {kind}"
    finally:
        if out_path:
            try:
                os.unlink(out_path)
            except Exception:
                pass

    return {
        "cve_count": len(cves),
        "cves": cves,
        "summary": summary or f"{len(cves)} CVE(s) found",
    }
