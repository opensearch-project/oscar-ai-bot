#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""DSL Query Builder for Security Advisories Lambda Functions.

This module constructs OpenSearch Query DSL directly from structured parameters
for vulnerability queries. It replaces the previous agentic search flow that
relied on an ML-powered pipeline for NL→DSL translation.

Functions:
    resolve_version_tag: Map user-provided version to canonical tag format (re-exported from query_utils)
    query_vulnerabilities: Construct and execute a DSL query for vulnerability scans
    query_advisories: Query advisories index to filter CVEs by age and/or severity
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from aws_utils import get_latest_scans_index, opensearch_request
from query_utils import connection_error, error_response, resolve_version_tag

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Default query size — matches the previous agentic search configuration
_DEFAULT_QUERY_SIZE = 1000


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

    # Log truncation warning when total hits exceed the returned count
    hits = result.get('hits', {}) if isinstance(result, dict) else {}
    if not isinstance(hits, dict):
        hits = {}
    total_hits = hits.get('total', {}).get('value', 0)
    returned_count = len(hits.get('hits', []))
    if total_hits > returned_count:
        logger.warning(
            f'DSL_QUERY: results truncated — '
            f'returned {returned_count} of {total_hits} total hits '
            f'(size limit: {_DEFAULT_QUERY_SIZE})',
        )

    return result


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
        return error_response('index_resolution_error', 'Failed to resolve scans index.')

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
            return error_response(
                'opensearch_error',
                f'OpenSearch query failed: {error_msg}',
                status_code=status_code,
            )

        # Connection or unexpected error
        logger.error(
            f'SECURITY_ADVISORIES_DSL_QUERY_FAILED: {error_msg}',
        )
        return connection_error(e)

    return result


# --- Advisories Index Query ---

# The advisories alias points to the current advisories index.
_ADVISORIES_INDEX = 'advisories'

# Maximum number of advisory IDs to query in a single terms lookup.
# OpenSearch has a default max_terms_count of 65536; we use a conservative
# batch size to stay well within limits and avoid oversized payloads.
_ADVISORIES_BATCH_SIZE = 1000


def query_advisories(
    cve_ids: List[str],
    age_days: Optional[int] = None,
    severity: Optional[Set[str]] = None,
) -> Tuple[Set[str], bool]:
    """Query the advisories index to filter CVEs by age and/or severity.

    Constructs a bool/filter query that:
      1. Matches advisory documents whose ``aliases`` field contains any of
         the provided CVE IDs. This is more resilient than matching on ``id``
         because advisory re-keying can change the ``id`` while ``aliases``
         retains all known identifiers.
      2. Optionally filters to those with ``timestamp.publish`` older than the
         cutoff date (when ``age_days`` is provided).
      3. Optionally filters by severity level(s) (when ``severity`` is provided).

    At least one of ``age_days`` or ``severity`` must be specified for this
    function to execute a query. If neither is provided, returns an empty set.

    Args:
        cve_ids: List of CVE/advisory identifiers to look up.
        age_days: Minimum age in days. Only advisories published at least this
            many days ago will be returned. If None, no age filter is applied.
        severity: Optional set of severity levels to filter on (e.g., {"HIGH", "CRITICAL"}).
            If None, no severity filter is applied.

    Returns:
        A tuple of (matched_cve_ids, is_partial) where matched_cve_ids is the
        set of CVE IDs matching the specified criteria, and is_partial is True
        if one or more query batches failed (meaning results may be incomplete).
    """
    if (not cve_ids) or (not age_days and not severity):
        return set(), False

    # Calculate the cutoff date if age filtering is requested
    cutoff_iso = None
    if age_days and age_days > 0:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=age_days)
        cutoff_iso = cutoff.strftime('%Y-%m-%dT%H:%M:%S.000Z')

    # Deduplicate input IDs
    unique_ids = list(set(cve_ids))

    matched_cve_ids: Set[str] = set()
    is_partial = False

    # Batch the terms query to avoid hitting OpenSearch limits
    for i in range(0, len(unique_ids), _ADVISORIES_BATCH_SIZE):
        batch = unique_ids[i:i + _ADVISORIES_BATCH_SIZE]
        batch_set = set(batch)

        filter_clauses: List[Dict[str, Any]] = [
            {'terms': {'aliases': batch}},
        ]

        if cutoff_iso:
            filter_clauses.append({'range': {'timestamp.publish': {'lte': cutoff_iso}}})

        if severity:
            filter_clauses.append({'terms': {'severity': list(severity)}})

        query_body = json.dumps({
            'size': len(batch),
            '_source': ['aliases'],
            'query': {
                'bool': {
                    'filter': filter_clauses,
                },
            },
        })

        try:
            result = _execute_query(_ADVISORIES_INDEX, query_body)
        except Exception as e:
            error_msg = str(e)
            logger.error(
                f'SECURITY_ADVISORIES_ADVISORIES_QUERY_FAILED: {error_msg}',
            )
            # Mark results as partial and continue with remaining batches
            is_partial = True
            continue

        hits = result.get('hits', {}).get('hits', [])

        for hit in hits:
            aliases = hit.get('_source', {}).get('aliases', [])
            for alias in aliases:
                if alias in batch_set:
                    matched_cve_ids.add(alias)

    logger.info(
        f'ADVISORIES_QUERY: Found {len(matched_cve_ids)} matching CVE(s)'
        f'{" (partial results due to batch failure)" if is_partial else ""}',
    )

    return matched_cve_ids, is_partial
