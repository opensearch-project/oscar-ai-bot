# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Bedrock action group definitions for security advisories agent."""

from typing import List

from aws_cdk import aws_bedrock as bedrock


def get_action_groups(lambda_arn: str) -> List[bedrock.CfnAgent.AgentActionGroupProperty]:
    return [
        bedrock.CfnAgent.AgentActionGroupProperty(
            action_group_name="securityAdvisoriesActions",
            description="Query CVEs and security vulnerabilities for OpenSearch project components",
            action_group_state="ENABLED",
            action_group_executor=bedrock.CfnAgent.ActionGroupExecutorProperty(lambda_=lambda_arn),
            function_schema=bedrock.CfnAgent.FunctionSchemaProperty(
                functions=[
                    bedrock.CfnAgent.FunctionProperty(
                        name="query_vulnerabilities",
                        description=(
                            "Query CVEs and vulnerabilities using natural language. "
                            "The query is routed through an agentic flow pipeline that "
                            "automatically translates it into OpenSearch DSL. Optionally "
                            "scope by version or project name."
                        ),
                        parameters={
                            "query": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string",
                                description=(
                                    "Natural language query about vulnerabilities "
                                    "(e.g., 'Show me critical CVEs for OpenSearch Dashboards 2.19.6', "
                                    "'High severity vulnerabilities from the past 30 days')"
                                ),
                                required=True,
                            ),
                            "version": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string",
                                description=(
                                    "OpenSearch version to scope the query "
                                    "(e.g., '2.19.6', '3.0.0')"
                                ),
                                required=False,
                            ),
                            "project_name": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string",
                                description=(
                                    "Project name to scope the query "
                                    "(e.g., 'OpenSearch Dashboards', 'OpenSearch')"
                                ),
                                required=False,
                            ),
                            "severity": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string",
                                description=(
                                    "Comma-separated severity levels to filter results "
                                    "(e.g., 'CRITICAL', 'CRITICAL,HIGH'). "
                                    "Valid values: CRITICAL, HIGH, MEDIUM, LOW"
                                ),
                                required=False,
                            ),
                            "age_days": bedrock.CfnAgent.ParameterDetailProperty(
                                type="integer",
                                description=(
                                    "Maximum age in days for scan results. Only return "
                                    "vulnerabilities from scans within this many days "
                                    "(e.g., 30 for the past month, 7 for the past week)"
                                ),
                                required=False,
                            ),
                        },
                    ),
                    bedrock.CfnAgent.FunctionProperty(
                        name="list_projects",
                        description=(
                            "List all projects and their available tags/versions in the scans index. "
                            "Use to discover what components and release versions are available."
                        ),
                        parameters={},
                    ),
                ]
            ),
        )
    ]
