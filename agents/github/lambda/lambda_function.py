# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Lambda handler for GitHub agent — delegates to GitHub MCP Server via subprocess."""

import json
import logging
import os
import traceback
import uuid
from typing import Any, Dict

import boto3
from authorizer import audit_log, validate_org_scope
from github_api import (add_comment, bulk_comment, get_repo_maintainers,
                        transfer_issue)
from guardrails import (bulk_merge, list_merge_candidates,
                        validate_bulk_comment, validate_comment,
                        validate_single_pr, validate_transfer_issue)
from http_client import ORG, GitHubAPIError
from mcp_client import MCPClient
from oscar_shared.approval_guard import validate_two_person_approval
from registry import FunctionDef
from response_builder import create_response

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Fields redacted from write-operation audit logs
_REDACTED_FIELDS = frozenset({"content", "body"})


# ---------------------------------------------------------------------------
# MCP param transforms
# ---------------------------------------------------------------------------

def _transform_get_pr_details(params: Dict[str, str]) -> Dict[str, Any]:
    args = dict(params)
    args["pullNumber"] = int(args.pop("pr_number"))
    args["method"] = "get"
    return args


def _transform_get_issue_details(params: Dict[str, str]) -> Dict[str, Any]:
    args = dict(params)
    args["issue_number"] = int(args.pop("issue_number"))
    args["method"] = "get"
    return args


def _transform_list_issues(params: Dict[str, str]) -> Dict[str, Any]:
    args = dict(params)
    if "state" in args:
        args["state"] = args["state"].upper()
    if "labels" in args and isinstance(args["labels"], str):
        args["labels"] = [lab.strip() for lab in args["labels"].split(",") if lab.strip()]
    return args


def _transform_merge_pr(params: Dict[str, str]) -> Dict[str, Any]:
    args = dict(params)
    args["pullNumber"] = int(args.pop("pr_number"))
    if "merge_method" not in args:
        args["merge_method"] = "merge"
    args.pop("force", None)
    return args


def _transform_create_issue(params: Dict[str, str]) -> Dict[str, Any]:
    args = dict(params)
    args["method"] = "create"
    if "labels" in args and isinstance(args["labels"], str):
        args["labels"] = [lab.strip() for lab in args["labels"].split(",") if lab.strip()]
    if "assignees" in args and isinstance(args["assignees"], str):
        args["assignees"] = [a.strip() for a in args["assignees"].split(",") if a.strip()]
    return args


def _transform_close_issue(params: Dict[str, str]) -> Dict[str, Any]:
    args = dict(params)
    args["method"] = "update"
    args["issue_number"] = int(args.pop("issue_number"))
    args["state"] = "closed"
    reason = args.pop("reason", "completed")
    args["state_reason"] = reason
    return args


def _transform_search_issues(params: Dict[str, str]) -> Dict[str, Any]:
    args = dict(params)
    query = args.get("query", "")
    if f"org:{ORG}" not in query:
        args["query"] = f"org:{ORG} {query}"
    return args


def _transform_search_pull_requests(params: Dict[str, str]) -> Dict[str, Any]:
    args = dict(params)
    query = args.get("query", "")
    if f"org:{ORG}" not in query:
        args["query"] = f"org:{ORG} {query}"
    return args


# ---------------------------------------------------------------------------
# Direct API handlers
# ---------------------------------------------------------------------------

def _parse_issue_targets(issues_str: str) -> list:
    """Parse 'repo1#1,repo2#2' into [(repo, number)] tuples."""
    targets = []
    for entry in issues_str.split(","):
        entry = entry.strip()
        if "#" in entry:
            r, num = entry.rsplit("#", 1)
            targets.append((r.strip(), int(num.strip())))
    return targets


def _handle_transfer_issue(token: str, params: Dict[str, str], request_id: str, session_attributes: Dict[str, str] = None) -> Any:
    repo = params.get("repo", "")
    target_repo = params.get("target_repo", "")
    issue_number = int(params.get("issue_number", "0"))

    enable_2pr = os.environ.get("ENABLE_2PR", "false").lower() == "true"
    approval_error = validate_two_person_approval(
        session_attributes or {}, enable_2pr, f'action=transfer_issue, repo={repo}, issue={issue_number}',
    )
    if approval_error:
        return json.dumps(approval_error)

    logger.info(
        "GITHUB [%s]: Direct API transfer_issue #%d from %s to %s",
        request_id, issue_number, repo, target_repo,
    )
    return transfer_issue(token, ORG, repo, issue_number, target_repo)


