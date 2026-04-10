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
from authorizer import audit_log, is_write_operation, validate_org_scope
from github_api import (add_comment, bulk_comment, get_external_contributors,
                        get_new_maintainers, get_new_repositories,
                        transfer_issue)
from guardrails import (bulk_merge, list_merge_candidates,
                        validate_bulk_comment, validate_comment,
                        validate_single_pr, validate_transfer_issue)
from http_client import ORG, GitHubAPIError
from mcp_client import MCPClient
from response_builder import create_response

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

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


# Maps Bedrock action group function names to MCP tool names.
# Functions mapped to None are handled via direct API calls.
TOOL_NAME_MAP = {
    # Read operations
    "get_pr_details": "pull_request_read",
    "list_prs": "list_pull_requests",
    "get_issue_details": "issue_read",
    "list_issues": "list_issues",
    # Search operations
    "search_issues": "search_issues",
    "search_pull_requests": "search_pull_requests",
    # Write operations (MCP)
    "merge_pr": "merge_pull_request",
    "create_issue": "issue_write",
    "close_issue": "issue_write",
    # Write operations (direct API)
    "transfer_issue": None,
    "add_comment": None,
    "bulk_comment": None,
    # Bulk merge operations (direct API with guardrails)
    "list_merge_candidates": None,
    "bulk_merge_prs": None,
    # Community metrics (direct API)
    "get_new_maintainers": None,
    "get_new_repositories": None,
    "get_external_contributors": None,
}

# Tools that need owner/repo injected
_NEEDS_OWNER = {
    "pull_request_read", "list_pull_requests",
    "issue_read", "list_issues",
    "merge_pull_request", "issue_write",
}

# Functions handled via direct GitHub REST API (not MCP)
_DIRECT_API_FUNCTIONS = {
    "transfer_issue", "add_comment", "bulk_comment",
    "list_merge_candidates", "bulk_merge_prs",
    "get_new_maintainers", "get_new_repositories", "get_external_contributors",
}


def _transform_params(function_name: str, params: Dict[str, str]) -> Dict[str, Any]:
    """Transform Bedrock params to MCP tool arguments."""
    mcp_tool = TOOL_NAME_MAP.get(function_name, function_name)
    args: Dict[str, Any] = dict(params)

    # Inject owner for tools that take owner/repo
    if mcp_tool and mcp_tool in _NEEDS_OWNER and "owner" not in args:
        args["owner"] = ORG

    if function_name == "get_pr_details":
        args["pullNumber"] = int(args.pop("pr_number"))
        args["method"] = "get"

    elif function_name == "get_issue_details":
        args["issue_number"] = int(args.pop("issue_number"))
        args["method"] = "get"

    elif function_name == "list_issues":
        if "state" in args:
            args["state"] = args["state"].upper()
        if "labels" in args and isinstance(args["labels"], str):
            args["labels"] = [lab.strip() for lab in args["labels"].split(",") if lab.strip()]

    elif function_name == "merge_pr":
        args["pullNumber"] = int(args.pop("pr_number"))
        if "merge_method" not in args:
            args["merge_method"] = "merge"

    elif function_name == "create_issue":
        args["method"] = "create"
        if "labels" in args and isinstance(args["labels"], str):
            args["labels"] = [lab.strip() for lab in args["labels"].split(",") if lab.strip()]
        if "assignees" in args and isinstance(args["assignees"], str):
            args["assignees"] = [a.strip() for a in args["assignees"].split(",") if a.strip()]

    elif function_name == "close_issue":
        args["method"] = "update"
        args["issue_number"] = int(args.pop("issue_number"))
        args["state"] = "closed"
        reason = args.pop("reason", "completed")
        args["state_reason"] = reason

    return args


