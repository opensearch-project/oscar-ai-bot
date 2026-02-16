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
- Plugin-based collaborator agents created from OscarPlugin definitions
- Privileged supervisor agent with full access capabilities
- Limited supervisor agent with read-only access
- Action groups with proper Lambda function associations
"""
import logging
from typing import Any, List, Optional

from aws_cdk import Fn, Stack
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_ssm as ssm
from constructs import Construct

from utils.foundation_models import FoundationModels

from .bedrock_agent_details import get_ssm_param_paths

logger = logging.getLogger(__name__)


class OscarAgentsStack(Stack):
    """Bedrock agents infrastructure for OSCAR."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        permissions_stack: Any,
        environment: str,
        lambda_stack: Any,
        plugins: Optional[List] = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.permissions_stack = permissions_stack
        self.lambda_stack = lambda_stack
        self.agent_role_arn = self.permissions_stack.bedrock_agent_role.role_arn
        self.knowledge_base_id = Fn.import_value("OscarKnowledgeBaseId")
        self.env_name = environment

        # Create plugin collaborator agents, then supervisors
        privileged_collaborators, limited_collaborators = self._create_plugin_agents(plugins or [])
        self._create_supervisor_agent(privileged_collaborators)
        self._create_limited_supervisor_agent(limited_collaborators)

    # --------------------------------------------------------------- plugins
    def _create_plugin_agents(self, plugins) -> tuple:
        """Create Bedrock agents for each plugin and partition into supervisor lists."""
        privileged_collaborators = []
        limited_collaborators = []

        for plugin in plugins:
            lambda_fn = self.lambda_stack.lambda_functions[plugin.name]
            construct_name = plugin.name.replace("-", " ").title().replace(" ", "")

            # Knowledge base attachment
            kb_config = None
            if plugin.uses_knowledge_base():
                kb_config = [bedrock.CfnAgent.AgentKnowledgeBaseProperty(
                    description="Knowledge base with all build, test and release related docs",
                    knowledge_base_id=self.knowledge_base_id,
                )]

            # Create agent
            agent = bedrock.CfnAgent(
                self, f"Oscar{construct_name}Agent",
                agent_name=f"oscar-{plugin.name}-agent-{self.env_name}",
                agent_resource_role_arn=self.agent_role_arn,
                description=f"OSCAR {plugin.name} collaborator agent",
                foundation_model=plugin.get_foundation_model(),
                idle_session_ttl_in_seconds=600,
                auto_prepare=True,
                action_groups=plugin.get_action_groups(lambda_fn.function_arn),
                instruction=plugin.get_agent_instruction(),
                knowledge_bases=kb_config,
            )

            # Create alias
            alias = bedrock.CfnAgentAlias(
                self, f"Oscar{construct_name}Alias",
                agent_alias_name="LIVE",
                agent_id=agent.attr_agent_id,
                description=f"Live alias for OSCAR {plugin.name} agent",
            )
            alias.node.add_dependency(agent)

            # Write agent ID + alias to SSM
            ssm.StringParameter(
                self, f"{construct_name}AgentIdParam",
                parameter_name=f"/oscar/{self.env_name}/bedrock/{plugin.name}-agent-id",
                string_value=agent.attr_agent_id,
                description=f"OSCAR {plugin.name} agent ID for {self.env_name}",
            )
            ssm.StringParameter(
                self, f"{construct_name}AgentAliasParam",
                parameter_name=f"/oscar/{self.env_name}/bedrock/{plugin.name}-agent-alias",
                string_value=alias.attr_agent_alias_id,
                description=f"OSCAR {plugin.name} agent alias ID for {self.env_name}",
            )

            # Build collaborator spec
            collaborator = bedrock.CfnAgent.AgentCollaboratorProperty(
                agent_descriptor=bedrock.CfnAgent.AgentDescriptorProperty(
                    alias_arn=alias.attr_agent_alias_arn
                ),
                collaboration_instruction=plugin.get_collaborator_instruction(),
                collaborator_name=plugin.get_collaborator_name(),
                relay_conversation_history="TO_COLLABORATOR",
            )

            # Route to correct supervisor(s)
            access = plugin.get_access_level()
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
            knowledge_bases=[bedrock.CfnAgent.AgentKnowledgeBaseProperty(
                description="Knowledge base with all build, test and release related docs",
                knowledge_base_id=self.knowledge_base_id,
            )],
            instruction="""You are OSCAR (OpenSearch Conversational Automation for Releases), the comprehensive AI assistant for OpenSearch project releases and release automation. Your primary goal is to provide accurate, actionable, and context-aware responses to user queries by leveraging your knowledge base, specialized collaborators, and communication capabilities.

            INTELLIGENT ROUTING CAPABILITIES
            DOCUMENTATION QUERIES → Knowledge Base
            OpenSearch configuration, installation instructions, APIs, commands & information to build and test, and implementation-level code.
            Best practices, troubleshooting guides, release workflows, and release manager duties.
            Feature explanations, templates, and tutorials.
            Static information and how-to questions.

            OVERALL RESPONSE GUIDELINES
            CRITICAL: Always respond with plain text directly to the user. NEVER use AgentCommunication__sendMessage or any tool calls in your final response.
            Use tools ONLY for retrieving information (knowledge base queries, collaborator queries), not for sending responses.
            After gathering information from tools, formulate your answer as plain text.
            Always provide comprehensive, actionable responses.
            Synthesize insights from multiple sources when relevant.
            At the end of each response, you MUST mention your information sources. Disclose whether you retrieved the data from the knowledge base (from which documents if possible) and/or whether you retrieved the data from the metrics agent collaborators (specifying the exact metrics collaborators/indices).
        """,
        )

        privileged_alias = bedrock.CfnAgentAlias(
            self, "OscarPrivilegedAgentAlias",
            agent_alias_name="LIVE",
            agent_id=privileged_agent.attr_agent_id,
            description="Live alias for OSCAR privileged agent",
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
            knowledge_bases=[bedrock.CfnAgent.AgentKnowledgeBaseProperty(
                description="Knowledge base with all build, test and release related docs",
                knowledge_base_id=self.knowledge_base_id,
            )],
            instruction="""You are OSCAR (OpenSearch Conversational Automation for Releases) - Limited Version, the AI assistant for OpenSearch project documentation and metrics analysis. Your primary goal is to provide accurate, actionable, and context-aware responses to user queries by leveraging your knowledge base and metrics specialists.

            IMPORTANT LIMITATIONS:
            You are a LIMITED version of OSCAR with restricted capabilities:
            - You do NOT have access to communication features (sending messages to channels)
            - You do NOT have access to Jenkins operations (triggering jobs, builds, scans)

            If users ask about communication or Jenkins features, respond with:
            "I don't have access to [communication/Jenkins] features. This is the limited version of OSCAR. Please contact an administrator or request access to the full OSCAR agent if you need these capabilities."

            INTELLIGENT ROUTING CAPABILITIES
            DOCUMENTATION QUERIES → Knowledge Base
            OpenSearch configuration, installation, APIs, build commands & information, and implementation-level code.
            Best practices, troubleshooting guides, release workflows, and release manager duties.
            Feature explanations, templates, and tutorials.
            Static information and how-to questions.

            RESTRICTED FUNCTIONALITY RESPONSES:
            For communication requests (send message, notify channel, alert channel, post to channel):
            "I don't have access to communication features. This is the limited version of OSCAR. Please contact an administrator or request access to the full OSCAR agent if you need to send messages to channels."

            For Jenkins requests (scan, run job, trigger job, build, compile, deploy, Jenkins operations):
            "I don't have access to Jenkins operations. This is the limited version of OSCAR. Please contact an administrator or request access to the full OSCAR agent if you need to execute Jenkins jobs or builds."

            OVERALL RESPONSE GUIDELINES
            CRITICAL: Always respond with plain text directly to the user. NEVER use AgentCommunication__sendMessage or any tool calls in your final response.
            Use tools ONLY for retrieving information (knowledge base queries, collaborator queries), not for sending responses.
            After gathering information from tools, formulate your answer as plain text.
            Always provide comprehensive, actionable responses.
            Synthesize insights from multiple sources when relevant.
            At the end of each response, you MUST mention your information sources. Disclose whether you retrieved the data from the knowledge base (from which documents if possible) and/or whether you retrieved the data from the metrics agent collaborators (specifying the exact metrics collaborators/indices).
            """,
        )

        limited_alias = bedrock.CfnAgentAlias(
            self, "OscarLimitedAgentAlias",
            agent_alias_name="LIVE",
            agent_id=limited_agent.attr_agent_id,
            description="Live alias for OSCAR limited agent",
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
