#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Slack message construction for the release notifier.

Messages are phase-aware: they lead with the criteria that are actually due in the
current phase, because entrance criteria gate the RC while exit criteria gate GA. During
the pre-RC window an exit criterion being unfinished is expected, not news, so leading
with the blended verdict would train readers to ignore the alert. The overall verdict is
still reported, just as supporting detail.
"""

from typing import Any, Dict, List, Optional

from identity import render_release_manager

VERDICT_EMOJI = {
    'red': ':red_circle:',
    'yellow': ':large_yellow_circle:',
    'green': ':large_green_circle:',
}

# Which criterion type gates the milestone the release is currently working towards. Used
# only when the verdict does not report its own scope, which the metrics Lambda now always
# does - kept as a fallback so an older metrics deployment still renders sensibly.
PHASE_FOCUS = {
    'pre_rc_daily': 'entrance',
    'pre_rc_frequent': 'entrance',
    'rc_overdue': 'entrance',
    'rc_to_release': 'exit',
    'final_push': 'exit',
    'overdue': 'exit',
}

# How the criteria that are outside the verdict's scope are introduced. Before the RC the
# exit criteria simply are not due yet; after it, an unmet entrance criterion is not pending
# work but something that was waived or left behind at the gate, and saying "not yet due"
# about it would be plainly wrong.
LEFTOVER_LABEL = {
    'entrance': '_Also open, not yet due (exit criteria):_',
    'exit': '_Left open at RC (entrance criteria):_',
}

PHASE_LABEL = {
    'pre_rc_daily': 'approaching RC',
    'pre_rc_frequent': 'RC imminent',
    # States the fact rather than asserting a milestone: the RC date is behind us and no RC
    # build exists. Claiming the RC here is what made the notifier report a milestone the
    # release had not reached.
    'rc_overdue': 'RC date passed, no RC created yet',
    'rc_to_release': 'RC created, approaching release',
    'final_push': 'final stretch before release',
    'overdue': 'past its release date',
    'released': 'released',
    'cancelled': 'cancelled',
    'out_of_window': 'early',
    'not_scheduled': 'no dates registered',
}

MAX_LISTED_COMPONENTS = 10


def _days(count: int) -> str:
    return f"{count} day{'s' if count != 1 else ''}"


def _countdown(window: Dict[str, Any]) -> str:
    """Describe how far away the next milestone is."""
    days_to_rc = window.get('days_to_rc')
    days_to_release = window.get('days_to_release')

    if days_to_rc is not None and days_to_rc >= 0:
        return f"RC in {_days(days_to_rc)} ({window.get('rc_date')})"

    if days_to_release is not None and days_to_release >= 0:
        countdown = f"release in {_days(days_to_release)} ({window.get('release_date')})"
        # An RC that has not been created is the nearer milestone and the one that is late, so
        # the headline says how late rather than only counting down to a date further out.
        if window.get('cadence_phase') == 'rc_overdue' and days_to_rc is not None:
            return f"RC {_days(abs(days_to_rc))} overdue ({window.get('rc_date')}) · {countdown}"
        return countdown

    return f"release date {window.get('release_date')}"


def _rc_progress(window: Dict[str, Any]) -> Optional[str]:
    """Report the RC number reached per distribution, when it is known.

    Both are named even when one is at zero: the distributions are built separately and reach
    different RC numbers, so a single figure would hide one of them being behind.
    """
    numbers = window.get('rc_numbers')
    if not isinstance(numbers, dict) or not numbers:
        return None
    parts = [
        f"{product}: {f'RC{number}' if number else 'none yet'}"
        for product, number in numbers.items()
    ]
    return 'RC builds — ' + ', '.join(parts)


def _criterion_line(criterion: Dict[str, Any]) -> str:
    """Render one outstanding criterion, naming the components that hold it up."""
    name = criterion.get('criterion_name', 'unknown')
    status = criterion.get('status', 'unknown')
    product = criterion.get('product')
    scope = '' if product in (None, 'both') else f' [{product}]'

    line = f"• `{name}`{scope} — {status}"

    components = criterion.get('blocking_components') or []
    if components:
        shown = components[:MAX_LISTED_COMPONENTS]
        more = len(components) - len(shown)
        suffix = f' (+{more} more)' if more > 0 else ''
        line += f"\n    {', '.join(shown)}{suffix}"
    return line


def _outstanding(status: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Criteria that are not satisfied, blocking ones first."""
    gaps = [
        c for c in status.get('criteria', [])
        if c.get('status') not in ('met', 'not_applicable')
    ]
    gaps.sort(key=lambda c: (c.get('severity') != 'blocking', c.get('criterion_name') or ''))
    return gaps


