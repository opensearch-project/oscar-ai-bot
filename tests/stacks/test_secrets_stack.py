# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for OSCAR secrets stack."""

import pytest
from aws_cdk import App, Environment
from aws_cdk.assertions import Template

from plugins.jenkins import JenkinsPlugin
from stacks.secrets_stack import OscarSecretsStack


@pytest.fixture
def template_no_plugins():
    """Synthesise secrets stack without plugins."""
    app = App()
    stack = OscarSecretsStack(
        app, "TestSecretsStack",
        environment="dev",
        env=Environment(account="123456789012", region="us-east-1"),
    )
    return Template.from_stack(stack)


@pytest.fixture
def template_with_plugins():
    """Synthesise secrets stack with Jenkins plugin (which declares a secret)."""
    app = App()
    stack = OscarSecretsStack(
        app, "TestSecretsStackPlugins",
        environment="dev",
        plugins=[JenkinsPlugin()],
        env=Environment(account="123456789012", region="us-east-1"),
    )
    return Template.from_stack(stack)


class TestSecretsStack:
    """Test cases for OscarSecretsStack."""

    def test_central_secret_created(self, template_no_plugins):
        """Central environment secret should exist."""
        template_no_plugins.has_resource_properties("AWS::SecretsManager::Secret", {
            "Name": "oscar-central-env-dev",
            "Description": "Central environment variables for OSCAR (includes all tokens and config)",
        })

    def test_one_secret_without_plugins(self, template_no_plugins):
        """Only the central secret should exist when no plugins are registered."""
        template_no_plugins.resource_count_is("AWS::SecretsManager::Secret", 1)

    def test_plugin_secret_created(self, template_with_plugins):
        """Jenkins plugin's api-token secret should be created."""
        template_with_plugins.has_resource_properties("AWS::SecretsManager::Secret", {
            "Name": "oscar-jenkins-api-token-dev",
            "Description": "Jenkins API token in username:token format",
        })

    def test_two_secrets_with_jenkins_plugin(self, template_with_plugins):
        """Central secret + Jenkins api-token secret = 2."""
        template_with_plugins.resource_count_is("AWS::SecretsManager::Secret", 2)
