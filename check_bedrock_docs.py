#!/usr/bin/env python3
"""
Check the actual Bedrock agent configuration to see what response format it expects.
"""

import boto3
import json

def check_bedrock_agent_config():
    """Check the Bedrock agent configuration."""
    
    bedrock_client = boto3.client('bedrock-agent', region_name='us-east-1')
    
    # Agent IDs from your logs
    agent_ids = [
        'NFCKXG7OIN',  # Privileged agent from logs
        'DKGVSQJG3D'   # Limited agent from logs
    ]
    
    for agent_id in agent_ids:
        try:
            print(f"\n{'='*60}")
            print(f"Checking Agent: {agent_id}")
            print(f"{'='*60}")
            
            # Get agent details
            agent_response = bedrock_client.get_agent(agentId=agent_id)
            agent = agent_response['agent']
            
            print(f"Agent Name: {agent.get('agentName', 'Unknown')}")
            print(f"Agent Status: {agent.get('agentStatus', 'Unknown')}")
            print(f"Foundation Model: {agent.get('foundationModel', 'Unknown')}")
            
            # Get action groups
            action_groups_response = bedrock_client.list_agent_action_groups(
                agentId=agent_id,
                agentVersion='DRAFT'
            )
            
            print(f"\nAction Groups:")
            for ag in action_groups_response.get('actionGroupSummaries', []):
                print(f"  - {ag.get('actionGroupName', 'Unknown')}: {ag.get('actionGroupState', 'Unknown')}")
                
                # Get detailed action group info
                try:
                    ag_detail = bedrock_client.get_agent_action_group(
                        agentId=agent_id,
                        agentVersion='DRAFT',
                        actionGroupId=ag['actionGroupId']
                    )
                    
                    ag_info = ag_detail['agentActionGroup']
                    print(f"    Lambda ARN: {ag_info.get('actionGroupExecutor', {}).get('lambda', 'Not set')}")
                    
                    # Check if there's an API schema that defines response format
                    if 'apiSchema' in ag_info:
                        print(f"    Has API Schema: Yes")
                        schema = ag_info['apiSchema']
                        if 'payload' in schema:
                            print(f"    Schema Type: {type(schema['payload'])}")
                    
                except Exception as e:
                    print(f"    Error getting details: {e}")
            
        except Exception as e:
            print(f"❌ Error checking agent {agent_id}: {e}")

def check_lambda_permissions():
    """Check Lambda function permissions for Bedrock."""
    
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    
    functions = [
        'oscar-test-metrics-agent-new',
        'oscar-build-metrics-agent-new',
        'oscar-release-metrics-agent-new'
    ]
    
    for func_name in functions:
        try:
            print(f"\n--- Checking {func_name} ---")
            
            # Get function configuration
            config_response = lambda_client.get_function_configuration(
                FunctionName=func_name
            )
            
            print(f"Runtime: {config_response.get('Runtime', 'Unknown')}")
            print(f"Timeout: {config_response.get('Timeout', 'Unknown')}s")
            print(f"Memory: {config_response.get('MemorySize', 'Unknown')}MB")
            
            # Check resource-based policy
            try:
                policy_response = lambda_client.get_policy(FunctionName=func_name)
                policy = json.loads(policy_response['Policy'])
                
                print(f"Has Resource Policy: Yes")
                for statement in policy.get('Statement', []):
                    if 'bedrock' in statement.get('Principal', {}).get('Service', '').lower():
                        print(f"  Bedrock Permission: ✅")
                        break
                else:
                    print(f"  Bedrock Permission: ❌ Not found")
                    
            except lambda_client.exceptions.ResourceNotFoundException:
                print(f"Has Resource Policy: No")
                
        except Exception as e:
            print(f"❌ Error checking {func_name}: {e}")

if __name__ == "__main__":
    print("Checking Bedrock Agent Configuration...")
    check_bedrock_agent_config()
    
    print("\n" + "="*80)
    print("Checking Lambda Permissions...")
    check_lambda_permissions()