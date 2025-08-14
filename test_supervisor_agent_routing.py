#!/usr/bin/env python3

import json
import boto3
import os
from datetime import datetime

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

def test_supervisor_agent_routing():
    """Test that the supervisor agent correctly routes to metrics functions with proper agent_type."""
    
    bedrock_client = boto3.client('bedrock-agent-runtime', region_name='us-east-1')
    
    # Get supervisor agent configuration from environment
    supervisor_agent_id = os.getenv('OSCAR_BEDROCK_AGENT_ID')
    supervisor_agent_alias_id = os.getenv('OSCAR_BEDROCK_AGENT_ALIAS_ID')
    
    if not supervisor_agent_id or not supervisor_agent_alias_id:
        print("❌ ERROR: OSCAR_BEDROCK_AGENT_ID and OSCAR_BEDROCK_AGENT_ALIAS_ID must be set")
        return
    
    test_queries = [
        {
            'name': 'Integration Test Query',
            'query': 'Show me integration test results for version 2.18.0',
            'expected_keywords': ['integration_test', 'test_results', 'version']
        },
        {
            'name': 'Build Metrics Query',
            'query': 'Show me build results for version 2.18.0',
            'expected_keywords': ['build', 'version', 'results']
        },
        {
            'name': 'Release Readiness Query',
            'query': 'Show me release readiness for version 2.18.0',
            'expected_keywords': ['release', 'version', 'readiness']
        }
    ]
    
    print(f"🤖 Testing Supervisor Agent Routing")
    print(f"{'='*60}")
    print(f"Supervisor Agent ID: {supervisor_agent_id}")
    print(f"Supervisor Agent Alias: {supervisor_agent_alias_id}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()
    
    results = []
    
    for i, test_query in enumerate(test_queries, 1):
        print(f"Test {i}: {test_query['name']}")
        print(f"Query: {test_query['query']}")
        
        try:
            # Invoke the supervisor agent
            response = bedrock_client.invoke_agent(
                agentId=supervisor_agent_id,
                agentAliasId=supervisor_agent_alias_id,
                inputText=test_query['query'],
                sessionId=f"test-session-{i}-{int(datetime.now().timestamp())}"
            )
            
            # Process the streaming response
            response_text = ""
            session_id = None
            
            if 'completion' in response:
                for event in response['completion']:
                    if 'chunk' in event:
                        chunk = event['chunk']
                        if 'bytes' in chunk:
                            chunk_text = chunk['bytes'].decode('utf-8')
                            response_text += chunk_text
                        
                        # Extract session ID from the chunk if available
                        if 'sessionId' in chunk:
                            session_id = chunk['sessionId']
            
            # Check if response contains expected keywords
            response_lower = response_text.lower()
            found_keywords = [kw for kw in test_query['expected_keywords'] if kw.lower() in response_lower]
            
            if found_keywords:
                print(f"✅ PASSED - Found keywords: {found_keywords}")
                print(f"📝 Response preview: {response_text[:200]}...")
                results.append({
                    'test': test_query['name'],
                    'status': 'PASSED',
                    'found_keywords': found_keywords,
                    'response_length': len(response_text)
                })
            else:
                print(f"❌ FAILED - No expected keywords found")
                print(f"📝 Response preview: {response_text[:200]}...")
                results.append({
                    'test': test_query['name'],
                    'status': 'FAILED',
                    'found_keywords': found_keywords,
                    'expected_keywords': test_query['expected_keywords'],
                    'response_preview': response_text[:500]
                })
            
        except Exception as e:
            print(f"❌ ERROR: {str(e)}")
            results.append({
                'test': test_query['name'],
                'status': 'ERROR',
                'error': str(e)
            })
        
        print("-" * 40)
        print()
    
    # Summary
    passed = len([r for r in results if r['status'] == 'PASSED'])
    failed = len([r for r in results if r['status'] == 'FAILED'])
    errors = len([r for r in results if r['status'] == 'ERROR'])
    
    print(f"📊 Supervisor Agent Routing Test Summary:")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"🚨 Errors: {errors}")
    print(f"📈 Success Rate: {passed}/{len(results)} ({passed/len(results)*100:.1f}%)")
    
    # Show failed tests details
    failed_tests = [r for r in results if r['status'] in ['FAILED', 'ERROR']]
    if failed_tests:
        print(f"\n🔍 Failed Test Details:")
        for test in failed_tests:
            print(f"  - {test['test']}: {test.get('error', 'Keywords not found')}")
    
    return results

if __name__ == "__main__":
    test_supervisor_agent_routing()