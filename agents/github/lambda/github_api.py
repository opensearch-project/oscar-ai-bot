# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Direct GitHub REST API client for operations not supported by the MCP server.

Used for: transfer_issue, add_comment, bulk_comment, get_repo_maintainers.
"""

import json
import logging
import os
import re
from typing import Dict, List

import boto3
import requests
from http_client import API_BASE, GitHubAPIError, get, post

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


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


_MAINTAINERS_LINK_RE = re.compile(
    r"\[([^\]]+)\]\(https?://github\.com/([^)]+)\)",
)

LLM_MODEL_ID = os.environ.get("LLM_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")


def _invoke_llm(prompt: str, max_tokens: int = 256) -> str:
    """Invoke Bedrock Claude Haiku and return the text response."""
    bedrock = boto3.client("bedrock-runtime")
    response = bedrock.invoke_model(
        modelId=LLM_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }),
    )
    result = json.loads(response["body"].read())
    return result.get("content", [{}])[0].get("text", "")


def _parse_maintainers_fallback(content: str) -> List[Dict]:
    """Regex fallback: extract GitHub handles from the Current Maintainers section."""
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
    """Fetch current maintainers from MAINTAINERS.md using LLM with regex fallback."""
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

        content = resp.text
        maintainers = None

        try:
            prompt = (
                "Extract ONLY the current/active maintainers from this MAINTAINERS.md file. "
                "Do NOT include emeritus, former, or inactive maintainers.\n\n"
                f"{content}\n\n"
                "Respond with ONLY a JSON array of objects like:\n"
                '[{"github_id": "username", "name": "Display Name"}]\n'
                "If you cannot determine any maintainers, return an empty array []."
            )
            text = _invoke_llm(prompt, max_tokens=1000)
            maintainers = json.loads(text)
        except Exception as e:
            logger.warning("LLM maintainer parsing failed for %s/%s: %s, using regex fallback", owner, repo, e)

        if not maintainers:
            maintainers = _parse_maintainers_fallback(content)

        return json.dumps({
            "status": "success",
            "repo": f"{owner}/{repo}",
            "maintainers": maintainers,
            "total": len(maintainers),
        })
    except Exception as e:
        logger.warning("Failed to fetch maintainers for %s/%s: %s", owner, repo, e)
        return json.dumps({"status": "error", "message": str(e)})


