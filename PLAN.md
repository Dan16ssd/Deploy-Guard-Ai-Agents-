# DeployGuard — Implementation Plan

## Context

**Goal:** Build DeployGuard for the Band of Agents Hackathon (Track 2, deadline **Jun 19, 2026**): a multi-agent production-deployment safety system where a GitHub PR against `main` triggers a **sequential approval chain of 5 agents coordinating exclusively through Band @mentions**, with a human-in-the-loop escalation. The differentiator is that the chain is *structurally* impossible to bypass — remove Band and DeployAgent never gets its green light.

**Decisions locked in (from planning Q&A):**
- **Scope:** Full blueprint — webhook + 5 agents + Docker + Railway + full CI/CD + real deployment trigger.
- **LLM provider:** Open-source models via **Featherless** (primary) and **AI/ML API** (secondary), both OpenAI-compatible. Per-agent model assignment, provider-agnostic factory.
- **Deploy step:** **Real GitHub Actions** `workflow_dispatch` + run-status polling.
- **Starting state:** Nothing set up — plan includes all account/credential/repo setup.

**Current repo state:** `C:\Users\Danny\Desktop\deployguard` is **empty** and currently sits *inside* the home-directory git repo (`C:\Users\Danny`, whose commits are unrelated `*.py` algorithm files). First action must be to make this its own project + git repo.

---

## Phase 0 — Accounts, credentials & repo bootstrap (do first)

1. **New git repo here** (do NOT commit into the home repo):
   - `git init` in `deployguard/`, add a Python `.gitignore` (ignore `.env`, `__pycache__`, `.venv`).
   - Create a **new public GitHub repo** `deployguard` and set it as `origin`.
2. **Separate "target" GitHub repo** (the repo DeployGuard *watches*) — a tiny app repo where demo PRs are opened. It holds the deploy `workflow_dispatch` workflow.
3. **Register 5 agents at https://app.band.ai** → record `agent_id` + `api_key` for each: `ScanAgent`, `SecurityAgent`, `RiskAgent`, `DeployAgent`, `ReportAgent`. Also note the **service credential** used by the webhook to create rooms / post the opening message (a 6th non-agent identity or a Band REST token).
4. **LLM keys:** Featherless API key (`https://api.featherless.ai/v1`) and AI/ML API key (`https://api.aimlapi.com/v1`).
5. **GitHub token (PAT or App)** with `contents:read`, `pull_requests:write` (PR comments), and `actions:write` (workflow_dispatch). Store all secrets in `.env`; commit only `.env.example`.
6. **Python 3.11+ venv**, `pip install "band-sdk[langgraph]"` plus deps (see requirements below).

---

## Phase 1 — Integration spikes (DE-RISK before building features)

The Band docs are gated; three integration points are **unverified** and must be confirmed against the installed SDK **on Day 1**, because the whole architecture depends on them. Build a throwaway `spike/` script for each:

- **Spike A — Agent receives @mention & replies.** Stand up one agent with `Agent.create(adapter=LangGraphAdapter(llm=..., checkpointer=InMemorySaver()), agent_id=..., api_key=...)` + `await agent.run()`. In Band, @mention it; confirm it replies. Confirms WebSocket + adapter + LLM tool-calling all work.
- **Spike B — Custom tools.** Confirm *how the LangGraphAdapter accepts custom LangChain tools* (e.g. a `tools=[...]` arg, or passing a prebuilt ReAct graph). This determines how every `tools/*.py` is wired. Write tools as plain `@tool` functions so they attach either way.
- **Spike C — Programmatic room creation + post (no @mention trigger).** Confirm the Band **REST API** path the webhook uses to (a) create/open a room and (b) post the opening `@ScanAgent …` message from a non-agent service identity. This is what `band_initiator.py` needs.

> If B or C differ from assumptions, adjust the relevant module only — the chain design is unaffected.

**Verified SDK facts (from PyPI band-sdk 1.0.0):**
```python
from band import Agent
from band.adapters import LangGraphAdapter
from langgraph.checkpoint.memory import InMemorySaver
# llm = any LangChain chat model (ChatOpenAI pointed at Featherless/AI-ML API)
agent = Agent.create(adapter=adapter, agent_id=..., api_key=...)
await agent.run()
```
Agents wake on `message_created` when @mentioned; they reply / hand off via a `band_send_message(content, mentions)`-style chat tool using `@AgentName` syntax. **Chain logic lives in each agent's system prompt.**

---

## Architecture & module structure

Use the blueprint's layout. Each agent is a **persistent process**: a shared runner + a per-agent system prompt + a per-agent tool set + a per-agent model.

