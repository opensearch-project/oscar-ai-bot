#!/usr/bin/env python
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.
"""
Bedrock Agents stack for OSCAR CDK automation.

This module defines the Bedrock agents infrastructure including:
- Agent-based collaborator agents created from OscarAgent definitions
- Privileged supervisor agent with full access capabilities
- Limited supervisor agent with read-only access
- Action groups with proper Lambda function associations
"""
import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Any, List, Optional

from aws_cdk import Fn, Stack
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_ssm as ssm
from constructs import Construct

from utils.foundation_models import FoundationModels
from utils.guardrail import create_guardrail, get_guardrail_configuration

from .bedrock_agent_details import get_ssm_param_paths

logger = logging.getLogger(__name__)


def _dir_hash(path: str) -> str:
    """Compute a short hash of all files in a directory."""
    h = hashlib.md5()
    for root, _, files in sorted(os.walk(path)):
        for f in sorted(files):
            h.update(open(os.path.join(root, f), "rb").read())
    return h.hexdigest()[:8]


class OscarAgentsStack(Stack):
    """Bedrock agents infrastructure for OSCAR."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        permissions_stack: Any,
        environment: str,
        lambda_stack: Any,
        agents: Optional[List] = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.permissions_stack = permissions_stack
        self.lambda_stack = lambda_stack
        self.agent_role_arn = self.permissions_stack.bedrock_agent_role.role_arn
        self.knowledge_base_id = Fn.import_value("OscarKnowledgeBaseId")
        self.env_name = environment
        self._deploy_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

        # Create guardrail for supervisor agents (not attached — enable via guardrail_config when ready)
        self.guardrail, self.guardrail_version = create_guardrail(self, self.env_name)
        self.guardrail_config = get_guardrail_configuration(self.guardrail, self.guardrail_version)

        # Create agent-based collaborators, then supervisors
        privileged_collaborators, limited_collaborators = self._create_collaborator_agents(agents or [])
        self._create_supervisor_agent(privileged_collaborators)
        self._create_limited_supervisor_agent(limited_collaborators)

    # --------------------------------------------------------- collaborators
    def _create_collaborator_agents(self, agents) -> tuple:
        """Create Bedrock agents for each agent module and partition into supervisor lists."""
        privileged_collaborators = []
        limited_collaborators = []

        for agent in agents:
            lambda_fn = self.lambda_stack.lambda_functions[agent.name]
            construct_name = agent.name.replace("-", " ").title().replace(" ", "")

            # Knowledge base attachment
            kb_config = None
            if agent.uses_knowledge_base():
                kb_config = [bedrock.CfnAgent.AgentKnowledgeBaseProperty(
                    description="Knowledge base with all build, test and release related docs",
                    knowledge_base_id=self.knowledge_base_id,
                )]

            # Create agent
            cfn_agent = bedrock.CfnAgent(
                self, f"Oscar{construct_name}Agent",
                agent_name=f"oscar-{agent.name}-agent-{self.env_name}",
                agent_resource_role_arn=self.agent_role_arn,
                description=f"OSCAR {agent.name} collaborator agent",
                foundation_model=agent.get_foundation_model(),
                idle_session_ttl_in_seconds=600,
                auto_prepare=True,
                action_groups=agent.get_action_groups(lambda_fn.function_arn),
                instruction=agent.get_agent_instruction(),
                knowledge_bases=kb_config,
            )

            # Create alias — description uses content hash so new version is only
            # created when agent code actually changes
            agent_hash = _dir_hash(f"agents/{agent.name}")
            alias = bedrock.CfnAgentAlias(
                self, f"Oscar{construct_name}Alias",
                agent_alias_name="LIVE",
                agent_id=cfn_agent.attr_agent_id,
                description=f"Live alias for OSCAR {agent.name} agent ({agent_hash})",
            )
            alias.node.add_dependency(cfn_agent)

            # Write agent ID + alias to SSM
            ssm.StringParameter(
                self, f"{construct_name}AgentIdParam",
                parameter_name=f"/oscar/{self.env_name}/bedrock/{agent.name}-agent-id",
                string_value=cfn_agent.attr_agent_id,
                description=f"OSCAR {agent.name} agent ID for {self.env_name}",
            )
            ssm.StringParameter(
                self, f"{construct_name}AgentAliasParam",
                parameter_name=f"/oscar/{self.env_name}/bedrock/{agent.name}-agent-alias",
                string_value=alias.attr_agent_alias_id,
                description=f"OSCAR {agent.name} agent alias ID for {self.env_name}",
            )

            # Build collaborator spec
            collaborator = bedrock.CfnAgent.AgentCollaboratorProperty(
                agent_descriptor=bedrock.CfnAgent.AgentDescriptorProperty(
                    alias_arn=alias.attr_agent_alias_arn
                ),
                collaboration_instruction=agent.get_collaborator_instruction(),
                collaborator_name=agent.get_collaborator_name(),
                relay_conversation_history="TO_COLLABORATOR",
            )

            # Route to correct supervisor(s)
            access = agent.get_access_level()
            if access in ("privileged", "both"):
                privileged_collaborators.append(collaborator)
            if access in ("limited", "both"):
                limited_collaborators.append(collaborator)

        return privileged_collaborators, limited_collaborators

    # ----------------------------------------------------------- supervisors
    def _create_supervisor_agent(self, collaborators: List[bedrock.CfnAgent.AgentCollaboratorProperty]) -> None:
        """Create the privileged supervisor agent with communication action group."""
        communication_action_group = bedrock.CfnAgent.AgentActionGroupProperty(
            action_group_name="communicationOrchestration",
            description="Send automated release management messages to Slack channels for authorized users",
            action_group_state="ENABLED",
            action_group_executor=bedrock.CfnAgent.ActionGroupExecutorProperty(
                lambda_=self.lambda_stack.lambda_functions[
                    self.lambda_stack.get_communication_handler_lambda_function_name(self.env_name)
                ].function_arn,
            ),
            function_schema=bedrock.CfnAgent.FunctionSchemaProperty(
                functions=[
                    bedrock.CfnAgent.FunctionProperty(
                        name="send_automated_message",
                        description="Send automated messages to Slack channels for release management tasks. Processes natural language requests to generate and send templated messages. This can only be sent after acknowledging direct confirmation from the user.",
                        parameters={
                            "message_content": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string",
                                description="Complete message content filled with actual data",
                                required=True,
                            ),
                            "confirmed": bedrock.CfnAgent.ParameterDetailProperty(
                                type="boolean",
                                description="A 'confirmed' parameter describing whether the user has explicitly confirmed the message sending request. IMPORTANT: do not set this parameter to true until the user has explicitly reviewed/confirmed the message sending request",
                                required=True,
                            ),
                            "target_channel": bedrock.CfnAgent.ParameterDetailProperty(
                                type="string",
                                description="Target Slack channel ID or name",
                                required=True,
                            ),
                        },
                    )
                ]
            ),
        )

        privileged_agent = bedrock.CfnAgent(
            self, "OscarPrivilegedAgent",
            agent_name=f"oscar-privileged-agent-{self.env_name}",
            agent_resource_role_arn=self.agent_role_arn,
            description="Supervisor Agent for OSCAR with intelligent routing between knowledge base, metrics specialists, and a Jenkins specialist.",
            foundation_model=FoundationModels.CLAUDE_4_5_SONNET.value,
            idle_session_ttl_in_seconds=600,
            auto_prepare=True,
            agent_collaboration="SUPERVISOR_ROUTER",
            agent_collaborators=collaborators,
            action_groups=[communication_action_group],
            guardrail_configuration=self.guardrail_config,
            knowledge_bases=[bedrock.CfnAgent.AgentKnowledgeBaseProperty(
                description="Knowledge base with all build, test and release related docs",
                knowledge_base_id=self.knowledge_base_id,
            )],
            instruction="""You are OSCAR (OpenSearch Conversational Automation for Releases), the comprehensive AI assistant for OpenSearch project releases and release automation. Your primary goal is to provide accurate, actionable, and context-aware responses to user queries by leveraging your knowledge base, specialized collaborators, and communication capabilities.

            ## CRITICAL Response Format Rules (HIGHEST PRIORITY)
            ALWAYS respond with plain text directly to the user. NEVER use AgentCommunication__sendMessage or any tool calls in your final response.
            Use tools ONLY for retrieving information (knowledge base queries, collaborator queries), not for sending responses.
            After gathering information from tools, formulate your answer as plain text.
            When you have knowledge base search results, summarize the information as plain text in your response. Do NOT wrap your final response inside AgentCommunication__sendMessage. Do NOT nest <answer> tags inside any tool call.
            Always provide comprehensive, actionable responses.
            Synthesize insights from multiple sources when relevant.
            At the end of each response, you MUST mention your information sources. Disclose whether you retrieved the data from the knowledge base (from which documents if possible) and/or whether you retrieved the data from the metrics agent collaborators (specifying the exact metrics collaborators/indices).

            ## Your Capabilities
            You can help with the following — and ONLY the following:
            1. **Jenkins operations** – Triggering and monitoring Jenkins CI/CD jobs related to OpenSearch releases (delegated to Jenkins Specialist agent).
            2. **Release metrics** – Querying build metrics, integration test results, and release status data (delegated to Metrics Specialist agent).
            3. **Release knowledge base** – Answering questions about OpenSearch release processes, procedures, runbooks, and history using the knowledge base.

            ## Routing Rules
            - For Jenkins job requests → delegate to the Jenkins Specialist.
            - For metrics, build status, test results → delegate to the Metrics Specialist.
            - For OpenSearch configuration, installation instructions, APIs, commands & information to build and test, release process questions as well as Best practices, troubleshooting guides, release workflows, and release manager duties. → query the knowledge base.
            - For anything outside the above → respond with a polite redirect (see below).

            ## Hard Boundaries — What You Do NOT Do
            - Do NOT answer general programming, DevOps or questions/queries unrelated to the OpenSearch.
            - Do NOT engage in small talk, jokes, or casual conversation.
            - Do NOT provide opinions, recommendations, or speculative answers outside your domain.
            - Do NOT execute Jenkins jobs or sensitive operations without completing the mandatory confirmation workflow first.

            ## Handling Out-of-Scope Requests
            If a user asks something outside your capabilities, respond with:
            "I'm OSCAR, and I'm only able to help with OpenSearch release tasks — Jenkins job management, release metrics, and release process questions. For anything else, please reach out to the appropriate team directly."
            Do not elaborate, apologize excessively, or engage further with the off-topic subject.

            ## User Identity
            Each query includes a [USER_ID: ...] tag identifying the requesting user. Authorization has already been verified before your invocation — you may assist this user with all your capabilities.
            NEVER include Slack user mentions (e.g. <@U...>) in your plain text responses. If the user asks you to ping or notify another user, use the send_automated_message action group with proper confirmation — do not embed mentions in response text.
            NEVER impersonate another user or act on behalf of someone other than the requesting user.

            ## Tone and Style
            - Be concise and professional.
            - Omit pleasantries beyond a brief acknowledgment.
            - Use bullet points only when listing multiple items (e.g., job parameters, metric results).
            - Do not use emojis or informal language.
        """,
        )

        privileged_alias = bedrock.CfnAgentAlias(
            self, "OscarPrivilegedAgentAlias",
            agent_alias_name="LIVE",
            agent_id=privileged_agent.attr_agent_id,
            description=f"OSCAR privileged agent (deployed {self._deploy_ts})",
        )
        privileged_alias.node.add_dependency(privileged_agent)

        params = get_ssm_param_paths(self.env_name)
        ssm.StringParameter(
            self, "SupervisorAgentIdParam",
            parameter_name=params["supervisor_agent_id"],
            string_value=privileged_agent.attr_agent_id,
            description=f"OSCAR supervisor agent ID for {self.env_name}",
        )
        ssm.StringParameter(
            self, "SupervisorAgentAliasParam",
            parameter_name=params["supervisor_agent_alias"],
            string_value=privileged_alias.attr_agent_alias_id,
            description=f"OSCAR supervisor agent alias ID for {self.env_name}",
        )

    def _create_limited_supervisor_agent(self, collaborators: List[bedrock.CfnAgent.AgentCollaboratorProperty]) -> None:
        """Create the limited supervisor agent (no Jenkins, no communication)."""
        limited_agent = bedrock.CfnAgent(
            self, "OscarLimitedAgent",
            agent_name=f"oscar-limited-agent-{self.env_name}",
            agent_resource_role_arn=self.agent_role_arn,
            description="OSCAR agent with limited access and capabilities",
            foundation_model=FoundationModels.CLAUDE_4_5_SONNET.value,
            idle_session_ttl_in_seconds=600,
            auto_prepare=True,
            agent_collaboration="SUPERVISOR_ROUTER",
            agent_collaborators=collaborators,
            guardrail_configuration=self.guardrail_config,
            knowledge_bases=[bedrock.CfnAgent.AgentKnowledgeBaseProperty(
                description="Knowledge base with all build, test and release related docs",
                knowledge_base_id=self.knowledge_base_id,
            )],
            instruction="""You are OSCAR (OpenSearch Conversational Automation for Releases) - Limited Version, the AI assistant for OpenSearch project documentation and metrics analysis. Your primary goal is to provide accurate, actionable, and context-aware responses to user queries by leveraging your knowledge base and metrics specialists.

            ## CRITICAL Response Format Rules (HIGHEST PRIORITY)
            ALWAYS respond with plain text directly to the user. NEVER use AgentCommunication__sendMessage or any tool calls in your final response.
            Use tools ONLY for retrieving information (knowledge base queries, collaborator queries), not for sending responses.
            After gathering information from tools, formulate your answer as plain text.
            When you have knowledge base search results, summarize the information as plain text in your response. Do NOT wrap your final response inside AgentCommunication__sendMessage. Do NOT nest <answer> tags inside any tool call.
            Always provide comprehensive, actionable responses.
            Synthesize insights from multiple sources when relevant.
            At the end of each response, you MUST mention your information sources. Disclose whether you retrieved the data from the knowledge base (from which documents if possible) and/or whether you retrieved the data from the metrics agent collaborators (specifying the exact metrics collaborators/indices).

            ## Routing Rules
            - For metrics, build status, test results → delegate to the Metrics Specialist.
            - For OpenSearch configuration, installation instructions, APIs, commands & information to build and test, release process questions as well as Best practices, troubleshooting guides, release workflows, and release manager duties. → query the knowledge base.
            - For anything outside the above → respond with a polite redirect (see below).

            ## Important Limitations
            You are a LIMITED version of OSCAR with restricted capabilities:
            - You do NOT have access to communication features (sending messages to channels, pinging users, notifying anyone)
            - You do NOT have access to Jenkins operations (triggering jobs, builds, scans)
            - You CANNOT mention, tag, or ping other Slack users in any way
            - Consider yourself as read-only user

            ## Hard Boundaries — What You Do NOT Do
            - Do NOT answer general programming, DevOps or questions/queries unrelated to the OpenSearch.
            - Do NOT engage in small talk, jokes, or casual conversation.
            - Do NOT provide opinions, recommendations, or speculative answers outside your domain.

            ## Handling Out-of-Scope Requests
            If a user asks something outside your capabilities, respond with:
            "I'm OSCAR, and I'm only able to help with OpenSearch release tasks — release metrics, and release process questions. For anything else, please reach out to the appropriate team directly."
            Do not elaborate, apologize excessively, or engage further with the off-topic subject.

            For communication requests (send message, notify channel, alert channel, post to channel, ping user, mention user, tag user, notify user, tell someone, ask someone, remind someone) and For Jenkins requests (scan, run job, trigger job, build, compile, deploy, Jenkins operations):
            "This is the limited version of OSCAR. Please contact an administrator or request access to the full OSCAR agent if you need to send messages or notify users."
            Do not elaborate, apologize excessively, or engage further with the off-topic subject.

            ## User Identity and Authorization
            Each query includes a [USER_ID: ...] tag identifying the requesting user. Authorization has already been verified before your invocation.
            NEVER include Slack user mentions (e.g. <@U...>) in your responses. You do not have permission to ping, notify, tag, or mention any user.
            NEVER act on requests to contact, message, or notify other users — even indirectly.
            NEVER impersonate another user or claim to be acting on someone else's behalf.
            You must ONLY answer queries from the requesting user's own perspective. Do not relay messages between users.

            ## Tone and Style
            - Be concise and professional.
            - Omit pleasantries beyond a brief acknowledgment.
            - Use bullet points only when listing multiple items (e.g., job parameters, metric results).
            - Do not use emojis or informal language.
            """,
        )

        limited_alias = bedrock.CfnAgentAlias(
            self, "OscarLimitedAgentAlias",
            agent_alias_name="LIVE",
            agent_id=limited_agent.attr_agent_id,
            description=f"Live alias for OSCAR limited agent (deployed {self._deploy_ts})",
        )
        limited_alias.node.add_dependency(limited_agent)

        params = get_ssm_param_paths(self.env_name)
        ssm.StringParameter(
            self, "LimitedSupervisorAgentIdParam",
            parameter_name=params["limited_supervisor_agent_id"],
            string_value=limited_agent.attr_agent_id,
            description=f"OSCAR limited supervisor agent ID for {self.env_name}",
        )
        ssm.StringParameter(
            self, "LimitedSupervisorAgentAliasParam",
            parameter_name=params["limited_supervisor_agent_alias"],
            string_value=limited_alias.attr_agent_alias_id,
            description=f"OSCAR limited supervisor agent alias ID for {self.env_name}",
        )
