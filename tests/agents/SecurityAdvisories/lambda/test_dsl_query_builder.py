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
    os.path.dirname(__file__), '..', '..', '..', '..', 'agents', 'SecurityAdvisories', 'lambda',
)


def _load_dsl_query_builder(
    scans_index='scans',
    mock_opensearch_request=None,
    opensearch_query_size=100,
):
    """Import dsl_query_builder from security_advisories lambda with mocked deps.

    Args:
        scans_index: Value bound as ``aws_utils.SCANS_INDEX`` (the scans alias).
        mock_opensearch_request: Mock or side_effect for opensearch_request.
        opensearch_query_size: Config value for query size.

    Returns:
        The loaded module with mocked aws_utils and config.
    """
    if _LAMBDA_PATH not in sys.path:
        sys.path.insert(0, _LAMBDA_PATH)

    mock_aws_utils = MagicMock()
    mock_aws_utils.SCANS_INDEX = scans_index
    mock_aws_utils.SCANS_RECENCY_WINDOW = 'now-7d'

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
        assert len(filters) == 2  # tag + always-present scan-recency range
        assert {'term': {'project.tag': 'origin/3.7'}} in filters
        assert any('timestamp.scan' in f.get('range', {}) for f in filters)

    def test_project_name_only_produces_name_filter_without_tag(self):
        """Validates: Requirement 1.4 — project_name alone returns all versions."""
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
        assert len(filters) == 2  # name + always-present scan-recency range
        assert {'term': {'project.name': 'OpenSearch Dashboards'}} in filters
        assert any('timestamp.scan' in f.get('range', {}) for f in filters)

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
        assert len(filters) == 3  # tag + name + always-present scan-recency range
        # Three-part semver resolves to origin/major.minor
        assert {'term': {'project.tag': 'origin/2.19'}} in filters
        assert {'term': {'project.name': 'OpenSearch'}} in filters
        assert any('timestamp.scan' in f.get('range', {}) for f in filters)

    def test_release_components_adds_release_type_filter(self):
        """release_components=True scopes the query to the two release bundles."""
        mock_response = {'hits': {'hits': []}}
        mod, mock_aws = _load_dsl_query_builder(
            mock_opensearch_request=mock_response,
        )

        mod.query_vulnerabilities(version='3.7', release_components=True)

        call_args = mock_aws.opensearch_request.call_args
        body_str = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get('body')
        filters = json.loads(body_str)['query']['bool']['filter']
        assert {'terms': {'release_type.keyword':
                          ['bundle_opensearch', 'bundle_opensearch_dashboards']}} in filters
        assert {'term': {'project.tag': 'origin/3.7'}} in filters

    def test_release_components_only_produces_bundle_filter(self):
        """release_components alone (no version/project) still filters to bundles."""
        mock_response = {'hits': {'hits': []}}
        mod, mock_aws = _load_dsl_query_builder(
            mock_opensearch_request=mock_response,
        )

        mod.query_vulnerabilities(project_name='OpenSearch', release_components=True)

        call_args = mock_aws.opensearch_request.call_args
        body_str = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get('body')
        filters = json.loads(body_str)['query']['bool']['filter']
        assert {'terms': {'release_type.keyword':
                          ['bundle_opensearch', 'bundle_opensearch_dashboards']}} in filters

    def test_release_components_omitted_by_default(self):
        """Without release_components, no release_type filter is applied."""
        mock_response = {'hits': {'hits': []}}
        mod, mock_aws = _load_dsl_query_builder(
            mock_opensearch_request=mock_response,
        )

        mod.query_vulnerabilities(version='3.7')

        call_args = mock_aws.opensearch_request.call_args
        body_str = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get('body')
        filters = json.loads(body_str)['query']['bool']['filter']
        assert not any('release_type.keyword' in f.get('terms', {}) for f in filters)

    def test_query_targets_correct_index(self):
        """Validates: Requirement 1.4"""
        mock_response = {'hits': {'hits': []}}
        mod, mock_aws = _load_dsl_query_builder(
            scans_index='scans',
            mock_opensearch_request=mock_response,
        )

        mod.query_vulnerabilities(version='3.7')

        call_args = mock_aws.opensearch_request.call_args
        path = call_args[0][1]
        assert path == '/scans/_search'

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
        """Validates: sort by [commit desc, scan desc] to pick latest per collapse."""
        mock_response = {'hits': {'hits': []}}
        mod, mock_aws = _load_dsl_query_builder(
            mock_opensearch_request=mock_response,
        )

        mod.query_vulnerabilities(version='3.7')

        call_args = mock_aws.opensearch_request.call_args
        body_str = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get('body')
        body = json.loads(body_str)

        assert 'sort' in body
        assert body['sort'] == [
            {'timestamp.commit': {'order': 'desc'}},
            {'timestamp.scan': {'order': 'desc'}},
        ]

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

    def test_no_param_query_still_bounds_by_scan_recency(self):
        """With no tag/name filters the query is still bool/filter with the
        always-present scan-recency range (no match_all), plus sort and collapse."""
        mock_response = {'hits': {'hits': []}}
        mod, mock_aws = _load_dsl_query_builder(
            mock_opensearch_request=mock_response,
        )

        body = mod._build_dsl_query(resolved_tag=None, project_name=None)

        filters = body['query']['bool']['filter']
        assert filters == [{'range': {'timestamp.scan': {'gte': 'now-7d'}}}]
        assert body['sort'] == [
            {'timestamp.commit': {'order': 'desc'}},
            {'timestamp.scan': {'order': 'desc'}},
        ]
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


