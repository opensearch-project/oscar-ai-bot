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
flow agent with QueryPlanningTool to translate natural language queries to DSL.

Functions:
    route_index: Determine target index and pipeline from query intent
    enhance_query: Append version and filters to natural language query
    agentic_search: Send agentic search request to OpenSearch
"""

import json
import logging
from typing import Any, Dict, Optional, Tuple

from config import config

logger = logging.getLogger(__name__)


class IndexRoutingError(Exception):
    """Raised when query intent cannot be determined for index routing."""
    pass


class AgenticSearchError(Exception):
    """Raised when agentic search request fails."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


# Mapping from keywords to (config_index_attr, agent_type)
# Index names are resolved at runtime from config so they match the flow agent's
# concrete index (or alias) rather than a wildcard pattern.
# All indices share a single agentic pipeline (config.agentic_pipeline).
ROUTING_KEYWORDS = {
    'build': ('build_results_index', 'build-metrics'),
    'test': ('integration_test_index', 'integration-test'),
    'integration': ('integration_test_index', 'integration-test'),
    'release': ('release_metrics_index', 'release-metrics'),
    'readiness': ('release_metrics_index', 'release-metrics'),
}


def route_index(query: str) -> Tuple[str, str, str]:
    """Determine target index, pipeline, and agent type from query intent.

    Uses keyword matching on terms like 'build', 'test', 'integration',
    'release', 'readiness' to classify intent. First match wins.
    Index names are resolved from config so they match the flow agent's
    concrete index (or alias) on the cluster.
    All indices share a single agentic pipeline.

    Args:
        query: Natural language query

    Returns:
        Tuple of (index_name, pipeline_name, agent_type)

    Raises:
        IndexRoutingError: When intent cannot be determined
    """
    query_lower = query.lower()

    for keyword, (index_attr, agent_type) in ROUTING_KEYWORDS.items():
        if keyword in query_lower:
            index_name = getattr(config, index_attr)
            pipeline_name = config.agentic_pipeline
            logger.info(f"ROUTE_INDEX: Matched keyword '{keyword}' -> index={index_name}, pipeline={pipeline_name}, agent_type={agent_type}")
            return (index_name, pipeline_name, agent_type)

    raise IndexRoutingError(
        "Cannot determine query intent. Please specify if this is about builds, tests, or releases."
    )


def enhance_query(query: str, version: str, filters: Optional[Dict[str, Any]] = None) -> str:
    """Append version and explicit filters to the natural language query.

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
    # Instruct the LLM to use a large size in the generated DSL
    enhanced += f'. Use size {config.large_query_size} in the query.'
    logger.info(f"ENHANCE_QUERY: '{query}' -> '{enhanced}'")
    return enhanced


def agentic_search(index: str, pipeline: str, query_text: str) -> Dict[str, Any]:
    """Send agentic search request to OpenSearch.

    Sends a GET to /{index}/_search?search_pipeline={pipeline} with
    the agentic query body. Uses SigV4 signing for auth.

    Args:
        index: Target index name (e.g., 'opensearch-integration-test-results-03-2026')
        pipeline: Agentic pipeline name for this index
        query_text: Enhanced natural language query

    Returns:
        Raw OpenSearch response dict

    Raises:
        AgenticSearchError: On request failure with status code and reason
    """
    from aws_utils import opensearch_request

    path = f'/{index}/_search?search_pipeline={pipeline}'
    body = {
        "size": config.large_query_size,
        "query": {
            "agentic": {
                "query_text": query_text
            }
        }
    }

    logger.info(f"AGENTIC_SEARCH: GET {path}")
    logger.info(f"AGENTIC_SEARCH: query_text='{query_text}'")

    try:
        result = opensearch_request('GET', path, body)
    except Exception as e:
        raise AgenticSearchError(f"Agentic search request failed: {e}")

    # Log generated DSL if present
    dsl_query = result.get('ext', {}).get('dsl_query')
    if dsl_query:
        logger.info(f"AGENTIC_SEARCH: Generated DSL: {json.dumps(dsl_query)}")

    return result
