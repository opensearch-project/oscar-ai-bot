#!/usr/bin/env python
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.
"""
Least-privilege policy definitions for OSCAR components.

This module defines granular IAM policies with resource-specific access
and principle of least privilege for all OSCAR components.
"""

from typing import List

from aws_cdk import aws_iam as iam

from .lambda_stack import OscarLambdaStack
from .secrets_stack import OscarSecretsStack
from .storage_stack import OscarStorageStack


class OscarPolicyDefinitions:
    """
    Centralized policy definitions for OSCAR components.
    This class provides least-privilege IAM policy statements for different
    OSCAR components with resource-specific access controls.
    """

    def __init__(self, account_id: str, region: str, env_name: str) -> None:
        """
        Initialize policy definitions.
        Args:
            account_id: AWS account ID
            region: AWS region
        """
        self.account_id = account_id
        self.region = region
        self.env_name = env_name

    def get_bedrock_agent_policies(self) -> List[iam.PolicyStatement]:
        """
        Get least-privilege policies for Bedrock agents.
        Returns:
            List of IAM policy statements for Bedrock agents
        """
        return [
            # Lambda invocation for action groups
            iam.PolicyStatement(
                sid="InvokeActionGroupLambdas",
                effect=iam.Effect.ALLOW,
                actions=["lambda:InvokeFunction"],
                resources=[
                    f"arn:aws:lambda:{self.region}:{self.account_id}:function:*oscar*{self.env_name}"
                ]
            ),

            # Knowledge Base retrieval
            iam.PolicyStatement(
                sid="KnowledgeBaseRetrieval",
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:Retrieve",
                    "bedrock:RetrieveAndGenerate"
                ],
                resources=["*"]
            ),

            # Guardrail invocation
            iam.PolicyStatement(
                sid="GuardrailAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:ApplyGuardrail",
                    "bedrock:GetGuardrail",
                ],
                resources=[
                    f"arn:aws:bedrock:{self.region}:{self.account_id}:guardrail/*"
                ]
            ),

            # Foundation model access
            iam.PolicyStatement(
                sid="FoundationModelAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                    "bedrock:CreateInferenceProfile",
                    "bedrock:GetInferenceProfile",
                    "bedrock:GetFoundationModel"
                ],
                resources=["*"]
            ),

            iam.PolicyStatement(
                sid="AmazonBedrockAgentInferencProfilePolicy2",
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:GetInferenceProfile",
                    "bedrock:ListInferenceProfiles",
                    "bedrock:DeleteInferenceProfile",
                    "bedrock:TagResource",
                    "bedrock:UntagResource",
                    "bedrock:ListTagsForResource"
                ],
                resources=[
                    "arn:aws:bedrock:*:*:inference-profile/*",
                    "arn:aws:bedrock:*:*:application-inference-profile/*"
                ]
            ),

            iam.PolicyStatement(
                sid="AmazonBedrockAgentsMultiAgentsPoliciesProd",
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:GetAgentAlias",
                    "bedrock:InvokeAgent"
                ],
                resources=[
                    "arn:aws:bedrock:*:*:agent/*",
                    "arn:aws:bedrock:*:*:agent-alias/*"
                ]
            )
        ]

    def get_lambda_base_policies(self) -> List[iam.PolicyStatement]:
        """
        Get base policies for Lambda functions.
        Returns:
            List of IAM policy statements for base Lambda functions
        """
        return [
            # DynamoDB access for sessions and context
            iam.PolicyStatement(
                sid="DynamoDBSessionsAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:DeleteItem"
                ],
                resources=[
                    f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/oscar-*"
                ]
            ),

            iam.PolicyStatement(
                sid="DynamoDBContextAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:Query",
                    "dynamodb:Scan"
                ],
                resources=[
                    f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{OscarStorageStack.get_dynamodb_table_name(self.env_name)}"
                ]
            ),

            # Secrets Manager access for central environment
            iam.PolicyStatement(
                sid="CentralSecretsAccess",
                effect=iam.Effect.ALLOW,
                actions=["secretsmanager:GetSecretValue"],
                resources=[
                    f"arn:aws:secretsmanager:{self.region}:{self.account_id}:secret:{OscarSecretsStack.get_central_env_secret_name(self.env_name)}"
                ]
            ),

            # Bedrock agent invocation
            iam.PolicyStatement(
                sid="BedrockAgentInvocation",
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeAgent",
                    "bedrock-agent-runtime:InvokeAgent",
                    "bedrock:GetAgent",
                    "bedrock:GetKnowledgeBase",
                    "bedrock:Retrieve",
                    "bedrock:RetrieveAndGenerate"
                ],
                resources=["*"]
            ),

            # Bedrock model access for direct invocation
            iam.PolicyStatement(
                sid="BedrockModelInvocation",
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel"
                ],
                resources=[
                    f"arn:aws:bedrock:{self.region}::foundation-model/*",
                    f"arn:aws:bedrock:{self.region}:{self.account_id}:inference-profile/*"
                ]
            ),

            # Lambda self-invocation for async processing
            iam.PolicyStatement(
                sid="LambdaSelfInvocation",
                effect=iam.Effect.ALLOW,
                actions=["lambda:InvokeFunction"],
                resources=[
                    f"arn:aws:lambda:{self.region}:{self.account_id}:function:oscar*{self.env_name}"
                ]
            ),

            # SSM Parameter Store access for agent configuration
            iam.PolicyStatement(
                sid="SSMParameterAccess",
                effect=iam.Effect.ALLOW,
                actions=["ssm:GetParameter"],
                resources=[
                    f"arn:aws:ssm:{self.region}:{self.account_id}:parameter/oscar/{self.env_name}/bedrock/*"
                ]
            )
        ]

    def get_communication_handler_policies(self) -> List[iam.PolicyStatement]:
        """
        Get policies for communication handler Lambda.
        Returns:
            List of IAM policy statements for communication handler
        """
        return [
            # DynamoDB access for message routing and context
            iam.PolicyStatement(
                sid="MessageRoutingDynamoDBAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:Query"
                ],
                resources=[
                    f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/oscar-sessions*",
                    f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{OscarStorageStack.get_dynamodb_table_name(self.env_name)}"
                ]
            ),

            # Secrets Manager access for Slack credentials
            iam.PolicyStatement(
                sid="SlackSecretsAccess",
                effect=iam.Effect.ALLOW,
                actions=["secretsmanager:GetSecretValue"],
                resources=[
                    f"arn:aws:secretsmanager:{self.region}:{self.account_id}:secret:{OscarSecretsStack.get_central_env_secret_name(self.env_name)}"
                ]
            ),

            # Lambda invocation for other OSCAR functions
            iam.PolicyStatement(
                sid="InvokeOscarLambdas",
                effect=iam.Effect.ALLOW,
                actions=["lambda:InvokeFunction"],
                resources=[
                    f"arn:aws:lambda:{self.region}:{self.account_id}:function:{OscarLambdaStack.get_supervisor_agent_function_name(self.env_name)}"
                ]
            )
        ]

    def get_api_gateway_policies(self) -> List[iam.PolicyStatement]:
        """
        Get policies for API Gateway.
        Returns:
            List of IAM policy statements for API Gateway
        """
        return [
            # Lambda invocation for Slack webhooks
            iam.PolicyStatement(
                sid="SlackWebhookLambdaInvocation",
                effect=iam.Effect.ALLOW,
                actions=["lambda:InvokeFunction"],
                resources=[
                    f"arn:aws:lambda:{self.region}:{self.account_id}:function:*oscar*{self.env_name}"
                ]
            ),

            # CloudWatch Logs for API Gateway
            iam.PolicyStatement(
                sid="ApiGatewayLogsAccess",
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "logs:DescribeLogGroups",
                    "logs:DescribeLogStreams"
                ],
                resources=[
                    f"arn:aws:logs:{self.region}:{self.account_id}:log-group:/aws/apigateway/oscar-*"
                ]
            )
        ]
