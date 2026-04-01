# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for OSCAR permissions stack."""

import os

import pytest
from aws_cdk import App, Environment
from aws_cdk.assertions import Template

from agents.jenkins import JenkinsAgent
from agents.metrics import MetricsAgent
from stacks.permissions_stack import OscarPermissionsStack


@pytest.fixture
def template():
    """Synthesise the permissions stack and return its CloudFormation template."""
    os.environ["CDK_DEFAULT_ACCOUNT"] = "123456789012"
    os.environ["CDK_DEFAULT_REGION"] = "us-east-1"

    app = App()
    agents_list = [JenkinsAgent(), MetricsAgent()]
    stack = OscarPermissionsStack(
        app,
        "TestOscarPermissionsStack",
        environment="dev",
        agents=agents_list,
        env=Environment(account="123456789012", region="us-east-1"),
    )
    return Template.from_stack(stack)


class TestOscarPermissionsStack:
    """Test cases for OscarPermissionsStack."""

    def test_bedrock_agent_role_creation(self, template):
        """Test that Bedrock agent execution role is created."""
        template.has_resource_properties("AWS::IAM::Role", {
            "AssumeRolePolicyDocument": {
                "Statement": [{
                    "Effect": "Allow",
                    "Principal": {"Service": "bedrock.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }],
            },
        })

    def test_core_lambda_roles_creation(self, template):
        """Test that core Lambda execution roles are created."""
        # Base Lambda role (oscar-agent)
        template.has_resource_properties("AWS::IAM::Role", {
            "AssumeRolePolicyDocument": {
                "Statement": [{
                    "Effect": "Allow",
                    "Principal": {"Service": "lambda.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }],
            },
            "Description": "Base execution role for OSCAR Lambda functions",
        })

        # Communication handler role
        template.has_resource_properties("AWS::IAM::Role", {
            "Description": "Execution role for OSCAR communication handler Lambda",
        })

    def test_agent_roles_creation(self, template):
        """Test that agent Lambda roles are created (deduplicated by entry path)."""
        template.has_resource_properties("AWS::IAM::Role", {
            "Description": "Execution role for OSCAR jenkins Lambda",
        })
        # All metrics agents share the same Lambda entry, so they share one role
        template.has_resource_properties("AWS::IAM::Role", {
            "Description": "Execution role for OSCAR metrics Lambda",
        })

    def test_api_gateway_role_creation(self, template):
        """Test that API Gateway execution role is created."""
        template.has_resource_properties("AWS::IAM::Role", {
            "AssumeRolePolicyDocument": {
                "Statement": [{
                    "Effect": "Allow",
                    "Principal": {"Service": "apigateway.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }],
            },
        })

    def test_least_privilege_policies(self, template):
        """Test that no sensitive actions use wildcard resources."""
        template_dict = template.to_json()

        sensitive_actions = [
            "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
            "lambda:InvokeFunction", "secretsmanager:GetSecretValue",
        ]

        for resource_name, resource in template_dict.get("Resources", {}).items():
            if resource.get("Type") == "AWS::IAM::Policy":
                statements = resource.get("Properties", {}).get("PolicyDocument", {}).get("Statement", [])
                for statement in statements:
                    actions = statement.get("Action", [])
                    resources = statement.get("Resource", [])
                    if isinstance(actions, str):
                        actions = [actions]
                    if isinstance(resources, str):
                        resources = [resources]

                    for action in actions:
                        if any(s in action for s in sensitive_actions):
                            assert "*" not in resources, \
                                f"Action {action} should not use wildcard resources"
