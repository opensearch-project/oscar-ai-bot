#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Notification cadence and change detection for the release notifier.

The Lambda wakes on a fixed 6-hourly schedule and this module decides whether a given
release is actually due for a post. Two things gate a post:

  1. Cadence - how close the release is, from the phase get_release_window returns.
     Notifications escalate as the release approaches and stay silent well before RC.
  2. Change - whether anything moved since the last post. A run that finds no change
     stays quiet, except for a heartbeat so that silence never reads as a broken job.
"""

from typing import Any, Dict, List, Optional, Tuple

# Minimum hours between posts per cadence phase. None means never post.
PHASE_INTERVAL_HOURS: Dict[str, Optional[int]] = {
    'out_of_window': None,
    'pre_rc_daily': 24,
    'pre_rc_frequent': 6,
    'rc_to_release': 24,
    'final_push': 6,
    # An active release past its date is late by definition and the RM already knows it, so
    # it stays reported but every two days rather than nagging every six hours.
    'overdue': 48,
    'released': None,
    'cancelled': None,
    'not_scheduled': None,
}

# Longest a release can go without any post while its phase is active, so an unchanged
# but still-open release confirms the pipeline is alive.
HEARTBEAT_HOURS = 24

GAP_FIELDS = (
    'blocking_failures',
    'blocking_in_progress',
    'blocking_unknowns',
    'non_blocking_gaps',
)


def gap_signature(status: Dict[str, Any]) -> Dict[str, List[str]]:
    """Reduce a verdict to the comparable set of outstanding criteria per bucket."""
    return {field: sorted(status.get(field) or []) for field in GAP_FIELDS}


def diff_gaps(
    previous: Optional[Dict[str, Any]],
    current: Dict[str, List[str]],
) -> Dict[str, List[str]]:
    """Return criteria that were resolved and newly raised since the previous post."""
    if not previous:
        return {'resolved': [], 'raised': []}

    was = {name for field in GAP_FIELDS for name in (previous.get(field) or [])}
    now = {name for field in GAP_FIELDS for name in (current.get(field) or [])}
    return {'resolved': sorted(was - now), 'raised': sorted(now - was)}


def should_notify(
    phase: str,
    verdict: str,
    gaps: Dict[str, List[str]],
    last_post: Optional[Dict[str, Any]],
    hours_since_last: Optional[float],
) -> Tuple[bool, str]:
    """Decide whether to post, returning the decision and the reason for it.

    The reason is logged so an operator can tell a deliberate silence from a failure.
    """
    interval = PHASE_INTERVAL_HOURS.get(phase)
    if interval is None:
        return False, f'phase {phase} does not notify'

    if last_post is None:
        return True, 'first post for this release'

    if hours_since_last is not None and hours_since_last < interval:
        return False, (
            f'last post was {hours_since_last:.1f}h ago, '
            f'phase {phase} posts every {interval}h'
        )

    if last_post.get('verdict') != verdict:
        return True, f"verdict changed from {last_post.get('verdict')} to {verdict}"

    delta = diff_gaps(last_post, gaps)
    if delta['resolved'] or delta['raised']:
        return True, 'outstanding criteria changed'

    if hours_since_last is not None and hours_since_last >= HEARTBEAT_HOURS:
        return True, f'heartbeat, nothing changed in {hours_since_last:.1f}h'

    return False, 'nothing changed since the last post'
