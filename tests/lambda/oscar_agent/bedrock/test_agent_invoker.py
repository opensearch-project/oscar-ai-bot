# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for BedrockAgentCore."""

from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import ClientError


@pytest.fixture
def agent_core():
    """Create a BedrockAgentCore with mocked config and boto3 client."""
    with patch('bedrock.agent_invoker.config') as mock_config, \
         patch('bedrock.agent_invoker.boto3') as mock_boto3:
        mock_config.region = 'us-east-1'
        mock_config.oscar_privileged_bedrock_agent_id = 'priv-agent'
        mock_config.oscar_privileged_bedrock_agent_alias_id = 'priv-alias'
        mock_config.oscar_limited_bedrock_agent_id = 'ltd-agent'
        mock_config.oscar_limited_bedrock_agent_alias_id = 'ltd-alias'
        mock_config.agent_timeout = 90
        mock_config.agent_max_retries = 2
        mock_config.log_query_preview_length = 100

        mock_client = Mock()
        mock_boto3.client.return_value = mock_client

        from bedrock.agent_invoker import BedrockAgentCore
        core = BedrockAgentCore(region='us-east-1')
        core.client = mock_client
        yield core, mock_client


class TestCreateAgentRequest:

    def test_privileged_uses_privileged_ids(self, agent_core):
        core, _ = agent_core
        req = core.create_agent_request('hello', privilege=True)
        assert req['agentId'] == 'priv-agent'
        assert req['agentAliasId'] == 'priv-alias'

    def test_limited_uses_limited_ids(self, agent_core):
        core, _ = agent_core
        req = core.create_agent_request('hello', privilege=False)
        assert req['agentId'] == 'ltd-agent'
        assert req['agentAliasId'] == 'ltd-alias'

    def test_session_id_passthrough(self, agent_core):
        core, _ = agent_core
        req = core.create_agent_request('hello', privilege=True, session_id='my-session')
        assert req['sessionId'] == 'my-session'

    def test_session_id_generated_when_none(self, agent_core):
        core, _ = agent_core
        req = core.create_agent_request('hello', privilege=True)
        assert req['sessionId'].startswith('session-')

    def test_enable_trace_always_true(self, agent_core):
        core, _ = agent_core
        req = core.create_agent_request('hello', privilege=True)
        assert req['enableTrace'] is True

    def test_input_text_matches_query(self, agent_core):
        core, _ = agent_core
        req = core.create_agent_request('what is opensearch?', privilege=True)
        assert req['inputText'] == 'what is opensearch?'


class TestInvokeAgent:

    def test_returns_assembled_text(self, agent_core):
        core, mock_client = agent_core
        mock_client.invoke_agent.return_value = {
            'completion': [
                {'chunk': {'bytes': b'Hello '}},
                {'chunk': {'bytes': b'world'}},
            ],
            'sessionId': 'sess-1',
        }
        text, session_id = core.invoke_agent('hi', privilege=True)
        assert text == 'Hello world'
        assert session_id == 'sess-1'

    def test_session_id_from_top_level(self, agent_core):
        """Top-level sessionId takes precedence."""
        core, mock_client = agent_core
        mock_client.invoke_agent.return_value = {
            'completion': [{'chunk': {'bytes': b'response'}}],
            'sessionId': 'top-level-sess',
        }
        _, session_id = core.invoke_agent('hi', privilege=True)
        assert session_id == 'top-level-sess'

    def test_session_id_from_request_when_not_in_response(self, agent_core):
        """Falls back to request session_id when response has none."""
        core, mock_client = agent_core
        mock_client.invoke_agent.return_value = {
            'completion': [{'chunk': {'bytes': b'response'}}],
        }
        _, session_id = core.invoke_agent('hi', privilege=True, session_id='req-sess')
        assert session_id == 'req-sess'

    def test_client_error_reraised(self, agent_core):
        core, mock_client = agent_core
        mock_client.invoke_agent.side_effect = ClientError(
            {'Error': {'Code': 'ThrottlingException', 'Message': 'Rate exceeded'}},
            'InvokeAgent',
        )
        with pytest.raises(ClientError):
            core.invoke_agent('hi', privilege=True)

    def test_generic_exception_reraised(self, agent_core):
        core, mock_client = agent_core
        mock_client.invoke_agent.side_effect = RuntimeError('unexpected')
        with pytest.raises(RuntimeError):
            core.invoke_agent('hi', privilege=True)

    def test_empty_completion_returns_empty_string(self, agent_core):
        core, mock_client = agent_core
        mock_client.invoke_agent.return_value = {
            'completion': [],
            'sessionId': 'sess',
        }
        text, _ = core.invoke_agent('hi', privilege=True, session_id='sess')
        assert text == ''
