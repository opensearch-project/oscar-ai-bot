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
                            "memory_id": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string",
                                description="Memory ID from a previous query_metrics response. Pass this to maintain conversational context with the search agent across follow-up queries.",
                                required=False,
                            ),
                        },
                    ),
                    bedrock.CfnAgent.FunctionProperty(
                        name="get_release_status",
                        description="Get the authoritative release-readiness verdict (red/yellow/green) for a version, computed deterministically from the latest indexed state of every release criterion. Use this whenever the user asks whether a release is ready, a go/no-go, on track, or what its overall status is.",
                        parameters={
                            "version": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string",
                                description="Release version to check, e.g. '3.9.0'",
                                required=True,
                            ),
                        },
                    ),
                    bedrock.CfnAgent.FunctionProperty(
                        name="get_release_window",
                        description="Get the release schedule for a version: RC date, release date, days remaining to each, release manager, and the current cadence phase. Use this for any question about release timing, deadlines, or dates.",
                        parameters={
                            "version": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string",
                                description="Release version to look up, e.g. '3.9.0'",
                                required=True,
                            ),
                        },
                    ),
                    bedrock.CfnAgent.FunctionProperty(
                        name="query_release_state",
                        description="Ask a free-form question about release-readiness criteria or the release schedule using natural language, e.g. 'which components are blocking 3.9.0', 'which criteria changed in the last day', 'which releases are active'. Use get_release_status for the overall verdict and get_release_window for dates instead of this.",
                        parameters={
                            "query": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string",
                                description="Natural language question about release criteria or schedule",
                                required=True,
                            ),
                            "version": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string",
                                description="Release version to scope the question to, e.g. '3.9.0'",
                                required=False,
                            ),
                            "scope": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string",
                                description="Which index to query: 'state' (default) for per-criterion readiness data, 'schedule' for release dates and registration data",
                                required=False,
                            ),
                        },
                    ),
                ]
            ),
        )
    ]
