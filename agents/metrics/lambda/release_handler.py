#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.

"""
Release-readiness Handlers for the Metrics Lambda.

Three read-only handlers over the release indices on the metrics cluster:

    handle_get_release_status:  fixed DSL + rubric -> authoritative R/Y/G verdict
    handle_get_release_window:  fixed DSL -> schedule dates, days remaining, phase
    handle_query_release_state: agentic search -> free-form questions about release state

The first two build their own term-filter DSL rather than going through the agentic
pipeline. The rubric decides the verdict by checking whether every blocking criterion is
satisfied, so its answer is only correct if it sees ALL criteria: a planner that narrows
the result set (an extra status filter, a missing sort, a smaller size) would yield a
confident but wrong verdict. These two queries are also fixed projections with no natural
language to interpret, and the Phase 3 notifier runs them on a schedule.

Free-form questions have no such completeness requirement, so they route through the
release flow agent.

Every exact filter targets a .keyword sub-field: both release indices are dynamically
mapped, so fields such as product are analyzed text and a term query on the bare field
misses hyphenated values like opensearch-dashboards.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import release_rubric
from agentic_search import AgenticSearchError, agentic_search
from aws_utils import opensearch_request
from config import config
from data_processors import extract_release_state_results, parse_timestamp

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Upper bound on history documents pulled before reduction. A release has at most 13
# criteria across 2 products, but the index holds one document per criterion per check run
# (roughly 6-hourly), so the window must be wide enough that the newest document for every
# criterion falls inside it.
RELEASE_STATE_FETCH_SIZE = 1000

SCOPE_STATE = 'state'
SCOPE_SCHEDULE = 'schedule'


def _require_version(params: Dict[str, Any]) -> Optional[str]:
    """Return the trimmed version string, or None when missing or blank."""
    version = params.get('version')
    if isinstance(version, str):
        version = version.strip()
    return version or None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def handle_get_release_status(params: Dict[str, Any], request_id: str = 'unknown') -> Dict[str, Any]:
    """Fetch current per-criterion state for a version and compute the R/Y/G verdict."""
    version = _require_version(params)
    if not version:
        return {'error': "A version is required, e.g. '3.9.0'."}

    index = config.release_state_index
    query = {
        'size': RELEASE_STATE_FETCH_SIZE,
        'query': {
            'bool': {
                'filter': [
                    {'term': {'version.keyword': version}},
                    {'term': {'doc_type.keyword': 'criterion'}},
                ]
            }
        },
        'sort': [{'last_checked': {'order': 'desc'}}],
    }

    try:
        response = opensearch_request('GET', f'/{index}/_search', query)
    except Exception as e:
        logger.error(f"RELEASE_STATE_QUERY_FAILED [{request_id}]: {e}")
        return {'error': f'Failed to query release state: {e}', 'type': 'query_error'}

    criteria = extract_release_state_results(response)
    if not criteria:
        return {
            'version': version,
            'found': False,
            'data_source': index,
            'message': (
                f'No indexed release state found for {version}. It may not be an active '
                f'release yet, or state has not been indexed.'
            ),
        }

    total_hits = response.get('hits', {}).get('total', {}).get('value')
    logger.info(
        f"RELEASE_STATUS [{request_id}]: reduced {total_hits} history documents to "
        f"{len(criteria)} current criteria for {version}"
    )

    verdict = release_rubric.compute_verdict(criteria)
    release_issue = next(
        (c.get('release_issue') for c in criteria if c.get('release_issue')), None
    )

    result = {
        'version': version,
        'found': True,
        'data_source': index,
        'verdict': verdict['verdict'],
        'blocking_failures': verdict['blocking_failures'],
        'blocking_in_progress': verdict['blocking_in_progress'],
        'blocking_unknowns': verdict['blocking_unknowns'],
        'non_blocking_gaps': verdict['non_blocking_gaps'],
        'not_applicable': verdict['not_applicable'],
        'counts': verdict['counts'],
        'criteria': verdict['criteria'],
    }
    if release_issue:
        result['release_issue'] = release_issue
    return result


def handle_get_release_window(params: Dict[str, Any], request_id: str = 'unknown') -> Dict[str, Any]:
    """Fetch the schedule for a version and compute days remaining and cadence phase."""
    version = _require_version(params)
    if not version:
        return {'error': "A version is required, e.g. '3.9.0'."}

    index = config.release_schedule_index
    query = {
        'size': 1,
        'query': {'bool': {'filter': [{'term': {'version.keyword': version}}]}},
        'sort': [{'registered_at': {'order': 'desc', 'unmapped_type': 'date'}}],
    }

    try:
        response = opensearch_request('GET', f'/{index}/_search', query)
    except Exception as e:
        logger.error(f"RELEASE_SCHEDULE_QUERY_FAILED [{request_id}]: {e}")
        return {'error': f'Failed to query release schedule: {e}', 'type': 'query_error'}

    hits = response.get('hits', {}).get('hits', [])
    if not hits:
        return {
            'version': version,
            'found': False,
            'data_source': index,
            'message': (
                f'No release schedule found for {version}. It may not have been '
                f'registered yet.'
            ),
        }

    source = hits[0].get('_source', {})
    rc_date = parse_timestamp(source.get('rc_date'))
    release_date = parse_timestamp(source.get('release_date'))
    today = _now().date()

    days_to_rc = (rc_date.date() - today).days if rc_date else None
    days_to_release = (release_date.date() - today).days if release_date else None

    return {
        'version': version,
        'found': True,
        'data_source': index,
        'status': source.get('status'),
        'rc_date': source.get('rc_date'),
        'release_date': source.get('release_date'),
        'days_to_rc': days_to_rc,
        'days_to_release': days_to_release,
        'cadence_phase': _cadence_phase(days_to_rc, days_to_release, source.get('status')),
        'release_manager': source.get('release_manager'),
        'release_issue': source.get('release_issue'),
    }


def _cadence_phase(
    days_to_rc: Optional[int],
    days_to_release: Optional[int],
    status: Optional[str] = None,
) -> str:
    """Classify the schedule phase from the release status and its dates.

    The schedule status wins wherever it disagrees with the dates: dates alone cannot tell
    a shipped release from a cancelled or a late one, so inferring the lifecycle from them
    would contradict the status field reported alongside this phase.

    Phases follow the escalating notification cadence in the proposal:
      cancelled:        schedule status is cancelled, whatever the dates say
      released:         schedule status is released, or the date passed with no status
      overdue:          still active but the release date has passed
      out_of_window:    more than 14 days before RC
      pre_rc_daily:     14 to 8 days before RC
      pre_rc_frequent:  7 to 0 days before RC
      rc_to_release:    RC cut, more than 2 days before release
      final_push:       final 2 days before release
      not_scheduled:    no usable dates
    """
    lifecycle = (status or '').strip().lower()
    if lifecycle == 'cancelled':
        return 'cancelled'
    if lifecycle == 'released':
        return 'released'

    if days_to_release is not None and days_to_release < 0:
        return 'overdue' if lifecycle == 'active' else 'released'

    if days_to_rc is not None:
        if days_to_rc > 14:
            return 'out_of_window'
        if 8 <= days_to_rc <= 14:
            return 'pre_rc_daily'
        if 0 <= days_to_rc <= 7:
            return 'pre_rc_frequent'
        if days_to_release is None:
            # RC is cut but no release date is registered: still post-RC, not unscheduled.
            return 'rc_to_release'

    if days_to_release is not None:
        if days_to_release <= 2:
            return 'final_push'
        return 'rc_to_release'

    return 'not_scheduled'


def enhance_release_query(query: str, version: Optional[str] = None) -> str:
    """Append release-specific context to a natural language query.

    Deliberately not enhance_query from agentic_search: that one appends a monthly index
    date suffix for the build and test indices, which is meaningless for the two static
    release indices.
    """
    parts = [query]
    if version:
        parts.append(f'for version {version}')
    enhanced = ' '.join(parts)
    logger.info(f"ENHANCE_RELEASE_QUERY: '{query}' -> '{enhanced}'")
    return enhanced


def handle_query_release_state(params: Dict[str, Any], request_id: str = 'unknown') -> Dict[str, Any]:
    """Answer a free-form release question through the release flow agent.

    A flow agent cannot choose an index, so scope selects one and it goes in the request
    path - that is also how the query planner receives a mapping. No memory_id is passed:
    a flow agent has no memory, unlike the conversational agent behind query_metrics.
    """
    query = params.get('query')
    if not query:
        return {'error': 'A query is required for release state questions'}

    version = _require_version(params)
    scope = (params.get('scope') or SCOPE_STATE).strip().lower()
    if scope not in (SCOPE_STATE, SCOPE_SCHEDULE):
        return {'error': f"Unknown scope '{scope}'. Use '{SCOPE_STATE}' or '{SCOPE_SCHEDULE}'."}

    index = (
        config.release_schedule_index if scope == SCOPE_SCHEDULE
        else config.release_state_index
    )
    enhanced_query = enhance_release_query(query, version)
    logger.info(f"RELEASE_QUERY [{request_id}]: scope={scope}, index={index}")

    try:
        response = agentic_search(config.release_agentic_pipeline, enhanced_query, index=index)
    except AgenticSearchError as e:
        logger.error(f"AGENTIC_SEARCH_FAILED [{request_id}]: {e}")
        return {
            'error': str(e),
            'status_code': e.status_code,
            'type': 'agentic_search_error',
            'retryable': False,
            'message': (
                'The search agent could not generate a valid query. Try rephrasing or '
                'simplifying the question. Do not retry this exact query.'
            ),
        }

    if 'hits' not in response:
        logger.error(f"RELEASE_QUERY [{request_id}]: unexpected response structure")
        return {'error': 'Unexpected response structure', 'type': 'response_parse_error'}

    generated_dsl = response.get('ext', {}).get('dsl_query')
    if generated_dsl:
        logger.info(f"RELEASE_QUERY [{request_id}]: Generated DSL: {generated_dsl}")

    if scope == SCOPE_STATE:
        results = extract_release_state_results(response)
    else:
        results = [hit.get('_source', {}) for hit in response.get('hits', {}).get('hits', [])]

    result = {
        'scope': scope,
        'data_source': index,
        'total_results': len(results),
        'results': results,
    }
    if version:
        result['version'] = version
    if generated_dsl:
        result['generated_dsl'] = generated_dsl
    return result
