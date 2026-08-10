# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Clean up sys.modules after GitHub agent tests to prevent pollution."""

import sys

import pytest


@pytest.fixture(autouse=True)
def _cleanup_github_lambda_modules():
    """Remove mocked GitHub lambda modules from sys.modules after each test."""
    yield
    for mod_name in ['lambda_function', 'authorizer', 'guardrails',
                     'github_api', 'http_client', 'mcp_client',
                     'response_builder']:
        sys.modules.pop(mod_name, None)
