# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the security advisories response filter.

These tests verify that array-level filtering (severity, exclusion status)
works correctly on vulnerability arrays returned from OpenSearch.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'agents', 'security_advisories', 'lambda'
))

from response_filter import build_summary, filter_vulnerabilities  # noqa: E402

# Reusable mock vulnerability data
MOCK_VULNERABILITIES = [
    {
        "id": "CVE-2024-001",
        "aliases": ["GHSA-xxxx-0001"],
        "severity": "CRITICAL",
        "package": {"name": "lodash", "version": "4.17.20"},
    },
    {
        "id": "CVE-2024-002",
        "aliases": ["GHSA-xxxx-0002"],
        "severity": "HIGH",
        "package": {"name": "express", "version": "4.17.1"},
    },
    {
        "id": "CVE-2024-003",
        "aliases": ["GHSA-xxxx-0003"],
        "severity": "HIGH",
        "excluded": "AT_PROJECT",
        "package": {"name": "axios", "version": "0.21.1"},
    },
    {
        "id": "CVE-2024-004",
        "aliases": ["GHSA-xxxx-0004"],
        "severity": "MEDIUM",
        "package": {"name": "minimist", "version": "1.2.5"},
    },
    {
        "id": "CVE-2024-005",
        "aliases": ["GHSA-xxxx-0005"],
        "severity": "LOW",
        "excluded": "AT_RULE",
        "package": {"name": "debug", "version": "4.3.1"},
    },
]


class TestFilterVulnerabilities(unittest.TestCase):
    """Test array-level vulnerability filtering."""

    def test_no_filters_excludes_suppressed(self):
        """Default behavior: return all non-excluded CVEs."""
        result = filter_vulnerabilities(MOCK_VULNERABILITIES)

        self.assertEqual(len(result), 3)
        ids = {v["id"] for v in result}
        self.assertIn("CVE-2024-001", ids)
        self.assertIn("CVE-2024-002", ids)
        self.assertIn("CVE-2024-004", ids)
        self.assertNotIn("CVE-2024-003", ids)
        self.assertNotIn("CVE-2024-005", ids)

    def test_include_excluded(self):
        """'Show me all CVEs including excluded' — include_excluded=True."""
        result = filter_vulnerabilities(MOCK_VULNERABILITIES, include_excluded=True)

        self.assertEqual(len(result), 5)

    def test_allowlist_keeps_only_listed_cves(self):
        """Only CVEs in the allowlist are returned (excluded still filtered)."""
        allowed = {"CVE-2024-001", "CVE-2024-002"}
        result = filter_vulnerabilities(MOCK_VULNERABILITIES, allowed_cve_ids=allowed)

        self.assertEqual(len(result), 2)
        ids = {v["id"] for v in result}
        self.assertEqual(ids, {"CVE-2024-001", "CVE-2024-002"})

    def test_allowlist_with_excluded_cve(self):
        """Excluded CVEs are still filtered even if they're in the allowlist."""
        allowed = {"CVE-2024-002", "CVE-2024-003"}  # CVE-003 is excluded
        result = filter_vulnerabilities(MOCK_VULNERABILITIES, allowed_cve_ids=allowed)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "CVE-2024-002")

    def test_allowlist_include_excluded(self):
        """With include_excluded=True, excluded CVEs in the allowlist are kept."""
        allowed = {"CVE-2024-002", "CVE-2024-003"}
        result = filter_vulnerabilities(
            MOCK_VULNERABILITIES, allowed_cve_ids=allowed, include_excluded=True,
        )

        self.assertEqual(len(result), 2)
        ids = {v["id"] for v in result}
        self.assertEqual(ids, {"CVE-2024-002", "CVE-2024-003"})

    def test_allowlist_no_match(self):
        """Allowlist with no matching CVEs returns empty."""
        allowed = {"CVE-9999-999"}
        result = filter_vulnerabilities(MOCK_VULNERABILITIES, allowed_cve_ids=allowed)
        self.assertEqual(result, [])

    def test_allowlist_none_means_no_filtering(self):
        """When allowed_cve_ids is None, all non-excluded CVEs pass through."""
        result = filter_vulnerabilities(MOCK_VULNERABILITIES, allowed_cve_ids=None)

        self.assertEqual(len(result), 3)
        ids = {v["id"] for v in result}
        self.assertEqual(ids, {"CVE-2024-001", "CVE-2024-002", "CVE-2024-004"})

    def test_empty_vulnerabilities(self):
        """No vulnerabilities at all."""
        result = filter_vulnerabilities([])
        self.assertEqual(result, [])

    def test_empty_allowlist_returns_empty(self):
        """An empty allowlist (not None) means nothing passes."""
        result = filter_vulnerabilities(MOCK_VULNERABILITIES, allowed_cve_ids=set())
        self.assertEqual(result, [])


