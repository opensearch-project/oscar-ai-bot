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

# Active releases are few (usually one), but a version can be re-registered, so fetch
# enough documents to reduce to the newest registration per version.
ACTIVE_RELEASES_FETCH_SIZE = 100

# Unsuffixed and unwildcarded, matching the Jenkins libraries that own this data
# (opensearch-build-libraries: vars/buildRC.groovy, vars/checkIntegTestResultsOverview.groovy).
# Deliberately not the monthly -{month}-{year} pattern the other build queries use: this index
# is not month-partitioned, and an RC may predate the month being asked about.
BUILD_RESULTS_INDEX = 'opensearch-distribution-build-results'

# Release-state product name -> the component_category recorded in the build results index.
# The two distributions are built independently and reach different RC numbers, so both are
# reported rather than collapsed: OpenSearch on RC3 while Dashboards is still on RC1 is exactly
# the kind of gap a release manager needs to see.
RC_PRODUCTS = {
    'opensearch': 'OpenSearch',
    'opensearch-dashboards': 'OpenSearch Dashboards',
}

SCOPE_STATE = 'state'
SCOPE_SCHEDULE = 'schedule'

# Which criteria the verdict is judged against in each phase: entrance criteria gate the RC,
# exit criteria gate GA, so the verdict tracks whichever milestone is still ahead. A phase
# with no milestone ahead (shipped, cancelled, undated) is judged against everything, as is
# a version whose schedule cannot be read - guessing a scope there would quietly drop gates.
CRITERIA_FOCUS_BY_PHASE = {
    'out_of_window': release_rubric.ENTRANCE,
    'pre_rc_daily': release_rubric.ENTRANCE,
    'pre_rc_frequent': release_rubric.ENTRANCE,
    # The RC date came and went without an RC, so the RC is still the milestone ahead and
    # entrance criteria are still what gates it. Judging this against exit criteria would
    # report on a gate the release has not reached.
    'rc_overdue': release_rubric.ENTRANCE,
    'rc_to_release': release_rubric.EXIT,
    'final_push': release_rubric.EXIT,
    'overdue': release_rubric.EXIT,
    'released': None,
    'cancelled': None,
    'not_scheduled': None,
}


def _latest_rc_number(version: str, component_category: str, request_id: str) -> Optional[int]:
    """Highest RC number successfully built for one distribution of a version.

    Mirrors ReleaseCandidateStatus.getLatestRcNumberQuery in opensearch-build-libraries so
    that OSCAR and the Jenkins jobs read the same signal the same way: match_phrase rather
    than term (this index is dynamically mapped and every field here is analyzed text), the
    rc flag rather than rc_number to identify an RC build (every build document carries an
    rc_number, RC or not), and a SUCCESS filter because an RC that failed to build is not one
    the release has actually reached.

    Returns 0 when no RC has been built, or None when the query failed - the two must not be
    conflated, since "no RC yet" changes the release's phase and "we could not tell" must not.
    """
    query = {
        'size': 1,
        '_source': ['rc_number'],
        'sort': [
            {'distribution_build_number': {'order': 'desc'}},
            {'rc_number': {'order': 'desc'}},
        ],
        'query': {
            'bool': {
                'filter': [
                    {'match_phrase': {'component_category': component_category}},
                    {'match_phrase': {'rc': 'true'}},
                    {'match_phrase': {'version': version}},
                    {'match_phrase': {'overall_build_result': 'SUCCESS'}},
                ]
            }
        },
    }

    try:
        response = opensearch_request('GET', f'/{BUILD_RESULTS_INDEX}/_search', query)
    except Exception as e:
        logger.warning(
            f"RC_NUMBER_QUERY_FAILED [{request_id}]: {version} {component_category}: {e}"
        )
        return None

    hits = response.get('hits', {}).get('hits', [])
    if not hits:
        return 0

    raw = hits[0].get('_source', {}).get('rc_number')
    try:
        # Indexed as a string by the Jenkins side, so never compared without coercion.
        return int(raw)
    except (TypeError, ValueError):
        logger.warning(
            f"RC_NUMBER_UNPARSEABLE [{request_id}]: {version} {component_category}: {raw!r}"
        )
        return None


