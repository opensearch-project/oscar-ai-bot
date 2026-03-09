# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Bedrock action group definitions for Jenkins plugin."""

from typing import List

from aws_cdk import aws_bedrock as bedrock


def get_action_groups(lambda_arn: str) -> List[bedrock.CfnAgent.AgentActionGroupProperty]:
    return [
        bedrock.CfnAgent.AgentActionGroupProperty(
            action_group_name="jenkinsOperations",
            description="Comprehensive Jenkins job operations with parameter validation",
            action_group_state="ENABLED",
            action_group_executor=bedrock.CfnAgent.ActionGroupExecutorProperty(
                lambda_=lambda_arn
            ),
            function_schema=bedrock.CfnAgent.FunctionSchemaProperty(
                functions=[
                    bedrock.CfnAgent.FunctionProperty(
                        name="get_job_info",
                        description="Retrieve detailed information about a Jenkins job including parameters and requirements. Use when users need to understand job requirements/available parameters or when you need to look at this data. Defaults to docker-scan job if no job specified.",
                        parameters={
                            "job_name": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string",
                                description="Name of the Jenkins job to get information about (defaults to docker-scan)",
                                required=True,
                            )
                        },
                    ),
                    bedrock.CfnAgent.FunctionProperty(
                        name="list_jobs",
                        description="List all Jenkins jobs supported by this agent with their parameters and descriptions. Use when users ask 'what jobs are available?' or when you need to see all supported Jenkins operations.",
                        parameters={},
                    ),
                    bedrock.CfnAgent.FunctionProperty(
                        name="trigger_job",
                        description="Execute any supported Jenkins job with specified parameters. CRITICAL: Only executes when confirmed=true. Use for job execution ONLY after user confirmation.",
                        parameters={
                            "job_name": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string",
                                description="Name of the Jenkins job to trigger (e.g., 'docker-scan', 'central-release-promotion')",
                                required=True,
                            ),
                            "job_parameters": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string",
                                description="JSON object containing job-specific parameters. Each job has different required and optional parameters.",
                                required=False,
                            ),
                            "confirmed": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string",
                                description="REQUIRED: Must be 'true' to execute the job. Set to 'true' ONLY after user explicitly confirms job execution. Never set to 'true' without user confirmation. Accepts: 'true', 'false', true, false.",
                                required=True,
                            ),
                        },
                    ),
                    bedrock.CfnAgent.FunctionProperty(
                        name="get_build_status",
                        description="Get the current status of a Jenkins build. Returns the build state (SUCCESS, FAILURE, ABORTED, UNSTABLE, IN_PROGRESS), duration, and build URL. Use when users ask about the status or result of a specific build.",
                        parameters={
                            "job_name": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string",
                                description="Name of the Jenkins job",
                                required=True,
                            ),
                            "build_number": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string",
                                description="Build number to check status for",
                                required=True,
                            ),
                        },
                    ),
                    bedrock.CfnAgent.FunctionProperty(
                        name="get_build_failure_details",
                        description="Get failure details for a Jenkins build. Returns which pipeline stages failed or are unstable, their log output, and direct URLs to the failed stage logs. Use when a build has failed or is unstable and the user wants to know why.",
                        parameters={
                            "job_name": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string",
                                description="Name of the Jenkins job",
                                required=True,
                            ),
                            "build_number": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string",
                                description="Build number to get failure details for",
                                required=True,
                            ),
                        },
                    ),
                ]
            ),
        )
    ]
