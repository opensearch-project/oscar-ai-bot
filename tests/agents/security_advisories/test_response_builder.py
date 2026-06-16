# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for security advisories response_builder.py.

These tests verify the Bedrock response envelope structure and
JSON serialization of result dicts.

_Requirements: 3.6_
"""

import importlib
import json
import os
from unittest.mock import MagicMock, patch

# Path to the real response_builder module
_LAMBDA_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'agents', 'security_advisories', 'lambda',
)


def _load_response_builder(message_version='1.0'):
    """Import response_builder from security_advisories lambda, fresh each time.

    Mocks the config module so tests don't depend on real config/secrets.
    """
    mock_config = MagicMock()
    mock_config.bedrock_message_version = message_version

    mock_config_module = MagicMock()
    mock_config_module.config = mock_config

    with patch.dict('sys.modules', {'config': mock_config_module}):
        spec = importlib.util.spec_from_file_location(
            'sa_response_builder', os.path.join(_LAMBDA_PATH, 'response_builder.py'),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod


# ---------------------------------------------------------------------------
# Bedrock response envelope structure tests
# ---------------------------------------------------------------------------


class TestBedrockResponseEnvelopeStructure:
    """Test Bedrock response envelope structure.

    Validates: messageVersion, response, actionGroup, function, functionResponse.
    """

    def test_response_contains_message_version(self):
        mod = _load_response_builder()
        event = {'actionGroup': 'securityAdvisoriesActions', 'function': 'query_vulnerabilities'}
        result = {'status': 'success'}

        response = mod.create_response(event, result)

        assert 'messageVersion' in response
        assert response['messageVersion'] == '1.0'

    def test_response_contains_response_key(self):
        mod = _load_response_builder()
        event = {'actionGroup': 'securityAdvisoriesActions', 'function': 'query_vulnerabilities'}
        result = {'status': 'success'}

        response = mod.create_response(event, result)

        assert 'response' in response

    def test_response_contains_action_group(self):
        mod = _load_response_builder()
        event = {'actionGroup': 'securityAdvisoriesActions', 'function': 'query_vulnerabilities'}
        result = {'status': 'success'}

        response = mod.create_response(event, result)

        assert response['response']['actionGroup'] == 'securityAdvisoriesActions'

    def test_response_contains_function(self):
        mod = _load_response_builder()
        event = {'actionGroup': 'securityAdvisoriesActions', 'function': 'query_vulnerabilities'}
        result = {'status': 'success'}

        response = mod.create_response(event, result)

        assert response['response']['function'] == 'query_vulnerabilities'

    def test_response_contains_function_response(self):
        mod = _load_response_builder()
        event = {'actionGroup': 'securityAdvisoriesActions', 'function': 'query_vulnerabilities'}
        result = {'status': 'success'}

        response = mod.create_response(event, result)

        func_response = response['response']['functionResponse']
        assert 'responseBody' in func_response
        assert 'TEXT' in func_response['responseBody']
        assert 'body' in func_response['responseBody']['TEXT']

    def test_function_defaults_to_unknown_when_missing(self):
        mod = _load_response_builder()
        event = {'actionGroup': 'securityAdvisoriesActions'}
        result = {'status': 'success'}

        response = mod.create_response(event, result)

        assert response['response']['function'] == 'unknown'

    def test_action_group_is_none_when_missing(self):
        mod = _load_response_builder()
        event = {'function': 'query_vulnerabilities'}
        result = {'status': 'success'}

        response = mod.create_response(event, result)

        assert response['response']['actionGroup'] is None

    def test_custom_message_version(self):
        mod = _load_response_builder(message_version='2.0')
        event = {'actionGroup': 'securityAdvisoriesActions', 'function': 'list_projects'}
        result = {'status': 'success'}

        response = mod.create_response(event, result)

        assert response['messageVersion'] == '2.0'


# ---------------------------------------------------------------------------
# JSON serialization tests
# ---------------------------------------------------------------------------


class TestJsonSerializationOfResult:
    """Test JSON serialization of result dict."""

    def test_result_dict_serialized_to_json_string(self):
        mod = _load_response_builder()
        event = {'actionGroup': 'securityAdvisoriesActions', 'function': 'query_vulnerabilities'}
        result = {'status': 'success', 'result_count': 3}

        response = mod.create_response(event, result)

        body = response['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        assert parsed == {'status': 'success', 'result_count': 3}

    def test_nested_result_dict_serialized(self):
        mod = _load_response_builder()
        event = {'actionGroup': 'securityAdvisoriesActions', 'function': 'query_vulnerabilities'}
        result = {
            'status': 'success',
            'results': [
                {
                    'project': {'name': 'OpenSearch', 'tag': '2.19.6'},
                    'severity_summary': {'CRITICAL': 1, 'HIGH': 2},
                },
            ],
        }

        response = mod.create_response(event, result)

        body = response['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        assert parsed['results'][0]['project']['name'] == 'OpenSearch'
        assert parsed['results'][0]['severity_summary']['CRITICAL'] == 1

    def test_empty_result_dict_serialized(self):
        mod = _load_response_builder()
        event = {'actionGroup': 'securityAdvisoriesActions', 'function': 'query_vulnerabilities'}
        result = {}

        response = mod.create_response(event, result)

        body = response['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        assert parsed == {}

    def test_result_with_non_serializable_types_uses_default_str(self):
        """Verify that non-JSON-serializable types (e.g., datetime) are handled via default=str."""
        from datetime import datetime

        mod = _load_response_builder()
        event = {'actionGroup': 'securityAdvisoriesActions', 'function': 'query_vulnerabilities'}
        ts = datetime(2024, 1, 15, 10, 30, 0)
        result = {'timestamp': ts}

        response = mod.create_response(event, result)

        body = response['response']['functionResponse']['responseBody']['TEXT']['body']
        parsed = json.loads(body)
        assert parsed['timestamp'] == str(ts)
