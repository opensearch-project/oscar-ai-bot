#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Vulnerabilities Handler for Security Advisories Lambda Functions.

This module orchestrates the agentic search flow for vulnerability queries:
enhance the NL query, execute agentic search, extract and filter results,
and return structured data.

Functions:
    handle_query_vulnerabilities: Handle query_vulnerabilities requests
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

from agentic_search import AgenticSearchError, agentic_search, enhance_query
from config import config
from response_filter import build_summary, filter_vulnerabilities

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


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


def _is_within_age(timestamp: Dict[str, Any], age_days: int) -> bool:
    """Check whether a scan timestamp falls within the age threshold.

    Supports both ISO-8601 strings and epoch-millis integers for the
    ``scan`` field inside the timestamp dict.

    Args:
        timestamp: Timestamp dict from the scan document (contains ``scan``).
        age_days: Maximum age in days.

    Returns:
        ``True`` if the scan is within the threshold, ``False`` otherwise.
    """
    scan_ts = timestamp.get('scan')
    if scan_ts is None:
        return True  # No timestamp — don't filter out

    try:
        if isinstance(scan_ts, (int, float)):
            # Epoch milliseconds
            scan_dt = datetime.fromtimestamp(scan_ts / 1000, tz=timezone.utc)
        else:
            # ISO-8601 string — handle with/without timezone
            ts_str = str(scan_ts)
            if ts_str.endswith('Z'):
                ts_str = ts_str[:-1] + '+00:00'
            scan_dt = datetime.fromisoformat(ts_str)
            if scan_dt.tzinfo is None:
                scan_dt = scan_dt.replace(tzinfo=timezone.utc)

        age = datetime.now(timezone.utc) - scan_dt
        return age.days <= age_days
    except (ValueError, TypeError, OSError) as e:
        logger.warning(f"Could not parse scan timestamp '{scan_ts}': {e}")
        return True  # Don't filter out on parse errors


def handle_query_vulnerabilities(params: Dict[str, Any], request_id: str) -> Dict[str, Any]:
    """Handle query_vulnerabilities requests via agentic search.

    Extracts query parameters, enhances the NL query with version/project
    context, executes agentic search through the configured pipeline, and
    post-processes results with severity/exclusion/age filtering.

    Args:
        params: Parameters dict containing:
            - query (str): Natural language query (required).
            - version (str, optional): Version to scope the query.
            - project_name (str, optional): Project name to scope the query.
            - severity (str, optional): Comma-separated severity levels.
            - age_days (str, optional): Max age in days for scan results.
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

    # Enhance the NL query with version/project context
    enhanced_query = enhance_query(query, version=version, project_name=project_name)
    logger.info(f"[{request_id}] Enhanced query: '{enhanced_query}'")

    # Execute agentic search
    try:
        response = agentic_search(config.agentic_pipeline, enhanced_query)
    except AgenticSearchError as e:
        logger.error(f"[{request_id}] SECURITY_ADVISORIES_AGENTIC_SEARCH_FAILED: {e}")
        return {
            'status': 'error',
            'type': 'agentic_search_error',
            'retryable': False,
            'message': (
                'The search agent could not process the query. '
                'Try rephrasing the question.'
            ),
        }

    # Extract hits
    hits = response.get('hits', {}).get('hits', [])

    if not hits:
        logger.info(f"[{request_id}] No hits returned from agentic search")
        return {
            'status': 'success',
            'message': 'No results found for the given query. Try broadening or rephrasing your search.',
            'results': [],
            'result_count': 0,
        }

    # Process each scan document hit
    results = []
    for hit in hits:
        source = hit.get('_source', {})
        project = source.get('project', {})
        raw_vulns = source.get('vulnerabilities', [])
        count = source.get('count', {})
        timestamp = source.get('timestamp', {})

        # Apply age threshold filter at the scan-document level
        if age_days is not None and not _is_within_age(timestamp, age_days):
            logger.info(
                f"[{request_id}] Skipping scan for {project.get('name')} "
                f"tag={project.get('tag')} — older than {age_days} days",
            )
            continue

        # Apply post-query filters (severity, exclusion)
        filtered_vulns = filter_vulnerabilities(raw_vulns, severity=severity)

        results.append({
            'project': project,
            'timestamp': timestamp,
            'total_count': count,
            'filtered_vulnerabilities': filtered_vulns,
            'filtered_count': len(filtered_vulns),
            'severity_summary': build_summary(filtered_vulns),
        })

    logger.info(f"[{request_id}] Returning {len(results)} result entries")

    return {
        'status': 'success',
        'result_count': len(results),
        'results': results,
    }
