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
from typing import Any, Dict, Optional

import semver

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
    and specific release version tags as three-part semver (e.g., ``2.19.6``).

    Mapping rules:
      - Already prefixed with ``"origin/"`` → returned as-is
      - ``"main"`` or ``"latest"`` → ``"origin/main"``
      - Two-part version (e.g., ``"3.7"``) → ``"origin/3.7"`` (branch tag)
      - Three-part version (e.g., ``"3.7.0"``, ``"2.19.6"``) → returned as-is (release tag)
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

    # Try parsing as a full semver (three-part: "3.7.0", "2.19.6")
    try:
        semver.Version.parse(version)
        logger.info(f"RESOLVE_TAG: '{version}' is a valid semver version, using as-is")
        return version
    except ValueError:
        pass

    # Validate that the input is a numeric two-part version (e.g., "3.7")
    # by appending ".0" to form valid semver — rejects non-numeric strings
    try:
        semver.Version.parse(f'{version}.0')
        resolved = f'origin/{version}'
        logger.info(f"RESOLVE_TAG: '{version}' -> '{resolved}'")
        return resolved
    except ValueError:
        pass

    # Non-parseable — return as-is (exact tag lookup)
    logger.info(f"RESOLVE_TAG: Cannot parse '{version}', using as-is")
    return version


def enhance_query(
    query: str = '',
    version: Optional[str] = None,
    resolved_tag: Optional[str] = None,
    project_name: Optional[str] = None,
) -> str:
    """Build a standardized query string for the agentic pipeline.

    Produces a consistent format that the pipeline can reliably parse:
    ``"Show me CVEs tag: {tag} project: {project_name}"``

    This avoids passing arbitrary user phrasing (like "all CVEs", "critical
    vulnerabilities", etc.) which can confuse the pipeline's NL→DSL translation.

    Args:
        query: Original natural language query (used only for logging, not in output).
        version: Original user-provided version (e.g., ``'3.7.0'``).
        resolved_tag: The actual tag to query (e.g., ``'origin/3.7'`` or ``'3.7.0'``).
                      If ``None``, falls back to ``version``.
        project_name: Optional project name to scope the query.

    Returns:
        Standardized query string for the agentic pipeline.
    """
    tag_to_use = resolved_tag or version

    parts = ['Show me CVEs']

    if tag_to_use:
        parts.append(f'tag: {tag_to_use}')

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
