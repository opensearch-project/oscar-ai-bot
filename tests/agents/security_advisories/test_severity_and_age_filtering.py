# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for severity filtering and age threshold filtering in vulnerabilities_handler.

These tests cover the new _parse_severity, _parse_age_days, and _is_within_age
helper functions, as well as the end-to-end integration of severity and age_days
parameters through handle_query_vulnerabilities.

**Validates Acceptance Criteria 3: Query results are returned and processed
accurately for a given release version, severity, repository and age threshold.**
"""

import importlib
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

# Path to the real vulnerabilities_handler module
_LAMBDA_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'agents', 'security_advisories', 'lambda',
)


def _make_mock_config():
    """Create a mock config module with required attributes."""
    mock_config = MagicMock()
    mock_config.agentic_pipeline = 'oscar-agentic-pipeline'
    mock_config_module = MagicMock()
    mock_config_module.config = mock_config
    return mock_config_module


def _make_mock_agentic_search():
    """Create a mock agentic_search module."""
    mock_mod = MagicMock()
    mock_mod.enhance_query = MagicMock(side_effect=lambda q, **kw: q)
    mock_mod.agentic_search = MagicMock(return_value={'hits': {'hits': []}})
    mock_mod.AgenticSearchError = type('AgenticSearchError', (Exception,), {
        '__init__': lambda self, msg, status_code=None: (
            super(type(self), self).__init__(msg),
            setattr(self, 'status_code', status_code),
        )[-1],
    })
    return mock_mod


def _load_vulnerabilities_handler(mock_config=None, mock_agentic=None):
    """Import vulnerabilities_handler with mocked dependencies."""
    if mock_config is None:
        mock_config = _make_mock_config()
    if mock_agentic is None:
        mock_agentic = _make_mock_agentic_search()

    if _LAMBDA_PATH not in sys.path:
        sys.path.insert(0, _LAMBDA_PATH)

    with patch.dict('sys.modules', {
        'config': mock_config,
        'agentic_search': mock_agentic,
    }):
        spec = importlib.util.spec_from_file_location(
            'sa_vulnerabilities_handler_sev_age',
            os.path.join(_LAMBDA_PATH, 'vulnerabilities_handler.py'),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod, mock_agentic


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
# _is_within_age tests
# ---------------------------------------------------------------------------


class TestIsWithinAge:
    """Tests for _is_within_age helper function."""

    def test_no_scan_timestamp_returns_true(self):
        mod, _ = _load_vulnerabilities_handler()
        assert mod._is_within_age({}, 30) is True

    def test_scan_timestamp_none_returns_true(self):
        mod, _ = _load_vulnerabilities_handler()
        assert mod._is_within_age({'scan': None}, 30) is True

    def test_recent_iso_timestamp_within_threshold(self):
        mod, _ = _load_vulnerabilities_handler()
        recent = datetime.now(timezone.utc).isoformat()
        assert mod._is_within_age({'scan': recent}, 30) is True

    def test_old_iso_timestamp_outside_threshold(self):
        mod, _ = _load_vulnerabilities_handler()
        old = '2020-01-01T00:00:00Z'
        assert mod._is_within_age({'scan': old}, 30) is False

    def test_recent_epoch_millis_within_threshold(self):
        mod, _ = _load_vulnerabilities_handler()
        recent_ms = int(time.time() * 1000)
        assert mod._is_within_age({'scan': recent_ms}, 30) is True

    def test_old_epoch_millis_outside_threshold(self):
        mod, _ = _load_vulnerabilities_handler()
        # 2020-01-01 in epoch millis
        old_ms = 1577836800000
        assert mod._is_within_age({'scan': old_ms}, 30) is False

    def test_iso_timestamp_with_z_suffix(self):
        mod, _ = _load_vulnerabilities_handler()
        recent = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        assert mod._is_within_age({'scan': recent}, 30) is True

    def test_iso_timestamp_without_timezone(self):
        mod, _ = _load_vulnerabilities_handler()
        recent = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
        assert mod._is_within_age({'scan': recent}, 30) is True

    def test_boundary_exactly_at_threshold(self):
        """A scan exactly age_days old should be included (days <= age_days)."""
        mod, _ = _load_vulnerabilities_handler()
        boundary = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        assert mod._is_within_age({'scan': boundary}, 30) is True

    def test_one_day_past_threshold(self):
        mod, _ = _load_vulnerabilities_handler()
        past = (datetime.now(timezone.utc) - timedelta(days=32)).isoformat()
        assert mod._is_within_age({'scan': past}, 30) is False

    def test_unparseable_timestamp_returns_true(self):
        """Unparseable timestamps should not filter out results."""
        mod, _ = _load_vulnerabilities_handler()
        assert mod._is_within_age({'scan': 'not-a-date'}, 30) is True

    def test_float_epoch_millis(self):
        mod, _ = _load_vulnerabilities_handler()
        recent_ms = time.time() * 1000
        assert mod._is_within_age({'scan': recent_ms}, 30) is True


# ---------------------------------------------------------------------------
# Severity filtering integration in handle_query_vulnerabilities
# ---------------------------------------------------------------------------


class TestSeverityFilteringIntegration:
    """Verify severity param is wired through handle_query_vulnerabilities."""

    def test_severity_filters_vulnerabilities(self):
        """Only CRITICAL vulns should remain when severity=CRITICAL."""
        mock_agentic = _make_mock_agentic_search()
        hit = _make_hit('OpenSearch', '2.19.6', [
            _make_vuln('CVE-001', 'CRITICAL'),
            _make_vuln('CVE-002', 'HIGH'),
            _make_vuln('CVE-003', 'MEDIUM'),
        ])
        mock_agentic.agentic_search.return_value = {'hits': {'hits': [hit]}}
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'severity': 'CRITICAL'}, 'test-sev-001',
        )

        assert result['status'] == 'success'
        entry = result['results'][0]
        assert entry['filtered_count'] == 1
        assert entry['filtered_vulnerabilities'][0]['id'] == 'CVE-001'

    def test_multiple_severity_levels(self):
        """CRITICAL,HIGH should return both severity levels."""
        mock_agentic = _make_mock_agentic_search()
        hit = _make_hit('OpenSearch', '2.19.6', [
            _make_vuln('CVE-001', 'CRITICAL'),
            _make_vuln('CVE-002', 'HIGH'),
            _make_vuln('CVE-003', 'MEDIUM'),
            _make_vuln('CVE-004', 'LOW'),
        ])
        mock_agentic.agentic_search.return_value = {'hits': {'hits': [hit]}}
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'severity': 'CRITICAL,HIGH'}, 'test-sev-002',
        )

        entry = result['results'][0]
        assert entry['filtered_count'] == 2
        ids = {v['id'] for v in entry['filtered_vulnerabilities']}
        assert ids == {'CVE-001', 'CVE-002'}

    def test_no_severity_param_returns_all_non_excluded(self):
        """Without severity param, all non-excluded vulns are returned."""
        mock_agentic = _make_mock_agentic_search()
        hit = _make_hit('OpenSearch', '2.19.6', [
            _make_vuln('CVE-001', 'CRITICAL'),
            _make_vuln('CVE-002', 'HIGH'),
            _make_vuln('CVE-003', 'MEDIUM'),
            _make_vuln('CVE-004', 'LOW', excluded='AT_PROJECT'),
        ])
        mock_agentic.agentic_search.return_value = {'hits': {'hits': [hit]}}
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs'}, 'test-sev-003',
        )

        entry = result['results'][0]
        assert entry['filtered_count'] == 3  # CVE-004 excluded

    def test_severity_summary_reflects_filter(self):
        """Severity summary should only count filtered vulnerabilities."""
        mock_agentic = _make_mock_agentic_search()
        hit = _make_hit('OpenSearch', '2.19.6', [
            _make_vuln('CVE-001', 'CRITICAL'),
            _make_vuln('CVE-002', 'CRITICAL'),
            _make_vuln('CVE-003', 'HIGH'),
            _make_vuln('CVE-004', 'MEDIUM'),
        ])
        mock_agentic.agentic_search.return_value = {'hits': {'hits': [hit]}}
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'severity': 'CRITICAL'}, 'test-sev-004',
        )

        entry = result['results'][0]
        assert entry['severity_summary'] == {'CRITICAL': 2}

    def test_severity_no_match_returns_empty_filtered(self):
        """If no vulns match the severity filter, filtered list is empty."""
        mock_agentic = _make_mock_agentic_search()
        hit = _make_hit('OpenSearch', '2.19.6', [
            _make_vuln('CVE-001', 'MEDIUM'),
            _make_vuln('CVE-002', 'LOW'),
        ])
        mock_agentic.agentic_search.return_value = {'hits': {'hits': [hit]}}
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'severity': 'CRITICAL'}, 'test-sev-005',
        )

        entry = result['results'][0]
        assert entry['filtered_count'] == 0
        assert entry['filtered_vulnerabilities'] == []


# ---------------------------------------------------------------------------
# Age threshold filtering integration in handle_query_vulnerabilities
# ---------------------------------------------------------------------------


class TestAgeThresholdFilteringIntegration:
    """Verify age_days param filters out old scan documents."""

    def test_recent_scan_included(self):
        """A scan from today should be included with age_days=30."""
        mock_agentic = _make_mock_agentic_search()
        recent_ts = datetime.now(timezone.utc).isoformat()
        hit = _make_hit('OpenSearch', '2.19.6', [
            _make_vuln('CVE-001', 'HIGH'),
        ], scan_timestamp=recent_ts)
        mock_agentic.agentic_search.return_value = {'hits': {'hits': [hit]}}
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'age_days': '30'}, 'test-age-001',
        )

        assert result['result_count'] == 1

    def test_old_scan_excluded(self):
        """A scan from 2020 should be excluded with age_days=30."""
        mock_agentic = _make_mock_agentic_search()
        old_ts = '2020-01-01T00:00:00Z'
        hit = _make_hit('OpenSearch', '2.19.6', [
            _make_vuln('CVE-001', 'HIGH'),
        ], scan_timestamp=old_ts)
        mock_agentic.agentic_search.return_value = {'hits': {'hits': [hit]}}
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'age_days': '30'}, 'test-age-002',
        )

        assert result['result_count'] == 0
        assert result['results'] == []

    def test_mixed_ages_filters_correctly(self):
        """Only recent scans should be included when age_days is set."""
        mock_agentic = _make_mock_agentic_search()
        recent_ts = datetime.now(timezone.utc).isoformat()
        old_ts = '2020-06-15T12:00:00Z'
        hit_recent = _make_hit('OpenSearch', '2.19.6', [
            _make_vuln('CVE-001', 'HIGH'),
        ], scan_timestamp=recent_ts)
        hit_old = _make_hit('OpenSearch Dashboards', '2.19.6', [
            _make_vuln('CVE-002', 'CRITICAL'),
        ], scan_timestamp=old_ts)
        mock_agentic.agentic_search.return_value = {
            'hits': {'hits': [hit_recent, hit_old]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'age_days': '30'}, 'test-age-003',
        )

        assert result['result_count'] == 1
        assert result['results'][0]['project']['name'] == 'OpenSearch'

    def test_no_age_days_includes_all(self):
        """Without age_days, all scans are included regardless of age."""
        mock_agentic = _make_mock_agentic_search()
        old_ts = '2020-01-01T00:00:00Z'
        hit = _make_hit('OpenSearch', '2.19.6', [
            _make_vuln('CVE-001', 'HIGH'),
        ], scan_timestamp=old_ts)
        mock_agentic.agentic_search.return_value = {'hits': {'hits': [hit]}}
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs'}, 'test-age-004',
        )

        assert result['result_count'] == 1

    def test_invalid_age_days_includes_all(self):
        """Invalid age_days value should be treated as no filter."""
        mock_agentic = _make_mock_agentic_search()
        old_ts = '2020-01-01T00:00:00Z'
        hit = _make_hit('OpenSearch', '2.19.6', [
            _make_vuln('CVE-001', 'HIGH'),
        ], scan_timestamp=old_ts)
        mock_agentic.agentic_search.return_value = {'hits': {'hits': [hit]}}
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'age_days': 'abc'}, 'test-age-005',
        )

        assert result['result_count'] == 1

    def test_age_days_with_epoch_millis_timestamp(self):
        """age_days should work with epoch millisecond timestamps."""
        mock_agentic = _make_mock_agentic_search()
        recent_ms = int(time.time() * 1000)
        hit = _make_hit('OpenSearch', '2.19.6', [
            _make_vuln('CVE-001', 'HIGH'),
        ], scan_timestamp=recent_ms)
        mock_agentic.agentic_search.return_value = {'hits': {'hits': [hit]}}
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'age_days': '7'}, 'test-age-006',
        )

        assert result['result_count'] == 1

    def test_all_scans_filtered_out_returns_empty(self):
        """When all scans are older than age_days, result is empty."""
        mock_agentic = _make_mock_agentic_search()
        old_ts_1 = '2019-01-01T00:00:00Z'
        old_ts_2 = '2019-06-01T00:00:00Z'
        hit1 = _make_hit('OpenSearch', '2.19.6', [
            _make_vuln('CVE-001', 'HIGH'),
        ], scan_timestamp=old_ts_1)
        hit2 = _make_hit('Dashboards', '2.19.6', [
            _make_vuln('CVE-002', 'CRITICAL'),
        ], scan_timestamp=old_ts_2)
        mock_agentic.agentic_search.return_value = {
            'hits': {'hits': [hit1, hit2]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'age_days': '7'}, 'test-age-007',
        )

        assert result['status'] == 'success'
        assert result['result_count'] == 0
        assert result['results'] == []


# ---------------------------------------------------------------------------
# Combined severity + age filtering
# ---------------------------------------------------------------------------


class TestCombinedSeverityAndAgeFiltering:
    """Verify severity and age_days work together correctly."""

    def test_severity_and_age_both_applied(self):
        """Both filters should be applied: age filters scans, severity filters vulns."""
        mock_agentic = _make_mock_agentic_search()
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

        mock_agentic.agentic_search.return_value = {
            'hits': {'hits': [hit_recent, hit_old]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'severity': 'CRITICAL', 'age_days': '30'},
            'test-combo-001',
        )

        # Old hit filtered by age, recent hit filtered by severity
        assert result['result_count'] == 1
        entry = result['results'][0]
        assert entry['project']['name'] == 'OpenSearch'
        assert entry['filtered_count'] == 1
        assert entry['filtered_vulnerabilities'][0]['id'] == 'CVE-001'

    def test_age_filter_applied_before_severity(self):
        """Old scans should be dropped entirely, not just have vulns filtered."""
        mock_agentic = _make_mock_agentic_search()
        old_ts = '2020-01-01T00:00:00Z'

        hit = _make_hit('OpenSearch', '2.19.6', [
            _make_vuln('CVE-001', 'CRITICAL'),
        ], scan_timestamp=old_ts)

        mock_agentic.agentic_search.return_value = {'hits': {'hits': [hit]}}
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'severity': 'CRITICAL', 'age_days': '7'},
            'test-combo-002',
        )

        # Even though the vuln matches severity, the scan is too old
        assert result['result_count'] == 0


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
        assert 'age_days="30"' in instruction or 'age_days="7"' in instruction

    def test_instruction_documents_valid_severity_values(self, agent):
        instruction = agent.get_agent_instruction()
        assert 'CRITICAL' in instruction
        assert 'HIGH' in instruction
        assert 'MEDIUM' in instruction
        assert 'LOW' in instruction
