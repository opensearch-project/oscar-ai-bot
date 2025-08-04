#!/usr/bin/env python
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.
"""
Main stack for OSCAR Slack Bot.

This module defines the main CDK stack that combines all components of the OSCAR Slack Bot.
"""

import os
from aws_cdk import (
    Stack,
    CfnOutput
)
from constructs import Construct
from .storage_stack import OscarStorageStack
from .lambda_stack import OscarLambdaStack
from .metrics_lambda_stack import OscarMetricsLambdaStack
from .multi_agent_stack import OscarMultiAgentStack
from .vpc_multi_agent_stack import OscarVpcMultiAgentStack

class OscarSlackBotStack(Stack):
    """
    Main stack for OSCAR Slack Bot.
    
    This stack serves as the parent stack that combines all components
    of the OSCAR Slack Bot infrastructure, including storage resources
    and Lambda functions.
    """
    
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        """
        Initialize the OSCAR Slack Bot stack.
        
        Args:
            scope: The CDK construct scope
            construct_id: The ID of the construct
            **kwargs: Additional keyword arguments passed to the parent Stack class
        """
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
        
        # Create metrics Lambda function (legacy single-agent)
        metrics_lambda_stack = OscarMetricsLambdaStack(
            self,
            "MetricsLambdaStack"
        )
        
        # Create multi-agent infrastructure
        # Check if VPC deployment is requested
        use_vpc = os.environ.get("USE_VPC", "false").lower() == "true"
        vpc_id = os.environ.get("VPC_ID")
        
        if use_vpc or vpc_id:
            multi_agent_stack = OscarVpcMultiAgentStack(
                self,
                "VpcMultiAgentStack",
                vpc_id=vpc_id
            )
        else:
            multi_agent_stack = OscarMultiAgentStack(
                self,
                "MultiAgentStack"
            )
        
        # Export important outputs
        CfnOutput(
            self, 
            "SlackBotApiUrl",
            value=lambda_stack.api.url,
            description="Base URL of the API Gateway endpoint"
        )
        
        CfnOutput(
            self, 
            "SlackBotFunctionName",
            value=lambda_stack.lambda_function.function_name,
            description="Name of the Lambda function"
        )
        
        CfnOutput(
            self, 
            "MetricsLambdaFunctionName",
            value=metrics_lambda_stack.lambda_function.function_name,
            description="Name of the metrics Lambda function (legacy)"
        )
        
        CfnOutput(
            self, 
            "AgentRouterFunctionName",
            value=multi_agent_stack.agent_router_function.function_name,
            description="Name of the multi-agent router Lambda function"
        )