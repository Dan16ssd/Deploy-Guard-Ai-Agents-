"""LangChain tool: trigger a GitHub Actions workflow and poll until completion."""

from __future__ import annotations

import os
import time

from langchain_core.tools import tool


@tool
def trigger_deployment(
    ref: str = "main",
    repo: str | None = None,
    workflow_file: str | None = None,
) -> dict:
    """Trigger workflow_dispatch on the target deploy repo and poll until done.

    Returns: {"success": bool, "run_id": int, "run_url": str, "status": str, "error": str}
    """
    from github import Github, GithubException

    token = os.environ["GITHUB_TOKEN"]
    target_repo = repo or os.environ["TARGET_REPO"]
    wf_file = workflow_file or os.environ.get("DEPLOY_WORKFLOW_FILE", "deploy.yml")

    g = Github(token)
    r = g.get_repo(target_repo)

    try:
        wf = r.get_workflow(wf_file)
        wf.create_dispatch(ref=ref, inputs={})
    except GithubException as exc:
        return {
            "success": False,
            "run_id": None,
            "run_url": "",
            "status": "FAILED",
            "error": str(exc),
        }

    # Give Actions a moment to register the run
    time.sleep(4)

    run_id, run_url = _find_latest_run(r, wf.id, ref)
    if not run_id:
        return {
            "success": False,
            "run_id": None,
            "run_url": "",
            "status": "FAILED",
            "error": "Run not found after dispatch",
        }

    result = _poll_run(r, run_id, timeout=300)
    result["run_id"] = run_id
    result["run_url"] = run_url
    return result


def _find_latest_run(repo, workflow_id: int, branch: str) -> tuple[int | None, str]:
    try:
        runs = list(repo.get_workflow_runs(workflow_id=workflow_id, branch=branch))
        if runs:
            return runs[0].id, runs[0].html_url
    except Exception:
        pass
    return None, ""


def _poll_run(repo, run_id: int, timeout: int) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            run = repo.get_workflow_run(run_id)
            if run.status == "completed":
                success = run.conclusion == "success"
                return {
                    "success": success,
                    "status": "READY" if success else "FAILED",
                    "error": "" if success else f"conclusion={run.conclusion}",
                }
        except Exception as exc:
            return {"success": False, "status": "FAILED", "error": str(exc)}
        time.sleep(10)
    return {"success": False, "status": "TIMEOUT", "error": "Timed out after 5 min"}
