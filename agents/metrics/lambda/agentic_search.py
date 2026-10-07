#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.

"""
Agentic Search Module for Metrics Lambda Functions.

This module provides agentic search functionality using OpenSearch's
conversational agent to translate natural language queries to DSL.
The conversational agent handles index routing internally, so the
Lambda only needs to send the query text and pipeline name.

Functions:
    enhance_query: Append version and filters to natural language query
    agentic_search: Send agentic search request to OpenSearch
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class AgenticSearchError(Exception):
    """Raised when agentic search request fails."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


def enhance_query(query: str, version: str, filters: Optional[Dict[str, Any]] = None) -> str:
    """Append version, date context, and explicit filters to the natural language query.

    Args:
        query: Original natural language query
        version: Version to scope the query (e.g., '3.2.0')
        filters: Dict of optional filters
            {components, status, platform, architecture, distribution}

    Returns:
        Enhanced query string
    """
    parts = [query]

    if version:
        parts.append(f"for version {version}")

    # Add current month/year so the agent picks the right monthly index
    now = datetime.utcnow()
    parts.append(f"Index date suffix: {now.strftime('%m-%Y')}.")

    if filters:
        if filters.get('components'):
            components = filters['components']
            if isinstance(components, list):
                parts.append(f"components: {', '.join(components)}")
            else:
                parts.append(f"component: {components}")

        if filters.get('status'):
            parts.append(f"status: {filters['status']}")

        if filters.get('platform'):
            parts.append(f"platform: {filters['platform']}")

        if filters.get('architecture'):
            parts.append(f"architecture: {filters['architecture']}")

        if filters.get('distribution'):
            parts.append(f"distribution: {filters['distribution']}")

    enhanced = ' '.join(parts)
    logger.info(f"ENHANCE_QUERY: '{query}' -> '{enhanced}'")
    return enhanced


def agentic_search(
    pipeline: str,
    query_text: str,
    memory_id: Optional[str] = None,
    index: Optional[str] = None,
) -> Dict[str, Any]:
    """Send agentic search request to OpenSearch.

    Sends a GET to /{index}/_search?search_pipeline={pipeline} with the agentic query
    body. Which of the two arguments is needed depends on the agent behind the pipeline:

    - A conversational agent (metrics) routes indices itself via ListIndexTool and
      IndexMappingTool, so index is omitted, and memory_id gives it conversational
      context across follow-up queries.
    - A flow agent (release state) holds only a QueryPlanningTool and has no memory, so
      the index MUST be supplied - it is the only way the planner receives a mapping -
      and memory_id must be left unset.

    Args:
        pipeline: Agentic pipeline name (e.g., 'metrics-agentic-pipeline')
        query_text: Enhanced natural language query
        memory_id: Optional memory ID; only meaningful for a conversational agent
        index: Optional index to scope the search to; required for a flow agent

    Returns:
        Raw OpenSearch response dict

    Raises:
        AgenticSearchError: On request failure with status code and reason
    """
    from aws_utils import opensearch_request

    scope = f'/{index}' if index else ''
    path = f'{scope}/_search?search_pipeline={pipeline}'
    body = {
        "query": {
            "agentic": {
                "query_text": query_text
            }
        }
    }

    # Include memory_id for conversational context if provided
    if memory_id:
        body["query"]["agentic"]["memory_id"] = memory_id
        logger.info(f"AGENTIC_SEARCH: Using memory_id={memory_id}")

    logger.info(f"AGENTIC_SEARCH: GET {path}")
    logger.info(f"AGENTIC_SEARCH: query_text='{query_text}'")

    try:
        result = opensearch_request('GET', path, body)
    except Exception as e:
        error_msg = str(e)
        # Extract status code from error message if present
        status_code = None
        if 'OpenSearch request failed:' in error_msg:
            try:
                status_code = int(error_msg.split('OpenSearch request failed:')[1].strip().split(' ')[0])
            except (ValueError, IndexError):
                pass
        raise AgenticSearchError(f"Agentic search request failed: {e}", status_code=status_code)

    # Log generated DSL if present
    dsl_query = result.get('ext', {}).get('dsl_query')
    if dsl_query:
        logger.info(f"AGENTIC_SEARCH: Generated DSL: {json.dumps(dsl_query)}")

    # Return memory_id from response if present (for future calls)
    response_memory_id = result.get('ext', {}).get('memory_id')
    if response_memory_id:
        logger.info(f"AGENTIC_SEARCH: Response memory_id={response_memory_id}")

    return result
