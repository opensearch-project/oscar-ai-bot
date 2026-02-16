# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""IAM policies for Jenkins plugin."""

from typing import List

from aws_cdk import aws_iam as iam


def get_policies(account_id: str, region: str, env: str) -> List[iam.PolicyStatement]:
    return [
        iam.PolicyStatement(
            sid="JenkinsSecretsAccess",
            effect=iam.Effect.ALLOW,
            actions=["secretsmanager:GetSecretValue"],
            resources=[
                f"arn:aws:secretsmanager:{region}:{account_id}:secret:oscar-central-env-{env}*"
            ],
        ),
        iam.PolicyStatement(
            sid="JenkinsLogsAccess",
            effect=iam.Effect.ALLOW,
            actions=[
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents",
            ],
            resources=[
                f"arn:aws:logs:{region}:{account_id}:log-group:/aws/lambda/oscar-jenkins-*"
            ],
        ),
    ]
