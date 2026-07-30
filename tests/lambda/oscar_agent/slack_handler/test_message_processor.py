# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for MessageProcessor."""

import os
import sys
from unittest.mock import Mock, patch

from slack_handler.message_processor import MessageProcessor

# Get the mock config from conftest
mock_config = sys.modules['config'].config


def _make_processor(**overrides):
    """Create a MessageProcessor with mocked dependencies."""
    defaults = dict(
        storage=Mock(),
        oscar_agent=Mock(),
        reaction_manager=Mock(),
        timeout_handler=Mock(),
    )
    defaults.update(overrides)
    return MessageProcessor(**defaults)


class TestExtractQuery:

    def test_removes_mention(self):
        mp = _make_processor()
        assert mp.extract_query('<@U123ABC> what is opensearch?') == 'what is opensearch?'

    def test_removes_multiple_mentions(self):
        mp = _make_processor()
        assert mp.extract_query('<@U1> <@U2> hello') == 'hello'

    def test_no_mention_passthrough(self):
        mp = _make_processor()
        assert mp.extract_query('hello world') == 'hello world'

    def test_whitespace_stripped(self):
        mp = _make_processor()
        assert mp.extract_query('  <@U1>  hello  ') == 'hello'


class TestAddUserContextToQuery:

    def test_prefixes_user_id(self):
        mp = _make_processor()
        result = mp.add_user_context_to_query('original query', 'U123')
        assert result == '[USER_ID: U123] original query'


class TestIsFullyAuthorizedUser:

    def test_authorized_true(self):
        mp = _make_processor()
        assert mp.is_fully_authorized_user('U_ADMIN') is True

    def test_unauthorized_false(self):
        mp = _make_processor()
        assert mp.is_fully_authorized_user('U_NOBODY') is False


class TestHandleConfirmationDetection:

    def test_strips_marker_and_adds_reaction(self):
        reaction_mgr = Mock()
        mp = _make_processor(reaction_manager=reaction_mgr)
        result = mp._handle_confirmation_detection(
            '[CONFIRMATION_REQUIRED] Please confirm', 'C123', 'ts1',
        )
        assert '[CONFIRMATION_REQUIRED]' not in result
        assert 'Please confirm' in result
        reaction_mgr.manage_reactions.assert_called_once()

    def test_no_marker_no_reaction(self):
        reaction_mgr = Mock()
        mp = _make_processor(reaction_manager=reaction_mgr)
        result = mp._handle_confirmation_detection('clean response', 'C123', 'ts1')
        assert result == 'clean response'
        reaction_mgr.manage_reactions.assert_not_called()


class TestProcessMessage:

    def _setup(self):

        storage = Mock()
        storage.get_context.return_value = {'session_id': 'sess1', 'history': []}
        storage.get_context_for_query.return_value = ''

        timeout_handler = Mock()
        timeout_handler.query_agent_with_timeout.return_value = ('Agent response', 'sess2')

        mp = _make_processor(
            storage=storage,
            reaction_manager=Mock(),
            timeout_handler=timeout_handler,
        )
        mp._has_identity_mapping = Mock(return_value=True)
        say = Mock()
        return mp, storage, say

    def test_happy_path(self):
        mp, storage, say = self._setup()
        mp.process_message('C_ALLOWED', 'tts', 'U_ADMIN', '<@BOT> hello', say, message_ts='mts')

        say.assert_called_once()
        mp.reaction_manager.manage_reactions.assert_any_call(
            'C_ALLOWED', 'mts',
            add_reaction='white_check_mark',
            remove_reaction=['thinking_face', 'hourglass_flowing_sand'],
        )

    def test_empty_agent_response_sends_fallback(self):
        mp, _, say = self._setup()
        mp.timeout_handler.query_agent_with_timeout.return_value = ('', 'sess2')

        mp.process_message('C_ALLOWED', 'tts', 'U_ADMIN', '<@BOT> hello', say, message_ts='mts')

        sent_text = say.call_args[1]['text']
        assert 'trouble generating' in sent_text

    def test_none_response_returns_early(self):
        """When agent returns None response (timeout or otherwise), method returns early."""
        mp, _, say = self._setup()
        mp.timeout_handler.query_agent_with_timeout.return_value = (None, 'sess2')

        mp.process_message('C_ALLOWED', 'tts', 'U_ADMIN', '<@BOT> hello', say, message_ts='mts')

        say.assert_not_called()

    def test_timeout_returns_early(self):
        mp, _, say = self._setup()
        mp.timeout_handler.query_agent_with_timeout.return_value = (None, None)

        mp.process_message('C_ALLOWED', 'tts', 'U_ADMIN', '<@BOT> hello', say, message_ts='mts')

        say.assert_not_called()

    def test_error_sends_friendly_message(self):
        mp, _, say = self._setup()
        mp.timeout_handler.query_agent_with_timeout.side_effect = RuntimeError('boom')

        mp.process_message('C_ALLOWED', 'tts', 'U_ADMIN', '<@BOT> hello', say, message_ts='mts')

        assert say.call_count >= 1
        mp.reaction_manager.manage_reactions.assert_any_call(
            'C_ALLOWED', 'mts',
            add_reaction='x',
            remove_reaction=['thinking_face', 'hourglass_flowing_sand'],
        )

    def test_throttle_error_message(self):
        mp, _, say = self._setup()
        mp.timeout_handler.query_agent_with_timeout.side_effect = RuntimeError('throttling error')

        mp.process_message('C_ALLOWED', 'tts', 'U_ADMIN', '<@BOT> hello', say, message_ts='mts')

        sent_text = say.call_args[1]['text']
        assert 'high load' in sent_text

    def test_slash_command_uses_text_directly(self):
        mp, _, say = self._setup()
        mp.process_message('C_ALLOWED', 'tts', 'U_ADMIN', 'pre-formatted query', say,
                           message_ts='mts', slash_command='announce')

        query = mp.timeout_handler.query_agent_with_timeout.call_args[0][1]
        assert 'pre-formatted query' in query

    def test_skip_context_storage(self):
        mp, storage, say = self._setup()
        mp.process_message('C_ALLOWED', 'tts', 'U_ADMIN', '<@BOT> hello', say,
                           message_ts='mts', skip_context_storage=True)

        storage.update_context.assert_not_called()