class TestBuildSummary(unittest.TestCase):
    """Test severity summary generation."""

    def test_summary_from_filtered(self):
        filtered = filter_vulnerabilities(MOCK_VULNERABILITIES)
        summary = build_summary(filtered)

        self.assertEqual(summary, {"CRITICAL": 1, "HIGH": 1, "MEDIUM": 1})

    def test_summary_all_including_excluded(self):
        filtered = filter_vulnerabilities(MOCK_VULNERABILITIES, include_excluded=True)
        summary = build_summary(filtered)

        self.assertEqual(summary, {"CRITICAL": 1, "HIGH": 2, "MEDIUM": 1, "LOW": 1})

    def test_summary_empty(self):
        summary = build_summary([])
        self.assertEqual(summary, {})

    def test_summary_single_severity(self):
        # Use allowlist to keep only the CRITICAL CVE
        filtered = filter_vulnerabilities(
            MOCK_VULNERABILITIES, allowed_cve_ids={"CVE-2024-001"},
        )
        summary = build_summary(filtered)

        self.assertEqual(summary, {"CRITICAL": 1})


class TestProperty2AllowlistFilterCorrectness(unittest.TestCase):
    """**Validates: Requirements 3.2**

    Property 2: Allowlist filter returns only CVEs in the allowed set and
    drops none that match.

    For any list of vulnerability dicts and any non-empty allowlist,
    filter_vulnerabilities with that allowlist SHALL return only
    vulnerabilities whose ID is in the allowed set, and SHALL return all
    non-excluded vulnerabilities from the input whose ID is in the allowed set.
    """

    def _make_vuln(self, vuln_id, severity="HIGH", excluded=None):
        """Helper to create a vulnerability dict."""
        vuln = {
            "id": vuln_id,
            "severity": severity,
            "package": {"name": "pkg", "version": "1.0.0"},
        }
        if excluded:
            vuln["excluded"] = excluded
        return vuln

    def test_allowlist_returns_only_matching(self):
        """Only vulns with IDs in the allowlist are returned."""
        vulns = [
            self._make_vuln("CVE-1", "CRITICAL"),
            self._make_vuln("CVE-2", "HIGH"),
            self._make_vuln("CVE-3", "MEDIUM"),
            self._make_vuln("CVE-4", "HIGH"),
            self._make_vuln("CVE-5", "LOW"),
        ]
        allowed = {"CVE-2", "CVE-4"}
        result = filter_vulnerabilities(vulns, allowed_cve_ids=allowed)

        for v in result:
            self.assertIn(v["id"], allowed)

    def test_allowlist_drops_none_that_match(self):
        """All non-excluded vulns in the allowlist are returned."""
        vulns = [
            self._make_vuln("CVE-1", "CRITICAL"),
            self._make_vuln("CVE-2", "HIGH"),
            self._make_vuln("CVE-3", "MEDIUM"),
            self._make_vuln("CVE-4", "HIGH"),
            self._make_vuln("CVE-5", "LOW"),
        ]
        allowed = {"CVE-2", "CVE-4"}
        result = filter_vulnerabilities(vulns, allowed_cve_ids=allowed)

        result_ids = {v["id"] for v in result}
        self.assertEqual(result_ids, {"CVE-2", "CVE-4"})

    def test_allowlist_with_multiple_ids(self):
        """Multiple IDs in allowlist all pass through."""
        vulns = [
            self._make_vuln("CVE-1", "CRITICAL"),
            self._make_vuln("CVE-2", "HIGH"),
            self._make_vuln("CVE-3", "MEDIUM"),
            self._make_vuln("CVE-4", "LOW"),
        ]
        allowed = {"CVE-1", "CVE-4"}
        result = filter_vulnerabilities(
            vulns, allowed_cve_ids=allowed, include_excluded=True,
        )

        result_ids = {v["id"] for v in result}
        self.assertEqual(result_ids, {"CVE-1", "CVE-4"})

    def test_allowlist_respects_exclusion(self):
        """Excluded vulns in the allowlist are dropped when include_excluded=False."""
        vulns = [
            self._make_vuln("CVE-1", "HIGH"),
            self._make_vuln("CVE-2", "HIGH", excluded="AT_PROJECT"),
            self._make_vuln("CVE-3", "HIGH"),
        ]
        allowed = {"CVE-1", "CVE-2", "CVE-3"}
        result = filter_vulnerabilities(vulns, allowed_cve_ids=allowed)

        # CVE-2 is excluded, so only CVE-1 and CVE-3 should be returned
        result_ids = {v["id"] for v in result}
        self.assertEqual(result_ids, {"CVE-1", "CVE-3"})

    def test_allowlist_all_ids_returns_all_non_excluded(self):
        """Allowlist containing all IDs returns all non-excluded vulns."""
        vulns = [
            self._make_vuln("CVE-1", "CRITICAL"),
            self._make_vuln("CVE-2", "HIGH"),
            self._make_vuln("CVE-3", "MEDIUM"),
            self._make_vuln("CVE-4", "LOW"),
        ]
        all_ids = {"CVE-1", "CVE-2", "CVE-3", "CVE-4"}
        result = filter_vulnerabilities(vulns, allowed_cve_ids=all_ids)

        self.assertEqual(len(result), 4)

    def test_allowlist_none_returns_all_non_excluded(self):
        """When allowed_cve_ids is None, all non-excluded vulns are returned."""
        vulns = [
            self._make_vuln("CVE-1", "CRITICAL"),
            self._make_vuln("CVE-2", "HIGH"),
            self._make_vuln("CVE-3", "MEDIUM"),
            self._make_vuln("CVE-4", "LOW"),
        ]
        result = filter_vulnerabilities(vulns, allowed_cve_ids=None)

        self.assertEqual(len(result), 4)


