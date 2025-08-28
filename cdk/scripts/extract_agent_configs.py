#!/usr/bin/env python3
"""
Script to extract current OSCAR agent configurations from AWS Bedrock.
This script extracts both privileged and limited agent configurations and saves them as JSON files.
"""

import os
import sys
from pathlib import Path

# Add the utils directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent / 'utils'))

from agent_config_extractor import AgentConfigExtractor


def load_env_file(env_path: str = '.env') -> dict:
    """Load environment variables from .env file."""
    env_vars = {}
    env_file = Path(env_path)
    
    if not env_file.exists():
        print(f"Warning: .env file not found at {env_path}")
        return env_vars
    
    with open(env_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                env_vars[key] = value
    
    return env_vars


def main():
    """Extract OSCAR agent configurations."""
    print("OSCAR Agent Configuration Extractor")
    print("=" * 40)
    
    # Load environment variables
    env_vars = load_env_file()
    
    # Get all agent IDs from environment
    privileged_agent_id = env_vars.get('OSCAR_PRIVILEGED_BEDROCK_AGENT_ID')
    privileged_alias_id = env_vars.get('OSCAR_PRIVILEGED_BEDROCK_AGENT_ALIAS_ID')
    limited_agent_id = env_vars.get('OSCAR_LIMITED_BEDROCK_AGENT_ID')
    limited_alias_id = env_vars.get('OSCAR_LIMITED_BEDROCK_AGENT_ALIAS_ID')
    jenkins_agent_id = env_vars.get('JENKINS_AGENT_ID')
    jenkins_alias_id = env_vars.get('JENKINS_AGENT_ALIAS_ID')
    region = env_vars.get('AWS_REGION', 'us-east-1')
    
    # Also check for metrics agents (they might be in different env vars)
    # Based on the current config, we have a release-metrics-agent with ID 4FCARBPEYB
    
    print(f"Region: {region}")
    print(f"Privileged Agent ID: {privileged_agent_id}")
    print(f"Limited Agent ID: {limited_agent_id}")
    print(f"Jenkins Agent ID: {jenkins_agent_id}")
    print()
    
    # Initialize extractor
    try:
        extractor = AgentConfigExtractor(region=region)
        print("✓ Initialized AWS Bedrock client")
    except Exception as e:
        print(f"✗ Failed to initialize extractor: {e}")
        return 1
    
    # First, let's list all available agents to see what we have
    print("Discovering available agents...")
    available_agents = extractor.list_available_agents()
    
    if available_agents:
        print(f"Found {len(available_agents)} agents:")
        for agent in available_agents:
            print(f"  - {agent['agent_name']} ({agent['agent_id']}) - {agent['agent_status']}")
        print()
    
    # Extract configurations for known agents
    agents_to_extract = []
    
    if privileged_agent_id:
        agents_to_extract.append({
            'agent_id': privileged_agent_id,
            'alias_id': privileged_alias_id,
            'filename': 'oscar-privileged-agent-current.json'
        })
    
    if limited_agent_id:
        agents_to_extract.append({
            'agent_id': limited_agent_id,
            'alias_id': limited_alias_id,
            'filename': 'oscar-limited-agent-current.json'
        })
    
    if jenkins_agent_id:
        agents_to_extract.append({
            'agent_id': jenkins_agent_id,
            'alias_id': jenkins_alias_id,
            'filename': 'jenkins-agent-current.json'
        })
    
    # Add any other agents we discover that might be metrics agents
    for agent in available_agents:
        agent_id = agent['agent_id']
        agent_name = agent['agent_name'].lower()
        
        # Skip agents we already have
        if agent_id in [privileged_agent_id, limited_agent_id, jenkins_agent_id]:
            continue
            
        # Look for metrics agents or other OSCAR-related agents
        if any(keyword in agent_name for keyword in ['metrics', 'test', 'build', 'release', 'deployment', 'oscar']):
            safe_name = agent_name.replace(' ', '-').replace('_', '-')
            agents_to_extract.append({
                'agent_id': agent_id,
                'alias_id': None,  # Will auto-discover
                'filename': f'{safe_name}-current.json'
            })
    
    if not agents_to_extract:
        print("No agents found to extract. Check environment variables.")
        return 1
    
    print(f"Extracting {len(agents_to_extract)} agent configurations...")
    print("-" * 50)
    
    results = extractor.extract_multiple_agents(agents_to_extract)
    
    # Report results
    success_count = 0
    for agent_id, result in results.items():
        # Find the agent name from our list
        agent_info = next((agent for agent in available_agents if agent['agent_id'] == agent_id), None)
        agent_name = agent_info['agent_name'] if agent_info else agent_id
        
        if result.success:
            print(f"✓ {agent_name} ({agent_id}): SUCCESS")
            if result.warnings:
                for warning in result.warnings:
                    print(f"  ⚠ {warning}")
            success_count += 1
        else:
            print(f"✗ {agent_name} ({agent_id}): FAILED")
            print(f"  Error: {result.error_message}")
    
    print()
    print(f"Extraction completed: {success_count}/{len(agents_to_extract)} agents successful")
    
    if success_count > 0:
        print(f"✓ {success_count} agent configurations extracted successfully!")
        print("Files saved in: cdk/agents/configs/")
        
        if success_count < len(agents_to_extract):
            print("⚠ Some extractions failed. Check the errors above.")
        
        return 0
    else:
        print("✗ All extractions failed. Check the errors above.")
        return 1


if __name__ == "__main__":
    exit(main())