class TestHasIdentityMapping:

    @patch.dict(os.environ, {"ENVIRONMENT": ""})
    def test_returns_true_when_no_workspace_tables(self):
        mp = _make_processor()
        assert mp._has_identity_mapping("U123") is True

    @patch.dict(os.environ, {"ENVIRONMENT": "dev", "SLACK_WORKSPACE_IDS": "W1"})
    @patch("slack_handler.message_processor.boto3")
    def test_returns_true_when_active_mapping_exists(self, mock_boto3):
        table = Mock()
        table.query.return_value = {"Items": [{"status": "active", "github_handle": "user1"}]}
        mock_boto3.resource.return_value.Table.return_value = table

        mp = _make_processor()
        assert mp._has_identity_mapping("U123") is True

    @patch.dict(os.environ, {"ENVIRONMENT": "dev", "SLACK_WORKSPACE_IDS": "W1"})
    @patch("slack_handler.message_processor.boto3")
    def test_returns_false_when_no_active_mapping(self, mock_boto3):
        table = Mock()
        table.query.return_value = {"Items": [{"status": "revoked"}]}
        mock_boto3.resource.return_value.Table.return_value = table

        mp = _make_processor()
        assert mp._has_identity_mapping("U123") is False

    @patch.dict(os.environ, {"ENVIRONMENT": "dev", "SLACK_WORKSPACE_IDS": "W1"})
    @patch("slack_handler.message_processor.boto3")
    def test_returns_false_when_no_items(self, mock_boto3):
        table = Mock()
        table.query.return_value = {"Items": []}
        mock_boto3.resource.return_value.Table.return_value = table

        mp = _make_processor()
        assert mp._has_identity_mapping("U123") is False


