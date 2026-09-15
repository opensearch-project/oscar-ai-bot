# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for OSCAR storage stack."""

import pytest
from aws_cdk import App, Environment
from aws_cdk.assertions import Template

from stacks.storage_stack import OscarStorageStack


@pytest.fixture
def template():
    """Synthesise storage stack for dev environment."""
    app = App()
    stack = OscarStorageStack(
        app, "TestStorageStack",
        environment="dev",
        env=Environment(account="123456789012", region="us-east-1"),
    )
    return Template.from_stack(stack)


class TestStorageStack:
    """Test cases for OscarStorageStack."""

    def test_dynamodb_tables_created(self, template):
        """Context table plus the release notifier's state table."""
        template.resource_count_is("AWS::DynamoDB::Table", 2)

    def test_context_table_key_schema(self, template):
        """Context table uses thread_key as partition key."""
        template.has_resource_properties("AWS::DynamoDB::Table", {
            "KeySchema": [
                {"AttributeName": "thread_key", "KeyType": "HASH"},
            ],
            "AttributeDefinitions": [
                {"AttributeName": "thread_key", "AttributeType": "S"},
            ],
        })

    def test_context_table_billing_mode(self, template):
        """Context table uses PAY_PER_REQUEST billing."""
        template.has_resource_properties("AWS::DynamoDB::Table", {
            "BillingMode": "PAY_PER_REQUEST",
        })

    def test_context_table_ttl_enabled(self, template):
        """Context table has TTL on the 'ttl' attribute."""
        template.has_resource_properties("AWS::DynamoDB::Table", {
            "TimeToLiveSpecification": {
                "AttributeName": "ttl",
                "Enabled": True,
            },
        })

    def test_context_table_encryption(self, template):
        """Context table uses AWS managed encryption."""
        template.has_resource_properties("AWS::DynamoDB::Table", {
            "SSESpecification": {"SSEEnabled": True},
        })

    def test_context_table_point_in_time_recovery(self, template):
        """Context table has PITR enabled."""
        template.has_resource_properties("AWS::DynamoDB::Table", {
            "PointInTimeRecoverySpecification": {
                "PointInTimeRecoveryEnabled": True,
            },
        })

    def test_context_table_stream(self, template):
        """Context table has DynamoDB Streams with NEW_AND_OLD_IMAGES."""
        template.has_resource_properties("AWS::DynamoDB::Table", {
            "StreamSpecification": {
                "StreamViewType": "NEW_AND_OLD_IMAGES",
            },
        })

    def test_dev_table_not_deletion_protected(self, template):
        """Dev environment tables should NOT have deletion protection."""
        template.has_resource_properties("AWS::DynamoDB::Table", {
            "DeletionProtectionEnabled": False,
        })

    def test_prod_table_deletion_protected(self):
        """Prod environment tables should have deletion protection."""
        app = App()
        stack = OscarStorageStack(
            app, "ProdStorageStack",
            environment="prod",
            env=Environment(account="123456789012", region="us-east-1"),
        )
        prod_template = Template.from_stack(stack)
        prod_template.has_resource_properties("AWS::DynamoDB::Table", {
            "DeletionProtectionEnabled": True,
        })

    def test_cloudwatch_alarms_created(self, template):
        """Three alarms each for the context and release-notify tables."""
        template.resource_count_is("AWS::CloudWatch::Alarm", 10)

    def test_read_throttle_alarm(self, template):
        """Read throttle alarm exists with correct metric."""
        template.has_resource_properties("AWS::CloudWatch::Alarm", {
            "AlarmName": "oscar-context-read-throttles-dev",
        })

    def test_write_throttle_alarm(self, template):
        """Write throttle alarm exists with correct metric."""
        template.has_resource_properties("AWS::CloudWatch::Alarm", {
            "AlarmName": "oscar-context-write-throttles-dev",
        })

    def test_error_alarm(self, template):
        """Error alarm exists."""
        template.has_resource_properties("AWS::CloudWatch::Alarm", {
            "AlarmName": "oscar-context-errors-dev",
        })

    def test_sns_alert_topic_created(self, template):
        """SNS topic for storage alerts should exist."""
        template.resource_count_is("AWS::SNS::Topic", 1)
        template.has_resource_properties("AWS::SNS::Topic", {
            "TopicName": "oscar-storage-alerts-dev",
        })

    def test_table_name_includes_environment(self, template):
        """Table name should include the environment suffix."""
        template.has_resource_properties("AWS::DynamoDB::Table", {
            "TableName": "oscar-agent-context-dev",
        })


class TestReleaseNotifyStateTable:
    """The release notifier's per-version last-posted record."""

    def test_table_keyed_on_version(self, template):
        template.has_resource_properties("AWS::DynamoDB::Table", {
            "TableName": "oscar-release-notify-state-dev",
            "KeySchema": [{"AttributeName": "version", "KeyType": "HASH"}],
            "AttributeDefinitions": [{"AttributeName": "version", "AttributeType": "S"}],
            "BillingMode": "PAY_PER_REQUEST",
        })

    def test_table_is_monitored(self, template):
        """Throttling here silently drops duplicate suppression, so it must alarm."""
        for name in ("oscar-releasenotify-read-throttles-dev",
                     "oscar-releasenotify-write-throttles-dev",
                     "oscar-releasenotify-errors-dev"):
            template.has_resource_properties("AWS::CloudWatch::Alarm", {"AlarmName": name})

    def test_table_is_exposed_to_other_stacks(self):
        """The Lambda stack reads the table name off the stack to set an env var."""
        app = App()
        stack = OscarStorageStack(
            app, "TestStorageStack",
            environment="dev",
            env=Environment(account="123456789012", region="us-east-1"),
        )
        assert stack.release_notify_table is not None
        assert OscarStorageStack.get_release_notify_table_name("dev") == \
            "oscar-release-notify-state-dev"

    def test_created_without_a_workspace_id(self, template):
        """Unlike the identity table, this one does not depend on a Slack workspace."""
        tables = Template.from_stack(
            OscarStorageStack(
                App(), "NoWorkspaceStorageStack",
                environment="dev",
                env=Environment(account="123456789012", region="us-east-1"),
            )
        ).find_resources("AWS::DynamoDB::Table")
        names = {t["Properties"]["TableName"] for t in tables.values()}
        assert "oscar-release-notify-state-dev" in names
