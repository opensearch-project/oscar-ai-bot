"""
Storage stack for OSCAR Slack Bot.

This module defines the DynamoDB tables used by the OSCAR Slack Bot.
"""

from aws_cdk import (
    RemovalPolicy,
    aws_dynamodb as dynamodb,
    CfnOutput
)
from constructs import Construct

class OscarStorageStack(Construct):
    """Storage resources for OSCAR Slack Bot."""
    
    def __init__(self, scope: Construct, construct_id: str) -> None:
        """Initialize storage resources."""
        super().__init__(scope, construct_id)
        
        # Create DynamoDB Tables
        self.sessions_table = dynamodb.Table(
            self, "OscarSessionsTable",
            table_name="oscar-sessions-v2",
            partition_key=dynamodb.Attribute(
                name="event_id",
                type=dynamodb.AttributeType.STRING
            ),
            time_to_live_attribute="ttl",
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY
        )

        self.context_table = dynamodb.Table(
            self, "OscarContextTable",
            table_name="oscar-context",
            partition_key=dynamodb.Attribute(
                name="thread_key",
                type=dynamodb.AttributeType.STRING
            ),
            time_to_live_attribute="ttl",
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY
        )
        
        # Outputs
        CfnOutput(
            self, "SessionsTableName",
            value=self.sessions_table.table_name,
            description="Name of the DynamoDB table for session data"
        )
        
        CfnOutput(
            self, "ContextTableName",
            value=self.context_table.table_name,
            description="Name of the DynamoDB table for context data"
        )