# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for OSCAR Security Monitoring stack."""

import os

import pytest
from aws_cdk import App, Environment
from aws_cdk.assertions import Match, Template

from agents.jenkins import JenkinsAgent
from agents.metrics import MetricsAgent
from stacks.permissions_stack import OscarPermissionsStack
from stacks.secrets_stack import OscarSecretsStack
from stacks.security_monitoring_stack import (CORE_MONITORING,
                                              OscarSecurityMonitoringStack)
from stacks.storage_stack import OscarStorageStack

ALL_AGENTS = [JenkinsAgent(), MetricsAgent()]
ENV = Environment(account="123456789012", region="us-east-1")


@pytest.fixture(scope="module")
def template():
    os.environ["CDK_DEFAULT_ACCOUNT"] = "123456789012"
    os.environ["CDK_DEFAULT_REGION"] = "us-east-1"

    app = App(context={"aws:cdk:bundling-stacks": []})

    permissions = OscarPermissionsStack(
        app, "MonPerms", environment="dev", agents=ALL_AGENTS, env=ENV,
    )
    secrets = OscarSecretsStack(
        app, "MonSecrets", environment="dev", agents=ALL_AGENTS, env=ENV,
    )
    storage = OscarStorageStack(app, "MonStorage", environment="dev", env=ENV)

    stack = OscarSecurityMonitoringStack(
        app, "TestSecurityMonitoring",
        environment="dev",
        permissions_stack=permissions,
        secrets_stack=secrets,
        storage_stack=storage,
        agents=ALL_AGENTS,
        env=ENV,
    )
    return Template.from_stack(stack)


class TestSecurityMonitoringStack:

    def test_sns_topic_created(self, template):
        template.has_resource_properties("AWS::SNS::Topic", {
            "TopicName": "oscar-security-alerts-dev",
        })

    def test_metric_filter_count(self, template):
        """Total metric filters = core + all agent-declared configs."""
        expected = len(CORE_MONITORING) + sum(
            len(a.get_monitoring_config()) for a in ALL_AGENTS
        )
        template.resource_count_is("AWS::Logs::MetricFilter", expected)

    def test_alarm_count_matches_filters(self, template):
        """Each metric filter should have exactly one alarm. Total: 3 core + 2 jenkins + 3 metrics = 8."""
        template.resource_count_is("AWS::CloudWatch::Alarm", 8)

    def test_all_alarms_have_sns_action(self, template):
        alarms = template.find_resources("AWS::CloudWatch::Alarm")
        for alarm in alarms.values():
            actions = alarm["Properties"].get("AlarmActions", [])
            assert len(actions) == 1

    def test_unauthorized_dm_filter(self, template):
        template.has_resource_properties("AWS::Logs::MetricFilter", {
            "FilterPattern": Match.string_like_regexp("UNAUTHORIZED_DM_ATTEMPT"),
        })

    def test_guardrail_filter(self, template):
        template.has_resource_properties("AWS::Logs::MetricFilter", {
            "FilterPattern": Match.string_like_regexp("GUARDRAIL_INTERVENED"),
        })

    def test_prompt_injection_filter(self, template):
        template.has_resource_properties("AWS::Logs::MetricFilter", {
            "FilterPattern": Match.string_like_regexp("PROMPT_INJECTION_DETECTED"),
        })

    def test_dashboard_created(self, template):
        template.resource_count_is("AWS::CloudWatch::Dashboard", 1)

    def test_dashboard_name(self, template):
        template.has_resource_properties("AWS::CloudWatch::Dashboard", {
            "DashboardName": "oscar-security-dev",
        })
