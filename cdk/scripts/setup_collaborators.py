#!/usr/bin/env python3
"""
Post-deployment script to set up Bedrock agent collaborators.

This script handles the setup of agent collaborators after CDK deployment,
since collaborators cannot be configured directly in CDK CloudFormation.
"""

import boto3
import json
import logging
import os
import sys
from typing import Dict, List, Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CollaboratorSetup:
    """Handles the setup of Bedrock agent collaborators."""
    
    def __init__(self, region: str = "us-east-1"):
        """
        Initialize the collaborator setup.
        
        Args:
            region: AWS region for Bedrock operations
        """
        self.region = region
        self.bedrock_client = boto3.client('bedrock-agent', region_name=region)
        self.cloudformation_client = boto3.client('cloudformation', region_name=region)
    
    def get_stack_outputs(self, stack_name: str) -> Dict[str, str]:
        """
        Get CloudFormation stack outputs.
        
        Args:
            stack_name: Name of the CloudFormation stack
            
        Returns:
            Dictionary of output key-value pairs
        """
        try:
            response = self.cloudformation_client.describe_stacks(StackName=stack_name)
            outputs = {}
            
            for stack in response['Stacks']:
                for output in stack.get('Outputs', []):
                    outputs[output['OutputKey']] = output['OutputValue']
            
            return outputs
        except Exception as e:
            logger.error(f"Failed to get stack outputs for {stack_name}: {e}")
            return {}
    
    def load_agent_config(self, config_file: str) -> Dict[str, Any]:
        """
        Load agent configuration from JSON file.
        
        Args:
            config_file: Path to the configuration file
            
        Returns:
            Agent configuration dictionary
        """
        config_path = os.path.join(os.path.dirname(__file__), "..", "agents", "configs", config_file)
        
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load config file {config_file}: {e}")
            return {}
    
    def setup_collaborators_for_agent(self, agent_id: str, collaborators: List[Dict[str, Any]], 
                                    agent_id_mapping: Dict[str, str]) -> bool:
        """
        Set up collaborators for a specific agent.
        
        Args:
            agent_id: ID of the agent to configure
            collaborators: List of collaborator configurations
            agent_id_mapping: Mapping of placeholder IDs to actual agent IDs
            
        Returns:
            True if successful, False otherwise
        """
        try:
            for collaborator in collaborators:
                placeholder_id = collaborator.get("agent_id")
                
                # Replace placeholder with actual agent ID
                if placeholder_id in agent_id_mapping:
                    actual_agent_id = agent_id_mapping[placeholder_id]
                    
                    # Associate the collaborator agent
                    response = self.bedrock_client.associate_agent_collaborator(
                        agentId=agent_id,
                        agentVersion='DRAFT',
                        collaboratorId=actual_agent_id,
                        collaboratorName=collaborator.get("collaborator_name", "collaborator"),
                        collaborationInstruction=collaborator.get("collaboration_instruction", ""),
                        relayConversationHistory=collaborator.get("relay_conversation_history", "TO_COLLABORATOR")
                    )
                    
                    logger.info(f"Successfully associated collaborator {actual_agent_id} with agent {agent_id}")
                else:
                    logger.warning(f"No mapping found for placeholder ID: {placeholder_id}")
            
            return True
        except Exception as e:
            logger.error(f"Failed to setup collaborators for agent {agent_id}: {e}")
            return False
    
    def run_setup(self, stack_name: str) -> bool:
        """
        Run the complete collaborator setup process.
        
        Args:
            stack_name: Name of the CDK stack
            
        Returns:
            True if successful, False otherwise
        """
        logger.info("Starting collaborator setup process")
        
        # Get stack outputs to map agent IDs
        outputs = self.get_stack_outputs(stack_name)
        if not outputs:
            logger.error("Failed to get stack outputs")
            return False
        
        # Create agent ID mapping
        agent_id_mapping = {
            "CDK_JENKINS_AGENT_ID": outputs.get("AgentJenkinsId"),
            "CDK_BUILD_METRICS_AGENT_ID": outputs.get("AgentBuildMetricsId"),
            "CDK_TEST_METRICS_AGENT_ID": outputs.get("AgentTestMetricsId"),
            "CDK_RELEASE_METRICS_AGENT_ID": outputs.get("AgentReleaseMetricsId")
        }
        
        # Verify all required agent IDs are available
        missing_ids = [k for k, v in agent_id_mapping.items() if not v]
        if missing_ids:
            logger.error(f"Missing agent IDs in stack outputs: {missing_ids}")
            return False
        
        # Setup collaborators for privileged agent
        privileged_agent_id = outputs.get("AgentPrivilegedId")
        if privileged_agent_id:
            privileged_config = self.load_agent_config("oscar-privileged-agent-current.json")
            if privileged_config.get("collaborators"):
                logger.info("Setting up collaborators for privileged agent")
                success = self.setup_collaborators_for_agent(
                    privileged_agent_id, 
                    privileged_config["collaborators"], 
                    agent_id_mapping
                )
                if not success:
                    logger.error("Failed to setup collaborators for privileged agent")
                    return False
        
        # Setup collaborators for limited agent
        limited_agent_id = outputs.get("AgentLimitedId")
        if limited_agent_id:
            limited_config = self.load_agent_config("oscar-limited-agent-current.json")
            if limited_config.get("collaborators"):
                logger.info("Setting up collaborators for limited agent")
                success = self.setup_collaborators_for_agent(
                    limited_agent_id, 
                    limited_config["collaborators"], 
                    agent_id_mapping
                )
                if not success:
                    logger.error("Failed to setup collaborators for limited agent")
                    return False
        
        logger.info("Collaborator setup completed successfully")
        return True


def main():
    """Main entry point for the script."""
    if len(sys.argv) != 2:
        print("Usage: python setup_collaborators.py <stack-name>")
        sys.exit(1)
    
    stack_name = sys.argv[1]
    setup = CollaboratorSetup()
    
    success = setup.run_setup(stack_name)
    if not success:
        logger.error("Collaborator setup failed")
        sys.exit(1)
    
    logger.info("Collaborator setup completed successfully")


if __name__ == "__main__":
    main()