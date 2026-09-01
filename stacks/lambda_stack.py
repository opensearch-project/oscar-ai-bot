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

from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_ecr_assets as ecr_assets
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda
from aws_cdk import aws_logs as logs
from aws_cdk.aws_lambda_python_alpha import PythonFunction
from constructs import Construct

from .bedrock_agent_details import get_ssm_param_paths

logger = logging.getLogger(__name__)


class OscarLambdaStack(Stack):
    """Lambda resources for OSCAR infrastructure."""

    SUPERVISOR_AGENT_LAMBDA_FUNCTION_NAME = 'oscar-supervisor-agent'
    COMMUNICATION_HANDLER_LAMBDA_FUNCTION_NAME = 'oscar-communication-handler'
    GITHUB_WEBHOOK_HANDLER_LAMBDA_FUNCTION_NAME = 'oscar-github-webhook-handler'

    @classmethod
    def get_supervisor_agent_function_name(cls, env: str) -> str:
        return f"{cls.SUPERVISOR_AGENT_LAMBDA_FUNCTION_NAME}-{env}"

    @classmethod
    def get_communication_handler_lambda_function_name(cls, env: str) -> str:
        return f"{cls.COMMUNICATION_HANDLER_LAMBDA_FUNCTION_NAME}-{env}"

    @classmethod
    def get_github_webhook_handler_function_name(cls, env: str) -> str:
        return f"{cls.GITHUB_WEBHOOK_HANDLER_LAMBDA_FUNCTION_NAME}-{env}"

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

        # Shared layer for common utilities (e.g. two-person approval guard)
        self.shared_layer = aws_lambda.LayerVersion(
            self, "OscarSharedLayer",
            code=aws_lambda.Code.from_asset("lambda/shared-layer"),
            compatible_runtimes=[aws_lambda.Runtime.PYTHON_3_12],
            description="Shared utilities for OSCAR Lambda functions",
        )

        # Core lambdas
        self._create_supervisor_agent_lambda()
        self._create_communication_handler_lambda()
        self._create_github_webhook_handler_lambda()

        # Identity lambda
        if storage_stack.identity_table:
            self._create_identity_lambda()

        # The CVE remediation worker runs as a Fargate task (below), not a
        # Lambda — large repos (core, and defensively all repos) exceed Lambda's
        # 15-min / disk / memory limits. The SecurityAdvisories handler dispatches
        # to it via ecs.run_task.
        self.remediation_cluster: Optional[ecs.Cluster] = None
        self.remediation_npm_task_def: Optional[ecs.FargateTaskDefinition] = None
        self._create_remediation_ecs()

        # Agent lambdas
        if agents:
            self._create_agent_lambdas(agents)

        # Let the SecurityAdvisories agent Lambda dispatch to the worker.
        self._wire_remediation_dispatch()

    # ------------------------------------------------------------------ core
    def _create_supervisor_agent_lambda(self) -> None:
        execution_role = self.permissions_stack.lambda_execution_roles["base"]
        self.secrets_stack.grant_read_access(execution_role)

        # Grant identity table access if configured
        if self.storage_stack.identity_table:
            self.storage_stack.identity_table.grant_read_write_data(execution_role)

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
            layers=[self.shared_layer],
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
            layers=[self.shared_layer],
        )
        function.add_permission(
            "AllowBedrockInvoke",
            principal=iam.ServicePrincipal("bedrock.amazonaws.com"),
            action="lambda:InvokeFunction",
            source_account=self.account,
        )
        self.lambda_functions[self.get_communication_handler_lambda_function_name(self.env_name)] = function

    # ----------------------------------------------------------- identity
    def _create_identity_lambda(self) -> None:
        """Create the OAuth callback Lambda for identity linking."""
        role = self.permissions_stack.lambda_execution_roles.get("identity")
        if not role:
            role = self.permissions_stack.lambda_execution_roles["base"]

        function = PythonFunction(
            self, "IdentityLambda",
            function_name=f"oscar-identity-{self.env_name}",
            runtime=aws_lambda.Runtime.PYTHON_3_12,
            handler="lambda_handler",
            entry="lambda/oscar-identity",
            index="lambda_function.py",
            timeout=Duration.seconds(300),
            memory_size=256,
            layers=[self.shared_layer],
            environment={
                "ENVIRONMENT": self.env_name,
                "CENTRAL_SECRET_NAME": self.secrets_stack.central_env_secret.secret_name,
                "IDENTITY_TABLE_NAME": self.storage_stack.identity_table.table_name,
            },
            role=role,
            description="Identity linking and weekly membership validation",
            reserved_concurrent_executions=5,
        )
        self.storage_stack.identity_table.grant_read_write_data(role)
        self.secrets_stack.grant_read_access(role)

        # Weekly EventBridge schedule for membership validation
        rule = events.Rule(
            self, "IdentityValidationSchedule",
            rule_name=f"oscar-identity-validation-{self.env_name}",
            schedule=events.Schedule.rate(Duration.days(7)),
            description="Weekly identity membership validation",
        )
        rule.add_target(targets.LambdaFunction(function))

        self.lambda_functions["identity"] = function

    def _create_github_webhook_handler_lambda(self) -> None:
        execution_role = self.permissions_stack.github_webhook_role
        fn_name = self.get_github_webhook_handler_function_name(self.env_name)
        secret_name = f"oscar-github-webhook-{self.env_name}"

        function = PythonFunction(
            self, "GitHubWebhookHandlerLambda",
            function_name=fn_name,
            runtime=aws_lambda.Runtime.PYTHON_3_12,
            handler="lambda_handler",
            entry="lambda/github-webhook-handler",
            index="lambda_function.py",
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "WEBHOOK_SECRET_NAME": secret_name,
            },
            role=execution_role,
            description="GitHub webhook handler — posts notifications to Slack",
            reserved_concurrent_executions=5,
            layers=[self.shared_layer],
        )
        self.lambda_functions[fn_name] = function

    # ------------------------------------------------- remediation worker
    def _remediation_worker_env(self) -> Dict[str, str]:
        """Environment for the remediation worker (the Fargate task).

        The write-target fork plus whichever GitHub + Slack credential source is
        set (a dev PAT via *_TOKEN, or a Secrets Manager name via *_SECRET_NAME —
        never both required). Kept as a helper so the container and task
        definition can't drift apart.
        """
        env = {
            "REMEDIATION_WRITE_OWNER": os.environ.get("REMEDIATION_WRITE_OWNER", "v-e-e-m-a"),
            # Unbuffered stdout so logs reach CloudWatch: a short Fargate task
            # exits before block-buffered Python output flushes to the awslogs
            # driver, otherwise leaving an empty log stream.
            "PYTHONUNBUFFERED": "1",
        }
        for key in ("GH_TOKEN", "GH_TOKEN_SECRET_NAME",
                    "SLACK_BOT_TOKEN", "SLACK_BOT_TOKEN_SECRET_NAME"):
            if os.environ.get(key):
                env[key] = os.environ[key]
        return env

    def _create_remediation_ecs(self) -> None:
        """Fargate cluster + npm task definition for the remediation worker.

        Fargate runs the clone/build/PR work that exceeds Lambda's limits. The
        image is built from the npm worker Dockerfile (a Lambda base image), so
        the container command is overridden to run ``main.py``, bypassing the
        Lambda runtime client.
        """
        if not self.vpc_stack:
            logger.warning("No VPC stack; skipping remediation Fargate cluster")
            return

        self.remediation_cluster = ecs.Cluster(
            self, "RemediationCluster",
            cluster_name=f"oscar-remediation-{self.env_name}",
            vpc=self.vpc_stack.vpc,
            container_insights=True,
        )

        # The task + execution roles live HERE, not permissions_stack, alongside
        # the task def and log group: the log driver auto-grants the execution
        # role write access to the log group, and a role in permissions_stack
        # would make that grant a permissions->lambda edge and cycle (lambda
        # already depends on permissions). Co-locating avoids it.
        task_role = iam.Role(
            self, "RemediationEcsTaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            description="Task role for the OSCAR CVE remediation Fargate worker",
        )
        # Read the GitHub + Slack tokens under the oscar-remediation-* prefix.
        task_role.add_to_policy(iam.PolicyStatement(
            actions=["secretsmanager:GetSecretValue"],
            resources=[
                f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:oscar-remediation-*"
            ],
        ))
        execution_role = iam.Role(
            self, "RemediationEcsExecutionRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy")
            ],
            description="Execution role for the OSCAR CVE remediation Fargate task",
        )

        task_def = ecs.FargateTaskDefinition(
            self, "RemediationNpmTaskDef",
            family=f"oscar-remediation-npm-{self.env_name}",
            cpu=2048,                 # 2 vCPU
            memory_limit_mib=8192,    # 8 GB (OSD install peaked ~4 GB; headroom)
            ephemeral_storage_gib=50,  # clone + node_modules + yarn cache; up to 200 for core
            # Match the image platform (arm64) — native Apple-Silicon builds,
            # cheaper Graviton, and consistent with the npm worker Lambda.
            runtime_platform=ecs.RuntimePlatform(
                cpu_architecture=ecs.CpuArchitecture.ARM64,
                operating_system_family=ecs.OperatingSystemFamily.LINUX,
            ),
            task_role=task_role,
            execution_role=execution_role,
        )

        task_def.add_container(
            "worker",
            container_name="worker",
            image=ecs.ContainerImage.from_asset(
                directory="agents/SecurityAdvisories/remediation-workers/npm",
                platform=ecr_assets.Platform.LINUX_ARM64,
            ),
            # Bypass the Lambda runtime client baked into the base image and run
            # the env-driven Fargate entrypoint directly. Files are under
            # /var/task (LAMBDA_TASK_ROOT); python is the base image's runtime.
            entry_point=["/var/lang/bin/python"],
            command=["/var/task/main.py"],
            environment=self._remediation_worker_env(),
            logging=ecs.LogDriver.aws_logs(
                stream_prefix="npm",
                log_group=logs.LogGroup(
                    self, "RemediationNpmLogGroup",
                    log_group_name=f"/ecs/oscar-remediation-npm-{self.env_name}",
                    retention=logs.RetentionDays.TWO_WEEKS,
                    removal_policy=RemovalPolicy.DESTROY,
                ),
            ),
        )
        self.remediation_npm_task_def = task_def

    def _wire_remediation_dispatch(self) -> None:
        """Point the SecurityAdvisories agent Lambda at the Fargate worker.

        Injects the ECS cluster, per-ecosystem task definition ARN, and the
        network config (public subnets + security group) so the remediation
        handler's dispatch step can ``run_task``. The RunTask/PassRole
        PERMISSIONS are granted as identity policies on the SA role (see
        iam_policies.py) using deterministic ARNs — granting them here via
        construct refs would add a lambda-stack ARN to the permissions-stack role
        and create a cyclic permissions<->lambda stack dependency.
        """
        if not (self.remediation_npm_task_def and self.remediation_cluster
                and self.vpc_stack):
            return
        sa_fn = self.lambda_functions.get("SecurityAdvisories")
        if not sa_fn:
            logger.warning(
                "SecurityAdvisories Lambda not found; remediation dispatch not wired"
            )
            return
        sa_fn.add_environment(
            "NPM_REMEDIATION_TASKDEF", self.remediation_npm_task_def.task_definition_arn
        )
        sa_fn.add_environment(
            "REMEDIATION_ECS_CLUSTER", self.remediation_cluster.cluster_name
        )
        sa_fn.add_environment(
            "REMEDIATION_ECS_SUBNETS",
            ",".join(s.subnet_id for s in self.vpc_stack.vpc.public_subnets),
        )
        sa_fn.add_environment(
            "REMEDIATION_ECS_SECURITY_GROUP",
            self.vpc_stack.lambda_security_group.security_group_id,
        )

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
                layers=[self.shared_layer],
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
        "ENABLE_DM", "ENABLE_2PR", "CONTEXT_TTL", "AGENT_TIMEOUT", "AGENT_MAX_RETRIES",
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
        "ENABLE_2PR", "CONTEXT_TTL", "BEDROCK_RESPONSE_MESSAGE_VERSION", "CHANNEL_MAPPINGS",
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
        if self.storage_stack.identity_table:
            env["ENVIRONMENT"] = self.env_name
            env["IDENTITY_TABLE_NAME"] = self.storage_stack.identity_table.table_name
            env["SLACK_WORKSPACE_ID"] = self.storage_stack.workspace_id
        return env

    def _get_communication_handler_environment_variables(self) -> Dict[str, str]:
        env = self._passthrough_env(self._COMM_HANDLER_ENV_KEYS)
        env.update({
            "CENTRAL_SECRET_NAME": self.secrets_stack.central_env_secret.secret_name,
            "CONTEXT_TABLE_NAME": self.storage_stack.context_table_name,
        })
        return env
