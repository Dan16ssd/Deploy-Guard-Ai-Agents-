# DeployGuard — Current State

_Last updated: 2026-06-13_

Progress log for the DeployGuard build. See [PLAN.md](PLAN.md) for the full plan.

## ✅ Done (Phase 0 — bootstrap + shared foundation)

**Repo & config**
- Git repo initialized (`main` branch) — separate from the surrounding home-dir repo.
- `.gitignore` (ignores `.env`, caches, venv), `requirements.txt`, `.env.example` (all credential slots), `agent_config.yaml` (per-agent model + provider map).
- `README.md`, `PLAN.md`, this `current-state.md`.

**`shared/` package — all verified working**
- `verdict.py` — `Verdict` (PASS/WARN/BLOCK/ESCALATE), `Severity` (ordered LOW→CRIT), `HumanDecision`, `SEVERITY_TO_VERDICT` map.
- `context_schema.py` — Pydantic payloads: `PRContext`, `Finding`, `ScanFindings`, `SecurityFindings`, `RiskReport`, `DeployResult`, `AuditRecord`.
- `band_helpers.py` — parse @mentions, extract/format fenced-JSON payloads, `compose_handoff`, `detect_human_decision`.
- `chain_state.py` — lightweight per-room idempotency + stage tracking (in-memory, swappable for Redis).
- `llm_factory.py` — builds per-agent `ChatOpenAI` from config + env (Featherless/AI-ML API); credential resolver.
- `agent_runner.py` — single Band SDK bootstrap (`Agent.create(...).run()`) reused by all agents.

**Tests / fixtures**
- `tests/test_shared.py` — **7 tests, all passing** (verdict mapping, handoff round-trip, mention extraction, human-decision detection, schema defaults).
- `tests/fixtures/vuln_pr_diff.txt` — planted SQL-injection + auth-bypass diff for the demo.
- `tests/fixtures/clean_pr_diff.txt` — parameterized-query control diff.

**Spikes**
- `spike/spike_a_echo_agent.py` — single-agent connectivity check (gates everything; run once credentials exist).

## ⏳ Blocked on credentials (need accounts — "nothing set up yet")
- Register 5 agents at app.band.ai → fill `*_AGENT_ID` / `*_AGENT_API_KEY` in `.env`.
- Featherless (and/or AI/ML API) key → `.env`.
- GitHub PAT (`contents:read`, `pull_requests:write`, `actions:write`) + target repo + webhook secret.

## 🔜 Next up
1. **Run Spikes A/B/C** against the real SDK (confirm tool attachment + Band REST room-creation API). _This may adjust `agent_runner.build_adapter` and the webhook initiator._
2. `tools/` — `github_api`, `static_analyzer`, `test_runner`, `dep_auditor`, `security_scanner` (regex + LLM), `risk_scorer`, `deploy_trigger`.
3. `webhook/` — FastAPI receiver, HMAC verifier, PR parser, Band room initiator.
4. `agents/` — the 5 agent processes (system prompt + tools + model via `agent_runner`).
5. Docker Compose, GitHub Actions CI + deploy, Railway, demo video.

## ⚠️ Open verification items (carry into spikes)
- Exact `band-sdk` `LangGraphAdapter` signature for custom `tools=` / `system_prompt=`.
- Band REST endpoints for room creation + posting as the webhook service identity.
- Confirm `ChatOpenAI(base_url=...)` works for Featherless/AI-ML API and which exact open-source model IDs are live.

## How to run what exists
```bash
pip install pytest pydantic pyyaml   # minimal, for the shared tests
pytest tests/test_shared.py -q       # -> 7 passed
```
