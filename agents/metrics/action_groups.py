# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Bedrock action group definitions for metrics agent."""

from typing import List

from aws_cdk import aws_bedrock as bedrock


def get_action_groups(lambda_arn: str) -> List[bedrock.CfnAgent.AgentActionGroupProperty]:
    return [
        bedrock.CfnAgent.AgentActionGroupProperty(
            action_group_name="metricsActionGroup",
            description="Unified metrics analysis for builds, tests, and release readiness",
            action_group_state="ENABLED",
            action_group_executor=bedrock.CfnAgent.ActionGroupExecutorProperty(lambda_=lambda_arn),
            function_schema=bedrock.CfnAgent.FunctionSchemaProperty(
                functions=[
                    bedrock.CfnAgent.FunctionProperty(
                        name="query_metrics",
                        description="Query metrics data using natural language. Automatically routes to the appropriate data source (build results, test results, or release metrics) based on query content.",
                        parameters={
                            "query": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string",
                                description="Natural language query about metrics (e.g., 'Failed components for 3.5.0', 'What tests are failing on linux for 3.6.0 version?', 'Release readiness for OpenSearch-Dashboards')",
                                required=True,
                            ),
                            "version": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string",
                                description="OpenSearch version to scope the query (e.g., '3.2.0', '2.18.0')",
                                required=True,
                            ),
                        },
                    ),
                ]
            ),
        )
    ]
