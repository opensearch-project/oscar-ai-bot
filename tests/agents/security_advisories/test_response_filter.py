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

    def test_filter_high_severity(self):
        """'Show me high severity CVEs' — severity={"HIGH"}."""
        result = filter_vulnerabilities(MOCK_VULNERABILITIES, severity={"HIGH"})

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "CVE-2024-002")

    def test_filter_high_severity_include_excluded(self):
        """'Show me all high severity CVEs including excluded'."""
        result = filter_vulnerabilities(
            MOCK_VULNERABILITIES, severity={"HIGH"}, include_excluded=True
        )

        self.assertEqual(len(result), 2)
        ids = {v["id"] for v in result}
        self.assertIn("CVE-2024-002", ids)
        self.assertIn("CVE-2024-003", ids)

    def test_filter_critical_severity(self):
        """'Show me critical CVEs'."""
        result = filter_vulnerabilities(MOCK_VULNERABILITIES, severity={"CRITICAL"})

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "CVE-2024-001")

    def test_filter_multiple_severities(self):
        """'Show me high and critical CVEs'."""
        result = filter_vulnerabilities(
            MOCK_VULNERABILITIES, severity={"HIGH", "CRITICAL"}
        )

        self.assertEqual(len(result), 2)
        ids = {v["id"] for v in result}
        self.assertIn("CVE-2024-001", ids)
        self.assertIn("CVE-2024-002", ids)

    def test_filter_low_severity(self):
        """'Show me low severity CVEs' — the only LOW one is excluded."""
        result = filter_vulnerabilities(MOCK_VULNERABILITIES, severity={"LOW"})

        self.assertEqual(len(result), 0)

    def test_filter_low_severity_include_excluded(self):
        """'Show me low severity CVEs including excluded'."""
        result = filter_vulnerabilities(
            MOCK_VULNERABILITIES, severity={"LOW"}, include_excluded=True
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "CVE-2024-005")

    def test_empty_vulnerabilities(self):
        """No vulnerabilities at all."""
        result = filter_vulnerabilities([])
        self.assertEqual(result, [])

    def test_severity_filter_no_match(self):
        """Filter for a severity that doesn't exist."""
        result = filter_vulnerabilities(MOCK_VULNERABILITIES, severity={"UNKNOWN"})
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
        filtered = filter_vulnerabilities(MOCK_VULNERABILITIES, severity={"CRITICAL"})
        summary = build_summary(filtered)

        self.assertEqual(summary, {"CRITICAL": 1})


