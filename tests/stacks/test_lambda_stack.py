# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for OSCAR Lambda stack."""

import json
import os

import pytest
from aws_cdk import App, Environment
from aws_cdk.assertions import Match, Template

from agents.jenkins import JenkinsAgent
from agents.metrics import MetricsAgent
from stacks.lambda_stack import OscarLambdaStack
from stacks.permissions_stack import OscarPermissionsStack
from stacks.secrets_stack import OscarSecretsStack
from stacks.storage_stack import OscarStorageStack
from stacks.vpc_stack import OscarVpcStack

AGENTS = [JenkinsAgent(), MetricsAgent()]
ENV = Environment(account="123456789012", region="us-east-1")


@pytest.fixture
def template():
    """Synthesise the Lambda stack, skipping Docker bundling for speed."""
    os.environ["CDK_DEFAULT_ACCOUNT"] = "123456789012"
    os.environ["CDK_DEFAULT_REGION"] = "us-east-1"

    # Skip Docker bundling — CDK will use placeholder code assets
    app = App(context={"aws:cdk:bundling-stacks": []})

    permissions = OscarPermissionsStack(
        app, "Perms", environment="dev", agents=AGENTS, env=ENV,
    )
    secrets = OscarSecretsStack(
        app, "Secrets", environment="dev", agents=AGENTS, env=ENV,
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
        agents=AGENTS,
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

    def test_jenkins_agent_lambda_created(self, template):
        """Jenkins agent Lambda should exist."""
        template.has_resource_properties("AWS::Lambda::Function", {
            "FunctionName": "oscar-jenkins-dev",
            "Runtime": "python3.12",
        })

    def test_metrics_agent_lambda_created(self, template):
        """Unified metrics agent Lambda should exist."""
        template.has_resource_properties("AWS::Lambda::Function", {
            "FunctionName": "oscar-metrics-dev",
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


def _synth_with_identity():
    """Synthesise with identity tables configured, returning (lambda, permissions) templates.

    Grants made in the Lambda stack against a role owned by the permissions stack land in the
    permissions stack's template, so assertions about them need both.
    """
    os.environ["CDK_DEFAULT_ACCOUNT"] = "123456789012"
    os.environ["CDK_DEFAULT_REGION"] = "us-east-1"

    app = App(context={"aws:cdk:bundling-stacks": []})

    permissions = OscarPermissionsStack(
        app, "PermsIdentity", environment="dev", agents=AGENTS, env=ENV,
    )
    secrets = OscarSecretsStack(
        app, "SecretsIdentity", environment="dev", agents=AGENTS, env=ENV,
    )
    storage = OscarStorageStack(
        app, "StorageIdentity", environment="dev",
        workspace_id="T01INTERNAL",
        env=ENV,
    )
    vpc = OscarVpcStack(app, "VpcIdentity", env=ENV)

    stack = OscarLambdaStack(
        app, "TestLambdaStackIdentity",
        permissions_stack=permissions,
        secrets_stack=secrets,
        storage_stack=storage,
        vpc_stack=vpc,
        environment="dev",
        agents=AGENTS,
        env=ENV,
    )
    return Template.from_stack(stack), Template.from_stack(permissions)


@pytest.fixture
def template_with_identity():
    """The Lambda stack template, with identity tables configured."""
    return _synth_with_identity()[0]


@pytest.fixture
def permissions_template_with_identity():
    """The permissions stack template, which holds grants made against its roles."""
    return _synth_with_identity()[1]


class TestIdentityLambda:
    """Test cases for identity Lambda creation."""

    def test_identity_lambda_created(self, template_with_identity):
        """Identity Lambda should be created when workspace_id is configured."""
        template_with_identity.has_resource_properties("AWS::Lambda::Function", {
            "FunctionName": "oscar-identity-dev",
            "Runtime": "python3.12",
            "Handler": "lambda_function.lambda_handler",
            "Timeout": 300,
            "MemorySize": 256,
        })

    def test_identity_lambda_env_vars(self, template_with_identity):
        """Identity Lambda should have required environment variables."""
        template_with_identity.has_resource_properties("AWS::Lambda::Function", {
            "FunctionName": "oscar-identity-dev",
            "Environment": {
                "Variables": Match.object_like({
                    "ENVIRONMENT": "dev",
                    "IDENTITY_TABLE_NAME": Match.any_value(),
                }),
            },
        })

    def test_identity_validation_schedule_created(self, template_with_identity):
        """Weekly validation EventBridge rule should be created."""
        template_with_identity.has_resource_properties("AWS::Events::Rule", {
            "ScheduleExpression": "rate(7 days)",
            "Description": "Weekly identity membership validation",
        })

    def test_no_identity_lambda_without_workspace(self, template):
        """Identity Lambda should NOT be created when no workspace_id configured."""
        # The base template fixture has no workspace_id
        functions = template.find_resources("AWS::Lambda::Function")
        identity_fns = [
            k for k, v in functions.items()
            if v.get("Properties", {}).get("FunctionName", "").startswith("oscar-identity")
        ]
        assert len(identity_fns) == 0


class TestReleaseNotifierLambda:
    """Test cases for the scheduled release notifier."""

    def test_notifier_lambda_created(self, template):
        template.has_resource_properties("AWS::Lambda::Function", {
            "FunctionName": "oscar-release-notifier-dev",
            "Runtime": "python3.12",
            "Handler": "lambda_function.lambda_handler",
            "Timeout": 300,
            "MemorySize": 256,
        })

    def test_notifier_env_vars(self, template):
        """The notifier is told which metrics Lambda to call and where to record posts."""
        template.has_resource_properties("AWS::Lambda::Function", {
            "FunctionName": "oscar-release-notifier-dev",
            "Environment": {
                "Variables": Match.object_like({
                    "ENVIRONMENT": "dev",
                    "CENTRAL_SECRET_NAME": Match.any_value(),
                    "METRICS_FUNCTION_NAME": Match.any_value(),
                    "RELEASE_NOTIFY_TABLE_NAME": Match.any_value(),
                }),
            },
        })

    def test_metrics_function_name_references_the_metrics_lambda(self, template):
        """A Ref, not a rebuilt name string, so the two can never drift apart."""
        functions = template.find_resources(
            "AWS::Lambda::Function",
            {"Properties": {"FunctionName": "oscar-release-notifier-dev"}},
        )
        env = next(iter(functions.values()))["Properties"]["Environment"]["Variables"]
        assert env["METRICS_FUNCTION_NAME"]["Ref"].startswith("MetricsLambda")

    def test_six_hourly_schedule_created(self, template):
        template.has_resource_properties("AWS::Events::Rule", {
            "ScheduleExpression": "rate(6 hours)",
            "Description": "Six-hourly release readiness check",
        })

    def test_notifier_is_not_in_the_vpc(self, template):
        """The notifier reaches no cluster, so it must not pay for an ENI."""
        functions = template.find_resources(
            "AWS::Lambda::Function",
            {"Properties": {"FunctionName": "oscar-release-notifier-dev"}},
        )
        assert len(functions) == 1
        assert "VpcConfig" not in next(iter(functions.values()))["Properties"]

    def test_identity_table_not_injected_without_identity_mapping(self, template):
        """Identity mapping is beta/prod only - the notifier must not expect the table."""
        functions = template.find_resources(
            "AWS::Lambda::Function",
            {"Properties": {"FunctionName": "oscar-release-notifier-dev"}},
        )
        env = next(iter(functions.values()))["Properties"]["Environment"]["Variables"]
        assert "IDENTITY_TABLE_NAME" not in env

    def test_identity_table_injected_when_deployed(self, template_with_identity):
        """With the table deployed the notifier can tag the release manager."""
        template_with_identity.has_resource_properties("AWS::Lambda::Function", {
            "FunctionName": "oscar-release-notifier-dev",
            "Environment": {
                "Variables": Match.object_like({
                    "IDENTITY_TABLE_NAME": Match.any_value(),
                }),
            },
        })

    def test_notifier_gets_read_only_access_to_the_identity_table(
        self, permissions_template_with_identity,
    ):
        """Resolving a handle is a read - the notifier must never be able to alter a mapping."""
        policies = permissions_template_with_identity.find_resources("AWS::IAM::Policy")
        notifier_policy = next(
            p for name, p in policies.items() if name.startswith("ReleaseNotifierRole")
        )

        actions = set()
        for statement in notifier_policy["Properties"]["PolicyDocument"]["Statement"]:
            if "IdentityTable" not in json.dumps(statement.get("Resource")):
                continue
            declared = statement["Action"]
            actions.update(declared if isinstance(declared, list) else [declared])

        assert "dynamodb:Scan" in actions
        assert not {"dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem"} & actions

    def test_no_notifier_without_the_metrics_agent(self):
        """The verdict lives in the metrics Lambda, so the notifier is pointless without it."""
        os.environ["CDK_DEFAULT_ACCOUNT"] = "123456789012"
        os.environ["CDK_DEFAULT_REGION"] = "us-east-1"
        app = App(context={"aws:cdk:bundling-stacks": []})
        agents = [JenkinsAgent()]

        stack = OscarLambdaStack(
            app, "NoMetricsLambdaStack",
            permissions_stack=OscarPermissionsStack(
                app, "PermsNoMetrics", environment="dev", agents=agents, env=ENV),
            secrets_stack=OscarSecretsStack(
                app, "SecretsNoMetrics", environment="dev", agents=agents, env=ENV),
            storage_stack=OscarStorageStack(
                app, "StorageNoMetrics", environment="dev", env=ENV),
            vpc_stack=OscarVpcStack(app, "VpcNoMetrics", env=ENV),
            environment="dev",
            agents=agents,
            env=ENV,
        )
        functions = Template.from_stack(stack).find_resources(
            "AWS::Lambda::Function",
            {"Properties": {"FunctionName": "oscar-release-notifier-dev"}},
        )
        assert functions == {}
