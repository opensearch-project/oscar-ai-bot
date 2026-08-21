# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Bedrock action group definitions for security advisories agent."""

from typing import List

from aws_cdk import aws_bedrock as bedrock


def get_action_groups(lambda_arn: str) -> List[bedrock.CfnAgent.AgentActionGroupProperty]:
    return [
        _privileged_action_group(lambda_arn),
    ]


def _privileged_action_group(
    lambda_arn: str,
) -> bedrock.CfnAgent.AgentActionGroupProperty:
    """Action group for privileged users — full vulnerability querying."""
    return bedrock.CfnAgent.AgentActionGroupProperty(
        action_group_name="securityAdvisoriesActions",
        description="Query CVEs and security vulnerabilities for OpenSearch project components, and remediate a CVE by opening a fix pull request",
        action_group_state="ENABLED",
        action_group_executor=bedrock.CfnAgent.ActionGroupExecutorProperty(lambda_=lambda_arn),
        function_schema=bedrock.CfnAgent.FunctionSchemaProperty(
            functions=[
                bedrock.CfnAgent.FunctionProperty(
                    name="query_vulnerabilities",
                    description=(
                        "Query CVEs and vulnerabilities for OpenSearch project "
                        "components. Scope by version or project name. Call "
                        "list_projects() first to resolve the exact canonical "
                        "project name."
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
                                "OpenSearch version or branch to scope the query. "
                                "Valid values: a three-part version (e.g., '2.19.6', '3.0.0') "
                                "which resolves to its branch (origin/major.minor), "
                                "a two-part branch version (e.g., '3.7', '2.19'), "
                                "'main', "
                                "or an origin-prefixed tag (e.g., 'origin/2.19'). "
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
                                "Minimum age in days of CVE advisories to include. "
                                "Only return CVEs published at least this many days ago "
                                "(e.g., 60 for advisories older than 60 days, 14 for 2 weeks). "
                                "Default to 60 for release preparation queries."
                            ),
                            required=False,
                        ),
                    },
                ),
                bedrock.CfnAgent.FunctionProperty(
                    name="list_projects",
                    description=(
                        "List all projects and their available tags/versions in the scans index. "
                        "Use to discover what components and release versions are available. "
                        "Each project includes a 'tags' array with all available versions and "
                        "branches sorted in descending semver order."
                    ),
                    parameters={},
                ),
                bedrock.CfnAgent.FunctionProperty(
                    name="query_tickets",
                    description=(
                        "Query SIM tickets by CVE ID, project name, or branch."
                    ),
                    parameters={
                        "cve_id": bedrock.CfnAgent.ParameterDetailProperty(
                            type="string",
                            description=(
                                "CVE identifier to filter tickets (e.g., 'CVE-2026-27903')."
                            ),
                            required=False,
                        ),
                        "project_name": bedrock.CfnAgent.ParameterDetailProperty(
                            type="string",
                            description=(
                                "Project or component name to filter tickets."
                            ),
                            required=False,
                        ),
                        "branch": bedrock.CfnAgent.ParameterDetailProperty(
                            type="string",
                            description=(
                                "Branch name to filter tickets (e.g., 'origin/main' or 'origin/3.7')."
                            ),
                            required=False,
                        ),
                    },
                ),
                bedrock.CfnAgent.FunctionProperty(
                    name="list_ticket_projects",
                    description=(
                        "List projects that currently have assigned SIM tickets."
                    ),
                    parameters={},
                ),
                bedrock.CfnAgent.FunctionProperty(
                    name="remediate_cve",
                    description=(
                        "Remediate a specific CVE on a specific OpenSearch project "
                        "repository by opening a pull request that bumps the vulnerable "
                        "dependency. Before doing any work it checks whether an open PR "
                        "already fixes this CVE (e.g. from Dependabot, Mend, or a "
                        "maintainer) and, if so, returns that existing PR instead of "
                        "opening a duplicate."
                    ),
                    parameters={
                        "cve_id": bedrock.CfnAgent.ParameterDetailProperty(
                            type="string",
                            description=(
                                "The CVE identifier to remediate (e.g., 'CVE-2026-1225')."
                            ),
                            required=True,
                        ),
                        "project": bedrock.CfnAgent.ParameterDetailProperty(
                            type="string",
                            description=(
                                "The affected project or repository (e.g., 'alerting', "
                                "'OpenSearch'). Used to select the repository when a CVE "
                                "affects more than one. The actual repository is resolved "
                                "from the advisory data."
                            ),
                            required=True,
                        ),
                    },
                ),
            ]
        ),
    )
