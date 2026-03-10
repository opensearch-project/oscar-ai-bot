# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Fixtures for CDK stack tests."""

import os

import pytest
from aws_cdk import App


@pytest.fixture
def cdk_app():
    """Create a CDK App with required environment variables."""
    os.environ['CDK_DEFAULT_ACCOUNT'] = '123456789012'
    os.environ['CDK_DEFAULT_REGION'] = 'us-east-1'
    return App()
