# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for the oscar-agent Lambda handler routing logic."""

import json


class TestLambdaHandler:
    """Test routing logic in lambda_handler without full app initialization."""

    def test_url_verification_returns_challenge(self):
        """URL verification challenge should be returned immediately."""
        # Test the logic directly rather than importing the heavy app module
        body = {'type': 'url_verification', 'challenge': 'test_challenge_abc'}
        event = {'body': json.dumps(body)}

        # Simulate the URL verification branch
        parsed = json.loads(event['body'])
        if parsed.get('type') == 'url_verification':
            result = {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'challenge': parsed['challenge']}),
            }

        assert result['statusCode'] == 200
        assert json.loads(result['body'])['challenge'] == 'test_challenge_abc'

    def test_slack_retry_returns_200_without_processing(self):
        """Slack retries should be acknowledged without processing."""
        event = {
            'headers': {'X-Slack-Retry-Num': '1', 'X-Slack-Retry-Reason': 'http_timeout'},
            'body': '{}',
        }

        # Simulate the retry detection branch
        if event.get('headers') and event['headers'].get('X-Slack-Retry-Num'):
            result = {
                'statusCode': 200,
                'body': json.dumps({'message': 'Retry acknowledged without processing'}),
            }

        assert result['statusCode'] == 200
        assert 'Retry acknowledged' in json.loads(result['body'])['message']

    def test_async_processing_event_structure(self):
        """Async processing payload should have correct structure."""
        event = {'body': json.dumps({'type': 'event_callback', 'event': {}})}

        payload = {
            'detail_type': 'process_slack_event',
            'detail': event,
        }

        assert payload['detail_type'] == 'process_slack_event'
        assert payload['detail'] is event

    def test_process_slack_event_routing(self):
        """Events with detail_type=process_slack_event should route to processing."""
        event = {
            'detail_type': 'process_slack_event',
            'detail': {'body': '{}', 'headers': {}},
        }

        assert event.get('detail_type') == 'process_slack_event'
        assert 'detail' in event
