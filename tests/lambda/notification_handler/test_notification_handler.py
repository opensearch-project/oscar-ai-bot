# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for the alarm notification Lambda."""

import importlib
import json
import os
from unittest.mock import MagicMock, patch

# Import the notification handler's lambda_function specifically to avoid
# collision with other lambda_function modules already on sys.path
_notification_dir = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'lambda', 'oscar-notification-handler')
_spec = importlib.util.spec_from_file_location("notification_lambda", os.path.join(_notification_dir, "lambda_function.py"))
notification_lambda = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(notification_lambda)

format_alarm_message = notification_lambda.format_alarm_message
lambda_handler = notification_lambda.lambda_handler


class TestFormatAlarmMessage:

    def test_alarm_state(self):
        record = {"Sns": {"Message": json.dumps({
            "AlarmName": "oscar-test-alarm",
            "AlarmDescription": "Test alarm",
            "NewStateValue": "ALARM",
            "NewStateReason": "Threshold crossed",
            "StateChangeTime": "2026-04-14T00:00:00Z",
        })}}
        result = format_alarm_message(record)
        assert ":rotating_light:" in result
        assert "oscar-test-alarm" in result
        assert "ALARM" in result
        assert "Threshold crossed" in result

    def test_ok_state(self):
        record = {"Sns": {"Message": json.dumps({
            "AlarmName": "oscar-test-alarm",
            "NewStateValue": "OK",
        })}}
        result = format_alarm_message(record)
        assert ":white_check_mark:" in result

    def test_invalid_json_fallback(self):
        record = {"Sns": {"Message": "plain text alert"}}
        result = format_alarm_message(record)
        assert "OSCAR Alert" in result
        assert "plain text alert" in result

    def test_missing_optional_fields(self):
        record = {"Sns": {"Message": json.dumps({
            "AlarmName": "minimal-alarm",
            "NewStateValue": "ALARM",
        })}}
        result = format_alarm_message(record)
        assert "minimal-alarm" in result


class TestLambdaHandler:

    @patch.object(notification_lambda, "get_config")
    def test_missing_token(self, mock_config):
        mock_config.return_value = {"token": "", "channels": ["C123"]}
        result = lambda_handler({"Records": []}, None)
        assert result["statusCode"] == 500
        assert "Missing Slack token" in result["body"]

    @patch.object(notification_lambda, "get_config")
    def test_no_channels(self, mock_config):
        mock_config.return_value = {"token": "xoxb-test", "channels": []}
        result = lambda_handler({"Records": []}, None)
        assert result["statusCode"] == 500
        assert "No alert channels" in result["body"]

    @patch.object(notification_lambda, "WebClient")
    @patch.object(notification_lambda, "get_config")
    def test_successful_notification(self, mock_config, mock_client_cls):
        mock_config.return_value = {"token": "xoxb-test", "channels": ["C123"]}
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        event = {"Records": [{"Sns": {"Message": json.dumps({
            "AlarmName": "test-alarm",
            "NewStateValue": "ALARM",
        })}}]}

        result = lambda_handler(event, None)
        assert result["statusCode"] == 200
        mock_client.chat_postMessage.assert_called_once()
        call_kwargs = mock_client.chat_postMessage.call_args[1]
        assert call_kwargs["channel"] == "C123"
        assert "test-alarm" in call_kwargs["text"]

    @patch.object(notification_lambda, "WebClient")
    @patch.object(notification_lambda, "get_config")
    def test_multiple_channels(self, mock_config, mock_client_cls):
        mock_config.return_value = {"token": "xoxb-test", "channels": ["C123", "C456"]}
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        event = {"Records": [{"Sns": {"Message": json.dumps({
            "AlarmName": "test-alarm",
            "NewStateValue": "ALARM",
        })}}]}

        result = lambda_handler(event, None)
        assert result["statusCode"] == 200
        assert mock_client.chat_postMessage.call_count == 2

    @patch.object(notification_lambda, "WebClient")
    @patch.object(notification_lambda, "get_config")
    def test_slack_error_partial_failure(self, mock_config, mock_client_cls):
        from slack_sdk.errors import SlackApiError
        mock_config.return_value = {"token": "xoxb-test", "channels": ["C123"]}
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.chat_postMessage.side_effect = SlackApiError(
            message="error", response={"error": "channel_not_found"}
        )

        event = {"Records": [{"Sns": {"Message": json.dumps({
            "AlarmName": "test-alarm",
            "NewStateValue": "ALARM",
        })}}]}

        result = lambda_handler(event, None)
        assert result["statusCode"] == 207
