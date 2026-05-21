# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""CDK-level tests for SecurityAdvisoriesAgent."""

import pytest

from agents.base_agent import LambdaConfig, MonitoringConfig, OscarAgent
from agents.security_advisories import SecurityAdvisoriesAgent


@pytest.fixture
def agent():
    return SecurityAdvisoriesAgent()


class TestSecurityAdvisoriesAgentInterface:
    """SecurityAdvisoriesAgent must satisfy the OscarAgent interface."""

    def test_is_oscar_agent_subclass(self, agent):
        assert isinstance(agent, OscarAgent)

    def test_name(self, agent):
        assert agent.name == "security-advisories"

    def test_get_lambda_config_returns_lambda_config(self, agent):
        config = agent.get_lambda_config()
        assert isinstance(config, LambdaConfig)

    def test_get_access_level_returns_privileged(self, agent):
        assert agent.get_access_level() == "privileged"

    def test_uses_knowledge_base_returns_false(self, agent):
        assert agent.uses_knowledge_base() is False


class TestActionGroups:
    """Action group defines query_vulnerabilities and list_projects."""

    def test_action_group_returns_list(self, agent):
        groups = agent.get_action_groups("arn:aws:lambda:us-east-1:123456789012:function:placeholder")
        assert isinstance(groups, list)
        assert len(groups) == 1

    def test_action_group_has_query_vulnerabilities(self, agent):
        groups = agent.get_action_groups("arn:aws:lambda:us-east-1:123456789012:function:placeholder")
        group = groups[0]
        functions = group.function_schema.functions
        func_names = [f.name for f in functions]
        assert "query_vulnerabilities" in func_names

    def test_action_group_has_list_projects(self, agent):
        groups = agent.get_action_groups("arn:aws:lambda:us-east-1:123456789012:function:placeholder")
        group = groups[0]
        functions = group.function_schema.functions
        func_names = [f.name for f in functions]
        assert "list_projects" in func_names

    def test_query_vulnerabilities_has_required_query_param(self, agent):
        groups = agent.get_action_groups("arn:aws:lambda:us-east-1:123456789012:function:placeholder")
        group = groups[0]
        functions = group.function_schema.functions
        qv_func = next(f for f in functions if f.name == "query_vulnerabilities")
        assert "query" in qv_func.parameters
        assert qv_func.parameters["query"].required is True

    def test_query_vulnerabilities_has_optional_version_param(self, agent):
        groups = agent.get_action_groups("arn:aws:lambda:us-east-1:123456789012:function:placeholder")
        group = groups[0]
        functions = group.function_schema.functions
        qv_func = next(f for f in functions if f.name == "query_vulnerabilities")
        assert "version" in qv_func.parameters
        assert qv_func.parameters["version"].required is False

    def test_query_vulnerabilities_has_optional_project_name_param(self, agent):
        groups = agent.get_action_groups("arn:aws:lambda:us-east-1:123456789012:function:placeholder")
        group = groups[0]
        functions = group.function_schema.functions
        qv_func = next(f for f in functions if f.name == "query_vulnerabilities")
        assert "project_name" in qv_func.parameters
        assert qv_func.parameters["project_name"].required is False

    def test_list_projects_has_no_parameters(self, agent):
        groups = agent.get_action_groups("arn:aws:lambda:us-east-1:123456789012:function:placeholder")
        group = groups[0]
        functions = group.function_schema.functions
        lp_func = next(f for f in functions if f.name == "list_projects")
        assert lp_func.parameters == {}

    def test_no_get_vulnerabilities_function(self, agent):
        """Old get_vulnerabilities function should be replaced."""
        groups = agent.get_action_groups("arn:aws:lambda:us-east-1:123456789012:function:placeholder")
        group = groups[0]
        functions = group.function_schema.functions
        func_names = [f.name for f in functions]
        assert "get_vulnerabilities" not in func_names


class TestInstructions:
    """Agent and collaborator instructions contain required content."""

    def test_agent_instruction_contains_agentic(self, agent):
        instruction = agent.get_agent_instruction()
        assert "agentic" in instruction.lower()

    def test_agent_instruction_contains_query_vulnerabilities(self, agent):
        instruction = agent.get_agent_instruction()
        assert "query_vulnerabilities" in instruction

    def test_agent_instruction_contains_list_projects(self, agent):
        instruction = agent.get_agent_instruction()
        assert "list_projects" in instruction

    def test_agent_instruction_no_manual_dsl_references(self, agent):
        """Instructions should not reference old manual DSL filter params."""
        instruction = agent.get_agent_instruction()
        assert "get_vulnerabilities" not in instruction

    def test_collaborator_instruction_describes_security_capabilities(self, agent):
        instruction = agent.get_collaborator_instruction()
        assert "security" in instruction.lower()
        assert "vulnerabilit" in instruction.lower()

    def test_collaborator_instruction_non_empty(self, agent):
        instruction = agent.get_collaborator_instruction()
        assert isinstance(instruction, str)
        assert len(instruction) > 0


@pytest.mark.skip(reason="Monitoring config temporarily disabled until log group exists")
class TestMonitoringConfig:
    """Monitoring config includes all three log markers."""

    def test_monitoring_config_returns_list(self, agent):
        configs = agent.get_monitoring_config()
        assert isinstance(configs, list)
        assert len(configs) == 3

    def test_monitoring_config_has_agentic_search_failed(self, agent):
        configs = agent.get_monitoring_config()
        patterns = [c.pattern for c in configs]
        assert "SECURITY_ADVISORIES_AGENTIC_SEARCH_FAILED" in patterns

    def test_monitoring_config_has_opensearch_connection_failed(self, agent):
        configs = agent.get_monitoring_config()
        patterns = [c.pattern for c in configs]
        assert "SECURITY_ADVISORIES_OPENSEARCH_CONNECTION_FAILED" in patterns

    def test_monitoring_config_has_cross_account_role_failed(self, agent):
        configs = agent.get_monitoring_config()
        patterns = [c.pattern for c in configs]
        assert "SECURITY_ADVISORIES_CROSS_ACCOUNT_ROLE_FAILED" in patterns

    def test_monitoring_configs_are_monitoring_config_instances(self, agent):
        configs = agent.get_monitoring_config()
        for config in configs:
            assert isinstance(config, MonitoringConfig)