# ---------------------------------------------------------------------------
# Test: query_advisories — aliases extraction, batching, partial results
# ---------------------------------------------------------------------------


class TestQueryAdvisoriesBasicBehavior:
    """Test query_advisories early-return conditions and basic behavior."""

    def test_empty_cve_ids_returns_empty_set(self):
        """Empty input list returns empty set immediately without querying."""
        mod, mock_aws = _load_dsl_query_builder()

        result, is_partial = mod.query_advisories(cve_ids=[], age_days=30)

        assert result == set()
        assert is_partial is False
        # No query should have been made
        mock_aws.opensearch_request.assert_not_called()

    def test_no_filter_criteria_returns_empty_set(self):
        """When neither age_days nor severity is provided, returns empty set."""
        mod, mock_aws = _load_dsl_query_builder()

        result, is_partial = mod.query_advisories(
            cve_ids=['CVE-2024-0001'],
            age_days=None,
            severity=None,
        )

        assert result == set()
        assert is_partial is False
        mock_aws.opensearch_request.assert_not_called()

    def test_zero_age_days_no_severity_returns_empty_set(self):
        """age_days=0 is falsy, so without severity, returns empty set."""
        mod, mock_aws = _load_dsl_query_builder()

        result, is_partial = mod.query_advisories(
            cve_ids=['CVE-2024-0001'],
            age_days=0,
            severity=None,
        )

        assert result == set()
        assert is_partial is False
        mock_aws.opensearch_request.assert_not_called()


