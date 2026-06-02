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
    os.path.dirname(__file__), '..', '..', '..', 'agents', 'security_advisories', 'lambda',
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


class TestTagsSortedDescending:
    """**Validates Property 7: List projects output ordering**

    Each project's tags SHALL be sorted in descending semantic version order,
    with version tags before non-version (branch) tags.
    """

    def test_version_tags_before_branch_tags(self):
        mock_aws = MagicMock()
        mock_aws.opensearch_request.return_value = SAMPLE_AGG_RESPONSE
        mod, _ = _load_projects_handler(mock_aws_utils=mock_aws)

        result = mod.handle_list_projects('test-010')

        for project in result['projects']:
            tags = project['tags']
            # Version tags (starting with a digit) should come before branch tags
            saw_branch = False
            for tag in tags:
                if not tag[0].isdigit():
                    saw_branch = True
                elif saw_branch:
                    assert False, (
                        f"Version tag '{tag}' found after branch tag in "
                        f"{project['name']}: {tags}"
                    )

    def test_opensearch_tags_sorted_descending(self):
        mock_aws = MagicMock()
        mock_aws.opensearch_request.return_value = SAMPLE_AGG_RESPONSE
        mod, _ = _load_projects_handler(mock_aws_utils=mock_aws)

        result = mod.handle_list_projects('test-011')

        # Find the OpenSearch project
        os_project = next(p for p in result['projects'] if p['name'] == 'OpenSearch')
        assert os_project['tags'] == ['2.19.6', '2.19.5', '2.18.0']

    def test_dashboards_tags_sorted_descending(self):
        mock_aws = MagicMock()
        mock_aws.opensearch_request.return_value = SAMPLE_AGG_RESPONSE
        mod, _ = _load_projects_handler(mock_aws_utils=mock_aws)

        result = mod.handle_list_projects('test-012')

        osd_project = next(
            (p for p in result['projects'] if p['name'] == 'OpenSearch Dashboards'),
        )
        # Version tags sorted descending by semver, branch tags at the end
        assert osd_project['tags'] == ['2.19.6', '2.19.5', 'origin/main']


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
