# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""GitHub agent for OSCAR."""

import os

from agents.base_agent import (LambdaConfig, MonitoringConfig, OscarAgent,
                               SecretConfig)
from agents.github.action_groups import get_action_groups
from agents.github.iam_policies import get_policies
from agents.github.instructions import (AGENT_INSTRUCTION,
                                        COLLABORATOR_INSTRUCTION)

GITHUB_ORG = os.environ.get("GITHUB_ORG", "opensearch-project")


class GitHubAgent(OscarAgent):

    @property
    def name(self):
        return "github"

    def get_lambda_config(self):
        return LambdaConfig(
            entry="agents/github/lambda",
            timeout_seconds=180,
            memory_size=1024,
            reserved_concurrency=2,
            environment_variables={
                "MCP_TOOLSETS": "issues,pull_requests",
                "MCP_READ_ONLY": "false",
                "GITHUB_ORG": GITHUB_ORG,
                "ENABLE_2PR": os.environ.get("ENABLE_2PR", "false"),
            },
        )

    def get_iam_policies(self, account_id, region, env):
        return get_policies(account_id, region, env)

    def get_action_groups(self, lambda_arn):
        return get_action_groups(lambda_arn)

    def get_agent_instruction(self):
        return AGENT_INSTRUCTION.format(org=GITHUB_ORG)

    def get_collaborator_instruction(self):
        return COLLABORATOR_INSTRUCTION.format(org=GITHUB_ORG)

    def get_collaborator_name(self):
        return "GitHub-Specialist"

    def get_access_level(self):
        return "privileged"

    def get_secrets(self):
        return [
            SecretConfig(
                name_suffix="env",
                description="GitHub App credentials (App ID, private key, installation ID)",
                env_var="GITHUB_SECRET_NAME",
            ),
        ]

    def uses_knowledge_base(self):
        return False

    def get_monitoring_config(self):
        return [
            MonitoringConfig(
                pattern="GITHUB_FORCE_MERGE",
                alarm_threshold=3,
                description="Force-merges bypassing guardrails",
            ),
            MonitoringConfig(
                pattern="BULK_MERGE_SUCCESS",
                alarm_threshold=75,
                description="Bulk merge volume exceeds threshold (runaway operation)",
            ),
        ]