class TestQueryAdvisoriesAliasesExtraction:
    """Test that aliases from hits are correctly matched to input CVE IDs."""

    def test_single_cve_matched_via_aliases(self):
        """A hit with aliases containing the queried CVE is returned."""
        mock_response = {
            'hits': {
                'hits': [
                    {
                        '_source': {
                            'aliases': ['CVE-2024-0001', 'GHSA-xxxx-yyyy-zzzz'],
                        },
                    },
                ],
            },
        }
        mod, _ = _load_dsl_query_builder(mock_opensearch_request=mock_response)

        result, is_partial = mod.query_advisories(
            cve_ids=['CVE-2024-0001'],
            age_days=30,
        )

        assert result == {'CVE-2024-0001'}
        assert is_partial is False

    def test_multiple_cves_matched_via_aliases(self):
        """Multiple CVEs matched across different hits."""
        mock_response = {
            'hits': {
                'hits': [
                    {
                        '_source': {
                            'aliases': ['CVE-2024-0001', 'GHSA-aaaa-bbbb-cccc'],
                        },
                    },
                    {
                        '_source': {
                            'aliases': ['CVE-2024-0003'],
                        },
                    },
                ],
            },
        }
        mod, _ = _load_dsl_query_builder(mock_opensearch_request=mock_response)

        result, is_partial = mod.query_advisories(
            cve_ids=['CVE-2024-0001', 'CVE-2024-0002', 'CVE-2024-0003'],
            age_days=90,
        )

        # CVE-2024-0002 is not in any aliases, so not returned
        assert result == {'CVE-2024-0001', 'CVE-2024-0003'}
        assert is_partial is False

    def test_alias_not_in_batch_is_ignored(self):
        """Aliases in the hit that are not in the queried batch are not returned."""
        mock_response = {
            'hits': {
                'hits': [
                    {
                        '_source': {
                            'aliases': ['CVE-2024-0001', 'CVE-2024-9999'],
                        },
                    },
                ],
            },
        }
        mod, _ = _load_dsl_query_builder(mock_opensearch_request=mock_response)

        result, is_partial = mod.query_advisories(
            cve_ids=['CVE-2024-0001'],
            age_days=30,
        )

        # Only CVE-2024-0001 was queried, so CVE-2024-9999 is not included
        assert result == {'CVE-2024-0001'}
        assert is_partial is False

    def test_no_matching_aliases_returns_empty_set(self):
        """If no aliases match the queried IDs, returns empty set."""
        mock_response = {
            'hits': {
                'hits': [
                    {
                        '_source': {
                            'aliases': ['CVE-2024-9999', 'GHSA-xxxx-yyyy-zzzz'],
                        },
                    },
                ],
            },
        }
        mod, _ = _load_dsl_query_builder(mock_opensearch_request=mock_response)

        result, is_partial = mod.query_advisories(
            cve_ids=['CVE-2024-0001'],
            age_days=30,
        )

        assert result == set()
        assert is_partial is False

    def test_deduplicates_input_cve_ids(self):
        """Duplicate CVE IDs in input are deduplicated before querying."""
        mock_response = {
            'hits': {
                'hits': [
                    {
                        '_source': {
                            'aliases': ['CVE-2024-0001'],
                        },
                    },
                ],
            },
        }
        mod, mock_aws = _load_dsl_query_builder(mock_opensearch_request=mock_response)

        result, is_partial = mod.query_advisories(
            cve_ids=['CVE-2024-0001', 'CVE-2024-0001', 'CVE-2024-0001'],
            age_days=30,
        )

        assert result == {'CVE-2024-0001'}
        assert is_partial is False
        # One batch (1 unique ID), but age filtering issues two queries: the
        # non-critical/age-filtered one and the critical/no-age one.
        assert mock_aws.opensearch_request.call_count == 2


