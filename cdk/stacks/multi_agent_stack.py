#!/usr/bin/env python
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Multi-Agent Stack for OSCAR Metrics.

This module defines the Lambda functions for the multi-agent metrics architecture.
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


class OscarMultiAgentStack(Construct):
    """
    Multi-agent Lambda resources for OSCAR Metrics.
    
    This construct creates specialized Lambda functions for different metrics domains.
    """
    
    def __init__(self, scope: Construct, construct_id: str) -> None:
        """
        Initialize multi-agent Lambda resources.
        
        Args:
            scope: The CDK construct scope
            construct_id: The ID of the construct
        """
        super().__init__(scope, construct_id)
        
        # Create shared IAM role for all metrics agents
        self.shared_lambda_role = self._create_shared_lambda_role()
        
        # Create agent router Lambda
        self.agent_router_function = self._create_agent_router_function()
        
        # Create specialized agent Lambda functions
        self.test_metrics_function = self._create_test_metrics_function()
        self.build_metrics_function = self._create_build_metrics_function()
        self.release_metrics_function = self._create_release_metrics_function()
        self.deployment_metrics_function = self._create_deployment_metrics_function()
        
        # Add outputs for important resources
        self._add_outputs()
    
    def _create_shared_lambda_role(self) -> iam.Role:
        """
        Create shared IAM role for all metrics Lambda functions.
        
        Returns:
            The created IAM role
        """
        role = iam.Role(
            self, "OscarMultiAgentLambdaRole",
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
        
        # Add permissions for Bedrock agent invocation (for agent router)
        role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock-agent-runtime:InvokeAgent"
                ],
                resources=["*"]
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
    
    def _create_agent_router_function(self) -> lambda_.Function:
        """Create the agent router Lambda function."""
        return lambda_.Function(
            self, "OscarAgentRouterFunction",
            function_name="oscar-agent-router",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="agent_router.handler",
            code=lambda_.Code.from_asset("../multi-agent/src"),
            timeout=Duration.seconds(120),  # Longer timeout for multi-agent coordination
            memory_size=1024,  # More memory for concurrent agent calls
            environment=self._get_router_environment_variables(),
            role=self.shared_lambda_role
        )
    
    def _create_test_metrics_function(self) -> lambda_.Function:
        """Create the test metrics Lambda function."""
        return lambda_.Function(
            self, "OscarTestMetricsFunction",
            function_name="oscar-test-metrics-agent",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="test_metrics_agent.handler",
            code=lambda_.Code.from_asset("../multi-agent/src"),
            timeout=Duration.seconds(60),
            memory_size=512,
            environment=self._get_metrics_environment_variables(),
            role=self.shared_lambda_role
        )
    
    def _create_build_metrics_function(self) -> lambda_.Function:
        """Create the build metrics Lambda function."""
        return lambda_.Function(
            self, "OscarBuildMetricsFunction",
            function_name="oscar-build-metrics-agent",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="build_metrics_agent.handler",
            code=lambda_.Code.from_asset("../multi-agent/src"),
            timeout=Duration.seconds(60),
            memory_size=512,
            environment=self._get_metrics_environment_variables(),
            role=self.shared_lambda_role
        )
    
    def _create_release_metrics_function(self) -> lambda_.Function:
        """Create the release metrics Lambda function."""
        return lambda_.Function(
            self, "OscarReleaseMetricsFunction",
            function_name="oscar-release-metrics-agent",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="release_metrics_agent.handler",
            code=lambda_.Code.from_asset("../multi-agent/src"),
            timeout=Duration.seconds(60),
            memory_size=512,
            environment=self._get_metrics_environment_variables(),
            role=self.shared_lambda_role
        )
    
    def _create_deployment_metrics_function(self) -> lambda_.Function:
        """Create the deployment metrics Lambda function."""
        return lambda_.Function(
            self, "OscarDeploymentMetricsFunction",
            function_name="oscar-deployment-metrics-agent",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="deployment_metrics_agent.handler",
            code=lambda_.Code.from_asset("../multi-agent/src"),
            timeout=Duration.seconds(60),
            memory_size=512,
            environment=self._get_metrics_environment_variables(),
            role=self.shared_lambda_role
        )
    
    def _get_router_environment_variables(self) -> dict[str, str]:
        """Get environment variables for the agent router."""
        return {
            "LOG_LEVEL": os.environ.get("LOG_LEVEL", "INFO"),
            "TEST_METRICS_AGENT_ID": os.environ.get("TEST_METRICS_AGENT_ID", "PLACEHOLDER"),
            "BUILD_METRICS_AGENT_ID": os.environ.get("BUILD_METRICS_AGENT_ID", "PLACEHOLDER"),
            "RELEASE_METRICS_AGENT_ID": os.environ.get("RELEASE_METRICS_AGENT_ID", "PLACEHOLDER"),
            "DEPLOYMENT_METRICS_AGENT_ID": os.environ.get("DEPLOYMENT_METRICS_AGENT_ID", "PLACEHOLDER")
        }
    
    def _get_metrics_environment_variables(self) -> dict[str, str]:
        """Get environment variables for metrics Lambda functions."""
        opensearch_host = os.environ.get(
            "OPENSEARCH_HOST", 
            "mock-cluster-for-testing"
        )
        
        # Enable mock mode by default for testing
        mock_mode = os.environ.get("MOCK_MODE", "true")
        
        return {
            "OPENSEARCH_HOST": opensearch_host,
            "OPENSEARCH_REGION": os.environ.get("AWS_REGION", "us-east-1"),
            "OPENSEARCH_SERVICE": "es",
            "LOG_LEVEL": os.environ.get("LOG_LEVEL", "INFO"),
            "MOCK_MODE": mock_mode
        }
    
    def _add_outputs(self) -> None:
        """Add CloudFormation outputs for important resources."""
        CfnOutput(
            self, "AgentRouterFunctionName",
            value=self.agent_router_function.function_name,
            description="Name of the agent router Lambda function"
        )
        
        CfnOutput(
            self, "TestMetricsFunctionName",
            value=self.test_metrics_function.function_name,
            description="Name of the test metrics Lambda function"
        )
        
        CfnOutput(
            self, "BuildMetricsFunctionName",
            value=self.build_metrics_function.function_name,
            description="Name of the build metrics Lambda function"
        )
        
        CfnOutput(
            self, "ReleaseMetricsFunctionName",
            value=self.release_metrics_function.function_name,
            description="Name of the release metrics Lambda function"
        )
        
        CfnOutput(
            self, "DeploymentMetricsFunctionName",
            value=self.deployment_metrics_function.function_name,
            description="Name of the deployment metrics Lambda function"
        )
        
        CfnOutput(
            self, "SharedLambdaRoleArn",
            value=self.shared_lambda_role.role_arn,
            description="ARN of the shared Lambda execution role"
        )