class TestProperty3ExclusionFilterCorrectness(unittest.TestCase):
    """**Validates: Requirements 3.3, 3.4**

    Property 3: Exclusion filter correctness.

    When include_excluded is False, filter_vulnerabilities SHALL return no
    vulnerability with a truthy excluded field; when include_excluded is True,
    filter_vulnerabilities SHALL not remove any vulnerability based on its
    excluded field.
    """

    def _make_vuln(self, vuln_id, severity="HIGH", excluded=None):
        """Helper to create a vulnerability dict."""
        vuln = {
            "id": vuln_id,
            "severity": severity,
            "package": {"name": "pkg", "version": "1.0.0"},
        }
        if excluded:
            vuln["excluded"] = excluded
        return vuln

    def test_include_excluded_false_no_excluded_in_result(self):
        """With include_excluded=False, no returned vuln has a truthy excluded field."""
        vulns = [
            self._make_vuln("CVE-1"),
            self._make_vuln("CVE-2", excluded="AT_PROJECT"),
            self._make_vuln("CVE-3"),
            self._make_vuln("CVE-4", excluded="AT_RULE"),
            self._make_vuln("CVE-5"),
        ]
        result = filter_vulnerabilities(vulns, include_excluded=False)

        for v in result:
            self.assertFalse(
                v.get("excluded"),
                f"Vuln {v['id']} has excluded={v.get('excluded')} but should not be in result",
            )

    def test_include_excluded_false_keeps_non_excluded(self):
        """With include_excluded=False, all non-excluded vulns are retained."""
        vulns = [
            self._make_vuln("CVE-1"),
            self._make_vuln("CVE-2", excluded="AT_PROJECT"),
            self._make_vuln("CVE-3"),
            self._make_vuln("CVE-4", excluded="AT_RULE"),
            self._make_vuln("CVE-5"),
        ]
        result = filter_vulnerabilities(vulns, include_excluded=False)

        result_ids = {v["id"] for v in result}
        self.assertEqual(result_ids, {"CVE-1", "CVE-3", "CVE-5"})

    def test_include_excluded_true_retains_all(self):
        """With include_excluded=True, no vuln is removed based on excluded field."""
        vulns = [
            self._make_vuln("CVE-1"),
            self._make_vuln("CVE-2", excluded="AT_PROJECT"),
            self._make_vuln("CVE-3"),
            self._make_vuln("CVE-4", excluded="AT_RULE"),
            self._make_vuln("CVE-5"),
        ]
        result = filter_vulnerabilities(vulns, include_excluded=True)

        self.assertEqual(len(result), len(vulns))
        result_ids = {v["id"] for v in result}
        expected_ids = {v["id"] for v in vulns}
        self.assertEqual(result_ids, expected_ids)

    def test_include_excluded_true_with_allowlist(self):
        """With include_excluded=True and allowlist, excluded vulns in allowlist are kept."""
        vulns = [
            self._make_vuln("CVE-1", severity="HIGH"),
            self._make_vuln("CVE-2", severity="HIGH", excluded="AT_PROJECT"),
            self._make_vuln("CVE-3", severity="LOW"),
            self._make_vuln("CVE-4", severity="LOW", excluded="AT_RULE"),
        ]
        allowed = {"CVE-1", "CVE-2"}
        result = filter_vulnerabilities(
            vulns, allowed_cve_ids=allowed, include_excluded=True,
        )

        result_ids = {v["id"] for v in result}
        self.assertEqual(result_ids, {"CVE-1", "CVE-2"})

    def test_all_excluded_with_include_false_returns_empty(self):
        """When all vulns are excluded and include_excluded=False, result is empty."""
        vulns = [
            self._make_vuln("CVE-1", excluded="AT_PROJECT"),
            self._make_vuln("CVE-2", excluded="AT_RULE"),
        ]
        result = filter_vulnerabilities(vulns, include_excluded=False)

        self.assertEqual(result, [])

    def test_all_excluded_with_include_true_returns_all(self):
        """When all vulns are excluded and include_excluded=True, all are returned."""
        vulns = [
            self._make_vuln("CVE-1", excluded="AT_PROJECT"),
            self._make_vuln("CVE-2", excluded="AT_RULE"),
        ]
        result = filter_vulnerabilities(vulns, include_excluded=True)

        self.assertEqual(len(result), 2)

    def test_excluded_field_none_treated_as_non_excluded(self):
        """A vuln with excluded=None is treated as non-excluded."""
        vulns = [
            {"id": "CVE-1", "severity": "HIGH", "excluded": None,
             "package": {"name": "pkg", "version": "1.0.0"}},
        ]
        result = filter_vulnerabilities(vulns, include_excluded=False)

        self.assertEqual(len(result), 1)

    def test_excluded_field_missing_treated_as_non_excluded(self):
        """A vuln without an excluded field is treated as non-excluded."""
        vulns = [
            {"id": "CVE-1", "severity": "HIGH",
             "package": {"name": "pkg", "version": "1.0.0"}},
        ]
        result = filter_vulnerabilities(vulns, include_excluded=False)

        self.assertEqual(len(result), 1)


