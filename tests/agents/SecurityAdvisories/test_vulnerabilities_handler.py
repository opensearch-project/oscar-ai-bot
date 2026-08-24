# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for security advisories vulnerabilities_handler.py.

These tests verify the DSL query flow for vulnerability queries:
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
    os.path.dirname(__file__), '..', '..', '..', 'agents', 'SecurityAdvisories', 'lambda',
)


def _make_mock_dsl_query_builder():
    """Create a mock dsl_query_builder module."""
    mock_mod = MagicMock()
    mock_mod.query_vulnerabilities = MagicMock(return_value={'hits': {'total': {'value': 0}, 'hits': []}})
    mock_mod.resolve_version_tag = MagicMock(side_effect=lambda v: v)
    mock_mod.query_advisories = MagicMock(return_value=(set(), False))
    mock_mod._DEFAULT_QUERY_SIZE = 1000
    return mock_mod


def _load_vulnerabilities_handler(mock_dsl=None):
    """Import vulnerabilities_handler with mocked dependencies."""
    if mock_dsl is None:
        mock_dsl = _make_mock_dsl_query_builder()

    # Also need response_filter — load the real one
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
        mock_dsl = _make_mock_dsl_query_builder()
        mock_dsl.query_vulnerabilities.return_value = {
            'hits': {'total': {'value': 1}, 'hits': [SAMPLE_HIT]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show critical CVEs', 'version': '2.19', '_access_tier': 'privileged'}, 'test-001',
        )

        assert result['status'] == 'success'
        assert result['result_count'] == 1
        entry = result['results'][0]
        assert self.REQUIRED_KEYS.issubset(set(entry.keys()))

    def test_result_entry_project_matches_source(self):
        mock_dsl = _make_mock_dsl_query_builder()
        mock_dsl.query_vulnerabilities.return_value = {
            'hits': {'total': {'value': 1}, 'hits': [SAMPLE_HIT]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'version': '2.19', '_access_tier': 'privileged'}, 'test-002',
        )

        entry = result['results'][0]
        assert entry['project'] == {'name': 'OpenSearch', 'tag': '2.19.6'}

    def test_result_entry_timestamp_matches_source(self):
        mock_dsl = _make_mock_dsl_query_builder()
        mock_dsl.query_vulnerabilities.return_value = {
            'hits': {'total': {'value': 1}, 'hits': [SAMPLE_HIT]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'version': '2.19', '_access_tier': 'privileged'}, 'test-003',
        )

        entry = result['results'][0]
        assert entry['timestamp'] == {'scan': '2024-01-15T10:30:00Z'}

    def test_result_entry_total_count_matches_source(self):
        mock_dsl = _make_mock_dsl_query_builder()
        mock_dsl.query_vulnerabilities.return_value = {
            'hits': {'total': {'value': 1}, 'hits': [SAMPLE_HIT]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'version': '2.19', '_access_tier': 'privileged'}, 'test-004',
        )

        entry = result['results'][0]
        assert entry['total_count'] == {'severe': 1, 'minor': 1}

    def test_result_entry_severity_summary_is_dict(self):
        mock_dsl = _make_mock_dsl_query_builder()
        mock_dsl.query_vulnerabilities.return_value = {
            'hits': {'total': {'value': 1}, 'hits': [SAMPLE_HIT]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'version': '2.19', '_access_tier': 'privileged'}, 'test-005',
        )

        entry = result['results'][0]
        assert isinstance(entry['severity_summary'], dict)

    def test_result_entry_filtered_count_is_int(self):
        mock_dsl = _make_mock_dsl_query_builder()
        mock_dsl.query_vulnerabilities.return_value = {
            'hits': {'total': {'value': 1}, 'hits': [SAMPLE_HIT]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'version': '2.19', '_access_tier': 'privileged'}, 'test-006',
        )

        entry = result['results'][0]
        assert isinstance(entry['filtered_count'], int)


# ---------------------------------------------------------------------------
# Property 6: Vulnerability extraction completeness
# ---------------------------------------------------------------------------


class TestVulnerabilityExtractionCompleteness:
    """**Validates Property 6: Vulnerability extraction completeness**

    For any DSL query response containing N hits, the handler SHALL
    produce exactly N result entries.
    """

    def test_multiple_hits_produce_correct_number_of_entries(self):
        mock_dsl = _make_mock_dsl_query_builder()
        mock_dsl.query_vulnerabilities.return_value = {
            'hits': {'total': {'value': 2}, 'hits': [SAMPLE_HIT, SAMPLE_HIT_2]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show all CVEs', 'version': '2.19', '_access_tier': 'privileged'}, 'test-010',
        )

        assert result['status'] == 'success'
        assert result['result_count'] == 2
        assert len(result['results']) == 2

    def test_single_hit_produces_one_entry(self):
        mock_dsl = _make_mock_dsl_query_builder()
        mock_dsl.query_vulnerabilities.return_value = {
            'hits': {'total': {'value': 1}, 'hits': [SAMPLE_HIT]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'version': '2.19', '_access_tier': 'privileged'}, 'test-011',
        )

        assert result['result_count'] == 1
        assert len(result['results']) == 1

    def test_three_hits_produce_three_entries(self):
        mock_dsl = _make_mock_dsl_query_builder()
        hit3 = {
            '_index': 'scans',
            '_source': {
                'project': {'name': 'Reporting', 'tag': '1.0.0'},
                'vulnerabilities': [],
                'count': {'severe': 0, 'minor': 0},
                'timestamp': {'scan': '2024-01-17T12:00:00Z'},
            },
        }
        mock_dsl.query_vulnerabilities.return_value = {
            'hits': {'total': {'value': 3}, 'hits': [SAMPLE_HIT, SAMPLE_HIT_2, hit3]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show all CVEs', 'version': '2.19', '_access_tier': 'privileged'}, 'test-012',
        )

        assert result['result_count'] == 3
        assert len(result['results']) == 3


# ---------------------------------------------------------------------------
# Property 7: Deduplication by project.name + project.tag (keep newest)
# ---------------------------------------------------------------------------


class TestCollapseDeduplication:
    """**Validates: Deduplication via OpenSearch collapse**

    Deduplication is now handled at the query layer via the ``collapse``
    clause on ``project.name``. The handler trusts that each hit in the
    response is already unique per project. These tests verify that the
    handler correctly processes pre-deduplicated results.
    """

    def test_single_hit_per_project_processed_correctly(self):
        """Handler processes collapsed results (one per project) as-is."""
        mock_dsl = _make_mock_dsl_query_builder()
        mock_dsl.query_vulnerabilities.return_value = {
            'hits': {'total': {'value': 2}, 'hits': [SAMPLE_HIT, SAMPLE_HIT_2]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'version': '2.19', '_access_tier': 'privileged'}, 'test-collapse-01',
        )

        assert result['status'] == 'success'
        assert result['result_count'] == 2


# ---------------------------------------------------------------------------
# Default version behavior
# ---------------------------------------------------------------------------


class TestDefaultVersionBehavior:
    """Test that missing version/project_name defaults to origin/main in the builder."""

    def test_neither_version_nor_project_name_defaults_to_origin_main(self):
        """When both version and project_name are absent, builder defaults to origin/main."""
        mock_dsl = _make_mock_dsl_query_builder()
        mock_dsl.query_vulnerabilities.return_value = {'hits': {'hits': []}}
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show all CVEs', '_access_tier': 'privileged'}, 'test-050',
        )

        # Handler passes through to builder; builder applies origin/main default
        mock_dsl.query_vulnerabilities.assert_called_once_with(
            version=None, project_name=None,
        )
        assert result['status'] == 'success'

    def test_empty_string_version_and_project_name_defaults_to_origin_main(self):
        """Empty strings for both version and project_name are treated as absent."""
        mock_dsl = _make_mock_dsl_query_builder()
        mock_dsl.query_vulnerabilities.return_value = {'hits': {'hits': []}}
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'version': '', 'project_name': '', '_access_tier': 'privileged'},
            'test-051',
        )

        mock_dsl.query_vulnerabilities.assert_called_once_with(
            version='', project_name='',
        )
        assert result['status'] == 'success'

    def test_none_version_and_project_name_defaults_to_origin_main(self):
        """Explicit None for both version and project_name are treated as absent."""
        mock_dsl = _make_mock_dsl_query_builder()
        mock_dsl.query_vulnerabilities.return_value = {'hits': {'hits': []}}
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'version': None, 'project_name': None},
            'test-052',
        )

        mock_dsl.query_vulnerabilities.assert_called_once_with(
            version=None, project_name=None,
        )
        assert result['status'] == 'success'

    def test_version_provided_passes_validation(self):
        """When version is provided, validation passes."""
        mock_dsl = _make_mock_dsl_query_builder()
        mock_dsl.query_vulnerabilities.return_value = {'hits': {'hits': []}}
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'version': '2.19'}, 'test-053',
        )

        assert result['status'] == 'success'
        mock_dsl.query_vulnerabilities.assert_called_once()

    def test_project_name_provided_passes_validation(self):
        """When project_name is provided, validation passes."""
        mock_dsl = _make_mock_dsl_query_builder()
        mock_dsl.query_vulnerabilities.return_value = {'hits': {'hits': []}}
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'project_name': 'OpenSearch'}, 'test-054',
        )

        assert result['status'] == 'success'
        mock_dsl.query_vulnerabilities.assert_called_once()


