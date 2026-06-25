# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for security advisories dsl_query_builder.py.

These tests verify DSL query construction, error handling, and response
validation for the direct DSL query builder that replaces agentic search.

Validates: Requirements 1.4, 1.7, 3.2
"""

import importlib
import json
import os
import sys
from unittest.mock import MagicMock, patch

# Path to the real dsl_query_builder module
_LAMBDA_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', '..', 'agents', 'security_advisories', 'lambda',
)


def _load_dsl_query_builder(
    mock_get_latest_scans_index=None,
    mock_opensearch_request=None,
    opensearch_query_size=100,
):
    """Import dsl_query_builder from security_advisories lambda with mocked deps.

    Args:
        mock_get_latest_scans_index: Mock or side_effect for get_latest_scans_index.
        mock_opensearch_request: Mock or side_effect for opensearch_request.
        opensearch_query_size: Config value for query size.

    Returns:
        The loaded module with mocked aws_utils and config.
    """
    if _LAMBDA_PATH not in sys.path:
        sys.path.insert(0, _LAMBDA_PATH)

    mock_aws_utils = MagicMock()
    if mock_get_latest_scans_index is not None:
        if isinstance(mock_get_latest_scans_index, Exception):
            mock_aws_utils.get_latest_scans_index.side_effect = mock_get_latest_scans_index
        else:
            mock_aws_utils.get_latest_scans_index.return_value = mock_get_latest_scans_index
    else:
        mock_aws_utils.get_latest_scans_index.return_value = 'scans-000164'

    if mock_opensearch_request is not None:
        if isinstance(mock_opensearch_request, Exception):
            mock_aws_utils.opensearch_request.side_effect = mock_opensearch_request
        else:
            mock_aws_utils.opensearch_request.return_value = mock_opensearch_request
    else:
        mock_aws_utils.opensearch_request.return_value = {'hits': {'hits': []}}

    mock_config_module = MagicMock()
    mock_config_module.config.opensearch_query_size = opensearch_query_size

    with patch.dict('sys.modules', {
        'aws_utils': mock_aws_utils,
        'config': mock_config_module,
    }):
        spec = importlib.util.spec_from_file_location(
            'sa_dsl_query_builder_unit', os.path.join(_LAMBDA_PATH, 'dsl_query_builder.py'),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

    return mod, mock_aws_utils


# ---------------------------------------------------------------------------
# Test: get_latest_scans_index() RuntimeError → index_resolution_error
# ---------------------------------------------------------------------------


class TestIndexResolutionError:
    """Test that RuntimeError from get_latest_scans_index produces error response."""

    def test_runtime_error_returns_index_resolution_error(self):
        """Validates: Requirement 1.7"""
        mod, _ = _load_dsl_query_builder(
            mock_get_latest_scans_index=RuntimeError('No scans indices found'),
        )

        result = mod.query_vulnerabilities(version='3.7', project_name='OpenSearch')

        assert result['status'] == 'error'
        assert result['type'] == 'index_resolution_error'
        assert result['retryable'] is False
        assert 'No scans indices found' in result['message']

    def test_runtime_error_with_custom_message(self):
        """Validates: Requirement 1.7"""
        mod, _ = _load_dsl_query_builder(
            mock_get_latest_scans_index=RuntimeError(
                'Failed to resolve latest scans index: timeout',
            ),
        )

        result = mod.query_vulnerabilities()

        assert result['status'] == 'error'
        assert result['type'] == 'index_resolution_error'
        assert result['retryable'] is False
        assert 'timeout' in result['message']


# ---------------------------------------------------------------------------
# Test: match_all query when both params are absent/empty
# ---------------------------------------------------------------------------


class TestDefaultVersionBehavior:
    """Test that missing/empty version defaults to origin/main filter."""

    def test_both_params_none_defaults_to_origin_main(self):
        """Validates: Requirement 1.4 — no version defaults to origin/main."""
        mock_response = {'hits': {'hits': []}}
        mod, mock_aws = _load_dsl_query_builder(
            mock_opensearch_request=mock_response,
        )

        mod.query_vulnerabilities(version=None, project_name=None)

        call_args = mock_aws.opensearch_request.call_args
        body_str = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get('body')
        body = json.loads(body_str)

        assert 'bool' in body['query']
        filters = body['query']['bool']['filter']
        assert {'term': {'project.tag': 'origin/main'}} in filters

    def test_both_params_empty_string_defaults_to_origin_main(self):
        """Validates: Requirement 1.4 — empty version defaults to origin/main."""
        mock_response = {'hits': {'hits': []}}
        mod, mock_aws = _load_dsl_query_builder(
            mock_opensearch_request=mock_response,
        )

        mod.query_vulnerabilities(version='', project_name='')

        call_args = mock_aws.opensearch_request.call_args
        body_str = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get('body')
        body = json.loads(body_str)

        assert 'bool' in body['query']
        filters = body['query']['bool']['filter']
        assert {'term': {'project.tag': 'origin/main'}} in filters

    def test_no_args_defaults_to_origin_main(self):
        """Validates: Requirement 1.4 — no args defaults to origin/main."""
        mock_response = {'hits': {'hits': []}}
        mod, mock_aws = _load_dsl_query_builder(
            mock_opensearch_request=mock_response,
        )

        mod.query_vulnerabilities()

        call_args = mock_aws.opensearch_request.call_args
        body_str = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get('body')
        body = json.loads(body_str)

        assert 'bool' in body['query']
        filters = body['query']['bool']['filter']
        assert {'term': {'project.tag': 'origin/main'}} in filters


# ---------------------------------------------------------------------------
# Test: Empty hits response — success with empty results
# ---------------------------------------------------------------------------


class TestEmptyHitsResponse:
    """Test that zero hits returns success with empty results."""

    def test_empty_hits_returns_envelope(self):
        """Validates: Requirement 3.2"""
        mock_response = {'hits': {'hits': []}}
        mod, _ = _load_dsl_query_builder(
            mock_opensearch_request=mock_response,
        )

        result = mod.query_vulnerabilities(version='3.7')

        assert result == {'hits': {'hits': []}}
        assert 'status' not in result  # Not an error response

    def test_empty_hits_with_total_field(self):
        """Validates: Requirement 3.2"""
        mock_response = {
            'hits': {
                'total': {'value': 0, 'relation': 'eq'},
                'hits': [],
            },
        }
        mod, _ = _load_dsl_query_builder(
            mock_opensearch_request=mock_response,
        )

        result = mod.query_vulnerabilities(project_name='OpenSearch')

        assert result['hits']['hits'] == []
        assert result['hits']['total']['value'] == 0


# ---------------------------------------------------------------------------
# Test: Specific version/project combinations produce expected DSL
# ---------------------------------------------------------------------------


class TestDSLQueryStructure:
    """Test that specific parameters produce correct DSL query structure."""

    def test_version_only_produces_tag_filter(self):
        """Validates: Requirement 1.4"""
        mock_response = {'hits': {'hits': []}}
        mod, mock_aws = _load_dsl_query_builder(
            mock_opensearch_request=mock_response,
        )

        mod.query_vulnerabilities(version='3.7')

        call_args = mock_aws.opensearch_request.call_args
        body_str = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get('body')
        body = json.loads(body_str)

        assert 'bool' in body['query']
        filters = body['query']['bool']['filter']
        assert len(filters) == 1
        assert filters[0] == {'term': {'project.tag': 'origin/3.7'}}

    def test_project_name_only_produces_name_and_default_tag_filter(self):
        """Validates: Requirement 1.4 — project_name alone still gets origin/main default."""
        mock_response = {'hits': {'hits': []}}
        mod, mock_aws = _load_dsl_query_builder(
            mock_opensearch_request=mock_response,
        )

        mod.query_vulnerabilities(project_name='OpenSearch Dashboards')

        call_args = mock_aws.opensearch_request.call_args
        body_str = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get('body')
        body = json.loads(body_str)

        assert 'bool' in body['query']
        filters = body['query']['bool']['filter']
        assert len(filters) == 2
        assert {'term': {'project.tag': 'origin/main'}} in filters
        assert {'term': {'project.name': 'OpenSearch Dashboards'}} in filters

    def test_both_params_produce_combined_filter(self):
        """Validates: Requirement 1.4"""
        mock_response = {'hits': {'hits': []}}
        mod, mock_aws = _load_dsl_query_builder(
            mock_opensearch_request=mock_response,
        )

        mod.query_vulnerabilities(version='2.19.6', project_name='OpenSearch')

        call_args = mock_aws.opensearch_request.call_args
        body_str = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get('body')
        body = json.loads(body_str)

        assert 'bool' in body['query']
        filters = body['query']['bool']['filter']
        assert len(filters) == 2
        # Three-part semver passes through unchanged
        assert {'term': {'project.tag': '2.19.6'}} in filters
        assert {'term': {'project.name': 'OpenSearch'}} in filters

    def test_query_targets_correct_index(self):
        """Validates: Requirement 1.4"""
        mock_response = {'hits': {'hits': []}}
        mod, mock_aws = _load_dsl_query_builder(
            mock_get_latest_scans_index='scans-000200',
            mock_opensearch_request=mock_response,
        )

        mod.query_vulnerabilities(version='3.7')

        call_args = mock_aws.opensearch_request.call_args
        path = call_args[0][1]
        assert path == '/scans-000200/_search'

    def test_query_includes_size_field(self):
        """Validates: Requirement 1.4"""
        mock_response = {'hits': {'hits': []}}
        mod, mock_aws = _load_dsl_query_builder(
            mock_opensearch_request=mock_response,
        )

        mod.query_vulnerabilities(version='3.7')

        call_args = mock_aws.opensearch_request.call_args
        body_str = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get('body')
        body = json.loads(body_str)

        assert 'size' in body
        assert isinstance(body['size'], int)
        assert body['size'] == 1000

    def test_query_includes_sort_by_timestamp_desc(self):
        """Validates: sort by timestamp.scan descending for collapse."""
        mock_response = {'hits': {'hits': []}}
        mod, mock_aws = _load_dsl_query_builder(
            mock_opensearch_request=mock_response,
        )

        mod.query_vulnerabilities(version='3.7')

        call_args = mock_aws.opensearch_request.call_args
        body_str = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get('body')
        body = json.loads(body_str)

        assert 'sort' in body
        assert body['sort'] == [{'timestamp.scan': {'order': 'desc'}}]

    def test_query_includes_collapse_on_project_name(self):
        """Validates: collapse on project.name for deduplication at query level."""
        mock_response = {'hits': {'hits': []}}
        mod, mock_aws = _load_dsl_query_builder(
            mock_opensearch_request=mock_response,
        )

        mod.query_vulnerabilities(version='3.7')

        call_args = mock_aws.opensearch_request.call_args
        body_str = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get('body')
        body = json.loads(body_str)

        assert 'collapse' in body
        assert body['collapse'] == {'field': 'project.name'}

    def test_match_all_query_includes_sort_and_collapse(self):
        """Validates: even match_all queries include sort and collapse."""
        mock_response = {'hits': {'hits': []}}
        mod, mock_aws = _load_dsl_query_builder(
            mock_opensearch_request=mock_response,
        )

        # Both params default to origin/main, resulting in bool/filter, but let's
        # directly test the internal _build_dsl_query with no filters
        body = mod._build_dsl_query(resolved_tag=None, project_name=None)

        assert 'sort' in body
        assert body['sort'] == [{'timestamp.scan': {'order': 'desc'}}]
        assert 'collapse' in body
        assert body['collapse'] == {'field': 'project.name'}


# ---------------------------------------------------------------------------
# Test: OpenSearch non-2xx error → opensearch_error
# ---------------------------------------------------------------------------


class TestOpenSearchError:
    """Test non-2xx OpenSearch responses produce opensearch_error."""

    def test_non_2xx_returns_opensearch_error(self):
        """Validates: Requirement 1.4"""
        mod, _ = _load_dsl_query_builder(
            mock_opensearch_request=Exception(
                'OpenSearch request failed: 400 - Bad Request',
            ),
        )

        result = mod.query_vulnerabilities(version='3.7')

        assert result['status'] == 'error'
        assert result['type'] == 'opensearch_error'
        assert result['retryable'] is False
        assert result['status_code'] == 400

    def test_500_error_returns_correct_status_code(self):
        """Validates: Requirement 1.4"""
        mod, _ = _load_dsl_query_builder(
            mock_opensearch_request=Exception(
                'OpenSearch request failed: 500 - Internal Server Error',
            ),
        )

        result = mod.query_vulnerabilities(version='3.7')

        assert result['status'] == 'error'
        assert result['type'] == 'opensearch_error'
        assert result['status_code'] == 500

    def test_403_error_returns_correct_status_code(self):
        """Validates: Requirement 1.4"""
        mod, _ = _load_dsl_query_builder(
            mock_opensearch_request=Exception(
                'OpenSearch request failed: 403 - Forbidden',
            ),
        )

        result = mod.query_vulnerabilities(project_name='OpenSearch')

        assert result['status'] == 'error'
        assert result['type'] == 'opensearch_error'
        assert result['status_code'] == 403


# ---------------------------------------------------------------------------
# Test: Connection error → sanitized connection_error
# ---------------------------------------------------------------------------


class TestConnectionError:
    """Test connection errors produce sanitized error response."""

    def test_connection_timeout_returns_sanitized_error(self):
        """Validates: Requirement 1.4"""
        mod, _ = _load_dsl_query_builder(
            mock_opensearch_request=ConnectionError(
                'Failed to connect to search-internal-host.us-east-1.es.amazonaws.com:443',
            ),
        )

        result = mod.query_vulnerabilities(version='3.7')

        assert result['status'] == 'error'
        assert result['type'] == 'connection_error'
        assert result['retryable'] is False
        # Verify sanitization: no internal hostnames leaked
        assert 'search-internal-host' not in result['message']
        assert 'amazonaws.com' not in result['message']

    def test_timeout_error_returns_sanitized_error(self):
        """Validates: Requirement 1.4"""
        mod, _ = _load_dsl_query_builder(
            mock_opensearch_request=TimeoutError(
                'Connection timed out after 60s',
            ),
        )

        result = mod.query_vulnerabilities(version='3.7')

        assert result['status'] == 'error'
        assert result['type'] == 'connection_error'
        assert result['retryable'] is False
        # Verify message is generic/sanitized
        assert 'connect' in result['message'].lower() or 'unavailable' in result['message'].lower()

    def test_connection_error_no_credentials_leaked(self):
        """Validates: Requirement 1.4"""
        mod, _ = _load_dsl_query_builder(
            mock_opensearch_request=Exception(
                'AKIA1234567890EXAMPLE secret credentials leaked in error',
            ),
        )

        result = mod.query_vulnerabilities(version='3.7')

        assert result['status'] == 'error'
        assert result['type'] == 'connection_error'
        # Verify no credentials in message
        assert 'AKIA1234567890' not in result['message']


# ---------------------------------------------------------------------------
# Test: Malformed response — caller handles gracefully via .get() defaults
# ---------------------------------------------------------------------------


class TestMalformedResponse:
    """Test that malformed OpenSearch responses are handled gracefully.

    Since opensearch_request raises on non-2xx and the caller uses
    .get() with defaults, these scenarios pass through without error.
    The caller treats missing hits as empty results.
    """

    def test_missing_hits_key_passes_through(self):
        """Response without 'hits' passes through; caller handles via .get() defaults."""
        mod, _ = _load_dsl_query_builder(
            mock_opensearch_request={'took': 5, 'timed_out': False},
        )

        result = mod.query_vulnerabilities(version='3.7')

        # No error — the response passes through as-is
        assert 'status' not in result
        assert result == {'took': 5, 'timed_out': False}

    def test_hits_not_a_dict_passes_through(self):
        """Response with non-dict 'hits' passes through."""
        mod, _ = _load_dsl_query_builder(
            mock_opensearch_request={'hits': 'not a dict'},
        )

        result = mod.query_vulnerabilities(version='3.7')

        assert 'status' not in result

    def test_hits_hits_missing_passes_through(self):
        """Response with hits but no hits.hits passes through."""
        mod, _ = _load_dsl_query_builder(
            mock_opensearch_request={'hits': {'total': {'value': 0, 'relation': 'eq'}}},
        )

        result = mod.query_vulnerabilities(version='3.7')

        assert 'status' not in result
        assert result['hits']['total']['value'] == 0

    def test_hits_hits_not_a_list_passes_through(self):
        """Response with non-list hits.hits passes through."""
        mod, _ = _load_dsl_query_builder(
            mock_opensearch_request={'hits': {'hits': {'unexpected': 'structure'}}},
        )

        result = mod.query_vulnerabilities(version='3.7')

        assert 'status' not in result
