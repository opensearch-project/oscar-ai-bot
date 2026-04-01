#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.

"""
Metrics Handler for Metrics Lambda Functions.

This module provides the main metrics query handling logic using agentic search,
coordinating between index routing, query enhancement, and data processors.

Functions:
    handle_metrics_query: Main metrics query handler using agentic search
"""

import logging
from typing import Any, Dict, Optional

from agentic_search import (AgenticSearchError, IndexRoutingError,
                            agentic_search, enhance_query, route_index)
from data_processors import (extract_build_results, extract_release_results,
                             extract_test_results)
from summary_generators import (generate_build_summary,
                                generate_integration_summary,
                                generate_release_summary)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def handle_metrics_query(params: Dict[str, Any], request_id: Optional[str] = None) -> Dict[str, Any]:
    """Metrics query handler using agentic search.

    Receives a natural language query and version, routes to the appropriate index,
    enhances the query with filters, executes agentic search, and processes results.

    Args:
        params: Parameters for the query containing:
            - query: Natural language query (required)
            - version: Version to scope the query (required)
            - components: Optional list of components to filter
            - status_filter: Optional status filter ('passed', 'failed')
            - platform: Optional platform filter
            - architecture: Optional architecture filter
            - distribution: Optional distribution filter
        request_id: Optional request ID for logging

    Returns:
        Dictionary containing query results and metadata
    """
    req_id = request_id or "unknown"

    try:
        logger.info(f"METRICS_QUERY [{req_id}]: Starting agentic search handler")
        logger.info(f"METRICS_QUERY [{req_id}]: params keys: {list(params.keys()) if isinstance(params, dict) else 'Not a dict'}")

        # Extract required parameters
        query = params.get('query')
        version = params.get('version')

        # Validate required parameters
        if not query:
            return {'error': 'Query is required for metrics queries'}
        if not version:
            return {'error': 'Version is required for metrics queries'}

        logger.info(f"METRICS_QUERY [{req_id}]: query='{query}', version={version}")

        # Extract optional filter parameters
        components = params.get('components') or []
        status_filter = params.get('status_filter')
        platform = params.get('platform')
        architecture = params.get('architecture')
        distribution = params.get('distribution')

        # Normalize components if string
        if isinstance(components, str):
            components = [item.strip() for item in components.split(',') if item.strip()]

        # Build filters dict for query enhancement
        filters = {}
        if components:
            filters['components'] = components
        if status_filter:
            filters['status'] = status_filter
        if platform:
            filters['platform'] = platform
        if architecture:
            filters['architecture'] = architecture
        if distribution:
            filters['distribution'] = distribution

        logger.info(f"METRICS_QUERY [{req_id}]: filters={filters}")

        # Step 1: Route to appropriate index and pipeline
        try:
            index_pattern, pipeline_name, agent_type = route_index(query)
            logger.info(f"METRICS_QUERY [{req_id}]: Routed to index={index_pattern}, pipeline={pipeline_name}, agent_type={agent_type}")
        except IndexRoutingError as e:
            logger.warning(f"METRICS_QUERY [{req_id}]: Index routing failed: {e}")
            return {'error': str(e), 'type': 'routing_error'}

        logger.info(f"METRICS_QUERY [{req_id}]: agent_type={agent_type}")

        # Step 2: Enhance query with version and filters
        enhanced_query = enhance_query(query, version, filters if filters else None)
        logger.info(f"METRICS_QUERY [{req_id}]: Enhanced query='{enhanced_query}'")

        # Step 3: Execute agentic search
        try:
            opensearch_results = agentic_search(index_pattern, pipeline_name, enhanced_query)
            logger.info(f"METRICS_QUERY [{req_id}]: Agentic search completed")
        except AgenticSearchError as e:
            logger.error(f"METRICS_QUERY [{req_id}]: Agentic search failed: {e}")
            return {
                'error': str(e),
                'status_code': e.status_code,
                'type': 'agentic_search_error'
            }

        # Step 4: Validate response structure
        if 'hits' not in opensearch_results or 'hits' not in opensearch_results.get('hits', {}):
            logger.error(f"METRICS_QUERY [{req_id}]: Unexpected response structure - missing hits")
            return {'error': 'Unexpected response structure', 'type': 'response_parse_error'}

        # Step 5: Log generated DSL for debugging
        generated_dsl = opensearch_results.get('ext', {}).get('dsl_query')
        if generated_dsl:
            logger.info(f"METRICS_QUERY [{req_id}]: Generated DSL: {generated_dsl}")

        # Step 6: Extract and process results based on agent type
        logger.info(f"METRICS_QUERY [{req_id}]: Extracting results for agent_type={agent_type}")

        if agent_type == 'integration-test':
            results = extract_test_results(opensearch_results)
            summary = generate_integration_summary(results)
            data_source = 'opensearch-integration-test-results'
        elif agent_type == 'build-metrics':
            results = extract_build_results(opensearch_results)
            summary = generate_build_summary(results)
            data_source = 'opensearch-distribution-build-results'
        elif agent_type == 'release-metrics':
            results = extract_release_results(opensearch_results)
            summary = generate_release_summary(results)
            data_source = 'opensearch_release_metrics'
        else:
            # Fallback to raw extraction
            hits = opensearch_results.get('hits', {}).get('hits', [])
            results = [hit.get('_source', {}) for hit in hits]
            summary = {}
            data_source = index_pattern

        logger.info(f"METRICS_QUERY [{req_id}]: Extracted {len(results)} results")

        # Build response
        response = {
            'agent_type': agent_type,
            'version': version,
            'data_source': data_source,
            'total_results': len(results),
            'results': results,
            'summary': summary,
        }

        # Include generated DSL when available
        if generated_dsl:
            response['generated_dsl'] = generated_dsl

        logger.info(f"METRICS_QUERY [{req_id}]: Returning response with {len(results)} results")
        return response

    except Exception as e:
        logger.error(f"METRICS_QUERY [{req_id}]: Unexpected error: {e}")
        return {'error': str(e), 'type': 'metrics_error'}
