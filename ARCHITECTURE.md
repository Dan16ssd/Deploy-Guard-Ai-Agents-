# DeployGuard — Architecture & Pipeline

DeployGuard is a multi-agent CI/CD security gate. When a pull request is opened, a GitHub
webhook spins up a [Band](https://band.ai) chat room where **five specialist AI agents**
review the change in sequence — linting, scanning for vulnerabilities, scoring risk, and
deciding whether to deploy — with a human on-call engineer in the loop for escalations.

## End-to-end pipeline

```mermaid
flowchart TD
    Dev([Developer opens / updates PR]) --> GH[GitHub: pull_request event]
    GH -->|"webhook POST + HMAC-SHA256 signature"| WH["FastAPI Webhook<br/>(Railway)"]
    WH --> V{"Signature valid<br/>& base branch = main?"}
    V -->|no| Drop["Ignore (202) / reject (401)"]
    V -->|yes| Room["Create Band room<br/>add 5 agents + on-call engineer<br/>post opening @ScanAgent"]
    Room --> Scan

    subgraph BAND["🟣 Band multi-agent chat room"]
        direction TB
        Scan["🔍 ScanAgent<br/>lint · tests · dependency audit"] --> ScanV{verdict}
        ScanV -->|PASS / WARN| Sec["🛡️ SecurityAgent<br/>vuln + secrets scan (regex + LLM)"]
        ScanV -->|BLOCK| Eng

        Sec --> SecV{max severity}
        SecV -->|"LOW/MED → PASS<br/>HIGH → WARN"| Risk["⚖️ RiskAgent<br/>weighted risk score 0–100"]
        SecV -->|"CRIT → BLOCK"| SecCmt["Post CRITICAL PR comment<br/>(file:line)"] --> Eng

        Risk --> RiskV{"risk score"}
        RiskV -->|"< 71 → PASS"| Deploy["🚀 DeployAgent"]
        RiskV -->|"≥ 71 → ESCALATE"| Eng["👤 On-call Engineer<br/>(human, in-chat)"]
        Eng -->|"reply APPROVE"| Deploy
        Eng -->|"reply REJECT"| Report

        Deploy --> Trig["Trigger GitHub Actions<br/>workflow_dispatch + poll"]
        Trig --> Report["📋 ReportAgent<br/>assemble audit trail"]
    end

    SecCmt -.-> PRc[["PR comments"]]
    Trig -.deploy result.-> PRc
    Report --> Audit["Post audit summary<br/>(PR comment + Band)"]
    Audit --> PRc
    Report --> Done([Chain complete])
```

## The agents

| # | Agent | Tools | Decision |
|---|-------|-------|----------|
| 1 | 🔍 **ScanAgent** | `github_api`, `static_analyzer` (ruff), `test_runner` (pytest), `dep_auditor` (pip-audit) | hand off to SecurityAgent, or **BLOCK** to engineer |
| 2 | 🛡️ **SecurityAgent** | `security_scanner` (regex + LLM), `github_api` | LOW/MED → PASS, HIGH → WARN → RiskAgent; **CRIT → BLOCK** + PR comment → engineer |
| 3 | ⚖️ **RiskAgent** | `risk_scorer` (weighted heuristics) | score `< 71` → DeployAgent; score `≥ 71` → **ESCALATE** to engineer, await APPROVE/REJECT |
| 4 | 🚀 **DeployAgent** | `deploy_trigger` (`workflow_dispatch`), `github_api` | fire the real deploy **only if approved** → ReportAgent |
| 5 | 📋 **ReportAgent** | `github_api` | post the full audit trail; always runs last |

## Risk scoring (RiskAgent)

Weighted heuristics → a 0–100 score; **≥ 71 escalates to a human**:

| Signal | Weight |
|--------|--------|
| Auth-related files changed | +30 |
| Payment-related files changed | +40 |
| Friday deploy | +15 |
| Diff > 500 lines | +10 |
| Each upstream WARN | +5 (cap 20) |

## Two paths through the chain

- **Clean PR (happy path):** `Scan → Security → Risk → Deploy → Report` — ends in a real deployment and an audit comment.
- **Risky / vulnerable PR (block path):** the chain **stops early** — a CRIT finding blocks the deploy and escalates to the engineer, who can `APPROVE`/`REJECT` in the same chat.

## Tech stack

| Layer | Technology |
|-------|------------|
| Multi-agent orchestration | **Band** (agent chat + `@mention` hand-offs) |
| Agent runtime | **LangGraph** ReAct agents |
| LLMs | **Featherless** (Qwen models) |
| Ingress | **FastAPI** webhook (HMAC-verified) |
| Source / CI | **GitHub** PRs + Actions (`workflow_dispatch`) |
| Hosting | **Railway** (2 services: `webhook` + `agents`) |

## Deployment topology

```mermaid
flowchart LR
    GH["GitHub repo<br/>(pull requests)"] -->|webhook| WHS["Railway: webhook service<br/>python -m webhook.main"]
    WHS -->|"create room + @ScanAgent"| BANDP["Band platform"]
    AGS["Railway: agents service<br/>python -m run_all_agents<br/>(5 agents, 1 process)"] <-->|WebSocket| BANDP
    AGS -->|"PR comments · deploy trigger"| GH
```
