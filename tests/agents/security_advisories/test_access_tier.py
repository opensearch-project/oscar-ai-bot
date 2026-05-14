# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for access-tier gating in the security advisories handler.

**Property 1: Limited-access response invariance**
For any function invocation, for any combination of query parameters, and for any
access_tier value that is not "privileged", the handler SHALL return a response where:
- status is "success"
- access_tier is "limited"
- dashboard_url equals "https://advisories.opensearch.org"
- results is an empty list
- The response contains no CVE identifiers, severity levels, component names, etc.

**Property 3: No external calls for limited-access requests**
For any function invocation and any non-privileged access_tier value, calling the handler
SHALL NOT invoke the agentic search pipeline or make any OpenSearch queries.

_Validates: Requirements 1.1, 1.2, 1.3, 1.4, 3.3, 5.1, 6.1, 6.2, 6.4_
"""

import importlib
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Path to the real vulnerabilities_handler module
_LAMBDA_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'agents', 'security_advisories', 'lambda',
)

DASHBOARD_URL = "https://advisories.opensearch.org"

# Sensitive fields that must NEVER appear in a limited response
SENSITIVE_FIELDS = {'neglected_page_url', 'filtered_vulnerabilities', 'severity_summary'}

# Non-privileged access tier values to test
NON_PRIVILEGED_TIERS = [
    'limited',
    '',
    'LIMITED',
    'admin',
    'unknown',
    'read-only',
    'PRIVILEGED',  # wrong case before .lower() — but code does .lower(), so this becomes privileged
    'viewer',
    'none',
    '0',
    'false',
]

# Filter out values that would become "privileged" after .lower().strip()
NON_PRIVILEGED_TIERS = [t for t in NON_PRIVILEGED_TIERS if str(t).lower().strip() != 'privileged']


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
            'sa_vulnerabilities_handler_access_tier',
            os.path.join(_LAMBDA_PATH, 'vulnerabilities_handler.py'),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod, mock_agentic


# ---------------------------------------------------------------------------
# Property 1: Limited-access response invariance
# ---------------------------------------------------------------------------


class TestLimitedAccessResponseInvariance:
    """Property 1: Limited-access response invariance.

    For any non-privileged access_tier value and any query parameters,
    the handler returns only the dashboard link with no CVE data.

    **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 3.3, 5.1, 6.2**
    """

    @pytest.mark.parametrize('access_tier', NON_PRIVILEGED_TIERS)
    def test_limited_response_structure(self, access_tier):
        """Any non-privileged access_tier produces dashboard-only response."""
        mod, _ = _load_vulnerabilities_handler()
        params = {'query': 'Show critical CVEs', '_access_tier': access_tier}

        result = mod.handle_query_vulnerabilities(params, 'prop-test')

        assert result['status'] == 'success'
        assert result['access_tier'] == 'limited'
        assert result['dashboard_url'] == DASHBOARD_URL
        assert result['results'] == []

    @pytest.mark.parametrize('access_tier', NON_PRIVILEGED_TIERS)
    def test_limited_response_has_no_sensitive_fields(self, access_tier):
        """Limited response contains no CVE data, severity, or neglected URLs."""
        mod, _ = _load_vulnerabilities_handler()
        params = {'query': 'Show CVEs', '_access_tier': access_tier}

        result = mod.handle_query_vulnerabilities(params, 'prop-test')

        for field in SENSITIVE_FIELDS:
            assert field not in result, f"Sensitive field '{field}' found in limited response"

    @pytest.mark.parametrize('access_tier', NON_PRIVILEGED_TIERS)
    def test_limited_response_message_present(self, access_tier):
        """Limited response includes a user-facing message."""
        mod, _ = _load_vulnerabilities_handler()
        params = {'query': 'Show CVEs', '_access_tier': access_tier}

        result = mod.handle_query_vulnerabilities(params, 'prop-test')

        assert 'message' in result
        assert len(result['message']) > 0

    def test_missing_access_tier_defaults_to_limited(self):
        """When _access_tier key is missing, defaults to limited response."""
        mod, _ = _load_vulnerabilities_handler()
        params = {'query': 'Show CVEs'}

        result = mod.handle_query_vulnerabilities(params, 'test-default')

        assert result['status'] == 'success'
        assert result['access_tier'] == 'limited'
        assert result['dashboard_url'] == DASHBOARD_URL
        assert result['results'] == []

    def test_none_access_tier_defaults_to_limited(self):
        """None access_tier is treated as limited."""
        mod, _ = _load_vulnerabilities_handler()
        params = {'query': 'Show CVEs', '_access_tier': None}

        result = mod.handle_query_vulnerabilities(params, 'test-none')

        assert result['access_tier'] == 'limited'
        assert result['results'] == []

    def test_dashboard_url_has_no_query_params(self):
        """Dashboard URL is the bare URL with no query parameters."""
        mod, _ = _load_vulnerabilities_handler()
        params = {
            'query': 'Show CVEs',
            'severity': 'CRITICAL',
            'age_days': '30',
            '_access_tier': 'limited',
        }

        result = mod.handle_query_vulnerabilities(params, 'test-no-params')

        assert '?' not in result['dashboard_url']
        assert result['dashboard_url'] == DASHBOARD_URL

    @pytest.mark.parametrize('params', [
        {'query': 'Show CVEs', 'version': '2.19.6', 'severity': 'CRITICAL'},
        {'query': 'List all high CVEs', 'project_name': 'OpenSearch', 'age_days': '7'},
        {'query': 'Critical vulnerabilities', 'severity': 'CRITICAL,HIGH'},
        {'query': 'CVEs for Dashboards'},
    ])
    def test_limited_regardless_of_query_params(self, params):
        """Limited response is the same regardless of query parameters."""
        mod, _ = _load_vulnerabilities_handler()
        params['_access_tier'] = 'limited'

        result = mod.handle_query_vulnerabilities(params, 'test-params')

        assert result['status'] == 'success'
        assert result['access_tier'] == 'limited'
        assert result['dashboard_url'] == DASHBOARD_URL
        assert result['results'] == []


# ---------------------------------------------------------------------------
# Property 3: No external calls for limited-access requests
# ---------------------------------------------------------------------------


class TestNoExternalCallsForLimitedAccess:
    """Property 3: Agentic search is never invoked for limited-access requests.

    For any non-privileged access_tier value and any query parameters,
    calling handle_query_vulnerabilities SHALL NOT invoke agentic_search
    or enhance_query.

    **Validates: Requirements 6.1, 6.4**
    """

    @pytest.mark.parametrize('access_tier', NON_PRIVILEGED_TIERS)
    def test_agentic_search_never_called(self, access_tier):
        """Agentic search is never invoked for non-privileged access."""
        mock_agentic = _make_mock_agentic_search()
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)
        params = {'query': 'Show critical CVEs', '_access_tier': access_tier}

        mod.handle_query_vulnerabilities(params, 'prop-test')

        mock_agentic.agentic_search.assert_not_called()

    @pytest.mark.parametrize('access_tier', NON_PRIVILEGED_TIERS)
    def test_enhance_query_never_called(self, access_tier):
        """enhance_query is never invoked for non-privileged access."""
        mock_agentic = _make_mock_agentic_search()
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)
        params = {'query': 'Show critical CVEs', '_access_tier': access_tier}

        mod.handle_query_vulnerabilities(params, 'prop-test')

        mock_agentic.enhance_query.assert_not_called()

    def test_privileged_does_call_agentic_search(self):
        """Sanity check: privileged access DOES invoke agentic search."""
        mock_agentic = _make_mock_agentic_search()
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)
        params = {'query': 'Show CVEs', '_access_tier': 'privileged'}

        mod.handle_query_vulnerabilities(params, 'test-priv')

        mock_agentic.enhance_query.assert_called_once()
        mock_agentic.agentic_search.assert_called_once()

    @pytest.mark.parametrize('params', [
        {'query': 'Show CVEs', 'version': '2.19.6', 'severity': 'CRITICAL'},
        {'query': 'List all high CVEs', 'project_name': 'OpenSearch', 'age_days': '7'},
        {'query': 'Critical vulnerabilities', 'severity': 'CRITICAL,HIGH'},
    ])
    def test_no_external_calls_with_various_params(self, params):
        """No external calls regardless of query parameters for limited access."""
        mock_agentic = _make_mock_agentic_search()
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)
        params['_access_tier'] = 'limited'

        mod.handle_query_vulnerabilities(params, 'test-various')

        mock_agentic.agentic_search.assert_not_called()
        mock_agentic.enhance_query.assert_not_called()
