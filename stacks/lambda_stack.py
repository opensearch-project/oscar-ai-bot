#!/usr/bin/env python
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
"""
Lambda stack for OSCAR infrastructure.

This module defines all Lambda functions used by OSCAR including:
- Main OSCAR agent with Slack event processing
- Communication handler for Bedrock action groups
- Plugin-based Lambda functions for collaborator agents
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
        plugins: Optional[List] = None,
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

        # Plugin lambdas
        if plugins:
            self._create_plugin_lambdas(plugins)

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

    # --------------------------------------------------------------- plugins
    def _create_plugin_lambdas(self, plugins) -> None:
        """Create Lambda functions for plugins, deduplicating shared entry paths."""
        created_entries: Dict[str, PythonFunction] = {}

        for plugin in plugins:
            config = plugin.get_lambda_config()

            # Reuse Lambda if another plugin already created one for this entry
            if config.entry in created_entries:
                self.lambda_functions[plugin.name] = created_entries[config.entry]
                continue

            fn_name = f"oscar-{plugin.name}-{self.env_name}"
            role = self.permissions_stack.plugin_roles[plugin.name]
            self.secrets_stack.grant_read_access(role)

            kwargs = dict(
                function_name=fn_name,
                runtime=aws_lambda.Runtime.PYTHON_3_12,
                handler=config.handler,
                entry=config.entry,
                index=config.index,
                timeout=Duration.seconds(config.timeout_seconds),
                memory_size=config.memory_size,
                environment=config.environment_variables,
                role=role,
                description=f"OSCAR {plugin.name} agent lambda function",
                reserved_concurrent_executions=config.reserved_concurrency,
            )

            if config.needs_vpc and self.vpc_stack:
                kwargs["vpc"] = self.vpc_stack.vpc
                kwargs["security_groups"] = [self.vpc_stack.lambda_security_group]
                kwargs["allow_public_subnet"] = True

            construct_id = plugin.name.replace("-", " ").title().replace(" ", "") + "Lambda"
            function = PythonFunction(self, construct_id, **kwargs)
            function.add_permission(
                "AllowBedrockInvoke",
                principal=iam.ServicePrincipal("bedrock.amazonaws.com"),
                action="lambda:InvokeFunction",
                source_account=self.account,
            )

            self.lambda_functions[plugin.name] = function
            created_entries[config.entry] = function

    # ------------------------------------------------------------- env vars
    def _get_main_agent_environment_variables(self) -> Dict[str, str]:
        params = get_ssm_param_paths(self.env_name)
        return {
            "CENTRAL_SECRET_NAME": self.secrets_stack.central_env_secret.secret_name,
            "CONTEXT_TABLE_NAME": self.storage_stack.context_table_name,
            "OSCAR_PRIVILEGED_BEDROCK_AGENT_ID_PARAM_PATH": params["supervisor_agent_id"],
            "OSCAR_PRIVILEGED_BEDROCK_AGENT_ALIAS_PARAM_PATH": params["supervisor_agent_alias"],
            "OSCAR_LIMITED_BEDROCK_AGENT_ID_PARAM_PATH": params["limited_supervisor_agent_id"],
            "OSCAR_LIMITED_BEDROCK_AGENT_ALIAS_PARAM_PATH": params["limited_supervisor_agent_alias"],
            "ENABLE_DM": os.environ.get("ENABLE_DM", "false"),
            "AWS_ACCOUNT_ID": os.environ.get("AWS_ACCOUNT_ID") or os.environ.get("CDK_DEFAULT_ACCOUNT", ""),
        }

    def _get_communication_handler_environment_variables(self) -> Dict[str, str]:
        return {
            "CENTRAL_SECRET_NAME": self.secrets_stack.central_env_secret.secret_name,
            "CONTEXT_TABLE_NAME": self.storage_stack.context_table_name,
            "MESSAGE_TIMEOUT": os.environ.get("MESSAGE_TIMEOUT", "30"),
            "MAX_RETRIES": os.environ.get("MAX_RETRIES", "3"),
            "LOG_LEVEL": os.environ.get("LOG_LEVEL", "INFO"),
        }