```
deployguard/
├── webhook/        main.py · verifier.py · parser.py · band_initiator.py
├── agents/         scan_agent.py · security_agent.py · risk_agent.py · deploy_agent.py · report_agent.py
├── tools/          github_api.py · static_analyzer.py · test_runner.py · dep_auditor.py
│                   security_scanner.py · risk_scorer.py · deploy_trigger.py
├── shared/         band_helpers.py · context_schema.py · verdict.py · chain_state.py
│                   llm_factory.py · agent_runner.py        # NEW: see below
├── tests/          test_*.py · fixtures/{sample_pr_payload.json, clean_pr_diff.txt, vuln_pr_diff.txt}
├── .github/workflows/  ci.yml · deploy.yml
├── docker-compose.yml · agent_config.yaml · requirements.txt · .env.example · README.md
```

**Two additions to the blueprint structure:**
- `shared/llm_factory.py` — maps an agent name → `(provider_base_url, api_key, model)` from `agent_config.yaml` + env, returns a configured `ChatOpenAI`. Lets each agent use a different open-source model on Featherless or AI/ML API without code changes.
- `shared/agent_runner.py` — the one shared `Agent.create(...).run()` bootstrap; each `agents/*.py` just supplies `{system_prompt, tools, model_key}`. Avoids 5x duplicated SDK plumbing.

---

## The 5 agents (system-prompt-driven chain)

Each prompt ends with an explicit hand-off instruction so the LLM emits the right `@mention`. Verdict vocabulary lives in `shared/verdict.py` (`PASS/WARN/BLOCK/ESCALATE`). Structured payloads passed between agents use `shared/context_schema.py` (Pydantic: `PRContext`, `ScanFindings`, `SecurityFindings`, `RiskReport`, `DeployResult`).

| Agent | Model (open-source) | Tools | Hand-off rule |
|---|---|---|---|
| **ScanAgent** | Qwen3-Coder-30B (Featherless) | `github_api`, `static_analyzer`, `test_runner`, `dep_auditor` | PASS/WARN → `@SecurityAgent` + findings JSON; BLOCK → `@{engineer}` |
| **SecurityAgent** | large coder model, e.g. Qwen3-Coder-480B (Featherless) or 235B via AI/ML API | `github_api`, `security_scanner` | LOW/MED→PASS, HIGH→WARN → `@RiskAgent`; CRIT → `@{engineer}` BLOCK |
| **RiskAgent** | Qwen3-235B (judgment) | `risk_scorer` | score<71 → `@DeployAgent`; ≥71 → `@{engineer}` ESCALATE then waits |
| **DeployAgent** | Qwen3-8B (mechanical) | `deploy_trigger`, `github_api` | activates only on green light → triggers Actions → `@ReportAgent` |
| **ReportAgent** | Qwen3-30B (writing) | `github_api` | always last → audit report to room + PR comment |

**Human-in-the-loop:** RiskAgent's escalation message instructs the engineer to reply **`@RiskAgent APPROVE`** or **`@RiskAgent REJECT`** (the reply must @mention the agent so Band wakes it). On APPROVE, RiskAgent @mentions `@DeployAgent`; on REJECT it @mentions `@ReportAgent` to log a held deploy. Same pattern for the `override`/`fix` reply on a BLOCK.

**State:** Band delivers room history to each agent, so the transcript *is* the primary chain state. `shared/chain_state.py` stays lightweight — a per-room guard to ignore duplicate/already-processed messages and record which stages completed.

---

## Tools (the real work; LLM only orchestrates)

- `tools/github_api.py` — PyGithub + REST: fetch PR diff/files, post PR comment, read PR metadata, trigger `workflow_dispatch`, poll run status. Reused by Scan/Security/Deploy/Report.
- `tools/static_analyzer.py` — run `ruff` (and `eslint` if JS) via subprocess on changed files; parse to structured findings.
- `tools/test_runner.py` — `pytest`/`jest` via subprocess; parse pass/fail. (Note: running tests needs the PR checked out; for the demo, scope to "run against checked-out head or skip gracefully if no suite.")
- `tools/dep_auditor.py` — `pip-audit` / `npm audit` for CVEs.
- `tools/security_scanner.py` — **the star**: regex patterns for OWASP-top-10 + hardcoded secrets (catches the planted SQL-injection in `vuln_pr_diff.txt`) **plus** an LLM deep-scan pass over the diff. Returns severity LOW/MED/HIGH/CRIT with file+line.
- `tools/risk_scorer.py` — weighted score 0–100: auth touched +30, payments +40, Friday +15, diff>500 lines +10, each upstream WARN +5.
- `tools/deploy_trigger.py` — **real GitHub Actions**: POST `workflow_dispatch` to the target repo's `deploy.yml`, then poll `actions/runs` every ~10s until `completed`/`failure` or 5-min timeout.

---

## Trigger — FastAPI webhook (`webhook/`)

- `main.py` — `POST /webhook` (GitHub `pull_request` events: `opened`, `synchronize`, base=`main`) + `GET /health`.
- `verifier.py` — HMAC-SHA256 of raw body vs `X-Hub-Signature-256` using the webhook secret. Reject mismatches.
- `parser.py` — extract PR number, diff URL, author, base/head branch, repo full name.
- `band_initiator.py` — via Band REST (Spike C): create room `PR-{number}-deployguard`, post opening message `@ScanAgent new PR #{n} by {author} targeting main — begin safety review: {pr_context_json}`. That single message fires the chain.
- **Dev exposure:** `ngrok http 8000`; point the target repo's webhook at the ngrok HTTPS URL. **Prod:** Railway public URL.

