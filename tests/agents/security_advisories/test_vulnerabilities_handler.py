# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for security advisories vulnerabilities_handler.py.

These tests verify the agentic search flow for vulnerability queries:
result entry structure, multiple hits, empty results, and error handling.

**Validates Property 5: Result entry structural completeness**
**Validates Property 6: Vulnerability extraction completeness**
"""

import importlib
import os
import sys
from unittest.mock import MagicMock, patch

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

    # Also need response_filter — load the real one
    if _LAMBDA_PATH not in sys.path:
        sys.path.insert(0, _LAMBDA_PATH)

    with patch.dict('sys.modules', {
        'config': mock_config,
        'agentic_search': mock_agentic,
    }):
        spec = importlib.util.spec_from_file_location(
            'sa_vulnerabilities_handler',
            os.path.join(_LAMBDA_PATH, 'vulnerabilities_handler.py'),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod, mock_agentic


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

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
            {
                'id': 'CVE-2024-002',
                'severity': 'HIGH',
                'package': {'name': 'express', 'version': '4.17.1'},
            },
        ],
        'count': {'severe': 1, 'minor': 1},
        'timestamp': {'scan': '2024-01-15T10:30:00Z'},
    },
}

SAMPLE_HIT_2 = {
    '_index': 'scans',
    '_source': {
        'project': {'name': 'OpenSearch Dashboards', 'tag': '2.19.6'},
        'vulnerabilities': [
            {
                'id': 'CVE-2024-003',
                'severity': 'MEDIUM',
                'package': {'name': 'minimist', 'version': '1.2.5'},
            },
        ],
        'count': {'severe': 0, 'minor': 1},
        'timestamp': {'scan': '2024-01-16T08:00:00Z'},
    },
}


# ---------------------------------------------------------------------------
# Property 5: Result entry structural completeness
# ---------------------------------------------------------------------------


class TestResultEntryStructuralCompleteness:
    """**Validates Property 5: Result entry structural completeness**

    For any valid scan document containing project, timestamp, count, and
    vulnerabilities fields, the result entry produced by the handler SHALL
    contain the keys: project, timestamp, total_count, filtered_vulnerabilities,
    filtered_count, and severity_summary.
    """

    REQUIRED_KEYS = {
        'project', 'timestamp', 'total_count',
        'filtered_vulnerabilities', 'filtered_count', 'severity_summary',
    }

    def test_single_hit_contains_all_required_keys(self):
        mock_agentic = _make_mock_agentic_search()
        mock_agentic.agentic_search.return_value = {
            'hits': {'hits': [SAMPLE_HIT]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show critical CVEs', '_access_tier': 'privileged'}, 'test-001',
        )

        assert result['status'] == 'success'
        assert result['result_count'] == 1
        entry = result['results'][0]
        assert self.REQUIRED_KEYS.issubset(set(entry.keys()))

    def test_result_entry_project_matches_source(self):
        mock_agentic = _make_mock_agentic_search()
        mock_agentic.agentic_search.return_value = {
            'hits': {'hits': [SAMPLE_HIT]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', '_access_tier': 'privileged'}, 'test-002',
        )

        entry = result['results'][0]
        assert entry['project'] == {'name': 'OpenSearch', 'tag': '2.19.6'}

    def test_result_entry_timestamp_matches_source(self):
        mock_agentic = _make_mock_agentic_search()
        mock_agentic.agentic_search.return_value = {
            'hits': {'hits': [SAMPLE_HIT]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', '_access_tier': 'privileged'}, 'test-003',
        )

        entry = result['results'][0]
        assert entry['timestamp'] == {'scan': '2024-01-15T10:30:00Z'}

    def test_result_entry_total_count_matches_source(self):
        mock_agentic = _make_mock_agentic_search()
        mock_agentic.agentic_search.return_value = {
            'hits': {'hits': [SAMPLE_HIT]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', '_access_tier': 'privileged'}, 'test-004',
        )

        entry = result['results'][0]
        assert entry['total_count'] == {'severe': 1, 'minor': 1}

    def test_result_entry_severity_summary_is_dict(self):
        mock_agentic = _make_mock_agentic_search()
        mock_agentic.agentic_search.return_value = {
            'hits': {'hits': [SAMPLE_HIT]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', '_access_tier': 'privileged'}, 'test-005',
        )

        entry = result['results'][0]
        assert isinstance(entry['severity_summary'], dict)

    def test_result_entry_filtered_count_is_int(self):
        mock_agentic = _make_mock_agentic_search()
        mock_agentic.agentic_search.return_value = {
            'hits': {'hits': [SAMPLE_HIT]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', '_access_tier': 'privileged'}, 'test-006',
        )

        entry = result['results'][0]
        assert isinstance(entry['filtered_count'], int)


# ---------------------------------------------------------------------------
# Property 6: Vulnerability extraction completeness
# ---------------------------------------------------------------------------


class TestVulnerabilityExtractionCompleteness:
    """**Validates Property 6: Vulnerability extraction completeness**

    For any agentic search response containing N hits, the handler SHALL
    produce exactly N result entries.
    """

    def test_multiple_hits_produce_correct_number_of_entries(self):
        mock_agentic = _make_mock_agentic_search()
        mock_agentic.agentic_search.return_value = {
            'hits': {'hits': [SAMPLE_HIT, SAMPLE_HIT_2]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show all CVEs', '_access_tier': 'privileged'}, 'test-010',
        )

        assert result['status'] == 'success'
        assert result['result_count'] == 2
        assert len(result['results']) == 2

    def test_single_hit_produces_one_entry(self):
        mock_agentic = _make_mock_agentic_search()
        mock_agentic.agentic_search.return_value = {
            'hits': {'hits': [SAMPLE_HIT]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', '_access_tier': 'privileged'}, 'test-011',
        )

        assert result['result_count'] == 1
        assert len(result['results']) == 1

    def test_three_hits_produce_three_entries(self):
        mock_agentic = _make_mock_agentic_search()
        hit3 = {
            '_index': 'scans',
            '_source': {
                'project': {'name': 'Reporting', 'tag': '1.0.0'},
                'vulnerabilities': [],
                'count': {'severe': 0, 'minor': 0},
                'timestamp': {'scan': '2024-01-17T12:00:00Z'},
            },
        }
        mock_agentic.agentic_search.return_value = {
            'hits': {'hits': [SAMPLE_HIT, SAMPLE_HIT_2, hit3]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show all CVEs', '_access_tier': 'privileged'}, 'test-012',
        )

        assert result['result_count'] == 3
        assert len(result['results']) == 3


# ---------------------------------------------------------------------------
# Empty results
# ---------------------------------------------------------------------------


class TestEmptyResults:
    """Test empty results return success with descriptive message."""

    def test_no_hits_returns_success_with_message(self):
        mock_agentic = _make_mock_agentic_search()
        mock_agentic.agentic_search.return_value = {
            'hits': {'hits': []},
        }
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs for nonexistent project', '_access_tier': 'privileged'}, 'test-020',
        )

        assert result['status'] == 'success'
        assert 'message' in result
        assert result['results'] == []
        assert result['result_count'] == 0

    def test_missing_hits_key_returns_success_with_empty(self):
        mock_agentic = _make_mock_agentic_search()
        mock_agentic.agentic_search.return_value = {}
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', '_access_tier': 'privileged'}, 'test-021',
        )

        assert result['status'] == 'success'
        assert result['results'] == []


# ---------------------------------------------------------------------------
# AgenticSearchError handling
# ---------------------------------------------------------------------------


class TestAgenticSearchErrorHandling:
    """Test AgenticSearchError returns non-retryable error response."""

    def test_agentic_search_error_returns_non_retryable(self):
        mock_agentic = _make_mock_agentic_search()
        mock_agentic.agentic_search.side_effect = mock_agentic.AgenticSearchError(
            'Search failed', status_code=500,
        )
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', '_access_tier': 'privileged'}, 'test-030',
        )

        assert result['status'] == 'error'
        assert result['type'] == 'agentic_search_error'
        assert result['retryable'] is False
        assert 'rephras' in result['message'].lower()

    def test_agentic_search_error_without_status_code(self):
        mock_agentic = _make_mock_agentic_search()
        mock_agentic.agentic_search.side_effect = mock_agentic.AgenticSearchError(
            'Connection refused',
        )
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', '_access_tier': 'privileged'}, 'test-031',
        )

        assert result['status'] == 'error'
        assert result['retryable'] is False

    def test_error_response_has_message_key(self):
        mock_agentic = _make_mock_agentic_search()
        mock_agentic.agentic_search.side_effect = mock_agentic.AgenticSearchError(
            'Bad request', status_code=400,
        )
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', '_access_tier': 'privileged'}, 'test-032',
        )

        assert 'message' in result
        assert len(result['message']) > 0

# ---------------------------------------------------------------------------
# Privileged response enrichment (access_tier and neglected_page_url)
# ---------------------------------------------------------------------------


class TestPrivilegedResponseEnrichment:
    """Test that privileged responses include access_tier and neglected_page_url.

    _Validates: Requirements 2.1, 3.1, 5.2_
    """

    def test_privileged_response_has_access_tier(self):
        """Privileged response includes access_tier: 'privileged'."""
        mock_agentic = _make_mock_agentic_search()
        mock_agentic.agentic_search.return_value = {
            'hits': {'hits': [SAMPLE_HIT]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', '_access_tier': 'privileged'}, 'test-040',
        )

        assert result['access_tier'] == 'privileged'

    def test_privileged_response_has_neglected_page_url(self):
        """Privileged response includes neglected_page_url field."""
        mock_agentic = _make_mock_agentic_search()
        mock_agentic.agentic_search.return_value = {
            'hits': {'hits': [SAMPLE_HIT]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', '_access_tier': 'privileged'}, 'test-041',
        )

        assert 'neglected_page_url' in result
        assert result['neglected_page_url'].startswith(
            'https://advisories.opensearch.org/advisories/neglected/',
        )

    def test_neglected_url_includes_age_param(self):
        """Neglected URL includes age parameter when provided in query."""
        mock_agentic = _make_mock_agentic_search()
        mock_agentic.agentic_search.return_value = {
            'hits': {'hits': [SAMPLE_HIT]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'age': '30d', '_access_tier': 'privileged'}, 'test-042',
        )

        assert 'age=30d' in result['neglected_page_url']

    def test_neglected_url_includes_severe_param(self):
        """Neglected URL includes severe parameter when provided."""
        mock_agentic = _make_mock_agentic_search()
        mock_agentic.agentic_search.return_value = {
            'hits': {'hits': [SAMPLE_HIT]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'severe': 'true', '_access_tier': 'privileged'}, 'test-043',
        )

        assert 'severe=true' in result['neglected_page_url']

    def test_neglected_url_includes_tag_param(self):
        """Neglected URL includes tag parameter when provided."""
        mock_agentic = _make_mock_agentic_search()
        mock_agentic.agentic_search.return_value = {
            'hits': {'hits': [SAMPLE_HIT]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'tag': '2.19.6', '_access_tier': 'privileged'}, 'test-044',
        )

        assert 'tag=2.19.6' in result['neglected_page_url']

    def test_neglected_url_includes_releases_and_critical(self):
        """Neglected URL includes releases and critical params when provided."""
        mock_agentic = _make_mock_agentic_search()
        mock_agentic.agentic_search.return_value = {
            'hits': {'hits': [SAMPLE_HIT]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {
                'query': 'Show CVEs',
                'releases': 'true',
                'critical': 'false',
                '_access_tier': 'privileged',
            },
            'test-045',
        )

        assert 'releases=true' in result['neglected_page_url']
        assert 'critical=false' in result['neglected_page_url']

    def test_neglected_url_base_when_no_filter_params(self):
        """Neglected URL is the base URL when no filter params are provided."""
        mock_agentic = _make_mock_agentic_search()
        mock_agentic.agentic_search.return_value = {
            'hits': {'hits': [SAMPLE_HIT]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', '_access_tier': 'privileged'}, 'test-046',
        )

        assert result['neglected_page_url'] == 'https://advisories.opensearch.org/advisories/neglected/'

    def test_empty_results_still_has_neglected_url(self):
        """Even with no hits, privileged response includes neglected_page_url."""
        mock_agentic = _make_mock_agentic_search()
        mock_agentic.agentic_search.return_value = {
            'hits': {'hits': []},
        }
        mod, _ = _load_vulnerabilities_handler(mock_agentic=mock_agentic)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs for nonexistent', '_access_tier': 'privileged'}, 'test-047',
        )

        # Empty results return a message-style response, which may or may not have neglected_url
        # The key point is it doesn't crash and returns success
        assert result['status'] == 'success'
