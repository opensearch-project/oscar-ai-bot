# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Guardrail validation for GitHub agent operations.

Covers merge operations (single + bulk), bulk commenting, and issue transfers.
"""

import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import requests
from http_client import API_BASE, get, put

logger = logging.getLogger(__name__)

PR_TYPES = {
    "version_increment": {
        "expected_author": os.environ.get(
            "VERSION_INCREMENT_AUTHOR", "opensearch-trigger-bot"
        ),
        "title_pattern": re.compile(
            r"^\[AUTO\] Increment version to (\d+\.\d+\.\d+).*$"
        ),
        "requires_version_label": True,
    },
    "release_notes": {
        "expected_author": os.environ.get(
            "RELEASE_NOTES_AUTHOR", "opensearch-ci-bot"
        ),
        "title_pattern": re.compile(
            r"^(?:\[Backport [^\]]+\] )?\[AUTO\] Add release notes for (\d+\.\d+\.\d+)$"
        ),
        "requires_version_label": False,
    },
}


def _classify_pr(title: str) -> Optional[str]:
    for pr_type, cfg in PR_TYPES.items():
        if cfg["title_pattern"].match(title):
            return pr_type
    return None


def _search_auto_prs(token: str, org: str, title_query: str) -> List[Dict]:
    """Search for open PRs matching a title query across the org."""
    query = f'org:{org} is:pr is:open "{title_query}" in:title'
    items: List[Dict] = []
    page = 1
    while True:
        data = get(token, "/search/issues", {"q": query, "per_page": 100, "page": page})
        items.extend(data.get("items", []))
        if len(items) >= data.get("total_count", 0) or not data.get("items"):
            break
        page += 1
    return items


def _get_ci_status(token: str, repo: str, sha: str) -> Dict[str, Any]:
    """Check combined commit status and check runs for a SHA."""
    status_data = get(token, f"/repos/{repo}/commits/{sha}/status")
    combined_state = status_data.get("state", "pending")
    total_statuses = status_data.get("total_count", 0)

    checks_data = get(token, f"/repos/{repo}/commits/{sha}/check-runs")
    check_runs = checks_data.get("check_runs", [])

    if total_statuses == 0 and len(check_runs) == 0:
        return {"passed": True, "detail": "No CI checks configured"}

    if total_statuses > 0 and combined_state != "success":
        return {"passed": False, "detail": f"Commit status: {combined_state}"}

    for run in check_runs:
        if run["status"] != "completed":
            return {
                "passed": False,
                "detail": f"Check '{run['name']}' still {run['status']}",
            }
        if run["conclusion"] not in ("success", "skipped", "neutral"):
            return {
                "passed": False,
                "detail": f"Check '{run['name']}' concluded {run['conclusion']}",
            }

    return {"passed": True, "detail": "All checks passed"}


def _validate_pr(
    token: str, pr_detail: Dict, version: str, pr_type: str
) -> Dict[str, Dict[str, Any]]:
    """Run all guardrail checks on a single PR."""
    cfg = PR_TYPES[pr_type]
    checks: Dict[str, Dict[str, Any]] = {}

    author = pr_detail["user"]["login"]
    checks["author"] = {
        "passed": author == cfg["expected_author"],
        "detail": f"Expected '{cfg['expected_author']}', got '{author}'",
    }

    title = pr_detail["title"]
    match = cfg["title_pattern"].match(title)
    checks["title_pattern"] = {
        "passed": match is not None,
        "detail": title,
    }

    if cfg["requires_version_label"]:
        labels = [lab["name"] for lab in pr_detail.get("labels", [])]
        expected_label = f"v{version}"
        checks["version_label"] = {
            "passed": expected_label in labels,
            "detail": f"Expected '{expected_label}', found {labels}",
        }

    title_version = match.group(1) if match else None
    checks["version_match"] = {
        "passed": title_version == version,
        "detail": f"PR version '{title_version}', requested '{version}'",
    }

    checks["not_draft"] = {
        "passed": not pr_detail.get("draft", False),
        "detail": "Draft" if pr_detail.get("draft") else "Ready",
    }

    mergeable = pr_detail.get("mergeable")
    checks["no_conflicts"] = {
        "passed": mergeable is True,
        "detail": f"mergeable={mergeable}",
    }

    repo = pr_detail["base"]["repo"]["full_name"]
    sha = pr_detail["head"]["sha"]
    checks["ci_passing"] = _get_ci_status(token, repo, sha)

    return checks


def _repo_from_search_item(item: Dict) -> str:
    return item["repository_url"].replace(f"{API_BASE}/repos/", "")


def _checks_result(
    entity: str, checks: Dict, extra: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Build a standardised guardrail result dict."""
    all_passed = all(c["passed"] for c in checks.values())
    result: Dict[str, Any] = {"all_passed": all_passed, "checks": checks}
    if extra:
        result.update(extra)
    if all_passed:
        result["status"] = "success"
    else:
        failed = [f"{n}: {c['detail']}" for n, c in checks.items() if not c["passed"]]
        result["status"] = "error"
        result["message"] = (
            f"Guardrail failures for {entity}:\n" + "\n".join(f"  ✗ {f}" for f in failed)
        )
    return result


