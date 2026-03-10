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


class TestHandleMessage:

    def test_dm_from_fully_authorized_user(self):
        processor = Mock()
        handler = EventHandlers(processor)

        message = {'channel_type': 'im', 'channel': 'D123', 'ts': 'ts1',
                   'user': 'U_ADMIN', 'text': 'hello'}
        handler.handle_message(message, Mock())

        processor.process_message.assert_called_once()

    def test_dm_from_dm_authorized_user(self):
        processor = Mock()
        handler = EventHandlers(processor)

        message = {'channel_type': 'im', 'channel': 'D123', 'ts': 'ts1',
                   'user': 'U_DM', 'text': 'hello'}
        handler.handle_message(message, Mock())

        processor.process_message.assert_called_once()

    def test_dm_from_unauthorized_user_ignored(self):
        processor = Mock()
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
