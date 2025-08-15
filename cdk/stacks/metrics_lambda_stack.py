#!/usr/bin/env python
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Metrics Lambda stack for OSCAR Agent.

This module defines the Lambda function for handling metrics action groups
in the OSCAR Bedrock agent.
"""

import logging
import os
from aws_cdk import (
    Duration,
    aws_lambda as lambda_,
    aws_iam as iam,
    CfnOutput
)
from constructs import Construct

logger = logging.getLogger(__name__)


class OscarMetricsLambdaStack(Construct):
    """
    Metrics Lambda resources for OSCAR Agent.
    
    This construct creates and configures the Lambda function for handling
    metrics queries from the OSCAR Bedrock agent.
    """
    
    def __init__(self, scope: Construct, construct_id: str) -> None:
        """
        Initialize metrics Lambda resources.
        
        Args:
            scope: The CDK construct scope
            construct_id: The ID of the construct
        """
        super().__init__(scope, construct_id)
        
        # Create Lambda function role with appropriate permissions
        self.lambda_role = self._create_lambda_role()

        # Create Lambda function
        self.lambda_function = self._create_lambda_function()
        
        # Add outputs for important resources
        self._add_outputs()
    
    def _create_lambda_role(self) -> iam.Role:
        """
        Create the IAM role for the metrics Lambda function.
        
        Returns:
            The created IAM role
        """
        role = iam.Role(
            self, "OscarMetricsLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
            ]
        )

        # Add permissions for OpenSearch access (same as Jenkins)
        role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "es:ESHttpGet",
                    "es:ESHttpPost", 
                    "es:ESHttpHead"
                ],
                resources=["arn:aws:es:*:*:domain/*"]
            )
        )
        
        # Add permissions for OpenSearch Serverless (if needed)
        role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "aoss:APIAccessAll"
                ],
                resources=["*"]
            )
        )
        
        return role
    
    def _create_lambda_function(self) -> lambda_.Function:
        """
        Create the metrics Lambda function.
        
        Returns:
            The created Lambda function
        """
        function_name = os.environ.get("METRICS_LAMBDA_FUNCTION_NAME", "oscar-metrics-agent")
        
        return lambda_.Function(
            self, "OscarMetricsFunction",
            function_name=function_name,
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="main.handler",
            code=lambda_.Code.from_asset("../metrics/src"),
            timeout=Duration.seconds(60),
            memory_size=512,
            environment=self._get_lambda_environment_variables(),
            role=self.lambda_role
        )
    
    def _get_lambda_environment_variables(self) -> dict[str, str]:
        """
        Get environment variables for the metrics Lambda function.
        
        Returns:
            Dictionary of environment variables
        """
        # Get OpenSearch endpoint from environment
        opensearch_host = os.environ.get(
            "OPENSEARCH_HOST", 
            "search-opensearch-health-metrics-domain-xxxxx.us-east-1.es.amazonaws.com"
        )
        
        return {
            "OPENSEARCH_HOST": opensearch_host,
            "OPENSEARCH_REGION": os.environ.get("AWS_REGION", "us-east-1"),
            "OPENSEARCH_SERVICE": "es",
            "LOG_LEVEL": os.environ.get("LOG_LEVEL", "INFO")
        }
    
    def _add_outputs(self) -> None:
        """
        Add CloudFormation outputs for important resources.
        """
        CfnOutput(
            self, "MetricsLambdaFunctionName",
            value=self.lambda_function.function_name,
            description="Name of the metrics Lambda function"
        )
        
        CfnOutput(
            self, "MetricsLambdaFunctionArn",
            value=self.lambda_function.function_arn,
            description="ARN of the metrics Lambda function"
        )
        
        CfnOutput(
            self, "MetricsLambdaRoleArn",
            value=self.lambda_role.role_arn,
            description="ARN of the metrics Lambda execution role"
        )