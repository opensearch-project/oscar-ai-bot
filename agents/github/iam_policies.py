# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""IAM policy definitions for the GitHub agent."""

from typing import List

from aws_cdk import aws_iam as iam


def get_policies(account_id: str, region: str, env: str) -> List[iam.PolicyStatement]:
    """IAM policies for the GitHub agent Lambda."""
    secret_name = f"oscar-github-env-{env}"
    return [
        # Read GitHub App credentials from Secrets Manager
        iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "secretsmanager:GetSecretValue",
            ],
            resources=[
                f"arn:aws:secretsmanager:{region}:{account_id}:secret:{secret_name}*",
            ],
        ),
        # CloudWatch logging
        iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents",
            ],
            resources=[
                f"arn:aws:logs:{region}:{account_id}:log-group:/aws/lambda/oscar-github-*",
            ],
        ),
    ]
