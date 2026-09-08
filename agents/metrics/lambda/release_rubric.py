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
"""

from typing import Any, Dict, List

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


def severity_of(criterion_name: str) -> str:
    """Return 'blocking' or 'non_blocking' for a criterion name.

    Unrecognized names default to blocking, so a criterion renamed in
    ReleaseCriterionCatalog without a matching change here becomes stricter rather than
    being silently ignored.
    """
    if criterion_name in NON_BLOCKING_CRITERIA:
        return NON_BLOCKING
    return BLOCKING


def compute_verdict(criteria: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute the R/Y/G verdict and a structured breakdown.

    Args:
        criteria: one dict per criterion, each with at least 'criterion_name' and
            'status'. 'product', 'criterion_type', 'details', 'blocking_components' and
            'last_checked' are carried into the breakdown when present.

    Returns:
        Dict with the verdict, criterion names bucketed by the kind of gap, the
        per-criterion breakdown, and counts for display.
    """
    buckets: Dict[str, List[str]] = {
        'blocking_failures': [],
        'blocking_in_progress': [],
        'blocking_unknowns': [],
        'non_blocking_gaps': [],
        'not_applicable': [],
    }
    breakdown: List[Dict[str, Any]] = []

    for criterion in criteria:
        name = criterion.get('criterion_name', '')
        status = (criterion.get('status') or UNKNOWN).lower()
        severity = severity_of(name)

        breakdown.append({
            'criterion_name': name,
            'status': status,
            'severity': severity,
            'product': criterion.get('product'),
            'criterion_type': criterion.get('criterion_type'),
            'details': criterion.get('details'),
            'blocking_components': criterion.get('blocking_components'),
            'last_checked': criterion.get('last_checked'),
        })

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

    return {
        'verdict': verdict,
        **buckets,
        'criteria': breakdown,
        'counts': counts,
    }