class TestQueryAdvisoriesBatchFailure:
    """Test is_partial flag when batch queries fail."""

    def test_single_batch_failure_sets_is_partial(self):
        """When the only batch fails, is_partial=True and result is empty."""
        mod, _ = _load_dsl_query_builder(
            mock_opensearch_request=Exception('OpenSearch request failed: 500 - Internal Server Error'),
        )

        result, is_partial = mod.query_advisories(
            cve_ids=['CVE-2024-0001'],
            age_days=30,
        )

        assert result == set()
        assert is_partial is True

    def test_partial_batch_failure_continues_processing(self):
        """When one batch fails and another succeeds, results are partial."""
        call_count = [0]

        def mock_execute_query(index, query_body):
            """First call raises, second call returns a hit matching one of the batch IDs."""
            idx = call_count[0]
            call_count[0] += 1
            if idx == 0:
                raise Exception('Connection timeout')
            # Return a hit whose alias matches the first ID in this batch
            import json as _json
            body = _json.loads(query_body)
            batch_ids = body['query']['bool']['filter'][0]['terms']['aliases']
            return {
                'hits': {
                    'hits': [
                        {'_source': {'aliases': [batch_ids[0]]}},
                    ],
                },
            }

        mod, _ = _load_dsl_query_builder()

        # Patch _ADVISORIES_BATCH_SIZE to 2 so we get multiple batches
        mod._ADVISORIES_BATCH_SIZE = 2
        # Patch _execute_query directly since opensearch_request is bound at import
        original_execute = mod._execute_query
        mod._execute_query = mock_execute_query

        try:
            result, is_partial = mod.query_advisories(
                cve_ids=['CVE-2024-0001', 'CVE-2024-0002', 'CVE-2024-1001', 'CVE-2024-1002'],
                age_days=30,
            )

            # Age filtering issues 2 queries per batch (non-critical + critical); with
            # 2 batches that's 4 calls, and only the first fails. The other three
            # succeed, so each batch still contributes its match and is_partial flags
            # the failure. (Which specific CVE ids land is nondeterministic — batching
            # is over set(cve_ids) — so assert the count, not particular ids.)
            assert is_partial is True
            assert len(result) == 2            # one match from each batch
        finally:
            mod._execute_query = original_execute

    def test_all_batches_succeed_is_partial_false(self):
        """When all batches succeed, is_partial=False."""
        def mock_execute_query(index, query_body):
            """Return a hit matching the first ID in each batch."""
            import json as _json
            body = _json.loads(query_body)
            batch_ids = body['query']['bool']['filter'][0]['terms']['aliases']
            return {
                'hits': {
                    'hits': [
                        {'_source': {'aliases': [batch_ids[0]]}},
                    ],
                },
            }

        mod, _ = _load_dsl_query_builder()

        # Patch batch size to create two batches
        mod._ADVISORIES_BATCH_SIZE = 2
        # Patch _execute_query directly since opensearch_request is bound at import
        original_execute = mod._execute_query
        mod._execute_query = mock_execute_query

        try:
            result, is_partial = mod.query_advisories(
                cve_ids=['CVE-2024-0001', 'CVE-2024-0002', 'CVE-2024-1001', 'CVE-2024-1002'],
                age_days=30,
            )

            # Both batches succeeded — should have 2 matches (one per batch)
            assert len(result) == 2
            assert is_partial is False
        finally:
            mod._execute_query = original_execute


