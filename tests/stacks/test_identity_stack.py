# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for identity tables in OSCAR storage stack."""

import pytest
from aws_cdk import App, Environment
from aws_cdk.assertions import Template

from stacks.storage_stack import OscarStorageStack


@pytest.fixture
def template_with_workspaces():
    """Synthesise storage stack with two workspaces."""
    app = App()
    stack = OscarStorageStack(
        app, "TestStorageStack",
        environment="dev",
        workspace_ids=["T01INTERNAL", "T02OPENSOURCE"],
        env=Environment(account="123456789012", region="us-east-1"),
    )
    return Template.from_stack(stack)


@pytest.fixture
def template_no_workspaces():
    """Synthesise storage stack with no workspaces."""
    app = App()
    stack = OscarStorageStack(
        app, "TestStorageStackEmpty",
        environment="dev",
        workspace_ids=[],
        env=Environment(account="123456789012", region="us-east-1"),
    )
    return Template.from_stack(stack)


class TestIdentityTables:

    def test_creates_identity_tables_per_workspace(self, template_with_workspaces):
        # 1 context table + 2 identity tables = 3
        template_with_workspaces.resource_count_is("AWS::DynamoDB::Table", 3)

    def test_no_identity_tables_when_no_workspaces(self, template_no_workspaces):
        # Only the context table
        template_no_workspaces.resource_count_is("AWS::DynamoDB::Table", 1)

    def test_identity_table_has_github_id_as_pk(self, template_with_workspaces):
        template_with_workspaces.has_resource_properties("AWS::DynamoDB::Table", {
            "KeySchema": [
                {"AttributeName": "github_id", "KeyType": "HASH"},
            ],
        })

    def test_identity_table_has_gsi_on_slack_user_id(self, template_with_workspaces):
        template_with_workspaces.has_resource_properties("AWS::DynamoDB::Table", {
            "GlobalSecondaryIndexes": [{
                "IndexName": "slack-user-index",
                "KeySchema": [
                    {"AttributeName": "slack_user_id", "KeyType": "HASH"},
                ],
            }],
        })

    def test_identity_table_uses_pay_per_request(self, template_with_workspaces):
        template_with_workspaces.has_resource_properties("AWS::DynamoDB::Table", {
            "BillingMode": "PAY_PER_REQUEST",
        })