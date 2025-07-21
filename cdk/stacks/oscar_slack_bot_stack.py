"""
Main stack for OSCAR Slack Bot.

This module defines the main CDK stack that combines all components of the OSCAR Slack Bot.
"""

from aws_cdk import (
    Stack,
    CfnOutput
)
from constructs import Construct
from .storage_stack import OscarStorageStack
from .lambda_stack import OscarLambdaStack

class OscarSlackBotStack(Stack):
    """Main stack for OSCAR Slack Bot."""
    
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        """Initialize the OSCAR Slack Bot stack."""
        super().__init__(scope, construct_id, **kwargs)
        
        # Create storage resources (DynamoDB tables only)
        storage_stack = OscarStorageStack(self, "StorageStack")
        
        # Create Lambda function and API Gateway
        lambda_stack = OscarLambdaStack(
            self, 
            "LambdaStack",
            sessions_table=storage_stack.sessions_table,
            context_table=storage_stack.context_table
        )