#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""DSL Query Builder for Security Advisories Lambda Functions.

This module constructs OpenSearch Query DSL directly from structured parameters
for vulnerability queries. It replaces the previous agentic search flow that
relied on an ML-powered pipeline for NL→DSL translation.

Functions:
    resolve_version_tag: Map user-provided version to canonical tag format
    query_vulnerabilities: Construct and execute a DSL query for vulnerability scans
"""

import json
import logging
import re
from typing import Any, Dict, Optional

import semver
from aws_utils import get_latest_scans_index, opensearch_request

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Default query size — matches the previous agentic search configuration
_DEFAULT_QUERY_SIZE = 1000

# Strict two-part numeric pattern (e.g., "3.7", "2.19") to avoid
# misclassifying pre-release/build metadata strings like "3.7-rc".
_TWO_PART_RE = re.compile(r'^\d+\.\d+$')


def _classify_version(version: str) -> str:
    """Classify a version string into a known category for dispatch.

    Returns one of: 'origin_prefixed', 'main_alias', 'three_part', 'two_part', 'unknown'.
    """
    if version.startswith('origin/'):
        return 'origin_prefixed'
    if version.lower() in ('main', 'latest'):
        return 'main_alias'
    try:
        semver.Version.parse(version)
        return 'three_part'
    except (ValueError, TypeError):
        pass
    if _TWO_PART_RE.match(version):
        try:
            semver.Version.parse(f'{version}.0')
            return 'two_part'
        except (ValueError, TypeError):
            pass
    return 'unknown'


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

    match _classify_version(version):
        case 'origin_prefixed':
            logger.info(f"RESOLVE_TAG: '{version}' already has origin/ prefix, using as-is")
            return version
        case 'main_alias':
            resolved = 'origin/main'
            logger.info(f"RESOLVE_TAG: '{version}' -> '{resolved}'")
            return resolved
        case 'three_part':
            logger.info(f"RESOLVE_TAG: '{version}' is a valid semver version, using as-is")
            return version
        case 'two_part':
            resolved = f'origin/{version}'
            logger.info(f"RESOLVE_TAG: '{version}' -> '{resolved}'")
            return resolved
        case _:
            logger.info(f"RESOLVE_TAG: Cannot parse '{version}', using as-is")
            return version


def _build_dsl_query(
    resolved_tag: Optional[str] = None,
    project_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the OpenSearch Query DSL body.

    Constructs a bool/filter query with term clauses for the provided
    parameters, or a match_all query if no filters are specified.

    Args:
        resolved_tag: Resolved version tag for project.tag filter.
        project_name: Exact project name for project.name filter.

    Returns:
        A dict ready for json.dumps() containing the query body.
    """
    filters = []

    if resolved_tag:
        filters.append({'term': {'project.tag': resolved_tag}})

    if project_name:
        filters.append({'term': {'project.name': project_name}})

    # Sort by scan timestamp descending so the newest scan per project
    # appears first when combined with collapse.
    sort = [{'timestamp.scan': {'order': 'desc'}}]

    # Collapse on project.name to return only the most recent scan
    # document per project. Combined with the descending sort, this
    # guarantees one result per project — the latest scan.
    collapse = {'field': 'project.name'}

    if filters:
        query = {
            'size': _DEFAULT_QUERY_SIZE,
            'sort': sort,
            'collapse': collapse,
            'query': {
                'bool': {
                    'filter': filters,
                },
            },
        }
    else:
        query = {
            'size': _DEFAULT_QUERY_SIZE,
            'sort': sort,
            'collapse': collapse,
            'query': {
                'match_all': {},
            },
        }

    return query