# ---------------------------------------------------------------------------
# Single PR validation
# ---------------------------------------------------------------------------

def validate_single_pr(token: str, org: str, repo: str, pr_number: int) -> Dict[str, Any]:
    full_repo = f"{org}/{repo}" if "/" not in repo else repo
    pr_detail = get(token, f"/repos/{full_repo}/pulls/{pr_number}")

    title = pr_detail["title"]
    pr_type = _classify_pr(title)

    if pr_type is None:
        return {
            "status": "success",
            "is_auto_pr": False,
            "message": "Not an automated PR — no merge guardrails apply.",
        }

    match = PR_TYPES[pr_type]["title_pattern"].match(title)
    version = match.group(1) if match else None
    checks = _validate_pr(token, pr_detail, version, pr_type)

    result = _checks_result(f"{full_repo}#{pr_number}", checks, {"is_auto_pr": True, "type": pr_type})
    return result


# ---------------------------------------------------------------------------
# Bulk merge
# ---------------------------------------------------------------------------

def list_merge_candidates(token: str, version: str, org: str) -> Dict[str, Any]:
    """Find auto PRs for a version and validate each against guardrails."""
    candidates: List[Dict] = []
    seen = set()

    for title_query in [
        f"[AUTO] Increment version to {version}",
        f"[AUTO] Add release notes for {version}",
    ]:
        for item in _search_auto_prs(token, org, title_query):
            pr_type = _classify_pr(item["title"])
            if pr_type is None:
                continue

            repo = _repo_from_search_item(item)
            key = (repo, item["number"])
            if key in seen:
                continue
            seen.add(key)

            try:
                pr_detail = get(token, f"/repos/{repo}/pulls/{item['number']}")
            except requests.HTTPError as e:
                logger.warning("Failed to fetch %s#%d: %s", repo, item["number"], e)
                candidates.append({
                    "repo": repo, "number": item["number"], "title": item["title"],
                    "type": pr_type,
                    "checks": {"fetch_error": {"passed": False, "detail": str(e)}},
                    "all_passed": False,
                })
                continue

            checks = _validate_pr(token, pr_detail, version, pr_type)
            candidates.append({
                "repo": repo, "number": pr_detail["number"],
                "title": pr_detail["title"], "html_url": pr_detail["html_url"],
                "type": pr_type, "checks": checks,
                "all_passed": all(c["passed"] for c in checks.values()),
            })

    ready = [c for c in candidates if c["all_passed"]]
    blocked = [c for c in candidates if not c["all_passed"]]
    vi = [c for c in candidates if c["type"] == "version_increment"]
    rn = [c for c in candidates if c["type"] == "release_notes"]

    summary = [
        f"Found {len(candidates)} auto PR(s) for version {version} in {org}:",
        f"  Version increment PRs: {len(vi)}",
        f"  Release notes PRs: {len(rn)}",
        f"  Ready to merge: {len(ready)}",
        f"  Blocked: {len(blocked)}",
    ]
    if blocked:
        summary.append("\nBlocked PRs:")
        for c in blocked:
            fails = [f"{n}: {chk['detail']}" for n, chk in c["checks"].items() if not chk["passed"]]
            summary.append(f"  • {c['repo']}#{c['number']} — {c['title']}")
            for f in fails:
                summary.append(f"    ✗ {f}")

    return {
        "status": "success", "version": version, "organization": org,
        "total": len(candidates), "ready_count": len(ready), "blocked_count": len(blocked),
        "candidates": candidates, "message": "\n".join(summary),
    }


def bulk_merge(token: str, version: str, org: str) -> Dict[str, Any]:
    """Re-validate all candidates and merge those passing all guardrails."""
    report = list_merge_candidates(token, version, org)

    merged, skipped, failed = [], [], []
    for c in report["candidates"]:
        if not c["all_passed"]:
            failed_names = [n for n, chk in c["checks"].items() if not chk["passed"]]
            skipped.append({"repo": c["repo"], "number": c["number"],
                            "title": c["title"], "reason": f"Failed: {', '.join(failed_names)}"})
            continue
        try:
            put(token, f"/repos/{c['repo']}/pulls/{c['number']}/merge", {"merge_method": "merge"})
            merged.append({"repo": c["repo"], "number": c["number"], "title": c["title"]})
            logger.info("BULK_MERGE_SUCCESS %s#%d — %s", c["repo"], c["number"], c["title"])
        except Exception as e:
            logger.error("BULK_MERGE_FAILED %s#%d: %s", c["repo"], c["number"], e)
            failed.append({"repo": c["repo"], "number": c["number"],
                           "title": c["title"], "reason": str(e)})

    return {
        "status": "success", "version": version, "organization": org,
        "merged_count": len(merged), "skipped_count": len(skipped), "failed_count": len(failed),
        "merged": merged, "skipped": skipped, "failed": failed,
        "message": (
            f"Bulk merge complete for version {version}: "
            f"{len(merged)} merged, {len(skipped)} skipped, {len(failed)} failed."
        ),
    }


