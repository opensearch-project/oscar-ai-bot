# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Smoke tests for ticket-related action group definitions.

Validates: Requirements 3.1, 3.2, 3.3, 3.4, 7.1
"""

import importlib
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Path to the action_groups module
_AGENTS_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'agents', 'security-advisories',
)


def _load_action_groups():
    """Import action_groups with mocked aws_cdk."""
    if _AGENTS_PATH not in sys.path:
        sys.path.insert(0, _AGENTS_PATH)

    # Mock aws_cdk.aws_bedrock so we can inspect the raw values passed to constructors
    mock_bedrock = MagicMock()

    # Make CDK construct calls return plain dicts for easy inspection
    mock_bedrock.CfnAgent.FunctionProperty = lambda **kwargs: kwargs
    mock_bedrock.CfnAgent.ParameterDetailProperty = lambda **kwargs: kwargs
    mock_bedrock.CfnAgent.AgentActionGroupProperty = lambda **kwargs: kwargs
    mock_bedrock.CfnAgent.ActionGroupExecutorProperty = lambda **kwargs: kwargs
    mock_bedrock.CfnAgent.FunctionSchemaProperty = lambda **kwargs: kwargs

    mock_cdk = MagicMock()
    mock_cdk.aws_bedrock = mock_bedrock

    with patch.dict('sys.modules', {
        'aws_cdk': mock_cdk,
        'aws_cdk.aws_bedrock': mock_bedrock,
    }):
        spec = importlib.util.spec_from_file_location(
            'sa_action_groups',
            os.path.join(_AGENTS_PATH, 'action_groups.py'),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod


@pytest.fixture(scope="module")
def action_groups():
    """Load action groups once for all tests in this module."""
    mod = _load_action_groups()
    return mod.get_action_groups('arn:aws:lambda:us-east-1:123:function:test')


@pytest.fixture(scope="module")
def functions(action_groups):
    """Extract the functions list from the first (privileged) action group."""
    ag = action_groups[0]
    return ag['function_schema']['functions']


@pytest.fixture(scope="module")
def query_tickets_func(functions):
    """Find the query_tickets function definition."""
    matches = [f for f in functions if f['name'] == 'query_tickets']
    assert len(matches) == 1, "Expected exactly one query_tickets function"
    return matches[0]


@pytest.fixture(scope="module")
def list_ticket_projects_func(functions):
    """Find the list_ticket_projects function definition."""
    matches = [f for f in functions if f['name'] == 'list_ticket_projects']
    assert len(matches) == 1, "Expected exactly one list_ticket_projects function"
    return matches[0]


class TestQueryTicketsFunction:
    """Requirement 3.1: query_tickets function exists with correct definition."""

    def test_function_exists(self, query_tickets_func):
        assert query_tickets_func['name'] == 'query_tickets'

    def test_function_has_description(self, query_tickets_func):
        desc = query_tickets_func['description']
        assert 'ticket' in desc.lower()
        assert 'CVE' in desc or 'cve' in desc.lower()

    def test_cve_id_parameter_exists(self, query_tickets_func):
        """Requirement 3.2: cve_id parameter of type string, optional."""
        params = query_tickets_func['parameters']
        assert 'cve_id' in params

    def test_cve_id_parameter_type(self, query_tickets_func):
        params = query_tickets_func['parameters']
        assert params['cve_id']['type'] == 'string'

    def test_cve_id_parameter_not_required(self, query_tickets_func):
        params = query_tickets_func['parameters']
        assert params['cve_id']['required'] is False

    def test_project_name_parameter_exists(self, query_tickets_func):
        """Requirement 3.3: project_name parameter of type string, optional."""
        params = query_tickets_func['parameters']
        assert 'project_name' in params

    def test_project_name_parameter_type(self, query_tickets_func):
        params = query_tickets_func['parameters']
        assert params['project_name']['type'] == 'string'

    def test_project_name_parameter_not_required(self, query_tickets_func):
        params = query_tickets_func['parameters']
        assert params['project_name']['required'] is False

    def test_branch_parameter_exists(self, query_tickets_func):
        """Requirement 3.4: branch parameter of type string, optional."""
        params = query_tickets_func['parameters']
        assert 'branch' in params

    def test_branch_parameter_type(self, query_tickets_func):
        params = query_tickets_func['parameters']
        assert params['branch']['type'] == 'string'

    def test_branch_parameter_not_required(self, query_tickets_func):
        params = query_tickets_func['parameters']
        assert params['branch']['required'] is False


class TestListTicketProjectsFunction:
    """Requirement 7.1: list_ticket_projects function exists with correct definition."""

    def test_function_exists(self, list_ticket_projects_func):
        assert list_ticket_projects_func['name'] == 'list_ticket_projects'

    def test_function_has_description(self, list_ticket_projects_func):
        desc = list_ticket_projects_func['description']
        assert 'project' in desc.lower()
        assert 'ticket' in desc.lower()

    def test_empty_parameters(self, list_ticket_projects_func):
        params = list_ticket_projects_func['parameters']
        assert params == {}
