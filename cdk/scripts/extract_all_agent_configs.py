#!/usr/bin/env python3
"""
Script to extract all OSCAR agent configurations from AWS Bedrock.
This script discovers all agents in the account and extracts their configurations.
"""

import json
import sys
from pathlib import Path

# Add the utils directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent / 'utils'))

from agent_config_extractor import AgentConfigExtractor


def main():
    """Extract all OSCAR agent configurations."""
    print("OSCAR All Agents Configuration Extractor")
    print("=" * 45)
    
    # Initialize extractor
    try:
        extractor = AgentConfigExtractor()
        print("✓ Initialized AWS Bedrock client")
    except Exception as e:
        print(f"✗ Failed to initialize extractor: {e}")
        return 1
    
    # Get all available agents
    print("\nDiscovering available agents...")
    agents = extractor.list_available_agents()
    
    if not agents:
        print("✗ No agents found in the account")
        return 1
    
    print(f"Found {len(agents)} agents:")
    for agent in agents:
        print(f"  - {agent['agent_name']} ({agent['agent_id']}) - {agent['agent_status']}")
    print()
    
    # Extract configurations for all agents
    print("Extracting agent configurations...")
    print("-" * 35)
    
    # Prepare agent configurations for extraction
    agent_configs = []
    for agent in agents:
        agent_id = agent['agent_id']
        agent_name = agent['agent_name']
        
        # Generate safe filename
        safe_name = agent_name.lower().replace(' ', '-').replace('_', '-')
        filename = f"{safe_name}-current.json"
        
        agent_configs.append({
            'agent_id': agent_id,
            'filename': filename
        })
    
    # Extract all configurations
    results = extractor.extract_multiple_agents(agent_configs)
    
    # Report results
    success_count = 0
    failed_agents = []
    
    for agent_id, result in results.items():
        # Find agent name for reporting
        agent_name = next((a['agent_name'] for a in agents if a['agent_id'] == agent_id), agent_id)
        
        if result.success:
            print(f"✓ {agent_name} ({agent_id}): SUCCESS")
            if result.warnings:
                for warning in result.warnings:
                    if "Configuration saved to:" in warning:
                        print(f"  📁 {warning}")
                    else:
                        print(f"  ⚠ {warning}")
            success_count += 1
        else:
            print(f"✗ {agent_name} ({agent_id}): FAILED")
            print(f"  Error: {result.error_message}")
            failed_agents.append(agent_name)
    
    print()
    print("=" * 45)
    print(f"Extraction Summary:")
    print(f"  Total agents: {len(agents)}")
    print(f"  Successful extractions: {success_count}")
    print(f"  Failed extractions: {len(failed_agents)}")
    
    if success_count == len(agents):
        print("✓ All agent configurations extracted successfully!")
        print("📁 Files saved in: cdk/agents/configs/")
    else:
        print("⚠ Some extractions failed:")
        for failed_agent in failed_agents:
            print(f"  - {failed_agent}")
    
    # List extracted files
    configs_dir = Path("cdk/agents/configs")
    if configs_dir.exists():
        config_files = list(configs_dir.glob("*-current.json"))
        if config_files:
            print(f"\n📋 Extracted configuration files:")
            for config_file in sorted(config_files):
                print(f"  - {config_file.name}")
    
    return 0 if success_count == len(agents) else 1


if __name__ == "__main__":
    exit(main())