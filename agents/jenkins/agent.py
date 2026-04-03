# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Jenkins agent for OSCAR."""

import os

from agents.base_agent import LambdaConfig, OscarAgent, SecretConfig
from agents.jenkins.action_groups import get_action_groups
from agents.jenkins.iam_policies import get_policies
from agents.jenkins.instructions import (AGENT_INSTRUCTION,
                                         COLLABORATOR_INSTRUCTION)


class JenkinsAgent(OscarAgent):

    @property
    def name(self):
        return "jenkins"

    def get_lambda_config(self):
        return LambdaConfig(
            entry="agents/jenkins/lambda",
            timeout_seconds=120,
            memory_size=512,
            reserved_concurrency=5,
            environment_variables={
                "JENKINS_URL": os.environ.get("JENKINS_URL", "https://build.ci.opensearch.org"),
                "JENKINS_VERIFY_SSL": os.environ.get("JENKINS_VERIFY_SSL", "true"),
                "JENKINSFILE_GITHUB_REPO": os.environ.get("JENKINSFILE_GITHUB_REPO", "opensearch-project/opensearch-build"),
                "JENKINSFILE_GITHUB_BRANCH": os.environ.get("JENKINSFILE_GITHUB_BRANCH", "main"),
                "JENKINSFILE_IGNORE_LIST": os.environ.get("JENKINSFILE_IGNORE_LIST", ""),
            },
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

    def get_secrets(self):
        return [
            SecretConfig(
                name_suffix="api-token",
                description="Jenkins API token in username:token format",
                env_var="JENKINS_SECRET_NAME",
            ),
        ]

    def get_access_level(self):
        return "privileged"
