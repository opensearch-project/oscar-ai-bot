#!/usr/bin/env python3

import json
import boto3
import os
from datetime import datetime, timedelta

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

def test_query_strategy_debug():
    """Debug our query strategy to see if we're filtering first or sorting first"""
    
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    
    print(f"🔍 Debugging Query Strategy - Filter First vs Sort First")
    print(f"{'='*80}")
    print(f"Dashboard shows: 377 RC 6 results in last 24 hours")
    print(f"We're getting: 49 RC 6 results")
    print(f"Theory: We're sorting globally first, then filtering")
    print()
    
    # Test 1: Get all version 3.2.0 results to see the distribution
    print(f"🧪 Test 1: All version 3.2.0 results (to see RC distribution)")
    
    test_payload_all = {
        'actionGroup': 'integration-test-metrics-actions',
        'function': 'get_integration_test_metrics',
        'parameters': [
            {'name': 'version', 'value': '3.2.0'}
        ]
    }
    
    try:
        response = lambda_client.invoke(
            FunctionName='oscar-test-metrics-agent-new',
            InvocationType='RequestResponse',
            Payload=json.dumps(test_payload_all)
        )
        
        response_payload = json.loads(response['Payload'].read())
        
        if not response.get('FunctionError'):
            if 'response' in response_payload and 'functionResponse' in response_payload['response']:
                function_response = response_payload['response']['functionResponse']
                if 'responseBody' in function_response and 'TEXT' in function_response['responseBody']:
                    body_data = json.loads(function_response['responseBody']['TEXT']['body'])
                    
                    results = body_data.get('results', [])
                    total_results = body_data.get('total_results', 0)
                    
                    print(f"✅ Got {total_results} total results")
                    
                    # Analyze RC distribution in the results we got
                    rc_counts = {}
                    time_analysis = {}
                    
                    for result in results:
                        rc = result.get('rc_number')
                        timestamp = result.get('build_start_time')
                        
                        if rc is not None:
                            rc_counts[rc] = rc_counts.get(rc, 0) + 1
                            
                            if rc not in time_analysis:
                                time_analysis[rc] = []
                            if timestamp:
                                time_analysis[rc].append(timestamp)
                    
                    print(f"📊 RC Distribution in results: {dict(sorted(rc_counts.items()))}")
                    
                    # Check time ranges for each RC
                    print(f"\n⏰ Time Analysis by RC:")
                    for rc in sorted(time_analysis.keys()):
                        timestamps = time_analysis[rc]
                        if timestamps:
                            min_ts = min(timestamps)
                            max_ts = max(timestamps)
                            min_date = datetime.fromtimestamp(min_ts / 1000)
                            max_date = datetime.fromtimestamp(max_ts / 1000)
                            
                            # Check if this is within last 24 hours
                            now = datetime.now()
                            hours_ago_24 = now - timedelta(hours=24)
                            
                            recent_count = sum(1 for ts in timestamps if datetime.fromtimestamp(ts / 1000) >= hours_ago_24)
                            
                            print(f"   RC {rc}: {len(timestamps)} total, {recent_count} in last 24h")
                            print(f"          Range: {min_date} to {max_date}")
                    
                    # Key insight: Check if we're hitting the size limit
                    if total_results >= 10000:
                        print(f"\n❗ CRITICAL: We hit the 10,000 result limit!")
                        print(f"❗ This means we're getting the newest 10,000 results across ALL RCs")
                        print(f"❗ Then filtering for RC 6 within those 10,000 results")
                        print(f"❗ But there might be more RC 6 results outside the newest 10,000!")
                    elif total_results >= 1000:
                        print(f"\n❗ We got {total_results} results (hit our size limit)")
                        print(f"❗ This suggests we're still limiting globally before filtering")
                    
    except Exception as e:
        print(f"❌ Error in test 1: {e}")
    
    # Test 2: Try to get RC 6 results with a different approach
    print(f"\n🧪 Test 2: RC 6 specific query")
    
    test_payload_rc6 = {
        'actionGroup': 'integration-test-metrics-actions',
        'function': 'get_integration_test_metrics',
        'parameters': [
            {'name': 'version', 'value': '3.2.0'},
            {'name': 'rc_numbers', 'value': '6'}
        ]
    }
    
    try:
        response = lambda_client.invoke(
            FunctionName='oscar-test-metrics-agent-new',
            InvocationType='RequestResponse',
            Payload=json.dumps(test_payload_rc6)
        )
        
        response_payload = json.loads(response['Payload'].read())
        
        if not response.get('FunctionError'):
            if 'response' in response_payload and 'functionResponse' in response_payload['response']:
                function_response = response_payload['response']['functionResponse']
                if 'responseBody' in function_response and 'TEXT' in function_response['responseBody']:
                    body_data = json.loads(function_response['responseBody']['TEXT']['body'])
                    
                    total_results = body_data.get('total_results', 0)
                    results = body_data.get('results', [])
                    
                    print(f"✅ RC 6 query returned: {total_results} results")
                    
                    if results:
                        # Check time range of RC 6 results
                        timestamps = [r.get('build_start_time') for r in results if r.get('build_start_time')]
                        
                        if timestamps:
                            min_ts = min(timestamps)
                            max_ts = max(timestamps)
                            min_date = datetime.fromtimestamp(min_ts / 1000)
                            max_date = datetime.fromtimestamp(max_ts / 1000)
                            
                            print(f"⏰ RC 6 time range: {min_date} to {max_date}")
                            
                            # Check how many are in last 24 hours
                            now = datetime.now()
                            hours_ago_24 = now - timedelta(hours=24)
                            
                            recent_count = sum(1 for ts in timestamps if datetime.fromtimestamp(ts / 1000) >= hours_ago_24)
                            print(f"📊 RC 6 results in last 24h: {recent_count} out of {len(timestamps)}")
                            
                            if recent_count < 377:
                                print(f"❗ We're missing {377 - recent_count} RC 6 results from last 24h!")
                                print(f"❗ This confirms we're not getting all RC 6 results")
                    
    except Exception as e:
        print(f"❌ Error in test 2: {e}")

def analyze_query_issue():
    """Analyze what's wrong with our query approach"""
    print(f"\n🔍 Query Issue Analysis:")
    print(f"{'='*80}")
    print(f"Current approach:")
    print(f"1. Query with version=3.2.0 AND rc_number=6")
    print(f"2. Sort by build_start_time DESC")
    print(f"3. Limit to 10,000 results")
    print()
    print(f"Expected behavior:")
    print(f"- OpenSearch should find ALL records where version=3.2.0 AND rc_number=6")
    print(f"- Then sort those RC 6 records by build_start_time DESC")
    print(f"- Then return up to 10,000 of those RC 6 records")
    print()
    print(f"Actual behavior (suspected):")
    print(f"- OpenSearch finds ALL records where version=3.2.0")
    print(f"- Sorts ALL version 3.2.0 records by build_start_time DESC")
    print(f"- Takes the first 10,000 newest records across ALL RCs")
    print(f"- Then filters those 10,000 for rc_number=6")
    print(f"- Only 49 of those 10,000 newest records happen to be RC 6")
    print()
    print(f"Solution:")
    print(f"- The query structure should be correct, but maybe OpenSearch")
    print(f"  is not executing it as expected")
    print(f"- We might need to use a different query approach")
    print(f"- Or there might be an issue with how we're building the query")

if __name__ == "__main__":
    test_query_strategy_debug()
    analyze_query_issue()