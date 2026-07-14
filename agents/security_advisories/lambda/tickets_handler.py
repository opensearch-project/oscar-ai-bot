#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tickets Handler for Security Advisories Lambda Functions.

This module handles ticket query requests against the tickets OpenSearch index.
It supports querying tickets by CVE ID, project name, or branch, and listing
projects that have assigned tickets.

Functions:
    handle_query_tickets: Handle query_tickets requests
    handle_list_ticket_projects: Handle list_ticket_projects requests
"""

import json
import logging
from typing import Any, Dict

from aws_utils import opensearch_request
from tickets_query_builder import (build_list_projects_query,
                                   build_tickets_query)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

TICKETS_INDEX = "tickets"
_TICKET_URL_PREFIX = "https://t.corp.amazon.com/"


def handle_query_tickets(params: Dict[str, str], request_id: str) -> Dict[str, Any]:
    """Handle query_tickets requests.

    Extracts query parameters, builds a DSL query via the tickets query builder,
    executes it against the tickets index, and returns structured results.

    Args:
        params: Parameters dict containing optional keys:
            - cve_id (str): CVE identifier to filter tickets.
            - project_name (str): Project name to filter tickets.
            - branch (str): Branch name to filter tickets.
        request_id: Short request ID for log correlation.

    Returns:
        On success: {"status": "success", "result_count": N, "results": [...]}
        On error: {"status": "error", "type": "...", "message": "..."}
    """
    cve_id = params.get('cve_id')
    project_name = params.get('project_name')
    branch = params.get('branch')

    logger.info(
        f"[{request_id}] QUERY_TICKETS: cve_id={cve_id}, "
        f"project_name={project_name}, branch={branch}",
    )

    query_body_dict = build_tickets_query(
        cve_id=cve_id, project_name=project_name, branch=branch,
    )
    query_body = json.dumps(query_body_dict)

    try:
        result = opensearch_request('GET', f'/{TICKETS_INDEX}/_search', body=query_body)
    except Exception as e:
        error_message = str(e)
        logger.error(f"[{request_id}] QUERY_TICKETS_FAILED: {error_message}")
        if "OpenSearch request failed:" in error_message:
            return {
                'status': 'error',
                'type': 'opensearch_error',
                'message': error_message,
            }
        return {
            'status': 'error',
            'type': 'connection_error',
            'message': error_message,
        }

    hits = result.get('hits', {}).get('hits', [])
    results = []
    for hit in hits:
        ticket_id = hit.get("_source", {}).get("ticketId")
        if not ticket_id:
            continue
        results.append({
            "ticketId": ticket_id,
            "ticket_url": f'{_TICKET_URL_PREFIX}{ticket_id}',
        })

    logger.info(f"[{request_id}] QUERY_TICKETS: Found {len(results)} ticket(s)")

    return {
        'status': 'success',
        'result_count': len(results),
        'results': results,
    }


def handle_list_ticket_projects(request_id: str) -> Dict[str, Any]:
    """Handle list_ticket_projects requests.

    Builds a collapsed query to find unique project names with assigned tickets,
    executes it against the tickets index, and returns the project list.

    Args:
        request_id: Short request ID for log correlation.

    Returns:
        On success: {"status": "success", "projects": [...]}
        On error: {"status": "error", "type": "...", "message": "..."}
    """
    logger.info(f"[{request_id}] LIST_TICKET_PROJECTS: Listing projects with assigned tickets")

    query_body_dict = build_list_projects_query()
    query_body = json.dumps(query_body_dict)

    try:
        result = opensearch_request('GET', f'/{TICKETS_INDEX}/_search', body=query_body)
    except Exception as e:
        error_message = str(e)
        logger.error(f"[{request_id}] LIST_TICKET_PROJECTS_FAILED: {error_message}")
        if "OpenSearch request failed:" in error_message:
            return {
                'status': 'error',
                'type': 'opensearch_error',
                'message': error_message,
            }
        return {
            'status': 'error',
            'type': 'connection_error',
            'message': error_message,
        }

    hits = result.get('hits', {}).get('hits', [])
    projects = [
        hit.get("_source", {}).get("projectName")
        for hit in hits
        if hit.get("_source", {}).get("projectName")
    ]

    logger.info(f"[{request_id}] LIST_TICKET_PROJECTS: Found {len(projects)} project(s)")

    return {
        'status': 'success',
        'projects': projects,
    }