class TestProperty2SeverityFilterCorrectness(unittest.TestCase):
    """**Validates: Requirements 3.2**

    Property 2: Severity filter returns only matching severities and drops
    none that match.

    For any list of vulnerability dicts and any non-empty subset of severity
    levels, filter_vulnerabilities with that severity set SHALL return only
    vulnerabilities whose severity is in the filter set, and SHALL return all
    vulnerabilities from the input whose severity is in the filter set (no
    false drops).
    """

    def _make_vuln(self, vuln_id, severity, excluded=None):
        """Helper to create a vulnerability dict."""
        vuln = {
            "id": vuln_id,
            "severity": severity,
            "package": {"name": "pkg", "version": "1.0.0"},
        }
        if excluded:
            vuln["excluded"] = excluded
        return vuln

    def test_single_severity_returns_only_matching(self):
        """Only vulns with the requested severity are returned."""
        vulns = [
            self._make_vuln("CVE-1", "CRITICAL"),
            self._make_vuln("CVE-2", "HIGH"),
            self._make_vuln("CVE-3", "MEDIUM"),
            self._make_vuln("CVE-4", "HIGH"),
            self._make_vuln("CVE-5", "LOW"),
        ]
        result = filter_vulnerabilities(vulns, severity={"HIGH"})

        # All returned vulns must have severity HIGH
        for v in result:
            self.assertEqual(v["severity"], "HIGH")

    def test_single_severity_drops_none_that_match(self):
        """All non-excluded vulns matching the severity are returned."""
        vulns = [
            self._make_vuln("CVE-1", "CRITICAL"),
            self._make_vuln("CVE-2", "HIGH"),
            self._make_vuln("CVE-3", "MEDIUM"),
            self._make_vuln("CVE-4", "HIGH"),
            self._make_vuln("CVE-5", "LOW"),
        ]
        result = filter_vulnerabilities(vulns, severity={"HIGH"})

        result_ids = {v["id"] for v in result}
        self.assertEqual(result_ids, {"CVE-2", "CVE-4"})

    def test_multiple_severities_returns_only_matching(self):
        """Only vulns with one of the requested severities are returned."""
        vulns = [
            self._make_vuln("CVE-1", "CRITICAL"),
            self._make_vuln("CVE-2", "HIGH"),
            self._make_vuln("CVE-3", "MEDIUM"),
            self._make_vuln("CVE-4", "LOW"),
        ]
        result = filter_vulnerabilities(
            vulns, severity={"CRITICAL", "LOW"}, include_excluded=True
        )

        severities = {v["severity"] for v in result}
        self.assertTrue(severities.issubset({"CRITICAL", "LOW"}))

    def test_multiple_severities_drops_none_that_match(self):
        """All non-excluded vulns matching any of the severities are returned."""
        vulns = [
            self._make_vuln("CVE-1", "CRITICAL"),
            self._make_vuln("CVE-2", "HIGH"),
            self._make_vuln("CVE-3", "MEDIUM"),
            self._make_vuln("CVE-4", "LOW"),
        ]
        result = filter_vulnerabilities(
            vulns, severity={"CRITICAL", "LOW"}, include_excluded=True
        )

        result_ids = {v["id"] for v in result}
        self.assertEqual(result_ids, {"CVE-1", "CVE-4"})

    def test_severity_filter_with_excluded_vulns(self):
        """Excluded vulns matching severity are dropped when include_excluded=False."""
        vulns = [
            self._make_vuln("CVE-1", "HIGH"),
            self._make_vuln("CVE-2", "HIGH", excluded="AT_PROJECT"),
            self._make_vuln("CVE-3", "HIGH"),
        ]
        result = filter_vulnerabilities(vulns, severity={"HIGH"})

        # CVE-2 is excluded, so only CVE-1 and CVE-3 should be returned
        result_ids = {v["id"] for v in result}
        self.assertEqual(result_ids, {"CVE-1", "CVE-3"})

    def test_severity_filter_with_all_severities(self):
        """Filtering with all four severity levels returns all non-excluded vulns."""
        vulns = [
            self._make_vuln("CVE-1", "CRITICAL"),
            self._make_vuln("CVE-2", "HIGH"),
            self._make_vuln("CVE-3", "MEDIUM"),
            self._make_vuln("CVE-4", "LOW"),
        ]
        all_severities = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
        result = filter_vulnerabilities(vulns, severity=all_severities)

        self.assertEqual(len(result), 4)

    def test_severity_none_returns_all_non_excluded(self):
        """When severity is None, all non-excluded vulns are returned regardless of severity."""
        vulns = [
            self._make_vuln("CVE-1", "CRITICAL"),
            self._make_vuln("CVE-2", "HIGH"),
            self._make_vuln("CVE-3", "MEDIUM"),
            self._make_vuln("CVE-4", "LOW"),
        ]
        result = filter_vulnerabilities(vulns, severity=None)

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

    def test_include_excluded_true_with_severity_filter(self):
        """With include_excluded=True and severity filter, excluded vulns matching severity are kept."""
        vulns = [
            self._make_vuln("CVE-1", severity="HIGH"),
            self._make_vuln("CVE-2", severity="HIGH", excluded="AT_PROJECT"),
            self._make_vuln("CVE-3", severity="LOW"),
            self._make_vuln("CVE-4", severity="LOW", excluded="AT_RULE"),
        ]
        result = filter_vulnerabilities(
            vulns, severity={"HIGH"}, include_excluded=True
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
        filtered = filter_vulnerabilities(vulns, severity={"CRITICAL", "HIGH"})
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
