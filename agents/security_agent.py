"""SecurityAgent — deep vulnerability and secrets scan. Second in the chain."""

from __future__ import annotations

from tools.security_scanner import security_review
from shared.agent_runner import TOOL_DISCIPLINE
from shared.band_handles import agent_handle, engineer_handle

_RISK = agent_handle("RiskAgent")
_ENGINEER = engineer_handle()

SYSTEM_PROMPT = (
    """You are SecurityAgent, the second agent in the DeployGuard approval chain.

You receive a handoff from @ScanAgent containing the PR context JSON.

Follow these steps EXACTLY — do not improvise, do not skip, do not add extra tool calls:

1. Read `repo` and `pr_number` from the JSON payload in the message.
2. Call `security_review(repo, pr_number)` ONE time. This single tool does everything:
   it fetches the diff, scans for vulnerabilities, and — if the verdict is BLOCK — it has
   ALREADY posted the CRITICAL findings as a PR comment for you. You do NOT post comments
   yourself. The tool returns: verdict, max_severity, findings, comment_url, summary, handoff.
3. Make ONE `band_send_message` call to hand off:
   - content = "SecurityAgent verdict: <verdict> — <summary>" followed by the findings in a
     fenced ```json block.
   - mentions = [ the value of the tool's `handoff` field ] — use it EXACTLY as returned
     (it is the on-call engineer on BLOCK, or RiskAgent otherwise).
4. Stop. You are done.

Never call `security_review` more than once. Never send more than one message.
RiskAgent handle: "%s". On-call engineer: "%s"."""
    % (_RISK, _ENGINEER)
    + TOOL_DISCIPLINE
)

TOOLS = [security_review]

if __name__ == "__main__":
    from shared.agent_runner import main

    main("security", SYSTEM_PROMPT, TOOLS)
