# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for security advisories lambda_function.py (request router).

These tests verify routing to handlers, parameter parsing, unknown function
handling, and the Bedrock response envelope structure.

_Requirements: 2.1, 4.3, 6.1_
"""

import importlib
import json
import os
from unittest.mock import MagicMock, patch

# Path to the real lambda_function module
_LAMBDA_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'agents', 'security_advisories', 'lambda',
)


def _make_mock_config(message_version='1.0'):
    """Create a mock config module."""
    mock_config = MagicMock()
    mock_config.bedrock_message_version = message_version
    mock_config_module = MagicMock()
    mock_config_module.config = mock_config
    return mock_config_module


def _make_mock_response_builder(message_version='1.0'):
    """Create a mock response_builder module that mimics real create_response."""
    mock_mod = MagicMock()

    def fake_create_response(event, result):
        return {
            'messageVersion': message_version,
            'response': {
                'actionGroup': event.get('actionGroup'),
                'function': event.get('function', 'unknown'),
                'functionResponse': {
                    'responseBody': {
                        'TEXT': {
                            'body': json.dumps(result, default=str),
                        },
                    },
                },
            },
        }

    mock_mod.create_response = MagicMock(side_effect=fake_create_response)
    return mock_mod


def _load_lambda_function(
    mock_config=None,
    mock_vuln_handler=None,
    mock_proj_handler=None,
    mock_response_builder=None,
):
    """Import lambda_function with mocked dependencies."""
    if mock_config is None:
        mock_config = _make_mock_config()
    if mock_vuln_handler is None:
        mock_vuln_handler = MagicMock()
        mock_vuln_handler.handle_query_vulnerabilities = MagicMock(
            return_value={'status': 'success', 'results': []},
        )
    if mock_proj_handler is None:
        mock_proj_handler = MagicMock()
        mock_proj_handler.handle_list_projects = MagicMock(
            return_value={'status': 'success', 'projects': []},
        )
    if mock_response_builder is None:
        mock_response_builder = _make_mock_response_builder()

    with patch.dict('sys.modules', {
        'config': mock_config,
        'vulnerabilities_handler': mock_vuln_handler,
        'projects_handler': mock_proj_handler,
        'response_builder': mock_response_builder,
    }):
        spec = importlib.util.spec_from_file_location(
            'sa_lambda_function',
            os.path.join(_LAMBDA_PATH, 'lambda_function.py'),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod, mock_vuln_handler, mock_proj_handler, mock_response_builder


# ---------------------------------------------------------------------------
# Routing tests
# ---------------------------------------------------------------------------


class TestRoutingToQueryVulnerabilities:
    """Test routing to query_vulnerabilities handler."""

    def test_routes_to_vulnerabilities_handler(self):
        mock_vuln = MagicMock()
        mock_vuln.handle_query_vulnerabilities = MagicMock(
            return_value={'status': 'success', 'results': []},
        )
        mod, _, _, _ = _load_lambda_function(mock_vuln_handler=mock_vuln)

        event = {
            'function': 'query_vulnerabilities',
            'actionGroup': 'securityAdvisoriesActions',
            'parameters': [
                {'name': 'query', 'value': 'Show critical CVEs'},
            ],
        }
        mod.lambda_handler(event, None)

        mock_vuln.handle_query_vulnerabilities.assert_called_once()

    def test_passes_parsed_params_to_handler(self):
        mock_vuln = MagicMock()
        mock_vuln.handle_query_vulnerabilities = MagicMock(
            return_value={'status': 'success', 'results': []},
        )
        mod, _, _, _ = _load_lambda_function(mock_vuln_handler=mock_vuln)

        event = {
            'function': 'query_vulnerabilities',
            'actionGroup': 'securityAdvisoriesActions',
            'parameters': [
                {'name': 'query', 'value': 'Show critical CVEs'},
                {'name': 'version', 'value': '2.19.6'},
                {'name': 'project_name', 'value': 'OpenSearch'},
            ],
        }
        mod.lambda_handler(event, None)

        call_args = mock_vuln.handle_query_vulnerabilities.call_args
        params = call_args[0][0]
        assert params['query'] == 'Show critical CVEs'
        assert params['version'] == '2.19.6'
        assert params['project_name'] == 'OpenSearch'


class TestRoutingToListProjects:
    """Test routing to list_projects handler."""

    def test_routes_to_projects_handler(self):
        mock_proj = MagicMock()
        mock_proj.handle_list_projects = MagicMock(
            return_value={'status': 'success', 'projects': []},
        )
        mod, _, _, _ = _load_lambda_function(mock_proj_handler=mock_proj)

        event = {
            'function': 'list_projects',
            'actionGroup': 'securityAdvisoriesActions',
            'parameters': [],
        }
        mod.lambda_handler(event, None)

        mock_proj.handle_list_projects.assert_called_once()

    def test_list_projects_receives_request_id(self):
        mock_proj = MagicMock()
        mock_proj.handle_list_projects = MagicMock(
            return_value={'status': 'success', 'projects': []},
        )
        mod, _, _, _ = _load_lambda_function(mock_proj_handler=mock_proj)

        event = {
            'function': 'list_projects',
            'actionGroup': 'securityAdvisoriesActions',
            'parameters': [],
        }
        mod.lambda_handler(event, None)

        call_args = mock_proj.handle_list_projects.call_args
        request_id = call_args[0][0]
        assert isinstance(request_id, str)
        assert len(request_id) > 0


# ---------------------------------------------------------------------------
# Unknown function handling
# ---------------------------------------------------------------------------


class TestUnknownFunctionHandling:
    """Test unknown function name returns error with available_functions."""

    def test_unknown_function_returns_error(self):
        mod, _, _, _ = _load_lambda_function()

        event = {
            'function': 'nonexistent_function',
            'actionGroup': 'securityAdvisoriesActions',
            'parameters': [],
        }
        response = mod.lambda_handler(event, None)

        body = json.loads(
            response['response']['functionResponse']['responseBody']['TEXT']['body'],
        )
        assert body['status'] == 'error'
        assert 'nonexistent_function' in body['message']

    def test_unknown_function_includes_available_functions(self):
        mod, _, _, _ = _load_lambda_function()

        event = {
            'function': 'nonexistent_function',
            'actionGroup': 'securityAdvisoriesActions',
            'parameters': [],
        }
        response = mod.lambda_handler(event, None)

        body = json.loads(
            response['response']['functionResponse']['responseBody']['TEXT']['body'],
        )
        assert 'available_functions' in body
        assert 'query_vulnerabilities' in body['available_functions']
        assert 'list_projects' in body['available_functions']

    def test_empty_function_name_returns_error(self):
        mod, _, _, _ = _load_lambda_function()

        event = {
            'function': '',
            'actionGroup': 'securityAdvisoriesActions',
            'parameters': [],
        }
        response = mod.lambda_handler(event, None)

        body = json.loads(
            response['response']['functionResponse']['responseBody']['TEXT']['body'],
        )
        assert body['status'] == 'error'
        assert 'available_functions' in body


# ---------------------------------------------------------------------------
# Parameter parsing
# ---------------------------------------------------------------------------


class TestParameterParsing:
    """Test parameter parsing from Bedrock event format."""

    def test_parse_parameters_from_list(self):
        mod, _, _, _ = _load_lambda_function()

        params = mod._parse_parameters([
            {'name': 'query', 'value': 'Show CVEs'},
            {'name': 'version', 'value': '2.19.6'},
        ])

        assert params == {'query': 'Show CVEs', 'version': '2.19.6'}

    def test_parse_empty_parameters(self):
        mod, _, _, _ = _load_lambda_function()

        params = mod._parse_parameters([])

        assert params == {}

    def test_parse_ignores_malformed_entries(self):
        mod, _, _, _ = _load_lambda_function()

        params = mod._parse_parameters([
            {'name': 'query', 'value': 'Show CVEs'},
            {'bad_key': 'ignored'},
            'not_a_dict',
        ])

        assert params == {'query': 'Show CVEs'}

    def test_parse_parameters_missing_from_event(self):
        """When parameters key is missing from event, default to empty list."""
        mock_vuln = MagicMock()
        mock_vuln.handle_query_vulnerabilities = MagicMock(
            return_value={'status': 'success', 'results': []},
        )
        mod, _, _, _ = _load_lambda_function(mock_vuln_handler=mock_vuln)

        event = {
            'function': 'query_vulnerabilities',
            'actionGroup': 'securityAdvisoriesActions',
        }
        # Should not raise
        mod.lambda_handler(event, None)

        call_args = mock_vuln.handle_query_vulnerabilities.call_args
        params = call_args[0][0]
        assert params == {}


# ---------------------------------------------------------------------------
# Response envelope
# ---------------------------------------------------------------------------


class TestResponseEnvelope:
    """Test Bedrock response envelope structure."""

    def test_response_has_message_version(self):
        mod, _, _, _ = _load_lambda_function()

        event = {
            'function': 'list_projects',
            'actionGroup': 'securityAdvisoriesActions',
            'parameters': [],
        }
        response = mod.lambda_handler(event, None)

        assert 'messageVersion' in response
        assert response['messageVersion'] == '1.0'

    def test_response_has_action_group(self):
        mod, _, _, _ = _load_lambda_function()

        event = {
            'function': 'list_projects',
            'actionGroup': 'securityAdvisoriesActions',
            'parameters': [],
        }
        response = mod.lambda_handler(event, None)

        assert response['response']['actionGroup'] == 'securityAdvisoriesActions'

    def test_response_has_function_name(self):
        mod, _, _, _ = _load_lambda_function()

        event = {
            'function': 'list_projects',
            'actionGroup': 'securityAdvisoriesActions',
            'parameters': [],
        }
        response = mod.lambda_handler(event, None)

        assert response['response']['function'] == 'list_projects'

    def test_response_body_is_json_string(self):
        mod, _, _, _ = _load_lambda_function()

        event = {
            'function': 'list_projects',
            'actionGroup': 'securityAdvisoriesActions',
            'parameters': [],
        }
        response = mod.lambda_handler(event, None)

        body_str = response['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body_str)
        assert isinstance(parsed, dict)

    def test_create_response_called_with_event_and_result(self):
        mock_rb = _make_mock_response_builder()
        mod, _, _, _ = _load_lambda_function(mock_response_builder=mock_rb)

        event = {
            'function': 'list_projects',
            'actionGroup': 'securityAdvisoriesActions',
            'parameters': [],
        }
        mod.lambda_handler(event, None)

        mock_rb.create_response.assert_called_once()
        call_args = mock_rb.create_response.call_args
        assert call_args[0][0] == event


# ---------------------------------------------------------------------------
# Lambda context handling
# ---------------------------------------------------------------------------


class TestLambdaContextHandling:
    """Test Lambda context request ID handling."""

    def test_sets_request_id_from_context(self):
        mock_config = _make_mock_config()
        mod, _, _, _ = _load_lambda_function(mock_config=mock_config)

        mock_context = MagicMock()
        mock_context.aws_request_id = 'lambda-req-123'

        event = {
            'function': 'list_projects',
            'actionGroup': 'securityAdvisoriesActions',
            'parameters': [],
        }
        mod.lambda_handler(event, mock_context)

        mock_config.config.set_request_id.assert_called_once_with('lambda-req-123')

    def test_handles_none_context(self):
        mod, _, _, _ = _load_lambda_function()

        event = {
            'function': 'list_projects',
            'actionGroup': 'securityAdvisoriesActions',
            'parameters': [],
        }
        # Should not raise
        response = mod.lambda_handler(event, None)

        assert 'messageVersion' in response
