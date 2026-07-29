# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for MessageProcessor."""

import sys
from unittest.mock import Mock

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


class TestBuildIdentityAttributes:

    def test_first_message_sets_requester(self):
        storage = Mock()
        storage.get_context.return_value = None
        mp = _make_processor(storage=storage)
        result = mp._build_identity_attributes('C123_ts1', 'U_FIRST')
        assert result['current_user_id'] == 'U_FIRST'
        assert result['requester_user_id'] == 'U_FIRST'
        assert 'approver_user_id' not in result

    def test_pending_approval_different_user_sets_approver(self):
        """A different user replying after a confirmation prompt becomes approver."""
        storage = Mock()
        storage.get_context.return_value = {'pending_approval_requester': 'U_REQ'}
        mp = _make_processor(storage=storage)
        result = mp._build_identity_attributes('C123_ts1', 'U_APP')
        assert result['current_user_id'] == 'U_APP'
        assert result['requester_user_id'] == 'U_REQ'
        assert result['approver_user_id'] == 'U_APP'

    def test_pending_approval_same_user_no_approver(self):
        """The same user replying after their own confirmation prompt gets no approver."""
        storage = Mock()
        storage.get_context.return_value = {'pending_approval_requester': 'U_SAME'}
        mp = _make_processor(storage=storage)
        result = mp._build_identity_attributes('C123_ts1', 'U_SAME')
        assert result['current_user_id'] == 'U_SAME'
        assert result['requester_user_id'] == 'U_SAME'
        assert 'approver_user_id' not in result

    def test_no_pending_approval_current_user_is_requester(self):
        """Without a pending approval, the current user is the requester (no approver)."""
        storage = Mock()
        storage.get_context.return_value = {'thread_user_ids': ['U_OTHER', 'U_CURRENT']}
        mp = _make_processor(storage=storage)
        result = mp._build_identity_attributes('C123_ts1', 'U_CURRENT')
        assert result['current_user_id'] == 'U_CURRENT'
        assert result['requester_user_id'] == 'U_CURRENT'
        assert 'approver_user_id' not in result

    def test_stale_thread_participant_not_used_as_requester(self):
        """A stale thread participant should NOT become the requester for an action
        they never initiated — this was the SSC-1 bypass."""
        storage = Mock()
        storage.get_context.return_value = {
            'thread_user_ids': ['U_BOB', 'U_ALICE'],
            # No pending_approval_requester — no confirmation prompt has been shown
        }
        mp = _make_processor(storage=storage)
        result = mp._build_identity_attributes('C123_ts1', 'U_ALICE')
        assert result['requester_user_id'] == 'U_ALICE'
        assert 'approver_user_id' not in result


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

    def test_privileged_user_advisory_response_passed_through(self):
        """Privileged user receives the full agent response with advisory content."""
        mp, _, say = self._setup()
        advisory_response = (
            'Here is a detailed CVE breakdown from advisories.opensearch.org with specifics.'
        )
        mp.timeout_handler.query_agent_with_timeout.return_value = (advisory_response, 'sess2')

        mp.process_message('C_ALLOWED', 'tts', 'U_ADMIN', '<@BOT> show vulns', say, message_ts='mts')

        sent_text = say.call_args[1]['text']
        assert 'detailed CVE breakdown' in sent_text
