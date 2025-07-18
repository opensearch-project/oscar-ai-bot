"""
Main stack for OSCAR Slack Bot.

This module defines the main CDK stack that combines all components of the OSCAR Slack Bot.
"""

from aws_cdk import (
    Stack,
    aws_secretsmanager as secretsmanager,
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

        # Create Secrets for Slack credentials
        slack_secrets = secretsmanager.Secret(
            self, "SlackSecrets",
            secret_name="oscar-slack-bot-secrets",
            description="Secrets for OSCAR Slack Bot",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"SLACK_BOT_TOKEN":"","SLACK_SIGNING_SECRET":""}',
                generate_string_key="dummy"
            )
        )
        
        # Create storage resources (DynamoDB tables and S3 bucket)
        storage_stack = OscarStorageStack(self, "StorageStack")
        
        # Create Lambda function and API Gateway
        lambda_stack = OscarLambdaStack(
            self, 
            "LambdaStack",
            sessions_table=storage_stack.sessions_table,
            context_table=storage_stack.context_table,
            slack_secrets=slack_secrets
        )
        
        # Output Slack secrets ARN
        CfnOutput(
            self, "SlackSecretsArn",
            value=slack_secrets.secret_arn,
            description="ARN of the Slack secrets in Secrets Manager"
        )