# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the release notifier's Slack message.

The message is phase-aware: before RC an unfinished exit criterion is expected rather than
news, so it must not be presented as blocking. These tests pin which criteria lead, and
that the advisory disclaimer is never dropped.
"""

import pytest

WINDOW = {
    'version': '3.9.0',
    'rc_date': '2026-09-15',
    'release_date': '2026-09-29',
    'days_to_rc': 4,
    'days_to_release': 18,
    'cadence_phase': 'pre_rc_frequent',
    'release_manager': 'someone',
    'release_issue': 'https://github.com/opensearch-project/opensearch-build/issues/6426',
}


def criterion(name, status='not_met', criterion_type='entrance', severity='blocking', **extra):
    return {
        'criterion_name': name,
        'status': status,
        'criterion_type': criterion_type,
        'severity': severity,
        **extra,
    }


def status(verdict='red', criteria=None, **extra):
    return {'verdict': verdict, 'criteria': criteria or [], **extra}


class TestHeadline:

    def test_verdict_phase_and_countdown(self, message_builder):
        text = message_builder.build_message('3.9.0', WINDOW, status())
        assert text.startswith(':red_circle: *3.9.0* — RED')
        assert 'RC imminent' in text
        assert 'RC in 4 days (2026-09-15)' in text

    def test_singular_day(self, message_builder):
        window = {**WINDOW, 'days_to_rc': 1}
        assert 'RC in 1 day (' in message_builder.build_message('3.9.0', window, status())

    def test_counts_down_to_release_once_rc_has_passed(self, message_builder):
        window = {**WINDOW, 'days_to_rc': -2, 'cadence_phase': 'rc_to_release'}
        text = message_builder.build_message('3.9.0', window, status())
        assert 'release in 18 days (2026-09-29)' in text

    def test_unknown_verdict_gets_a_neutral_marker(self, message_builder):
        text = message_builder.build_message('3.9.0', WINDOW, status(verdict='unknown'))
        assert text.startswith(':white_circle:')


class TestPhaseFocus:

    def test_pre_rc_leads_with_entrance_criteria(self, message_builder):
        text = message_builder.build_message('3.9.0', WINDOW, status(criteria=[
            criterion('security_reviews_complete', criterion_type='entrance'),
            criterion('release_blog_ready', criterion_type='exit'),
        ]))
        blocking, also_open = text.split('Also open')
        assert 'Blocking RC (entrance criteria):' in blocking
        assert 'security_reviews_complete' in blocking
        # The exit criterion is not due yet, so it is listed but not as blocking.
        assert 'release_blog_ready' in also_open

    def test_post_rc_leads_with_exit_criteria(self, message_builder):
        window = {**WINDOW, 'cadence_phase': 'final_push'}
        text = message_builder.build_message('3.9.0', window, status(criteria=[
            criterion('security_reviews_complete', criterion_type='entrance'),
            criterion('release_blog_ready', criterion_type='exit'),
        ]))
        blocking, leftover = text.split('Left open at RC')
        assert 'Blocking release (exit criteria):' in blocking
        assert 'release_blog_ready' in blocking
        # Past the gate it belonged to, so it is not "not yet due" - it was left behind.
        assert 'security_reviews_complete' in leftover
        assert 'not yet due' not in text

    def test_overdue_release_is_judged_on_exit_criteria(self, message_builder):
        window = {**WINDOW, 'cadence_phase': 'overdue', 'days_to_rc': -20,
                  'days_to_release': -3}
        text = message_builder.build_message('3.9.0', window, status(criteria=[
            criterion('release_blog_ready', criterion_type='exit'),
        ]))
        assert 'Blocking release (exit criteria):' in text
        assert 'past its release date' in text

    def test_nothing_due_in_this_phase_is_stated_explicitly(self, message_builder):
        text = message_builder.build_message('3.9.0', WINDOW, status(
            verdict='green',
            criteria=[criterion('release_blog_ready', criterion_type='exit')],
        ))
        assert 'Nothing outstanding for RC.' in text

    def test_a_non_green_verdict_never_reads_as_nothing_outstanding(self, message_builder):
        """The verdict wins over the focused list when the two disagree.

        They are computed from the same criteria in different places, so a notifier running
        ahead of an older metrics Lambda can be handed a verdict scoped differently from the
        message. "Nothing outstanding" under a RED headline would be worse than noisy.
        """
        text = message_builder.build_message('3.9.0', WINDOW, status(
            verdict='red',
            criteria=[criterion('release_blog_ready', criterion_type='exit')],
        ))
        assert 'Nothing outstanding' not in text
        assert 'yet the verdict is RED' in text

    def test_phase_without_a_focus_lists_everything_together(self, message_builder):
        window = {**WINDOW, 'cadence_phase': 'not_scheduled'}
        text = message_builder.build_message('3.9.0', window, status(criteria=[
            criterion('release_blog_ready', criterion_type='exit'),
        ]))
        assert '*Outstanding:*' in text
        assert 'Also open' not in text

    def test_all_criteria_satisfied(self, message_builder):
        window = {**WINDOW, 'cadence_phase': 'not_scheduled'}
        text = message_builder.build_message('3.9.0', window, status(
            verdict='green', criteria=[criterion('release_blog_ready', status='met')]))
        assert 'All criteria satisfied.' in text


class TestOutstandingCriteria:

    @pytest.mark.parametrize('satisfied', ['met', 'not_applicable'])
    def test_satisfied_criteria_are_omitted(self, message_builder, satisfied):
        text = message_builder.build_message('3.9.0', WINDOW, status(criteria=[
            criterion('security_reviews_complete', status=satisfied),
        ]))
        assert 'security_reviews_complete' not in text

    def test_blocking_criteria_are_listed_before_non_blocking(self, message_builder):
        text = message_builder.build_message('3.9.0', WINDOW, status(criteria=[
            criterion('roadmap_up_to_date', severity='non_blocking'),
            criterion('security_reviews_complete', severity='blocking'),
        ]))
        assert text.index('security_reviews_complete') < text.index('roadmap_up_to_date')

    def test_blocking_components_are_named(self, message_builder):
        text = message_builder.build_message('3.9.0', WINDOW, status(criteria=[
            criterion('release_notes_ready', blocking_components=['sql', 'k-NN']),
        ]))
        assert 'sql, k-NN' in text

    def test_long_component_lists_are_truncated(self, message_builder):
        components = [f'component-{i}' for i in range(15)]
        text = message_builder.build_message('3.9.0', WINDOW, status(criteria=[
            criterion('release_notes_ready', blocking_components=components),
        ]))
        assert 'component-9' in text
        assert 'component-10' not in text
        assert '(+5 more)' in text

    def test_per_product_criteria_are_scoped(self, message_builder):
        text = message_builder.build_message('3.9.0', WINDOW, status(criteria=[
            criterion('all_integration_tests_passing', product='opensearch-dashboards'),
        ]))
        assert '[opensearch-dashboards]' in text

    def test_both_products_is_not_scoped(self, message_builder):
        text = message_builder.build_message('3.9.0', WINDOW, status(criteria=[
            criterion('all_integration_tests_passing', product='both'),
        ]))
        assert '[both]' not in text


class TestDeltaAndFooter:

    def test_delta_reported_when_present(self, message_builder):
        text = message_builder.build_message('3.9.0', WINDOW, status(), delta={
            'resolved': ['security_reviews_complete'], 'raised': ['release_blog_ready'],
        })
        assert 'Since last update' in text
        assert 'resolved: `security_reviews_complete`' in text
        assert 'newly raised: `release_blog_ready`' in text

    def test_empty_delta_is_omitted(self, message_builder):
        text = message_builder.build_message(
            '3.9.0', WINDOW, status(), delta={'resolved': [], 'raised': []})
        assert 'Since last update' not in text

    def test_manager_and_issue_included(self, message_builder):
        text = message_builder.build_message('3.9.0', WINDOW, status())
        assert 'Release manager: <https://github.com/someone|@someone>' in text
        assert 'issues/6426' in text

    def test_linked_manager_is_tagged(self, message_builder):
        """The one person who has to act on this gets a real Slack ping."""
        text = message_builder.build_message(
            '3.9.0', WINDOW, status(), None, {'someone': 'U111'})
        assert 'Release manager: <@U111>' in text

    def test_unknown_manager_is_omitted(self, message_builder):
        window = {k: v for k, v in WINDOW.items() if k != 'release_manager'}
        text = message_builder.build_message('3.9.0', window, status())
        assert 'Release manager' not in text

    def test_release_issue_falls_back_to_the_state_index(self, message_builder):
        window = {k: v for k, v in WINDOW.items() if k != 'release_issue'}
        text = message_builder.build_message('3.9.0', window, status(
            release_issue='https://github.com/opensearch-project/opensearch-build/issues/1'))
        assert 'issues/1' in text

    def test_advisory_disclaimer_is_always_present(self, message_builder):
        # OSCAR advises; the release manager decides. The message must never imply otherwise.
        text = message_builder.build_message('3.9.0', WINDOW, status(verdict='green'))
        assert 'release manager makes the go/no-go decision' in text
