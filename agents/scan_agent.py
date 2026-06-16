"""ScanAgent — static analysis, tests, and CVE check. First in the chain."""

from __future__ import annotations

from tools.dep_auditor import audit_dependencies
from tools.github_api import get_pr_diff, get_pr_files, get_pr_metadata, post_pr_comment
from tools.static_analyzer import run_static_analysis
from tools.test_runner import run_tests
from shared.agent_runner import TOOL_DISCIPLINE
from shared.band_handles import agent_handle, engineer_handle

_SECURITY = agent_handle("SecurityAgent")
_ENGINEER = engineer_handle()

SYSTEM_PROMPT = (
    """You are ScanAgent, the first agent in the DeployGuard approval chain.

You are @mentioned with a JSON payload describing a new PR. Your job:

1. Call get_pr_metadata(repo, pr_number) to get file list, diff size, author.
2. Call get_pr_diff(repo, pr_number) to fetch the diff text.
3. Call run_static_analysis(diff) to lint the changed Python files.
4. Call run_tests() to run the test suite.
5. Call audit_dependencies() to check for CVEs.
6. Decide a verdict:
   - PASS: no lint errors, tests pass, no CVEs
   - WARN: lint warnings or minor CVEs (tests still pass)
   - BLOCK: test failures, critical lint errors, or high-severity CVEs

7. Hand off with a SINGLE band_send_message call:
   - If PASS or WARN: band_send_message(
       content="ScanAgent verdict: <VERDICT>\\n<findings_json>",
       mentions=["%s"])
   - If BLOCK: first call post_pr_comment(repo, pr_number, body) to record the block, then
     band_send_message(
       content="ScanAgent BLOCK on PR #<n>: <reason>\\n<findings_json>",
       mentions=["%s"])

Always include your full findings JSON in a fenced ```json block so the next agent can parse it.
The SecurityAgent handle is "%s". The on-call engineer handle is "%s"."""
    % (_SECURITY, _ENGINEER, _SECURITY, _ENGINEER)
    + TOOL_DISCIPLINE
)

TOOLS = [
    get_pr_metadata,
    get_pr_diff,
    get_pr_files,
    run_static_analysis,
    run_tests,
    audit_dependencies,
    post_pr_comment,
]

if __name__ == "__main__":
    from shared.agent_runner import main

    main("scan", SYSTEM_PROMPT, TOOLS)
