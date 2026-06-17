"""DeployAgent — fires the real GitHub Actions deployment. Fourth in the chain."""

from __future__ import annotations

from shared.agent_runner import TOOL_DISCIPLINE
from shared.band_handles import agent_handle
from tools.deploy_trigger import trigger_deployment
from tools.github_api import post_pr_comment

_REPORT = agent_handle("ReportAgent")

SYSTEM_PROMPT = (
    """You are DeployAgent, the fourth agent in the DeployGuard approval chain.

You ONLY activate on a green-light (PASS / human APPROVE) handoff from @RiskAgent. Follow
these steps EXACTLY — do not improvise:

1. Read `head_branch` from the JSON payload (and repo, pr_number).
2. Call `trigger_deployment(ref=head_branch)` ONE time. It fires the GitHub Actions deploy
   and polls until it finishes; it returns the deploy result (status + run URL).
3. Make ONE `band_send_message` call:
   - content = "DeployAgent: deployment <status>" + the deploy result in a fenced ```json block
   - mentions = ["%s"]   (ReportAgent — always hand off so the audit gets posted)
4. Stop. One tool call, one message, done.

ReportAgent handle: "%s".""" % (_REPORT, _REPORT) + TOOL_DISCIPLINE
)

TOOLS = [trigger_deployment, post_pr_comment]

if __name__ == "__main__":
    from shared.agent_runner import main

    main("deploy", SYSTEM_PROMPT, TOOLS)
