# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Bedrock action group definitions for build metrics plugin."""

from typing import List

from aws_cdk import aws_bedrock as bedrock


def get_action_groups(lambda_arn: str) -> List[bedrock.CfnAgent.AgentActionGroupProperty]:
    return [
        bedrock.CfnAgent.AgentActionGroupProperty(
            action_group_name="buildMetricsActionGroup",
            description="Enhanced build metrics analysis and distribution build insights",
            action_group_state="ENABLED",
            action_group_executor=bedrock.CfnAgent.ActionGroupExecutorProperty(lambda_=lambda_arn),
            function_schema=bedrock.CfnAgent.FunctionSchemaProperty(
                functions=[
                    bedrock.CfnAgent.FunctionProperty(
                        name="get_build_metrics",
                        description="Retrieve comprehensive build performance metrics including success rates, failure patterns, and component build results",
                        parameters={
                            "rc_numbers": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string", description="Comma-separated RC numbers to analyze (e.g., '1,2,3')", required=False
                            ),
                            "components": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string", description="Comma-separated component names to focus on (e.g., 'OpenSearch,OpenSearch-Dashboards')", required=False
                            ),
                            "status_filter": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string", description="Filter by build status: 'passed' or 'failed'", required=False
                            ),
                            "build_numbers": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string", description="Comma-separated distribution build numbers to analyze (e.g., '12345,12346')", required=False
                            ),
                            "version": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string", description="OpenSearch version to analyze (e.g., '3.2.0', '2.18.0') - REQUIRED", required=False
                            ),
                        },
                    ),
                    bedrock.CfnAgent.FunctionProperty(
                        name="resolve_components_from_builds",
                        description="Resolve which components are associated with specific build numbers",
                        parameters={
                            "build_numbers": bedrock.CfnAgent.ParameterDetailProperty(
                                type="array", description="List of build numbers to resolve", required=False
                            ),
                            "version": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string", description="Version number", required=False
                            ),
                        },
                    ),
                ]
            ),
        )
    ]
