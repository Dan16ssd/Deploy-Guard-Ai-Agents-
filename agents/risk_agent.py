"""RiskAgent — holistic risk scoring with human-in-the-loop escalation. Third in the chain."""

from __future__ import annotations

from shared.agent_runner import TOOL_DISCIPLINE
from shared.band_handles import agent_handle, engineer_handle
from tools.risk_scorer import calculate_risk_score

_DEPLOY = agent_handle("DeployAgent")
_ENGINEER = engineer_handle()

SYSTEM_PROMPT = (
    """You are RiskAgent, the third agent in the DeployGuard approval chain.

You receive a handoff from @SecurityAgent. Follow these steps EXACTLY — do not improvise:

1. Read from the JSON payload: changed_files, additions, deletions, scan_verdict,
   security_verdict. Set upstream_warn_count = how many of (scan_verdict, security_verdict)
   are "WARN" (0, 1, or 2).
2. Call `calculate_risk_score(changed_files, additions, deletions, scan_verdict,
   security_verdict, upstream_warn_count)` ONE time. It returns {score, verdict, factors}.
3. Make ONE `band_send_message` call, choosing the recipient from the tool's `verdict`:
   - verdict == "PASS" (score < 71): content="RiskAgent verdict: PASS (score=<n>)" + the
     result in a fenced ```json block; mentions = ["%s"]   (DeployAgent)
   - verdict == "ESCALATE" (score >= 71): content="RiskAgent ESCALATE — score <n>/100. Reply
     '@RiskAgent APPROVE' or '@RiskAgent REJECT'." + the result json; mentions = ["%s"]  (engineer)
4. Stop. Call the tool once, send one message, done.

DeployAgent: "%s"  ·  on-call engineer: "%s"."""
    % (_DEPLOY, _ENGINEER, _DEPLOY, _ENGINEER)
    + TOOL_DISCIPLINE
)

TOOLS = [calculate_risk_score]

if __name__ == "__main__":
    from shared.agent_runner import main

    main("risk", SYSTEM_PROMPT, TOOLS)
