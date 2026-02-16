# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Shared IAM policies for all metrics plugins."""

from typing import List, Optional

from aws_cdk import aws_iam as iam


def get_policies(account_id: str, region: str, env: str, metrics_account_role: Optional[str] = None) -> List[iam.PolicyStatement]:
    policies = [
        iam.PolicyStatement(
            sid="MetricsSecretsAccess",
            effect=iam.Effect.ALLOW,
            actions=["secretsmanager:GetSecretValue"],
            resources=[
                f"arn:aws:secretsmanager:{region}:{account_id}:secret:oscar-central-env-{env}*"
            ],
        ),
        iam.PolicyStatement(
            sid="VPCEndpointAccess",
            effect=iam.Effect.ALLOW,
            actions=["s3:GetObject", "s3:PutObject"],
            resources=[f"arn:aws:s3:::oscar-metrics-cache-{account_id}/*"],
        ),
    ]
    if metrics_account_role:
        policies.append(
            iam.PolicyStatement(
                sid="CrossAccountOpenSearchAssumeRole",
                effect=iam.Effect.ALLOW,
                actions=["sts:AssumeRole"],
                resources=[metrics_account_role],
            )
        )
    return policies
