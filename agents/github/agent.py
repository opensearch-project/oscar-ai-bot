# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""GitHub agent for OSCAR."""

import os

from agents.base_agent import (LambdaConfig, MonitoringConfig,  # noqa: F401
                               OscarAgent, SecretConfig)
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
                "ALLOWED_MERGE_AUTHORS": os.environ.get("ALLOWED_MERGE_AUTHORS", "opensearch-ci-bot"),
            },
        )

    def get_iam_policies(self, account_id, region, env):
        return get_policies(account_id, region, env)

    def get_action_groups(self, lambda_arn):
        return get_action_groups(lambda_arn)

    def get_agent_instruction(self):
        enable_2pr = os.environ.get("ENABLE_2PR", "false").lower() == "true"
        if enable_2pr:
            two_person_review_section = (
                "TWO-PERSON REVIEW (MANDATORY FOR ALL WRITE OPERATIONS):\n"
                "- When you receive a write request, present a summary and include [CONFIRMATION_REQUIRED] "
                "at the end. State: \"This requires approval from a different authorized user. "
                "Please have another authorized user reply 'yes' to confirm.\"\n"
                "- You must ONLY emit [CONFIRMATION_REQUIRED] ONCE per action. After you have emitted it, "
                "do NOT emit it again in the same thread for the same action.\n"
                "- When ANY user replies 'yes' or 'confirm' after your [CONFIRMATION_REQUIRED] message, "
                "IMMEDIATELY call the tool. Do NOT re-summarize, re-confirm, or ask again. "
                "A different user saying 'yes' IS the approval — call the tool right away.\n"
                "- Do NOT verify or judge authorization yourself. Authorization is enforced entirely "
                "server-side. Your only job is to call the tool and relay what it returns.\n"
                "- If the tool returns an error, relay it verbatim. Do NOT re-ask for confirmation."
            )
        else:
            two_person_review_section = (
                "CONFIRMATION (MANDATORY FOR ALL WRITE OPERATIONS):\n"
                "- When you receive a write request, ask for confirmation and include [CONFIRMATION_REQUIRED].\n"
                "- The same user who requested the action can confirm it.\n"
                "- Do NOT mention two-person review or ask for a different user to approve."
            )
        return AGENT_INSTRUCTION.format(
            org=GITHUB_ORG,
            two_person_review_section=two_person_review_section,
        )

    def get_collaborator_instruction(self):
        return COLLABORATOR_INSTRUCTION.format(org=GITHUB_ORG)

    def get_collaborator_name(self):
        return "GitHub-Specialist"

    def get_access_level(self):
        return "both"

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
        # TODO: Re-enable after log groups are explicitly created in the Lambda stack.
        # return [
        #     MonitoringConfig(
        #         pattern="GITHUB_FORCE_MERGE",
        #         alarm_threshold=3,
        #         description="Force-merges bypassing guardrails",
        #     ),
        #     MonitoringConfig(
        #         pattern="BULK_MERGE_SUCCESS",
        #         alarm_threshold=75,
        #         description="Bulk merge volume exceeds threshold (runaway operation)",
        #     ),
        # ]
        return []
