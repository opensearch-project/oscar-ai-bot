#!/usr/bin/env python
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
VPC-enabled Multi-Agent Stack for OSCAR Metrics.

This module defines Lambda functions deployed in a specific VPC for secure access
to OpenSearch clusters and other VPC resources.
"""

import logging
import os
from aws_cdk import (
    Duration,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_ec2 as ec2,
    CfnOutput
)
from constructs import Construct

logger = logging.getLogger(__name__)


class OscarVpcMultiAgentStack(Construct):
    """
    VPC-enabled multi-agent Lambda resources for OSCAR Metrics.
    
    This construct creates specialized Lambda functions deployed in a VPC
    for secure access to OpenSearch and other VPC resources.
    """
    
    def __init__(self, scope: Construct, construct_id: str, 
                 vpc_id: str = None, subnet_ids: list = None) -> None:
        """
        Initialize VPC-enabled multi-agent Lambda resources.
        
        Args:
            scope: The CDK construct scope
            construct_id: The ID of the construct
            vpc_id: Existing VPC ID to use (optional)
            subnet_ids: List of subnet IDs to use (optional)
        """
        super().__init__(scope, construct_id)
        
        # Get or create VPC configuration
        self.vpc, self.subnets, self.security_group = self._setup_vpc_config(vpc_id, subnet_ids)
        
        # Create shared IAM role for all metrics agents (with VPC permissions)
        self.shared_lambda_role = self._create_shared_lambda_role()
        
        # Create specialized agent Lambda functions in VPC
        self.test_metrics_function = self._create_test_metrics_function()
        self.build_metrics_function = self._create_build_metrics_function()
        self.release_metrics_function = self._create_release_metrics_function()
        self.deployment_metrics_function = self._create_deployment_metrics_function()
        
        # Add outputs for important resources
        self._add_outputs()
    
    def _setup_vpc_config(self, vpc_id: str = None, subnet_ids: list = None):
        """
        Set up VPC configuration for Lambda functions.
        
        Args:
            vpc_id: Existing VPC ID to use
            subnet_ids: List of subnet IDs to use
            
        Returns:
            Tuple of (vpc, subnets, security_group)
        """
        if vpc_id:
            # Use existing VPC
            vpc = ec2.Vpc.from_lookup(self, "ExistingVpc", vpc_id=vpc_id)
            logger.info(f"Using existing VPC: {vpc_id}")
        else:
            # Look up default VPC or use environment variable
            vpc_id_env = os.environ.get("VPC_ID")
            if vpc_id_env:
                vpc = ec2.Vpc.from_lookup(self, "ExistingVpc", vpc_id=vpc_id_env)
                logger.info(f"Using VPC from environment: {vpc_id_env}")
            else:
                # Use default VPC
                vpc = ec2.Vpc.from_lookup(self, "DefaultVpc", is_default=True)
                logger.info("Using default VPC")
        
        # Configure subnets
        if subnet_ids:
            # Use specific subnets
            subnets = [
                ec2.Subnet.from_subnet_id(self, f"Subnet{i}", subnet_id)
                for i, subnet_id in enumerate(subnet_ids)
            ]
        else:
            # Use private subnets with NAT gateway for internet access
            subnets = vpc.select_subnets(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ).subnets
            
            # Fallback to private subnets if no NAT gateway subnets
            if not subnets:
                subnets = vpc.select_subnets(
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
                ).subnets
            
            # Last resort: use public subnets (not recommended for production)
            if not subnets:
                logger.warning("No private subnets found, using public subnets")
                subnets = vpc.select_subnets(
                    subnet_type=ec2.SubnetType.PUBLIC
                ).subnets
        
        # Create security group for Lambda functions
        security_group = ec2.SecurityGroup(
            self, "OscarMetricsLambdaSecurityGroup",
            vpc=vpc,
            description="Security group for OSCAR metrics Lambda functions",
            allow_all_outbound=True  # Allow outbound for OpenSearch and internet access
        )
        
        # Add ingress rules if needed (typically not needed for Lambda)
        # security_group.add_ingress_rule(
        #     peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
        #     connection=ec2.Port.tcp(443),
        #     description="HTTPS access within VPC"
        # )
        
        return vpc, subnets, security_group
    
    def _create_shared_lambda_role(self) -> iam.Role:
        """
        Create shared IAM role for all metrics Lambda functions with VPC permissions.
        
        Returns:
            The created IAM role
        """
        role = iam.Role(
            self, "OscarVpcMultiAgentLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                # VPC execution role includes basic execution permissions
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaVPCAccessExecutionRole")
            ]
        )

        # Add permissions for OpenSearch access
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
        
        # Add permissions for Bedrock agent invocation
        role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock-agent-runtime:InvokeAgent"
                ],
                resources=["*"]
            )
        )
        
        return role
    
    def _create_vpc_config(self) -> lambda_.VpcConfig:
        """Create VPC configuration for Lambda functions."""
        return lambda_.VpcConfig(
            vpc=self.vpc,
            subnets=ec2.SubnetSelection(subnets=self.subnets),
            security_groups=[self.security_group]
        )
    
    def _create_test_metrics_function(self) -> lambda_.Function:
        """Create the test metrics Lambda function in VPC."""
        return lambda_.Function(
            self, "OscarTestMetricsFunction",
            function_name="oscar-test-metrics-agent",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="test_metrics_agent.handler",
            code=lambda_.Code.from_asset("../multi-agent/src"),
            timeout=Duration.seconds(60),
            memory_size=512,
            environment=self._get_metrics_environment_variables(),
            role=self.shared_lambda_role,
            vpc_config=self._create_vpc_config()  # Deploy in VPC
        )
    
    def _create_build_metrics_function(self) -> lambda_.Function:
        """Create the build metrics Lambda function in VPC."""
        return lambda_.Function(
            self, "OscarBuildMetricsFunction",
            function_name="oscar-build-metrics-agent",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="build_metrics_agent.handler",
            code=lambda_.Code.from_asset("../multi-agent/src"),
            timeout=Duration.seconds(60),
            memory_size=512,
            environment=self._get_metrics_environment_variables(),
            role=self.shared_lambda_role,
            vpc_config=self._create_vpc_config()  # Deploy in VPC
        )
    
    def _create_release_metrics_function(self) -> lambda_.Function:
        """Create the release metrics Lambda function in VPC."""
        return lambda_.Function(
            self, "OscarReleaseMetricsFunction",
            function_name="oscar-release-metrics-agent",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="release_metrics_agent.handler",
            code=lambda_.Code.from_asset("../multi-agent/src"),
            timeout=Duration.seconds(60),
            memory_size=512,
            environment=self._get_metrics_environment_variables(),
            role=self.shared_lambda_role,
            vpc_config=self._create_vpc_config()  # Deploy in VPC
        )
    
    def _create_deployment_metrics_function(self) -> lambda_.Function:
        """Create the deployment metrics Lambda function in VPC."""
        return lambda_.Function(
            self, "OscarDeploymentMetricsFunction",
            function_name="oscar-deployment-metrics-agent",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="deployment_metrics_agent.handler",
            code=lambda_.Code.from_asset("../multi-agent/src"),
            timeout=Duration.seconds(60),
            memory_size=512,
            environment=self._get_metrics_environment_variables(),
            role=self.shared_lambda_role,
            vpc_config=self._create_vpc_config()  # Deploy in VPC
        )
    
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
            self, "VpcId",
            value=self.vpc.vpc_id,
            description="VPC ID where Lambda functions are deployed"
        )
        
        CfnOutput(
            self, "SecurityGroupId",
            value=self.security_group.security_group_id,
            description="Security group ID for Lambda functions"
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