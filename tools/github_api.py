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


@tool
def get_pr_metadata(repo: str, pr_number: int) -> dict:
    """Return PR metadata: title, author, branches, additions, deletions, changed files."""
    try:
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
        return [{"error": _err(exc), "note": f"could not list files for {repo}#{pr_number}"}]


@tool
def post_pr_comment(repo: str, pr_number: int, body: str) -> str:
    """Post a comment on a GitHub pull request. Returns the comment URL."""
    try:
        pr = _gh().get_repo(repo).get_pull(int(pr_number))
        comment = pr.create_issue_comment(body)
        return comment.html_url
    except Exception as exc:  # noqa: BLE001 - must not crash the agent
        return f"ERROR posting comment to {repo}#{pr_number}: {_err(exc)}"
