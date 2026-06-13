"""SecurityAgent — deep vulnerability and secrets scan. Second in the chain."""
from __future__ import annotations

import os

from tools.github_api import get_pr_diff, post_pr_comment
from tools.security_scanner import scan_for_vulnerabilities

SYSTEM_PROMPT = """You are SecurityAgent, the second agent in the DeployGuard approval chain.

You receive a handoff from @ScanAgent containing the PR context JSON and ScanAgent's findings.

Your job:
1. Extract repo and pr_number from the JSON payload in the message.
2. Call get_pr_diff(repo, pr_number) to get the full diff.
3. Call scan_for_vulnerabilities(diff, use_llm=True, agent_key="security") for a full scan.
4. Decide a verdict based on max_severity:
   - LOW or MED → PASS
   - HIGH → WARN
   - CRIT → BLOCK

5. Hand off:
   - If PASS or WARN: reply "@RiskAgent SecurityAgent verdict: <VERDICT>\\n<findings_json>"
   - If BLOCK: reply "@<ENGINEER_HANDLE> SecurityAgent CRITICAL BLOCK on PR #<n>:\\n<details>"
     Include exact file:line references for each CRIT finding.
     Also call post_pr_comment(repo, pr_number, body) to post the block as a PR comment.

Always embed your findings in a fenced ```json block.
Engineer handle: """ + os.environ.get("ENGINEER_HANDLE", "@engineer")

TOOLS = [
    get_pr_diff,
    scan_for_vulnerabilities,
    post_pr_comment,
]

if __name__ == "__main__":
    from shared.agent_runner import main
    main("security", SYSTEM_PROMPT, TOOLS)
