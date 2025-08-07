#!/usr/bin/env python3
"""
Test script to identify issues with metrics queries vs knowledge base queries.
"""

import json
import time
import boto3
import requests
from datetime import datetime
from typing import List, Dict, Any

# Knowledge base queries (should work)
KNOWLEDGE_BASE_QUERIES = [
    "Hello",
    "What is OpenSearch?",
    "How do I configure OpenSearch?",
    "Tell me about OpenSearch security",
    "What are OpenSearch best practices?"
]

# Test metrics queries (organized by agent type)
TEST_METRICS_QUERIES = {
    "test_metrics": [
        "What is the test status today?",
        "Show me recent test failures"
    ],
    "build_metrics": [
        "What is the build status today?", 
        "Show me recent build failures"
    ],
    "release_metrics": [
        "What is the release status today?",
        "Show me recent release information"
    ],
    "deployment_metrics": [
        "What is the deployment status today?",
        "Show me recent deployment metrics"
    ]
}

WEBHOOK_URL = "https://x7b5urlaof.execute-api.us-east-1.amazonaws.com/prod/slack/events"

def create_slack_event(query: str, channel: str = "C09827S7CEB", user: str = "U091B0QH1QD") -> Dict[str, Any]:
    """Create a mock Slack app_mention event."""
    timestamp = str(time.time())
    return {
        "token": "verification_token",
        "team_id": "T123456", 
        "api_app_id": "A123456",
        "event": {
            "type": "app_mention",
            "user": user,
            "text": f"<@UBOT123456> {query}",
            "ts": timestamp,
            "channel": channel,
            "event_ts": timestamp
        },
        "type": "event_callback",
        "event_id": f"Ev{int(time.time())}",
        "event_time": int(time.time())
    }

def send_test_query(query: str, test_id: int, query_type: str) -> Dict[str, Any]:
    """Send a test query and measure response."""
    print(f"\n🧪 Test {test_id} ({query_type}): '{query}'")
    
    start_time = time.time()
    event = create_slack_event(query)
    
    try:
        response = requests.post(
            WEBHOOK_URL,
            json=event,
            headers={
                "Content-Type": "application/json",
                "X-Slack-Request-Timestamp": str(int(time.time())),
                "X-Slack-Signature": f"v0=test_signature_{test_id}"
            },
            timeout=15
        )
        
        response_time = time.time() - start_time
        
        result = {
            "test_id": test_id,
            "query": query,
            "query_type": query_type,
            "status_code": response.status_code,
            "response_time": response_time,
            "response_body": response.text,
            "timestamp": datetime.now().isoformat(),
            "success": response.status_code == 200
        }
        
        status_icon = "✅" if response.status_code == 200 else "❌"
        print(f"   {status_icon} Status: {response.status_code}, Time: {response_time:.2f}s")
        return result
        
    except Exception as e:
        response_time = time.time() - start_time
        result = {
            "test_id": test_id,
            "query": query,
            "query_type": query_type,
            "status_code": None,
            "response_time": response_time,
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
            "success": False
        }
        
        print(f"   ❌ Error: {e}")
        return result

def get_recent_lambda_logs(minutes: int = 5) -> List[Dict[str, Any]]:
    """Get recent Lambda logs with error details."""
    print(f"\n📋 Checking Lambda logs from last {minutes} minutes...")
    
    try:
        logs_client = boto3.client('logs', region_name='us-east-1')
        
        # Calculate start time
        start_time = int((time.time() - (minutes * 60)) * 1000)
        
        # Get all log events (not just errors)
        response = logs_client.filter_log_events(
            logGroupName='/aws/lambda/oscar-supervisor-agent',
            startTime=start_time
        )
        
        log_entries = []
        for event in response.get('events', []):
            message = event['message']
            log_entries.append({
                'timestamp': event['timestamp'],
                'message': message,
                'is_error': 'ERROR' in message,
                'is_bedrock_error': 'bedrock' in message.lower() or 'throttl' in message.lower(),
                'is_metrics_error': any(agent in message.lower() for agent in ['test-metrics', 'build-metrics', 'release-metrics', 'deployment-metrics'])
            })
            
        return log_entries
        
    except Exception as e:
        print(f"   ❌ Error checking logs: {e}")
        return []

