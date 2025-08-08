#!/usr/bin/env python3

import boto3
import json
import time

# Agent IDs (replace with actual IDs from your deployment)
AGENTS = {
    'integration_test': 'AGENT_ID_HERE',
    'build_metrics': 'AGENT_ID_HERE', 
    'release_metrics': 'AGENT_ID_HERE'
}

TEST_QUERIES = [
    "Which components failed the integration tests for RC number 1 for version 3.2.0?",
    "Which components failed the integration tests for build number 11323 and build number 8585. Version is 3.2.0?",
    "Which components failed the integration tests for RC number 1 of both OpenSearch and OpenSearch-Dashboards for version 3.2.0?",
    "Show me build status for version 3.2.0",
    "What's the release readiness for version 3.2.0?"
]

def test_agent(client, agent_id, query):
    """Test a Bedrock agent with a query"""
    print(f"\n🧪 Testing query: {query[:60]}...")
    
    try:
        response = client.invoke_agent(
            agentId=agent_id,
            agentAliasId='TSTALIASID',
            sessionId=f'test-{int(time.time())}',
            inputText=query
        )
        
        # Process streaming response
        response_text = ""
        for event in response['completion']:
            if 'chunk' in event:
                chunk = event['chunk']
                if 'bytes' in chunk:
                    response_text += chunk['bytes'].decode('utf-8')
        
        if 'error' in response_text.lower() or 'unable' in response_text.lower():
            print(f"❌ Error in response: {response_text[:200]}...")
            return False
        else:
            print(f"✅ Success: {len(response_text)} chars")
            return True
            
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False

def main():
    client = boto3.client('bedrock-agent-runtime', region_name='us-east-1')
    
    print("Note: Update AGENTS dictionary with actual agent IDs before running")
    print("This is a template - replace AGENT_ID_HERE with real agent IDs")
    
    # Test each query against integration test agent (as example)
    if AGENTS['integration_test'] != 'AGENT_ID_HERE':
        for query in TEST_QUERIES[:3]:  # First 3 are integration test queries
            test_agent(client, AGENTS['integration_test'], query)
            time.sleep(2)

if __name__ == "__main__":
    main()