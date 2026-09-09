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
            'release_manager': 'someone',
            'release_issue': 'https://github.com/opensearch-project/opensearch-build/issues/6426',
            'status': 'active',
        }
        source.update(overrides)
        return {'hits': {'total': {'value': 1}, 'hits': [{'_source': source}]}}

    def test_query_shape(self):
        handler, mock_aws, _ = _load_handler(opensearch_response=self._schedule_response())
        handler.handle_get_release_window({'version': '3.9.0'})

        _, path, query = mock_aws.opensearch_request.call_args[0]
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

    def test_rc_cut_without_a_release_date_is_post_rc(self):
        # RC has passed and no release date is registered: post-RC, not unscheduled.
        handler, _, _ = _load_handler()
        assert handler._cadence_phase(-3, None) == 'rc_to_release'

    def test_only_a_release_date_still_classifies(self):
        handler, _, _ = _load_handler()
        assert handler._cadence_phase(None, 10) == 'rc_to_release'
        assert handler._cadence_phase(None, 1) == 'final_push'


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
