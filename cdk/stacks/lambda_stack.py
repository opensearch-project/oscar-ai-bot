"""
Lambda stack for OSCAR Slack Bot.

This module defines the Lambda function and API Gateway used by the OSCAR Slack Bot.
"""

from aws_cdk import (
    Duration,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_apigateway as apigateway,
    CfnOutput
)
from constructs import Construct
import os

class OscarLambdaStack(Construct):
    """Lambda resources for OSCAR Slack Bot."""
    
    def __init__(
        self, 
        scope: Construct, 
        construct_id: str, 
        sessions_table, 
        context_table, 
        slack_secrets
    ) -> None:
        """Initialize Lambda resources."""
        super().__init__(scope, construct_id)
        
        # Create Lambda function role
        self.lambda_role = iam.Role(
            self, "OscarLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
            ]
        )

        # Add permissions for Bedrock
        self.lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:RetrieveAndGenerate",
                    "bedrock:Retrieve",
                    "bedrock:GetFoundationModel",
                    "bedrock:ListFoundationModels",
                    "bedrock:GetKnowledgeBase",
                    "bedrock:ListKnowledgeBases",
                    "bedrock:GetInferenceProfile",
                    "bedrock:ListInferenceProfiles",
                    "bedrock-agent-runtime:Retrieve",
                    "bedrock-agent-runtime:RetrieveAndGenerate",
                    "bedrock-agent-runtime:InvokeAgent"
                ],
                resources=["*"]
            )
        )

        # Add permissions for DynamoDB
        self.lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:DeleteItem",
                    "dynamodb:Query"
                ],
                resources=[
                    sessions_table.table_arn,
                    context_table.table_arn
                ]
            )
        )

        # Add permissions for Secrets Manager
        self.lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "secretsmanager:GetSecretValue"
                ],
                resources=[slack_secrets.secret_arn]
            )
        )

        # Create Lambda function with placeholder code
        self.lambda_function = lambda_.Function(
            self, "OscarSlackBotFunction",
            function_name="oscar-slack-bot",
            runtime=lambda_.Runtime.PYTHON_3_9,
            handler="app.lambda_handler",
            code=lambda_.Code.from_inline("""
import os
def lambda_handler(event, context):
    return {
        'statusCode': 200,
        'body': 'Lambda function deployed successfully. Will be updated with full code.'
    }
"""),
            timeout=Duration.seconds(30),
            memory_size=512,
            environment=self._get_lambda_environment_variables(slack_secrets),
            role=self.lambda_role
        )

        # Create API Gateway
        self.api = apigateway.LambdaRestApi(
            self, "OscarSlackBotApi",
            handler=self.lambda_function,
            proxy=False
        )

        # Add Slack events endpoint
        slack_events = self.api.root.add_resource("slack").add_resource("events")
        slack_events.add_method("POST")
        
        # Outputs
        CfnOutput(
            self, "SlackWebhookUrl",
            value=f"{self.api.url}slack/events",
            description="URL to configure in Slack Events API"
        )
        
        CfnOutput(
            self, "LambdaFunctionName",
            value=self.lambda_function.function_name,
            description="Name of the Lambda function"
        )
    
    def _get_lambda_environment_variables(self, slack_secrets):
        """Get environment variables for Lambda function."""
        env_vars = {
            # Required configuration
            "KNOWLEDGE_BASE_ID": os.environ.get("KNOWLEDGE_BASE_ID", "PLACEHOLDER_KNOWLEDGE_BASE_ID"),
            "MODEL_ARN": os.environ.get("MODEL_ARN", "arn:aws:bedrock:us-west-2::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0"),
            "SLACK_SECRETS_ARN": slack_secrets.secret_arn,
            
            # Optional configuration
            # Note: AWS_REGION is a reserved environment variable in Lambda and cannot be set manually
            "SESSIONS_TABLE_NAME": os.environ.get("SESSIONS_TABLE_NAME", "oscar-sessions"),
            "CONTEXT_TABLE_NAME": os.environ.get("CONTEXT_TABLE_NAME", "oscar-context"),
            "DEDUP_TTL": os.environ.get("DEDUP_TTL", "300"),
            "SESSION_TTL": os.environ.get("SESSION_TTL", "3600"),
            "CONTEXT_TTL": os.environ.get("CONTEXT_TTL", "172800"),
            "MAX_CONTEXT_LENGTH": os.environ.get("MAX_CONTEXT_LENGTH", "3000"),
            "CONTEXT_SUMMARY_LENGTH": os.environ.get("CONTEXT_SUMMARY_LENGTH", "500"),
            
            # Feature flags
            "ENABLE_DM": os.environ.get("ENABLE_DM", "false"),
        }
        
        # Add prompt template if provided
        if os.environ.get("PROMPT_TEMPLATE"):
            env_vars["PROMPT_TEMPLATE"] = os.environ.get("PROMPT_TEMPLATE")
            
        return env_vars