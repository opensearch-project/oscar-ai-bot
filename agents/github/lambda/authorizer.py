# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Authorization and audit logging for GitHub agent write operations."""

import logging
from typing import Dict, Optional

from http_client import ORG

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Functions that perform mutating operations
WRITE_FUNCTIONS = frozenset({
    "merge_pr",
    "create_issue",
    "close_issue",
    "transfer_issue",
    "add_comment",
    "bulk_comment",
    "bulk_merge_prs",
})


def is_write_operation(function_name: str) -> bool:
    """Check if a function is a mutating/write operation."""
    return function_name in WRITE_FUNCTIONS


def validate_org_scope(function_name: str, params: Dict[str, str]) -> Optional[str]:
    """Validate that the operation targets only the opensearch-project organization.

    Returns an error message if validation fails, None if valid.
    """
    # Reject any model-supplied organization that differs from the configured ORG
    org_param = params.get("organization", "")
    if org_param and org_param != ORG:
        return (
            f"Operation rejected: organization '{org_param}' is not permitted. "
            f"Only operations within {ORG} are allowed."
        )

    # For transfer_issue, validate the target repo is within the org
    if function_name == "transfer_issue":
        target_repo = params.get("target_repo", "")
        if "/" in target_repo:
            return (
                f"Transfer rejected: target repository '{target_repo}' appears to be "
                f"outside the {ORG} organization. Only transfers within {ORG} are allowed."
            )

    # For all operations with a repo param, ensure no org prefix that differs
    repo = params.get("repo", "")
    if "/" in repo:
        parts = repo.split("/", 1)
        if parts[0] != ORG:
            return (
                f"Operation rejected: repository '{repo}' is outside the {ORG} organization. "
                f"Only repositories within {ORG} are supported."
            )

    return None


def audit_log(
    function_name: str,
    params: Dict[str, str],
    result: str,
    success: bool,
    request_id: str,
) -> None:
    """Log an audit entry for a GitHub agent operation."""
    repo = params.get("repo", "N/A")
    is_write = is_write_operation(function_name)
    level = "WRITE" if is_write else "READ"

    log_entry = {
        "request_id": request_id,
        "level": level,
        "function": function_name,
        "repo": repo,
        "success": success,
    }

    # Include authenticated actor IDs when available (from 2PR params)
    requester = params.get("requester_user_id")
    approver = params.get("approver_user_id")
    if requester:
        log_entry["requester_user_id"] = requester
    if approver:
        log_entry["approver_user_id"] = approver

    if is_write:
        if "pr_number" in params:
            log_entry["pr_number"] = params["pr_number"]
        if "issue_number" in params:
            log_entry["issue_number"] = params["issue_number"]
        if "issue_numbers" in params:
            log_entry["issue_numbers"] = params["issue_numbers"]
        if "target_repo" in params:
            log_entry["target_repo"] = params["target_repo"]

    if success:
        logger.info("AUDIT %s", log_entry)
    else:
        logger.error("AUDIT %s | result: %s", log_entry, str(result)[:500])
