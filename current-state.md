# DeployGuard — Current State

_Last updated: 2026-06-17_

**Repo:** https://github.com/Dan16ssd/Deploy-Guard-Ai-Agents-
**Status:** ✅ **Live & end-to-end automated** — deployed on Railway, PRs auto-trigger the five-agent chain.

See **[README.md](README.md)** for the overview and **[ARCHITECTURE.md](ARCHITECTURE.md)** for the full design.

---

## ✅ Live deployment

- **Hosting:** Railway, two services from this repo:
  - `webhook` — `python -m webhook.main`, public domain, `GET /health` → `{"status":"ok"}`.
  - `agents` — `python -m run_all_agents`, all five agents in one supervised process.
- **Trigger:** GitHub `pull_request` webhook (HMAC-verified) on `Dan16ssd/deployguard-target` → webhook creates a Band room and pings `@ScanAgent`.
- **Verified end-to-end:** opening a PR delivers the event (HTTP 202), the chain runs in Band, and the security verdict + audit land on the PR.
- **Demo PRs on the target repo:**
  - **#1 (vulnerable)** — planted SQL injection → SecurityAgent **blocks** and auto-posts a `CRITICAL` comment (fail-fast).
  - **#2 (clean)** — safe feature → flows `Scan → Security → Risk → Deploy → Report` and deploys.

---

## ✅ Reliability hardening (deterministic where it matters)

Small open-source models orchestrate the chat, but every **security-critical decision is produced by code**, so outcomes are consistent run to run:

- **`security_review`** — fetches the diff, scans (OWASP regex), and **auto-posts the `CRITICAL` block comment** itself; the block never depends on the model.
- **`post_audit_report`** — reconstructs the outcome from real signals (block comment + deploy run) and posts a clean audit table; no chat-history parsing.
- **Self-healing identifiers** (`_resolve_target`) — placeholder repo/PR args snap to the configured target + its open PR, so the chain always acts on the real PR.
- **Fail-closed** — if a diff can't be fetched, SecurityAgent escalates for manual review (never a silent approve).
- **Hand-off discipline** — one delivery per turn, mention allow-listing, reconnect-resilient agents, `temperature 0`.
- **Quality gate:** **22 tests passing**; `ruff` + `black` clean; CI runs lint + tests + Docker build.

---

## ✅ Architecture & components (built and in use)

**`shared/`** — `verdict.py` (PASS/WARN/BLOCK/ESCALATE), `context_schema.py` (Pydantic payloads), `band_helpers.py`, `llm_factory.py` (per-agent ChatOpenAI from `agent_config.yaml`), `agent_runner.py` (Band adapter wiring + hand-off discipline), `band_handles.py` (@mention resolution).

**`tools/`** — `github_api.py` (PR metadata/diff/files/comment + audit report + self-healing resolver), `security_scanner.py` (`security_review` deterministic block), `risk_scorer.py` (weighted 0–100 score), `static_analyzer.py` (ruff), `test_runner.py` (pytest), `dep_auditor.py` (pip-audit), `deploy_trigger.py` (`workflow_dispatch`).

**`agents/`** — `scan`, `security`, `risk`, `deploy`, `report`, each a rigid single-tool → hand-off flow. `run_all_agents.py` runs all five in one supervised process.

**`webhook/`** — `verifier.py` (HMAC-SHA256), `parser.py` (PR payload → `PRContext`, main-only), `band_initiator.py` (creates the Band room + opening message via the generated REST client), `main.py` (FastAPI `/webhook` + `/health`, binds `$PORT`).

**Infra** — `Dockerfile` (default CMD = webhook; agents override the start command), `docker-compose.yml`, GitHub Actions CI.

---

## Integration notes (resolved)

- **Band SDK** (`band-sdk 1.0.0`): adapter built via `graph_factory` so the injected `band_send_message` tool is wrapped for mention-normalization, allow-listing, and first-send-wins.
- **Band identities:** all five agents + the service agent authenticate; the engineer is a peer, so room participant-adding works without extra wiring.
- **Featherless models:** all five verified live; Qwen `<think>` output disabled globally; `temperature 0` for determinism.
- **Target repo:** `Dan16ssd/deployguard-target` (clean app + passing test + `deploy.yml` `workflow_dispatch` + planted-vuln PR).

---

## How to run

```bash
# Tests only (no credentials/network needed)
pip install -r requirements.txt
pytest -q                         # 22 passed

# Local run (with .env filled)
python -m webhook.main            # webhook on :8000 ($PORT in cloud)
python -m run_all_agents          # all five agents

# Cloud: Railway — webhook (python -m webhook.main) + agents (python -m run_all_agents)
```

---

## Remaining / future work

- **Demo deliverables:** record the 3–4 min video, export slides, submit on lablab.ai (repo, video, slides, live URL).
- **Production path:** GitHub App (per-install scoped tokens) for true multi-repo / multi-tenant review.
- **Nice-to-have:** richer risk factors; tighten agent chat prose (outcomes are already deterministic).
