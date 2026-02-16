# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Bedrock action group definitions for release metrics plugin."""

from typing import List

from aws_cdk import aws_bedrock as bedrock


def get_action_groups(lambda_arn: str) -> List[bedrock.CfnAgent.AgentActionGroupProperty]:
    return [
        bedrock.CfnAgent.AgentActionGroupProperty(
            action_group_name="releaseMetricsActionsGroup",
            description="Enhanced release readiness analysis and component release insights",
            action_group_state="ENABLED",
            action_group_executor=bedrock.CfnAgent.ActionGroupExecutorProperty(lambda_=lambda_arn),
            function_schema=bedrock.CfnAgent.FunctionSchemaProperty(
                functions=[
                    bedrock.CfnAgent.FunctionProperty(
                        name="get_release_metrics",
                        description="Get comprehensive release readiness metrics and component analysis",
                        parameters={
                            "components": bedrock.CfnAgent.ParameterDetailProperty(
                                type="array", description="List of component names", required=False
                            ),
                            "time_range": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string", description="Time range for analysis (1d, 7d, 30d)", required=False
                            ),
                            "query": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string", description="Natural language query about release readiness or status", required=False
                            ),
                            "version": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string", description="Version number (e.g., 3.2.0)", required=False
                            ),
                        },
                    )
                ]
            ),
        )
    ]
