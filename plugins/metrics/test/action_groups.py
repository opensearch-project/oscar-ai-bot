# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Bedrock action group definitions for test metrics plugin."""

from typing import List

from aws_cdk import aws_bedrock as bedrock


def get_action_groups(lambda_arn: str) -> List[bedrock.CfnAgent.AgentActionGroupProperty]:
    return [
        bedrock.CfnAgent.AgentActionGroupProperty(
            action_group_name="integrationTestActionGroup",
            description="Enhanced integration test failure analysis and component testing insights",
            action_group_state="ENABLED",
            action_group_executor=bedrock.CfnAgent.ActionGroupExecutorProperty(lambda_=lambda_arn),
            function_schema=bedrock.CfnAgent.FunctionSchemaProperty(
                functions=[
                    bedrock.CfnAgent.FunctionProperty(
                        name="get_integration_test_metrics",
                        description="Retrieve comprehensive integration test results including pass/fail rates, component testing, and security test outcomes",
                        parameters={
                            "rc_numbers": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string", description="Comma-separated RC numbers to analyze (e.g., '1,2,3' or '1')", required=False
                            ),
                            "integ_test_build_numbers": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string", description="Comma-separated integration test build numbers to analyze", required=False
                            ),
                            "components": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string", description="Comma-separated component names to focus on (e.g., 'OpenSearch,OpenSearch-Dashboards')", required=False
                            ),
                            "status_filter": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string", description="Filter by test status: 'passed' or 'failed'", required=False
                            ),
                            "without_security": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string", description="Filter non-security tests: 'pass' or 'fail'", required=False
                            ),
                            "build_numbers": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string", description="Comma-separated distribution build numbers to analyze (e.g., '12345,12346')", required=False
                            ),
                            "with_security": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string", description="Filter security tests: 'pass' or 'fail'", required=False
                            ),
                            "distribution": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string", description="Distribution type: 'tar', 'rpm', or 'deb' (default: 'tar')", required=False
                            ),
                            "version": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string", description="OpenSearch version to analyze (e.g., '3.2.0', '2.18.0') - REQUIRED", required=False
                            ),
                            "platform": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string", description="Platform: 'linux' or 'windows' (default: 'linux')", required=False
                            ),
                            "architecture": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string", description="Architecture: 'x64' or 'arm64' (default: 'x64')", required=False
                            ),
                        },
                    ),
                    bedrock.CfnAgent.FunctionProperty(
                        name="get_rc_build_mapping",
                        description="Get build numbers for specific RC numbers",
                        parameters={
                            "rc_numbers": bedrock.CfnAgent.ParameterDetailProperty(
                                type="array", description="List of RC numbers", required=False
                            ),
                            "component": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string", description="Component name for RC resolution", required=False
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