def _handle_direct_api(
    function_name: str, params: Dict[str, str], client: MCPClient, request_id: str,
) -> str:
    """Handle functions that require direct GitHub REST API calls."""
    token = client.get_token()
    repo = params.get("repo", "")

    if function_name == "transfer_issue":
        target_repo = params.get("target_repo", "")
        issue_number = int(params.get("issue_number", "0"))
        logger.info(
            "GITHUB [%s]: Direct API transfer_issue #%d from %s to %s",
            request_id, issue_number, repo, target_repo,
        )
        return transfer_issue(token, ORG, repo, issue_number, target_repo)

    elif function_name == "add_comment":
        issue_number = int(params.get("issue_number", "0"))
        body = params.get("body", "")
        logger.info(
            "GITHUB [%s]: Direct API add_comment on %s#%d",
            request_id, repo, issue_number,
        )
        return add_comment(token, ORG, repo, issue_number, body)

    elif function_name == "bulk_comment":
        issue_numbers_str = params.get("issue_numbers", "")
        issue_numbers = [int(n.strip()) for n in issue_numbers_str.split(",") if n.strip()]
        body = params.get("body", "")
        logger.info(
            "GITHUB [%s]: Direct API bulk_comment on %s issues %s",
            request_id, repo, issue_numbers,
        )
        return bulk_comment(token, ORG, repo, issue_numbers, body)

    elif function_name == "list_merge_candidates":
        version = params.get("version", "")
        org = params.get("organization", ORG)
        logger.info(
            "GITHUB [%s]: list_merge_candidates version=%s org=%s",
            request_id, version, org,
        )
        return list_merge_candidates(token, version, org)

    elif function_name == "bulk_merge_prs":
        version = params.get("version", "")
        confirmed = params.get("confirmed")
        org = params.get("organization", ORG)

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

        logger.info(
            "GITHUB [%s]: bulk_merge_prs version=%s org=%s",
            request_id, version, org,
        )
        return bulk_merge(token, version, org)

    elif function_name == "get_new_maintainers":
        since = params.get("since", "")
        until = params.get("until", "")
        org = params.get("organization", ORG)
        status = params.get("status", "closed")
        logger.info(
            "GITHUB [%s]: get_new_maintainers org=%s since=%s until=%s status=%s",
            request_id, org, since, until, status,
        )
        return get_new_maintainers(token, org, since, until, status)

    elif function_name == "get_new_repositories":
        since = params.get("since", "")
        until = params.get("until", "")
        org = params.get("organization", ORG)
        status = params.get("status", "closed")
        logger.info(
            "GITHUB [%s]: get_new_repositories org=%s since=%s until=%s status=%s",
            request_id, org, since, until, status,
        )
        return get_new_repositories(token, org, since, until, status)

    elif function_name == "get_external_contributors":
        repo = params.get("repo", "")
        since = params.get("since", "")
        until = params.get("until", "")
        org = params.get("organization", ORG)
        logger.info(
            "GITHUB [%s]: get_external_contributors org=%s repo=%s since=%s until=%s",
            request_id, org, repo, since, until,
        )
        return get_external_contributors(token, org, repo, since, until)

    raise ValueError(f"Unknown direct API function: {function_name}")


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main Lambda handler for GitHub agent."""
    request_id = str(uuid.uuid4())[:8]
    function_name = ""
    params = {}
    try:
        function_name = event.get("function", "")
        logger.info("GITHUB [%s]: Function: '%s'", request_id, function_name)

        if function_name not in TOOL_NAME_MAP:
            return create_response(event, {"error": f"Unknown function: {function_name}"})

        params = _parse_params(event)

        # --- Authorization: validate org scope ---
        org_error = validate_org_scope(function_name, params)
        if org_error:
            logger.warning("GITHUB [%s]: Org validation failed: %s", request_id, org_error)
            audit_log(function_name, params, org_error, False, request_id)
            return create_response(event, {"error": org_error})

        # Log write operations at INFO level for auditability
        if is_write_operation(function_name):
            logger.info(
                "GITHUB [%s]: WRITE operation '%s' on repo '%s', params: %s",
                request_id, function_name, params.get("repo", "N/A"),
                json.dumps({k: v for k, v in params.items() if k != "content"}),
            )

        client = _get_mcp_client()

        # --- Guardrail gates ---
        token = client.get_token()

        if function_name == "merge_pr":
            repo = params.get("repo", "")
            pr_number = int(params.get("pr_number", "0"))
            force = str(params.get("force", "")).strip().lower() in ("true", "1", "yes")
            guardrail_result = validate_single_pr(token, ORG, repo, pr_number)
            if guardrail_result.get("is_auto_pr") and not guardrail_result.get("all_passed"):
                if force:
                    logger.warning(
                        "GITHUB [%s]: merge_pr guardrails OVERRIDDEN (force=true) for %s#%d: %s",
                        request_id, repo, pr_number, guardrail_result.get("message", ""),
                    )
                    audit_log(function_name, params, f"FORCE MERGE — guardrails overridden: {guardrail_result.get('message', '')}", True, request_id)
                else:
                    logger.warning(
                        "GITHUB [%s]: merge_pr blocked by guardrails for %s#%d",
                        request_id, repo, pr_number,
                    )
                    audit_log(function_name, params, guardrail_result["message"], False, request_id)
                    return create_response(event, guardrail_result)

        elif function_name == "add_comment":
            repo = params.get("repo", "")
            issue_number = int(params.get("issue_number", "0"))
            body = params.get("body", "")
            guardrail_result = validate_comment(token, ORG, repo, issue_number, body)
            if not guardrail_result["all_passed"]:
                logger.warning(
                    "GITHUB [%s]: add_comment blocked by guardrails for %s#%d",
                    request_id, repo, issue_number,
                )
                audit_log(function_name, params, guardrail_result["message"], False, request_id)
                return create_response(event, guardrail_result)

        elif function_name == "bulk_comment":
            repo = params.get("repo", "")
            issue_numbers_str = params.get("issue_numbers", "")
            issue_numbers = [int(n.strip()) for n in issue_numbers_str.split(",") if n.strip()]
            body = params.get("body", "")
            guardrail_result = validate_bulk_comment(token, ORG, repo, issue_numbers, body)
            if not guardrail_result["all_passed"]:
                logger.warning(
                    "GITHUB [%s]: bulk_comment blocked by guardrails: %d/%d issues blocked",
                    request_id, guardrail_result["blocked_count"], guardrail_result.get("total", 0),
                )
                audit_log(function_name, params, guardrail_result["message"], False, request_id)
                return create_response(event, guardrail_result)

        elif function_name == "transfer_issue":
            repo = params.get("repo", "")
            issue_number = int(params.get("issue_number", "0"))
            target_repo = params.get("target_repo", "")
            guardrail_result = validate_transfer_issue(token, ORG, repo, issue_number, target_repo)
            if not guardrail_result["all_passed"]:
                logger.warning(
                    "GITHUB [%s]: transfer_issue blocked by guardrails for %s#%d",
                    request_id, repo, issue_number,
                )
                audit_log(function_name, params, guardrail_result["message"], False, request_id)
                return create_response(event, guardrail_result)

        # --- Route: direct API or MCP ---
        if function_name in _DIRECT_API_FUNCTIONS:
            result = _handle_direct_api(function_name, params, client, request_id)
        else:
            mcp_tool = TOOL_NAME_MAP[function_name]
            mcp_args = _transform_params(function_name, params)
            logger.info(
                "GITHUB [%s]: MCP tool: '%s', args: %s",
                request_id, mcp_tool, json.dumps(mcp_args),
            )
            result = client.call_tool(mcp_tool, mcp_args)

        audit_log(function_name, params, "success", True, request_id)
        return create_response(event, result)

    except GitHubAPIError as e:
        logger.error("GITHUB [%s]: API error: %s", request_id, e)
        audit_log(function_name, params, str(e), False, request_id)
        return create_response(event, {
            "error": str(e),
            "status_code": e.status_code,
        })
    except Exception as e:
        logger.error("GITHUB [%s]: %s\n%s", request_id, e, traceback.format_exc())
        audit_log(function_name, params, str(e), False, request_id)
        return create_response(event, {"error": str(e)})