class TestProperty4SeveritySummaryAccuracy(unittest.TestCase):
    """**Validates: Requirements 3.5**

    Property 4: Severity summary accuracy.

    For any list of vulnerability dicts, build_summary SHALL return a
    dictionary where each key is a severity level present in the input and
    each value equals the count of vulnerabilities with that severity, and
    the sum of all values SHALL equal the length of the input list.
    """

    def _make_vuln(self, vuln_id, severity):
        return {
            "id": vuln_id,
            "severity": severity,
            "package": {"name": "pkg", "version": "1.0.0"},
        }

    def test_summary_counts_match_actual_counts(self):
        """Each severity count in summary matches the actual count in the input."""
        vulns = [
            self._make_vuln("CVE-1", "CRITICAL"),
            self._make_vuln("CVE-2", "HIGH"),
            self._make_vuln("CVE-3", "HIGH"),
            self._make_vuln("CVE-4", "MEDIUM"),
            self._make_vuln("CVE-5", "LOW"),
            self._make_vuln("CVE-6", "LOW"),
            self._make_vuln("CVE-7", "LOW"),
        ]
        summary = build_summary(vulns)

        self.assertEqual(summary["CRITICAL"], 1)
        self.assertEqual(summary["HIGH"], 2)
        self.assertEqual(summary["MEDIUM"], 1)
        self.assertEqual(summary["LOW"], 3)

    def test_summary_sum_equals_input_length(self):
        """The sum of all summary values equals the length of the input list."""
        vulns = [
            self._make_vuln("CVE-1", "CRITICAL"),
            self._make_vuln("CVE-2", "HIGH"),
            self._make_vuln("CVE-3", "HIGH"),
            self._make_vuln("CVE-4", "MEDIUM"),
            self._make_vuln("CVE-5", "LOW"),
            self._make_vuln("CVE-6", "LOW"),
            self._make_vuln("CVE-7", "LOW"),
        ]
        summary = build_summary(vulns)

        self.assertEqual(sum(summary.values()), len(vulns))

    def test_summary_keys_match_input_severities(self):
        """Summary keys are exactly the set of severities present in the input."""
        vulns = [
            self._make_vuln("CVE-1", "CRITICAL"),
            self._make_vuln("CVE-2", "HIGH"),
            self._make_vuln("CVE-3", "MEDIUM"),
        ]
        summary = build_summary(vulns)

        expected_keys = {"CRITICAL", "HIGH", "MEDIUM"}
        self.assertEqual(set(summary.keys()), expected_keys)

    def test_summary_single_severity_all_same(self):
        """When all vulns have the same severity, summary has one key with count = len(input)."""
        vulns = [
            self._make_vuln("CVE-1", "HIGH"),
            self._make_vuln("CVE-2", "HIGH"),
            self._make_vuln("CVE-3", "HIGH"),
        ]
        summary = build_summary(vulns)

        self.assertEqual(summary, {"HIGH": 3})
        self.assertEqual(sum(summary.values()), len(vulns))

    def test_summary_empty_input(self):
        """Empty input produces empty summary with sum of values = 0."""
        summary = build_summary([])

        self.assertEqual(summary, {})
        self.assertEqual(sum(summary.values()), 0)

    def test_summary_after_filtering_matches_filtered_list(self):
        """Summary built from filtered results matches the filtered list, not the original."""
        vulns = [
            self._make_vuln("CVE-1", "CRITICAL"),
            self._make_vuln("CVE-2", "HIGH"),
            self._make_vuln("CVE-3", "MEDIUM"),
            self._make_vuln("CVE-4", "LOW"),
        ]
        allowed = {"CVE-1", "CVE-2"}
        filtered = filter_vulnerabilities(vulns, allowed_cve_ids=allowed)
        summary = build_summary(filtered)

        self.assertEqual(summary, {"CRITICAL": 1, "HIGH": 1})
        self.assertEqual(sum(summary.values()), len(filtered))

    def test_summary_with_mixed_excluded_vulns(self):
        """Summary counts from include_excluded=True include all vulns."""
        vulns = [
            {"id": "CVE-1", "severity": "HIGH",
             "package": {"name": "pkg", "version": "1.0.0"}},
            {"id": "CVE-2", "severity": "HIGH", "excluded": "AT_PROJECT",
             "package": {"name": "pkg", "version": "1.0.0"}},
            {"id": "CVE-3", "severity": "LOW",
             "package": {"name": "pkg", "version": "1.0.0"}},
        ]
        filtered = filter_vulnerabilities(vulns, include_excluded=True)
        summary = build_summary(filtered)

        self.assertEqual(summary, {"HIGH": 2, "LOW": 1})
        self.assertEqual(sum(summary.values()), len(vulns))


if __name__ == '__main__':
    unittest.main()
