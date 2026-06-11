#!/usr/bin/env python
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.
"""
Storage stack for OSCAR Slack Bot.

This module defines the DynamoDB tables used by the OSCAR Slack Bot.
"""

import os
from typing import Dict, List, Optional, cast

from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_cloudwatch as cloudwatch
from aws_cdk import aws_cloudwatch_actions as cw_actions
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_sns as sns
from constructs import Construct


class OscarStorageStack(Stack):
    """
    Storage resources for OSCAR Slack Bot.
    This construct creates and configures the DynamoDB tables used by the
    OSCAR Slack Bot for storing session data and conversation context.
    Includes production-ready configurations with monitoring and alerting.
    """

    CONTEXT_TABLE_NAME = "oscar-agent-context"
    IDENTITY_TABLE_PREFIX = "oscar-identity"

    @classmethod
    def get_dynamodb_table_name(cls, environment: str) -> str:
        return f"{cls.CONTEXT_TABLE_NAME}-{environment}"

    def __init__(self, scope: Construct, construct_id: str, environment: str, workspace_ids: Optional[List[str]] = None, **kwargs) -> None:
        """
        Initialize storage resources.
        Args:
            scope: The CDK construct scope
            construct_id: The ID of the construct
            environment: Deployment environment name
            workspace_ids: Slack workspace IDs for identity tables
            **kwargs: Additional keyword arguments
        """
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = environment
        self.context_table_name: str = self.get_dynamodb_table_name(environment)

        # Get TTL values from environment
        context_ttl: int = int(os.environ.get("CONTEXT_TTL", "604800"))  # 7 days default

        # Determine removal policy based on environment
        removal_policy: RemovalPolicy = (
            RemovalPolicy.RETAIN if environment == "prod" else RemovalPolicy.DESTROY
        )

        # Create only the context table (the only one actually used by the application)
        self.context_table = self._create_context_table(
            self.context_table_name,
            removal_policy,
            context_ttl
        )

        # Import existing identity tables by default; only create new ones when CREATE_IDENTITY_TABLES=true is explicitly set.
        create_tables = os.environ.get("CREATE_IDENTITY_TABLES", "false").lower() == "true"
        self.identity_tables: Dict[str, dynamodb.Table] = {}
        for workspace_id in (workspace_ids or []):
            table_name = f"{self.IDENTITY_TABLE_PREFIX}-{workspace_id}-{self.env_name}"
            if create_tables:
                table = self._create_identity_table(workspace_id, removal_policy)
            else:
                table = cast(dynamodb.Table, dynamodb.Table.from_table_attributes(
                    self, f"IdentityTable{workspace_id}",
                    table_name=table_name,
                    grant_index_permissions=True,
                ))
            self.identity_tables[workspace_id] = table

        # Create monitoring and alerting for context table only
        self._create_context_monitoring(environment)

    def _create_context_table(
        self,
        table_name: str,
        removal_policy: RemovalPolicy,
        ttl_seconds: int
    ) -> dynamodb.Table:
        """
        Create the context DynamoDB table with production configurations.
        Args:
            table_name: Name of the DynamoDB table
            removal_policy: CDK removal policy for the table
            ttl_seconds: TTL value in seconds for automatic item expiration
        Returns:
            The created DynamoDB table
        """
        return dynamodb.Table(
            self, "OscarContextTable",
            table_name=table_name,
            partition_key=dynamodb.Attribute(
                name="thread_key",
                type=dynamodb.AttributeType.STRING
            ),
            time_to_live_attribute="ttl",
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=removal_policy,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True
            ),
            deletion_protection=removal_policy == RemovalPolicy.RETAIN,
            stream=dynamodb.StreamViewType.NEW_AND_OLD_IMAGES,
            contributor_insights_enabled=True
        )

    def _create_identity_table(self, workspace_id: str, removal_policy: RemovalPolicy) -> dynamodb.Table:
        """Create a DynamoDB table for Slack-GitHub identity mappings."""
        table_name = f"{self.IDENTITY_TABLE_PREFIX}-{workspace_id}-{self.env_name}"
        table = dynamodb.Table(
            self, f"IdentityTable{workspace_id}",
            table_name=table_name,
            partition_key=dynamodb.Attribute(name="github_id", type=dynamodb.AttributeType.NUMBER),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=removal_policy,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True
            ),
        )

        table.add_global_secondary_index(
            index_name="slack-user-index",
            partition_key=dynamodb.Attribute(name="slack_user_id", type=dynamodb.AttributeType.STRING),
        )

        return table

    def _create_context_monitoring(self, environment: str) -> None:
        """
        Create CloudWatch monitoring and alerting for the context table only.
        This method creates CloudWatch alarms for monitoring table usage,
        throttling, and error rates with appropriate thresholds.
        """
        # Create SNS topic for alerts (optional - can be configured later)
        self.alert_topic = sns.Topic(
            self, "OscarStorageAlerts",
            topic_name=f"oscar-storage-alerts-{environment}",
            display_name="OSCAR Storage Monitoring Alerts"
        )

        # Context table monitoring
        self._create_table_alarms(
            table=self.context_table,
            table_type="Context",
            alert_topic=self.alert_topic,
            environment=environment
        )

        # Identity table monitoring
        for workspace_id, table in self.identity_tables.items():
            self._create_table_alarms(
                table=table,
                table_type=f"Identity{workspace_id}",
                alert_topic=self.alert_topic,
                environment=environment
            )

    def _create_table_alarms(
        self,
        table: dynamodb.Table,
        table_type: str,
        alert_topic: sns.Topic,
        environment: str
    ) -> None:
        """
        Create CloudWatch alarms for a DynamoDB table.
        Args:
            table: The DynamoDB table to monitor
            table_type: Type identifier for the table (Sessions/Context)
            alert_topic: SNS topic for alert notifications
        """
        # High read throttle alarm
        read_throttle_alarm = cloudwatch.Alarm(
            self, f"Oscar{table_type}ReadThrottleAlarm",
            alarm_name=f"oscar-{table_type.lower()}-read-throttles-{environment}",
            alarm_description=f"High read throttles on {table_type} table",
            metric=table.metric_throttled_requests_for_operation(
                operation="GetItem",
                statistic=cloudwatch.Stats.SUM
            ),
            threshold=5,
            evaluation_periods=2,
            datapoints_to_alarm=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        read_throttle_alarm.add_alarm_action(cw_actions.SnsAction(alert_topic))

        # High write throttle alarm
        write_throttle_alarm = cloudwatch.Alarm(
            self, f"Oscar{table_type}WriteThrottleAlarm",
            alarm_name=f"oscar-{table_type.lower()}-write-throttles-{environment}",
            alarm_description=f"High write throttles on {table_type} table",
            metric=table.metric_throttled_requests_for_operation(
                operation="PutItem",
                statistic=cloudwatch.Stats.SUM
            ),
            threshold=5,
            evaluation_periods=2,
            datapoints_to_alarm=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        write_throttle_alarm.add_alarm_action(cw_actions.SnsAction(alert_topic))

        # High error rate alarm - using user errors metric instead
        error_alarm = cloudwatch.Alarm(
            self, f"Oscar{table_type}ErrorAlarm",
            alarm_name=f"oscar-{table_type.lower()}-errors-{environment}",
            alarm_description=f"High error rate on {table_type} table",
            metric=table.metric_user_errors(
                statistic=cloudwatch.Stats.SUM
            ),
            threshold=10,
            evaluation_periods=3,
            datapoints_to_alarm=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        error_alarm.add_alarm_action(cw_actions.SnsAction(alert_topic))

        # High consumed read capacity alarm (for monitoring usage patterns)
        read_capacity_alarm = cloudwatch.Alarm(
            self, f"Oscar{table_type}ReadCapacityAlarm",
            alarm_name=f"oscar-{table_type.lower()}-high-read-usage-{environment}",
            alarm_description=f"High read capacity usage on {table_type} table",
            metric=table.metric_consumed_read_capacity_units(
                statistic=cloudwatch.Stats.SUM,
                period=Duration.minutes(5)
            ),
            threshold=1000,  # Adjust based on expected usage
            evaluation_periods=3,
            datapoints_to_alarm=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        read_capacity_alarm.add_alarm_action(cw_actions.SnsAction(alert_topic))

        # High consumed write capacity alarm
        write_capacity_alarm = cloudwatch.Alarm(
            self, f"Oscar{table_type}WriteCapacityAlarm",
            alarm_name=f"oscar-{table_type.lower()}-high-write-usage-{environment}",
            alarm_description=f"High write capacity usage on {table_type} table",
            metric=table.metric_consumed_write_capacity_units(
                statistic=cloudwatch.Stats.SUM,
                period=Duration.minutes(5)
            ),
            threshold=500,  # Adjust based on expected usage
            evaluation_periods=3,
            datapoints_to_alarm=2,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )
        write_capacity_alarm.add_alarm_action(cw_actions.SnsAction(alert_topic))