def _handle_add_comment(token: str, params: Dict[str, str], request_id: str, session_attributes: Dict[str, str] = None) -> Any:
    repo = params.get("repo", "")
    issue_number = int(params.get("issue_number", "0"))
    body = params.get("body", "")
    logger.info(
        "GITHUB [%s]: Direct API add_comment on %s#%d",
        request_id, repo, issue_number,
    )
    return add_comment(token, ORG, repo, issue_number, body)


def _handle_bulk_comment(token: str, params: Dict[str, str], request_id: str, session_attributes: Dict[str, str] = None) -> Any:
    body = params.get("body", "")
    issue_targets = _parse_issue_targets(params.get("issues", ""))

    enable_2pr = os.environ.get("ENABLE_2PR", "false").lower() == "true"
    approval_error = validate_two_person_approval(
        session_attributes or {}, enable_2pr, f'action=bulk_comment, issues={issue_targets}',
    )
    if approval_error:
        return json.dumps(approval_error)

    logger.info(
        "GITHUB [%s]: Direct API bulk_comment on %d issues",
        request_id, len(issue_targets),
    )
    return bulk_comment(token, ORG, issue_targets, body)


def _handle_list_merge_candidates(token: str, params: Dict[str, str], request_id: str, session_attributes: Dict[str, str] = None) -> Any:
    version = params.get("version", "")
    logger.info(
        "GITHUB [%s]: list_merge_candidates version=%s org=%s",
        request_id, version, ORG,
    )
    return list_merge_candidates(token, version, ORG)


def _handle_bulk_merge_prs(token: str, params: Dict[str, str], request_id: str, session_attributes: Dict[str, str] = None) -> Any:
    version = params.get("version", "")
    confirmed = params.get("confirmed")

    if confirmed is None:
        return json.dumps({
            "status": "error",
            "message": (
                "SECURITY ERROR: 'confirmed' parameter is required. "
                "Use list_merge_candidates first, then call bulk_merge_prs "
                "with confirmed=true after user confirmation."
            ),
        })

    if isinstance(confirmed, str):
        confirmed = confirmed.strip().lower() in ("true", "1", "yes")

    if not confirmed:
        return json.dumps({
            "status": "error",
            "message": "Bulk merge cancelled. confirmed=false.",
        })

    enable_2pr = os.environ.get("ENABLE_2PR", "false").lower() == "true"
    approval_error = validate_two_person_approval(
        session_attributes or {}, enable_2pr, f'action=bulk_merge_prs, version={version}',
    )
    if approval_error:
        return json.dumps(approval_error)

    logger.info(
        "GITHUB [%s]: bulk_merge_prs version=%s org=%s",
        request_id, version, ORG,
    )
    return bulk_merge(token, version, ORG)


def _handle_get_repo_maintainers(token: str, params: Dict[str, str], request_id: str, session_attributes: Dict[str, str] = None) -> Any:
    repo = params.get("repo", "")
    logger.info(
        "GITHUB [%s]: get_repo_maintainers org=%s repo=%s",
        request_id, ORG, repo,
    )
    return get_repo_maintainers(token, ORG, repo)


# ---------------------------------------------------------------------------
# Function registry — single source of truth
# ---------------------------------------------------------------------------

FUNCTIONS: Dict[str, FunctionDef] = {
    # Read operations (MCP, repo-scoped token, no guardrails)
    "get_pr_details": FunctionDef(
        mcp_tool="pull_request_read",
        needs_owner=True,
        transform=_transform_get_pr_details,
    ),
    "list_prs": FunctionDef(
        mcp_tool="list_pull_requests",
        needs_owner=True,
    ),
    "get_issue_details": FunctionDef(
        mcp_tool="issue_read",
        needs_owner=True,
        transform=_transform_get_issue_details,
    ),
    "list_issues": FunctionDef(
        mcp_tool="list_issues",
        needs_owner=True,
        transform=_transform_list_issues,
    ),
    "search_issues": FunctionDef(
        mcp_tool="search_issues",
        transform=_transform_search_issues,
    ),
    "search_pull_requests": FunctionDef(
        mcp_tool="search_pull_requests",
        transform=_transform_search_pull_requests,
    ),

    # Write operations (MCP)
    "merge_pr": FunctionDef(
        mcp_tool="merge_pull_request",
        write=True,
        needs_owner=True,
        transform=_transform_merge_pr,
    ),
    "create_issue": FunctionDef(
        mcp_tool="issue_write",
        write=True,
        needs_owner=True,
        transform=_transform_create_issue,
    ),
    "close_issue": FunctionDef(
        mcp_tool="issue_write",
        write=True,
        needs_owner=True,
        transform=_transform_close_issue,
    ),

    # Write operations (direct API)
    "transfer_issue": FunctionDef(
        write=True,
        token_scope="org",
        handler=_handle_transfer_issue,
    ),
    "add_comment": FunctionDef(
        write=True,
        handler=_handle_add_comment,
    ),
    "bulk_comment": FunctionDef(
        write=True,
        token_scope="org",
        handler=_handle_bulk_comment,
    ),

    # Bulk merge (direct API, org-wide)
    "list_merge_candidates": FunctionDef(
        token_scope="org",
        handler=_handle_list_merge_candidates,
    ),
    "bulk_merge_prs": FunctionDef(
        write=True,
        token_scope="org",
        handler=_handle_bulk_merge_prs,
    ),

    # Maintainer lookup (direct API, repo-scoped)
    "get_repo_maintainers": FunctionDef(
        handler=_handle_get_repo_maintainers,
    ),
}


