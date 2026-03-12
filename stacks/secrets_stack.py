#!/usr/bin/env python
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Secrets management stack for OSCAR Slack Bot.

Creates the central environment secret that contains all OSCAR configuration.
"""


from typing import Any, Dict, List, Optional

from aws_cdk import RemovalPolicy, Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_secretsmanager as secretsmanager
from constructs import Construct


class OscarSecretsStack(Stack):
    """
    Creates the central environment secret for OSCAR configuration
    and any plugin-declared secrets.
    """

    CENTRAL_ENV_SECRET_NAME = "oscar-central-env"
    METRICS_ACCOUNT_ROLE_SECRET_NAME = "metrics-account-role"

    @classmethod
    def get_central_env_secret_name(cls, environment: str) -> str:
        return f"{cls.CENTRAL_ENV_SECRET_NAME}-{environment}"

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        environment: str,
        plugins: Optional[List[Any]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        removal_policy = RemovalPolicy.RETAIN if environment == "prod" else RemovalPolicy.DESTROY

        # Create central environment secret
        self.central_env_secret = secretsmanager.Secret(
            self, "CentralEnvSecret",
            secret_name=self.get_central_env_secret_name(environment),
            description="Central environment variables for OSCAR (includes all tokens and config)",
            removal_policy=removal_policy,
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"PLACEHOLDER": "Run migration script to populate"}',
                generate_string_key="INITIAL_VALUE",
                password_length=32
            )
        )

        # Create plugin-declared secrets
        # Maps "plugin_name/secret_suffix" -> secretsmanager.Secret
        self.plugin_secrets: Dict[str, secretsmanager.Secret] = {}
        if plugins:
            self._create_plugin_secrets(plugins, environment, removal_policy)

    def _create_plugin_secrets(
        self,
        plugins: List[Any],
        environment: str,
        removal_policy: RemovalPolicy,
    ) -> None:
        """Create secrets declared by plugins via get_secrets()."""
        for plugin in plugins:
            for secret_config in plugin.get_secrets():
                secret_name = f"oscar-{plugin.name}-{secret_config.name_suffix}-{environment}"
                construct_name = plugin.name.replace("-", " ").title().replace(" ", "")
                suffix_name = secret_config.name_suffix.replace("-", " ").title().replace(" ", "")
                construct_id = f"{construct_name}{suffix_name}Secret"

                secret = secretsmanager.Secret(
                    self, construct_id,
                    secret_name=secret_name,
                    description=secret_config.description,
                    removal_policy=removal_policy,
                )

                key = f"{plugin.name}/{secret_config.name_suffix}"
                self.plugin_secrets[key] = secret

    def get_plugin_secret(self, plugin_name: str, name_suffix: str) -> Optional[secretsmanager.Secret]:
        """Get a plugin secret by plugin name and suffix."""
        return self.plugin_secrets.get(f"{plugin_name}/{name_suffix}")

    def grant_read_access(self, grantee: iam.IGrantable) -> iam.Grant:
        """Grant read access to the central environment secret."""
        return self.central_env_secret.grant_read(grantee)
