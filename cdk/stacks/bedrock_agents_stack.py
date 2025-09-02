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
- Privileged agent with full access capabilities and Claude 3.5 Sonnet
- Limited agent with read-only access and Claude 3.5 Sonnet
- Action groups for communication orchestration, metrics analysis, and Jenkins operations
- Knowledge Base associations and retrieval settings
- Collaborator agent configurations
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from aws_cdk import (
    Stack,
    Duration,
    aws_bedrock as bedrock,
    aws_iam as iam,
    aws_lambda as lambda_,
    CfnOutput
)
from constructs import Construct

# Configure logging
logger = logging.getLogger(__name__)

# Import utilities
try:
    from utils.agent_config_builder import AgentConfigBuilder, AgentConfig
    from utils.agent_config_validator import AgentConfigValidator
except ImportError as e:
    # Fallback for when utilities are not available
    logger.error(f"Failed to import utilities: {e}")
    AgentConfigBuilder = None
    AgentConfigValidator = None
    AgentConfig = None


class OscarAgentsStack(Stack):
    """
    Bedrock agents infrastructure for OSCAR.
    
    This construct creates and configures Bedrock agents including:
    - Privileged agent with full access capabilities
    - Limited agent with read-only access
    - Action groups for various operations
    - Knowledge Base associations
    - Collaborator configurations
    """
    
    def __init__(
        self, 
        scope: Construct, 
        construct_id: str,
        permissions_stack: Any,
        knowledge_base_stack: Any,
        lambda_stack: Any,
        **kwargs
    ) -> None:
        """
        Initialize Bedrock agents stack.
        
        Args:
            scope: The CDK construct scope
            construct_id: The ID of the construct
            permissions_stack: The permissions stack with IAM roles
            knowledge_base_stack: The knowledge base stack
            lambda_stack: The Lambda functions stack
            **kwargs: Additional keyword arguments
        """
        super().__init__(scope, construct_id, **kwargs)
        
        # Store references to other stacks
        self.permissions_stack = permissions_stack
        self.knowledge_base_stack = knowledge_base_stack
        self.lambda_stack = lambda_stack
        
        # Get configuration from environment
        self.account_id = os.environ.get("CDK_DEFAULT_ACCOUNT")
        self.aws_region = os.environ.get("CDK_DEFAULT_REGION", "us-east-1")
        self.env_name = os.environ.get("ENVIRONMENT", "dev")
        
        # Initialize configuration utilities
        if AgentConfigBuilder is None:
            logger.error("AgentConfigBuilder is not available - skipping agent creation")
            self.config_builder = None
            self.config_validator = None
        else:
            self.config_builder = AgentConfigBuilder()
            self.config_validator = AgentConfigValidator() if AgentConfigValidator else None
        
        # Dictionary to store created agents
        self.agents: Dict[str, bedrock.CfnAgent] = {}
        self.agent_aliases: Dict[str, bedrock.CfnAgentAlias] = {}
        
        # Create agents from configuration files
        self._create_agents_from_configs()
        
        # Create outputs
        self._create_outputs()
    
    def _create_agents_from_configs(self) -> None:
        """
        Create Bedrock agents from JSON configuration files.
        """
        logger.info("Creating Bedrock agents from configuration files")
        
        # Define agent configurations to deploy
        agent_configs = [
            {
                "config_file": "oscar-privileged-agent-current.json",
                "agent_key": "privileged",
                "description": "Privileged OSCAR agent with full access capabilities"
            },
            {
                "config_file": "oscar-limited-agent-current.json", 
                "agent_key": "limited",
                "description": "Limited OSCAR agent with read-only access"
            }
        ]
        
        for config_info in agent_configs:
            try:
                self._create_agent_from_config(
                    config_info["config_file"],
                    config_info["agent_key"],
                    config_info["description"]
                )
            except Exception as e:
                logger.error(f"Failed to create agent from {config_info['config_file']}: {e}")
                # Continue with other agents even if one fails
                continue
    
    def _create_agent_from_config(self, config_file: str, agent_key: str, description: str) -> None:
        """
        Create a Bedrock agent from a configuration file.
        
        Args:
            config_file: Name of the configuration file
            agent_key: Key to store the agent in the agents dictionary
            description: Description for the agent
        """
        logger.info(f"Creating agent from configuration: {config_file}")
        
        try:
            # Load agent configuration
            agent_config = self.config_builder.load_agent_config(config_file)
            
            # Validate configuration
            validation_result = self.config_validator.validate_agent_config(agent_config)
            if validation_result.has_errors:
                logger.error(f"Configuration validation failed for {config_file}")
                for error in validation_result.errors:
                    logger.error(f"  {error}")
                return
            
            if validation_result.warnings:
                for warning in validation_result.warnings:
                    logger.warning(f"  {warning}")
            
            # Update Lambda function ARNs with current deployment
            self._update_lambda_arns_in_config(agent_config)
            
            # Update Knowledge Base ID with current deployment
            self._update_knowledge_base_id_in_config(agent_config)
            
            # Create the agent
            agent = self._create_bedrock_agent(agent_config, agent_key)
            
            # Create agent alias
            alias = self._create_agent_alias(agent, agent_config, agent_key)
            
            # Store references
            self.agents[agent_key] = agent
            self.agent_aliases[agent_key] = alias
            
            logger.info(f"Successfully created agent: {agent_config.agent_name}")
            
        except FileNotFoundError:
            logger.error(f"Configuration file not found: {config_file}")
        except Exception as e:
            logger.error(f"Error creating agent from {config_file}: {e}")
            raise
    
    def _update_lambda_arns_in_config(self, agent_config: AgentConfig) -> None:
        """
        Update Lambda function ARNs in agent configuration with current deployment.
        
        Args:
            agent_config: Agent configuration to update
        """
        # Mapping of action group names to Lambda function keys
        lambda_function_mapping = {
            "communication-orchestration": "communication_handler",
            "oscar-enhanced-routing-v2": "main_agent",
            "jenkins-operations": "jenkins_agent",
            "metrics-analysis": "metrics_test_metrics"  # Default to test metrics
        }
        
        for action_group in agent_config.action_groups:
            if action_group.name in lambda_function_mapping:
                function_key = lambda_function_mapping[action_group.name]
                
                # Get Lambda function from the Lambda stack
                if function_key in self.lambda_stack.lambda_functions:
                    lambda_function = self.lambda_stack.lambda_functions[function_key]
                    action_group.lambda_function_arn = lambda_function.function_arn
                    logger.info(f"Updated Lambda ARN for action group {action_group.name}: {lambda_function.function_arn}")
                else:
                    logger.warning(f"Lambda function not found for action group {action_group.name}: {function_key}")
    
    def _update_knowledge_base_id_in_config(self, agent_config: AgentConfig) -> None:
        """
        Update Knowledge Base ID in agent configuration with current deployment.
        
        Args:
            agent_config: Agent configuration to update
        """
        if agent_config.knowledge_bases and self.knowledge_base_stack:
            for kb_config in agent_config.knowledge_bases:
                # Update with the current Knowledge Base ID
                kb_config.knowledge_base_id = self.knowledge_base_stack.knowledge_base.attr_knowledge_base_id
                logger.info(f"Updated Knowledge Base ID: {kb_config.knowledge_base_id}")
    
    def _create_bedrock_agent(self, agent_config: AgentConfig, agent_key: str) -> bedrock.CfnAgent:
        """
        Create a Bedrock agent from configuration.
        
        Args:
            agent_config: Agent configuration
            agent_key: Key for the agent
            
        Returns:
            Created Bedrock agent
        """
        logger.info(f"Creating Bedrock agent: {agent_config.agent_name}")
        
        # Get the Bedrock agent execution role
        agent_role = self.permissions_stack.bedrock_agent_role
        
        # Prepare agent properties
        agent_props = {
            "agent_name": f"{agent_config.agent_name}-cdk-created-{self.env_name}",
            "description": agent_config.description,
            "instruction": agent_config.instructions,
            "foundation_model": self._get_foundation_model_arn(agent_config.foundation_model),
            "agent_resource_role_arn": agent_role.role_arn,
            "idle_session_ttl_in_seconds": agent_config.idle_session_ttl_in_seconds
        }
        
        # Add customer encryption key if specified
        if agent_config.customer_encryption_key_arn:
            agent_props["customer_encryption_key_arn"] = agent_config.customer_encryption_key_arn
        
        # Add guardrails if configured
        if agent_config.guardrails:
            agent_props["guardrail_configuration"] = bedrock.CfnAgent.GuardrailConfigurationProperty(
                guardrail_identifier=agent_config.guardrails.guardrail_identifier,
                guardrail_version=agent_config.guardrails.guardrail_version
            )
        
        # Create the agent
        agent = bedrock.CfnAgent(
            self, f"BedrockAgent{agent_key.title()}",
            **agent_props
        )
        
        # Add tags
        if agent_config.tags:
            for key, value in agent_config.tags.items():
                agent.add_property_override(f"Tags.{key}", value)
        
        # Add default tags
        agent.add_property_override("Tags.Project", "OSCAR")
        agent.add_property_override("Tags.Environment", self.env_name)
        agent.add_property_override("Tags.AgentType", agent_key)
        
        return agent
    
    def _create_agent_alias(self, agent: bedrock.CfnAgent, agent_config: AgentConfig, agent_key: str) -> bedrock.CfnAgentAlias:
        """
        Create an agent alias for the Bedrock agent.
        
        Args:
            agent: The Bedrock agent
            agent_config: Agent configuration
            agent_key: Key for the agent
            
        Returns:
            Created agent alias
        """
        logger.info(f"Creating agent alias for: {agent_config.agent_name}")
        
        alias = bedrock.CfnAgentAlias(
            self, f"BedrockAgentAlias{agent_key.title()}",
            agent_alias_name=f"{agent_config.agent_name}-alias-cdk-created-{self.env_name}",
            agent_id=agent.attr_agent_id,
            description=f"Primary alias for {agent_config.agent_name}",
            routing_configuration=[
                bedrock.CfnAgentAlias.AgentAliasRoutingConfigurationListItemProperty(
                    agent_version="DRAFT"
                )
            ]
        )
        
        # Add dependency on agent
        alias.add_dependency(agent)
        
        return alias
    
    def _get_foundation_model_arn(self, foundation_model: str) -> str:
        """
        Get the full ARN for a foundation model.
        
        Args:
            foundation_model: Foundation model identifier
            
        Returns:
            Full ARN for the foundation model
        """
        # If it's already a full ARN (inference profile), return as-is
        if foundation_model.startswith("arn:aws:bedrock:"):
            return foundation_model
        
        # Convert model ID to ARN
        return f"arn:aws:bedrock:{self.aws_region}::foundation-model/{foundation_model}"
    
    def _create_action_groups_for_agent(self, agent: bedrock.CfnAgent, agent_config: AgentConfig, agent_key: str) -> None:
        """
        Create action groups for a Bedrock agent.
        
        Args:
            agent: The Bedrock agent
            agent_config: Agent configuration
            agent_key: Key for the agent
        """
        logger.info(f"Creating action groups for agent: {agent_config.agent_name}")
        
        for i, action_group_config in enumerate(agent_config.action_groups):
            try:
                # Prepare action group properties
                action_group_props = {
                    "agent_id": agent.attr_agent_id,
                    "agent_version": "DRAFT",
                    "action_group_name": action_group_config.name,
                    "description": action_group_config.description,
                    "action_group_state": action_group_config.action_group_state
                }
                
                # Add Lambda function executor
                if action_group_config.lambda_function_arn:
                    action_group_props["action_group_executor"] = bedrock.CfnAgentActionGroup.ActionGroupExecutorProperty(
                        lambda_=action_group_config.lambda_function_arn
                    )
                
                # Add API schema if available
                if action_group_config.api_schema and isinstance(action_group_config.api_schema, dict):
                    # Check if it's a valid OpenAPI schema
                    if "openAPIVersion" in action_group_config.api_schema:
                        action_group_props["api_schema"] = bedrock.CfnAgentActionGroup.APISchemaProperty(
                            payload=json.dumps(action_group_config.api_schema)
                        )
                
                # Create action group
                action_group = bedrock.CfnAgentActionGroup(
                    self, f"ActionGroup{agent_key.title()}{i}",
                    **action_group_props
                )
                
                # Add dependency on agent
                action_group.add_dependency(agent)
                
                logger.info(f"Created action group: {action_group_config.name}")
                
            except Exception as e:
                logger.error(f"Failed to create action group {action_group_config.name}: {e}")
                continue
    
    def _create_knowledge_base_associations_for_agent(self, agent: bedrock.CfnAgent, agent_config: AgentConfig, agent_key: str) -> None:
        """
        Create knowledge base associations for a Bedrock agent.
        
        Args:
            agent: The Bedrock agent
            agent_config: Agent configuration
            agent_key: Key for the agent
        """
        logger.info(f"Creating knowledge base associations for agent: {agent_config.agent_name}")
        
        for i, kb_config in enumerate(agent_config.knowledge_bases):
            try:
                # Create knowledge base association
                kb_association = bedrock.CfnAgentKnowledgeBase(
                    self, f"KnowledgeBaseAssociation{agent_key.title()}{i}",
                    agent_id=agent.attr_agent_id,
                    agent_version="DRAFT",
                    knowledge_base_id=kb_config.knowledge_base_id,
                    description=kb_config.description or f"Knowledge base association for {agent_config.agent_name}",
                    knowledge_base_state=kb_config.knowledge_base_state,
                    retrieval_configuration=bedrock.CfnAgentKnowledgeBase.KnowledgeBaseRetrievalConfigurationProperty(
                        vector_search_configuration=bedrock.CfnAgentKnowledgeBase.KnowledgeBaseVectorSearchConfigurationProperty(
                            number_of_results=kb_config.retrieval_configuration.get("vectorSearchConfiguration", {}).get("numberOfResults", 10),
                            override_search_type=kb_config.retrieval_configuration.get("vectorSearchConfiguration", {}).get("overrideSearchType", "HYBRID")
                        )
                    ) if kb_config.retrieval_configuration else None
                )
                
                # Add dependencies
                kb_association.add_dependency(agent)
                if self.knowledge_base_stack:
                    kb_association.add_dependency(self.knowledge_base_stack.knowledge_base)
                
                logger.info(f"Created knowledge base association: {kb_config.knowledge_base_id}")
                
            except Exception as e:
                logger.error(f"Failed to create knowledge base association {kb_config.knowledge_base_id}: {e}")
                continue
    
    def update_agent_configuration(self, agent_key: str, config_file: str) -> bool:
        """
        Update agent configuration without recreating dependent resources.
        
        Args:
            agent_key: Key of the agent to update
            config_file: Configuration file to load
            
        Returns:
            True if update was successful, False otherwise
        """
        try:
            logger.info(f"Updating agent configuration for: {agent_key}")
            
            # Load new configuration
            agent_config = self.config_builder.load_agent_config(config_file)
            
            # Validate configuration
            validation_result = self.config_validator.validate_agent_config(agent_config)
            if validation_result.has_errors:
                logger.error(f"Configuration validation failed for {config_file}")
                return False
            
            # Update Lambda ARNs and Knowledge Base IDs
            self._update_lambda_arns_in_config(agent_config)
            self._update_knowledge_base_id_in_config(agent_config)
            
            # Note: In CDK, configuration updates happen during deployment
            # This method provides the interface for configuration updates
            logger.info(f"Configuration update prepared for {agent_key}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update agent configuration for {agent_key}: {e}")
            return False
    
    def validate_agent_configurations(self) -> Dict[str, Any]:
        """
        Validate all agent configurations and action group associations.
        
        Returns:
            Dictionary with validation results
        """
        logger.info("Validating agent configurations")
        
        validation_results = {}
        
        # Get list of configuration files
        config_files = self.config_builder.list_agent_configs()
        
        for config_file in config_files:
            if config_file.startswith("oscar-"):  # Only validate OSCAR agent configs
                try:
                    config_path = f"cdk/agents/configs/{config_file}.json"
                    result = self.config_validator.validate_config_file(config_path)
                    validation_results[config_file] = {
                        "is_valid": result.is_valid,
                        "errors": [str(error) for error in result.errors],
                        "warnings": [str(warning) for warning in result.warnings]
                    }
                except Exception as e:
                    validation_results[config_file] = {
                        "is_valid": False,
                        "errors": [f"Validation failed: {e}"],
                        "warnings": []
                    }
        
        return validation_results
    
    def _create_outputs(self) -> None:
        """Create CloudFormation outputs for the Bedrock agents."""
        # Output for each agent
        for agent_key, agent in self.agents.items():
            # Agent ID output
            CfnOutput(
                self, f"BedrockAgent{agent_key.title()}Id",
                value=agent.attr_agent_id,
                description=f"ID of the {agent_key} Bedrock agent",
                export_name=f"OscarBedrockAgent{agent_key.title()}Id"
            )
            
            # Agent ARN output
            CfnOutput(
                self, f"BedrockAgent{agent_key.title()}Arn",
                value=agent.attr_agent_arn,
                description=f"ARN of the {agent_key} Bedrock agent",
                export_name=f"OscarBedrockAgent{agent_key.title()}Arn"
            )
        
        # Output for each agent alias
        for agent_key, alias in self.agent_aliases.items():
            # Alias ID output
            CfnOutput(
                self, f"BedrockAgentAlias{agent_key.title()}Id",
                value=alias.attr_agent_alias_id,
                description=f"ID of the {agent_key} Bedrock agent alias",
                export_name=f"OscarBedrockAgentAlias{agent_key.title()}Id"
            )
            
            # Alias ARN output
            CfnOutput(
                self, f"BedrockAgentAlias{agent_key.title()}Arn",
                value=alias.attr_agent_alias_arn,
                description=f"ARN of the {agent_key} Bedrock agent alias",
                export_name=f"OscarBedrockAgentAlias{agent_key.title()}Arn"
            )
        
        # Summary output
        agent_ids = [agent.attr_agent_id for agent in self.agents.values()]
        CfnOutput(
            self, "AllBedrockAgentIds",
            value=",".join(agent_ids),
            description="Comma-separated list of all OSCAR Bedrock agent IDs"
        )
    
    @property
    def privileged_agent(self) -> Optional[bedrock.CfnAgent]:
        """Get the privileged agent."""
        return self.agents.get("privileged")
    
    @property
    def limited_agent(self) -> Optional[bedrock.CfnAgent]:
        """Get the limited agent."""
        return self.agents.get("limited")
    
    @property
    def privileged_agent_alias(self) -> Optional[bedrock.CfnAgentAlias]:
        """Get the privileged agent alias."""
        return self.agent_aliases.get("privileged")
    
    @property
    def limited_agent_alias(self) -> Optional[bedrock.CfnAgentAlias]:
        """Get the limited agent alias."""
        return self.agent_aliases.get("limited")
    
    def get_agent_by_key(self, agent_key: str) -> Optional[bedrock.CfnAgent]:
        """
        Get agent by key.
        
        Args:
            agent_key: Key of the agent to retrieve
            
        Returns:
            Bedrock agent or None if not found
        """
        return self.agents.get(agent_key)
    
    def get_agent_alias_by_key(self, agent_key: str) -> Optional[bedrock.CfnAgentAlias]:
        """
        Get agent alias by key.
        
        Args:
            agent_key: Key of the agent alias to retrieve
            
        Returns:
            Bedrock agent alias or None if not found
        """
        return self.agent_aliases.get(agent_key)