def _rc_numbers(version: str, request_id: str) -> Optional[Dict[str, int]]:
    """Latest successfully built RC number per distribution, or None if it cannot be read.

    All or nothing: a partial answer would let one failed query read as "Dashboards has no
    RC", which is the difference between two phases.
    """
    numbers: Dict[str, int] = {}
    for product, component_category in RC_PRODUCTS.items():
        rc_number = _latest_rc_number(version, component_category, request_id)
        if rc_number is None:
            return None
        numbers[product] = rc_number

    logger.info(f"RC_NUMBERS [{request_id}]: {version} -> {numbers}")
    return numbers


def _resolve_rc_state(
    days_to_rc: Optional[int],
    status: Optional[str],
    version: Optional[str],
    request_id: str,
) -> Dict[str, Any]:
    """Look up RC build state, but only when the answer can change the phase.

    Asked lazily so a normal run pays for nothing extra: before the RC date the countdown
    decides the phase, and a released or cancelled release is decided by its status, so in
    neither case does the build index tell us anything the schedule has not already said.

    Returns the keys to merge into the window response. rc_created is None when unknown.
    """
    if version is None or days_to_rc is None or days_to_rc >= 0:
        return {'rc_created': None}
    if (status or '').strip().lower() != 'active':
        return {'rc_created': None}

    numbers = _rc_numbers(version, request_id)
    if numbers is None:
        return {'rc_created': None}

    # Any RC counts as the release having entered its RC phase - the distributions are built
    # separately, and one of them having started is not "no RC yet".
    return {'rc_created': any(n > 0 for n in numbers.values()), 'rc_numbers': numbers}


def _require_version(params: Dict[str, Any]) -> Optional[str]:
    """Return the trimmed version string, or None when missing or blank."""
    version = params.get('version')
    if isinstance(version, str):
        version = version.strip()
    return version or None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _criteria_focus(version: str, request_id: str) -> Optional[str]:
    """Decide which criteria the verdict is judged against, from the release's phase.

    Read here rather than accepted as a parameter so that every caller gets the same
    verdict: an RM asking OSCAR and the scheduled notifier must never disagree about
    whether a release is a go, and only one of them knows the phase already.
    """
    window = handle_get_release_window({'version': version}, request_id)
    if window.get('error') or not window.get('found'):
        logger.warning(
            f"RELEASE_STATUS_SCOPE [{request_id}]: no schedule for {version}, "
            f"judging every criterion"
        )
        return None

    phase = window.get('cadence_phase') or 'not_scheduled'
    focus = CRITERIA_FOCUS_BY_PHASE.get(phase)
    logger.info(f"RELEASE_STATUS_SCOPE [{request_id}]: phase {phase} -> criteria {focus or 'all'}")
    return focus


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

    verdict = release_rubric.compute_verdict(criteria, focus=_criteria_focus(version, request_id))
    release_issue = next(
        (c.get('release_issue') for c in criteria if c.get('release_issue')), None
    )

    result = {
        'version': version,
        'found': True,
        'data_source': index,
        'verdict': verdict['verdict'],
        'criteria_scope': verdict['criteria_scope'],
        'blocking_failures': verdict['blocking_failures'],
        'blocking_in_progress': verdict['blocking_in_progress'],
        'blocking_unknowns': verdict['blocking_unknowns'],
        'non_blocking_gaps': verdict['non_blocking_gaps'],
        'not_applicable': verdict['not_applicable'],
        'out_of_scope': verdict['out_of_scope'],
        'counts': verdict['counts'],
        'criteria': verdict['criteria'],
    }
    if release_issue:
        result['release_issue'] = release_issue
    return result