# ---------------------------------------------------------------------------
# Guardrail dispatch
# ---------------------------------------------------------------------------

def _run_guardrails(
    function_name: str, params: Dict[str, str], token: str, request_id: str,
) -> Dict[str, Any]:
    """Run pre-execution guardrails. Returns guardrail result dict or None if no guardrail applies."""
    if function_name == "merge_pr":
        repo = params.get("repo", "")
        pr_number = int(params.get("pr_number", "0"))
        return validate_single_pr(token, ORG, repo, pr_number)

    elif function_name == "add_comment":
        repo = params.get("repo", "")
        issue_number = int(params.get("issue_number", "0"))
        body = params.get("body", "")
        return validate_comment(token, ORG, repo, issue_number, body)

    elif function_name == "bulk_comment":
        issue_targets = _parse_issue_targets(params.get("issues", ""))
        body = params.get("body", "")
        return validate_bulk_comment(token, ORG, issue_targets, body)

    elif function_name == "transfer_issue":
        repo = params.get("repo", "")
        issue_number = int(params.get("issue_number", "0"))
        target_repo = params.get("target_repo", "")
        return validate_transfer_issue(token, ORG, repo, issue_number, target_repo)

    return None


# Functions that have pre-execution guardrails
_GUARDED_FUNCTIONS = frozenset({"merge_pr", "add_comment", "bulk_comment", "transfer_issue"})


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------

_mcp_client: MCPClient = None


def _get_mcp_client() -> MCPClient:
    """Lazy-init the MCP client from Secrets Manager credentials."""
    global _mcp_client
    if _mcp_client:
        return _mcp_client

    secret_name = os.environ.get("GITHUB_SECRET_NAME", "")
    if not secret_name:
        raise ValueError("GITHUB_SECRET_NAME not set")

    sm = boto3.client("secretsmanager")
    secret_value = sm.get_secret_value(SecretId=secret_name)
    creds = json.loads(secret_value["SecretString"])

    _mcp_client = MCPClient(
        app_id=creds["GITHUB_APP_ID"],
        private_key=creds["GITHUB_PRIVATE_KEY"],
        installation_id=creds["GITHUB_INSTALLATION_ID"],
    )
    return _mcp_client