def build_message(
    version: str,
    window: Dict[str, Any],
    status: Dict[str, Any],
    delta: Optional[Dict[str, List[str]]] = None,
    handle_map: Optional[Dict[str, str]] = None,
) -> str:
    """Build the Slack message for one release.

    handle_map resolves the release manager's GitHub handle to a Slack user so they are
    mentioned rather than merely named; see identity.render_release_manager.
    """
    phase = window.get('cadence_phase', 'not_scheduled')
    verdict = status.get('verdict', 'unknown')
    emoji = VERDICT_EMOJI.get(verdict, ':white_circle:')

    lines = [
        f"{emoji} *{version}* — {verdict.upper()} · {PHASE_LABEL.get(phase, phase)} · {_countdown(window)}"
    ]

    outstanding = _outstanding(status)
    # The verdict reports the criteria it was judged against, so the message groups them the
    # same way it was decided rather than re-deriving it from the phase.
    scope = status.get('criteria_scope')
    focus = None if scope == 'all' else scope or PHASE_FOCUS.get(phase)

    if focus:
        due_now = [c for c in outstanding if c.get('criterion_type') == focus]
        later = [c for c in outstanding if c.get('criterion_type') != focus]
        milestone = 'RC' if focus == 'entrance' else 'release'
        if due_now:
            lines.append(f"\n*Blocking {milestone} ({focus} criteria):*")
            lines.extend(_criterion_line(c) for c in due_now)
        elif verdict == 'green':
            lines.append(f"\nNothing outstanding for {milestone}.")
        else:
            # The verdict and this list are computed from the same criteria, so they should
            # agree - but they are computed in different places, and a notifier running
            # ahead of an older metrics Lambda gets a verdict scoped differently from the
            # message. Never let that render as "nothing outstanding" under a RED headline.
            lines.append(
                f"\nNo {focus} criteria are outstanding, yet the verdict is "
                f"{verdict.upper()} — treat the verdict as authoritative and check "
                f"the criteria below."
            )
        if later:
            names = ', '.join(f"`{c.get('criterion_name')}`" for c in later)
            lines.append(f"\n{LEFTOVER_LABEL[focus]} {names}")
    elif outstanding:
        lines.append('\n*Outstanding:*')
        lines.extend(_criterion_line(c) for c in outstanding)
    else:
        lines.append('\nAll criteria satisfied.')

    if delta and (delta.get('resolved') or delta.get('raised')):
        parts = []
        if delta.get('resolved'):
            parts.append('resolved: ' + ', '.join(f'`{n}`' for n in delta['resolved']))
        if delta.get('raised'):
            parts.append('newly raised: ' + ', '.join(f'`{n}`' for n in delta['raised']))
        lines.append('\n*Since last update* — ' + '; '.join(parts))

    rc_progress = _rc_progress(window)
    if rc_progress:
        lines.append(f"\n{rc_progress}")

    manager = render_release_manager(window.get('release_manager'), handle_map)
    if manager:
        lines.append(f"\nRelease manager: {manager}")

    issue = window.get('release_issue') or status.get('release_issue')
    if issue:
        lines.append(f"Release issue: {issue}")

    lines.append('\n_Advisory only — the release manager makes the go/no-go decision._')
    return '\n'.join(lines)
