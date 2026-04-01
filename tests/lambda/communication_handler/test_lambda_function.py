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
