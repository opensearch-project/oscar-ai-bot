# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for OSCAR API Gateway stack."""

from unittest.mock import MagicMock

import pytest
from aws_cdk import App, Environment, Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda
from aws_cdk.assertions import Template

from stacks.api_gateway_stack import OscarApiGatewayStack

ENV = Environment(account="123456789012", region="us-east-1")


@pytest.fixture
def template():
    """Synthesise the API Gateway stack with lightweight mocked dependencies."""
    app = App()

    # Create a helper stack to hold the mock Lambda function and IAM role
    helper = Stack(app, "Helper", env=ENV)

    mock_fn = aws_lambda.Function(
        helper, "MockLambda",
        runtime=aws_lambda.Runtime.PYTHON_3_12,
        handler="index.handler",
        code=aws_lambda.Code.from_inline("def handler(e,c): pass"),
        function_name="oscar-supervisor-agent-dev",
    )

    mock_role = iam.Role(
        helper, "MockApiGwRole",
        assumed_by=iam.ServicePrincipal("apigateway.amazonaws.com"),
    )

    # Wire up the mocks as the API Gateway stack expects them
    lambda_stack = MagicMock()
    lambda_stack.lambda_functions = {"oscar-supervisor-agent-dev": mock_fn}
    lambda_stack.get_supervisor_agent_function_name.return_value = "oscar-supervisor-agent-dev"

    permissions_stack = MagicMock()
    permissions_stack.api_gateway_role = mock_role

    stack = OscarApiGatewayStack(
        app, "TestApiGateway",
        lambda_stack=lambda_stack,
        permissions_stack=permissions_stack,
        environment="dev",
        env=ENV,
    )
    return Template.from_stack(stack)


class TestApiGatewayStack:
    """Test cases for OscarApiGatewayStack."""

    def test_rest_api_created(self, template):
        """One REST API should be created."""
        template.resource_count_is("AWS::ApiGateway::RestApi", 1)

    def test_rest_api_properties(self, template):
        """REST API should have correct name and configuration."""
        template.has_resource_properties("AWS::ApiGateway::RestApi", {
            "Name": "oscar-slack-bot-api-dev",
            "Description": "OSCAR Slack Bot API Gateway for webhook endpoints",
            "EndpointConfiguration": {
                "Types": ["REGIONAL"],
            },
        })

    def test_post_method_exists(self, template):
        """At least one POST method should exist for Slack events."""
        method_count = len(template.find_resources("AWS::ApiGateway::Method"))
        assert method_count >= 1, f"Expected at least 1 API Gateway Method, got {method_count}"

    def test_post_method_no_auth(self, template):
        """Slack events POST method should have no authorization."""
        template.has_resource_properties("AWS::ApiGateway::Method", {
            "HttpMethod": "POST",
            "AuthorizationType": "NONE",
        })

    def test_deployment_stage_created(self, template):
        """A deployment stage should be created."""
        template.has_resource_properties("AWS::ApiGateway::Stage", {
            "StageName": "prod",
        })

    def test_log_group_created(self, template):
        """CloudWatch log group for API access logs should exist."""
        template.has_resource_properties("AWS::Logs::LogGroup", {
            "LogGroupName": "/aws/apigateway/oscar-slack-bot-dev",
        })
