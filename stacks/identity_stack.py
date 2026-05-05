#!/usr/bin/env python
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""Identity storage stack — DynamoDB tables for Slack-GitHub mappings (one per workspace)."""

from typing import List, Optional

from aws_cdk import RemovalPolicy, Stack
from aws_cdk import aws_dynamodb as dynamodb
from constructs import Construct


class OscarIdentityStack(Stack):
    """DynamoDB tables for Slack-GitHub identity mappings. One table per workspace."""

    TABLE_PREFIX = "oscar-identity"

    def __init__(self, scope: Construct, construct_id: str, environment: str, workspace_ids: Optional[List[str]] = None, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = environment
        self.identity_tables = {}

        removal_policy = RemovalPolicy.RETAIN if environment == "prod" else RemovalPolicy.DESTROY

        for workspace_id in (workspace_ids or []):
            table_name = f"{self.TABLE_PREFIX}-{workspace_id}-{environment}"
            table = dynamodb.Table(
                self, f"IdentityTable{workspace_id}",
                table_name=table_name,
                partition_key=dynamodb.Attribute(name="github_id", type=dynamodb.AttributeType.NUMBER),
                billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
                removal_policy=removal_policy,
                point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                    point_in_time_recovery_enabled=True
                ),
            )

            table.add_global_secondary_index(
                index_name="slack-user-index",
                partition_key=dynamodb.Attribute(name="slack_user_id", type=dynamodb.AttributeType.STRING),
            )

            self.identity_tables[workspace_id] = table
