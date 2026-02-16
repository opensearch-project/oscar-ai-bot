#!/usr/bin/env python
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Secrets management stack for OSCAR Slack Bot.

Creates the central environment secret that contains all OSCAR configuration.
"""


from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_secretsmanager as secretsmanager
from constructs import Construct


class OscarSecretsStack(Stack):
    """
    Creates the central environment secret for OSCAR configuration.
    All OSCAR components read their configuration from this single secret,
    including Slack tokens, Bedrock agent IDs, and Jenkins credentials.
    """

    CENTRAL_ENV_SECRET_NAME = "oscar-central-env"
    METRICS_ACCOUNT_ROLE_SECRET_NAME = "metrics-account-role"

    @classmethod
    def get_central_env_secret_name(cls, environment: str) -> str:
        return f"{cls.CENTRAL_ENV_SECRET_NAME}-{environment}"

    def __init__(self, scope: Construct, construct_id: str, environment: str, **kwargs) -> None:
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

        # Output for other stacks
        CfnOutput(
            self, "CentralEnvSecretArn",
            value=self.central_env_secret.secret_arn,
            export_name="OscarCentralEnvSecretArn"
        )

    def grant_read_access(self, grantee: iam.IGrantable) -> iam.Grant:
        """Grant read access to the central environment secret."""
        return self.central_env_secret.grant_read(grantee)
