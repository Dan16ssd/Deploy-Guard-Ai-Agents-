"""LangChain tools for GitHub PR operations.

Every tool catches its own exceptions and returns a structured error instead of raising:
a tool that raises inside the Band LangGraph adapter aborts the agent's whole message
turn (the message is marked permanently failed), which silently breaks the approval chain.
Returning an error value keeps the agent alive and lets the LLM recover (retry with the
repo/pr_number from the opener, or proceed on the findings it already has).
"""

from __future__ import annotations

import os
from typing import Any

from langchain_core.tools import tool


def _gh() -> Any:
    from github import Github

    return Github(os.environ["GITHUB_TOKEN"])


def _err(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"[:300]


def _normalize_repo(value: str) -> str:
    v = (value or "").strip().rstrip("/")
    for prefix in ("https://github.com/", "http://github.com/", "git@github.com:"):
        if v.startswith(prefix):
            v = v[len(prefix) :]
            break
    return v[:-4] if v.endswith(".git") else v


def _latest_open_pr(repo: str) -> int | None:
    try:
        prs = list(
            _gh()
            .get_repo(repo)
            .get_pulls(state="open", sort="created", direction="desc")
        )
        return prs[0].number if prs else None
    except Exception:  # noqa: BLE001
        return None


def _resolve_target(repo: str, pr_number: Any) -> tuple[str, int]:
    """Self-heal placeholder identifiers to the real guarded repo + its open PR.

    The chain's small models sometimes hand GitHub tools placeholder args (the classic
    `example/repo` / `123`) instead of the real values from the message — which 404s and,
    for a security gate, must never let a PR through unreviewed. When `TARGET_REPO` is set
    (single-repo deployment) and the supplied repo isn't it, we snap to `TARGET_REPO` and
    its most recent OPEN pull request. A correctly-supplied repo+PR is trusted as-is.
    """
    try:
        pr_int = int(pr_number)
    except (TypeError, ValueError):
        pr_int = 0
    target = _normalize_repo(os.environ.get("TARGET_REPO", ""))
    if not target:
        return _normalize_repo(repo), pr_int
    if _normalize_repo(repo) == target and pr_int > 0:
        return target, pr_int
    real_pr = _latest_open_pr(target)
    return target, (real_pr if real_pr else pr_int)


@tool
def get_pr_metadata(repo: str, pr_number: int) -> dict:
    """Return PR metadata: title, author, branches, additions, deletions, changed files."""
    try:
        repo, pr_number = _resolve_target(repo, pr_number)
        pr = _gh().get_repo(repo).get_pull(int(pr_number))
        return {
            "title": pr.title,
            "author": pr.user.login,
            "base_branch": pr.base.ref,
            "head_branch": pr.head.ref,
            "head_sha": pr.head.sha,
            "additions": pr.additions,
            "deletions": pr.deletions,
            "changed_files": [f.filename for f in pr.get_files()],
        }
    except Exception as exc:  # noqa: BLE001 - must not crash the agent
        return {
            "error": _err(exc),
            "note": f"could not fetch metadata for {repo}#{pr_number}",
        }


@tool
def get_pr_diff(repo: str, pr_number: int) -> str:
    """Fetch the unified diff text for a pull request."""
    import httpx

    try:
        token = os.environ["GITHUB_TOKEN"]
        repo, pr_number = _resolve_target(repo, pr_number)
        pr = _gh().get_repo(repo).get_pull(int(pr_number))
        resp = httpx.get(
            pr.url,
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3.diff",
            },
            follow_redirects=True,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.text
    except Exception as exc:  # noqa: BLE001 - must not crash the agent
        return f"ERROR fetching diff for {repo}#{pr_number}: {_err(exc)}"


@tool
def get_pr_files(repo: str, pr_number: int) -> list:
    """List files changed in a PR with patch content."""
    try:
        repo, pr_number = _resolve_target(repo, pr_number)
        pr = _gh().get_repo(repo).get_pull(int(pr_number))
        return [
            {
                "filename": f.filename,
                "status": f.status,
                "additions": f.additions,
                "deletions": f.deletions,
                "patch": f.patch or "",
            }
            for f in pr.get_files()
        ]
    except Exception as exc:  # noqa: BLE001 - must not crash the agent
        return [
            {"error": _err(exc), "note": f"could not list files for {repo}#{pr_number}"}
        ]


@tool
def post_pr_comment(repo: str, pr_number: int, body: str) -> str:
    """Post a comment on a GitHub pull request. Returns the comment URL."""
    try:
        repo, pr_number = _resolve_target(repo, pr_number)
        pr = _gh().get_repo(repo).get_pull(int(pr_number))
        comment = pr.create_issue_comment(body)
        return comment.html_url
    except Exception as exc:  # noqa: BLE001 - must not crash the agent
        return f"ERROR posting comment to {repo}#{pr_number}: {_err(exc)}"


@tool
def post_audit_report(repo: str, pr_number: int) -> dict:
    """Assemble and post the FINAL DeployGuard audit report for a PR — deterministically.

    ReportAgent should call THIS once and nothing else. It reconstructs the outcome from real
    signals (whether SecurityAgent's block comment exists + the latest deploy run) instead of
    relying on the model to parse chat history, then posts a clean audit table as a PR comment.
    Returns {comment_url, overall} where overall is DEPLOYED or BLOCKED.
    """
    try:
        repo, pr_number = _resolve_target(repo, pr_number)
        gh_repo = _gh().get_repo(repo)
        pr = gh_repo.get_pull(int(pr_number))
        blocked = any(
            "DEPLOYMENT BLOCKED" in (c.body or "") for c in pr.get_issue_comments()
        )
        deploy_status = "n/a"
        try:
            runs = list(gh_repo.get_workflow_runs())
            if runs:
                deploy_status = runs[0].conclusion or runs[0].status or "n/a"
        except Exception:  # noqa: BLE001
            pass

        overall = "BLOCKED" if blocked else "DEPLOYED"
        security_cell = "🚫 BLOCK — critical findings" if blocked else "✅ PASS"
        risk_cell = "n/a (blocked upstream)" if blocked else "✅ within threshold"
        deploy_cell = "⛔ HELD" if blocked else f"🚀 {deploy_status}"
        body = (
            "## 📋 DeployGuard — Audit Report\n\n"
            f"**PR #{pr_number}** — {pr.title} · by @{pr.user.login}\n\n"
            "| Stage | Result |\n"
            "|-------|--------|\n"
            "| 🔍 Scan | ✅ completed |\n"
            f"| 🛡️ Security | {security_cell} |\n"
            f"| ⚖️ Risk | {risk_cell} |\n"
            f"| 🚀 Deploy | {deploy_cell} |\n\n"
            f"### Overall: **{overall}**\n\n"
            "_Generated by DeployGuard ReportAgent._"
        )
        comment = pr.create_issue_comment(body)
        return {"comment_url": comment.html_url, "overall": overall}
    except Exception as exc:  # noqa: BLE001 - must not crash the agent
        return {"error": _err(exc), "overall": "UNKNOWN", "comment_url": ""}
