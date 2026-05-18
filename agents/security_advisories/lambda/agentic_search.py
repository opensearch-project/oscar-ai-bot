#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Agentic Search Module for Security Advisories Lambda Functions.

This module provides agentic search functionality using OpenSearch's
flow agent to translate natural language queries to DSL. The flow agent
is stateless (single-pass) — there is no memory_id or cross-query memory
at the OpenSearch level.

Functions:
    enhance_query: Append version and project context to natural language query
    agentic_search: Send agentic search request to OpenSearch
"""

import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class AgenticSearchError(Exception):
    """Raised when agentic search request fails."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


def enhance_query(
    query: str,
    version: Optional[str] = None,
    project_name: Optional[str] = None,
) -> str:
    """Append version and project context to the natural language query.

    Args:
        query: Original natural language query.
        version: Optional version to scope the query (e.g., '2.19.6').
        project_name: Optional project name to scope the query.

    Returns:
        Enhanced query string with version and project context appended.
    """
    parts = [query]

    if version:
        parts.append(f'for version {version}')

    if project_name:
        parts.append(f'project: {project_name}')

    enhanced = ' '.join(parts)
    logger.info(f"ENHANCE_QUERY: '{query}' -> '{enhanced}'")
    return enhanced


def agentic_search(pipeline: str, query_text: str, index: str = None) -> Dict[str, Any]:
    """Send agentic search request to OpenSearch.

    Sends a GET to /{index}/_search?search_pipeline={pipeline} with the
    agentic query body. The flow agent is stateless — no memory_id is sent.

    Args:
        pipeline: Agentic pipeline name (e.g., 'oscar-agentic-pipeline').
        query_text: Enhanced natural language query.
        index: Index name to search against. Defaults to config.scans_index.

    Returns:
        Raw OpenSearch response dict.

    Raises:
        AgenticSearchError: On request failure with status code and reason.
    """
    from aws_utils import opensearch_request
    from config import config

    if index is None:
        index = config.scans_index

    path = f'/{index}/_search?search_pipeline={pipeline}'
    body = json.dumps({
        'query': {
            'agentic': {
                'query_text': query_text,
            },
        },
    })

    logger.info(f'AGENTIC_SEARCH: GET {path}')
    logger.info(f"AGENTIC_SEARCH: query_text='{query_text}'")

    try:
        result = opensearch_request('GET', path, body)
    except Exception as e:
        error_msg = str(e)
        status_code = None
        if 'OpenSearch request failed:' in error_msg:
            try:
                status_code = int(
                    error_msg.split('OpenSearch request failed:')[1]
                    .strip()
                    .split(' ')[0],
                )
            except (ValueError, IndexError):
                pass
        logger.error(f'SECURITY_ADVISORIES_AGENTIC_SEARCH_FAILED: {error_msg}')
        raise AgenticSearchError(
            f'Agentic search request failed: {e}', status_code=status_code,
        )

    # Log generated DSL if present
    dsl_query = result.get('ext', {}).get('dsl_query')
    if dsl_query:
        logger.info(f'AGENTIC_SEARCH: Generated DSL: {json.dumps(dsl_query)}')

    return result
