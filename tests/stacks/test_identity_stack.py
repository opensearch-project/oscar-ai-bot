# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""Tests for OSCAR identity stack."""

import pytest
from aws_cdk import App, Environment
from aws_cdk.assertions import Template

from stacks.identity_stack import OscarIdentityStack


@pytest.fixture
def template_with_workspaces():
    """Synthesise identity stack with two workspaces."""
    app = App()
    stack = OscarIdentityStack(
        app, "TestIdentityStack",
        environment="dev",
        workspace_ids=["T01INTERNAL", "T02OPENSOURCE"],
        env=Environment(account="123456789012", region="us-east-1"),
    )
    return Template.from_stack(stack)


@pytest.fixture
def template_no_workspaces():
    """Synthesise identity stack with no workspaces."""
    app = App()
    stack = OscarIdentityStack(
        app, "TestIdentityStackEmpty",
        environment="dev",
        workspace_ids=[],
        env=Environment(account="123456789012", region="us-east-1"),
    )
    return Template.from_stack(stack)


class TestIdentityStack:

    def test_creates_one_table_per_workspace(self, template_with_workspaces):
        template_with_workspaces.resource_count_is("AWS::DynamoDB::Table", 2)

    def test_no_tables_when_no_workspaces(self, template_no_workspaces):
        template_no_workspaces.resource_count_is("AWS::DynamoDB::Table", 0)

    def test_table_has_github_id_as_pk(self, template_with_workspaces):
        template_with_workspaces.has_resource_properties("AWS::DynamoDB::Table", {
            "KeySchema": [
                {"AttributeName": "github_id", "KeyType": "HASH"},
            ],
        })

    def test_table_has_gsi_on_slack_user_id(self, template_with_workspaces):
        template_with_workspaces.has_resource_properties("AWS::DynamoDB::Table", {
            "GlobalSecondaryIndexes": [{
                "IndexName": "slack-user-index",
                "KeySchema": [
                    {"AttributeName": "slack_user_id", "KeyType": "HASH"},
                ],
            }],
        })

    def test_table_uses_pay_per_request(self, template_with_workspaces):
        template_with_workspaces.has_resource_properties("AWS::DynamoDB::Table", {
            "BillingMode": "PAY_PER_REQUEST",
        })
