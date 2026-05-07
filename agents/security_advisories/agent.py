# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Security advisories agent for OSCAR."""

import os

from agents.base_agent import (LambdaConfig, MonitoringConfig, OscarAgent,
                               SecretConfig)
from agents.security_advisories.action_groups import get_action_groups
from agents.security_advisories.iam_policies import get_policies
from agents.security_advisories.instructions import (AGENT_INSTRUCTION,
                                                     COLLABORATOR_INSTRUCTION)

_ENV_KEYS = [
    "OPENSEARCH_REGION",
    "OPENSEARCH_SERVICE",
    "OPENSEARCH_REQUEST_TIMEOUT",
    "SCANS_INDEX",
    "ADVISORIES_INDEX",
    "AGENTIC_PIPELINE",
    "SECURITY_ADVISORIES_CROSS_ACCOUNT_ROLE_ARN",
]


def _passthrough_env(keys):
    """Pass through env vars to Lambda — only if set."""
    return {k: os.environ[k] for k in keys if k in os.environ}


class SecurityAdvisoriesAgent(OscarAgent):

    @property
    def name(self):
        return "security-advisories"

    def get_lambda_config(self):
        return LambdaConfig(
            entry="agents/security_advisories/lambda",
            timeout_seconds=180,
            memory_size=1024,
            reserved_concurrency=10,
            needs_vpc=False,
            environment_variables=_passthrough_env(_ENV_KEYS),
        )

    def get_iam_policies(self, account_id, region, env):
        return get_policies(account_id, region, env)

    def get_action_groups(self, lambda_arn):
        return get_action_groups(lambda_arn)

    def get_agent_instruction(self):
        return AGENT_INSTRUCTION

    def get_collaborator_instruction(self):
        return COLLABORATOR_INSTRUCTION

    def get_collaborator_name(self):
        return "Security-Advisories-Specialist"

    def get_access_level(self):
        return "privileged"

    def uses_knowledge_base(self):
        return False

    def get_secrets(self):
        return [
            SecretConfig(
                name_suffix="env",
                description="Security advisories agent secrets (OpenSearch host, etc.)",
                env_var="SECURITY_ADVISORIES_SECRET_NAME",
            ),
        ]

    def get_managed_policies(self):
        return [
            "service-role/AWSLambdaBasicExecutionRole",
        ]

    def get_monitoring_config(self):
        return [
            MonitoringConfig(
                pattern="SECURITY_ADVISORIES_AGENTIC_SEARCH_FAILED",
                alarm_threshold=5,
                description="OpenSearch agentic query failures",
            ),
            MonitoringConfig(
                pattern="SECURITY_ADVISORIES_OPENSEARCH_CONNECTION_FAILED",
                alarm_threshold=2,
                description="OpenSearch connectivity issues",
            ),
            MonitoringConfig(
                pattern="SECURITY_ADVISORIES_CROSS_ACCOUNT_ROLE_FAILED",
                alarm_threshold=1,
                description="Cross-account role assumption failure",
            ),
        ]
