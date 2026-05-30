# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for the communication handler Lambda function.

Uses importlib to load by file path, avoiding sys.path conflicts with
the Jenkins agent's lambda_function.py.
"""

import importlib.util
import os
import sys
from unittest.mock import MagicMock, patch

_COMM_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', '..', 'lambda', 'oscar-communication-handler',
))


def _load_comm_handler():
    """Load the communication handler lambda_function by file path."""
    # Temporarily prepend comm handler dir so its local imports resolve
    sys.path.insert(0, _COMM_DIR)
    try:
        # Clear any cached versions of modules that lambda_function imports
        for name in ['lambda_function', 'message_handler', 'response_builder',
                     'slack_client', 'channel_utils']:
            sys.modules.pop(name, None)

        spec = importlib.util.spec_from_file_location(
            'comm_handler_lf',
            os.path.join(_COMM_DIR, 'lambda_function.py'),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.path.remove(_COMM_DIR)


class TestCommunicationHandlerLambda:

    def test_send_automated_message_routes(self):
        mod = _load_comm_handler()
        mock_handler = MagicMock()
        mock_handler.handle_send_message.return_value = {'status': 'ok'}

        with patch.object(mod, 'MessageHandler', return_value=mock_handler):
            event = {
                'actionGroup': 'comm',
                'function': 'send_automated_message',
                'parameters': [
                    {'name': 'target_channel', 'value': 'C123'},
                    {'name': 'message_content', 'value': 'hello'},
                ],
            }
            mod.lambda_handler(event, None)

            mock_handler.handle_send_message.assert_called_once_with(
                {'target_channel': 'C123', 'message_content': 'hello'},
                'comm',
                'send_automated_message',
            )

    def test_unknown_function_returns_error(self):
        mod = _load_comm_handler()
        mock_rb = MagicMock()
        mock_rb.create_error_response.return_value = {'error': True}

        with patch.object(mod, 'MessageHandler', return_value=MagicMock()), \
             patch.object(mod, 'ResponseBuilder', return_value=mock_rb):
            event = {
                'actionGroup': 'comm',
                'function': 'unknown_func',
                'parameters': [],
            }
            mod.lambda_handler(event, None)

            mock_rb.create_error_response.assert_called_once()
            args = mock_rb.create_error_response.call_args[0]
            assert 'Unknown function' in args[2]

    def test_parameters_list_to_dict(self):
        mod = _load_comm_handler()
        mock_handler = MagicMock()
        mock_handler.handle_send_message.return_value = {'status': 'ok'}

        with patch.object(mod, 'MessageHandler', return_value=mock_handler):
            event = {
                'actionGroup': 'comm',
                'function': 'send_automated_message',
                'parameters': [
                    {'name': 'key1', 'value': 'val1'},
                    {'name': 'key2', 'value': 'val2'},
                ],
            }
            mod.lambda_handler(event, None)

            called_params = mock_handler.handle_send_message.call_args[0][0]
            assert called_params == {'key1': 'val1', 'key2': 'val2'}

    def test_exception_returns_error(self):
        mod = _load_comm_handler()
        mock_rb = MagicMock()
        mock_rb.create_error_response.return_value = {'error': True}

        with patch.object(mod, 'MessageHandler', side_effect=RuntimeError('boom')), \
             patch.object(mod, 'ResponseBuilder', return_value=mock_rb):
            event = {
                'actionGroup': 'comm',
                'function': 'send_automated_message',
                'parameters': [],
            }
            mod.lambda_handler(event, None)

            mock_rb.create_error_response.assert_called_once()


def _load_message_handler():
    """Load message_handler module by file path with mocked external deps."""
    sys.path.insert(0, _COMM_DIR)
    try:
        for name in ['message_handler', 'channel_utils', 'context_storage',
                     'message_formatter', 'response_builder', 'slack_client', 'config']:
            sys.modules.pop(name, None)
        # Provide a stub config module so message_handler import doesn't try to load real secrets
        stub_config = MagicMock()
        sys.modules['config'] = stub_config
        spec = importlib.util.spec_from_file_location(
            'comm_msg_handler',
            os.path.join(_COMM_DIR, 'message_handler.py'),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod, stub_config
    finally:
        sys.path.remove(_COMM_DIR)


class TestSendMessageTwoPersonApproval:
    """Test ENABLE_2PR enforcement in MessageHandler.handle_send_message."""

    def _build_handler(self, mod):
        # Bypass __init__ which constructs Slack client / storage / etc.
        handler = mod.MessageHandler.__new__(mod.MessageHandler)
        handler.slack_client = MagicMock()
        handler.storage = MagicMock()
        handler.channel_utils = MagicMock()
        handler.channel_utils.validate_channel.return_value = True
        handler.message_formatter = MagicMock()
        handler.response_builder = MagicMock()
        handler.response_builder.create_error_response.side_effect = lambda ag, fn, msg: {'error': True, 'message': msg}
        handler.response_builder.create_success_response.side_effect = lambda ag, fn, msg: {'success': True, 'message': msg}
        return handler

    def _base_params(self, **extra):
        params = {
            'query': 'send to #release',
            'message_content': 'Release 2.19.0 is ready',
            'target_channel': 'C123',
            'confirmed': True,
        }
        params.update(extra)
        return params

    def test_2pr_enabled_missing_user_ids_rejected(self):
        mod, stub_cfg = _load_message_handler()
        stub_cfg.config.enable_2pr = True
        handler = self._build_handler(mod)

        result = handler.handle_send_message(self._base_params(), 'comm', 'send_automated_message')

        assert result['error'] is True
        assert 'requester_user_id' in result['message']
        handler.slack_client.send_message.assert_not_called()

    def test_2pr_enabled_self_approval_rejected(self):
        mod, stub_cfg = _load_message_handler()
        stub_cfg.config.enable_2pr = True
        handler = self._build_handler(mod)

        result = handler.handle_send_message(
            self._base_params(requester_user_id='U_SAME', approver_user_id='U_SAME'),
            'comm', 'send_automated_message',
        )

        assert result['error'] is True
        assert 'Self-approval' in result['message']
        assert 'U_SAME' in result['message']
        handler.slack_client.send_message.assert_not_called()

    def test_2pr_enabled_distinct_users_proceeds(self):
        mod, stub_cfg = _load_message_handler()
        stub_cfg.config.enable_2pr = True
        handler = self._build_handler(mod)
        handler.slack_client.send_message.return_value = {'success': True, 'message_ts': '1.2'}

        result = handler.handle_send_message(
            self._base_params(requester_user_id='U_REQ', approver_user_id='U_APP'),
            'comm', 'send_automated_message',
        )

        assert result['success'] is True
        handler.slack_client.send_message.assert_called_once()

    def test_2pr_disabled_skips_check(self):
        """When ENABLE_2PR is off, missing/equal user IDs do not block sending."""
        mod, stub_cfg = _load_message_handler()
        stub_cfg.config.enable_2pr = False
        handler = self._build_handler(mod)
        handler.slack_client.send_message.return_value = {'success': True, 'message_ts': '1.2'}

        result = handler.handle_send_message(self._base_params(), 'comm', 'send_automated_message')

        assert result['success'] is True
        handler.slack_client.send_message.assert_called_once()
