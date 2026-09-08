#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.

"""
Metrics Handler for Metrics Lambda Functions.

This module provides the main metrics query handling logic using agentic search.
The conversational agent on the OpenSearch side handles index routing, so this
handler only needs to enhance the query, execute the search, and return results.

Functions:
    handle_metrics_query: Main metrics query handler using agentic search
"""

import logging
from typing import Any, Dict, Optional

from agentic_search import AgenticSearchError, agentic_search, enhance_query
from config import config
from data_processors import (extract_build_results, extract_release_results,
                             extract_test_results)
from summary_generators import (generate_build_summary,
                                generate_integration_summary,
                                generate_release_summary)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def handle_metrics_query(params: Dict[str, Any], request_id: Optional[str] = None) -> Dict[str, Any]:
    """Metrics query handler using agentic search.

    Receives a natural language query and version, enhances the query with
    filters, executes agentic search via the conversational agent, and
    returns results. Index routing is handled by the conversational agent.

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

        # Step 1: Enhance query with version and filters
        pipeline_name = config.agentic_pipeline
        enhanced_query = enhance_query(query, version, filters if filters else None)
        logger.info(f"METRICS_QUERY [{req_id}]: Enhanced query='{enhanced_query}'")

        # Step 2: Execute agentic search (conversational agent handles index routing)
        memory_id = params.get('memory_id')
        try:
            opensearch_results = agentic_search(pipeline_name, enhanced_query, memory_id=memory_id)
            logger.info(f"METRICS_QUERY [{req_id}]: Agentic search completed")
        except AgenticSearchError as e:
            logger.error(f"AGENTIC_SEARCH_FAILED [{req_id}]: {e}")
            # Return a clear non-retryable error so Bedrock agent stops retrying
            return {
                'error': str(e),
                'status_code': e.status_code,
                'type': 'agentic_search_error',
                'retryable': False,
                'message': 'The search agent could not generate a valid query. '
                           'Try rephrasing or simplifying the question. Do not retry this exact query.'
            }

        # Step 3: Validate response structure
        if 'hits' not in opensearch_results or 'hits' not in opensearch_results.get('hits', {}):
            logger.error(f"METRICS_QUERY [{req_id}]: Unexpected response structure - missing hits")
            return {'error': 'Unexpected response structure', 'type': 'response_parse_error'}

        # Step 4: Log generated DSL for debugging
        generated_dsl = opensearch_results.get('ext', {}).get('dsl_query')
        if generated_dsl:
            logger.info(f"METRICS_QUERY [{req_id}]: Generated DSL: {generated_dsl}")

        # Step 5: Extract, deduplicate, and summarize results
        # Detect data type from the index name in the first hit
        first_hit_index = ''
        raw_hits = opensearch_results.get('hits', {}).get('hits', [])
        if raw_hits:
            first_hit_index = raw_hits[0].get('_index', '')
            logger.info(f"METRICS_QUERY [{req_id}]: Resolved index: {first_hit_index}")
        else:
            logger.info(f"METRICS_QUERY [{req_id}]: Resolved index: none (empty result set)")

        if 'integration-test' in first_hit_index:
            results = extract_test_results(opensearch_results)
            summary = generate_integration_summary(results)
            data_source = 'opensearch-integration-test-results'
        elif first_hit_index in ('opensearch_release_state', 'opensearch_release_schedule'):
            # The conversational agent can route here via ListIndexTool, but these indices
            # do not fit extract_release_results (opensearch_release_metrics schema, which
            # the 'release' branch below would apply). Release-state questions belong to
            # the dedicated release functions.
            results = [hit.get('_source', {}) for hit in raw_hits]
            summary = {}
            data_source = first_hit_index
        elif 'distribution-build' in first_hit_index:
            results = extract_build_results(opensearch_results)
            summary = generate_build_summary(results)
            data_source = 'opensearch-distribution-build-results'
        elif 'release' in first_hit_index:
            results = extract_release_results(opensearch_results)
            summary = generate_release_summary(results)
            data_source = 'opensearch_release_metrics'
        else:
            # Fallback to raw extraction
            results = [hit.get('_source', {}) for hit in raw_hits]
            summary = {}
            data_source = first_hit_index or 'unknown'

        logger.info(f"METRICS_QUERY [{req_id}]: Extracted {len(results)} results")

        # Log failed components for quick diagnosis
        failed = [r.get('component', 'unknown') for r in results
                  if r.get('component_build_result') == 'failed' or r.get('status') == 'failed']
        if failed:
            logger.warning(f"METRICS_QUERY [{req_id}]: {len(failed)} failures: {failed}")

        # Build response
        response = {
            'version': version,
            'data_source': data_source,
            'total_results': len(results),
            'results': results,
            'summary': summary,
        }

        # Include generated DSL when available
        if generated_dsl:
            response['generated_dsl'] = generated_dsl

        # Include memory_id for conversational context continuity
        response_memory_id = opensearch_results.get('ext', {}).get('memory_id')
        if response_memory_id:
            response['memory_id'] = response_memory_id

        logger.info(f"METRICS_QUERY [{req_id}]: Returning response with {len(results)} results")
        return response

    except Exception as e:
        logger.error(f"METRICS_QUERY [{req_id}]: Unexpected error: {e}")
        return {'error': str(e), 'type': 'metrics_error'}
