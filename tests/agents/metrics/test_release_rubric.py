# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the release-readiness rubric.

Covers every verdict combination: all satisfied, blocking gaps in each status
(not_met, in_progress, unknown), non-blocking gaps, not_applicable handling,
unknown criterion names, and empty input.
"""

import importlib.util
import os

_LAMBDA_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'agents', 'metrics', 'lambda',
)


def _load_rubric():
    spec = importlib.util.spec_from_file_location(
        'release_rubric', os.path.join(_LAMBDA_PATH, 'release_rubric.py'),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rubric = _load_rubric()


def _criterion(name, status, **extra):
    return {'criterion_name': name, 'status': status, **extra}


class TestSeverityOf:

    def test_blocking_criterion(self):
        assert rubric.severity_of('all_integration_tests_passing') == 'blocking'

    def test_non_blocking_criterion(self):
        assert rubric.severity_of('release_owners_assigned') == 'non_blocking'

    def test_no_unpatched_vulnerabilities_is_blocking(self):
        assert rubric.severity_of('no_unpatched_vulnerabilities') == 'blocking'

    def test_unknown_name_defaults_to_blocking(self):
        assert rubric.severity_of('some_future_criterion') == 'blocking'

    def test_catalog_is_fully_classified(self):
        assert len(rubric.BLOCKING_CRITERIA) == 9
        assert len(rubric.NON_BLOCKING_CRITERIA) == 4
        assert not rubric.BLOCKING_CRITERIA & rubric.NON_BLOCKING_CRITERIA


class TestVerdictGreen:

    def test_all_met(self):
        criteria = [
            _criterion('all_integration_tests_passing', 'met'),
            _criterion('release_owners_assigned', 'met'),
        ]
        assert rubric.compute_verdict(criteria)['verdict'] == 'green'

    def test_not_applicable_counts_as_satisfied(self):
        criteria = [
            _criterion('all_integration_tests_passing', 'met'),
            _criterion('release_blog_ready', 'not_applicable'),
        ]
        result = rubric.compute_verdict(criteria)
        assert result['verdict'] == 'green'
        assert result['not_applicable'] == ['release_blog_ready']

    def test_empty_input_is_green(self):
        result = rubric.compute_verdict([])
        assert result['verdict'] == 'green'
        assert result['counts']['total'] == 0


class TestVerdictRed:

    def test_blocking_not_met(self):
        criteria = [
            _criterion('all_integration_tests_passing', 'not_met'),
            _criterion('release_owners_assigned', 'met'),
        ]
        result = rubric.compute_verdict(criteria)
        assert result['verdict'] == 'red'
        assert result['blocking_failures'] == ['all_integration_tests_passing']

    def test_blocking_in_progress_is_red(self):
        # A half-finished blocking gate must never read as ready.
        criteria = [_criterion('security_reviews_complete', 'in_progress')]
        result = rubric.compute_verdict(criteria)
        assert result['verdict'] == 'red'
        assert result['blocking_in_progress'] == ['security_reviews_complete']

    def test_blocking_unknown_is_red(self):
        criteria = [_criterion('performance_tests_posted', 'unknown')]
        result = rubric.compute_verdict(criteria)
        assert result['verdict'] == 'red'
        assert result['blocking_unknowns'] == ['performance_tests_posted']

    def test_missing_status_treated_as_unknown(self):
        result = rubric.compute_verdict([_criterion('release_notes_ready', None)])
        assert result['verdict'] == 'red'
        assert result['blocking_unknowns'] == ['release_notes_ready']

    def test_unclassified_criterion_gap_is_red(self):
        result = rubric.compute_verdict([_criterion('some_future_criterion', 'not_met')])
        assert result['verdict'] == 'red'

    def test_blocking_gap_wins_over_non_blocking_gap(self):
        criteria = [
            _criterion('all_integration_tests_passing', 'not_met'),
            _criterion('release_owners_assigned', 'not_met'),
        ]
        result = rubric.compute_verdict(criteria)
        assert result['verdict'] == 'red'
        assert result['non_blocking_gaps'] == ['release_owners_assigned']


class TestVerdictYellow:

    def test_only_non_blocking_gap(self):
        criteria = [
            _criterion('all_integration_tests_passing', 'met'),
            _criterion('release_owners_assigned', 'not_met'),
        ]
        result = rubric.compute_verdict(criteria)
        assert result['verdict'] == 'yellow'
        assert result['non_blocking_gaps'] == ['release_owners_assigned']

    def test_non_blocking_in_progress_and_unknown_are_yellow(self):
        criteria = [
            _criterion('sanity_testing_done', 'in_progress'),
            _criterion('roadmap_up_to_date', 'unknown'),
        ]
        result = rubric.compute_verdict(criteria)
        assert result['verdict'] == 'yellow'
        assert set(result['non_blocking_gaps']) == {'sanity_testing_done', 'roadmap_up_to_date'}


class TestBreakdown:

    def test_breakdown_carries_context_fields(self):
        criteria = [_criterion(
            'all_integration_tests_passing', 'not_met',
            product='opensearch', criterion_type='exit',
            blocking_components=['sql'], last_checked='2026-09-01T18:30:42Z',
        )]
        entry = rubric.compute_verdict(criteria)['criteria'][0]
        assert entry['severity'] == 'blocking'
        assert entry['product'] == 'opensearch'
        assert entry['criterion_type'] == 'exit'
        assert entry['blocking_components'] == ['sql']
        assert entry['last_checked'] == '2026-09-01T18:30:42Z'

    def test_counts(self):
        criteria = [
            _criterion('all_integration_tests_passing', 'not_met'),
            _criterion('security_reviews_complete', 'in_progress'),
            _criterion('performance_tests_posted', 'unknown'),
            _criterion('release_owners_assigned', 'not_met'),
            _criterion('release_blog_ready', 'not_applicable'),
            _criterion('release_notes_ready', 'met'),
        ]
        counts = rubric.compute_verdict(criteria)['counts']
        assert counts == {
            'blocking_failures': 1,
            'blocking_in_progress': 1,
            'blocking_unknowns': 1,
            'non_blocking_gaps': 1,
            'not_applicable': 1,
            'total': 6,
            'in_scope': 6,
            'out_of_scope': 0,
        }

    def test_status_is_case_insensitive(self):
        result = rubric.compute_verdict([_criterion('release_notes_ready', 'MET')])
        assert result['verdict'] == 'green'


class TestCriteriaScope:
    """The verdict is judged only against the milestone still ahead.

    Once the RC is cut, an unmet entrance criterion was waived at the gate or is a stale
    check; holding the release Red on it would report work that is no longer on the
    critical path as blocking.
    """

    _MIXED = [
        _criterion('security_reviews_complete', 'not_met', criterion_type='entrance'),
        _criterion('release_blog_ready', 'met', criterion_type='exit'),
    ]

    def test_no_focus_judges_everything(self):
        result = rubric.compute_verdict(self._MIXED)
        assert result['criteria_scope'] == 'all'
        assert result['verdict'] == 'red'
        assert result['out_of_scope'] == []

    def test_exit_focus_ignores_an_unmet_entrance_criterion(self):
        result = rubric.compute_verdict(self._MIXED, focus='exit')
        assert result['criteria_scope'] == 'exit'
        assert result['verdict'] == 'green'
        assert result['blocking_failures'] == []
        # Reported so a waived gate stays visible, but it holds nothing up.
        assert result['out_of_scope'] == ['security_reviews_complete']

    def test_entrance_focus_ignores_an_unmet_exit_criterion(self):
        criteria = [
            _criterion('security_reviews_complete', 'met', criterion_type='entrance'),
            _criterion('performance_tests_posted', 'not_met', criterion_type='exit'),
        ]
        result = rubric.compute_verdict(criteria, focus='entrance')
        assert result['verdict'] == 'green'
        assert result['out_of_scope'] == ['performance_tests_posted']

    def test_satisfied_criteria_outside_scope_are_not_reported(self):
        result = rubric.compute_verdict(self._MIXED, focus='entrance')
        assert result['verdict'] == 'red'
        assert result['out_of_scope'] == []

    def test_counts_split_in_and_out_of_scope(self):
        counts = rubric.compute_verdict(self._MIXED, focus='exit')['counts']
        assert counts['total'] == 2
        assert counts['in_scope'] == 1
        assert counts['out_of_scope'] == 1

    def test_breakdown_flags_scope_per_criterion(self):
        entries = rubric.compute_verdict(self._MIXED, focus='exit')['criteria']
        in_scope = {e['criterion_name']: e['in_scope'] for e in entries}
        assert in_scope == {'security_reviews_complete': False, 'release_blog_ready': True}

    def test_untyped_criterion_is_always_in_scope(self):
        # Older documents predate criterion_type; dropping them would silently lose a gate.
        result = rubric.compute_verdict([_criterion('release_notes_ready', 'not_met')], focus='exit')
        assert result['verdict'] == 'red'
        assert result['counts']['in_scope'] == 1

    def test_nothing_in_scope_falls_back_to_judging_everything(self):
        # No evidence about the milestone ahead must never read as ready.
        criteria = [_criterion('security_reviews_complete', 'not_met', criterion_type='entrance')]
        result = rubric.compute_verdict(criteria, focus='exit')
        assert result['verdict'] == 'red'
        assert result['criteria_scope'] == 'all'
        assert result['blocking_failures'] == ['security_reviews_complete']

    def test_empty_input_with_a_focus_stays_green(self):
        result = rubric.compute_verdict([], focus='exit')
        assert result['verdict'] == 'green'
        assert result['criteria_scope'] == 'exit'