def _parse_params(event: Dict) -> Dict[str, str]:
    """Parse parameters from Bedrock action group event."""
    params = {}
    for p in event.get("parameters", []):
        if isinstance(p, dict) and "name" in p and "value" in p:
            params[p["name"]] = p["value"]
    return params


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main Lambda handler for GitHub agent."""
    request_id = str(uuid.uuid4())[:8]
    function_name = ""
    params = {}
    try:
        function_name = event.get("function", "")
        logger.info("GITHUB [%s]: Function: '%s'", request_id, function_name)

        func_def = FUNCTIONS.get(function_name)
        if not func_def:
            return create_response(event, {"error": f"Unknown function: {function_name}"})

        params = _parse_params(event)
        session_attributes = event.get("sessionAttributes", {})

        # --- Authorization: validate org scope ---
        org_error = validate_org_scope(function_name, params)
        if org_error:
            logger.warning("GITHUB [%s]: Org validation failed: %s", request_id, org_error)
            audit_log(function_name, params, org_error, False, request_id, session_attributes)
            return create_response(event, {"error": org_error})

        # --- Audit log write operations (redacting sensitive fields) ---
        if func_def.write:
            safe_params = {
                k: (f"<redacted {len(v)} chars>" if k in _REDACTED_FIELDS and isinstance(v, str) else v)
                for k, v in params.items()
            }
            logger.info(
                "GITHUB [%s]: WRITE operation '%s' on repo '%s', params: %s",
                request_id, function_name, params.get("repo", "N/A"),
                json.dumps(safe_params),
            )

        # --- Token acquisition (scoped per AppSec requirement) ---
        client = _get_mcp_client()
        target_repo = params.get("repo", "")
        token = client.get_token(
            repositories=[target_repo] if target_repo and func_def.token_scope == "repo" else None
        )

        # --- Guardrail gates ---
        if function_name in _GUARDED_FUNCTIONS:
            guardrail_result = _run_guardrails(function_name, params, token, request_id)

            if function_name == "merge_pr":
                # merge_pr has special force-override and conditional 2PR logic
                if not guardrail_result.get("all_passed"):
                    force = str(params.get("force", "")).strip().lower() in ("true", "1", "yes")
                    if force:
                        force_approval_error = validate_two_person_approval(
                            session_attributes, True, f'action=force_merge, repo={params.get("repo", "")}, pr={params.get("pr_number", "")}'
                        )
                        if force_approval_error:
                            return create_response(event, json.dumps(force_approval_error))
                        logger.warning(
                            "GITHUB_FORCE_MERGE repo=%s pr=%s user=%s",
                            params.get("repo", ""), params.get("pr_number", ""),
                            session_attributes.get("requester_user_id", "unknown"),
                        )
                        logger.warning(
                            "GITHUB [%s]: merge_pr guardrails OVERRIDDEN (force=true) for %s#%s: %s",
                            request_id, params.get("repo", ""), params.get("pr_number", ""),
                            guardrail_result.get("message", ""),
                        )
                        audit_log(function_name, params, f"FORCE MERGE — guardrails overridden: {guardrail_result.get('message', '')}", True, request_id, session_attributes)
                    else:
                        logger.warning(
                            "GITHUB [%s]: merge_pr blocked by guardrails for %s#%s",
                            request_id, params.get("repo", ""), params.get("pr_number", ""),
                        )
                        audit_log(function_name, params, guardrail_result["message"], False, request_id, session_attributes)
                        return create_response(event, guardrail_result)
                else:
                    # Guardrails passed — enforce 2PR when enabled
                    enable_2pr = os.environ.get("ENABLE_2PR", "false").lower() == "true"
                    approval_error = validate_two_person_approval(
                        session_attributes, enable_2pr,
                        f'action=merge_pr, repo={params.get("repo", "")}, pr={params.get("pr_number", "")}',
                    )
                    if approval_error:
                        return create_response(event, json.dumps(approval_error))

                # Pin merge to validated SHA to prevent TOCTOU race
                validated_sha = guardrail_result.get("head_sha")
                if validated_sha:
                    params["sha"] = validated_sha

            elif guardrail_result and not guardrail_result["all_passed"]:
                # Generic guardrail failure for non-merge functions
                logger.warning(
                    "GITHUB [%s]: %s blocked by guardrails",
                    request_id, function_name,
                )
                audit_log(function_name, params, guardrail_result["message"], False, request_id, session_attributes)
                return create_response(event, guardrail_result)

        # --- Execute: direct API or MCP ---
        if func_def.is_direct_api:
            result = func_def.handler(token, params, request_id, session_attributes)
        else:
            args = func_def.transform(params) if func_def.transform else dict(params)
            if func_def.needs_owner and "owner" not in args:
                args["owner"] = ORG
            logger.info(
                "GITHUB [%s]: MCP tool: '%s', args: %s",
                request_id, func_def.mcp_tool, json.dumps(args),
            )
            result = client.call_tool(func_def.mcp_tool, args)

        audit_log(function_name, params, "success", True, request_id, session_attributes)
        return create_response(event, result)

    except GitHubAPIError as e:
        logger.error("GITHUB [%s]: API error: %s", request_id, e)
        audit_log(function_name, params, str(e), False, request_id, session_attributes)
        return create_response(event, {
            "error": str(e),
            "status_code": e.status_code,
        })
    except Exception as e:
        logger.error("GITHUB [%s]: %s\n%s", request_id, e, traceback.format_exc())
        audit_log(function_name, params, str(e), False, request_id, session_attributes)
        return create_response(event, {"error": str(e)})
