#!/usr/bin/env python
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.
"""
Example usage of OSCAR permissions stack.

This example demonstrates how to use the OscarPermissionsStack
in a CDK application with proper configuration.
"""

import os
from aws_cdk import App, Stack, Environment, CfnOutput
from constructs import Construct
from stacks.permissions_stack import OscarPermissionsStack


class ExamplePermissionsApp(Stack):
    """
    Example CDK stack that uses OscarPermissionsStack.
    
    This demonstrates how to integrate the permissions stack
    into a larger CDK application.
    """
    
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        """
        Initialize the example stack.
        
        Args:
            scope: The CDK construct scope
            construct_id: The ID of the construct
            **kwargs: Additional keyword arguments
        """
        super().__init__(scope, construct_id, **kwargs)
        
        # Create the permissions stack
        self.permissions = OscarPermissionsStack(
            self, "OscarPermissions"
        )
        
        # Example: Use the roles in other resources
        self._create_example_outputs()
    
    def _create_example_outputs(self) -> None:
        """Create example outputs showing how to use the roles."""
        
        # Output the Bedrock agent role ARN for use in agent creation
        CfnOutput(
            self, "ExampleBedrockAgentRoleArn",
            value=self.permissions.bedrock_agent_role.role_arn,
            description="Use this role ARN when creating Bedrock agents",
            export_name="oscar-bedrock-agent-role-arn"
        )
        
        # Output Lambda execution role ARNs for use in Lambda functions
        for role_type, role in self.permissions.lambda_execution_roles.items():
            CfnOutput(
                self, f"ExampleLambdaRole{role_type.title()}Arn",
                value=role.role_arn,
                description=f"Use this role ARN for {role_type} Lambda functions",
                export_name=f"oscar-lambda-{role_type}-role-arn"
            )
        
        # Output API Gateway role ARN for use in API Gateway configuration
        CfnOutput(
            self, "ExampleApiGatewayRoleArn",
            value=self.permissions.api_gateway_role.role_arn,
            description="Use this role ARN for API Gateway configuration",
            export_name="oscar-api-gateway-role-arn"
        )


def main() -> None:
    """
    Main function to deploy the example permissions stack.
    
    This function demonstrates how to deploy the OSCAR permissions
    stack as part of a CDK application.
    """
    # Set required environment variables
    os.environ.setdefault("CDK_DEFAULT_ACCOUNT", "123456789012")
    os.environ.setdefault("CDK_DEFAULT_REGION", "us-east-1")
    
    app = App()
    
    # Create the example stack
    ExamplePermissionsApp(
        app, "OscarPermissionsExample",
        env=Environment(
            account=os.environ["CDK_DEFAULT_ACCOUNT"],
            region=os.environ["CDK_DEFAULT_REGION"]
        ),
        description="Example OSCAR permissions stack deployment"
    )
    
    # Synthesize the CloudFormation template
    app.synth()


if __name__ == "__main__":
    main()