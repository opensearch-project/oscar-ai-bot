# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for security advisories tickets_query_builder.py.

These tests verify DSL query construction for the tickets index,
including filtering by CVE ID, project name, branch, and the
no-parameters case where only the mandatory status filter applies.

Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7
"""

import importlib
import os
import sys
from unittest.mock import MagicMock, patch

# Path to the real tickets_query_builder module
_LAMBDA_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', '..', 'agents', 'security-advisories', 'lambda',
)


def _load_tickets_query_builder():
    """Import tickets_query_builder from security_advisories lambda with mocked deps.

    Returns:
        The loaded module with mocked aws_utils and config.
    """
    if _LAMBDA_PATH not in sys.path:
        sys.path.insert(0, _LAMBDA_PATH)

    mock_aws_utils = MagicMock()
    mock_config_module = MagicMock()

    with patch.dict('sys.modules', {
        'aws_utils': mock_aws_utils,
        'config': mock_config_module,
    }):
        spec = importlib.util.spec_from_file_location(
            'sa_tickets_query_builder_unit',
            os.path.join(_LAMBDA_PATH, 'tickets_query_builder.py'),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

    return mod


# ---------------------------------------------------------------------------
# Test: build_tickets_query with cve_id only
# ---------------------------------------------------------------------------


class TestBuildTicketsQueryCveIdOnly:
    """Test build_tickets_query with only cve_id parameter."""

    def test_cve_id_only_produces_status_and_cve_filters(self):
        """Validates: Requirements 4.1, 4.2"""
        mod = _load_tickets_query_builder()

        result = mod.build_tickets_query(cve_id='CVE-2026-27903')

        assert result['size'] == 1
        assert result['_source'] == ['ticketId']
        assert result['sort'] == [{'timestamp.created': {'order': 'desc'}}]

        filters = result['query']['bool']['filter']
        assert {'term': {'status': 'Assigned'}} in filters

        expected_cve_filter = {
            'bool': {
                'should': [
                    {'term': {'cveId': 'CVE-2026-27903'}},
                    {'term': {'cveIds.keyword': 'CVE-2026-27903'}},
                ],
                'minimum_should_match': 1,
            },
        }
        assert expected_cve_filter in filters
        assert len(filters) == 2


# ---------------------------------------------------------------------------
# Test: build_tickets_query with project_name only
# ---------------------------------------------------------------------------


class TestBuildTicketsQueryProjectNameOnly:
    """Test build_tickets_query with only project_name parameter."""

    def test_project_name_only_produces_status_and_project_filters(self):
        """Validates: Requirements 4.1, 4.3"""
        mod = _load_tickets_query_builder()

        result = mod.build_tickets_query(project_name='OpenSearch Dashboards')

        assert result['size'] == 1000
        assert result['_source'] == ['ticketId']
        assert result['sort'] == [{'timestamp.created': {'order': 'desc'}}]

        filters = result['query']['bool']['filter']
        assert {'term': {'status': 'Assigned'}} in filters
        assert {'term': {'projectName': 'OpenSearch Dashboards'}} in filters
        assert len(filters) == 2


# ---------------------------------------------------------------------------
# Test: build_tickets_query with branch only
# ---------------------------------------------------------------------------


class TestBuildTicketsQueryBranchOnly:
    """Test build_tickets_query with only branch parameter."""

    def test_branch_only_produces_status_and_branches_filters(self):
        """Validates: Requirements 4.1, 4.4"""
        mod = _load_tickets_query_builder()

        result = mod.build_tickets_query(branch='origin/main')

        assert result['size'] == 1000
        assert result['_source'] == ['ticketId']
        assert result['sort'] == [{'timestamp.created': {'order': 'desc'}}]

        filters = result['query']['bool']['filter']
        assert {'term': {'status': 'Assigned'}} in filters
        assert {'term': {'branches': 'origin/main'}} in filters
        assert len(filters) == 2


# ---------------------------------------------------------------------------
# Test: build_tickets_query with all three parameters
# ---------------------------------------------------------------------------


class TestBuildTicketsQueryAllParams:
    """Test build_tickets_query with cve_id, project_name, and branch combined."""

    def test_all_params_produces_four_filters(self):
        """Validates: Requirements 4.1, 4.2, 4.3, 4.4"""
        mod = _load_tickets_query_builder()

        result = mod.build_tickets_query(
            cve_id='CVE-2026-27903',
            project_name='OpenSearch',
            branch='origin/3.7',
        )

        assert result['size'] == 1
        assert result['_source'] == ['ticketId']
        assert result['sort'] == [{'timestamp.created': {'order': 'desc'}}]

        filters = result['query']['bool']['filter']
        assert {'term': {'status': 'Assigned'}} in filters

        expected_cve_filter = {
            'bool': {
                'should': [
                    {'term': {'cveId': 'CVE-2026-27903'}},
                    {'term': {'cveIds.keyword': 'CVE-2026-27903'}},
                ],
                'minimum_should_match': 1,
            },
        }
        assert expected_cve_filter in filters
        assert {'term': {'projectName': 'OpenSearch'}} in filters
        assert {'term': {'branches': 'origin/3.7'}} in filters
        assert len(filters) == 4


# ---------------------------------------------------------------------------
# Test: build_tickets_query with no parameters
# ---------------------------------------------------------------------------


class TestBuildTicketsQueryNoParams:
    """Test build_tickets_query with no parameters applies only the status filter."""

    def test_no_params_produces_only_status_filter(self):
        """Validates: Requirements 4.1, 4.5"""
        mod = _load_tickets_query_builder()

        result = mod.build_tickets_query()

        assert result['size'] == 1000
        assert result['_source'] == ['ticketId']
        assert result['sort'] == [{'timestamp.created': {'order': 'desc'}}]

        filters = result['query']['bool']['filter']
        assert {'term': {'status': 'Assigned'}} in filters
        assert len(filters) == 1
        assert 'must' not in result['query']['bool']


# ---------------------------------------------------------------------------
# Test: build_list_projects_query
# ---------------------------------------------------------------------------


class TestBuildListProjectsQuery:
    """Test build_list_projects_query returns correct structure."""

    def test_list_projects_query_has_correct_structure(self):
        """Validates: Requirements 4.1, 4.5, 4.6, 4.7"""
        mod = _load_tickets_query_builder()

        result = mod.build_list_projects_query()

        assert result['size'] == 1000
        assert result['_source'] == ['projectName']
        assert result['collapse'] == {'field': 'projectName'}

        query = result['query']['bool']
        assert query['must'] == {'match_all': {}}
        filters = query['filter']
        assert {'term': {'status': 'Assigned'}} in filters
        assert len(filters) == 1
