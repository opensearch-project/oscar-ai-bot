#!/usr/bin/env python3
"""
Integration test for OSCAR supervisor and metrics agents
Tests the complete flow: Slack -> Supervisor -> Metrics Agents -> Response
"""

import boto3
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_supervisor_agent():
    """Test direct supervisor agent invocation"""
    print("=== Testing Supervisor Agent Direct Invocation ===")
    
    bedrock_agent = boto3.client('bedrock-agent-runtime', region_name='us-east-1')
    
    agent_id = os.getenv('OSCAR_BEDROCK_AGENT_ID')
    alias_id = os.getenv('OSCAR_BEDROCK_AGENT_ALIAS_ID')
    
    print(f"Agent ID: {agent_id}")
    print(f"Alias ID: {alias_id}")
    
    # Test metrics query through supervisor
    test_query = "Get me the latest build metrics summary"
    
    try:
        response = bedrock_agent.invoke_agent(
            agentId=agent_id,
            agentAliasId=alias_id,
            sessionId='test-integration-session',
            inputText=test_query
        )
        
        # Process streaming response
        result = ""
        for event in response['completion']:
            if 'chunk' in event:
                chunk = event['chunk']
                if 'bytes' in chunk:
                    result += chunk['bytes'].decode('utf-8')
        
        print(f"Query: {test_query}")
        print(f"Response: {result}")
        return True
        
    except Exception as e:
        print(f"Error testing supervisor agent: {e}")
        return False

def test_metrics_agents_direct():
    """Test direct metrics agent invocations"""
    print("\n=== Testing Metrics Agents Direct Invocation ===")
    
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    
    agents = [
        ('oscar-test-metrics-agent-new', 'get_test_metrics'),
        ('oscar-build-metrics-agent-new', 'get_build_metrics'),
        ('oscar-release-metrics-agent-new', 'get_release_metrics'),
        ('oscar-deployment-metrics-agent-new', 'get_deployment_metrics')
    ]
    
    results = {}
    
    for function_name, method in agents:
        try:
            response = lambda_client.invoke(
                FunctionName=function_name,
                Payload=json.dumps({"function": method})
            )
            
            payload = json.loads(response['Payload'].read())
            results[function_name] = {
                'status': 'success',
                'response': payload
            }
            print(f"✓ {function_name}: {payload.get('body', {}).get('type', 'unknown')}")
            
        except Exception as e:
            results[function_name] = {
                'status': 'error',
                'error': str(e)
            }
            print(f"✗ {function_name}: {e}")
    
    return results

def test_slack_integration():
    """Test Slack integration components"""
    print("\n=== Testing Slack Integration Setup ===")
    
    slack_token = os.getenv('SLACK_BOT_TOKEN')
    slack_secret = os.getenv('SLACK_SIGNING_SECRET')
    
    print(f"Slack Bot Token: {'✓ Set' if slack_token else '✗ Missing'}")
    print(f"Slack Signing Secret: {'✓ Set' if slack_secret else '✗ Missing'}")
    
    # Check if Slack Lambda exists
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    
    try:
        functions = lambda_client.list_functions()['Functions']
        slack_functions = [f for f in functions if 'slack' in f['FunctionName'].lower()]
        
        if slack_functions:
            print("Slack Lambda functions found:")
            for func in slack_functions:
                print(f"  - {func['FunctionName']}")
        else:
            print("⚠ No Slack Lambda functions found")
            
    except Exception as e:
        print(f"Error checking Slack functions: {e}")

def main():
    """Run all integration tests"""
    print("OSCAR Integration Test Suite")
    print("=" * 50)
    
    # Test 1: Direct metrics agents
    metrics_results = test_metrics_agents_direct()
    
    # Test 2: Supervisor agent
    supervisor_success = test_supervisor_agent()
    
    # Test 3: Slack integration setup
    test_slack_integration()
    
    # Summary
    print("\n=== Integration Test Summary ===")
    
    metrics_success = all(r['status'] == 'success' for r in metrics_results.values())
    print(f"Metrics Agents: {'✓ All working' if metrics_success else '✗ Some issues'}")
    print(f"Supervisor Agent: {'✓ Working' if supervisor_success else '✗ Issues'}")
    
    if metrics_success and supervisor_success:
        print("\n🎉 Integration test PASSED - Ready for Slack testing!")
        print("\nNext steps:")
        print("1. Test via Slack: '@oscar get build metrics'")
        print("2. Monitor CloudWatch logs for any issues")
        print("3. Verify response format in Slack")
    else:
        print("\n⚠ Integration test FAILED - Check errors above")

if __name__ == "__main__":
    main()