def _execute_query(index: str, query_body: str) -> Dict[str, Any]:
    """Execute the DSL query via opensearch_request.

    Args:
        index: The OpenSearch index to query.
        query_body: JSON-encoded query body string.

    Returns:
        The OpenSearch response dict.

    Raises:
        Exception: If the request fails (non-2xx, connection error, etc.).
    """
    path = f'/{index}/_search'

    logger.info(f'DSL_QUERY: GET {path}')
    logger.info(f'DSL_QUERY: body={query_body}')

    result = opensearch_request('GET', path, body=query_body)

    # Log truncation warning when result count equals the configured size
    hits = result.get('hits') if isinstance(result, dict) else None
    documents = hits.get('hits', []) if isinstance(hits, dict) else []
    if len(documents) == _DEFAULT_QUERY_SIZE:
        logger.warning(
            f'DSL_QUERY: results may be truncated — '
            f'returned {_DEFAULT_QUERY_SIZE} documents (equals size limit of {_DEFAULT_QUERY_SIZE})',
        )

    return result


def _error_response(
    error_type: str,
    message: str,
    status_code: Optional[int] = None,
) -> Dict[str, Any]:
    """Return a consistent error response dict.

    Args:
        error_type: Category of the error (e.g., opensearch_error, connection_error).
        message: Human-readable error description.
        status_code: Optional HTTP status code from OpenSearch.

    Returns:
        Error dict with status, type, retryable, message, and optional status_code.
    """
    error = {
        'status': 'error',
        'type': error_type,
        'retryable': False,
        'message': message,
    }

    if status_code is not None:
        error['status_code'] = status_code

    return error


def _connection_error(exception: Exception) -> Dict[str, Any]:
    """Return a connection error without leaking internal details.

    Logs the original exception internally for diagnostics, then returns
    a sanitized error dict via _error_response for consistent structure.

    Args:
        exception: The caught exception from the connection failure.

    Returns:
        Sanitized error dict with consistent structure.
    """
    logger.error(f'CONNECTION_ERROR: {type(exception).__name__}: {exception}')
    return _error_response(
        'connection_error',
        'Failed to connect to the OpenSearch cluster. '
        'The service may be temporarily unavailable.',
    )


def query_vulnerabilities(
    version: Optional[str] = None,
    project_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Construct and execute a DSL query for vulnerability scan documents.

    Orchestrates the full query flow: resolve the target index, resolve
    the version tag, build the DSL query, execute it, and return the result.

    Args:
        version: User-provided version string (resolved via resolve_version_tag).
        project_name: Exact project name for term filter.

    Returns:
        On success: The standard OpenSearch response envelope {"hits": {"hits": [...]}}.
        On error: {"status": "error", "retryable": False, "message": "...", ...}
    """
    # Resolve the target index
    try:
        index = get_latest_scans_index()
    except RuntimeError as e:
        logger.error(
            f'SECURITY_ADVISORIES_DSL_QUERY_FAILED: '
            f'Could not resolve scans index: {e}',
        )
        return _error_response('index_resolution_error', str(e))

    # Resolve version tag:
    # - version provided → resolve to canonical tag format
    # - only project_name provided → no tag filter (return all versions)
    # - neither provided → default to origin/main
    if version:
        resolved_tag = resolve_version_tag(version)
    elif project_name:
        resolved_tag = None
    else:
        resolved_tag = 'origin/main'

    # Build the DSL query
    query_body_dict = _build_dsl_query(
        resolved_tag=resolved_tag,
        project_name=project_name,
    )
    query_body = json.dumps(query_body_dict)

    # Execute the query
    try:
        result = _execute_query(index, query_body)
    except Exception as e:
        error_msg = str(e)

        # Check if this is an OpenSearch HTTP error
        if 'OpenSearch request failed:' in error_msg:
            status_code = None
            try:
                status_code = int(
                    error_msg.split('OpenSearch request failed:')[1]
                    .strip()
                    .split(' ')[0],
                )
            except (ValueError, IndexError):
                pass

            logger.error(
                f'SECURITY_ADVISORIES_DSL_QUERY_FAILED: {error_msg}',
            )
            return _error_response(
                'opensearch_error',
                f'OpenSearch query failed: {error_msg}',
                status_code=status_code,
            )

        # Connection or unexpected error
        logger.error(
            f'SECURITY_ADVISORIES_DSL_QUERY_FAILED: {error_msg}',
        )
        return _connection_error(e)

    return result
