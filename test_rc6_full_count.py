#!/usr/bin/env python3

import json
import boto3
import os
from datetime import datetime

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

def test_rc6_full_count():
    """Test to get the full count of RC 6 results by increasing the size limit"""
    
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    
    print(f"🧪 Testing RC 6 Full Count - Increasing Size Limit")
    print(f"{'='*60}")
    print(f"Hypothesis: We're only getting 49 RC 6 results because we're limited to")
    print(f"the newest 1000 results across ALL RCs, and only 49 of those are RC 6.")
    print(f"The dashboard shows 360 because it queries ALL RC 6 results.")
    print()
    
    # Test 1: Get RC 6 with much larger size limit
    test_payload_large = {
        'actionGroup': 'integration-test-metrics-actions',
        'function': 'get_integration_test_metrics',
        'parameters': [
            {'name': 'version', 'value': '3.2.0'},
            {'name': 'rc_numbers', 'value': '6'}
        ]
    }
    
    print(f"🚀 Test 1: RC 6 with current size limit (1000)")
    
    try:
        response = lambda_client.invoke(
            FunctionName='oscar-test-metrics-agent-new',
            InvocationType='RequestResponse',
            Payload=json.dumps(test_payload_large)
        )
        
        response_payload = json.loads(response['Payload'].read())
        
        if response.get('FunctionError'):
            print(f"❌ Function Error: {response_payload}")
            return
        
        # Extract results
        if 'response' in response_payload and 'functionResponse' in response_payload['response']:
            function_response = response_payload['response']['functionResponse']
            if 'responseBody' in function_response and 'TEXT' in function_response['responseBody']:
                body_data = json.loads(function_response['responseBody']['TEXT']['body'])
                
                total_results = body_data.get('total_results', 0)
                print(f"✅ RC 6 results with size 1000: {total_results}")
                
                if total_results > 0:
                    results = body_data.get('results', [])
                    
                    # Verify all are RC 6
                    rc_counts = {}
                    for result in results:
                        rc = result.get('rc_number')
                        rc_counts[rc] = rc_counts.get(rc, 0) + 1
                    
                    print(f"📊 RC breakdown: {rc_counts}")
                    
                    # Check build start times to see the time range
                    build_times = [result.get('build_start_time') for result in results if result.get('build_start_time')]
                    if build_times:
                        min_time = min(build_times)
                        max_time = max(build_times)
                        print(f"⏰ Build time range: {min_time} to {max_time}")
                        
                        # Convert to readable dates
                        min_date = datetime.fromtimestamp(min_time / 1000)
                        max_date = datetime.fromtimestamp(max_time / 1000)
                        print(f"📅 Date range: {min_date} to {max_date}")
                        
                        time_span = (max_time - min_time) / (1000 * 60 * 60)  # hours
                        print(f"⏱️  Time span: {time_span:.1f} hours")
                
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print(f"\n" + "="*60)
    print(f"🔍 Analysis:")
    print(f"If we're only getting 49 RC 6 results, it means:")
    print(f"1. Our query is correctly filtering for RC 6")
    print(f"2. But we're limited by the sort order (newest first)")
    print(f"3. The 360 results on the dashboard include older RC 6 results")
    print(f"4. We need to either:")
    print(f"   a) Increase the size limit significantly (to 5000+)")
    print(f"   b) Remove the sort by build_start_time when filtering by RC")
    print(f"   c) Use a different query strategy for RC-specific queries")

def test_without_sorting():
    """Test what happens if we modify the query to not sort by build_start_time"""
    print(f"\n🧪 Testing Query Strategy")
    print(f"{'='*60}")
    print(f"The issue is likely that we're sorting by build_start_time DESC")
    print(f"and then limiting to 1000 results, which gives us the newest")
    print(f"1000 results across ALL RCs, not the newest 1000 RC 6 results.")
    print()
    print(f"Solutions:")
    print(f"1. Increase size to 5000+ to capture all RC 6 results")
    print(f"2. Change query strategy: filter first, then sort")
    print(f"3. Use aggregation to get exact counts")
    print()
    print(f"Let's implement solution #1 first...")

if __name__ == "__main__":
    test_rc6_full_count()
    test_without_sorting()