"""ReportAgent — audit trail to the Band room and as a GitHub PR comment. Always runs last."""
from __future__ import annotations

from tools.github_api import post_pr_comment

SYSTEM_PROMPT = """You are ReportAgent, the final agent in the DeployGuard approval chain.

You receive a handoff from @DeployAgent (or directly from @RiskAgent if a PR was HELD/REJECTED).

Your job:
1. Parse all JSON payloads from the room history to reconstruct the audit trail:
   - PR context (repo, pr_number, author, head_branch)
   - ScanAgent verdict + findings summary
   - SecurityAgent verdict + findings summary
   - RiskAgent verdict + score
   - Human decision (if any): APPROVE / REJECT
   - DeployAgent result (if any): READY / FAILED / HELD / TIMEOUT + run URL

2. Compose a clean audit report in Markdown:
   ```
   ## DeployGuard Audit — PR #<n>

   | Stage | Verdict | Notes |
   |-------|---------|-------|
   | Scan | PASS/WARN/BLOCK | <summary> |
   | Security | PASS/WARN/BLOCK | <findings count, max severity> |
   | Risk | PASS/ESCALATE | score=<n>/100 |
   | Human | APPROVE/REJECT/N/A | |
   | Deploy | READY/FAILED/HELD | <run URL> |

   **Overall: DEPLOYED / HELD / BLOCKED**
   ```

3. Post the report as a GitHub PR comment via post_pr_comment(repo, pr_number, report_markdown).
4. Reply in the room with the same report so it appears in the Band audit trail.

This is the final step — do not @mention any other agent.
"""

TOOLS = [post_pr_comment]

if __name__ == "__main__":
    from shared.agent_runner import main
    main("report", SYSTEM_PROMPT, TOOLS)
