# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""IAM policies for security advisories agent."""

import os
from typing import List

from aws_cdk import aws_iam as iam


def get_policies(account_id: str, region: str, env: str) -> List[iam.PolicyStatement]:
    policies = [
        iam.PolicyStatement(
            sid="SecurityAdvisoriesSecretsAccess",
            effect=iam.Effect.ALLOW,
            actions=["secretsmanager:GetSecretValue"],
            resources=[
                f"arn:aws:secretsmanager:{region}:{account_id}:secret:oscar-security-advisories-*-{env}*",
                # GitHub token for the remediation pre-flight (read-side API calls).
                f"arn:aws:secretsmanager:{region}:{account_id}:secret:oscar-remediation-gh-token-{env}*",
            ],
        ),
        iam.PolicyStatement(
            sid="SecurityAdvisoriesLogsAccess",
            effect=iam.Effect.ALLOW,
            actions=[
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents",
            ],
            resources=[
                f"arn:aws:logs:{region}:{account_id}:log-group:/aws/lambda/oscar-security-advisories-*"
            ],
        ),
        # Deterministic string ARNs (not the CDK construct ARNs) so this identity
        # policy — in the permissions stack — does not create a cyclic dependency
        # on the lambda stack where the task definition lives.
        iam.PolicyStatement(
            sid="SecurityAdvisoriesRemediationRunTask",
            effect=iam.Effect.ALLOW,
            actions=["ecs:RunTask"],
            # Family ARN with :* covers every task-definition revision.
            resources=[
                f"arn:aws:ecs:{region}:{account_id}:task-definition/oscar-remediation-npm-{env}:*"
            ],
        ),
        # RunTask hands the task + execution roles to the ECS tasks service; the
        # caller needs PassRole for them. Scope by the target service rather than
        # role ARNs (the ECS role names are CDK-generated, not deterministic).
        iam.PolicyStatement(
            sid="SecurityAdvisoriesRemediationPassRole",
            effect=iam.Effect.ALLOW,
            actions=["iam:PassRole"],
            resources=["*"],
            conditions={
                "StringEquals": {"iam:PassedToService": "ecs-tasks.amazonaws.com"}
            },
        ),
    ]

    cross_account_role = os.environ.get("SECURITY_ADVISORIES_CROSS_ACCOUNT_ROLE_ARN")
    if cross_account_role:
        policies.append(
            iam.PolicyStatement(
                sid="CrossAccountOpenSearchAssumeRole",
                effect=iam.Effect.ALLOW,
                actions=["sts:AssumeRole"],
                resources=[cross_account_role],
            )
        )

    return policies
