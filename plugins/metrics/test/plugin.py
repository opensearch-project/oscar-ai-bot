# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Test metrics plugin for OSCAR."""

from plugins.base_plugin import LambdaConfig, OscarPlugin
from plugins.metrics.iam_policies import get_policies
from plugins.metrics.test.action_groups import get_action_groups
from plugins.metrics.test.instructions import (AGENT_INSTRUCTION,
                                               COLLABORATOR_INSTRUCTION)


class MetricsTestPlugin(OscarPlugin):

    @property
    def name(self):
        return "metrics-test"

    def get_lambda_config(self):
        return LambdaConfig(
            entry="plugins/metrics/lambda",
            timeout_seconds=180,
            memory_size=1024,
            reserved_concurrency=100,
            needs_vpc=True,
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
        return "Test-Metrics-Specialist"

    def get_access_level(self):
        return "both"

    def uses_knowledge_base(self):
        return False

    def get_managed_policies(self):
        return [
            "service-role/AWSLambdaBasicExecutionRole",
            "service-role/AWSLambdaVPCAccessExecutionRole",
        ]