def analyze_logs(log_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze log entries for patterns."""
    analysis = {
        'total_entries': len(log_entries),
        'error_entries': len([e for e in log_entries if e['is_error']]),
        'bedrock_errors': len([e for e in log_entries if e['is_bedrock_error']]),
        'metrics_errors': len([e for e in log_entries if e['is_metrics_error']]),
        'error_messages': []
    }
    
    # Collect unique error messages
    error_messages = set()
    for entry in log_entries:
        if entry['is_error']:
            # Extract key part of error message
            msg = entry['message']
            if 'Traceback' in msg:
                lines = msg.split('\n')
                for line in lines:
                    if 'Error:' in line or 'Exception:' in line:
                        error_messages.add(line.strip())
                        break
            else:
                error_messages.add(msg[:200])
    
    analysis['error_messages'] = list(error_messages)
    return analysis

def run_metrics_test():
    """Run comprehensive metrics vs knowledge base test."""
    print("🚀 Starting Metrics vs Knowledge Base Test")
    print("=" * 60)
    
    start_time = datetime.now()
    results = []
    test_id = 1
    
    # Test 1: Knowledge base queries (baseline)
    print("\n📚 Testing Knowledge Base Queries")
    print("-" * 40)
    for query in KNOWLEDGE_BASE_QUERIES:
        result = send_test_query(query, test_id, "knowledge_base")
        results.append(result)
        test_id += 1
        time.sleep(2)  # Give time between queries
    
    # Test 2: Metrics queries by agent type
    print("\n📊 Testing Metrics Queries")
    print("-" * 40)
    
    for agent_type, queries in TEST_METRICS_QUERIES.items():
        print(f"\n🔧 Testing {agent_type.replace('_', ' ').title()} Queries:")
        for query in queries:
            result = send_test_query(query, test_id, agent_type)
            results.append(result)
            test_id += 1
            time.sleep(3)  # Longer wait for metrics queries
    
    # Wait for async processing
    print("\n⏳ Waiting 45 seconds for async processing to complete...")
    time.sleep(45)
    
    # Get and analyze logs
    log_entries = get_recent_lambda_logs(10)
    log_analysis = analyze_logs(log_entries)
    
    # Generate comprehensive report
    print("\n📊 TEST RESULTS")
    print("=" * 60)
    
    # Overall stats
    total_tests = len(results)
    successful = [r for r in results if r['success']]
    failed = [r for r in results if not r['success']]
    
    print(f"Total Tests: {total_tests}")
    print(f"Successful: {len(successful)} ({len(successful)/total_tests*100:.1f}%)")
    print(f"Failed: {len(failed)} ({len(failed)/total_tests*100:.1f}%)")
    
    # Results by query type
    print(f"\n📈 Results by Query Type:")
    query_types = set(r['query_type'] for r in results)
    for qtype in query_types:
        type_results = [r for r in results if r['query_type'] == qtype]
        type_successful = [r for r in type_results if r['success']]
        success_rate = len(type_successful) / len(type_results) * 100
        print(f"   {qtype.replace('_', ' ').title()}: {len(type_successful)}/{len(type_results)} ({success_rate:.1f}%)")
    
    # Failed tests details
    if failed:
        print(f"\n❌ Failed Tests:")
        for result in failed:
            print(f"   Test {result['test_id']} ({result['query_type']}): {result['query']}")
            if 'error' in result:
                print(f"      Error: {result['error']}")
    
    # Log analysis
    print(f"\n🔍 Log Analysis:")
    print(f"   Total log entries: {log_analysis['total_entries']}")
    print(f"   Error entries: {log_analysis['error_entries']}")
    print(f"   Bedrock-related errors: {log_analysis['bedrock_errors']}")
    print(f"   Metrics-related errors: {log_analysis['metrics_errors']}")
    
    if log_analysis['error_messages']:
        print(f"\n🚨 Error Messages Found:")
        for i, error_msg in enumerate(log_analysis['error_messages'][:5], 1):
            print(f"   {i}. {error_msg}")
    
    # Response time analysis
    response_times = [r['response_time'] for r in successful]
    if response_times:
        avg_time = sum(response_times) / len(response_times)
        max_time = max(response_times)
        min_time = min(response_times)
        
        print(f"\n⏱️  Response Time Analysis:")
        print(f"   Average: {avg_time:.2f}s")
        print(f"   Min: {min_time:.2f}s") 
        print(f"   Max: {max_time:.2f}s")
    
    # Save detailed results
    test_results = {
        'results': results,
        'log_analysis': log_analysis,
        'summary': {
            'total': total_tests,
            'successful': len(successful),
            'failed': len(failed),
            'start_time': start_time.isoformat(),
            'end_time': datetime.now().isoformat()
        }
    }
    
    with open('metrics_test_results.json', 'w') as f:
        json.dump(test_results, f, indent=2)
    
    print(f"\n💾 Detailed results saved to: metrics_test_results.json")
    
    # Recommendations
    print(f"\n💡 Recommendations:")
    if log_analysis['bedrock_errors'] > 0:
        print("   - Bedrock errors detected - check for throttling or permission issues")
    if log_analysis['metrics_errors'] > 0:
        print("   - Metrics agent errors detected - check agent configurations")
    
    knowledge_base_success = len([r for r in results if r['query_type'] == 'knowledge_base' and r['success']])
    metrics_success = len([r for r in results if r['query_type'] != 'knowledge_base' and r['success']])
    
    if knowledge_base_success > metrics_success:
        print("   - Knowledge base queries more successful than metrics queries")
        print("   - Focus debugging on metrics agent integration")

if __name__ == "__main__":
    run_metrics_test()