# ---------------------------------------------------------------------------
# Empty results
# ---------------------------------------------------------------------------


class TestEmptyResults:
    """Test empty results return success with descriptive message."""

    def test_no_hits_returns_success_with_message(self):
        mock_dsl = _make_mock_dsl_query_builder()
        mock_dsl.query_vulnerabilities.return_value = {
            'hits': {'hits': []},
        }
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs for nonexistent project', 'project_name': 'Nonexistent', '_access_tier': 'privileged'}, 'test-020',
        )

        assert result['status'] == 'success'
        assert 'message' in result
        assert result['results'] == []
        assert result['result_count'] == 0

    def test_missing_hits_key_returns_success_with_empty(self):
        mock_dsl = _make_mock_dsl_query_builder()
        mock_dsl.query_vulnerabilities.return_value = {}
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'version': '3.7', '_access_tier': 'privileged'}, 'test-021',
        )

        assert result['status'] == 'success'
        assert result['results'] == []


# ---------------------------------------------------------------------------
# Error response handling (error dict from dsl_query_builder)
# ---------------------------------------------------------------------------


class TestErrorResponseHandling:
    """Test error dict response propagation from dsl_query_builder."""

    def test_error_response_is_propagated(self):
        mock_dsl = _make_mock_dsl_query_builder()
        mock_dsl.query_vulnerabilities.return_value = {
            'status': 'error',
            'type': 'opensearch_error',
            'retryable': False,
            'message': 'OpenSearch query failed: 500 - Internal Server Error',
            'status_code': 500,
        }
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'version': '3.7', '_access_tier': 'privileged'}, 'test-030',
        )

        assert result['status'] == 'error'
        assert result['retryable'] is False
        assert 'message' in result

    def test_connection_error_response_is_propagated(self):
        mock_dsl = _make_mock_dsl_query_builder()
        mock_dsl.query_vulnerabilities.return_value = {
            'status': 'error',
            'type': 'connection_error',
            'retryable': False,
            'message': 'Failed to connect to the OpenSearch cluster. '
                       'The service may be temporarily unavailable.',
        }
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'version': '3.7', '_access_tier': 'privileged'}, 'test-031',
        )

        assert result['status'] == 'error'
        assert result['retryable'] is False

    def test_error_response_has_message_key(self):
        mock_dsl = _make_mock_dsl_query_builder()
        mock_dsl.query_vulnerabilities.return_value = {
            'status': 'error',
            'type': 'index_resolution_error',
            'retryable': False,
            'message': 'Could not resolve scans index',
        }
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'version': '3.7', '_access_tier': 'privileged'}, 'test-032',
        )

        assert 'message' in result
        assert len(result['message']) > 0


