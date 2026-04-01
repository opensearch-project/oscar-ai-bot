#!/usr/bin/env python
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""
Lambda stack for OSCAR infrastructure.

This module defines all Lambda functions used by OSCAR including:
- Main OSCAR agent with Slack event processing
- Communication handler for Bedrock action groups
- Agent-based Lambda functions for collaborator agents
"""

import logging
import os
from typing import Any, Dict, List, Optional

from aws_cdk import Duration, Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda
from aws_cdk.aws_lambda_python_alpha import PythonFunction
from constructs import Construct

from .bedrock_agent_details import get_ssm_param_paths

logger = logging.getLogger(__name__)


class OscarLambdaStack(Stack):
    """Lambda resources for OSCAR infrastructure."""

    SUPERVISOR_AGENT_LAMBDA_FUNCTION_NAME = 'oscar-supervisor-agent'
    COMMUNICATION_HANDLER_LAMBDA_FUNCTION_NAME = 'oscar-communication-handler'

    @classmethod
    def get_supervisor_agent_function_name(cls, env: str) -> str:
        return f"{cls.SUPERVISOR_AGENT_LAMBDA_FUNCTION_NAME}-{env}"

    @classmethod
    def get_communication_handler_lambda_function_name(cls, env: str) -> str:
        return f"{cls.COMMUNICATION_HANDLER_LAMBDA_FUNCTION_NAME}-{env}"

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        permissions_stack: Any,
        secrets_stack: Any,
        storage_stack: Any,
        environment: str,
        agents: Optional[List] = None,
        vpc_stack: Optional[Any] = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.storage_stack = storage_stack
        self.permissions_stack = permissions_stack
        self.secrets_stack = secrets_stack
        self.vpc_stack = vpc_stack
        self.env_name = environment

        self.lambda_functions: Dict[str, PythonFunction] = {}

        # Core lambdas
        self._create_supervisor_agent_lambda()
        self._create_communication_handler_lambda()

        # Agent lambdas
        if agents:
            self._create_agent_lambdas(agents)

    # ------------------------------------------------------------------ core
    def _create_supervisor_agent_lambda(self) -> None:
        execution_role = self.permissions_stack.lambda_execution_roles["base"]
        self.secrets_stack.grant_read_access(execution_role)

        function = PythonFunction(
            self, "MainOscarAgentLambda",
            function_name=self.get_supervisor_agent_function_name(self.env_name),
            runtime=aws_lambda.Runtime.PYTHON_3_12,
            handler="lambda_handler",
            entry="lambda/oscar-agent",
            index="app.py",
            timeout=Duration.seconds(300),
            memory_size=1024,
            environment=self._get_main_agent_environment_variables(),
            role=execution_role,
            description="Main OSCAR agent with Slack event processing capabilities",
            reserved_concurrent_executions=10,
        )
        function.add_permission(
            "AllowBedrockInvoke",
            principal=iam.ServicePrincipal("bedrock.amazonaws.com"),
            action="lambda:InvokeFunction",
            source_account=self.account,
        )
        function.add_permission(
            "SelfInvoke",
            principal=iam.ServicePrincipal("lambda.amazonaws.com"),
            action="lambda:InvokeFunction",
            source_arn=function.function_arn,
        )
        self.lambda_functions[self.get_supervisor_agent_function_name(self.env_name)] = function

    def _create_communication_handler_lambda(self) -> None:
        execution_role = self.permissions_stack.lambda_execution_roles["communication"]
        self.secrets_stack.grant_read_access(execution_role)

        function = PythonFunction(
            self, "CommunicationHandlerLambda",
            function_name=self.get_communication_handler_lambda_function_name(self.env_name),
            runtime=aws_lambda.Runtime.PYTHON_3_12,
            handler="lambda_handler",
            entry="lambda/oscar-communication-handler",
            index="lambda_function.py",
            timeout=Duration.seconds(60),
            memory_size=512,
            environment=self._get_communication_handler_environment_variables(),
            role=execution_role,
            description="Communication handler for OSCAR Bedrock action groups",
            reserved_concurrent_executions=20,
        )
        function.add_permission(
            "AllowBedrockInvoke",
            principal=iam.ServicePrincipal("bedrock.amazonaws.com"),
            action="lambda:InvokeFunction",
            source_account=self.account,
        )
        self.lambda_functions[self.get_communication_handler_lambda_function_name(self.env_name)] = function

    # ------------------------------------------------------------ agents
    def _create_agent_lambdas(self, agents) -> None:
        """Create Lambda functions for agents, deduplicating shared entry paths."""
        created_entries: Dict[str, PythonFunction] = {}

        for agent in agents:
            config = agent.get_lambda_config()

            # Reuse Lambda if another agent already created one for this entry
            if config.entry in created_entries:
                self.lambda_functions[agent.name] = created_entries[config.entry]
                continue

            fn_name = f"oscar-{agent.name}-{self.env_name}"
            role = self.permissions_stack.agent_roles[agent.name]

            # Merge agent secret names into Lambda environment variables
            env_vars = dict(config.environment_variables)
            for secret_config in agent.get_secrets():
                secret = self.secrets_stack.get_agent_secret(
                    agent.name, secret_config.name_suffix
                )
                if secret:
                    env_vars[secret_config.env_var] = secret.secret_name
                    secret.grant_read(role)

            kwargs = dict(
                function_name=fn_name,
                runtime=aws_lambda.Runtime.PYTHON_3_12,
                handler=config.handler,
                entry=config.entry,
                index=config.index,
                timeout=Duration.seconds(config.timeout_seconds),
                memory_size=config.memory_size,
                environment=env_vars,
                role=role,
                description=f"OSCAR {agent.name} agent lambda function",
                reserved_concurrent_executions=config.reserved_concurrency,
            )

            if config.needs_vpc and self.vpc_stack:
                kwargs["vpc"] = self.vpc_stack.vpc
                kwargs["security_groups"] = [self.vpc_stack.lambda_security_group]
                kwargs["allow_public_subnet"] = True

            construct_id = agent.name.replace("-", " ").title().replace(" ", "") + "Lambda"
            function = PythonFunction(self, construct_id, **kwargs)
            function.add_permission(
                "AllowBedrockInvoke",
                principal=iam.ServicePrincipal("bedrock.amazonaws.com"),
                action="lambda:InvokeFunction",
                source_account=self.account,
            )

            self.lambda_functions[agent.name] = function
            created_entries[config.entry] = function

    # ------------------------------------------------------------- env vars

    # Keys to pass through from .env to Lambda (if set). Lambda config.py has its own defaults.
    _AGENT_ENV_KEYS = [
        "ENABLE_DM", "CONTEXT_TTL", "AGENT_TIMEOUT", "AGENT_MAX_RETRIES",
        "HOURGLASS_THRESHOLD_SECONDS", "TIMEOUT_THRESHOLD_SECONDS",
        "MAX_WORKERS", "MAX_ACTIVE_QUERIES", "MONITOR_INTERVAL_SECONDS",
        "SLACK_HANDLER_THREAD_NAME_PREFIX",
        "AGENT_QUERY_ANNOUNCE", "AGENT_QUERY_ASSIGN_OWNER", "AGENT_QUERY_REQUEST_OWNER",
        "AGENT_QUERY_RC_DETAILS", "AGENT_QUERY_MISSING_NOTES",
        "AGENT_QUERY_INTEGRATION_TEST", "AGENT_QUERY_BROADCAST",
        "CHANNEL_ID_PATTERN", "CHANNEL_REF_PATTERN", "AT_SYMBOL_PATTERN",
        "MENTION_PATTERN", "HEADING_PATTERN", "BOLD_PATTERN", "ITALIC_PATTERN",
        "LINK_PATTERN", "BULLET_PATTERN", "CHANNEL_MENTION_PATTERN", "VERSION_PATTERN",
        "LOG_QUERY_PREVIEW_LENGTH",
    ]

    _COMM_HANDLER_ENV_KEYS = [
        "CONTEXT_TTL", "BEDROCK_RESPONSE_MESSAGE_VERSION", "CHANNEL_MAPPINGS",
        "CHANNEL_ID_PATTERN", "CHANNEL_REF_PATTERN", "MESSAGE_TIMEOUT", "LOG_LEVEL",
    ]

    @staticmethod
    def _passthrough_env(keys: List[str]) -> Dict[str, str]:
        """Pass through env vars from .env to Lambda — only if set."""
        return {k: os.environ[k] for k in keys if k in os.environ}

    def _get_main_agent_environment_variables(self) -> Dict[str, str]:
        params = get_ssm_param_paths(self.env_name)
        env = self._passthrough_env(self._AGENT_ENV_KEYS)
        env.update({
            "CENTRAL_SECRET_NAME": self.secrets_stack.central_env_secret.secret_name,
            "CONTEXT_TABLE_NAME": self.storage_stack.context_table_name,
            "OSCAR_PRIVILEGED_BEDROCK_AGENT_ID_PARAM_PATH": params["supervisor_agent_id"],
            "OSCAR_PRIVILEGED_BEDROCK_AGENT_ALIAS_PARAM_PATH": params["supervisor_agent_alias"],
            "OSCAR_LIMITED_BEDROCK_AGENT_ID_PARAM_PATH": params["limited_supervisor_agent_id"],
            "OSCAR_LIMITED_BEDROCK_AGENT_ALIAS_PARAM_PATH": params["limited_supervisor_agent_alias"],
            "AWS_ACCOUNT_ID": os.environ.get("AWS_ACCOUNT_ID") or os.environ.get("CDK_DEFAULT_ACCOUNT", ""),
        })
        return env

    def _get_communication_handler_environment_variables(self) -> Dict[str, str]:
        env = self._passthrough_env(self._COMM_HANDLER_ENV_KEYS)
        env.update({
            "CENTRAL_SECRET_NAME": self.secrets_stack.central_env_secret.secret_name,
            "CONTEXT_TABLE_NAME": self.storage_stack.context_table_name,
        })
        return env
