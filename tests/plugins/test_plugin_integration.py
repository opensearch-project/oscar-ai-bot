# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""Integration tests validating plugins conform to the OscarPlugin interface
and are wired correctly into CDK stacks."""

import os

import pytest
from aws_cdk import App, Environment
from aws_cdk.assertions import Template

from plugins.base_plugin import LambdaConfig, OscarPlugin
from plugins.jenkins import JenkinsPlugin
from plugins.metrics.build import MetricsBuildPlugin
from plugins.metrics.release import MetricsReleasePlugin
from plugins.metrics.test import MetricsTestPlugin
from stacks.lambda_stack import OscarLambdaStack
from stacks.permissions_stack import OscarPermissionsStack
from stacks.secrets_stack import OscarSecretsStack
from stacks.storage_stack import OscarStorageStack
from stacks.vpc_stack import OscarVpcStack

ALL_PLUGINS = [JenkinsPlugin(), MetricsBuildPlugin(), MetricsTestPlugin(), MetricsReleasePlugin()]
PLUGIN_IDS = [p.name for p in ALL_PLUGINS]
ENV = Environment(account="123456789012", region="us-east-1")


# ---------------------------------------------------------------------------
# Plugin contract tests (parametrized over every plugin)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("plugin", ALL_PLUGINS, ids=PLUGIN_IDS)
class TestPluginContract:
    """Every plugin must satisfy the OscarPlugin interface."""

    def test_is_oscar_plugin_subclass(self, plugin):
        assert isinstance(plugin, OscarPlugin)

    def test_name_is_non_empty_string(self, plugin):
        assert isinstance(plugin.name, str)
        assert len(plugin.name) > 0

    def test_get_lambda_config_returns_lambda_config(self, plugin):
        config = plugin.get_lambda_config()
        assert isinstance(config, LambdaConfig)

    def test_lambda_entry_path_exists(self, plugin):
        config = plugin.get_lambda_config()
        assert os.path.isdir(config.entry), f"Entry path {config.entry} does not exist"

    def test_lambda_index_file_exists(self, plugin):
        config = plugin.get_lambda_config()
        index_path = os.path.join(config.entry, config.index)
        assert os.path.isfile(index_path), f"Index file {index_path} does not exist"

    def test_get_iam_policies_returns_list(self, plugin):
        policies = plugin.get_iam_policies("123456789012", "us-east-1", "dev")
        assert isinstance(policies, list)

    def test_get_action_groups_returns_list(self, plugin):
        # Action groups need a Lambda ARN; use a placeholder
        groups = plugin.get_action_groups("arn:aws:lambda:us-east-1:123456789012:function:placeholder")
        assert isinstance(groups, list)
        assert len(groups) >= 1, "Plugin must define at least one action group"

    def test_get_agent_instruction_non_empty(self, plugin):
        instruction = plugin.get_agent_instruction()
        assert isinstance(instruction, str)
        assert len(instruction) > 0

    def test_get_collaborator_instruction_non_empty(self, plugin):
        instruction = plugin.get_collaborator_instruction()
        assert isinstance(instruction, str)
        assert len(instruction) > 0

    def test_get_collaborator_name_non_empty(self, plugin):
        name = plugin.get_collaborator_name()
        assert isinstance(name, str)
        assert len(name) > 0

    def test_access_level_valid(self, plugin):
        level = plugin.get_access_level()
        assert level in ("privileged", "limited", "both"), \
            f"Invalid access level: {level}"


# ---------------------------------------------------------------------------
# Plugin registration tests
# ---------------------------------------------------------------------------

class TestPluginRegistration:
    """Validate the specific plugin set and their access levels."""

    def test_four_plugins_registered(self):
        assert len(ALL_PLUGINS) == 4

    def test_plugin_names_are_unique(self):
        names = [p.name for p in ALL_PLUGINS]
        assert len(names) == len(set(names)), f"Duplicate plugin names: {names}"

    def test_jenkins_is_privileged_only(self):
        assert JenkinsPlugin().get_access_level() == "privileged"

    def test_metrics_build_access_level(self):
        assert MetricsBuildPlugin().get_access_level() == "both"

    def test_metrics_test_access_level(self):
        assert MetricsTestPlugin().get_access_level() == "both"

    def test_metrics_release_access_level(self):
        assert MetricsReleasePlugin().get_access_level() == "both"


# ---------------------------------------------------------------------------
# CDK stack wiring tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def stacks():
    """Synthesise the Lambda stack with all plugins (no Docker bundling)."""
    os.environ["CDK_DEFAULT_ACCOUNT"] = "123456789012"
    os.environ["CDK_DEFAULT_REGION"] = "us-east-1"

    app = App(context={"aws:cdk:bundling-stacks": []})

    permissions = OscarPermissionsStack(
        app, "Perms", environment="dev", plugins=ALL_PLUGINS, env=ENV,
    )
    secrets = OscarSecretsStack(
        app, "Secrets", environment="dev", plugins=ALL_PLUGINS, env=ENV,
    )
    storage = OscarStorageStack(app, "Storage", environment="dev", env=ENV)
    vpc = OscarVpcStack(app, "Vpc", env=ENV)

    lambda_stack = OscarLambdaStack(
        app, "Lambda",
        permissions_stack=permissions,
        secrets_stack=secrets,
        storage_stack=storage,
        vpc_stack=vpc,
        environment="dev",
        plugins=ALL_PLUGINS,
        env=ENV,
    )
    return lambda_stack


class TestPluginStackWiring:
    """Verify plugins are wired into the Lambda stack correctly."""

    def test_each_plugin_has_lambda_function(self, stacks):
        """Every plugin name should have an entry in lambda_functions."""
        for plugin in ALL_PLUGINS:
            assert plugin.name in stacks.lambda_functions, \
                f"Plugin '{plugin.name}' missing from lambda_functions"

    def test_metrics_plugins_share_one_lambda(self, stacks):
        """All 3 metrics plugins should resolve to the same Lambda (shared entry path)."""
        build_fn = stacks.lambda_functions["metrics-build"]
        test_fn = stacks.lambda_functions["metrics-test"]
        release_fn = stacks.lambda_functions["metrics-release"]
        assert build_fn is test_fn, "metrics-build and metrics-test should share a Lambda"
        assert build_fn is release_fn, "metrics-build and metrics-release should share a Lambda"

    def test_jenkins_has_own_lambda(self, stacks):
        """Jenkins should have a separate Lambda from metrics."""
        jenkins_fn = stacks.lambda_functions["jenkins"]
        metrics_fn = stacks.lambda_functions["metrics-build"]
        assert jenkins_fn is not metrics_fn

    def test_lambda_function_count(self, stacks):
        """Should be 4 entries in lambda_functions dict (4 plugins) + 2 core."""
        # 4 plugins + supervisor-agent + communication-handler = 6 entries
        # But 3 metrics share 1 Lambda object, so 6 keys but 4 unique functions
        assert len(stacks.lambda_functions) == 6

    def test_lambda_template_function_count(self, stacks):
        """CloudFormation template should have 4 Lambda functions
        (supervisor + communication + jenkins + 1 shared metrics)."""
        template = Template.from_stack(stacks)
        template.resource_count_is("AWS::Lambda::Function", 4)
