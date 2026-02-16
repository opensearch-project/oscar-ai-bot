# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Jenkins plugin for OSCAR."""

from plugins.base_plugin import LambdaConfig, OscarPlugin
from plugins.jenkins.action_groups import get_action_groups
from plugins.jenkins.iam_policies import get_policies
from plugins.jenkins.instructions import (AGENT_INSTRUCTION,
                                          COLLABORATOR_INSTRUCTION)


class JenkinsPlugin(OscarPlugin):

    @property
    def name(self):
        return "jenkins"

    def get_lambda_config(self):
        return LambdaConfig(
            entry="plugins/jenkins/lambda",
            timeout_seconds=120,
            memory_size=512,
            reserved_concurrency=5,
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
        return "Jenkins-Specialist"

    def get_access_level(self):
        return "privileged"
