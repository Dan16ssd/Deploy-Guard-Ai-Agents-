"""LangChain tools for GitHub PR operations."""

from __future__ import annotations

import os
from typing import Any

from langchain_core.tools import tool


def _gh() -> Any:
    from github import Github

    return Github(os.environ["GITHUB_TOKEN"])


@tool
def get_pr_metadata(repo: str, pr_number: int) -> dict:
    """Return PR metadata: title, author, branches, additions, deletions, changed files."""
    pr = _gh().get_repo(repo).get_pull(pr_number)
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


@tool
def get_pr_diff(repo: str, pr_number: int) -> str:
    """Fetch the unified diff text for a pull request."""
    import httpx

    token = os.environ["GITHUB_TOKEN"]
    pr = _gh().get_repo(repo).get_pull(pr_number)
    resp = httpx.get(
        pr.url,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3.diff",
        },
        follow_redirects=True,
    )
    resp.raise_for_status()
    return resp.text


@tool
def get_pr_files(repo: str, pr_number: int) -> list:
    """List files changed in a PR with patch content."""
    pr = _gh().get_repo(repo).get_pull(pr_number)
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


@tool
def post_pr_comment(repo: str, pr_number: int, body: str) -> str:
    """Post a comment on a GitHub pull request. Returns the comment URL."""
    pr = _gh().get_repo(repo).get_pull(pr_number)
    comment = pr.create_issue_comment(body)
    return comment.html_url
