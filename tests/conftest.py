# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Root pytest configuration and shared fixtures."""

import os
from unittest.mock import Mock, patch

import pytest


@pytest.fixture(autouse=True)
def _mock_aws_credentials():
    """Ensure tests never hit real AWS services."""
    with patch.dict(os.environ, {
        'AWS_DEFAULT_REGION': 'us-east-1',
        'AWS_ACCESS_KEY_ID': 'testing',
        'AWS_SECRET_ACCESS_KEY': 'testing',
        'AWS_SECURITY_TOKEN': 'testing',
        'AWS_SESSION_TOKEN': 'testing',
    }):
        yield


@pytest.fixture
def mock_slack_event():
    """Mock Slack app_mention event."""
    return {
        'type': 'event_callback',
        'event': {
            'type': 'app_mention',
            'user': 'U123456',
            'text': '<@U987654> Hello OSCAR!',
            'channel': 'C123456',
            'ts': '1234567890.123456',
            'thread_ts': '1234567890.123456',
        },
        'team_id': 'T123456',
        'api_app_id': 'A123456',
    }


@pytest.fixture
def mock_lambda_context():
    """Mock AWS Lambda context."""
    context = Mock()
    context.function_name = 'test-function'
    context.function_version = '1'
    context.invoked_function_arn = 'arn:aws:lambda:us-east-1:123456789012:function:test-function'
    context.memory_limit_in_mb = 128
    context.remaining_time_in_millis = lambda: 30000
    context.log_group_name = '/aws/lambda/test-function'
    context.log_stream_name = '2023/01/01/[$LATEST]test'
    context.aws_request_id = 'test-request-id'
    return context
