#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Agentic Search Module for Security Advisories Lambda Functions.

This module provides agentic search functionality using OpenSearch's
flow agent to translate natural language queries to DSL. The flow agent
is stateless (single-pass) — there is no memory_id or cross-query memory
at the OpenSearch level.

Functions:
    resolve_version_tag: Map user-provided version to canonical tag format
    enhance_query: Append version and project context to natural language query
    agentic_search: Send agentic search request to OpenSearch
"""

import json
import logging
import re
from typing import Any, Dict, Optional

from aws_utils import get_latest_scans_index, opensearch_request

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class AgenticSearchError(Exception):
    """Raised when agentic search request fails."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


def resolve_version_tag(version: str) -> str:
    """Map a user-provided version string to the canonical project.tag format.

    The scans index stores release branch tags as ``origin/{major}.{minor}``
    (e.g., ``origin/2.19``, ``origin/3.7``). Users typically provide full
    semver versions like ``"2.19.6"`` or ``"3.7.0"``. This function maps
    user input to the canonical tag format used in the index.

    Mapping rules:
      - Semver input (e.g., ``"2.19.6"``, ``"3.7.0"``) → ``"origin/2.19"``, ``"origin/3.7"``
      - ``"main"`` or ``"latest"`` → ``"origin/main"``
      - Already prefixed with ``"origin/"`` → returned as-is
      - Non-parseable input → returned as-is (for exact tag lookups)

    Args:
        version: User-provided version or tag string.

    Returns:
        The canonical tag string to use in queries.
    """
    if not version:
        return version

    # Already in origin/ format — pass through
    if version.startswith('origin/'):
        logger.info(f"RESOLVE_TAG: '{version}' already has origin/ prefix, using as-is")
        return version

    # "main" or "latest" → origin/main
    if version.lower() in ('main', 'latest'):
        resolved = 'origin/main'
        logger.info(f"RESOLVE_TAG: '{version}' -> '{resolved}'")
        return resolved

    # Semver: extract major.minor → origin/{major}.{minor}
    match = re.match(r'^(\d+)\.(\d+)(?:\.\d+)*$', version)
    if match:
        major = match.group(1)
        minor = match.group(2)
        resolved = f'origin/{major}.{minor}'
        logger.info(f"RESOLVE_TAG: '{version}' -> '{resolved}'")
        return resolved

    # Non-parseable — return as-is (exact tag lookup)
    logger.info(f"RESOLVE_TAG: Cannot parse '{version}', using as-is")
    return version


def enhance_query(
    query: str,
    version: Optional[str] = None,
    resolved_tag: Optional[str] = None,
    project_name: Optional[str] = None,
) -> str:
    """Enhance a natural language query with version/project context.

    When a ``resolved_tag`` is provided and differs from the user's
    ``version``, the version string in the query text is replaced with
    the resolved tag so the agentic pipeline sees a single, unambiguous
    tag reference.

    Args:
        query: Original natural language query.
        version: Original user-provided version (e.g., ``'3.7.0'``).
        resolved_tag: The actual tag in the index (e.g., ``'origin/3.7'``).
                      If ``None``, falls back to ``version``.
        project_name: Optional project name to scope the query.

    Returns:
        Enhanced query string with resolved tag and project context.
    """
    tag_to_use = resolved_tag or version

    # If we resolved to a different tag, replace the original version in the query
    if version and tag_to_use and tag_to_use != version and version in query:
        query = query.replace(version, tag_to_use)

    parts = [query]

    if tag_to_use and tag_to_use not in query:
        parts.append(f'for version {tag_to_use}')

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

    if index is None:
        index = get_latest_scans_index()

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
