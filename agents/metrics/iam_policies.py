# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Shared IAM policies for all metrics agents."""

import os
from typing import List

from aws_cdk import aws_iam as iam


def get_policies(account_id: str, region: str, env: str) -> List[iam.PolicyStatement]:
    policies = [
        iam.PolicyStatement(
            sid="VPCEndpointAccess",
            effect=iam.Effect.ALLOW,
            actions=["s3:GetObject", "s3:PutObject"],
            resources=[f"arn:aws:s3:::oscar-metrics-cache-{account_id}/*"],
        ),
    ]
    metrics_account_role = os.environ.get("METRICS_CROSS_ACCOUNT_ROLE_ARN")
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
