# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the release notifier's cadence and change detection.

Two things gate a post: how close the release is, and whether anything moved since the
last one. These tests pin both, plus the phases that must stay silent - a notifier that
posts in the wrong phase trains release managers to ignore it.
"""


class TestPhaseIntervals:

    def test_phases_that_never_post(self, cadence):
        for phase in ('out_of_window', 'released', 'cancelled', 'not_scheduled'):
            assert cadence.PHASE_INTERVAL_HOURS[phase] is None

    def test_intervals_tighten_as_the_milestone_approaches(self, cadence):
        intervals = cadence.PHASE_INTERVAL_HOURS
        assert intervals['pre_rc_daily'] == 24
        assert intervals['pre_rc_frequent'] == 6
        assert intervals['rc_to_release'] == 24
        assert intervals['final_push'] == 6

    def test_overdue_is_reported_but_slowly(self, cadence):
        # A late release is already known to be late, so it is reported every two days.
        assert cadence.PHASE_INTERVAL_HOURS['overdue'] == 48

    def test_unknown_phase_does_not_post(self, cadence):
        notify, reason = cadence.should_notify('some_new_phase', 'red', {}, None, None)
        assert notify is False
        assert 'does not notify' in reason


class TestGapSignature:

    def test_buckets_are_sorted_for_comparison(self, cadence):
        signature = cadence.gap_signature({
            'blocking_failures': ['release_notes_ready', 'all_integration_tests_passing'],
            'non_blocking_gaps': ['roadmap_up_to_date'],
        })
        assert signature['blocking_failures'] == [
            'all_integration_tests_passing', 'release_notes_ready',
        ]
        assert signature['blocking_in_progress'] == []
        assert signature['non_blocking_gaps'] == ['roadmap_up_to_date']

    def test_missing_and_null_buckets_become_empty_lists(self, cadence):
        assert cadence.gap_signature({'blocking_failures': None}) == {
            field: [] for field in cadence.GAP_FIELDS
        }


class TestDiffGaps:

    def test_no_previous_post_reports_no_change(self, cadence):
        # The first post carries the full picture, so framing it as deltas would be noise.
        assert cadence.diff_gaps(None, {'blocking_failures': ['a']}) == {
            'resolved': [], 'raised': [],
        }

    def test_resolved_and_raised_detected(self, cadence):
        previous = {'blocking_failures': ['a'], 'non_blocking_gaps': ['b']}
        current = {'blocking_failures': ['c'], 'non_blocking_gaps': ['b']}
        assert cadence.diff_gaps(previous, current) == {
            'resolved': ['a'], 'raised': ['c'],
        }

    def test_moving_between_buckets_is_not_a_change(self, cadence):
        # in_progress -> not_met is the same open criterion, not a resolution plus a raise.
        previous = {'blocking_in_progress': ['release_notes_ready']}
        current = {'blocking_failures': ['release_notes_ready']}
        assert cadence.diff_gaps(previous, current) == {'resolved': [], 'raised': []}


class TestShouldNotify:

    GAPS = {'blocking_failures': ['release_notes_ready']}

    def test_first_post_always_goes_out(self, cadence):
        notify, reason = cadence.should_notify('pre_rc_daily', 'red', self.GAPS, None, None)
        assert notify is True
        assert 'first post' in reason

    def test_silent_inside_the_phase_interval(self, cadence):
        last = {'verdict': 'red', **self.GAPS}
        notify, reason = cadence.should_notify('pre_rc_daily', 'red', self.GAPS, last, 3.0)
        assert notify is False
        assert 'posts every 24h' in reason

    def test_verdict_change_posts_even_though_nothing_else_moved(self, cadence):
        last = {'verdict': 'red', **self.GAPS}
        notify, reason = cadence.should_notify('pre_rc_daily', 'yellow', self.GAPS, last, 25.0)
        assert notify is True
        assert 'verdict changed' in reason

    def test_verdict_change_still_waits_for_the_interval(self, cadence):
        # Otherwise a criterion flapping between runs would post every six hours.
        last = {'verdict': 'red', **self.GAPS}
        notify, _ = cadence.should_notify('pre_rc_daily', 'green', self.GAPS, last, 1.0)
        assert notify is False

    def test_criteria_change_posts(self, cadence):
        last = {'verdict': 'red', 'blocking_failures': ['release_notes_ready']}
        current = {'blocking_failures': ['release_blog_ready']}
        notify, reason = cadence.should_notify('pre_rc_frequent', 'red', current, last, 7.0)
        assert notify is True
        assert reason == 'outstanding criteria changed'

    def test_heartbeat_posts_when_nothing_changed(self, cadence):
        last = {'verdict': 'red', **self.GAPS}
        notify, reason = cadence.should_notify('pre_rc_frequent', 'red', self.GAPS, last, 30.0)
        assert notify is True
        assert 'heartbeat' in reason

    def test_unchanged_release_stays_quiet_before_the_heartbeat(self, cadence):
        last = {'verdict': 'red', **self.GAPS}
        notify, reason = cadence.should_notify('pre_rc_frequent', 'red', self.GAPS, last, 8.0)
        assert notify is False
        assert reason == 'nothing changed since the last post'

    def test_unreadable_last_post_time_still_requires_a_change(self, cadence):
        """An unparseable last_posted_at costs the interval check, nothing more.

        The timestamp is written by this Lambda, so an unreadable one means a manual edit or
        a schema change. Discarding the whole record instead would take the change detection
        with it and post unconditionally; keeping it means the only way to a post is that
        something actually moved.
        """
        last = {'verdict': 'red', **self.GAPS}
        notify, reason = cadence.should_notify('pre_rc_frequent', 'red', self.GAPS, last, None)
        assert notify is False
        assert reason == 'nothing changed since the last post'

        notify, reason = cadence.should_notify('pre_rc_frequent', 'green', self.GAPS, last, None)
        assert notify is True
        assert 'verdict changed' in reason

    def test_silent_phase_wins_over_a_changed_verdict(self, cadence):
        last = {'verdict': 'red', **self.GAPS}
        notify, reason = cadence.should_notify('released', 'green', {}, last, 100.0)
        assert notify is False
        assert 'does not notify' in reason
