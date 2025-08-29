#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.
"""
OSCAR CDK stacks package.

This package contains the CDK stacks for deploying the OSCAR Slack Bot infrastructure.
"""

# Import only working stacks for now
from .storage_stack import OscarStorageStack
from .permissions_stack import OscarPermissionsStack
from .secrets_stack import OscarSecretsStack

# TODO: Fix existing stacks that have CDK compatibility issues
# from .slack_bot_stack import OscarSlackBotStack
# from .lambda_stack import OscarLambdaStack

__all__ = [
    'OscarStorageStack',
    'OscarPermissionsStack',
    'OscarSecretsStack'
    # 'OscarSlackBotStack',
    # 'OscarLambdaStack'
]

# Package version
__version__ = '0.1.0'