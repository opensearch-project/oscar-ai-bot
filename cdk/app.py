#!/usr/bin/env python3
"""
Main CDK application for OSCAR Slack Bot.

This module defines the main CDK application that deploys the OSCAR Slack Bot stack.
"""

import os
import sys
from aws_cdk import (
    App,
    Environment,
    Tags
)
from stacks.oscar_slack_bot_stack import OscarSlackBotStack

def main():
    """Deploy the OSCAR Slack Bot stack."""
    app = App()

    # Get account and region from environment variables
    account = os.environ.get("CDK_DEFAULT_ACCOUNT")
    region = os.environ.get("CDK_DEFAULT_REGION")

    print(f"Deploying to account: {account}")
    print(f"Deploying to region: {region}")

    # Validate region
    if region != "us-west-2":
        print(f"ERROR: Region is set to {region}, but should be us-west-2")
        print("Please make sure CDK_DEFAULT_REGION is set correctly")
        sys.exit(1)

    # Deploy the main stack
    stack = OscarSlackBotStack(
        app, 
        "OscarSlackBotStack",
        env=Environment(
            account=account,
            region=region
        ),
        description="OSCAR Slack Bot infrastructure for OpenSearch release management"
    )
    
    # Add tags to all resources
    Tags.of(stack).add("Project", "OSCAR")
    Tags.of(stack).add("Service", "SlackBot")
    Tags.of(stack).add("Environment", os.environ.get("ENVIRONMENT", "dev"))
    
    # Synthesize the CloudFormation template
    app.synth()

if __name__ == "__main__":
    main()