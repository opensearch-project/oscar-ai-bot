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
import re
from typing import Any, Dict, Tuple

import semver

from aws_utils import get_latest_scans_index, opensearch_request

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _semver_sort_key(tag: str) -> Tuple:
    """Generate a sort key for semantic version comparison.

    Handles standard semver (e.g., "2.19.6", "3.7.0").
    Non-version tags (e.g., "origin/main") sort to the end.

    Args:
        tag: Version tag string to parse.

    Returns:
        Tuple suitable for reverse sorting (version tags first, highest first).
    """
    try:
        version = semver.Version.parse(tag, optional_minor_and_patch=True)
        return (1, version)
    except ValueError:
        pass

    # Non-version tags get (0,) so they sort after version tags in reverse
    return (0, (tag,))


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
            f'/{get_latest_scans_index()}/_search',
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
            key=_semver_sort_key,
            reverse=True,
        )

        # Determine the latest release version (highest semver, excluding branch tags)
        version_tags = [t for t in tags if re.match(r'^\d+', t)]
        latest_version = version_tags[0] if version_tags else None

        # Determine the latest development branch (highest origin/X.Y tag)
        branch_tags = [t for t in tags if re.match(r'^origin/\d+\.\d+$', t)]
        latest_branch = branch_tags[0] if branch_tags else None

        project_entry: Dict[str, Any] = {'name': project_name}
        if latest_version:
            project_entry['latest_version'] = latest_version
        if latest_branch:
            project_entry['latest_branch'] = latest_branch

        projects.append(project_entry)

    # Sort projects alphabetically by name
    projects.sort(key=lambda p: p['name'])

    logger.info(f"[{request_id}] LIST_PROJECTS: Found {len(projects)} projects")

    return {
        'status': 'success',
        'project_count': len(projects),
        'projects': projects,
        'ACTION_REQUIRED': (
            'STOP. DO NOT call query_vulnerabilities. '
            'Present the user with these options for their chosen project:\n'
            '1. latest_version (the specific shipped release)\n'
            '2. latest_branch (the in-progress development branch)\n'
            '3. origin/main (the latest unreleased code)\n'
            'Wait for the user to choose before proceeding.'
        ),
    }
