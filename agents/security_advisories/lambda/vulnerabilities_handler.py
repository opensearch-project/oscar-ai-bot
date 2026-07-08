#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Vulnerabilities Handler for Security Advisories Lambda Functions.

This module orchestrates the direct DSL query flow for vulnerability queries:
resolve parameters, execute a structured DSL query, extract and filter results,
and return structured data.

Functions:
    handle_query_vulnerabilities: Handle query_vulnerabilities requests
"""

import logging
from typing import Any, Dict, Optional, Set

from dsl_query_builder import (_DEFAULT_QUERY_SIZE, query_advisories,
                               query_vulnerabilities, resolve_version_tag)
from response_filter import (build_neglected_page_url, build_summary,
                             filter_vulnerabilities)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Fields to retain when trimming vulnerability objects for the response.
_VULN_SUMMARY_FIELDS = ('id', 'severity', 'advisory_url')


def _parse_severity(raw: Optional[str]) -> Optional[Set[str]]:
    """Parse a comma-separated severity string into a normalised set.

    Args:
        raw: Comma-separated severity levels (e.g. ``"CRITICAL,HIGH"``).

    Returns:
        Set of upper-cased severity strings, or ``None`` if *raw* is empty.
    """
    if not raw:
        return None
    return {s.strip().upper() for s in raw.split(',') if s.strip()}


def _parse_age_days(raw: Optional[str]) -> Optional[int]:
    """Parse an age-in-days value to an integer.

    Args:
        raw: String representation of the age threshold in days.

    Returns:
        Positive integer, or ``None`` if *raw* is empty or invalid.
    """
    if not raw:
        return None
    try:
        value = int(raw)
        return value if value > 0 else None
    except (ValueError, TypeError):
        return None


def _map_age_days_to_age(age_days: Optional[int]) -> Optional[str]:
    """Map an integer age-in-days value to the nearest valid neglected page bucket.

    The neglected page only supports discrete values: 15d, 30d, 45d, 60d.
    This maps the user's numeric threshold to the closest valid bucket.

    Args:
        age_days: Numeric age threshold from the action group parameter.

    Returns:
        A valid age bucket string (e.g. ``"30d"``), or ``None`` if not applicable.
    """
    if age_days is None:
        return None

    buckets = [15, 30, 45, 60]
    for bucket in buckets:
        if age_days <= bucket:
            return f"{bucket}d"
    return f"{buckets[-1]}d"


def _process_hits(
    hits: list,
    request_id: str,
    allowed_cve_ids: Optional[Set[str]] = None,
) -> list:
    """Process raw search hits into filtered, trimmed result entries.

    Each hit represents a distinct project from the latest scan index.
    The DSL query uses ``collapse`` on ``project.name`` to return only
    the most recent scan document per project, so no application-level
    deduplication is needed.

    When ``allowed_cve_ids`` is provided (from the advisories index query),
    only vulnerabilities whose ID is in that set are retained. This handles
    both severity and age filtering via a single allowlist.

    When ``allowed_cve_ids`` is None (no severity or age filter), only
    exclusion filtering is applied (removing excluded CVEs).

    Args:
        hits: Hit list from the DSL query response (already deduplicated via collapse).
        request_id: Short request ID for log correlation.
        allowed_cve_ids: If provided, only retain vulnerabilities whose ID is in
            this set. Used when severity and/or age filtering is active.

    Returns:
        List of structured result dicts ready for the response payload.
    """
    results = []
    for hit in hits:
        source = hit.get('_source', {})
        project = source.get('project', {})
        timestamp = source.get('timestamp', {})

        raw_vulns = source.get('vulnerabilities', [])

        if allowed_cve_ids is not None:
            # Advisories-based filtering: keep only non-excluded CVEs in the allowlist
            filtered_vulns = filter_vulnerabilities(raw_vulns, severity=None)
            pre_allowlist_count = len(filtered_vulns)
            filtered_vulns = [
                v for v in filtered_vulns if v.get('id') in allowed_cve_ids
            ]
            if pre_allowlist_count > 0 or len(filtered_vulns) > 0:
                logger.info(
                    f"[{request_id}] PROCESS_HITS: project={project.get('name')}, "
                    f"raw={len(raw_vulns)}, after_exclusion_filter={pre_allowlist_count}, "
                    f"after_advisories_filter={len(filtered_vulns)}",
                )
        else:
            # No severity/age filter — just remove excluded CVEs
            filtered_vulns = filter_vulnerabilities(raw_vulns, severity=None)

        trimmed_vulns = [
            {k: v for k, v in vuln.items() if k in _VULN_SUMMARY_FIELDS}
            for vuln in filtered_vulns
        ]

        entry = {
            'project': project,
            'timestamp': timestamp,
            'filtered_vulnerabilities': trimmed_vulns,
            'filtered_count': len(trimmed_vulns),
            'severity_summary': build_summary(filtered_vulns),
        }

        # Only include total_count when advisories filtering is NOT active.
        # When filtering is active the total scan counts are misleading
        # because they reflect the full scan, not the filtered subset.
        if allowed_cve_ids is None:
            entry['total_count'] = source.get('count', {})

        results.append(entry)
    return results


def handle_query_vulnerabilities(params: Dict[str, Any], request_id: str) -> Dict[str, Any]:
    """Handle query_vulnerabilities requests via direct DSL query.

    Extracts query parameters, executes a structured DSL query against the
    scans index, and post-processes results with severity/exclusion/age filtering.

    When ``age_days`` is provided, performs a secondary query against the
    advisories index to identify CVEs whose ``timestamp.publish`` is older
    than the specified threshold. Only those CVEs are retained in the results.

    Args:
        params: Parameters dict containing:
            - query (str): Natural language query (required).
            - version (str, optional): Version to scope the query.
            - project_name (str, optional): Project name to scope the query.
            - severity (str, optional): Comma-separated severity levels.
            - age_days (str, optional): Minimum age in days — only return CVEs
              published at least this many days ago.
        request_id: Short request ID for log correlation.

    Returns:
        Structured result dict with status, results, and metadata.
    """
    query = params.get('query', '')
    version = params.get('version')
    project_name = params.get('project_name')
    severity = _parse_severity(params.get('severity'))
    age_days = _parse_age_days(params.get('age_days'))

    logger.info(
        f"[{request_id}] QUERY_VULNERABILITIES: query='{query}', "
        f"version={version}, project_name={project_name}, "
        f"severity={severity}, age_days={age_days}",
    )

    # Resolve version to canonical project.tag format
    resolved_tag = None
    if version:
        resolved_tag = resolve_version_tag(version)
        if resolved_tag != version:
            logger.info(
                f"[{request_id}] TAG_RESOLVED: '{version}' -> '{resolved_tag}'"
            )

    # Execute DSL query
    response = query_vulnerabilities(version=version, project_name=project_name)

    # Check for error response
    if response.get('status') == 'error':
        logger.error(f"[{request_id}] SECURITY_ADVISORIES_DSL_QUERY_FAILED: {response.get('message')}")
        return response

    # Extract hits and total count
    hits_envelope = response.get('hits', {})
    hits = hits_envelope.get('hits', [])

    if not hits:
        logger.info(f"[{request_id}] No hits returned from DSL query")
        return {
            'status': 'success',
            'message': 'No results found for the given query. Try broadening or rephrasing your search.',
            'results': [],
            'result_count': 0,
        }

    total_value = hits_envelope.get('total', {}).get('value', len(hits))

    # Log collapse deduplication stats (total is pre-collapse, hits is post-collapse)
    collapsed_count = total_value - len(hits)
    if collapsed_count > 0:
        logger.info(
            f"[{request_id}] COLLAPSE: {total_value} total matches -> "
            f"{len(hits)} after collapse (removed {collapsed_count} duplicate(s))",
        )

    # With collapse, total_value > len(hits) is normal (duplicates removed).
    # True truncation only occurs when the collapsed result count hits the
    # query size limit, meaning there may be more unique projects than returned.
    results_truncated = len(hits) >= _DEFAULT_QUERY_SIZE

    # Advisories filtering: when severity or age_days is specified, query the
    # advisories index to get the authoritative set of CVE IDs matching those
    # criteria. This single allowlist replaces separate application-side filters.
    allowed_cve_ids = None
    advisories_partial = False
    if severity or age_days:
        # Collect all CVE IDs across all scan hits
        all_cve_ids = []
        for hit in hits:
            vulns = hit.get('_source', {}).get('vulnerabilities', [])
            for vuln in vulns:
                vuln_id = vuln.get('id')
                if vuln_id:
                    all_cve_ids.append(vuln_id)

        if all_cve_ids:
            allowed_cve_ids, advisories_partial = query_advisories(
                all_cve_ids, age_days=age_days, severity=severity,
            )
            logger.info(
                f"[{request_id}] ADVISORIES_FILTER: {len(allowed_cve_ids)} of "
                f"{len(set(all_cve_ids))} unique CVE(s) match criteria "
                f"(severity={severity}, age_days={age_days})",
            )

    # Process each scan document hit
    results = _process_hits(hits, request_id, allowed_cve_ids=allowed_cve_ids)

    logger.info(f"[{request_id}] Returning {len(results)} result entries")

    if results_truncated:
        logger.info(
            f"[{request_id}] Results truncated: returned {len(hits)} "
            f"collapsed results (hit size limit of {_DEFAULT_QUERY_SIZE})",
        )

    # Build neglected page URL derived from available action-group parameters
    neglected_url = build_neglected_page_url(
        age=_map_age_days_to_age(age_days),
        severe='HIGH' in severity if severity else None,
        critical='CRITICAL' in severity if severity else None,
        tag=resolved_tag or version,
    )

    result = {
        'status': 'success',
        'result_count': len(results),
        'total_matching_documents': total_value,
        'results_truncated': results_truncated,
        'results': results,
        'neglected_page_url': neglected_url,
    }

    if advisories_partial:
        result['advisory_filter_warning'] = (
            "Some advisory lookups failed. The severity/age filter results "
            "shown may be incomplete — some matching CVEs could be missing."
        )

    if results_truncated:
        result['truncation_message'] = (
            f"Showing {len(results)} unique projects (query size limit reached). "
            "Results may be incomplete — consider narrowing your query with "
            "additional filters (e.g. project_name, version, or severity)."
        )

    return result