# ---------------------------------------------------------------------------
# Comment guardrails
# ---------------------------------------------------------------------------

BULK_COMMENT_MAX_ISSUES = 50


def _get_issue_state(
    token: str, org: str, repo: str, issue_number: int,
) -> Tuple[Optional[str], Optional[bool]]:
    full_repo = f"{org}/{repo}" if "/" not in repo else repo
    try:
        data = get(token, f"/repos/{full_repo}/issues/{issue_number}")
        return data.get("state"), data.get("locked", False)
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            return None, None
        raise


def _has_duplicate_comment(
    token: str, org: str, repo: str, issue_number: int, body: str,
) -> bool:
    full_repo = f"{org}/{repo}" if "/" not in repo else repo
    comments = get(
        token, f"/repos/{full_repo}/issues/{issue_number}/comments",
        {"per_page": 100, "sort": "created", "direction": "desc"},
    )
    normalized = body.strip()
    return any(c.get("body", "").strip() == normalized for c in comments)


def validate_comment(
    token: str, org: str, repo: str, issue_number: int, body: str,
) -> Dict[str, Any]:
    checks: Dict[str, Dict[str, Any]] = {}
    state, locked = _get_issue_state(token, org, repo, issue_number)

    checks["target_exists"] = {
        "passed": state is not None,
        "detail": f"Issue #{issue_number} {'found' if state else 'not found'}",
    }
    if state is None:
        return _checks_result(f"{org}/{repo}#{issue_number}", checks)

    checks["target_open"] = {"passed": state == "open", "detail": f"State: {state}"}
    checks["not_locked"] = {"passed": not locked, "detail": "Locked" if locked else "Unlocked"}

    is_dup = _has_duplicate_comment(token, org, repo, issue_number, body)
    checks["no_duplicate"] = {
        "passed": not is_dup,
        "detail": "Duplicate comment already exists" if is_dup else "No duplicate",
    }

    return _checks_result(f"{org}/{repo}#{issue_number}", checks)


def validate_bulk_comment(
    token: str, org: str, repo: str, issue_numbers: List[int], body: str,
) -> Dict[str, Any]:
    if len(issue_numbers) > BULK_COMMENT_MAX_ISSUES:
        return {
            "status": "error", "all_passed": False,
            "message": (
                f"Bulk comment rejected: {len(issue_numbers)} issues exceeds "
                f"the maximum of {BULK_COMMENT_MAX_ISSUES}."
            ),
        }

    allowed: List[int] = []
    blocked: List[Dict] = []
    for num in issue_numbers:
        result = validate_comment(token, org, repo, num, body)
        if result["all_passed"]:
            allowed.append(num)
        else:
            failed_names = [n for n, chk in result["checks"].items() if not chk["passed"]]
            blocked.append({"issue_number": num, "reasons": failed_names})

    return {
        "status": "success" if not blocked else "partial",
        "all_passed": len(blocked) == 0,
        "total": len(issue_numbers),
        "allowed": allowed, "allowed_count": len(allowed),
        "blocked": blocked, "blocked_count": len(blocked),
        "message": (
            f"Bulk comment validation: {len(allowed)} allowed, {len(blocked)} blocked "
            f"out of {len(issue_numbers)} issues."
        ),
    }


# ---------------------------------------------------------------------------
# Transfer issue guardrails
# ---------------------------------------------------------------------------

def validate_transfer_issue(
    token: str, org: str, repo: str, issue_number: int, target_repo: str,
) -> Dict[str, Any]:
    checks: Dict[str, Dict[str, Any]] = {}

    state, _ = _get_issue_state(token, org, repo, issue_number)
    checks["source_exists"] = {
        "passed": state is not None,
        "detail": f"Issue #{issue_number} {'found' if state else 'not found'} in {org}/{repo}",
    }
    if state is not None:
        checks["source_open"] = {"passed": state == "open", "detail": f"State: {state}"}

    full_target = f"{org}/{target_repo}" if "/" not in target_repo else target_repo
    try:
        get(token, f"/repos/{full_target}")
        checks["target_repo_exists"] = {"passed": True, "detail": f"{full_target} found"}
    except requests.HTTPError:
        checks["target_repo_exists"] = {"passed": False, "detail": f"{full_target} not found"}

    return _checks_result(
        f"{org}/{repo}#{issue_number} -> {full_target}", checks,
    )
