# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for identity tables in OSCAR storage stack."""

import pytest
from aws_cdk import App, Environment
from aws_cdk.assertions import Template

from stacks.storage_stack import OscarStorageStack


@pytest.fixture(autouse=True)
def set_create_tables(monkeypatch):
    """Enable table creation for identity stack tests."""
    monkeypatch.setenv("CREATE_IDENTITY_TABLES", "true")


@pytest.fixture
def template_with_workspace():
    """Synthesise storage stack with a workspace."""
    app = App()
    stack = OscarStorageStack(
        app, "TestStorageStack",
        environment="dev",
        workspace_id="T01INTERNAL",
        env=Environment(account="123456789012", region="us-east-1"),
    )
    return Template.from_stack(stack)


@pytest.fixture
def template_no_workspace():
    """Synthesise storage stack with no workspace."""
    app = App()
    stack = OscarStorageStack(
        app, "TestStorageStackEmpty",
        environment="dev",
        workspace_id=None,
        env=Environment(account="123456789012", region="us-east-1"),
    )
    return Template.from_stack(stack)


class TestIdentityTables:

    def test_creates_identity_table(self, template_with_workspace):
        # 1 context table + 1 identity table = 2
        template_with_workspace.resource_count_is("AWS::DynamoDB::Table", 2)

    def test_no_identity_table_when_no_workspace(self, template_no_workspace):
        # Only the context table
        template_no_workspace.resource_count_is("AWS::DynamoDB::Table", 1)

    def test_identity_table_has_github_id_as_pk(self, template_with_workspace):
        template_with_workspace.has_resource_properties("AWS::DynamoDB::Table", {
            "KeySchema": [
                {"AttributeName": "github_id", "KeyType": "HASH"},
            ],
        })

    def test_identity_table_has_gsi_on_slack_user_id(self, template_with_workspace):
        template_with_workspace.has_resource_properties("AWS::DynamoDB::Table", {
            "GlobalSecondaryIndexes": [{
                "IndexName": "slack-user-index",
                "KeySchema": [
                    {"AttributeName": "slack_user_id", "KeyType": "HASH"},
                ],
            }],
        })

    def test_identity_table_uses_pay_per_request(self, template_with_workspace):
        template_with_workspace.has_resource_properties("AWS::DynamoDB::Table", {
            "BillingMode": "PAY_PER_REQUEST",
        })
