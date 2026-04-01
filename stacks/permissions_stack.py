#!/usr/bin/env python
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.
"""
Permissions stack for OSCAR CDK automation.

This module defines IAM roles and policies for all OSCAR components including
Bedrock agents, Lambda functions, API Gateway, and cross-account access.
"""

from typing import Dict, List, Optional

from aws_cdk import Stack
from aws_cdk import aws_iam as iam
from constructs import Construct

from .policy_definitions import OscarPolicyDefinitions


class OscarPermissionsStack(Stack):
    """
    IAM permissions and roles for OSCAR infrastructure.
    This construct creates all necessary IAM roles and policies for OSCAR components
    with least-privilege access and proper security boundaries.
    """

    def __init__(self, scope: Construct, construct_id: str, environment: str, agents: Optional[List] = None, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.account_id = self.env.account
        self.aws_region = self.env.region
        self.env_name = environment

        # Initialize policy definitions for core roles
        self.policy_definitions = OscarPolicyDefinitions(self.account_id, self.aws_region, self.env_name)

        # Create core IAM roles
        self.bedrock_agent_role = self._create_bedrock_agent_role()
        self.lambda_execution_roles = self._create_core_lambda_roles()
        self.api_gateway_role = self._create_api_gateway_role()

        # Create agent roles
        self.agent_roles: Dict[str, iam.Role] = {}
        if agents:
            self.agent_roles = self._create_agent_roles(agents)

    def _create_bedrock_agent_role(self) -> iam.Role:
        role = iam.Role(
            self, "BedrockAgentExecutionRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            description="Execution role for OSCAR Bedrock agents"
        )
        for policy_statement in self.policy_definitions.get_bedrock_agent_policies():
            role.add_to_policy(policy_statement)
        return role

    def _create_core_lambda_roles(self) -> Dict[str, iam.Role]:
        """Create Lambda execution roles for core (non-agent) functions."""
        roles = {}

        # Base role for oscar-agent
        base_role = iam.Role(
            self, "BaseLambdaExecutionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
            ],
            description="Base execution role for OSCAR Lambda functions"
        )
        for stmt in self.policy_definitions.get_lambda_base_policies():
            base_role.add_to_policy(stmt)
        roles["base"] = base_role

        # Communication handler role
        comm_role = iam.Role(
            self, "CommunicationHandlerRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
            ],
            description="Execution role for OSCAR communication handler Lambda"
        )
        for stmt in self.policy_definitions.get_communication_handler_policies():
            comm_role.add_to_policy(stmt)
        roles["communication"] = comm_role

        return roles

    def _create_agent_roles(self, agents) -> Dict[str, iam.Role]:
        """Create IAM roles for agents, deduplicating by Lambda entry path.

        Agents sharing the same Lambda entry directory share a single role.
        """
        roles = {}
        created_entries: Dict[str, iam.Role] = {}

        for agent in agents:
            entry = agent.get_lambda_config().entry
            if entry in created_entries:
                roles[agent.name] = created_entries[entry]
                continue

            role_prefix = entry.split("/")[1].title()  # e.g. "agents/metrics/lambda" → "Metrics"
            managed = [
                iam.ManagedPolicy.from_aws_managed_policy_name(p)
                for p in agent.get_managed_policies()
            ]
            role = iam.Role(
                self, f"{role_prefix}LambdaRole",
                assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
                managed_policies=managed,
                description=f"Execution role for OSCAR {role_prefix.lower()} Lambda"
            )
            for stmt in agent.get_iam_policies(self.account_id, self.aws_region, self.env_name):
                role.add_to_policy(stmt)
            roles[agent.name] = role
            created_entries[entry] = role
        return roles

    def _create_api_gateway_role(self) -> iam.Role:
        role = iam.Role(
            self, "ApiGatewayExecutionRole",
            assumed_by=iam.ServicePrincipal("apigateway.amazonaws.com"),
            description="Execution role for OSCAR API Gateway"
        )
        for policy_statement in self.policy_definitions.get_api_gateway_policies():
            role.add_to_policy(policy_statement)
        return role
