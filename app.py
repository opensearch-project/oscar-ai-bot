#!/usr/bin/env python
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""
Main CDK application for OSCAR infrastructure.

This module defines the main CDK application that deploys the complete OSCAR infrastructure
including permissions, secrets, storage, VPC, API Gateway, Knowledge Base, Lambda functions,
and Bedrock agents.
"""

import logging
import os
from typing import Optional

from aws_cdk import App, Environment

from plugins.jenkins import JenkinsPlugin
from plugins.metrics.build import MetricsBuildPlugin
from plugins.metrics.release import MetricsReleasePlugin
from plugins.metrics.test import MetricsTestPlugin
from stacks.api_gateway_stack import OscarApiGatewayStack
from stacks.bedrock_agents_stack import OscarAgentsStack
from stacks.knowledge_base_stack import OscarKnowledgeBaseStack
from stacks.lambda_stack import OscarLambdaStack
from stacks.permissions_stack import OscarPermissionsStack
from stacks.secrets_stack import OscarSecretsStack
from stacks.storage_stack import OscarStorageStack
from stacks.vpc_stack import OscarVpcStack

# Load environment variables from .env file
# load_dotenv()


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main() -> None:
    """
    Deploy the complete OSCAR infrastructure.
    This function initializes the CDK app, creates all required stacks in dependency order,
    and synthesizes the CloudFormation templates.
    """
    app = App()

    # Get account and region from environment variables
    account: Optional[str] = os.environ.get("CDK_DEFAULT_ACCOUNT")
    region: Optional[str] = os.environ.get("CDK_DEFAULT_REGION", "us-east-1")
    environment = app.node.try_get_context('ENVIRONMENT') or 'dev'

    if not account:
        raise ValueError("CDK_DEFAULT_ACCOUNT environment variable must be set")

    logger.info(f"Deploying to region: {region}")
    logger.info(f"Environment: {environment}")

    env = Environment(account=account, region=region)

    # Register plugins
    plugins = [
        JenkinsPlugin(),
        MetricsBuildPlugin(),
        MetricsTestPlugin(),
        MetricsReleasePlugin(),
    ]

    # Deploy stacks in dependency order
    # 1. Permissions (IAM roles and policies)
    permissions_stack = OscarPermissionsStack(
        app, f"OscarPermissionsStack-{environment}",
        env=env,
        description="OSCAR IAM permissions and roles",
        environment=environment,
        plugins=plugins
    )

    # 2. Secrets (AWS Secrets Manager)
    secrets_stack = OscarSecretsStack(
        app, f"OscarSecretsStack-{environment}",
        env=env,
        description="OSCAR secrets management",
        environment=environment
    )

    # 3. Storage (DynamoDB tables)
    storage_stack = OscarStorageStack(
        app, f"OscarStorageStack-{environment}",
        env=env,
        description="OSCAR DynamoDB storage",
        environment=environment
    )

    # 4. VPC
    vpc_stack = OscarVpcStack(
        app, f"OscarVpcStack-{environment}",
        env=env,
        description="OSCAR VPC configuration"
    )

    # 5. Knowledge Base
    knowledge_base_stack = OscarKnowledgeBaseStack(
        app, f"OscarKnowledgeBaseStack-{environment}",
        env=env,
        description="OSCAR Bedrock Knowledge Base",
        environment=environment,
        github_repositories=[
            "opensearch-project/opensearch-build",
            "opensearch-project/opensearch-build-libraries"
        ]
    )

    # 6. Lambda Functions
    lambda_stack = OscarLambdaStack(
        app, f"OscarLambdaStack-{environment}",
        permissions_stack=permissions_stack,
        secrets_stack=secrets_stack,
        vpc_stack=vpc_stack,
        storage_stack=storage_stack,
        env=env,
        environment=environment,
        plugins=plugins,
        description="OSCAR Lambda functions"
    )
    lambda_stack.add_dependency(permissions_stack)
    lambda_stack.add_dependency(secrets_stack)
    lambda_stack.add_dependency(vpc_stack)
    lambda_stack.add_dependency(storage_stack)

    # 7. API Gateway
    api_gateway_stack = OscarApiGatewayStack(
        app, f"OscarApiGatewayStack-{environment}",
        lambda_stack=lambda_stack,
        permissions_stack=permissions_stack,
        env=env,
        description="OSCAR API Gateway",
        environment=environment
    )
    api_gateway_stack.add_dependency(permissions_stack)
    api_gateway_stack.add_dependency(lambda_stack)

    # 8. Bedrock Agents
    agents_stack = OscarAgentsStack(
        app, f"OscarAgentsStack-{environment}",
        permissions_stack=permissions_stack,
        lambda_stack=lambda_stack,
        env=env,
        environment=environment,
        plugins=plugins,
        description="OSCAR Bedrock agents"
    )
    agents_stack.add_dependency(permissions_stack)
    agents_stack.add_dependency(knowledge_base_stack)
    agents_stack.add_dependency(lambda_stack)

    # Synthesize the CloudFormation templates
    app.synth()


if __name__ == "__main__":
    main()
