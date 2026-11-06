# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the release-readiness handlers in the metrics Lambda.

Covers: the deterministic DSL shape of get_release_status and get_release_window
(.keyword filters, sort, size), history reduction to newest-per-criterion, verdict
integration, window date math and cadence phases, and the agentic query_release_state
path (index in the request path, no memory_id, scope routing, error surfaces).
"""

import importlib.util
import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

_LAMBDA_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'agents', 'metrics', 'lambda',
)


def _load_module(name, mocks):
    if _LAMBDA_PATH not in sys.path:
        sys.path.insert(0, _LAMBDA_PATH)
    with patch.dict('sys.modules', mocks):
        spec = importlib.util.spec_from_file_location(
            name, os.path.join(_LAMBDA_PATH, f'{name}.py'),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod


def _load_handler(opensearch_response=None, opensearch_error=None,
                  agentic_response=None, agentic_error=None):
    """Import release_handler with mocked aws_utils, config, and agentic_search."""
    mock_aws_utils = MagicMock()
    if opensearch_error:
        mock_aws_utils.opensearch_request.side_effect = opensearch_error
    else:
        mock_aws_utils.opensearch_request.return_value = (
            opensearch_response or {'hits': {'total': {'value': 0}, 'hits': []}}
        )

    mock_config_module = MagicMock()
    mock_config_module.config.release_state_index = 'opensearch_release_state'
    mock_config_module.config.release_schedule_index = 'opensearch_release_schedule'
    mock_config_module.config.release_agentic_pipeline = 'release-flow-agentic-pipeline'

    class _AgenticSearchError(Exception):
        def __init__(self, message, status_code=None):
            super().__init__(message)
            self.status_code = status_code

    mock_agentic = MagicMock()
    mock_agentic.AgenticSearchError = _AgenticSearchError
    if agentic_error:
        mock_agentic.agentic_search.side_effect = agentic_error
    else:
        mock_agentic.agentic_search.return_value = (
            agentic_response or {'hits': {'total': {'value': 0}, 'hits': []}, 'ext': {}}
        )

    # Real reducer and rubric: their behavior is part of what these tests verify.
    data_processors = _load_module('data_processors', {})
    release_rubric = _load_module('release_rubric', {})

    handler = _load_module('release_handler', {
        'aws_utils': mock_aws_utils,
        'config': mock_config_module,
        'agentic_search': mock_agentic,
        'data_processors': data_processors,
        'release_rubric': release_rubric,
    })
    return handler, mock_aws_utils, mock_agentic


def _state_hit(criterion_name, status, last_checked, product='both', **extra):
    return {'_source': {
        'doc_type': 'criterion',
        'version': '3.9.0',
        'criterion_name': criterion_name,
        'status': status,
        'product': product,
        'last_checked': last_checked,
        **extra,
    }}


class TestGetReleaseStatusQueryShape:

    def test_query_uses_keyword_filters_sort_and_size(self):
        handler, mock_aws, _ = _load_handler()
        handler.handle_get_release_status({'version': '3.9.0'})

        method, path, query = mock_aws.opensearch_request.call_args[0]
        assert method == 'GET'
        assert path == '/opensearch_release_state/_search'
        assert query['size'] == handler.RELEASE_STATE_FETCH_SIZE
        assert {'term': {'version.keyword': '3.9.0'}} in query['query']['bool']['filter']
        assert {'term': {'doc_type.keyword': 'criterion'}} in query['query']['bool']['filter']
        assert query['sort'] == [{'last_checked': {'order': 'desc'}}]

    def test_version_required(self):
        handler, mock_aws, _ = _load_handler()
        assert 'error' in handler.handle_get_release_status({})
        assert 'error' in handler.handle_get_release_status({'version': '  '})
        mock_aws.opensearch_request.assert_not_called()

    def test_query_failure_surfaces_error(self):
        handler, _, _ = _load_handler(opensearch_error=Exception('boom'))
        result = handler.handle_get_release_status({'version': '3.9.0'})
        assert result['type'] == 'query_error'

    def test_no_hits_reports_not_found(self):
        handler, _, _ = _load_handler()
        result = handler.handle_get_release_status({'version': '9.9.9'})
        assert result['found'] is False


class TestGetReleaseStatusReduction:

    def test_history_reduced_to_newest_per_criterion(self):
        # Three runs of the same criterion: only the newest counts, and it is met,
        # so the stale not_met copies must not turn the verdict red.
        response = {'hits': {'total': {'value': 3}, 'hits': [
            _state_hit('release_notes_ready', 'met', '2026-09-01T18:30:00Z'),
            _state_hit('release_notes_ready', 'not_met', '2026-09-01T12:30:00Z'),
            _state_hit('release_notes_ready', 'not_met', '2026-09-01T06:30:00Z'),
        ]}}
        handler, _, _ = _load_handler(opensearch_response=response)
        result = handler.handle_get_release_status({'version': '3.9.0'})
        assert result['found'] is True
        assert result['counts']['total'] == 1
        assert result['verdict'] == 'green'

    def test_per_product_criteria_kept_separately(self):
        response = {'hits': {'total': {'value': 2}, 'hits': [
            _state_hit('all_integration_tests_passing', 'met',
                       '2026-09-01T18:30:00Z', product='opensearch'),
            _state_hit('all_integration_tests_passing', 'not_met',
                       '2026-09-01T18:30:00Z', product='opensearch-dashboards'),
        ]}}
        handler, _, _ = _load_handler(opensearch_response=response)
        result = handler.handle_get_release_status({'version': '3.9.0'})
        assert result['counts']['total'] == 2
        assert result['verdict'] == 'red'
        assert result['blocking_failures'] == ['all_integration_tests_passing']

    def test_newest_wins_across_mixed_timestamp_formats(self):
        # Same instant written as 'Z' and '+00:00', plus differing fractional precision:
        # comparing the raw strings would order these wrongly and pick a stale status.
        response = {'hits': {'total': {'value': 3}, 'hits': [
            _state_hit('release_notes_ready', 'not_met', '2026-09-01T06:30:00+00:00'),
            _state_hit('release_notes_ready', 'met', '2026-09-01T18:30:00.123Z'),
            _state_hit('release_notes_ready', 'not_met', '2026-09-01T12:30:00Z'),
        ]}}
        handler, _, _ = _load_handler(opensearch_response=response)
        result = handler.handle_get_release_status({'version': '3.9.0'})
        assert result['counts']['total'] == 1
        assert result['verdict'] == 'green'

    def test_unparseable_timestamp_does_not_displace_a_valid_one(self):
        response = {'hits': {'total': {'value': 2}, 'hits': [
            _state_hit('release_notes_ready', 'met', '2026-09-01T18:30:00Z'),
            _state_hit('release_notes_ready', 'not_met', 'not-a-timestamp'),
        ]}}
        handler, _, _ = _load_handler(opensearch_response=response)
        result = handler.handle_get_release_status({'version': '3.9.0'})
        assert result['verdict'] == 'green'

    def test_release_issue_surfaced(self):
        response = {'hits': {'total': {'value': 1}, 'hits': [
            _state_hit('release_notes_ready', 'met', '2026-09-01T18:30:00Z',
                       release_issue='https://github.com/opensearch-project/opensearch-build/issues/6426'),
        ]}}
        handler, _, _ = _load_handler(opensearch_response=response)
        result = handler.handle_get_release_status({'version': '3.9.0'})
        assert result['release_issue'].endswith('/6426')


class TestGetReleaseWindow:

    @staticmethod
    def _schedule_response(**overrides):
        source = {
            'version': '3.9.0',
            'rc_date': '2026-09-15',
            'release_date': '2026-09-29',
            'release_manager': ['Foo Bar'],
            'release_manager_gh_handle': ['foo'],
            'release_issue': 'https://github.com/opensearch-project/opensearch-build/issues/6426',
            'status': 'active',
        }
        source.update(overrides)
        return {'hits': {'total': {'value': 1}, 'hits': [{'_source': source}]}}

    def test_query_shape(self):
        handler, mock_aws, _ = _load_handler(opensearch_response=self._schedule_response())
        # Pinned, and asserting on the FIRST call: with an unpinned clock the rc_date is in
        # the past, which fires the RC build lookup and makes call_args the wrong query.
        fake_now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
        with patch.object(handler, '_now', return_value=fake_now):
            handler.handle_get_release_window({'version': '3.9.0'})

        _, path, query = mock_aws.opensearch_request.call_args_list[0][0]
        assert path == '/opensearch_release_schedule/_search'
        assert query['size'] == 1
        assert {'term': {'version.keyword': '3.9.0'}} in query['query']['bool']['filter']
        # unmapped_type keeps the sort from erroring on a schedule index that has no
        # registered_at mapping yet, e.g. a freshly created environment.
        assert query['sort'] == [
            {'registered_at': {'order': 'desc', 'unmapped_type': 'date'}}
        ]

    def test_days_remaining_computed_from_today(self):
        handler, _, _ = _load_handler(opensearch_response=self._schedule_response())
        fake_now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
        with patch.object(handler, '_now', return_value=fake_now):
            result = handler.handle_get_release_window({'version': '3.9.0'})
        assert result['days_to_rc'] == 14
        assert result['days_to_release'] == 28
        assert result['cadence_phase'] == 'pre_rc_daily'

    def test_missing_dates_yield_not_scheduled(self):
        handler, _, _ = _load_handler(
            opensearch_response=self._schedule_response(rc_date=None, release_date=None))
        result = handler.handle_get_release_window({'version': '3.9.0'})
        assert result['days_to_rc'] is None
        assert result['days_to_release'] is None
        assert result['cadence_phase'] == 'not_scheduled'

    def test_not_registered(self):
        handler, _, _ = _load_handler()
        result = handler.handle_get_release_window({'version': '9.9.9'})
        assert result['found'] is False

    def test_manager_name_and_handle_are_both_returned(self):
        """The notifier needs the handle to tag the manager and the name to fall back on."""
        handler, _, _ = _load_handler(opensearch_response=self._schedule_response())
        result = handler.handle_get_release_window({'version': '3.9.0'})
        assert result['release_manager'] == ['Foo Bar']
        assert result['release_manager_gh_handle'] == ['foo']

    def test_every_manager_of_a_co_managed_release_is_returned(self):
        """A release can be co-managed, and both managers have to be reachable - returning one
        handle would leave the other silently untagged in the notification."""
        handler, _, _ = _load_handler(opensearch_response=self._schedule_response(
            release_manager=['Foo Bar', 'Baz Qux'],
            release_manager_gh_handle=['foo', 'baz'],
        ))
        result = handler.handle_get_release_window({'version': '3.9.0'})
        assert result['release_manager'] == ['Foo Bar', 'Baz Qux']
        assert result['release_manager_gh_handle'] == ['foo', 'baz']

    def test_a_schedule_doc_without_a_handle_still_returns_the_name(self):
        """Docs indexed before the handle was scraped must not break the window response."""
        handler, _, _ = _load_handler(
            opensearch_response=self._schedule_response(release_manager_gh_handle=None))
        result = handler.handle_get_release_window({'version': '3.9.0'})
        assert result['release_manager'] == ['Foo Bar']
        assert result['release_manager_gh_handle'] is None


class TestListActiveReleases:

    @staticmethod
    def _schedule_hit(version, release_date, rc_date, registered_at, status='active'):
        return {'_source': {
            'version': version,
            'status': status,
            'rc_date': rc_date,
            'release_date': release_date,
            'registered_at': registered_at,
            'release_manager': ['Foo Bar'],
            'release_manager_gh_handle': ['foo'],
        }}

    def test_query_filters_on_active_status(self):
        handler, mock_aws, _ = _load_handler()
        handler.handle_list_active_releases({})

        _, path, query = mock_aws.opensearch_request.call_args[0]
        assert path == '/opensearch_release_schedule/_search'
        assert {'term': {'status.keyword': 'active'}} in query['query']['bool']['filter']
        assert query['sort'] == [{'release_date': {'order': 'asc', 'unmapped_type': 'date'}}]

    def test_manager_name_and_handle_are_both_listed(self):
        """The notifier tags from the handle, so listing it is what makes the mention possible."""
        response = {'hits': {'hits': [
            self._schedule_hit('3.9.0', '2026-09-29', '2026-09-15', '2026-08-01T00:00:00Z'),
        ]}}
        handler, _, _ = _load_handler(opensearch_response=response)
        release = handler.handle_list_active_releases({})['releases'][0]
        assert release['release_manager'] == ['Foo Bar']
        assert release['release_manager_gh_handle'] == ['foo']

    def test_every_manager_of_a_co_managed_release_is_listed(self):
        hit = self._schedule_hit('3.9.0', '2026-09-29', '2026-09-15', '2026-08-01T00:00:00Z')
        hit['_source']['release_manager'] = ['Foo Bar', 'Baz Qux']
        hit['_source']['release_manager_gh_handle'] = ['foo', 'baz']
        handler, _, _ = _load_handler(opensearch_response={'hits': {'hits': [hit]}})
        release = handler.handle_list_active_releases({})['releases'][0]
        assert release['release_manager'] == ['Foo Bar', 'Baz Qux']
        assert release['release_manager_gh_handle'] == ['foo', 'baz']

    def test_returns_soonest_release_first(self):
        response = {'hits': {'hits': [
            self._schedule_hit('4.0.0', '2026-12-01', '2026-11-15', '2026-08-01T00:00:00Z'),
            self._schedule_hit('3.9.0', '2026-09-29', '2026-09-15', '2026-08-01T00:00:00Z'),
        ]}}
        handler, _, _ = _load_handler(opensearch_response=response)
        result = handler.handle_list_active_releases({})
        assert [r['version'] for r in result['releases']] == ['3.9.0', '4.0.0']
        assert result['total_results'] == 2

    def test_reduces_reregistered_versions_to_newest(self):
        response = {'hits': {'hits': [
            self._schedule_hit('3.9.0', '2026-09-29', '2026-09-15', '2026-08-01T00:00:00Z'),
            self._schedule_hit('3.9.0', '2026-10-06', '2026-09-22', '2026-09-05T00:00:00Z'),
        ]}}
        handler, _, _ = _load_handler(opensearch_response=response)
        result = handler.handle_list_active_releases({})
        assert result['total_results'] == 1
        assert result['releases'][0]['release_date'] == '2026-10-06'

    def test_days_and_phase_computed(self):
        response = {'hits': {'hits': [
            self._schedule_hit('3.9.0', '2026-09-29', '2026-09-15', '2026-08-01T00:00:00Z'),
        ]}}
        handler, _, _ = _load_handler(opensearch_response=response)
        fake_now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
        with patch.object(handler, '_now', return_value=fake_now):
            release = handler.handle_list_active_releases({})['releases'][0]
        assert release['days_to_rc'] == 14
        assert release['days_to_release'] == 28
        assert release['cadence_phase'] == 'pre_rc_daily'

    def test_no_active_releases(self):
        handler, _, _ = _load_handler()
        result = handler.handle_list_active_releases({})
        assert result['total_results'] == 0
        assert result['releases'] == []

    def test_releases_without_dates_sort_last(self):
        response = {'hits': {'hits': [
            self._schedule_hit('4.0.0', None, None, '2026-08-01T00:00:00Z'),
            self._schedule_hit('3.9.0', '2026-09-29', '2026-09-15', '2026-08-01T00:00:00Z'),
        ]}}
        handler, _, _ = _load_handler(opensearch_response=response)
        result = handler.handle_list_active_releases({})
        assert [r['version'] for r in result['releases']] == ['3.9.0', '4.0.0']

    def test_query_failure_surfaces_error(self):
        handler, _, _ = _load_handler(opensearch_error=Exception('boom'))
        assert handler.handle_list_active_releases({})['type'] == 'query_error'


class TestCadencePhase:

    def test_phases(self):
        handler, _, _ = _load_handler()
        phase = handler._cadence_phase
        assert phase(20, 34) == 'out_of_window'
        assert phase(14, 28) == 'pre_rc_daily'
        assert phase(8, 22) == 'pre_rc_daily'
        assert phase(7, 21) == 'pre_rc_frequent'
        assert phase(0, 14) == 'pre_rc_frequent'
        assert phase(-1, 13) == 'rc_to_release'
        assert phase(-12, 2) == 'final_push'
        assert phase(-15, -1) == 'released'
        assert phase(None, None) == 'not_scheduled'

    def test_cancelled_status_wins_over_a_passed_release_date(self):
        # Dates cannot distinguish shipped from cancelled, so the phase must not
        # contradict the status field reported beside it.
        handler, _, _ = _load_handler()
        assert handler._cadence_phase(-30, -5, 'cancelled') == 'cancelled'
        assert handler._cadence_phase(10, 20, 'cancelled') == 'cancelled'

    def test_released_status_wins_over_future_dates(self):
        handler, _, _ = _load_handler()
        assert handler._cadence_phase(10, 20, 'released') == 'released'

    def test_active_release_past_its_date_is_overdue_not_released(self):
        handler, _, _ = _load_handler()
        assert handler._cadence_phase(-20, -3, 'active') == 'overdue'

    def test_passed_date_without_status_still_reads_as_released(self):
        handler, _, _ = _load_handler()
        assert handler._cadence_phase(-20, -3) == 'released'

    def test_status_is_case_and_whitespace_insensitive(self):
        handler, _, _ = _load_handler()
        assert handler._cadence_phase(-30, -5, ' Cancelled ') == 'cancelled'

    def test_window_phase_reflects_schedule_status(self):
        response = {'hits': {'total': {'value': 1}, 'hits': [{'_source': {
            'version': '3.7.0',
            'status': 'cancelled',
            'rc_date': '2026-06-01',
            'release_date': '2026-06-15',
        }}]}}
        handler, _, _ = _load_handler(opensearch_response=response)
        result = handler.handle_get_release_window({'version': '3.7.0'})
        assert result['status'] == 'cancelled'
        assert result['cadence_phase'] == 'cancelled'

    def test_rc_created_without_a_release_date_is_post_rc(self):
        # RC has passed and no release date is registered: post-RC, not unscheduled.
        handler, _, _ = _load_handler()
        assert handler._cadence_phase(-3, None) == 'rc_to_release'

    def test_only_a_release_date_still_classifies(self):
        handler, _, _ = _load_handler()
        assert handler._cadence_phase(None, 10) == 'rc_to_release'
        assert handler._cadence_phase(None, 1) == 'final_push'

    def test_a_passed_rc_date_with_no_rc_created_is_not_post_rc(self):
        # The reported bug: the date passing was taken as the RC having happened.
        handler, _, _ = _load_handler()
        assert handler._cadence_phase(-5, 13, 'active', rc_created=False) == 'rc_overdue'

    def test_a_created_rc_is_post_rc(self):
        handler, _, _ = _load_handler()
        assert handler._cadence_phase(-5, 13, 'active', rc_created=True) == 'rc_to_release'

    def test_unknown_rc_state_keeps_the_date_derived_phase(self):
        # A failed lookup must not reclassify every in-flight release.
        handler, _, _ = _load_handler()
        assert handler._cadence_phase(-5, 13, 'active', rc_created=None) == 'rc_to_release'

    def test_rc_state_does_not_override_the_lifecycle(self):
        handler, _, _ = _load_handler()
        assert handler._cadence_phase(-5, 13, 'cancelled', rc_created=False) == 'cancelled'
        assert handler._cadence_phase(-5, 13, 'released', rc_created=False) == 'released'

    def test_rc_state_does_not_override_an_overdue_release(self):
        # Past its release date matters more than which gate it never reached.
        handler, _, _ = _load_handler()
        assert handler._cadence_phase(-20, -3, 'active', rc_created=False) == 'overdue'

    def test_a_missing_rc_before_its_date_is_not_overdue(self):
        # Before the rc_date there is nothing late about not having an RC.
        handler, _, _ = _load_handler()
        assert handler._cadence_phase(5, 19, 'active', rc_created=False) == 'pre_rc_frequent'
        assert handler._cadence_phase(10, 24, 'active', rc_created=False) == 'pre_rc_daily'


class TestQueryReleaseState:

    def test_state_scope_passes_index_and_no_memory_id(self):
        handler, _, mock_agentic = _load_handler()
        handler.handle_query_release_state({'query': 'what is blocking', 'version': '3.9.0'})

        args, kwargs = mock_agentic.agentic_search.call_args
        assert args[0] == 'release-flow-agentic-pipeline'
        assert 'for version 3.9.0' in args[1]
        assert kwargs == {'index': 'opensearch_release_state'}

    def test_schedule_scope_targets_schedule_index(self):
        handler, _, mock_agentic = _load_handler()
        handler.handle_query_release_state({'query': 'which releases are active', 'scope': 'schedule'})
        assert mock_agentic.agentic_search.call_args.kwargs['index'] == 'opensearch_release_schedule'

    def test_invalid_scope_rejected(self):
        handler, _, mock_agentic = _load_handler()
        result = handler.handle_query_release_state({'query': 'q', 'scope': 'everything'})
        assert 'error' in result
        mock_agentic.agentic_search.assert_not_called()

    def test_query_required(self):
        handler, _, _ = _load_handler()
        assert 'error' in handler.handle_query_release_state({})

    def test_state_results_are_deduplicated(self):
        response = {'hits': {'total': {'value': 2}, 'hits': [
            _state_hit('release_notes_ready', 'met', '2026-09-01T18:30:00Z'),
            _state_hit('release_notes_ready', 'not_met', '2026-09-01T06:30:00Z'),
        ]}, 'ext': {'dsl_query': '{"size":1000}'}}
        handler, _, _ = _load_handler(agentic_response=response)
        result = handler.handle_query_release_state({'query': 'status of release notes'})
        assert result['total_results'] == 1
        assert result['results'][0]['status'] == 'met'
        assert result['generated_dsl'] == '{"size":1000}'

    def test_agentic_error_is_not_retryable(self):
        handler, _, mock_agentic = _load_handler()
        mock_agentic.agentic_search.side_effect = mock_agentic.AgenticSearchError('bad plan', status_code=400)
        result = handler.handle_query_release_state({'query': 'q'})
        assert result['type'] == 'agentic_search_error'
        assert result['retryable'] is False
        assert result['status_code'] == 400


class TestCriteriaScoping:
    """get_release_status judges only the criteria that gate the milestone still ahead.

    The scope is decided here rather than by the caller so an RM asking OSCAR and the
    scheduled notifier can never disagree about whether a release is a go. Every test
    therefore drives it through the schedule the handler reads for itself: the state query
    lands first, the schedule query second.
    """

    _MIXED_STATE = {'hits': {'total': {'value': 2}, 'hits': [
        _state_hit('security_reviews_complete', 'not_met', '2026-09-01T18:30:00Z',
                   criterion_type='entrance'),
        _state_hit('release_blog_ready', 'met', '2026-09-01T18:30:00Z',
                   criterion_type='exit'),
    ]}}

    # An RC was built, so a passed rc_date really does mean the release is post-RC.
    _RC_BUILT = {'hits': {'total': {'value': 1}, 'hits': [{'_source': {'rc_number': '2'}}]}}

    @staticmethod
    def _schedule(rc_date, release_date, status='active'):
        return {'hits': {'total': {'value': 1}, 'hits': [{'_source': {
            'version': '3.9.0',
            'rc_date': rc_date,
            'release_date': release_date,
            'status': status,
        }}]}}

    def _status(self, schedule, state=None, rc=None,
                now=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)):
        handler, mock_aws, _ = _load_handler()
        # State query, then the schedule, then one build query per distribution.
        rc_responses = rc if rc is not None else [self._RC_BUILT, self._RC_BUILT]
        mock_aws.opensearch_request.side_effect = [
            state or self._MIXED_STATE, schedule, *rc_responses,
        ]
        with patch.object(handler, '_now', return_value=now):
            return handler.handle_get_release_status({'version': '3.9.0'})

    def test_post_rc_judges_exit_criteria_only(self):
        # RC created on the 15th, release on the 29th: the entrance gate is behind us.
        result = self._status(self._schedule('2026-09-15', '2026-09-29'))
        assert result['criteria_scope'] == 'exit'
        assert result['verdict'] == 'green'
        assert result['out_of_scope'] == ['security_reviews_complete']

    def test_a_slipped_rc_is_still_judged_on_entrance_criteria(self):
        # Same dates as above, but no RC was ever built: the entrance gate is what the
        # release is still standing at, so judging it on exit criteria would report on a
        # gate it has not reached - and would have called this GREEN.
        no_rc = {'hits': {'total': {'value': 0}, 'hits': []}}
        result = self._status(
            self._schedule('2026-09-15', '2026-09-29'), rc=[no_rc, no_rc])
        assert result['criteria_scope'] == 'entrance'
        assert result['verdict'] == 'red'
        assert result['blocking_failures'] == ['security_reviews_complete']

    def test_pre_rc_judges_entrance_criteria_only(self):
        result = self._status(
            self._schedule('2026-09-25', '2026-10-09'),
            state={'hits': {'total': {'value': 2}, 'hits': [
                _state_hit('security_reviews_complete', 'met', '2026-09-01T18:30:00Z',
                           criterion_type='entrance'),
                _state_hit('performance_tests_posted', 'not_met', '2026-09-01T18:30:00Z',
                           criterion_type='exit'),
            ]}},
        )
        assert result['criteria_scope'] == 'entrance'
        # An unfinished exit criterion before the RC is expected, not a blocker.
        assert result['verdict'] == 'green'
        assert result['out_of_scope'] == ['performance_tests_posted']

    def test_shipped_release_is_judged_against_everything(self):
        result = self._status(self._schedule('2026-08-15', '2026-08-29', status='released'))
        assert result['criteria_scope'] == 'all'
        assert result['verdict'] == 'red'

    def test_unregistered_schedule_judges_everything(self):
        # Guessing a scope with no schedule to read would quietly drop gates.
        empty = {'hits': {'total': {'value': 0}, 'hits': []}}
        result = self._status(empty)
        assert result['criteria_scope'] == 'all'
        assert result['verdict'] == 'red'

    def test_schedule_query_failure_judges_everything(self):
        handler, mock_aws, _ = _load_handler()
        mock_aws.opensearch_request.side_effect = [self._MIXED_STATE, Exception('boom')]
        result = handler.handle_get_release_status({'version': '3.9.0'})
        assert result['criteria_scope'] == 'all'
        assert result['verdict'] == 'red'

    def test_no_criteria_in_scope_falls_back_to_everything(self):
        result = self._status(
            self._schedule('2026-09-15', '2026-09-29'),
            state={'hits': {'total': {'value': 1}, 'hits': [
                _state_hit('security_reviews_complete', 'not_met', '2026-09-01T18:30:00Z',
                           criterion_type='entrance'),
            ]}},
        )
        assert result['criteria_scope'] == 'all'
        assert result['verdict'] == 'red'

    def test_every_cadence_phase_has_a_scope_decision(self):
        # A phase missing from the map would silently be judged against everything.
        handler, _, _ = _load_handler()
        phases = {
            handler._cadence_phase(rc, rel, status, rc_created)
            for rc in (None, -5, 0, 5, 10, 20)
            for rel in (None, -3, 1, 5, 20)
            for status in (None, 'active', 'released', 'cancelled')
            for rc_created in (None, True, False)
        }
        assert phases <= set(handler.CRITERIA_FOCUS_BY_PHASE)


class TestRcDetection:
    """A passed rc_date is not an RC.

    The schedule index records the planned date and stays active either way, so the RC
    itself is read from the build results index - the same signal, read the same way, as
    ReleaseCandidateStatus.getLatestRcNumber in opensearch-build-libraries.
    """

    _NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)

    @staticmethod
    def _schedule(status='active', rc_date='2026-09-15', release_date='2026-09-29'):
        return {'hits': {'total': {'value': 1}, 'hits': [{'_source': {
            'version': '3.9.0',
            'status': status,
            'rc_date': rc_date,
            'release_date': release_date,
        }}]}}

    @staticmethod
    def _rc(rc_number):
        if rc_number is None:
            return {'hits': {'total': {'value': 0}, 'hits': []}}
        return {'hits': {'total': {'value': 1},
                         'hits': [{'_source': {'rc_number': rc_number}}]}}

    def _window(self, schedule=None, rc_responses=(), now=None):
        handler, mock_aws, _ = _load_handler()
        mock_aws.opensearch_request.side_effect = [
            schedule if schedule is not None else self._schedule(), *rc_responses,
        ]
        with patch.object(handler, '_now', return_value=now or self._NOW):
            result = handler.handle_get_release_window({'version': '3.9.0'})
        return result, mock_aws

    def test_query_matches_the_jenkins_library(self):
        _, mock_aws = self._window(rc_responses=[self._rc('3'), self._rc('1')])

        _, path, query = mock_aws.opensearch_request.call_args_list[1][0]
        # Unsuffixed and unwildcarded: this index is not month-partitioned.
        assert path == '/opensearch-distribution-build-results/_search'
        assert query['query']['bool']['filter'] == [
            {'match_phrase': {'component_category': 'OpenSearch'}},
            # The rc flag, not rc_number: every build document carries an rc_number.
            {'match_phrase': {'rc': 'true'}},
            {'match_phrase': {'version': '3.9.0'}},
            # An RC that failed to build is not one the release has reached.
            {'match_phrase': {'overall_build_result': 'SUCCESS'}},
        ]
        assert query['sort'] == [
            {'distribution_build_number': {'order': 'desc'}},
            {'rc_number': {'order': 'desc'}},
        ]
        assert query['size'] == 1

    def test_both_distributions_are_queried(self):
        _, mock_aws = self._window(rc_responses=[self._rc('3'), self._rc('1')])
        queried = [
            call[0][2]['query']['bool']['filter'][0]['match_phrase']['component_category']
            for call in mock_aws.opensearch_request.call_args_list[1:]
        ]
        # A space, not a hyphen - this is the value the build jobs index.
        assert queried == ['OpenSearch', 'OpenSearch Dashboards']

    def test_different_rc_numbers_per_distribution_are_both_reported(self):
        # The distributions are built independently, so one being behind must stay visible.
        result, _ = self._window(rc_responses=[self._rc('3'), self._rc('1')])
        assert result['rc_numbers'] == {'opensearch': 3, 'opensearch-dashboards': 1}
        assert result['rc_created'] is True
        assert result['cadence_phase'] == 'rc_to_release'

    def test_no_rc_on_either_distribution_is_overdue(self):
        result, _ = self._window(rc_responses=[self._rc(None), self._rc(None)])
        assert result['rc_created'] is False
        assert result['rc_numbers'] == {'opensearch': 0, 'opensearch-dashboards': 0}
        assert result['cadence_phase'] == 'rc_overdue'

    def test_one_distribution_having_an_rc_counts_as_post_rc(self):
        result, _ = self._window(rc_responses=[self._rc('2'), self._rc(None)])
        assert result['rc_created'] is True
        assert result['rc_numbers'] == {'opensearch': 2, 'opensearch-dashboards': 0}
        assert result['cadence_phase'] == 'rc_to_release'

    def test_a_failed_build_query_leaves_the_rc_state_unknown(self):
        # Never conflated with "no RC": one timed-out query must not reclassify a release.
        handler, mock_aws, _ = _load_handler()
        mock_aws.opensearch_request.side_effect = [self._schedule(), Exception('boom')]
        with patch.object(handler, '_now', return_value=self._NOW):
            result = handler.handle_get_release_window({'version': '3.9.0'})
        assert result['rc_created'] is None
        assert 'rc_numbers' not in result
        assert result['cadence_phase'] == 'rc_to_release'

    def test_one_failed_query_discards_the_partial_answer(self):
        handler, mock_aws, _ = _load_handler()
        mock_aws.opensearch_request.side_effect = [
            self._schedule(), self._rc('2'), Exception('boom'),
        ]
        with patch.object(handler, '_now', return_value=self._NOW):
            result = handler.handle_get_release_window({'version': '3.9.0'})
        assert result['rc_created'] is None
        assert 'rc_numbers' not in result

    def test_an_unparseable_rc_number_leaves_the_state_unknown(self):
        result, _ = self._window(rc_responses=[self._rc('not-a-number')])
        assert result['rc_created'] is None
        assert 'rc_numbers' not in result

    def test_a_string_rc_number_is_coerced(self):
        # The Jenkins side indexes it as a string, so it is never compared uncoerced.
        result, _ = self._window(rc_responses=[self._rc('10'), self._rc('9')])
        assert result['rc_numbers'] == {'opensearch': 10, 'opensearch-dashboards': 9}

    def test_the_build_index_is_not_queried_before_the_rc_date(self):
        # Before the rc_date the countdown decides the phase, so a normal run pays nothing.
        result, mock_aws = self._window(
            schedule=self._schedule(rc_date='2026-09-25', release_date='2026-10-09'))
        assert mock_aws.opensearch_request.call_count == 1
        assert result['rc_created'] is None
        assert result['cadence_phase'] == 'pre_rc_frequent'

    @pytest.mark.parametrize('status', ['released', 'cancelled'])
    def test_the_build_index_is_not_queried_for_a_finished_release(self, status):
        result, mock_aws = self._window(schedule=self._schedule(status=status))
        assert mock_aws.opensearch_request.call_count == 1
        assert result['rc_created'] is None
        assert result['cadence_phase'] == status

    def test_active_releases_carry_the_same_rc_state(self):
        # The notifier reads this list, so it must not disagree with the single-version view.
        handler, mock_aws, _ = _load_handler()
        schedule = {'hits': {'hits': [{'_source': {
            'version': '3.9.0',
            'status': 'active',
            'rc_date': '2026-09-15',
            'release_date': '2026-09-29',
            'registered_at': '2026-08-01T00:00:00Z',
        }}]}}
        mock_aws.opensearch_request.side_effect = [
            schedule, self._rc(None), self._rc(None),
        ]
        with patch.object(handler, '_now', return_value=self._NOW):
            release = handler.handle_list_active_releases({})['releases'][0]
        assert release['cadence_phase'] == 'rc_overdue'
        assert release['rc_created'] is False
        assert release['rc_numbers'] == {'opensearch': 0, 'opensearch-dashboards': 0}
