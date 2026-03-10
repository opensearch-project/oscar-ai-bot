# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for OSCAR Lambda stack."""

import os

import pytest
from aws_cdk import App, Environment
from aws_cdk.assertions import Match, Template

from plugins.jenkins import JenkinsPlugin
from plugins.metrics.build import MetricsBuildPlugin
from plugins.metrics.release import MetricsReleasePlugin
from plugins.metrics.test import MetricsTestPlugin
from stacks.lambda_stack import OscarLambdaStack
from stacks.permissions_stack import OscarPermissionsStack
from stacks.secrets_stack import OscarSecretsStack
from stacks.storage_stack import OscarStorageStack
from stacks.vpc_stack import OscarVpcStack

PLUGINS = [JenkinsPlugin(), MetricsBuildPlugin(), MetricsTestPlugin(), MetricsReleasePlugin()]
ENV = Environment(account="123456789012", region="us-east-1")


@pytest.fixture
def template():
    """Synthesise the Lambda stack, skipping Docker bundling for speed."""
    os.environ["CDK_DEFAULT_ACCOUNT"] = "123456789012"
    os.environ["CDK_DEFAULT_REGION"] = "us-east-1"

    # Skip Docker bundling — CDK will use placeholder code assets
    app = App(context={"aws:cdk:bundling-stacks": []})

    permissions = OscarPermissionsStack(
        app, "Perms", environment="dev", plugins=PLUGINS, env=ENV,
    )
    secrets = OscarSecretsStack(
        app, "Secrets", environment="dev", plugins=PLUGINS, env=ENV,
    )
    storage = OscarStorageStack(
        app, "Storage", environment="dev", env=ENV,
    )
    vpc = OscarVpcStack(app, "Vpc", env=ENV)

    stack = OscarLambdaStack(
        app, "TestLambdaStack",
        permissions_stack=permissions,
        secrets_stack=secrets,
        storage_stack=storage,
        vpc_stack=vpc,
        environment="dev",
        plugins=PLUGINS,
        env=ENV,
    )
    return Template.from_stack(stack)


class TestLambdaStack:
    """Test cases for OscarLambdaStack."""

    def test_supervisor_agent_lambda_created(self, template):
        """Main oscar-agent Lambda function should exist."""
        template.has_resource_properties("AWS::Lambda::Function", {
            "FunctionName": "oscar-supervisor-agent-dev",
            "Runtime": "python3.12",
            "Handler": "app.lambda_handler",
            "Timeout": 300,
            "MemorySize": 1024,
        })

    def test_communication_handler_lambda_created(self, template):
        """Communication handler Lambda should exist."""
        template.has_resource_properties("AWS::Lambda::Function", {
            "FunctionName": "oscar-communication-handler-dev",
            "Runtime": "python3.12",
            "Handler": "lambda_function.lambda_handler",
            "Timeout": 60,
            "MemorySize": 512,
        })

    def test_jenkins_plugin_lambda_created(self, template):
        """Jenkins plugin Lambda should exist."""
        template.has_resource_properties("AWS::Lambda::Function", {
            "FunctionName": "oscar-jenkins-dev",
            "Runtime": "python3.12",
        })

    def test_metrics_plugin_lambda_created(self, template):
        """Metrics plugins should share a single Lambda (same entry path)."""
        template.has_resource_properties("AWS::Lambda::Function", {
            "FunctionName": "oscar-metrics-build-dev",
            "Runtime": "python3.12",
        })

    def test_supervisor_agent_env_vars(self, template):
        """Supervisor agent Lambda should have required environment variables."""
        template.has_resource_properties("AWS::Lambda::Function", {
            "FunctionName": "oscar-supervisor-agent-dev",
            "Environment": {
                "Variables": Match.object_like({
                    "CONTEXT_TABLE_NAME": "oscar-agent-context-dev",
                    "OSCAR_PRIVILEGED_BEDROCK_AGENT_ID_PARAM_PATH":
                        "/oscar/dev/bedrock/supervisor-agent-id",
                    "OSCAR_PRIVILEGED_BEDROCK_AGENT_ALIAS_PARAM_PATH":
                        "/oscar/dev/bedrock/supervisor-agent-alias",
                    "OSCAR_LIMITED_BEDROCK_AGENT_ID_PARAM_PATH":
                        "/oscar/dev/bedrock/limited-supervisor-agent-id",
                    "OSCAR_LIMITED_BEDROCK_AGENT_ALIAS_PARAM_PATH":
                        "/oscar/dev/bedrock/limited-supervisor-agent-alias",
                }),
            },
        })

    def test_communication_handler_env_vars(self, template):
        """Communication handler Lambda should have required environment variables."""
        template.has_resource_properties("AWS::Lambda::Function", {
            "FunctionName": "oscar-communication-handler-dev",
            "Environment": {
                "Variables": Match.object_like({
                    "CONTEXT_TABLE_NAME": "oscar-agent-context-dev",
                }),
            },
        })

    def test_bedrock_invoke_permission_on_supervisor(self, template):
        """Bedrock should have invoke permission on supervisor Lambda."""
        template.has_resource_properties("AWS::Lambda::Permission", {
            "Action": "lambda:InvokeFunction",
            "Principal": "bedrock.amazonaws.com",
        })

    def test_self_invoke_permission(self, template):
        """Supervisor Lambda should have self-invoke permission for async processing."""
        template.has_resource_properties("AWS::Lambda::Permission", {
            "Action": "lambda:InvokeFunction",
            "Principal": "lambda.amazonaws.com",
        })
