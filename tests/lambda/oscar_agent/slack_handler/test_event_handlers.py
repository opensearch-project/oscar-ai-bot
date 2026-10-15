# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for EventHandlers."""

import sys
from unittest.mock import Mock

from slack_handler.event_handlers import EventHandlers

# Get the mock config from conftest (defaults: U_ADMIN, U_DM, C_ALLOWED)
mock_config = sys.modules['config'].config


class TestHandleAppMention:

    def test_allowed_channel_calls_process_message(self):
        processor = Mock()
        handler = EventHandlers(processor)

        event = {'channel': 'C_ALLOWED', 'thread_ts': 'tts', 'ts': 'ets', 'user': 'U1', 'text': 'hi'}
        handler.handle_app_mention(event, Mock())

        processor.process_message.assert_called_once()

    def test_disallowed_channel_ignored(self):
        processor = Mock()
        handler = EventHandlers(processor)

        event = {'channel': 'C_NOT_ALLOWED', 'ts': 'ets', 'user': 'U1', 'text': 'hi'}
        handler.handle_app_mention(event, Mock())

        processor.process_message.assert_not_called()

    def test_thread_ts_used_when_present(self):
        processor = Mock()
        handler = EventHandlers(processor)

        event = {'channel': 'C_ALLOWED', 'thread_ts': 'tts', 'ts': 'ets', 'user': 'U1', 'text': 'hi'}
        handler.handle_app_mention(event, Mock())

        args = processor.process_message.call_args[0]
        assert args[1] == 'tts'

    def test_ts_fallback_when_no_thread_ts(self):
        processor = Mock()
        handler = EventHandlers(processor)

        event = {'channel': 'C_ALLOWED', 'ts': 'ets', 'user': 'U1', 'text': 'hi'}
        handler.handle_app_mention(event, Mock())

        args = processor.process_message.call_args[0]
        assert args[1] == 'ets'

    def test_event_ts_passed_as_message_ts(self):
        processor = Mock()
        handler = EventHandlers(processor)

        event = {'channel': 'C_ALLOWED', 'thread_ts': 'tts', 'ts': 'ets', 'user': 'U1', 'text': 'hi'}
        handler.handle_app_mention(event, Mock())

        kwargs = processor.process_message.call_args[1]
        assert kwargs.get('message_ts') == 'ets'

    def test_app_mention_uses_default_identity_cache_reset(self):
        """Mentions have no prior identity lookup, so process_message resets the cache."""
        processor = Mock()
        handler = EventHandlers(processor)

        event = {'channel': 'C_ALLOWED', 'thread_ts': 'tts', 'ts': 'ets', 'user': 'U1', 'text': 'hi'}
        handler.handle_app_mention(event, Mock())

        assert 'reset_identity_cache' not in processor.process_message.call_args[1]
        processor.reset_identity_cache.assert_not_called()


class TestHandleMessage:

    def test_dm_from_global_admin_processed(self):
        processor = Mock()
        processor.is_global_admin.return_value = True
        handler = EventHandlers(processor)

        message = {'channel_type': 'im', 'channel': 'D123', 'ts': 'ts1',
                   'user': 'U_ADMIN', 'text': 'hello'}
        handler.handle_message(message, Mock())

        processor.is_global_admin.assert_called_once_with('U_ADMIN')
        processor.process_message.assert_called_once()

    def test_dm_from_agent_level_user_ignored(self):
        """Agent-level (non-global) users cannot DM."""
        processor = Mock()
        processor.is_global_admin.return_value = False
        handler = EventHandlers(processor)

        message = {'channel_type': 'im', 'channel': 'D123', 'ts': 'ts1',
                   'user': 'U_JENKINS', 'text': 'hello'}
        handler.handle_message(message, Mock())

        processor.process_message.assert_not_called()

    def test_dm_from_dm_allowlisted_user_processed(self):
        """A Slack user on dm_authorized_users can DM even if not a global admin."""
        processor = Mock()
        processor.is_global_admin.return_value = False
        handler = EventHandlers(processor)

        message = {'channel_type': 'im', 'channel': 'D123', 'ts': 'ts1',
                   'user': 'U_DM', 'text': 'hello'}
        handler.handle_message(message, Mock())

        processor.process_message.assert_called_once()

    def test_dm_from_unauthorized_user_ignored(self):
        processor = Mock()
        processor.is_global_admin.return_value = False
        handler = EventHandlers(processor)

        message = {'channel_type': 'im', 'channel': 'D123', 'ts': 'ts1',
                   'user': 'U_NOBODY', 'text': 'hello'}
        handler.handle_message(message, Mock())

        processor.process_message.assert_not_called()

    def test_non_im_channel_ignored(self):
        processor = Mock()
        handler = EventHandlers(processor)

        message = {'channel_type': 'channel', 'channel': 'C_ALLOWED', 'ts': 'ts1',
                   'user': 'U_ADMIN', 'text': 'hello'}
        handler.handle_message(message, Mock())

        processor.process_message.assert_not_called()

    def test_dm_resets_identity_cache_before_auth_check(self):
        """The DM check must not read an identity record cached by a previous message."""
        processor = Mock()
        processor.is_global_admin.return_value = True
        handler = EventHandlers(processor)

        message = {'channel_type': 'im', 'channel': 'D123', 'ts': 'ts1',
                   'user': 'U_ADMIN', 'text': 'hello'}
        handler.handle_message(message, Mock())

        call_names = [c[0] for c in processor.mock_calls]
        assert call_names.index('reset_identity_cache') < call_names.index('is_global_admin')

    def test_dm_reuses_identity_cache_in_process_message(self):
        """The record resolved by the DM check is reused, not queried again."""
        processor = Mock()
        processor.is_global_admin.return_value = True
        handler = EventHandlers(processor)

        message = {'channel_type': 'im', 'channel': 'D123', 'ts': 'ts1',
                   'user': 'U_ADMIN', 'text': 'hello'}
        handler.handle_message(message, Mock())

        assert processor.process_message.call_args[1]['reset_identity_cache'] is False

    def test_rejected_dm_still_resets_identity_cache(self):
        processor = Mock()
        processor.is_global_admin.return_value = False
        handler = EventHandlers(processor)

        message = {'channel_type': 'im', 'channel': 'D123', 'ts': 'ts1',
                   'user': 'U_NOBODY', 'text': 'hello'}
        handler.handle_message(message, Mock())

        processor.reset_identity_cache.assert_called_once()
        processor.process_message.assert_not_called()