class TestQueryAdvisoriesQueryConstruction:
    """Test that the DSL query body is constructed correctly."""

    @staticmethod
    def _bodies(mock_aws):
        return [
            json.loads(c[0][2] if len(c[0]) > 2 else c[1].get('body'))
            for c in mock_aws.opensearch_request.call_args_list
        ]

    def test_age_filter_splits_into_non_critical_and_critical_queries(self):
        """Age filtering issues two queries: non-critical (age-filtered, CRITICAL
        excluded) and critical (no age filter — always returned)."""
        mock_response = {'hits': {'hits': []}}
        mod, mock_aws = _load_dsl_query_builder(mock_opensearch_request=mock_response)

        mod.query_advisories(cve_ids=['CVE-2024-0001'], age_days=30)

        bodies = self._bodies(mock_aws)
        assert len(bodies) == 2

        # Non-critical query: aliases + range on timestamp.publish, CRITICAL excluded.
        non_crit = next(b for b in bodies if b['query']['bool'].get('must_not'))
        filt = non_crit['query']['bool']['filter']
        assert {'terms': {'aliases': ['CVE-2024-0001']}} in filt
        assert any('lte' in c.get('range', {}).get('timestamp.publish', {}) for c in filt)
        assert non_crit['query']['bool']['must_not'] == [{'term': {'severity': 'CRITICAL'}}]

        # Critical query: severity=CRITICAL and NO range (age bypassed).
        crit = next(b for b in bodies if not b['query']['bool'].get('must_not'))
        cfilt = crit['query']['bool']['filter']
        assert {'term': {'severity': 'CRITICAL'}} in cfilt
        assert all('range' not in c for c in cfilt)

    def test_severity_filter_produces_terms_clause(self):
        """When severity is provided, a terms filter on severity is added."""
        mock_response = {'hits': {'hits': []}}
        mod, mock_aws = _load_dsl_query_builder(mock_opensearch_request=mock_response)

        mod.query_advisories(
            cve_ids=['CVE-2024-0001'],
            severity={'HIGH', 'CRITICAL'},
        )

        call_args = mock_aws.opensearch_request.call_args
        body_str = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get('body')
        body = json.loads(body_str)

        filter_clauses = body['query']['bool']['filter']
        # Should have terms (aliases) + terms (severity)
        assert len(filter_clauses) == 2
        severity_clause = filter_clauses[1]
        assert 'terms' in severity_clause
        assert 'severity' in severity_clause['terms']
        assert set(severity_clause['terms']['severity']) == {'HIGH', 'CRITICAL'}

    def test_both_age_and_severity_splits_queries(self):
        """age_days + severity: the non-critical query carries aliases + range +
        severity (and excludes CRITICAL); the critical query is severity-only, no age."""
        mock_response = {'hits': {'hits': []}}
        mod, mock_aws = _load_dsl_query_builder(mock_opensearch_request=mock_response)

        mod.query_advisories(
            cve_ids=['CVE-2024-0001'],
            age_days=60,
            severity={'HIGH'},
        )

        bodies = self._bodies(mock_aws)
        assert len(bodies) == 2

        non_crit = next(b for b in bodies if b['query']['bool'].get('must_not'))
        filt = non_crit['query']['bool']['filter']
        assert {'terms': {'aliases': ['CVE-2024-0001']}} in filt
        assert any('range' in c for c in filt)
        assert any(c.get('terms', {}).get('severity') == ['HIGH'] for c in filt)
        assert non_crit['query']['bool']['must_not'] == [{'term': {'severity': 'CRITICAL'}}]

        crit = next(b for b in bodies if not b['query']['bool'].get('must_not'))
        assert {'term': {'severity': 'CRITICAL'}} in crit['query']['bool']['filter']

    def test_query_targets_advisories_index(self):
        """The query should target the 'advisories' index."""
        mock_response = {'hits': {'hits': []}}
        mod, mock_aws = _load_dsl_query_builder(mock_opensearch_request=mock_response)

        mod.query_advisories(cve_ids=['CVE-2024-0001'], age_days=30)

        call_args = mock_aws.opensearch_request.call_args
        path = call_args[0][1]
        assert path == '/advisories/_search'

    def test_query_source_limited_to_aliases(self):
        """The query should request only the aliases field in _source."""
        mock_response = {'hits': {'hits': []}}
        mod, mock_aws = _load_dsl_query_builder(mock_opensearch_request=mock_response)

        mod.query_advisories(cve_ids=['CVE-2024-0001'], age_days=30)

        call_args = mock_aws.opensearch_request.call_args
        body_str = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get('body')
        body = json.loads(body_str)

        assert body['_source'] == ['aliases']

    def test_query_size_equals_batch_length(self):
        """The query size should equal the number of IDs in the batch."""
        mock_response = {'hits': {'hits': []}}
        mod, mock_aws = _load_dsl_query_builder(mock_opensearch_request=mock_response)

        mod.query_advisories(
            cve_ids=['CVE-2024-0001', 'CVE-2024-0002', 'CVE-2024-0003'],
            age_days=30,
        )

        call_args = mock_aws.opensearch_request.call_args
        body_str = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get('body')
        body = json.loads(body_str)

        assert body['size'] == 3

    def test_severity_only_without_age_days_queries_successfully(self):
        """Severity alone (without age_days) still triggers a query."""
        mock_response = {
            'hits': {
                'hits': [
                    {'_source': {'aliases': ['CVE-2024-0001']}},
                ],
            },
        }
        mod, mock_aws = _load_dsl_query_builder(mock_opensearch_request=mock_response)

        result, is_partial = mod.query_advisories(
            cve_ids=['CVE-2024-0001'],
            severity={'CRITICAL'},
        )

        assert result == {'CVE-2024-0001'}
        assert is_partial is False
        # Verify no range clause was added
        call_args = mock_aws.opensearch_request.call_args
        body_str = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get('body')
        body = json.loads(body_str)
        filter_clauses = body['query']['bool']['filter']
        assert len(filter_clauses) == 2  # aliases + severity only
        assert not any('range' in clause for clause in filter_clauses)
