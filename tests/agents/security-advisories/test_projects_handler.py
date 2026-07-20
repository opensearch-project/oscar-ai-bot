# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for security advisories projects_handler.py.

These tests verify project listing via aggregation queries: alphabetical
sorting, descending tag sorting, and error handling.

**Validates Property 7: List projects output ordering**
"""

import importlib
import os
from unittest.mock import MagicMock, patch

# Path to the real projects_handler module
_LAMBDA_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'agents', 'security-advisories', 'lambda',
)


def _make_mock_config():
    """Create a mock config module with required attributes."""
    mock_config = MagicMock()
    mock_config_module = MagicMock()
    mock_config_module.config = mock_config
    return mock_config_module


def _load_projects_handler(mock_config=None, mock_aws_utils=None):
    """Import projects_handler with mocked dependencies."""
    if mock_config is None:
        mock_config = _make_mock_config()
    if mock_aws_utils is None:
        mock_aws_utils = MagicMock()

    with patch.dict('sys.modules', {
        'config': mock_config,
        'aws_utils': mock_aws_utils,
    }):
        spec = importlib.util.spec_from_file_location(
            'sa_projects_handler',
            os.path.join(_LAMBDA_PATH, 'projects_handler.py'),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod, mock_aws_utils


# ---------------------------------------------------------------------------
# Sample aggregation responses
# ---------------------------------------------------------------------------

SAMPLE_AGG_RESPONSE = {
    'aggregations': {
        'projects': {
            'buckets': [
                {
                    'key': 'OpenSearch Dashboards',
                    'doc_count': 10,
                    'tags': {
                        'buckets': [
                            {'key': '2.19.5', 'doc_count': 3},
                            {'key': '2.19.6', 'doc_count': 5},
                            {'key': 'origin/main', 'doc_count': 2},
                        ],
                    },
                },
                {
                    'key': 'OpenSearch',
                    'doc_count': 15,
                    'tags': {
                        'buckets': [
                            {'key': '2.18.0', 'doc_count': 2},
                            {'key': '2.19.6', 'doc_count': 8},
                            {'key': '2.19.5', 'doc_count': 5},
                        ],
                    },
                },
                {
                    'key': 'Reporting',
                    'doc_count': 5,
                    'tags': {
                        'buckets': [
                            {'key': '1.0.0', 'doc_count': 5},
                        ],
                    },
                },
            ],
        },
    },
}


# ---------------------------------------------------------------------------
# Property 7: List projects output ordering
# ---------------------------------------------------------------------------


class TestProjectsSortedAlphabetically:
    """**Validates Property 7: List projects output ordering**

    Projects SHALL be sorted alphabetically by name.
    """

    def test_projects_sorted_alphabetically(self):
        mock_aws = MagicMock()
        mock_aws.opensearch_request.return_value = SAMPLE_AGG_RESPONSE
        mod, _ = _load_projects_handler(mock_aws_utils=mock_aws)

        result = mod.handle_list_projects('test-001')

        assert result['status'] == 'success'
        names = [p['name'] for p in result['projects']]
        assert names == sorted(names)

    def test_projects_in_expected_order(self):
        mock_aws = MagicMock()
        mock_aws.opensearch_request.return_value = SAMPLE_AGG_RESPONSE
        mod, _ = _load_projects_handler(mock_aws_utils=mock_aws)

        result = mod.handle_list_projects('test-002')

        names = [p['name'] for p in result['projects']]
        assert names == ['OpenSearch', 'OpenSearch Dashboards', 'Reporting']

    def test_project_count_matches_buckets(self):
        mock_aws = MagicMock()
        mock_aws.opensearch_request.return_value = SAMPLE_AGG_RESPONSE
        mod, _ = _load_projects_handler(mock_aws_utils=mock_aws)

        result = mod.handle_list_projects('test-003')

        assert result['project_count'] == 3


class TestProjectTagsInOutput:
    """**Validates Property 7: List projects output includes tags array**

    Each project SHALL have a 'tags' array with all available tags sorted
    in descending semver order (version tags first, then non-version tags).
    """

    def test_tags_included_in_response(self):
        """Response should include the full tags array for each project."""
        mock_aws = MagicMock()
        mock_aws.opensearch_request.return_value = SAMPLE_AGG_RESPONSE
        mod, _ = _load_projects_handler(mock_aws_utils=mock_aws)

        result = mod.handle_list_projects('test-010')

        for project in result['projects']:
            assert 'tags' in project

    def test_tags_sorted_descending_semver(self):
        mock_aws = MagicMock()
        mock_aws.opensearch_request.return_value = SAMPLE_AGG_RESPONSE
        mod, _ = _load_projects_handler(mock_aws_utils=mock_aws)

        result = mod.handle_list_projects('test-011')

        os_project = next(p for p in result['projects'] if p['name'] == 'OpenSearch')
        # Version tags sorted descending: 2.19.6, 2.19.5, 2.18.0
        assert os_project['tags'] == ['2.19.6', '2.19.5', '2.18.0']

    def test_non_version_tags_sorted_after_versions(self):
        mock_aws = MagicMock()
        mock_aws.opensearch_request.return_value = SAMPLE_AGG_RESPONSE
        mod, _ = _load_projects_handler(mock_aws_utils=mock_aws)

        result = mod.handle_list_projects('test-012')

        osd_project = next(
            p for p in result['projects'] if p['name'] == 'OpenSearch Dashboards'
        )
        # Version tags first (descending), then non-version tags
        assert osd_project['tags'] == ['2.19.6', '2.19.5', 'origin/main']

    def test_mixed_version_and_branch_tags(self):
        mock_aws = MagicMock()
        agg_with_branches = {
            'aggregations': {
                'projects': {
                    'buckets': [
                        {
                            'key': 'OpenSearch',
                            'doc_count': 15,
                            'tags': {
                                'buckets': [
                                    {'key': '2.19.6', 'doc_count': 8},
                                    {'key': 'origin/2.19', 'doc_count': 5},
                                    {'key': 'origin/3.7', 'doc_count': 3},
                                    {'key': 'origin/main', 'doc_count': 2},
                                ],
                            },
                        },
                    ],
                },
            },
        }
        mock_aws.opensearch_request.return_value = agg_with_branches
        mod, _ = _load_projects_handler(mock_aws_utils=mock_aws)

        result = mod.handle_list_projects('test-013')

        os_project = result['projects'][0]
        # 2.19.6 is a version (sorts first), then non-version tags
        assert os_project['tags'][0] == '2.19.6'
        # Non-version tags come after
        assert 'origin/2.19' in os_project['tags']
        assert 'origin/3.7' in os_project['tags']
        assert 'origin/main' in os_project['tags']


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestAggregationQueryFailure:
    """Test aggregation query failure returns error response."""

    def test_opensearch_error_returns_error_response(self):
        mock_aws = MagicMock()
        mock_aws.opensearch_request.side_effect = Exception(
            'OpenSearch request failed: 500 - Internal Server Error',
        )
        mod, _ = _load_projects_handler(mock_aws_utils=mock_aws)

        result = mod.handle_list_projects('test-020')

        assert result['status'] == 'error'
        assert 'message' in result
        assert 'Failed to list projects' in result['message']

    def test_connection_error_returns_error_response(self):
        mock_aws = MagicMock()
        mock_aws.opensearch_request.side_effect = ConnectionError('Connection refused')
        mod, _ = _load_projects_handler(mock_aws_utils=mock_aws)

        result = mod.handle_list_projects('test-021')

        assert result['status'] == 'error'
        assert 'message' in result


# ---------------------------------------------------------------------------
# Empty results
# ---------------------------------------------------------------------------


class TestEmptyAggregation:
    """Test empty aggregation results."""

    def test_no_buckets_returns_empty_projects(self):
        mock_aws = MagicMock()
        mock_aws.opensearch_request.return_value = {
            'aggregations': {
                'projects': {
                    'buckets': [],
                },
            },
        }
        mod, _ = _load_projects_handler(mock_aws_utils=mock_aws)

        result = mod.handle_list_projects('test-030')

        assert result['status'] == 'success'
        assert result['project_count'] == 0
        assert result['projects'] == []
