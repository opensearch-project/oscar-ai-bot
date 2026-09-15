#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.

"""
Release-readiness Rubric.

Deterministic Red/Yellow/Green verdict over per-criterion release state. No LLM is
involved, so the same indexed state always produces the same verdict. Criterion names
match ReleaseCriterionCatalog in opensearch-build-libraries, which is what Jenkins writes
into opensearch_release_state.

Verdict logic:
  - Any BLOCKING criterion not satisfied         -> Red
  - All blocking satisfied, any NON-BLOCKING gap -> Yellow
  - Every criterion satisfied                    -> Green

Satisfied means met or not_applicable. Everything else (not_met, in_progress, unknown) is
a gap: an unverified or half-finished gate never reads as ready.

The verdict is scoped to the milestone still in play. Entrance criteria gate the RC and exit
criteria gate GA, so once the RC is cut an unmet entrance criterion no longer gates anything
- it was either waived at the gate or is a stale check - and letting it hold the release Red
would report a release as blocked by work that is no longer on the critical path. Criteria
outside the current scope are still reported, just separately from the verdict.
"""

from typing import Any, Dict, List, Optional

# Blocking criteria (9) - a gap here can block the release.
BLOCKING_CRITERIA = frozenset({
    'documentation_draft_prs_up',
    'release_notes_ready',
    'release_ticket_and_forum_post',
    'security_reviews_complete',
    'no_unpatched_vulnerabilities',
    'performance_tests_posted',
    'documentation_reviewed_signed_off',
    'all_integration_tests_passing',
    'release_blog_ready',
})

# Non-blocking criteria (4) - quality and process signals; they never force a Red.
NON_BLOCKING_CRITERIA = frozenset({
    'release_owners_assigned',
    'sanity_testing_done',
    'code_coverage_not_decreased',
    'roadmap_up_to_date',
})

RED = 'red'
YELLOW = 'yellow'
GREEN = 'green'

MET = 'met'
NOT_MET = 'not_met'
IN_PROGRESS = 'in_progress'
UNKNOWN = 'unknown'
NOT_APPLICABLE = 'not_applicable'

SATISFIED = frozenset({MET, NOT_APPLICABLE})

BLOCKING = 'blocking'
NON_BLOCKING = 'non_blocking'

ENTRANCE = 'entrance'
EXIT = 'exit'
SCOPE_ALL = 'all'


def severity_of(criterion_name: str) -> str:
    """Return 'blocking' or 'non_blocking' for a criterion name.

    Unrecognized names default to blocking, so a criterion renamed in
    ReleaseCriterionCatalog without a matching change here becomes stricter rather than
    being silently ignored.
    """
    if criterion_name in NON_BLOCKING_CRITERIA:
        return NON_BLOCKING
    return BLOCKING


def compute_verdict(
    criteria: List[Dict[str, Any]],
    focus: Optional[str] = None,
) -> Dict[str, Any]:
    """Compute the R/Y/G verdict and a structured breakdown.

    Args:
        criteria: one dict per criterion, each with at least 'criterion_name' and
            'status'. 'product', 'criterion_type', 'details', 'blocking_components' and
            'last_checked' are carried into the breakdown when present.
        focus: 'entrance' or 'exit' to scope the verdict to the criteria gating the
            milestone still ahead. None blends both, which is right only when the phase is
            unknown. A criterion with no criterion_type recorded counts as in scope, so an
            unclassified gate is never silently dropped from the verdict.

    Returns:
        Dict with the verdict, criterion names bucketed by the kind of gap, the names of
        unsatisfied criteria outside the scope, the per-criterion breakdown, and counts for
        display.
    """
    buckets: Dict[str, List[str]] = {
        'blocking_failures': [],
        'blocking_in_progress': [],
        'blocking_unknowns': [],
        'non_blocking_gaps': [],
        'not_applicable': [],
    }
    out_of_scope: List[str] = []
    breakdown: List[Dict[str, Any]] = []
    in_scope_total = 0

    for criterion in criteria:
        name = criterion.get('criterion_name', '')
        status = (criterion.get('status') or UNKNOWN).lower()
        severity = severity_of(name)
        criterion_type = criterion.get('criterion_type')
        in_scope = focus is None or not criterion_type or criterion_type == focus

        breakdown.append({
            'criterion_name': name,
            'status': status,
            'severity': severity,
            'product': criterion.get('product'),
            'criterion_type': criterion_type,
            'in_scope': in_scope,
            'details': criterion.get('details'),
            'blocking_components': criterion.get('blocking_components'),
            'last_checked': criterion.get('last_checked'),
        })

        if not in_scope:
            # Reported so a waived or stale gate stays visible, but it holds nothing up.
            if status not in SATISFIED:
                out_of_scope.append(name)
            continue

        in_scope_total += 1

        if status == NOT_APPLICABLE:
            buckets['not_applicable'].append(name)
        elif status == MET:
            continue
        elif severity == BLOCKING:
            if status == IN_PROGRESS:
                buckets['blocking_in_progress'].append(name)
            elif status == UNKNOWN:
                buckets['blocking_unknowns'].append(name)
            else:
                buckets['blocking_failures'].append(name)
        else:
            buckets['non_blocking_gaps'].append(name)

    # Nothing in scope means no evidence about the milestone ahead, and no evidence must
    # never read as ready. Fall back to judging every criterion rather than returning a
    # Green off an empty set.
    if focus is not None and in_scope_total == 0 and criteria:
        return compute_verdict(criteria, focus=None)

    has_blocking_gap = any(
        buckets[key] for key in
        ('blocking_failures', 'blocking_in_progress', 'blocking_unknowns')
    )
    if has_blocking_gap:
        verdict = RED
    elif buckets['non_blocking_gaps']:
        verdict = YELLOW
    else:
        verdict = GREEN

    counts = {key: len(names) for key, names in buckets.items()}
    counts['total'] = len(criteria)
    counts['in_scope'] = in_scope_total
    counts['out_of_scope'] = len(out_of_scope)

    return {
        'verdict': verdict,
        'criteria_scope': focus or SCOPE_ALL,
        **buckets,
        'out_of_scope': out_of_scope,
        'criteria': breakdown,
        'counts': counts,
    }
