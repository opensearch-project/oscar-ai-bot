# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Direct GitHub REST API client for operations not supported by the MCP server.

Used for: transfer_issue, add_comment, bulk_comment, get_repo_maintainers.
"""

import json
import logging
import re
from typing import Dict, List

import requests
from http_client import API_BASE, GitHubAPIError, get, post

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Patterns that should never appear in outbound comments — they could be used
# to inject prompts into downstream LLM-based tools that read GitHub comments.
_OUTBOUND_INJECTION_PATTERNS = [
    re.compile(r'<\s*/?system\s*>', re.IGNORECASE),
    re.compile(r'\[INST\]|\[/INST\]', re.IGNORECASE),
    re.compile(r'(ignore|disregard|override|forget)\s+(all\s+)?(previous|prior|above)\s+(instructions?|rules?|prompts?)', re.IGNORECASE),
    re.compile(r'(new|updated?)\s+system\s+prompt', re.IGNORECASE),
    re.compile(r'you\s+are\s+now', re.IGNORECASE),
    re.compile(r'```\s*system', re.IGNORECASE),
]


def _screen_outbound_body(body: str) -> str:
    """Screen outbound comment body for prompt injection patterns.

    Raises GitHubAPIError if suspicious content is detected, preventing
    the agent from being used as a vector to inject into other LLM tools.
    """
    for pattern in _OUTBOUND_INJECTION_PATTERNS:
        if pattern.search(body):
            raise GitHubAPIError(
                400,
                "Comment body rejected: contains content that resembles a prompt "
                "injection payload. The comment was not posted to protect downstream "
                "systems. Please rephrase the comment.",
                "outbound_screening",
            )
    return body


def _get_issue_node_id(token: str, owner: str, repo: str, issue_number: int) -> str:
    """Get the GraphQL node ID for an issue."""
    result = get(token, f"/repos/{owner}/{repo}/issues/{issue_number}")
    node_id = result.get("node_id")
    if not node_id:
        raise GitHubAPIError(404, f"Issue #{issue_number} not found in {owner}/{repo}",
                             f"{API_BASE}/repos/{owner}/{repo}/issues/{issue_number}")
    return node_id


def _get_repo_node_id(token: str, owner: str, repo: str) -> str:
    """Get the GraphQL node ID for a repository."""
    result = get(token, f"/repos/{owner}/{repo}")
    node_id = result.get("node_id")
    if not node_id:
        raise GitHubAPIError(404, f"Repository {owner}/{repo} not found",
                             f"{API_BASE}/repos/{owner}/{repo}")
    return node_id


def transfer_issue(
    token: str, owner: str, repo: str, issue_number: int, target_repo: str,
) -> str:
    """Transfer an issue to another repository using the GraphQL API."""
    issue_node_id = _get_issue_node_id(token, owner, repo, issue_number)
    repo_node_id = _get_repo_node_id(token, owner, target_repo)

    query = """
    mutation($issueId: ID!, $repoId: ID!) {
      transferIssue(input: {issueId: $issueId, repositoryId: $repoId}) {
        issue {
          number
          url
          title
          repository {
            nameWithOwner
          }
        }
      }
    }
    """
    result = post(token, "/graphql", json_body={
        "query": query,
        "variables": {"issueId": issue_node_id, "repoId": repo_node_id},
    })

    errors = result.get("errors")
    if errors:
        msg = "; ".join(e.get("message", "") for e in errors)
        raise GitHubAPIError(422, f"GraphQL error: {msg}", f"{API_BASE}/graphql")

    issue_data = result.get("data", {}).get("transferIssue", {}).get("issue", {})
    return json.dumps({
        "status": "success",
        "new_issue_number": issue_data.get("number"),
        "new_url": issue_data.get("url"),
        "title": issue_data.get("title"),
        "new_repository": issue_data.get("repository", {}).get("nameWithOwner"),
    })


def add_comment(
    token: str, owner: str, repo: str, issue_number: int, body: str,
) -> str:
    """Add a comment to an issue or pull request."""
    _screen_outbound_body(body)
    result = post(token, f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
                  json_body={"body": body})
    return json.dumps(result)


def bulk_comment(
    token: str, owner: str, issue_targets: List[tuple], body: str,
) -> str:
    """Add the same comment to multiple issues/PRs across repos.

    Args:
        token: GitHub auth token
        owner: Organization name
        issue_targets: List of (repo, issue_number) tuples
        body: Comment body text
    """
    _screen_outbound_body(body)
    results = []
    for repo, num in issue_targets:
        try:
            resp = post(token, f"/repos/{owner}/{repo}/issues/{num}/comments",
                        json_body={"body": body})
            results.append({"repo": repo, "issue_number": num, "status": "success", "url": resp.get("html_url", "")})
        except (GitHubAPIError, Exception) as e:
            results.append({"repo": repo, "issue_number": num, "status": "error", "error": str(e)})
    return json.dumps({
        "results": results,
        "total": len(issue_targets),
        "succeeded": sum(1 for r in results if r["status"] == "success"),
    })


_MAINTAINERS_LINK_RE = re.compile(
    r"\[([^\]]+)\]\(https?://github\.com/([^)]+)\)",
)


def _parse_maintainers(content: str) -> List[Dict]:
    """Deterministic regex parser: extract GitHub handles from the Current Maintainers section."""
    in_current = False
    maintainers = []
    for line in content.splitlines():
        lower = line.strip().lower()
        if "current maintainer" in lower:
            in_current = True
            continue
        if in_current and ("emeritus" in lower or (lower.startswith("##") and "current" not in lower)):
            break
        if not in_current:
            continue
        match = _MAINTAINERS_LINK_RE.search(line)
        if match:
            maintainers.append({
                "github_id": match.group(2).strip().split("/")[-1],
                "name": match.group(1).strip(),
            })
    return maintainers


def get_repo_maintainers(token: str, owner: str, repo: str) -> str:
    """Fetch current maintainers from MAINTAINERS.md using deterministic regex parsing."""
    try:
        resp = requests.get(
            f"{API_BASE}/repos/{owner}/{repo}/contents/MAINTAINERS.md",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.raw+json",
            },
            timeout=30,
        )
        if resp.status_code != 200:
            return json.dumps({
                "status": "error",
                "message": f"MAINTAINERS.md not found in {owner}/{repo} (HTTP {resp.status_code})",
            })

        maintainers = _parse_maintainers(resp.text)

        return json.dumps({
            "status": "success",
            "repo": f"{owner}/{repo}",
            "maintainers": maintainers,
            "total": len(maintainers),
        })
    except Exception as e:
        logger.warning("Failed to fetch maintainers for %s/%s: %s", owner, repo, e)
        return json.dumps({"status": "error", "message": str(e)})


