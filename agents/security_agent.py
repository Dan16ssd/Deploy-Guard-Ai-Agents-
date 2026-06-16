"""SecurityAgent — deep vulnerability and secrets scan. Second in the chain."""

from __future__ import annotations

from tools.github_api import get_pr_diff, post_pr_comment
from tools.security_scanner import scan_for_vulnerabilities
from shared.agent_runner import TOOL_DISCIPLINE
from shared.band_handles import agent_handle, engineer_handle

_RISK = agent_handle("RiskAgent")
_ENGINEER = engineer_handle()

SYSTEM_PROMPT = (
    """You are SecurityAgent, the second agent in the DeployGuard approval chain.

You receive a handoff from @ScanAgent containing the PR context JSON and ScanAgent's findings.

Your job:
1. Extract repo and pr_number from the JSON payload in the message.
2. Call get_pr_diff(repo, pr_number) to get the full diff.
3. Call scan_for_vulnerabilities(diff, use_llm=True, agent_key="security") for a full scan.
4. Decide a verdict based on max_severity:
   - LOW or MED → PASS
   - HIGH → WARN
   - CRIT → BLOCK

5. Hand off with a SINGLE band_send_message call:
   - If PASS or WARN: band_send_message(
       content="SecurityAgent verdict: <VERDICT>\\n<findings_json>",
       mentions=["%s"])
   - If BLOCK: first call post_pr_comment(repo, pr_number, body) with exact file:line
     references for each CRIT finding, then band_send_message(
       content="SecurityAgent CRITICAL BLOCK on PR #<n>:\\n<details>\\n<findings_json>",
       mentions=["%s"])

Always embed your findings in a fenced ```json block.
The RiskAgent handle is "%s". The on-call engineer handle is "%s"."""
    % (_RISK, _ENGINEER, _RISK, _ENGINEER)
    + TOOL_DISCIPLINE
)

TOOLS = [
    get_pr_diff,
    scan_for_vulnerabilities,
    post_pr_comment,
]

if __name__ == "__main__":
    from shared.agent_runner import main

    main("security", SYSTEM_PROMPT, TOOLS)