# ---------------------------------------------------------------------------
# Privileged response enrichment (neglected_page_url)
# ---------------------------------------------------------------------------


class TestPrivilegedResponseEnrichment:
    """Test that privileged responses include neglected_page_url.

    _Validates: Requirements 2.1, 3.1, 5.2_
    """

    def test_privileged_response_has_neglected_page_url(self):
        """Privileged response includes neglected_page_url field."""
        mock_dsl = _make_mock_dsl_query_builder()
        mock_dsl.query_vulnerabilities.return_value = {
            'hits': {'total': {'value': 1}, 'hits': [SAMPLE_HIT]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'version': '2.19', '_access_tier': 'privileged'}, 'test-041',
        )

        assert 'neglected_page_url' in result
        assert result['neglected_page_url'].startswith(
            'https://advisories.opensearch.org/advisories/neglected/?',
        )

    def test_neglected_url_includes_age_param_from_age_days(self):
        """Neglected URL includes age parameter derived from age_days."""
        mock_dsl = _make_mock_dsl_query_builder()
        mock_dsl.query_vulnerabilities.return_value = {
            'hits': {'total': {'value': 1}, 'hits': [SAMPLE_HIT]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'version': '2.19', 'age_days': '30', '_access_tier': 'privileged'}, 'test-042',
        )

        assert 'age=30d' in result['neglected_page_url']

    def test_neglected_url_includes_severe_when_high_severity(self):
        """Neglected URL includes severe=true when severity contains HIGH."""
        mock_dsl = _make_mock_dsl_query_builder()
        mock_dsl.query_vulnerabilities.return_value = {
            'hits': {'total': {'value': 1}, 'hits': [SAMPLE_HIT]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'version': '2.19', 'severity': 'HIGH', '_access_tier': 'privileged'}, 'test-043',
        )

        assert 'severe=true' in result['neglected_page_url']

    def test_neglected_url_includes_tag_from_version(self):
        """Neglected URL includes tag parameter derived from version."""
        mock_dsl = _make_mock_dsl_query_builder()
        mock_dsl.query_vulnerabilities.return_value = {
            'hits': {'total': {'value': 1}, 'hits': [SAMPLE_HIT]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'version': '2.19.6', '_access_tier': 'privileged'}, 'test-044',
        )

        assert 'tag=2.19.6' in result['neglected_page_url']

    def test_neglected_url_includes_critical_when_critical_severity(self):
        """Neglected URL includes critical=true when severity contains CRITICAL."""
        mock_dsl = _make_mock_dsl_query_builder()
        mock_dsl.query_vulnerabilities.return_value = {
            'hits': {'total': {'value': 1}, 'hits': [SAMPLE_HIT]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'version': '2.19', 'severity': 'CRITICAL,HIGH', '_access_tier': 'privileged'},
            'test-045',
        )

        assert 'critical=true' in result['neglected_page_url']
        assert 'severe=true' in result['neglected_page_url']

    def test_neglected_url_defaults_when_no_filter_params(self):
        """Neglected URL uses defaults when no severity/age filter params are provided."""
        mock_dsl = _make_mock_dsl_query_builder()
        mock_dsl.query_vulnerabilities.return_value = {
            'hits': {'total': {'value': 1}, 'hits': [SAMPLE_HIT]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs', 'version': 'origin/main', '_access_tier': 'privileged'}, 'test-046',
        )

        url = result['neglected_page_url']
        assert url.startswith('https://advisories.opensearch.org/advisories/neglected/?')
        assert 'age=30d' in url
        assert 'severe=true' in url
        assert 'releases=false' in url
        assert 'critical=false' in url
        assert 'tag=origin' in url

    def test_empty_results_still_has_success_status(self):
        """Even with no hits, response returns success status."""
        mock_dsl = _make_mock_dsl_query_builder()
        mock_dsl.query_vulnerabilities.return_value = {
            'hits': {'hits': []},
        }
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show CVEs for nonexistent', 'version': '3.7', '_access_tier': 'privileged'}, 'test-047',
        )

        # Empty results return a message-style response
        assert result['status'] == 'success'

    def test_severity_filter_with_empty_vulnerabilities_returns_zero_filtered(self):
        """When severity is specified but scan hits have empty vulnerabilities arrays,
        filtered_count should be 0 (not unfiltered passthrough)."""
        hit_no_vulns = {
            '_index': 'scans',
            '_source': {
                'project': {'name': 'OpenSearch', 'tag': '2.19.6'},
                'vulnerabilities': [],
                'count': {'severe': 0, 'minor': 0},
                'timestamp': {'scan': '2024-01-15T10:30:00Z'},
            },
        }
        mock_dsl = _make_mock_dsl_query_builder()
        mock_dsl.query_vulnerabilities.return_value = {
            'hits': {'total': {'value': 1}, 'hits': [hit_no_vulns]},
        }
        mod, _ = _load_vulnerabilities_handler(mock_dsl=mock_dsl)

        result = mod.handle_query_vulnerabilities(
            {'query': 'Show critical CVEs', 'severity': 'CRITICAL'}, 'test-048',
        )

        assert result['status'] == 'success'
        assert result['result_count'] == 1
        # The key assertion: with severity filter active but no CVEs in the scan,
        # filtered_count must be 0 (not passthrough of all vulnerabilities).
        assert result['results'][0]['filtered_count'] == 0
        assert result['results'][0]['filtered_vulnerabilities'] == []
