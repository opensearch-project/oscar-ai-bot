#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Post-query filtering for vulnerability results.

Handles array-level filtering that can't be efficiently done in OpenSearch:
exclusion removal, allowlist-based filtering, and advisory URL enrichment.
"""

import logging
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlencode

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _build_advisory_url(vuln_id: str) -> str:
    """Build the OpenSearch advisory URL for a given CVE ID.

    Args:
        vuln_id: The vulnerability identifier (e.g. ``"CVE-2024-12345"``).

    Returns:
        Full URL to the advisory page on advisories.opensearch.org.
    """
    return f"https://advisories.opensearch.org/advisory/{vuln_id}"


def filter_vulnerabilities(
    vulnerabilities: List[Dict[str, Any]],
    allowed_cve_ids: Optional[Set[str]] = None,
    include_excluded: bool = False,
) -> List[Dict[str, Any]]:
    """Remove excluded CVEs, apply an optional allowlist, and enrich with advisory URLs.

    This function handles post-query filtering that cannot be done at the
    OpenSearch level: exclusion removal and allowlist-based filtering (when
    severity/age filtering has been resolved into a set of CVE IDs by
    ``query_advisories``).

    Args:
        vulnerabilities: Raw vulnerabilities array from the scan document.
        allowed_cve_ids: If provided, only retain vulnerabilities whose ID is
            in this set. When ``None``, no allowlist filtering is applied.
        include_excluded: If False (default), only return open (non-excluded) CVEs.

    Returns:
        Filtered list of vulnerability dicts, each enriched with an
        ``advisory_url`` linking to advisories.opensearch.org.
    """
    filtered = []

    for vuln in vulnerabilities:
        # Exclusion filter
        if not include_excluded and vuln.get("excluded"):
            continue

        # Allowlist filter
        if allowed_cve_ids is not None and vuln.get("id") not in allowed_cve_ids:
            continue

        # Enrich with advisory link
        enriched = {**vuln, "advisory_url": _build_advisory_url(vuln.get("id", ""))}
        filtered.append(enriched)

    return filtered


def build_summary(vulnerabilities: List[Dict[str, Any]]) -> Dict[str, int]:
    """Build a severity summary from a filtered vulnerabilities list."""
    summary: Dict[str, int] = {}
    for vuln in vulnerabilities:
        sev = vuln.get("severity", "UNKNOWN")
        summary[sev] = summary.get(sev, 0) + 1
    return summary


# --- Neglected Page URL Builder ---

NEGLECTED_PAGE_BASE = "https://advisories.opensearch.org/advisories/neglected/"

VALID_AGE_VALUES = {"15d", "30d", "45d", "60d"}


_DEFAULT_AGE = "30d"
_DEFAULT_SEVERE = True
_DEFAULT_RELEASES = False
_DEFAULT_CRITICAL = False
_DEFAULT_TAG = "origin/main"


def build_neglected_page_url(
    age: Optional[str] = None,
    severe: Optional[bool] = None,
    releases: Optional[bool] = None,
    critical: Optional[bool] = None,
    tag: Optional[str] = None,
) -> str:
    """Build a neglected-page URL with query parameters matching the user's filters.

    When a parameter is not provided (None), a sensible default is used so the
    URL always contains a complete set of query parameters.

    Defaults:
        age="30d", severe=true, releases=false, critical=false, tag="origin/main"

    Parameters:
        age: Age threshold for neglected advisories. Valid values: "15d", "30d", "45d", "60d".
        severe: If True, only show high-severity advisories.
        releases: If True, only show release components.
        critical: If True, only show critical CVEs.
        tag: Branch or tag in the CVE (e.g., "1.2.0.1", "2.x", "origin/main").

    Returns:
        Full URL to the neglected vulnerabilities page with applicable query params.
    """
    effective_age = age if (age and age in VALID_AGE_VALUES) else _DEFAULT_AGE
    effective_severe = severe if severe is not None else _DEFAULT_SEVERE
    effective_releases = releases if releases is not None else _DEFAULT_RELEASES
    effective_critical = critical if critical is not None else _DEFAULT_CRITICAL
    effective_tag = tag if tag else _DEFAULT_TAG

    params = {
        "age": effective_age,
        "critical": str(effective_critical).lower(),
        "releases": str(effective_releases).lower(),
        "severe": str(effective_severe).lower(),
        "tag": effective_tag,
    }

    query_string = urlencode(sorted(params.items()))
    return f"{NEGLECTED_PAGE_BASE}?{query_string}"
