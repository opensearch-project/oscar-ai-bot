# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""Integration tests validating agents conform to the OscarAgent interface
and are wired correctly into CDK stacks."""

import ast
import glob
import os

import pytest
from aws_cdk import App, Environment
from aws_cdk.assertions import Match, Template

from agents.base_agent import LambdaConfig, OscarAgent
from agents.jenkins import JenkinsAgent
from agents.metrics import MetricsAgent
from stacks.bedrock_agents_stack import OscarAgentsStack
from stacks.lambda_stack import OscarLambdaStack
from stacks.permissions_stack import OscarPermissionsStack
from stacks.secrets_stack import OscarSecretsStack
from stacks.storage_stack import OscarStorageStack
from stacks.vpc_stack import OscarVpcStack

ALL_AGENTS = [JenkinsAgent(), MetricsAgent()]
AGENT_IDS = [a.name for a in ALL_AGENTS]
ENV = Environment(account="123456789012", region="us-east-1")


# ---------------------------------------------------------------------------
# Agent contract tests (parametrized over every agent)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("agent", ALL_AGENTS, ids=AGENT_IDS)
class TestAgentContract:
    """Every agent must satisfy the OscarAgent interface."""

    def test_is_oscar_agent_subclass(self, agent):
        assert isinstance(agent, OscarAgent)

    def test_name_is_non_empty_string(self, agent):
        assert isinstance(agent.name, str)
        assert len(agent.name) > 0

    def test_get_lambda_config_returns_lambda_config(self, agent):
        config = agent.get_lambda_config()
        assert isinstance(config, LambdaConfig)

    def test_lambda_entry_path_exists(self, agent):
        config = agent.get_lambda_config()
        assert os.path.isdir(config.entry), f"Entry path {config.entry} does not exist"

    def test_lambda_index_file_exists(self, agent):
        config = agent.get_lambda_config()
        index_path = os.path.join(config.entry, config.index)
        assert os.path.isfile(index_path), f"Index file {index_path} does not exist"

    def test_get_iam_policies_returns_list(self, agent):
        policies = agent.get_iam_policies("123456789012", "us-east-1", "dev")
        assert isinstance(policies, list)

    def test_get_action_groups_returns_list(self, agent):
        # Action groups need a Lambda ARN; use a placeholder
        groups = agent.get_action_groups("arn:aws:lambda:us-east-1:123456789012:function:placeholder")
        assert isinstance(groups, list)
        assert len(groups) >= 1, "Agent must define at least one action group"

    def test_get_agent_instruction_non_empty(self, agent):
        instruction = agent.get_agent_instruction()
        assert isinstance(instruction, str)
        assert len(instruction) > 0

    def test_get_collaborator_instruction_non_empty(self, agent):
        instruction = agent.get_collaborator_instruction()
        assert isinstance(instruction, str)
        assert len(instruction) > 0

    def test_get_collaborator_name_non_empty(self, agent):
        name = agent.get_collaborator_name()
        assert isinstance(name, str)
        assert len(name) > 0

    def test_access_level_valid(self, agent):
        level = agent.get_access_level()
        assert level in ("privileged", "limited", "both"), \
            f"Invalid access level: {level}"


# ---------------------------------------------------------------------------
# Agent registration tests
# ---------------------------------------------------------------------------

class TestAgentRegistration:
    """Validate the specific agent set and their access levels."""

    def test_two_agents_registered(self):
        assert len(ALL_AGENTS) == 2

    def test_agent_names_are_unique(self):
        names = [p.name for p in ALL_AGENTS]
        assert len(names) == len(set(names)), f"Duplicate agent names: {names}"

    def test_jenkins_is_privileged_only(self):
        assert JenkinsAgent().get_access_level() == "privileged"

    def test_metrics_access_level(self):
        assert MetricsAgent().get_access_level() == "both"


# ---------------------------------------------------------------------------
# CDK stack wiring tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def stacks():
    """Synthesise the Lambda stack with all agents (no Docker bundling)."""
    os.environ["CDK_DEFAULT_ACCOUNT"] = "123456789012"
    os.environ["CDK_DEFAULT_REGION"] = "us-east-1"

    app = App(context={"aws:cdk:bundling-stacks": []})

    permissions = OscarPermissionsStack(
        app, "Perms", environment="dev", agents=ALL_AGENTS, env=ENV,
    )
    secrets = OscarSecretsStack(
        app, "Secrets", environment="dev", agents=ALL_AGENTS, env=ENV,
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
        agents=ALL_AGENTS,
        env=ENV,
    )
    return lambda_stack


class TestAgentStackWiring:
    """Verify agents are wired into the Lambda stack correctly."""

    def test_each_agent_has_lambda_function(self, stacks):
        """Every agent name should have an entry in lambda_functions."""
        for agent in ALL_AGENTS:
            assert agent.name in stacks.lambda_functions, \
                f"Agent '{agent.name}' missing from lambda_functions"

    def test_jenkins_has_own_lambda(self, stacks):
        """Jenkins should have a separate Lambda from metrics."""
        jenkins_fn = stacks.lambda_functions["jenkins"]
        metrics_fn = stacks.lambda_functions["metrics"]
        assert jenkins_fn is not metrics_fn

    def test_lambda_function_count(self, stacks):
        """Should be 2 agent entries + 2 core = 4 keys in lambda_functions dict."""
        # 2 agents + supervisor-agent + communication-handler = 4 entries
        assert len(stacks.lambda_functions) == 4

    def test_lambda_template_function_count(self, stacks):
        """CloudFormation template should have 4 Lambda functions
        (supervisor + communication + jenkins + unified metrics)."""
        template = Template.from_stack(stacks)
        template.resource_count_is("AWS::Lambda::Function", 4)


# ---------------------------------------------------------------------------
# Metrics agent — no-write guardrail tests
# ---------------------------------------------------------------------------

class TestMetricsNoWriteGuardrail:
    """Ensure the metrics agent never makes mutating requests to OpenSearch.

    All OpenSearch calls from the metrics Lambda must be read-only (GET).
    These tests statically verify that no code path can issue POST, PUT,
    or DELETE requests.
    """

    def test_iam_policies_exclude_write_actions(self):
        """IAM policies must not grant es:ESHttpPost, es:ESHttpPut, or es:ESHttpDelete."""
        metrics_agent = MetricsAgent()
        policies = metrics_agent.get_iam_policies("123456789012", "us-east-1", "dev")
        forbidden_actions = {"es:ESHttpPost", "es:ESHttpPut", "es:ESHttpDelete"}
        for stmt in policies:
            stmt_json = stmt.to_json()
            actions = stmt_json.get("Action", [])
            if isinstance(actions, str):
                actions = [actions]
            overlap = forbidden_actions & set(actions)
            assert not overlap, (
                f"Metrics IAM policy grants forbidden actions: {overlap}. "
                f"This agent must be read-only — no POST/PUT/DELETE on OpenSearch."
            )

    def test_iam_policies_exclude_wildcard_es_actions(self):
        """IAM policies must not grant es:* (blanket OpenSearch access)."""
        metrics_agent = MetricsAgent()
        policies = metrics_agent.get_iam_policies("123456789012", "us-east-1", "dev")
        for stmt in policies:
            stmt_json = stmt.to_json()
            actions = stmt_json.get("Action", [])
            if isinstance(actions, str):
                actions = [actions]
            assert "es:*" not in actions, (
                "Metrics IAM policy must not grant wildcard es:* access"
            )

    def test_no_post_calls_in_metrics_lambda(self):
        """No code in the metrics Lambda may invoke _make_request or opensearch_request with POST."""
        lambda_dir = os.path.join("agents", "metrics", "lambda")
        violations = []

        for py_file in glob.glob(os.path.join(lambda_dir, "*.py")):
            with open(py_file) as f:
                source = f.read()
            try:
                tree = ast.parse(source, filename=py_file)
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = None
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                if name not in ("opensearch_request", "_make_request"):
                    continue
                # First positional arg is the HTTP method
                if node.args:
                    method_arg = node.args[0]
                    if isinstance(method_arg, ast.Constant) and method_arg.value == "POST":
                        violations.append(
                            f"{os.path.basename(py_file)}:{node.lineno} "
                            f"{name}('POST', ...) — POST is forbidden"
                        )

        assert not violations, (
            "Metrics Lambda makes POST calls to OpenSearch:\n" +
            "\n".join(violations)
        )

    def test_no_direct_post_put_delete_requests_in_metrics_lambda(self):
        """Metrics Lambda must not call requests.post(), requests.put(), or requests.delete()."""
        lambda_dir = os.path.join("agents", "metrics", "lambda")
        forbidden = {"post", "put", "delete"}
        violations = []

        for py_file in glob.glob(os.path.join(lambda_dir, "*.py")):
            with open(py_file) as f:
                source = f.read()
            try:
                tree = ast.parse(source, filename=py_file)
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if (isinstance(func, ast.Attribute) and
                        func.attr in forbidden and
                        isinstance(func.value, ast.Name) and
                        func.value.id == "requests"):
                    violations.append(
                        f"{os.path.basename(py_file)}:{node.lineno} "
                        f"calls requests.{func.attr}()"
                    )

        assert not violations, (
            "Metrics Lambda makes forbidden HTTP calls:\n" +
            "\n".join(violations)
        )

    def test_make_request_only_called_with_get(self):
        """_make_request() and opensearch_request() must only be invoked with GET."""
        lambda_dir = os.path.join("agents", "metrics", "lambda")
        violations = []

        for py_file in glob.glob(os.path.join(lambda_dir, "*.py")):
            with open(py_file) as f:
                source = f.read()
            try:
                tree = ast.parse(source, filename=py_file)
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = None
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                if name not in ("_make_request", "opensearch_request"):
                    continue
                if node.args:
                    method_arg = node.args[0]
                    if isinstance(method_arg, ast.Constant) and method_arg.value != "GET":
                        violations.append(
                            f"{os.path.basename(py_file)}:{node.lineno} "
                            f"{name}('{method_arg.value}', ...) — only GET allowed"
                        )

        assert not violations, (
            "Metrics Lambda uses non-GET HTTP methods:\n" +
            "\n".join(violations)
        )


# ---------------------------------------------------------------------------
# Bedrock guardrail tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def agents_template():
    """Synthesise the Bedrock agents stack with its own App."""
    os.environ["CDK_DEFAULT_ACCOUNT"] = "123456789012"
    os.environ["CDK_DEFAULT_REGION"] = "us-east-1"

    app = App(context={"aws:cdk:bundling-stacks": []})

    permissions = OscarPermissionsStack(
        app, "AgentsPerms", environment="dev", agents=ALL_AGENTS, env=ENV,
    )
    secrets = OscarSecretsStack(
        app, "AgentsSecrets", environment="dev", agents=ALL_AGENTS, env=ENV,
    )
    storage = OscarStorageStack(app, "AgentsStorage", environment="dev", env=ENV)
    vpc = OscarVpcStack(app, "AgentsVpc", env=ENV)

    lambda_stack = OscarLambdaStack(
        app, "AgentsLambda",
        permissions_stack=permissions,
        secrets_stack=secrets,
        storage_stack=storage,
        vpc_stack=vpc,
        environment="dev",
        agents=ALL_AGENTS,
        env=ENV,
    )

    agents_stack = OscarAgentsStack(
        app, "Agents",
        permissions_stack=permissions,
        lambda_stack=lambda_stack,
        environment="dev",
        agents=ALL_AGENTS,
        env=ENV,
    )
    return Template.from_stack(agents_stack)


class TestGuardrail:
    """Verify guardrail is created and attached only to supervisor agents."""

    def test_guardrail_created(self, agents_template):
        agents_template.resource_count_is("AWS::Bedrock::Guardrail", 1)

    def test_guardrail_has_content_policy(self, agents_template):
        agents_template.has_resource_properties("AWS::Bedrock::Guardrail", {
            "ContentPolicyConfig": {"FiltersConfig": Match.any_value()},
        })

    def test_guardrail_has_topic_policy(self, agents_template):
        agents_template.has_resource_properties("AWS::Bedrock::Guardrail", {
            "TopicPolicyConfig": {
                "TopicsConfig": Match.array_with([
                    Match.object_like({"Name": "CredentialExfiltration", "Type": "DENY"}),
                ]),
            },
        })

    def test_guardrail_blocks_aws_keys(self, agents_template):
        agents_template.has_resource_properties("AWS::Bedrock::Guardrail", {
            "SensitiveInformationPolicyConfig": {
                "PiiEntitiesConfig": Match.array_with([
                    Match.object_like({"Type": "AWS_ACCESS_KEY", "Action": "BLOCK"}),
                    Match.object_like({"Type": "AWS_SECRET_KEY", "Action": "BLOCK"}),
                ]),
            },
        })

    def test_privileged_agent_has_guardrail(self, agents_template):
        agents_template.has_resource_properties("AWS::Bedrock::Agent", {
            "AgentName": "oscar-privileged-agent-dev",
            "GuardrailConfiguration": {
                "GuardrailIdentifier": Match.any_value(),
                "GuardrailVersion": Match.any_value(),
            },
        })

    def test_limited_agent_has_guardrail(self, agents_template):
        agents_template.has_resource_properties("AWS::Bedrock::Agent", {
            "AgentName": "oscar-limited-agent-dev",
            "GuardrailConfiguration": {
                "GuardrailIdentifier": Match.any_value(),
                "GuardrailVersion": Match.any_value(),
            },
        })

    def test_collaborator_agents_no_guardrail(self, agents_template):
        agents = agents_template.find_resources("AWS::Bedrock::Agent")
        for logical_id, resource in agents.items():
            name = resource["Properties"].get("AgentName", "")
            if "privileged" not in name and "limited" not in name:
                assert "GuardrailConfiguration" not in resource["Properties"], \
                    f"Collaborator agent '{name}' should not have a guardrail"
