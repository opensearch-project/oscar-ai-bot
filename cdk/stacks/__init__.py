"""
OSCAR CDK stacks package.

This package contains the CDK stacks for deploying the OSCAR Slack Bot infrastructure.
"""

from .oscar_slack_bot_stack import OscarSlackBotStack
from .storage_stack import OscarStorageStack
from .lambda_stack import OscarLambdaStack

__all__ = [
    'OscarSlackBotStack',
    'OscarStorageStack',
    'OscarLambdaStack'
]