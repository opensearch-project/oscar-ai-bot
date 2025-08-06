#!/usr/bin/env python3
"""
Fix OSCAR integration issues:
1. Update supervisor agent to use new metrics Lambda functions
2. Provide instructions for Bedrock agent configuration
"""

import boto3
import json
import os
from dotenv import load_dotenv

load_dotenv()

def update_supervisor_agent():
    """Update supervisor agent environment to use new metrics functions"""
    print("=== Updating Supervisor Agent Configuration ===")
    
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    function_name = 'oscar-supervisor-agent'
    
    try:
        # Get current configuration
        response = lambda_client.get_function_configuration(FunctionName=function_name)
        current_env = response.get('Environment', {}).get('Variables', {})
        
        # Add new environment variables for metrics functions
        updated_env = current_env.copy()
        updated_env.update({
            'TEST_METRICS_FUNCTION': 'oscar-test-metrics-agent-new',
            'BUILD_METRICS_FUNCTION': 'oscar-build-metrics-agent-new', 
            'RELEASE_METRICS_FUNCTION': 'oscar-release-metrics-agent-new',
            'DEPLOYMENT_METRICS_FUNCTION': 'oscar-deployment-metrics-agent-new'
        })
        
        # Update function configuration
        lambda_client.update_function_configuration(
            FunctionName=function_name,
            Environment={'Variables': updated_env}
        )
        
        print(f"✓ Updated {function_name} with new metrics function names")
        return True
        
    except Exception as e:
        print(f"✗ Error updating supervisor agent: {e}")
        return False

def check_bedrock_agent_config():
    """Check current Bedrock agent configuration"""
    print("\n=== Checking Bedrock Agent Configuration ===")
    
    bedrock_agent = boto3.client('bedrock-agent', region_name='us-east-1')
    agent_id = os.getenv('OSCAR_BEDROCK_AGENT_ID')
    
    try:
        # Get agent details
        response = bedrock_agent.get_agent(agentId=agent_id)
        agent = response['agent']
        
        print(f"Agent Name: {agent.get('agentName')}")
        print(f"Agent Status: {agent.get('agentStatus')}")
        
        # Get action groups
        action_groups = bedrock_agent.list_agent_action_groups(
            agentId=agent_id,
            agentVersion='DRAFT'
        )
        
        print(f"\nAction Groups ({len(action_groups['actionGroupSummaries'])}):")
        for ag in action_groups['actionGroupSummaries']:
            print(f"  - {ag['actionGroupName']}: {ag['actionGroupState']}")
            
            # Get detailed action group info
            try:
                ag_detail = bedrock_agent.get_agent_action_group(
                    agentId=agent_id,
                    agentVersion='DRAFT',
                    actionGroupId=ag['actionGroupId']
                )
                
                lambda_config = ag_detail['agentActionGroup'].get('actionGroupExecutor', {}).get('lambda')
                if lambda_config:
                    print(f"    Lambda: {lambda_config}")
                    
            except Exception as e:
                print(f"    Error getting action group details: {e}")
        
        return True
        
    except Exception as e:
        print(f"✗ Error checking Bedrock agent: {e}")
        return False

def provide_fix_instructions():
    """Provide step-by-step instructions to fix the integration"""
    print("\n=== Fix Instructions ===")
    
    agent_id = os.getenv('OSCAR_BEDROCK_AGENT_ID')
    alias_id = os.getenv('OSCAR_BEDROCK_AGENT_ALIAS_ID')
    
    print(f"""
🔧 CRITICAL FIXES NEEDED:

1. UPDATE BEDROCK AGENT ACTION GROUPS:
   - Go to AWS Bedrock Console
   - Navigate to Agent: {agent_id}
   - For each action group, update Lambda function ARNs:
     * Test Metrics: oscar-test-metrics-agent-new
     * Build Metrics: oscar-build-metrics-agent-new  
     * Release Metrics: oscar-release-metrics-agent-new
     * Deployment Metrics: oscar-deployment-metrics-agent-new
   - Save changes and create new agent version
   - Update alias {alias_id} to point to new version

2. CREATE API GATEWAY FOR SLACK:
   - Go to AWS API Gateway Console
   - Create new REST API: 'oscar-slack-webhook'
   - Create resource '/slack' with POST method
   - Set integration to Lambda: oscar-supervisor-agent
   - Enable Lambda Proxy Integration
   - Deploy to 'prod' stage
   - Note the Invoke URL

3. CONFIGURE SLACK APP:
   - Go to https://api.slack.com/apps
   - Select your OSCAR app
   - Go to 'Event Subscriptions'
   - Set Request URL: [API Gateway URL]/slack
   - Subscribe to: app_mention, message.im
   - Save and reinstall app

4. TEST INTEGRATION:
   - Run: python3 test_integration.py
   - Test in Slack: @oscar get build metrics
""")

def main():
    """Run integration fixes"""
    print("OSCAR Integration Fix Tool")
    print("=" * 40)
    
    # Update supervisor agent
    supervisor_updated = update_supervisor_agent()
    
    # Check Bedrock configuration  
    bedrock_checked = check_bedrock_agent_config()
    
    # Provide instructions
    provide_fix_instructions()
    
    print(f"\n=== Summary ===")
    print(f"Supervisor Agent Updated: {'✓' if supervisor_updated else '✗'}")
    print(f"Bedrock Agent Checked: {'✓' if bedrock_checked else '✗'}")
    print(f"\n⚠️  Manual Bedrock agent configuration still required!")

if __name__ == "__main__":
    main()