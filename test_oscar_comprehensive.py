#!/usr/bin/env python3

import boto3
import json
import time
import os
from datetime import datetime

# Load environment
if os.path.exists('.env'):
    with open('.env', 'r') as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                key, value = line.strip().split('=', 1)
                os.environ[key] = value

AGENT_ID = os.getenv('OSCAR_BEDROCK_AGENT_ID')
AGENT_ALIAS_ID = os.getenv('OSCAR_BEDROCK_AGENT_ALIAS_ID')

TEST_QUERIES = [
    # Integration Test Queries
    "Which components failed the integration tests for RC number 1 for version 3.2.0?",
    "Show me integration test results for RC 2 and RC 3 for version 3.2.0",
    "What OpenSearch components passed integration tests for RC 1 version 3.2.0?",
    "Which OpenSearch-Dashboards components failed RC 1 for version 3.2.0?",
    "Which components failed integration tests for build number 11323 version 3.2.0?",
    "Show me test results for build numbers 11323, 8585, and 9876 for version 3.2.0",
    "What's the integration test status for build 11323?",
    "Show me OpenSearch integration test failures for version 3.2.0",
    "What's the test status for OpenSearch-Dashboards components version 3.2.0?",
    "Which knn and sql components failed integration tests for version 3.2.0?",
    "Show me ARM64 integration test failures for version 3.2.0",
    "Which components failed on Windows platform for version 3.2.0?",
    "What's the RPM distribution test status for version 3.2.0?",
    "What's the overall integration test status for version 3.2.0?",
    "Show me recent integration test failures",
    "Give me integration test success rates for version 3.2.0",
    
    # Build Metrics Queries
    "What's the build status for version 3.2.0?",
    "Show me build failures for version 3.2.0",
    "Give me build success rates for version 3.2.0",
    "What's the build status for OpenSearch components version 3.2.0?",
    "Show me build failures for knn and sql repos",
    "Which OpenSearch-Dashboards components have build issues?",
    "Show me build results for build numbers 11323 and 8585",
    "What's the build status for build 11323?",
    "Give me build details for recent build numbers",
    "Show me build failures in the last 7 days",
    "What's the build performance over the last 30 days?",
    "Give me recent build trends",
    "What's the current overall build status?",
    "Show me all build failures",
    "Give me build pipeline health summary",
    
    # Release Metrics Queries
    "What's the release readiness for version 3.2.0?",
    "Show me release readiness scores for version 3.2.0",
    "Which components are ready for release version 3.2.0?",
    "What's blocking the release for version 3.2.0?",
    "Show me OpenSearch release readiness for version 3.2.0",
    "What's the release status for OpenSearch-Dashboards version 3.2.0?",
    "Which components need attention for release 3.2.0?",
    "Who are the release owners for version 3.2.0?",
    "Show me release owners for OpenSearch components",
    "Give me contact information for release coordination",
    "Show me open release issues for version 3.2.0",
    "What release blockers exist for version 3.2.0?",
    "Give me release notes status for version 3.2.0",
    "What's the overall release health for version 3.2.0?",
    "Show me release pipeline status",
    "Give me release readiness summary",
    
    # Cross-Agent Complex Queries
    "Analyze integration test and build failures for version 3.2.0",
    "Show me the complete pipeline health for version 3.2.0",
    "Which components have both build and test issues?",
    "Give me an executive summary of version 3.2.0 readiness",
    "What's the overall development pipeline health?",
    "Show me critical issues blocking release 3.2.0",
    "Compare OpenSearch vs OpenSearch-Dashboards test results",
    "Show me ARM64 vs x64 performance differences",
    "Compare current vs previous release readiness",
    
    # Edge Cases
    "Show me results for version 99.99.99",
    "What's the status for build number 999999?",
    "Give me results for RC 999",
    "Show me integration test results",
    "What's the build status?",
    "Give me release readiness",
    "What's broken?",
    "Show me failures",
    "Give me status",
    
    # Knowledge Base Queries
    "How can I build an x64 tarball?",
    "What are the steps to build OpenSearch from source?",
    "How do I set up the build environment?",
    "How do I configure OpenSearch for production?",
    "What are the recommended JVM settings?",
    "How do I set up cluster security?",
    "How do I debug build failures?",
    "What should I do if integration tests fail?",
    "How do I resolve dependency issues?"
]

