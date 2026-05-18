#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Projects Handler for Security Advisories Lambda Functions.

This module handles project discovery via aggregation queries against
the scans index, returning sorted project names and their tags.

Functions:
    handle_list_projects: Handle list_projects requests
"""

import json
import logging
from typing import Any, Dict

from aws_utils import opensearch_request
from config import config

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def handle_list_projects(request_id: str) -> Dict[str, Any]:
    """Handle list_projects requests via aggregation query.

    Builds a terms aggregation on project.name with a nested sub-aggregation
    on project.tag, executes it against the scans index, and returns the
    results sorted alphabetically by project name with tags sorted in
    descending order.

    Args:
        request_id: Short request ID for log correlation.

    Returns:
        Structured result dict with sorted projects and tags.
    """
    logger.info(f"[{request_id}] LIST_PROJECTS: Listing projects and tags")

    query_body = json.dumps({
        'size': 0,
        'aggs': {
            'projects': {
                'terms': {
                    'field': 'project.name',
                    'size': 1000,
                },
                'aggs': {
                    'tags': {
                        'terms': {
                            'field': 'project.tag',
                            'size': 1000,
                        },
                    },
                },
            },
        },
    })

    try:
        response = opensearch_request(
            'POST',
            f'/{config.scans_index}/_search',
            query_body,
        )
    except Exception as e:
        logger.error(f"[{request_id}] LIST_PROJECTS_FAILED: {e}")
        return {
            'status': 'error',
            'message': f'Failed to list projects: {e}',
        }

    # Log response metadata for debugging
    total_hits = response.get('hits', {}).get('total', {})
    logger.info(f"[{request_id}] LIST_PROJECTS: total_hits={total_hits}, has_aggregations={'aggregations' in response}")

    # Parse aggregation buckets
    aggs = response.get('aggregations', {})
    project_buckets = aggs.get('projects', {}).get('buckets', [])

    projects = []
    for bucket in project_buckets:
        project_name = bucket['key']
        tag_buckets = bucket.get('tags', {}).get('buckets', [])
        tags = sorted(
            [tb['key'] for tb in tag_buckets],
            reverse=True,
        )
        projects.append({'name': project_name, 'tags': tags})

    # Sort projects alphabetically by name
    projects.sort(key=lambda p: p['name'])

    logger.info(f"[{request_id}] LIST_PROJECTS: Found {len(projects)} projects")

    return {
        'status': 'success',
        'project_count': len(projects),
        'projects': projects,
    }
