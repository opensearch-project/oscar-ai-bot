#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Post-query filtering for vulnerability results.

Handles array-level filtering that can't be efficiently done in OpenSearch:
severity, exclusion status, and specific CVE lookups.
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
    severity: Optional[Set[str]] = None,
    include_excluded: bool = False,
) -> List[Dict[str, Any]]:
    """Filter a vulnerabilities array from a scan document.

    Args:
        vulnerabilities: Raw vulnerabilities array from the scan document.
        severity: Set of severity levels to include (e.g., {"HIGH", "CRITICAL"}).
                  If None, all severities are included.
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

        # Severity filter
        if severity and vuln.get("severity") not in severity:
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


def build_neglected_page_url(
    age: Optional[str] = None,
    severe: Optional[bool] = None,
    releases: Optional[bool] = None,
    critical: Optional[bool] = None,
    tag: Optional[str] = None,
) -> str:
    """Build a neglected-page URL with query parameters matching the user's filters.

    Parameters:
        age: Age threshold for neglected advisories. Valid values: "15d", "30d", "45d", "60d".
        severe: If True, only show high-severity advisories.
        releases: If True, only show release components.
        critical: If True, only show critical CVEs.
        tag: Branch or tag in the CVE (e.g., "1.2.0.1", "2.x").

    Returns:
        Full URL to the neglected vulnerabilities page with applicable query params.
    """
    params = {}
    if age and age in VALID_AGE_VALUES:
        params["age"] = age
    if severe is not None:
        params["severe"] = str(severe).lower()
    if releases is not None:
        params["releases"] = str(releases).lower()
    if critical is not None:
        params["critical"] = str(critical).lower()
    if tag:
        params["tag"] = tag

    if params:
        query_string = urlencode(sorted(params.items()))
        return f"{NEGLECTED_PAGE_BASE}?{query_string}"
    return NEGLECTED_PAGE_BASE