def handle_list_active_releases(params: Dict[str, Any], request_id: str = 'unknown') -> Dict[str, Any]:
    """List every release whose schedule status is active, soonest release date first.

    A fixed projection, so it uses its own DSL rather than the agentic pipeline. The
    release notifier depends on it to decide which versions to report on.
    """
    index = config.release_schedule_index
    query = {
        'size': ACTIVE_RELEASES_FETCH_SIZE,
        'query': {'bool': {'filter': [{'term': {'status.keyword': 'active'}}]}},
        'sort': [{'release_date': {'order': 'asc', 'unmapped_type': 'date'}}],
    }

    try:
        response = opensearch_request('GET', f'/{index}/_search', query)
    except Exception as e:
        logger.error(f"RELEASE_SCHEDULE_QUERY_FAILED [{request_id}]: {e}")
        return {'error': f'Failed to query release schedule: {e}', 'type': 'query_error'}

    latest_by_version: Dict[str, Dict[str, Any]] = {}
    for hit in response.get('hits', {}).get('hits', []):
        source = hit.get('_source', {})
        version = source.get('version')
        if not version:
            continue
        existing = latest_by_version.get(version)
        if existing is None:
            latest_by_version[version] = source
            continue
        candidate = parse_timestamp(source.get('registered_at'))
        current = parse_timestamp(existing.get('registered_at'))
        if candidate and (current is None or candidate > current):
            latest_by_version[version] = source

    releases = []
    today = _now().date()
    for source in latest_by_version.values():
        rc_date = parse_timestamp(source.get('rc_date'))
        release_date = parse_timestamp(source.get('release_date'))
        days_to_rc = (rc_date.date() - today).days if rc_date else None
        days_to_release = (release_date.date() - today).days if release_date else None
        rc_state = _resolve_rc_state(
            days_to_rc, source.get('status'), source.get('version'), request_id
        )
        releases.append({
            'version': source.get('version'),
            'rc_date': source.get('rc_date'),
            'release_date': source.get('release_date'),
            'days_to_rc': days_to_rc,
            'days_to_release': days_to_release,
            'cadence_phase': _cadence_phase(
                days_to_rc, days_to_release, source.get('status'), rc_state['rc_created']
            ),
            'release_manager': source.get('release_manager'),
            'release_issue': source.get('release_issue'),
            **rc_state,
        })

    releases.sort(key=lambda r: (r['days_to_release'] is None, r['days_to_release']))
    logger.info(f"ACTIVE_RELEASES [{request_id}]: {[r['version'] for r in releases]}")

    return {
        'data_source': index,
        'total_results': len(releases),
        'releases': releases,
    }


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
    rc_state = _resolve_rc_state(days_to_rc, source.get('status'), version, request_id)

    return {
        'version': version,
        'found': True,
        'data_source': index,
        'status': source.get('status'),
        'rc_date': source.get('rc_date'),
        'release_date': source.get('release_date'),
        'days_to_rc': days_to_rc,
        'days_to_release': days_to_release,
        'cadence_phase': _cadence_phase(
            days_to_rc, days_to_release, source.get('status'), rc_state['rc_created']
        ),
        'release_manager': source.get('release_manager'),
        'release_issue': source.get('release_issue'),
        **rc_state,
    }


def _cadence_phase(
    days_to_rc: Optional[int],
    days_to_release: Optional[int],
    status: Optional[str] = None,
    rc_created: Optional[bool] = None,
) -> str:
    """Classify the schedule phase from the release status and its dates.

    The schedule status wins wherever it disagrees with the dates: dates alone cannot tell
    a shipped release from a cancelled or a late one, so inferring the lifecycle from them
    would contradict the status field reported alongside this phase.

    Once the RC date has passed, the dates cannot tell whether the RC was actually created
    either - the schedule records the planned date and stays active either way - so
    rc_created carries that answer from the build results index. It is deliberately a
    parameter rather than a lookup: this function stays pure, and the caller decides whether
    the question is worth a query. None means unknown, and preserves the date-derived phase
    rather than guessing.

    Phases follow the escalating notification cadence in the proposal:
      cancelled:        schedule status is cancelled, whatever the dates say
      released:         schedule status is released, or the date passed with no status
      overdue:          still active but the release date has passed
      out_of_window:    more than 14 days before RC
      pre_rc_daily:     14 to 8 days before RC
      pre_rc_frequent:  7 to 0 days before RC
      rc_overdue:       RC date has passed with no RC created
      rc_to_release:    RC created, more than 2 days before release
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
        if rc_created is False:
            # The RC date slipped. Reported as its own phase rather than as rc_to_release,
            # which would claim a milestone the release has not reached and judge it against
            # exit criteria while the entrance gate is still what stands in the way.
            return 'rc_overdue'
        if days_to_release is None:
            # An RC exists but no release date is registered: still post-RC, not unscheduled.
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
