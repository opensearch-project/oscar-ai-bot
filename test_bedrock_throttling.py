#!/usr/bin/env python3
"""
Test script to identify Bedrock throttling and other errors.
"""

import json
import time
import boto3
import requests
from datetime import datetime
from typing import List, Dict, Any

# Test queries of varying complexity
TEST_QUERIES = [
    "Hello",
    "Hi there",
    "What's the weather?",
    "Tell me about OpenSearch",
    "How do I configure OpenSearch clusters?",
    "What are the best practices for OpenSearch performance?",
    "Can you help me troubleshoot OpenSearch indexing issues?",
    "Explain OpenSearch security features in detail",
    "What are the latest OpenSearch releases and their features?",
    "How do I set up cross-cluster replication in OpenSearch?"
]

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

def send_test_query(query: str, test_id: int) -> Dict[str, Any]:
    """Send a test query and measure response."""
    print(f"\n🧪 Test {test_id}: '{query}'")
    
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
            timeout=10
        )
        
        response_time = time.time() - start_time
        
        result = {
            "test_id": test_id,
            "query": query,
            "status_code": response.status_code,
            "response_time": response_time,
            "response_body": response.text,
            "timestamp": datetime.now().isoformat(),
            "success": response.status_code == 200
        }
        
        print(f"   ✅ Status: {response.status_code}, Time: {response_time:.2f}s")
        return result
        
    except Exception as e:
        response_time = time.time() - start_time
        result = {
            "test_id": test_id,
            "query": query,
            "status_code": None,
            "response_time": response_time,
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
            "success": False
        }
        
        print(f"   ❌ Error: {e}")
        return result

def check_lambda_logs(start_time: str) -> List[str]:
    """Check Lambda logs for errors since start_time."""
    print("\n📋 Checking Lambda logs for errors...")
    
    try:
        logs_client = boto3.client('logs', region_name='us-east-1')
        
        # Get log events since start_time
        response = logs_client.filter_log_events(
            logGroupName='/aws/lambda/oscar-supervisor-agent',
            startTime=int(time.mktime(time.strptime(start_time, "%Y-%m-%dT%H:%M:%S")) * 1000),
            filterPattern='ERROR'
        )
        
        errors = []
        for event in response.get('events', []):
            errors.append(event['message'])
            
        return errors
        
    except Exception as e:
        print(f"   ❌ Error checking logs: {e}")
        return []

def run_throttling_test():
    """Run comprehensive throttling test."""
    print("🚀 Starting Bedrock Throttling Test")
    print("=" * 50)
    
    start_time = datetime.now().isoformat()
    results = []
    
    # Test 1: Rapid fire queries (potential throttling)
    print("\n📈 Test 1: Rapid Fire Queries (0.5s intervals)")
    for i, query in enumerate(TEST_QUERIES[:5], 1):
        result = send_test_query(query, i)
        results.append(result)
        time.sleep(0.5)  # Short interval
    
    # Test 2: Spaced queries (normal usage)
    print("\n⏱️  Test 2: Spaced Queries (3s intervals)")
    for i, query in enumerate(TEST_QUERIES[5:], 6):
        result = send_test_query(query, i)
        results.append(result)
        time.sleep(3)  # Normal interval
    
    # Wait for async processing to complete
    print("\n⏳ Waiting 30 seconds for async processing...")
    time.sleep(30)
    
    # Check logs for errors
    errors = check_lambda_logs(start_time)
    
    # Generate report
    print("\n📊 TEST RESULTS")
    print("=" * 50)
    
    successful = [r for r in results if r['success']]
    failed = [r for r in results if not r['success']]
    
    print(f"Total Tests: {len(results)}")
    print(f"Successful: {len(successful)}")
    print(f"Failed: {len(failed)}")
    
    if failed:
        print("\n❌ Failed Tests:")
        for result in failed:
            print(f"   Test {result['test_id']}: {result['query']}")
            if 'error' in result:
                print(f"      Error: {result['error']}")
    
    if errors:
        print(f"\n🔍 Lambda Errors Found: {len(errors)}")
        for error in errors[:5]:  # Show first 5 errors
            print(f"   {error[:200]}...")
    else:
        print("\n✅ No Lambda errors found")
    
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
    with open('throttling_test_results.json', 'w') as f:
        json.dump({
            'results': results,
            'errors': errors,
            'summary': {
                'total': len(results),
                'successful': len(successful),
                'failed': len(failed),
                'start_time': start_time,
                'end_time': datetime.now().isoformat()
            }
        }, f, indent=2)
    
    print(f"\n💾 Detailed results saved to: throttling_test_results.json")

if __name__ == "__main__":
    run_throttling_test()