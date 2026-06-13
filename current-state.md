# DeployGuard — Current State

_Last updated: 2026-06-13_

Progress log for the DeployGuard build. See [PLAN.md](PLAN.md) for the full plan.

**Repo:** https://github.com/Dan16ssd/Deploy-Guard-Ai-Agents- (Phase 1 pushed to `main`).

---

## ✅ Done (Phase 0 — bootstrap + shared foundation)

**Repo & config**
- Git repo initialized (`main` branch).
- `.gitignore`, `requirements.txt`, `.env.example`, `agent_config.yaml`.
- `README.md`, `PLAN.md`, `current-state.md`.

**`shared/` package — all verified working**
- `verdict.py` — `Verdict` (PASS/WARN/BLOCK/ESCALATE), `Severity`, `HumanDecision`, `SEVERITY_TO_VERDICT`.
- `context_schema.py` — Pydantic payloads: `PRContext`, `Finding`, `ScanFindings`, `SecurityFindings`, `RiskReport`, `DeployResult`, `AuditRecord`.
- `band_helpers.py` — parse @mentions, extract/format fenced-JSON payloads, `compose_handoff`, `detect_human_decision`.
- `chain_state.py` — per-room idempotency + stage tracking (in-memory).
- `llm_factory.py` — builds per-agent `ChatOpenAI` from `agent_config.yaml` + env.
- `agent_runner.py` — single Band SDK bootstrap reused by all agents.

**Tests / fixtures**
- `tests/test_shared.py` — 7 tests, all passing.
- `tests/fixtures/vuln_pr_diff.txt` — planted SQL-injection + auth-bypass diff.
- `tests/fixtures/clean_pr_diff.txt` — parameterized-query control diff.

**Spikes**
- `spike/spike_a_echo_agent.py` — single-agent connectivity check (run once credentials exist).

---

## ✅ Done (Phase 1 — tools, webhook, agents, infrastructure)

**`tools/` — 7 files, all complete**
- `github_api.py` — `get_pr_metadata`, `get_pr_diff`, `get_pr_files`, `post_pr_comment` (PyGithub + httpx).
- `static_analyzer.py` — runs `ruff` via subprocess on diff-extracted Python; returns structured `Finding` list.
- `test_runner.py` — runs `pytest` via subprocess; parses pass/fail/error counts.
- `dep_auditor.py` — runs `pip-audit` via subprocess; returns CVE list + count.
- `security_scanner.py` — **the star**: regex patterns for SQL injection (concat, %-format, f-string), hardcoded secrets, AWS keys, command injection, path traversal + optional LLM deep-scan pass. Returns verdict PASS/WARN/BLOCK with file+line.
- `risk_scorer.py` — weighted score 0–100: auth file +30, payment file +40, Friday +15, diff >500 lines +10, each WARN +5 (capped at 20). Returns verdict PASS or ESCALATE.
- `deploy_trigger.py` — fires real `workflow_dispatch` on `TARGET_REPO`; polls every 10s up to 5 min; returns READY/FAILED/TIMEOUT.

**`webhook/` — 4 files, complete**
- `verifier.py` — HMAC-SHA256 of raw body vs `X-Hub-Signature-256`.
- `parser.py` — GitHub `pull_request` payload → `PRContext` (ignores non-`main` base branches).
- `band_initiator.py` — creates Band room `PR-{n}-deployguard` + posts opening `@ScanAgent` message. ⚠️ Spike C endpoint paths TBD.
- `main.py` — FastAPI `POST /webhook` + `GET /health`.

**`agents/` — all 5 agents, complete**
- `scan_agent.py` — ScanAgent: calls github_api + static_analyzer + test_runner + dep_auditor; hands off to @SecurityAgent or blocks to engineer.
- `security_agent.py` — SecurityAgent: calls security_scanner (regex + LLM); hands off to @RiskAgent or CRIT-blocks to engineer.
- `risk_agent.py` — RiskAgent: calls risk_scorer; PASS → @DeployAgent; ESCALATE → @engineer then waits for APPROVE/REJECT reply.
- `deploy_agent.py` — DeployAgent: calls deploy_trigger; posts PR comment; hands off to @ReportAgent.
- `report_agent.py` — ReportAgent: assembles full audit table + posts PR comment. Always runs last.

**Infrastructure**
- `Dockerfile` — Python 3.11-slim, installs requirements, copies src.
- `docker-compose.yml` — 6 services: webhook (port 8000, health check) + 5 agents.
- `.github/workflows/ci.yml` — ruff + black + mypy + pytest + docker build on every push/PR.
- `.github/workflows/deploy.yml` — CI → GHCR image push → Railway redeploy → health check on merge to main.

**Tests**
- `tests/test_tools.py` — 13 new tests covering security_scanner (vuln flags CRIT, clean passes), risk_scorer (auth/payment/large-diff/cap), static_analyzer, webhook parser + verifier.
- `tests/fixtures/sample_pr_payload.json` — GitHub webhook payload fixture.
- **Total: 20 tests, all passing.**

---

## ⏳ Blocked on credentials (still needed)

- Register 5 agents at app.band.ai → fill `*_AGENT_ID` / `*_AGENT_API_KEY` in `.env`.
- Featherless API key → `FEATHERLESS_API_KEY` in `.env`.
- GitHub PAT (`contents:read`, `pull_requests:write`, `actions:write`) → `GITHUB_TOKEN`.
- Create target repo + `DEPLOY_WORKFLOW_FILE` (`deploy.yml` with `workflow_dispatch` trigger).
- Set `GITHUB_WEBHOOK_SECRET` and configure GitHub webhook pointing at ngrok/Railway URL.

---

## 🔜 Next up (in order)

1. **Fill `.env`** with real credentials (Band + Featherless + GitHub PAT).
2. **Run Spike A** (`python -m spike.spike_a_echo_agent`) — confirms Band WebSocket + LLM tool-calling work.
3. **Spike B** — confirm `LangGraphAdapter(tools=[...], system_prompt=...)` signature in `agent_runner.build_adapter`.
4. **Spike C** — confirm Band REST room-creation + message-post endpoints; adjust `webhook/band_initiator.py` if needed.
5. **ngrok** (`ngrok http 8000`) + register GitHub webhook on target repo.
6. **E2E test** — open a PR with `vuln_pr_diff.txt` content → watch Band room light up → confirm CRIT block.
7. **Railway deploy** — 6 services live, `GET /health` 200.
8. **Demo video + slides** — record 5-min demo, export PDF.
9. **Submit** on lablab.ai (repo, video, slides, live URL) by Jun 19.

---

## ⚠️ Open verification items (carry into spikes)

- Exact `band-sdk` `LangGraphAdapter` signature for `tools=` and `system_prompt=` → may require adjusting `shared/agent_runner.build_adapter`.
- Band REST endpoints for room creation + message posting (`webhook/band_initiator.py` marked with `# Spike C`).
- Confirm `ChatOpenAI(base_url=...)` works for Featherless; verify exact model IDs are live on Featherless.

---

## How to run what exists

```bash
# Minimal install (for tests only, no Band/LLM credentials needed)
pip install langchain-core pydantic pyyaml pytest
pytest tests/ -q   # -> 20 passed

# Full install
pip install -r requirements.txt

# Once .env is filled:
python -m spike.spike_a_echo_agent   # Spike A gate
uvicorn webhook.main:app --port 8000  # webhook only
docker-compose up                     # all 6 services
```