---

## Deployment, CI/CD, packaging

- **`docker-compose.yml`** — 6 services (webhook + 5 agents), each its own process, shared `.env`. One-command local bring-up.
- **Railway (prod):** 6 services from the same repo (Railway has no compose; define one service per process via `railway.json`/service config or a `Procfile`-style entry per agent). Health: `GET /health` 200 + all 5 agent WebSocket connections alive. The webhook service is the only public one.
- **`.github/workflows/ci.yml`** (every push/PR): `ruff` + `black --check`, `mypy`, `pytest` (mock Band client + fixtures), webhook HMAC test (POST `sample_pr_payload.json`, assert Band initiator called), docker build check.
- **`.github/workflows/deploy.yml`** (merge to `main`): full CI → build image → push to GHCR → trigger Railway redeploy → health check. **This same `deploy.yml` (or a copy in the target repo) is what DeployAgent fires via `workflow_dispatch`.**

---

## Tests (`tests/`)

- Mock Band client (no live WebSocket in CI). Unit-test each agent's verdict logic and hand-off message given fixture findings.
- `tools/` tested directly: `security_scanner` **must** flag the SQL injection in `vuln_pr_diff.txt` as CRIT, and pass `clean_pr_diff.txt`. `risk_scorer` math asserted.
- Webhook: HMAC accept/reject, parser extraction, initiator invocation.
- `pytest` + `pytest-asyncio`.

---

## Revised day-by-day (Jun 13 → 19)

- **Jun 13 (today):** Phase 0 bootstrap + **Phase 1 spikes A/B/C**. End state: one agent replies in Band; custom-tool wiring confirmed; webhook can post the opening message. *(Spikes gate everything — do them before feature code.)*
- **Jun 14:** `shared/` (schemas, verdict, llm_factory, agent_runner, band_helpers) + `webhook/` complete; ngrok trigger fires end-to-end into an empty ScanAgent.
- **Jun 15:** ScanAgent + its 4 tools; hands off to SecurityAgent.
- **Jun 16:** SecurityAgent + `security_scanner` (regex+LLM); catches the planted vuln; hands to RiskAgent.
- **Jun 17:** RiskAgent + `risk_scorer` + **human escalation** (reply `@RiskAgent APPROVE/REJECT`); DeployAgent + `deploy_trigger` (real Actions) + ReportAgent + PR comment. Full chain green.
- **Jun 18:** Docker, Railway deploy (all 6 services live), CI/CD green, README + architecture diagram, record 5-min demo, slides PDF.
- **Jun 19:** Buffer + submit on lablab.ai (repo, video, slides, live URL).

---

## Risks & mitigations

- **Open-source model tool-calling reliability** (biggest functional risk): some models won't emit tool calls consistently. Test each assigned model with a trivial tool call during Spike A; fall back to a larger instruct/coder variant or swap provider (Featherless ↔ AI/ML API) per agent via `agent_config.yaml`.
- **Band REST room-creation API shape unknown** → Spike C resolves; fallback is to have a dedicated "Webhook" agent identity post the opening @mention instead of raw REST.
- **Live demo fragility of real Actions deploy** → keep the target repo's `deploy.yml` trivial (echo + small deploy) so the run completes fast and reliably; the demo's emotional peak is the *security BLOCK*, not the deploy.
- **Railway 6-service free-tier limits** → if constrained, co-host agents in one container running all 5 `run()` loops via asyncio, webhook as a second service.

---

## Verification / demo runbook

1. **Unit/CI:** `pytest -v` green locally and in GitHub Actions; `security_scanner` test proves CRIT on `vuln_pr_diff.txt`.
2. **Local E2E:** `docker-compose up` → open a PR in the target repo containing the vuln diff → within ~2s the `PR-{n}-deployguard` Band room lights up → ScanAgent PASS → SecurityAgent posts CRITICAL BLOCK (SQL injection, file+line) → chain frozen, DeployAgent idle → engineer replies `fix` → ReportAgent posts audit to room **and** as a GitHub PR comment.
3. **Escalation path:** open a clean-but-risky PR (touches auth, >500 lines) → RiskAgent score ≥71 → escalates → reply `@RiskAgent APPROVE` → DeployAgent fires real `workflow_dispatch` → run completes → ReportAgent logs success.
4. **Prod:** Railway `GET /health` 200, all 5 agent WS connections alive; repeat step 2 against the Railway URL for the recorded demo.

---

## Open items to confirm during Spikes (carry into build)
- Exact `band-sdk` API for attaching custom tools to `LangGraphAdapter`.
- Exact Band REST endpoints for room creation + posting as the webhook service identity.
- Whether `ChatOpenAI(base_url=...)` is the right LangChain class for Featherless/AI-ML API (vs a provider-specific class), and which exact open-source model IDs are available on each provider.
