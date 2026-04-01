# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for OSCAR secrets stack."""

import pytest
from aws_cdk import App, Environment
from aws_cdk.assertions import Template

from agents.jenkins import JenkinsAgent
from stacks.secrets_stack import OscarSecretsStack


@pytest.fixture
def template_no_agents():
    """Synthesise secrets stack without agents."""
    app = App()
    stack = OscarSecretsStack(
        app, "TestSecretsStack",
        environment="dev",
        env=Environment(account="123456789012", region="us-east-1"),
    )
    return Template.from_stack(stack)


@pytest.fixture
def template_with_agents():
    """Synthesise secrets stack with Jenkins agent (which declares a secret)."""
    app = App()
    stack = OscarSecretsStack(
        app, "TestSecretsStackPlugins",
        environment="dev",
        agents=[JenkinsAgent()],
        env=Environment(account="123456789012", region="us-east-1"),
    )
    return Template.from_stack(stack)


class TestSecretsStack:
    """Test cases for OscarSecretsStack."""

    def test_central_secret_created(self, template_no_agents):
        """Central environment secret should exist."""
        template_no_agents.has_resource_properties("AWS::SecretsManager::Secret", {
            "Name": "oscar-central-env-dev",
            "Description": "Central environment variables for OSCAR (includes all tokens and config)",
        })

    def test_one_secret_without_agents(self, template_no_agents):
        """Only the central secret should exist when no agents are registered."""
        template_no_agents.resource_count_is("AWS::SecretsManager::Secret", 1)

    def test_agent_secret_created(self, template_with_agents):
        """Jenkins agent's api-token secret should be created."""
        template_with_agents.has_resource_properties("AWS::SecretsManager::Secret", {
            "Name": "oscar-jenkins-api-token-dev",
            "Description": "Jenkins API token in username:token format",
        })

    def test_two_secrets_with_jenkins_agent(self, template_with_agents):
        """Central secret + Jenkins api-token secret = 2."""
        template_with_agents.resource_count_is("AWS::SecretsManager::Secret", 2)
