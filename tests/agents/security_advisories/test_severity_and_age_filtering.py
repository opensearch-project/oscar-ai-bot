# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for severity filtering and age threshold filtering in vulnerabilities_handler.

These tests cover _parse_severity, _parse_age_days helper functions, and the
end-to-end integration of severity and age_days parameters through
handle_query_vulnerabilities.

Note: age_days now filters CVEs via the advisories index. When age_days is
provided, only CVEs whose advisory was published at least that many days ago
are retained in results.

**Validates Acceptance Criteria 3: Query results are returned and processed
accurately for a given release version, severity, repository and age threshold.**
"""

import importlib
import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

# Path to the real vulnerabilities_handler module
_LAMBDA_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'agents', 'security_advisories', 'lambda',
)


def _make_mock_dsl_query_builder():
    """Create a mock dsl_query_builder module."""
    mock_mod = MagicMock()
    mock_mod.query_vulnerabilities = MagicMock(return_value={'hits': {'hits': []}})
    mock_mod.resolve_version_tag = MagicMock(side_effect=lambda v: v)
    mock_mod.query_advisories = MagicMock(return_value=(set(), False))
    mock_mod._DEFAULT_QUERY_SIZE = 1000
    return mock_mod


def _load_vulnerabilities_handler(mock_dsl=None):
    """Import vulnerabilities_handler with mocked dependencies."""
    if mock_dsl is None:
        mock_dsl = _make_mock_dsl_query_builder()

    if _LAMBDA_PATH not in sys.path:
        sys.path.insert(0, _LAMBDA_PATH)

    with patch.dict('sys.modules', {
        'dsl_query_builder': mock_dsl,
    }):
        spec = importlib.util.spec_from_file_location(
            'sa_vulnerabilities_handler_sev_age',
            os.path.join(_LAMBDA_PATH, 'vulnerabilities_handler.py'),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod, mock_dsl


# ---------------------------------------------------------------------------
# Sample data helpers
# ---------------------------------------------------------------------------

def _make_hit(project_name, tag, vulns, scan_timestamp=None):
    """Build a scan document hit for testing."""
    if scan_timestamp is None:
        scan_timestamp = datetime.now(timezone.utc).isoformat()
    return {
        '_index': 'scans',
        '_source': {
            'project': {'name': project_name, 'tag': tag},
            'vulnerabilities': vulns,
            'count': {'severe': len([v for v in vulns if v.get('severity') in ('CRITICAL', 'HIGH')]),
                      'minor': len([v for v in vulns if v.get('severity') in ('MEDIUM', 'LOW')])},
            'timestamp': {'scan': scan_timestamp},
        },
    }


def _make_vuln(vuln_id, severity, excluded=None):
    """Build a vulnerability dict for testing."""
    vuln = {
        'id': vuln_id,
        'severity': severity,
        'package': {'name': 'test-pkg', 'version': '1.0.0'},
    }
    if excluded:
        vuln['excluded'] = excluded
    return vuln


# ---------------------------------------------------------------------------
# _parse_severity tests
# ---------------------------------------------------------------------------


class TestParseSeverity:
    """Tests for _parse_severity helper function."""

    def test_none_returns_none(self):
        mod, _ = _load_vulnerabilities_handler()
        assert mod._parse_severity(None) is None

    def test_empty_string_returns_none(self):
        mod, _ = _load_vulnerabilities_handler()
        assert mod._parse_severity('') is None

    def test_single_severity(self):
        mod, _ = _load_vulnerabilities_handler()
        assert mod._parse_severity('CRITICAL') == {'CRITICAL'}

    def test_multiple_severities(self):
        mod, _ = _load_vulnerabilities_handler()
        assert mod._parse_severity('CRITICAL,HIGH') == {'CRITICAL', 'HIGH'}

    def test_normalises_to_uppercase(self):
        mod, _ = _load_vulnerabilities_handler()
        assert mod._parse_severity('critical,high') == {'CRITICAL', 'HIGH'}

    def test_strips_whitespace(self):
        mod, _ = _load_vulnerabilities_handler()
        assert mod._parse_severity(' CRITICAL , HIGH ') == {'CRITICAL', 'HIGH'}

    def test_ignores_empty_segments(self):
        mod, _ = _load_vulnerabilities_handler()
        result = mod._parse_severity('CRITICAL,,HIGH,')
        assert result == {'CRITICAL', 'HIGH'}

    def test_all_four_severities(self):
        mod, _ = _load_vulnerabilities_handler()
        result = mod._parse_severity('CRITICAL,HIGH,MEDIUM,LOW')
        assert result == {'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'}

    def test_whitespace_only_returns_empty_set(self):
        """Whitespace-only input produces an empty set (falsy, no filtering)."""
        mod, _ = _load_vulnerabilities_handler()
        result = mod._parse_severity('   ')
        assert result == set()
        assert not result  # empty set is falsy — no filtering applied


# ---------------------------------------------------------------------------
# _parse_age_days tests
# ---------------------------------------------------------------------------


class TestParseAgeDays:
    """Tests for _parse_age_days helper function."""

    def test_none_returns_none(self):
        mod, _ = _load_vulnerabilities_handler()
        assert mod._parse_age_days(None) is None

    def test_empty_string_returns_none(self):
        mod, _ = _load_vulnerabilities_handler()
        assert mod._parse_age_days('') is None

    def test_valid_positive_integer(self):
        mod, _ = _load_vulnerabilities_handler()
        assert mod._parse_age_days('30') == 30

    def test_one_day(self):
        mod, _ = _load_vulnerabilities_handler()
        assert mod._parse_age_days('1') == 1

    def test_zero_returns_none(self):
        mod, _ = _load_vulnerabilities_handler()
        assert mod._parse_age_days('0') is None

    def test_negative_returns_none(self):
        mod, _ = _load_vulnerabilities_handler()
        assert mod._parse_age_days('-5') is None

    def test_non_numeric_returns_none(self):
        mod, _ = _load_vulnerabilities_handler()
        assert mod._parse_age_days('abc') is None

    def test_float_string_returns_none(self):
        mod, _ = _load_vulnerabilities_handler()
        assert mod._parse_age_days('30.5') is None

    def test_large_value(self):
        mod, _ = _load_vulnerabilities_handler()
        assert mod._parse_age_days('365') == 365


# ---------------------------------------------------------------------------
# Severity filtering integration in handle_query_vulnerabilities
# ---------------------------------------------------------------------------


class TestSeverityFilteringIntegration:
    """Verify severity param is wired through handle_query_vulnerabilities."""

    def test_severity_filters_vulnerabilities(self):
        """Only CRITICAL vulns should remain when severity=CRITICAL."""
        mock_dsl = _make_mock_dsl_query_builder()
        hit = _make_hit('OpenSearch', '2.19.6', [
            _make_vuln('CVE-001', 'CRITICAL'),
            _make_vuln('CVE-002', 'HIGH'),
            _make_vuln('CVE-003', 'MEDIUM'),
        ])
        mock_dsl.query_vulnerabilities.return_value = {'hits': {'total': {'value': 1}, 'hits': [hit]}}
        mock_dsl.query_advisories.return_value = ({'CVE-001'}, False)
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'version': '2.19', 'severity': 'CRITICAL', '_access_tier': 'privileged'}, 'test-sev-001',
        )

        assert result['status'] == 'success'
        entry = result['results'][0]
        assert entry['filtered_count'] == 1
        assert entry['filtered_vulnerabilities'][0]['id'] == 'CVE-001'

    def test_multiple_severity_levels(self):
        """CRITICAL,HIGH should return both severity levels."""
        mock_dsl = _make_mock_dsl_query_builder()
        hit = _make_hit('OpenSearch', '2.19.6', [
            _make_vuln('CVE-001', 'CRITICAL'),
            _make_vuln('CVE-002', 'HIGH'),
            _make_vuln('CVE-003', 'MEDIUM'),
            _make_vuln('CVE-004', 'LOW'),
        ])
        mock_dsl.query_vulnerabilities.return_value = {'hits': {'total': {'value': 1}, 'hits': [hit]}}
        mock_dsl.query_advisories.return_value = ({'CVE-001', 'CVE-002'}, False)
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'version': '2.19', 'severity': 'CRITICAL,HIGH', '_access_tier': 'privileged'}, 'test-sev-002',
        )

        entry = result['results'][0]
        assert entry['filtered_count'] == 2
        ids = {v['id'] for v in entry['filtered_vulnerabilities']}
        assert ids == {'CVE-001', 'CVE-002'}

    def test_no_severity_param_returns_all_non_excluded(self):
        """Without severity param, all non-excluded vulns are returned."""
        mock_dsl = _make_mock_dsl_query_builder()
        hit = _make_hit('OpenSearch', '2.19.6', [
            _make_vuln('CVE-001', 'CRITICAL'),
            _make_vuln('CVE-002', 'HIGH'),
            _make_vuln('CVE-003', 'MEDIUM'),
            _make_vuln('CVE-004', 'LOW', excluded='AT_PROJECT'),
        ])
        mock_dsl.query_vulnerabilities.return_value = {'hits': {'total': {'value': 1}, 'hits': [hit]}}
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'version': '2.19', '_access_tier': 'privileged'}, 'test-sev-003',
        )

        entry = result['results'][0]
        assert entry['filtered_count'] == 3  # CVE-004 excluded

    def test_severity_summary_reflects_filter(self):
        """Severity summary should only count filtered vulnerabilities."""
        mock_dsl = _make_mock_dsl_query_builder()
        hit = _make_hit('OpenSearch', '2.19.6', [
            _make_vuln('CVE-001', 'CRITICAL'),
            _make_vuln('CVE-002', 'CRITICAL'),
            _make_vuln('CVE-003', 'HIGH'),
            _make_vuln('CVE-004', 'MEDIUM'),
        ])
        mock_dsl.query_vulnerabilities.return_value = {'hits': {'total': {'value': 1}, 'hits': [hit]}}
        mock_dsl.query_advisories.return_value = ({'CVE-001', 'CVE-002'}, False)
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'version': '2.19', 'severity': 'CRITICAL', '_access_tier': 'privileged'}, 'test-sev-004',
        )

        entry = result['results'][0]
        assert entry['severity_summary'] == {'CRITICAL': 2}

    def test_severity_no_match_returns_empty_filtered(self):
        """If no vulns match the severity filter, filtered list is empty."""
        mock_dsl = _make_mock_dsl_query_builder()
        hit = _make_hit('OpenSearch', '2.19.6', [
            _make_vuln('CVE-001', 'MEDIUM'),
            _make_vuln('CVE-002', 'LOW'),
        ])
        mock_dsl.query_vulnerabilities.return_value = {'hits': {'total': {'value': 1}, 'hits': [hit]}}
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'version': '2.19', 'severity': 'CRITICAL', '_access_tier': 'privileged'}, 'test-sev-005',
        )

        entry = result['results'][0]
        assert entry['filtered_count'] == 0
        assert entry['filtered_vulnerabilities'] == []


# ---------------------------------------------------------------------------
# Age threshold — age_days filters CVEs via advisories index
# ---------------------------------------------------------------------------


class TestAgeThresholdIntegration:
    """Verify age_days filters CVEs via the advisories index and affects neglected URL."""

    def test_age_days_filters_cves_via_advisories(self):
        """Only CVEs returned by query_advisories are retained."""
        mock_dsl = _make_mock_dsl_query_builder()
        old_ts = '2020-01-01T00:00:00Z'
        hit = _make_hit('OpenSearch', '2.19.6', [
            _make_vuln('CVE-001', 'HIGH'),
            _make_vuln('CVE-002', 'MEDIUM'),
        ], scan_timestamp=old_ts)
        mock_dsl.query_vulnerabilities.return_value = {'hits': {'total': {'value': 1}, 'hits': [hit]}}
        # Only CVE-001 is old enough
        mock_dsl.query_advisories.return_value = ({'CVE-001'}, False)
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'version': '2.19', 'age_days': '30', '_access_tier': 'privileged'}, 'test-age-001',
        )

        assert result['result_count'] == 1
        assert result['results'][0]['filtered_count'] == 1
        assert result['results'][0]['filtered_vulnerabilities'][0]['id'] == 'CVE-001'

    def test_age_days_no_old_cves_returns_empty_filtered(self):
        """When no CVEs are old enough, filtered_count is 0."""
        mock_dsl = _make_mock_dsl_query_builder()
        hit = _make_hit('OpenSearch', '2.19.6', [
            _make_vuln('CVE-001', 'HIGH'),
        ])
        mock_dsl.query_vulnerabilities.return_value = {'hits': {'total': {'value': 1}, 'hits': [hit]}}
        mock_dsl.query_advisories.return_value = (set(), False)
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'version': '2.19', 'age_days': '30', '_access_tier': 'privileged'}, 'test-age-004',
        )

        assert result['result_count'] == 1
        assert result['results'][0]['filtered_count'] == 0

    def test_age_days_reflected_in_neglected_url(self):
        """age_days should map to the age param in the neglected URL."""
        mock_dsl = _make_mock_dsl_query_builder()
        hit = _make_hit('OpenSearch', '2.19.6', [
            _make_vuln('CVE-001', 'HIGH'),
        ])
        mock_dsl.query_vulnerabilities.return_value = {'hits': {'total': {'value': 1}, 'hits': [hit]}}
        mock_dsl.query_advisories.return_value = ({'CVE-001'}, False)
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'version': '2.19', 'age_days': '30', '_access_tier': 'privileged'}, 'test-age-002',
        )

        assert 'age=30d' in result['neglected_page_url']

    def test_invalid_age_days_still_returns_results(self):
        """Invalid age_days should not trigger age filtering."""
        mock_dsl = _make_mock_dsl_query_builder()
        old_ts = '2020-01-01T00:00:00Z'
        hit = _make_hit('OpenSearch', '2.19.6', [
            _make_vuln('CVE-001', 'HIGH'),
        ], scan_timestamp=old_ts)
        mock_dsl.query_vulnerabilities.return_value = {'hits': {'total': {'value': 1}, 'hits': [hit]}}
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'version': '2.19', 'age_days': 'abc', '_access_tier': 'privileged'}, 'test-age-003',
        )

        # Invalid age_days is parsed to None, so no age filtering happens
        assert result['result_count'] == 1
        assert result['results'][0]['filtered_count'] == 1


# ---------------------------------------------------------------------------
# Combined severity + age — severity filters vulns, age only affects URL
# ---------------------------------------------------------------------------


class TestCombinedSeverityAndAge:
    """Verify severity filters vulns and age_days filters via advisories index."""

    def test_severity_and_age_combined_filtering(self):
        """Severity filters CVEs within hits; age_days filters via advisories."""
        mock_dsl = _make_mock_dsl_query_builder()
        recent_ts = datetime.now(timezone.utc).isoformat()
        old_ts = '2020-01-01T00:00:00Z'

        hit_recent = _make_hit('OpenSearch', '2.19.6', [
            _make_vuln('CVE-001', 'CRITICAL'),
            _make_vuln('CVE-002', 'HIGH'),
            _make_vuln('CVE-003', 'MEDIUM'),
        ], scan_timestamp=recent_ts)
        hit_old = _make_hit('Dashboards', '2.19.6', [
            _make_vuln('CVE-004', 'CRITICAL'),
        ], scan_timestamp=old_ts)

        mock_dsl.query_vulnerabilities.return_value = {
            'hits': {'total': {'value': 2}, 'hits': [hit_recent, hit_old]},
        }
        # Both CRITICAL CVEs are old enough
        mock_dsl.query_advisories.return_value = ({'CVE-001', 'CVE-004'}, False)
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'version': '2.19', 'severity': 'CRITICAL', 'age_days': '30', '_access_tier': 'privileged'},
            'test-combo-001',
        )

        # Both hits are returned; severity + age filtering applied
        assert result['result_count'] == 2
        assert result['results'][0]['filtered_count'] == 1
        assert result['results'][0]['filtered_vulnerabilities'][0]['id'] == 'CVE-001'
        assert result['results'][1]['filtered_count'] == 1
        assert result['results'][1]['filtered_vulnerabilities'][0]['id'] == 'CVE-004'

    def test_age_filter_removes_young_cves_even_with_matching_severity(self):
        """CVEs matching severity but not age are excluded."""
        mock_dsl = _make_mock_dsl_query_builder()
        hit = _make_hit('OpenSearch', '2.19.6', [
            _make_vuln('CVE-001', 'CRITICAL'),
            _make_vuln('CVE-002', 'CRITICAL'),
        ])
        mock_dsl.query_vulnerabilities.return_value = {
            'hits': {'total': {'value': 1}, 'hits': [hit]},
        }
        # Only CVE-001 is old enough, CVE-002 is not
        mock_dsl.query_advisories.return_value = ({'CVE-001'}, False)
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'version': '2.19', 'severity': 'CRITICAL', 'age_days': '60', '_access_tier': 'privileged'},
            'test-combo-002',
        )

        assert result['results'][0]['filtered_count'] == 1
        assert result['results'][0]['filtered_vulnerabilities'][0]['id'] == 'CVE-001'


# ---------------------------------------------------------------------------
# Action group parameter definitions
# ---------------------------------------------------------------------------


class TestActionGroupNewParameters:
    """Verify severity and age_days are defined in the action group."""

    @pytest.fixture
    def agent(self):
        from agents.security_advisories import SecurityAdvisoriesAgent
        return SecurityAdvisoriesAgent()

    def _get_query_vulns_func(self, agent):
        groups = agent.get_action_groups(
            'arn:aws:lambda:us-east-1:123456789012:function:placeholder',
        )
        functions = groups[0].function_schema.functions
        return next(f for f in functions if f.name == 'query_vulnerabilities')

    def test_severity_param_exists(self, agent):
        func = self._get_query_vulns_func(agent)
        assert 'severity' in func.parameters

    def test_severity_param_is_optional(self, agent):
        func = self._get_query_vulns_func(agent)
        assert func.parameters['severity'].required is False

    def test_severity_param_is_string_type(self, agent):
        func = self._get_query_vulns_func(agent)
        assert func.parameters['severity'].type == 'string'

    def test_age_days_param_exists(self, agent):
        func = self._get_query_vulns_func(agent)
        assert 'age_days' in func.parameters

    def test_age_days_param_is_optional(self, agent):
        func = self._get_query_vulns_func(agent)
        assert func.parameters['age_days'].required is False

    def test_age_days_param_is_integer_type(self, agent):
        func = self._get_query_vulns_func(agent)
        assert func.parameters['age_days'].type == 'integer'


# ---------------------------------------------------------------------------
# Agent instruction documentation
# ---------------------------------------------------------------------------


class TestInstructionDocumentation:
    """Verify agent instructions document the new parameters."""

    @pytest.fixture
    def agent(self):
        from agents.security_advisories import SecurityAdvisoriesAgent
        return SecurityAdvisoriesAgent()

    def test_instruction_mentions_severity_param(self, agent):
        instruction = agent.get_agent_instruction()
        assert 'severity' in instruction.lower()

    def test_instruction_mentions_age_days_param(self, agent):
        instruction = agent.get_agent_instruction()
        assert 'age_days' in instruction

    def test_instruction_has_severity_example(self, agent):
        instruction = agent.get_agent_instruction()
        assert 'severity="CRITICAL"' in instruction or 'severity="HIGH"' in instruction

    def test_instruction_has_age_days_example(self, agent):
        instruction = agent.get_agent_instruction()
        assert 'age_days=30' in instruction or 'age_days=60' in instruction

    def test_instruction_documents_valid_severity_values(self, agent):
        instruction = agent.get_agent_instruction()
        assert 'CRITICAL' in instruction
        assert 'HIGH' in instruction
        assert 'MEDIUM' in instruction
        assert 'LOW' in instruction
