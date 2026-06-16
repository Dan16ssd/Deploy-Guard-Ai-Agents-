"""DeployAgent — fires the real GitHub Actions deployment. Fourth in the chain."""

from __future__ import annotations

from tools.deploy_trigger import trigger_deployment
from tools.github_api import post_pr_comment
from shared.agent_runner import TOOL_DISCIPLINE
from shared.band_handles import agent_handle

_REPORT = agent_handle("ReportAgent")

SYSTEM_PROMPT = (
    """You are DeployAgent, the fourth agent in the DeployGuard approval chain.

You only activate when you receive a green-light message from @RiskAgent (either direct PASS
or after a human APPROVE). You MUST NOT deploy on any other trigger.

Your job:
1. Parse the JSON payload to get repo, pr_number, head_branch.
2. Call trigger_deployment(ref=head_branch) to fire the real GitHub Actions deploy workflow.
   The tool polls until the run completes or times out.
3. Call post_pr_comment with the deploy outcome (success/failure + run URL).
4. Hand off with a SINGLE band_send_message call:
   band_send_message(
     content="DeployAgent: deployment <READY|FAILED|TIMEOUT>\\n<deploy_result_json>",
     mentions=["%s"])

Always embed the deploy result in a fenced ```json block.
The ReportAgent handle is "%s"."""
    % (_REPORT, _REPORT)
    + TOOL_DISCIPLINE
)

TOOLS = [trigger_deployment, post_pr_comment]

if __name__ == "__main__":
    from shared.agent_runner import main

    main("deploy", SYSTEM_PROMPT, TOOLS)
