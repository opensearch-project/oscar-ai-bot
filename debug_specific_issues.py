#!/usr/bin/env python3

import boto3
import json
import time
import os

# Load environment
if os.path.exists('.env'):
    with open('.env', 'r') as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                key, value = line.strip().split('=', 1)
                os.environ[key] = value

AGENT_ID = os.getenv('OSCAR_BEDROCK_AGENT_ID')
AGENT_ALIAS_ID = os.getenv('OSCAR_BEDROCK_AGENT_ALIAS_ID')

# Specific problematic queries to debug
DEBUG_QUERIES = [
    # Agent routing issue
    {
        'name': 'build_status_general',
        'query': "What's the build status for version 3.2.0?",
        'expected_agent': 'build'
    },
    {
        'name': 'build_failures_specific', 
        'query': "Show me build failures for version 3.2.0",
        'expected_agent': 'build'
    },
    
    # Data inconsistency issue
    {
        'name': 'build_11323_single',
        'query': "Which components failed integration tests for build number 11323 version 3.2.0?",
        'expected_agent': 'integration_test'
    },
    {
        'name': 'build_11323_multiple',
        'query': "Show me test results for build numbers 11323, 8585, and 9876 for version 3.2.0",
        'expected_agent': 'integration_test'
    },
    
    # Timeout issues (shorter versions)
    {
        'name': 'simple_cross_analysis',
        'query': "Show integration test and build status for version 3.2.0",
        'expected_agent': 'cross_agent'
    },
    
    # Knowledge base issues
    {
        'name': 'production_config',
        'query': "How do I configure OpenSearch for production?",
        'expected_agent': 'knowledge_base'
    }
]

def debug_query(client, test_case):
    """Debug a specific query with detailed logging"""
    print(f"\n{'='*60}")
    print(f"DEBUGGING: {test_case['name']}")
    print(f"Query: {test_case['query']}")
    print(f"Expected Agent: {test_case['expected_agent']}")
    print(f"{'='*60}")
    
    session_id = f"debug-{int(time.time())}-{test_case['name']}"
    
    try:
        start_time = time.time()
        response = client.invoke_agent(
            agentId=AGENT_ID,
            agentAliasId=AGENT_ALIAS_ID,
            sessionId=session_id,
            inputText=test_case['query']
        )
        
        # Process streaming response
        response_text = ""
        for event in response['completion']:
            if 'chunk' in event:
                chunk = event['chunk']
                if 'bytes' in chunk:
                    response_text += chunk['bytes'].decode('utf-8')
        
        end_time = time.time()
        duration = end_time - start_time
        
        print(f"✅ SUCCESS ({duration:.1f}s)")
        print(f"Response length: {len(response_text)} chars")
        print(f"First 200 chars: {response_text[:200]}...")
        
        # Look for agent indicators in response
        response_lower = response_text.lower()
        if 'integration test' in response_lower:
            detected_agent = 'integration_test'
        elif 'build' in response_lower and 'test' not in response_lower:
            detected_agent = 'build'
        elif 'release' in response_lower:
            detected_agent = 'release'
        elif any(kb_word in response_lower for kb_word in ['configure', 'setup', 'install', 'documentation']):
            detected_agent = 'knowledge_base'
        else:
            detected_agent = 'unknown'
        
        print(f"Detected agent: {detected_agent}")
        if detected_agent != test_case['expected_agent']:
            print(f"⚠️  ROUTING MISMATCH: Expected {test_case['expected_agent']}, got {detected_agent}")
        
        return {
            'status': 'success',
            'duration': duration,
            'response_length': len(response_text),
            'detected_agent': detected_agent,
            'response': response_text
        }
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return {
            'status': 'error',
            'error': str(e)
        }

def main():
    if not AGENT_ID or not AGENT_ALIAS_ID:
        print("❌ Missing agent configuration")
        return
    
    client = boto3.client('bedrock-agent-runtime', region_name='us-east-1')
    
    print(f"🔍 Debugging specific OSCAR issues")
    print(f"Agent ID: {AGENT_ID}")
    
    results = {}
    
    for test_case in DEBUG_QUERIES:
        result = debug_query(client, test_case)
        results[test_case['name']] = result
        time.sleep(5)  # Longer pause for debugging
    
    # Save detailed results
    with open('debug_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n{'='*60}")
    print("DEBUG SUMMARY")
    print(f"{'='*60}")
    
    for name, result in results.items():
        status = result['status']
        if status == 'success':
            duration = result['duration']
            agent = result.get('detected_agent', 'unknown')
            print(f"{name}: ✅ {status} ({duration:.1f}s) - {agent}")
        else:
            print(f"{name}: ❌ {status} - {result.get('error', 'unknown error')}")

if __name__ == "__main__":
    main()