def test_query(client, query, query_num, total_queries):
    """Test a single query against OSCAR"""
    print(f"\n[{query_num}/{total_queries}] Testing: {query[:60]}...")
    
    session_id = f"test-{int(time.time())}-{query_num}"
    
    try:
        response = client.invoke_agent(
            agentId=AGENT_ID,
            agentAliasId=AGENT_ALIAS_ID,
            sessionId=session_id,
            inputText=query
        )
        
        # Process streaming response
        response_text = ""
        for event in response['completion']:
            if 'chunk' in event:
                chunk = event['chunk']
                if 'bytes' in chunk:
                    response_text += chunk['bytes'].decode('utf-8')
        
        result = {
            'query_number': query_num,
            'query': query,
            'timestamp': datetime.now().isoformat(),
            'status': 'success',
            'response_length': len(response_text),
            'response': response_text,
            'session_id': session_id
        }
        
        # Check for common error patterns
        if any(error in response_text.lower() for error in ['error', 'unable', 'failed', 'sorry']):
            result['status'] = 'error_in_response'
            result['error_indicators'] = [word for word in ['error', 'unable', 'failed', 'sorry'] if word in response_text.lower()]
        
        print(f"✅ Success: {len(response_text)} chars")
        return result
        
    except Exception as e:
        result = {
            'query_number': query_num,
            'query': query,
            'timestamp': datetime.now().isoformat(),
            'status': 'exception',
            'error': str(e),
            'session_id': session_id
        }
        print(f"❌ Exception: {e}")
        return result

def main():
    if not AGENT_ID or not AGENT_ALIAS_ID:
        print("❌ Missing OSCAR_BEDROCK_AGENT_ID or OSCAR_BEDROCK_AGENT_ALIAS_ID in .env")
        return
    
    client = boto3.client('bedrock-agent-runtime', region_name='us-east-1')
    
    results = {
        'test_run': {
            'start_time': datetime.now().isoformat(),
            'agent_id': AGENT_ID,
            'agent_alias_id': AGENT_ALIAS_ID,
            'total_queries': len(TEST_QUERIES)
        },
        'results': []
    }
    
    print(f"🚀 Starting comprehensive OSCAR test with {len(TEST_QUERIES)} queries")
    print(f"Agent ID: {AGENT_ID}")
    print(f"Agent Alias: {AGENT_ALIAS_ID}")
    
    for i, query in enumerate(TEST_QUERIES, 1):
        result = test_query(client, query, i, len(TEST_QUERIES))
        results['results'].append(result)
        
        # Save intermediate results
        with open('oscar_test_results.json', 'w') as f:
            json.dump(results, f, indent=2)
        
        # Throttle to avoid rate limits
        time.sleep(3)
    
    results['test_run']['end_time'] = datetime.now().isoformat()
    
    # Final save
    with open('oscar_test_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    # Summary
    success_count = len([r for r in results['results'] if r['status'] == 'success'])
    error_count = len([r for r in results['results'] if r['status'] == 'error_in_response'])
    exception_count = len([r for r in results['results'] if r['status'] == 'exception'])
    
    print(f"\n{'='*60}")
    print("TEST SUMMARY")
    print(f"{'='*60}")
    print(f"Total queries: {len(TEST_QUERIES)}")
    print(f"Successful: {success_count}")
    print(f"Errors in response: {error_count}")
    print(f"Exceptions: {exception_count}")
    print(f"\nResults saved to: oscar_test_results.json")

if __name__ == "__main__":
    main()