class TestHandleLinkGithubViaDm:

    @patch.dict(os.environ, {"ENVIRONMENT": ""})
    def test_not_configured(self):
        mp = _make_processor(reaction_manager=Mock())
        say = Mock()
        mp._handle_link_github_via_dm("U1", "C1", "ts1", "rts1", say)
        say.assert_called_once()
        assert "not configured" in say.call_args[1]["text"]

    @patch.dict(os.environ, {"ENVIRONMENT": "dev", "SLACK_WORKSPACE_IDS": "W1"})
    @patch("slack_handler.message_processor.boto3")
    def test_already_linked(self, mock_boto3):
        table = Mock()
        table.query.return_value = {"Items": [{"status": "active", "github_handle": "octocat"}]}
        mock_boto3.resource.return_value.Table.return_value = table

        mp = _make_processor(reaction_manager=Mock())
        say = Mock()
        mp._handle_link_github_via_dm("U1", "C1", "ts1", "rts1", say)
        assert "octocat" in say.call_args[1]["text"]
        mp.reaction_manager.manage_reactions.assert_called_with(
            "C1", "rts1", add_reaction="white_check_mark", remove_reaction="thinking_face"
        )

    @patch.dict(os.environ, {"ENVIRONMENT": "dev", "SLACK_WORKSPACE_IDS": "W1"})
    @patch("slack_handler.message_processor.boto3")
    @patch("slack_handler.message_processor.WebClient")
    def test_sends_oauth_link_via_dm(self, mock_webclient_cls, mock_boto3):
        table = Mock()
        table.query.return_value = {"Items": []}
        mock_boto3.resource.return_value.Table.return_value = table

        mock_client = Mock()
        mock_webclient_cls.return_value = mock_client
        mp = _make_processor(reaction_manager=Mock())
        mock_config.github_oauth_client_id = "test-client-id"
        mock_config.oauth_callback_url = "https://example.com/callback"
        mock_config.oauth_state_secret = "test-signing-secret"
        mock_config.slack_bot_token = "xoxb-test"
        say = Mock()
        mp._handle_link_github_via_dm("U1", "C1", "ts1", "rts1", say)

        assert "DMs" in say.call_args[1]["text"] or "Check" in say.call_args[1]["text"]

    @patch.dict(os.environ, {"ENVIRONMENT": "dev", "SLACK_WORKSPACE_IDS": "W1"})
    @patch("slack_handler.message_processor.boto3")
    def test_dm_failure_fallback(self, mock_boto3):
        table = Mock()
        table.query.return_value = {"Items": []}
        mock_boto3.resource.return_value.Table.return_value = table

        with patch("slack_sdk.WebClient") as mock_wc:
            mock_wc.return_value.chat_postMessage.side_effect = Exception("DM failed")
            mp = _make_processor(reaction_manager=Mock())
            mock_config.github_oauth_client_id = "cid"
            mock_config.oauth_callback_url = "https://cb.com"
            mock_config.oauth_state_secret = "test-signing-secret"
            mock_config.slack_bot_token = "xoxb-test"
            say = Mock()
            mp._handle_link_github_via_dm("U1", "C1", "ts1", "rts1", say)

        assert "Failed" in say.call_args[1]["text"] or "oscar-link-github" in say.call_args[1]["text"]
        mp.reaction_manager.manage_reactions.assert_called_with(
            "C1", "rts1", add_reaction="x", remove_reaction="thinking_face"
        )


class TestProcessMessageIdentityGate:

    def _setup_with_identity(self, has_mapping=True):
        storage = Mock()
        storage.get_context.return_value = {'session_id': 'sess1'}
        storage.get_context_for_query.return_value = ''

        timeout_handler = Mock()
        timeout_handler.query_agent_with_timeout.return_value = ('response', 'sess2')

        mp = _make_processor(storage=storage, reaction_manager=Mock(), timeout_handler=timeout_handler)
        mp._has_identity_mapping = Mock(return_value=has_mapping)
        mp._handle_link_github_via_dm = Mock()
        return mp

    def test_unlinked_user_triggers_link_flow(self):
        mp = self._setup_with_identity(has_mapping=False)
        say = Mock()
        mp.process_message('C_ALLOWED', 'tts', 'U_ADMIN', '<@BOT> hello', say, message_ts='mts')
        mp._handle_link_github_via_dm.assert_called_once_with('U_ADMIN', 'C_ALLOWED', 'tts', 'mts', say)

    def test_linked_user_proceeds_to_agent(self):
        mp = self._setup_with_identity(has_mapping=True)
        say = Mock()
        mp.process_message('C_ALLOWED', 'tts', 'U_ADMIN', '<@BOT> hello', say, message_ts='mts')
        mp._handle_link_github_via_dm.assert_not_called()
        mp.timeout_handler.query_agent_with_timeout.assert_called_once()

    def test_privileged_user_advisory_response_passed_through(self):
        """Privileged user receives the full agent response with advisory content."""
        mp = self._setup_with_identity(has_mapping=True)
        advisory_response = (
            'Here is a detailed CVE breakdown from advisories.opensearch.org with specifics.'
        )
        mp.timeout_handler.query_agent_with_timeout.return_value = (advisory_response, 'sess2')

        say = Mock()
        mp.process_message('C_ALLOWED', 'tts', 'U_ADMIN', '<@BOT> show vulns', say, message_ts='mts')

        sent_text = say.call_args[1]['text']
        assert 'detailed CVE breakdown' in sent_text
