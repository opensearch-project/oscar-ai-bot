# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Direct GitHub REST API client for operations not supported by the MCP server.

Used for: transfer_issue, add_comment, bulk_comment, community metrics.
"""

import json
import logging
import re
from typing import Dict, List

import requests
from http_client import API_BASE, GitHubAPIError, get, post, request

logger = logging.getLogger(__name__)


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
    result = post(token, f"/repos/{owner}/{repo}/issues/{issue_number}/comments",
                  json_body={"body": body})
    return json.dumps(result)


def bulk_comment(
    token: str, owner: str, repo: str, issue_numbers: List[int], body: str,
) -> str:
    """Add the same comment to multiple issues/PRs. Returns per-issue results."""
    results = []
    for num in issue_numbers:
        try:
            resp = post(token, f"/repos/{owner}/{repo}/issues/{num}/comments",
                        json_body={"body": body})
            results.append({"issue_number": num, "status": "success", "url": resp.get("html_url", "")})
        except (GitHubAPIError, Exception) as e:
            results.append({"issue_number": num, "status": "error", "error": str(e)})
    return json.dumps({
        "results": results,
        "total": len(issue_numbers),
        "succeeded": sum(1 for r in results if r["status"] == "success"),
    })


# ---------------------------------------------------------------------------
# Community Metrics
# ---------------------------------------------------------------------------

_MAINTAINER_TITLE_RE = re.compile(
    r"\[GitHub Request\]\s+Add\s+(.+?)\s+to\s+(.+?)\s+maintainers",
    re.IGNORECASE,
)


def _get_user_company(token: str, username: str) -> str:
    """Fetch the company/affiliation field from a GitHub user profile."""
    try:
        data = get(token, f"/users/{username}")
        return data.get("company") or ""
    except Exception as e:
        logger.warning("Failed to fetch profile for %s: %s", username, e)
        return ""


def _date_filter(status: str, since: str, until: str) -> str:
    if status == "open":
        return f"created:{since}..{until}"
    return f"closed:{since}..{until}"


def get_new_maintainers(
    token: str, org: str, since: str, until: str, status: str = "closed",
) -> str:
    """Find maintainer requests via [GitHub Request] issues in org/.github."""
    status = status.lower() if status else "closed"
    query = (
        f"repo:{org}/.github "
        f"is:issue is:{status} "
        f"\"[GitHub Request] Add\" \"maintainers\" in:title "
        f"{_date_filter(status, since, until)}"
    )
    url = f"{API_BASE}/search/issues?q={requests.utils.quote(query)}&per_page=100&sort=updated&order=desc"
    result = request("GET", url, token)

    maintainers = []
    for item in result.get("items", []):
        title = item.get("title", "")
        match = _MAINTAINER_TITLE_RE.search(title)
        if not match:
            continue
        handle = match.group(1).strip().lstrip("@")
        repo = match.group(2).strip()
        affiliation = _get_user_company(token, handle)
        entry = {
            "github_handle": handle,
            "repository": repo,
            "affiliation": affiliation,
            "issue_url": item.get("html_url", ""),
        }
        if status == "open":
            entry["created_at"] = item.get("created_at", "")
        else:
            entry["closed_at"] = item.get("closed_at", "")
        maintainers.append(entry)

    return json.dumps({
        "maintainers": maintainers,
        "total": len(maintainers),
        "status": status,
        "period": f"{since} to {until}",
    })


_REPO_REQUEST_TITLE_RE = re.compile(
    r"\[Repository Request\]:?\s*(.+)",
    re.IGNORECASE,
)


def get_new_repositories(
    token: str, org: str, since: str, until: str, status: str = "closed",
) -> str:
    """Find repo requests via [Repository Request] issues in org/.github."""
    status = status.lower() if status else "closed"
    query = (
        f"repo:{org}/.github "
        f"is:issue is:{status} "
        f"\"[Repository Request]\" in:title "
        f"{_date_filter(status, since, until)}"
    )
    url = f"{API_BASE}/search/issues?q={requests.utils.quote(query)}&per_page=100&sort=updated&order=desc"
    result = request("GET", url, token)

    repos = []
    for item in result.get("items", []):
        title = item.get("title", "")
        match = _REPO_REQUEST_TITLE_RE.search(title)
        if not match:
            continue
        repo_name = match.group(1).strip()
        entry = {
            "name": repo_name,
            "issue_url": item.get("html_url", ""),
        }
        if status == "open":
            entry["created_at"] = item.get("created_at", "")
        else:
            entry["closed_at"] = item.get("closed_at", "")
        repos.append(entry)

    return json.dumps({
        "repositories": repos,
        "total": len(repos),
        "status": status,
        "period": f"{since} to {until}",
    })


def get_external_contributors(
    token: str, org: str, repo: str, since: str, until: str,
) -> str:
    """Find unique PR authors for a repo in a date range and fetch their company affiliation."""
    query = f"repo:{org}/{repo} is:pr created:{since}..{until}"
    url = (
        f"{API_BASE}/search/issues"
        f"?q={requests.utils.quote(query)}"
        f"&per_page=100&sort=created&order=desc"
    )
    result = request("GET", url, token)

    seen: Dict[str, int] = {}
    for item in result.get("items", []):
        login = (item.get("user") or {}).get("login", "")
        if not login or login.endswith("[bot]"):
            continue
        seen[login] = seen.get(login, 0) + 1

    contributors = []
    for login, pr_count in seen.items():
        affiliation = _get_user_company(token, login)
        contributors.append({
            "github_handle": login,
            "affiliation": affiliation,
            "pr_count": pr_count,
        })

    return json.dumps({
        "contributors": contributors,
        "total": len(contributors),
        "repository": f"{org}/{repo}",
        "period": f"{since} to {until}",
    })
