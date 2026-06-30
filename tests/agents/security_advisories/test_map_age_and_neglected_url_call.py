# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for _map_age_days_to_age and the build_neglected_page_url integration in vulnerabilities_handler.

Covers:
- _map_age_days_to_age: maps numeric age-in-days to the nearest valid bucket.
- build_neglected_page_url call: verifies the URL parameters derived from
  action-group parameters (severity, version, age_days) in handle_query_vulnerabilities.
"""

import importlib
import os
import sys
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

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
    mock_mod.query_advisories = MagicMock(return_value=set())
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
            'sa_vulnerabilities_handler',
            os.path.join(_LAMBDA_PATH, 'vulnerabilities_handler.py'),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod, mock_dsl


SAMPLE_HIT = {
    '_index': 'scans',
    '_source': {
        'project': {'name': 'OpenSearch', 'tag': '2.19.6'},
        'vulnerabilities': [
            {
                'id': 'CVE-2024-001',
                'severity': 'CRITICAL',
                'package': {'name': 'lodash', 'version': '4.17.20'},
            },
        ],
        'count': {'severe': 1, 'minor': 0},
        'timestamp': {'scan': '2024-01-15T10:30:00Z'},
    },
}


# ---------------------------------------------------------------------------
# _map_age_days_to_age
# ---------------------------------------------------------------------------


class TestMapAgeDaysToAge:
    """Tests for _map_age_days_to_age bucket mapping."""

    @pytest.fixture(autouse=True)
    def _load_module(self):
        self.mod, _ = _load_vulnerabilities_handler()

    def test_none_returns_none(self):
        """None input returns None (no age constraint)."""
        assert self.mod._map_age_days_to_age(None) is None

    @pytest.mark.parametrize('age_days,expected', [
        (1, '15d'),
        (10, '15d'),
        (15, '15d'),
    ])
    def test_maps_to_15d_bucket(self, age_days, expected):
        """Values <= 15 map to the 15d bucket."""
        assert self.mod._map_age_days_to_age(age_days) == expected

    @pytest.mark.parametrize('age_days,expected', [
        (16, '30d'),
        (20, '30d'),
        (30, '30d'),
    ])
    def test_maps_to_30d_bucket(self, age_days, expected):
        """Values 16-30 map to the 30d bucket."""
        assert self.mod._map_age_days_to_age(age_days) == expected

    @pytest.mark.parametrize('age_days,expected', [
        (31, '45d'),
        (40, '45d'),
        (45, '45d'),
    ])
    def test_maps_to_45d_bucket(self, age_days, expected):
        """Values 31-45 map to the 45d bucket."""
        assert self.mod._map_age_days_to_age(age_days) == expected

    @pytest.mark.parametrize('age_days,expected', [
        (46, '60d'),
        (55, '60d'),
        (60, '60d'),
    ])
    def test_maps_to_60d_bucket(self, age_days, expected):
        """Values 46-60 map to the 60d bucket."""
        assert self.mod._map_age_days_to_age(age_days) == expected

    @pytest.mark.parametrize('age_days', [61, 90, 100, 365])
    def test_values_exceeding_max_map_to_60d(self, age_days):
        """Values exceeding the largest bucket still map to 60d."""
        assert self.mod._map_age_days_to_age(age_days) == '60d'


# ---------------------------------------------------------------------------
# build_neglected_page_url call in handle_query_vulnerabilities
# ---------------------------------------------------------------------------


class TestNeglectedUrlFromHandlerParams:
    """Tests that handle_query_vulnerabilities builds the neglected URL correctly from params."""

    def _invoke_handler_with_hits(self, params):
        """Helper: invoke handler with a single hit and given params."""
        mock_dsl = _make_mock_dsl_query_builder()
        mock_dsl.query_vulnerabilities.return_value = {'hits': {'total': {'value': 1}, 'hits': [SAMPLE_HIT]}}
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)
        return mod.handle_query_vulnerabilities(params, 'test-req')

    def test_default_url_when_no_filters(self):
        """With no filter params, URL uses defaults: age=30d, severe=true, tag=origin/main."""
        result = self._invoke_handler_with_hits({
            'query': 'Show CVEs',
            'version': 'origin/main',
            '_access_tier': 'privileged',
        })
        url = result['neglected_page_url']
        parsed = parse_qs(urlparse(url).query)
        assert parsed['age'] == ['30d']
        assert parsed['severe'] == ['true']
        assert parsed['tag'] == ['origin/main']

    def test_age_days_maps_to_url_age(self):
        """age_days parameter is mapped to the nearest bucket in the URL."""
        result = self._invoke_handler_with_hits({
            'query': 'Show CVEs',
            'version': '2.19',
            'age_days': '20',
            '_access_tier': 'privileged',
        })
        url = result['neglected_page_url']
        assert 'age=30d' in url

    def test_age_days_15_maps_to_15d(self):
        """age_days=15 maps to age=15d."""
        result = self._invoke_handler_with_hits({
            'query': 'Show CVEs',
            'version': '2.19',
            'age_days': '15',
            '_access_tier': 'privileged',
        })
        assert 'age=15d' in result['neglected_page_url']

    def test_severity_high_sets_severe_true(self):
        """severity=HIGH sets severe=true in the URL."""
        result = self._invoke_handler_with_hits({
            'query': 'Show CVEs',
            'version': '2.19',
            'severity': 'HIGH',
            '_access_tier': 'privileged',
        })
        assert 'severe=true' in result['neglected_page_url']

    def test_severity_critical_sets_critical_true(self):
        """severity=CRITICAL sets critical=true in the URL."""
        result = self._invoke_handler_with_hits({
            'query': 'Show CVEs',
            'version': '2.19',
            'severity': 'CRITICAL',
            '_access_tier': 'privileged',
        })
        assert 'critical=true' in result['neglected_page_url']

    def test_severity_critical_high_sets_both(self):
        """severity=CRITICAL,HIGH sets both critical=true and severe=true."""
        result = self._invoke_handler_with_hits({
            'query': 'Show CVEs',
            'version': '2.19',
            'severity': 'CRITICAL,HIGH',
            '_access_tier': 'privileged',
        })
        url = result['neglected_page_url']
        assert 'critical=true' in url
        assert 'severe=true' in url

    def test_severity_medium_does_not_set_severe_or_critical(self):
        """severity=MEDIUM explicitly passes severe=False and critical=False."""
        result = self._invoke_handler_with_hits({
            'query': 'Show CVEs',
            'version': '2.19',
            'severity': 'MEDIUM',
            '_access_tier': 'privileged',
        })
        url = result['neglected_page_url']
        # When severity is provided but doesn't include HIGH, severe is explicitly False
        # When severity is provided but doesn't include CRITICAL, critical is explicitly False
        parsed = parse_qs(urlparse(url).query)
        assert parsed['severe'] == ['false']
        assert parsed['critical'] == ['false']

    def test_version_sets_tag(self):
        """version parameter is passed as the tag in the URL."""
        result = self._invoke_handler_with_hits({
            'query': 'Show CVEs',
            'version': '2.19.6',
            '_access_tier': 'privileged',
        })
        assert 'tag=2.19.6' in result['neglected_page_url']

    def test_all_params_combined(self):
        """All filter params produce the correct combined URL."""
        result = self._invoke_handler_with_hits({
            'query': 'Show CVEs',
            'age_days': '45',
            'severity': 'CRITICAL,HIGH',
            'version': '1.3.0',
            '_access_tier': 'privileged',
        })
        url = result['neglected_page_url']
        parsed = parse_qs(urlparse(url).query)
        assert parsed['age'] == ['45d']
        assert parsed['severe'] == ['true']
        assert parsed['critical'] == ['true']
        assert parsed['tag'] == ['1.3.0']

    def test_no_severity_uses_default_severe(self):
        """When severity is not provided, severe defaults to true."""
        result = self._invoke_handler_with_hits({
            'query': 'Show CVEs',
            'version': 'origin/main',
            '_access_tier': 'privileged',
        })
        url = result['neglected_page_url']
        parsed = parse_qs(urlparse(url).query)
        # None is passed for severe, so the default (True) applies
        assert parsed['severe'] == ['true']

    def test_url_base_has_trailing_slash(self):
        """The neglected URL base has a trailing slash before the query string."""
        result = self._invoke_handler_with_hits({
            'query': 'Show CVEs',
            'version': 'origin/main',
            '_access_tier': 'privileged',
        })
        url = result['neglected_page_url']
        base = url.split('?')[0]
        assert base.endswith('/')
        assert base == 'https://advisories.opensearch.org/advisories/neglected/'
