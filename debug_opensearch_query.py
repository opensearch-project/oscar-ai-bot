#!/usr/bin/env python3

import json
import boto3
import os
from datetime import datetime, timedelta

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

def check_cloudwatch_logs_detailed():
    """Check CloudWatch logs for the detailed query information"""
    
    logs_client = boto3.client('logs', region_name='us-east-1')
    log_group = '/aws/lambda/oscar-test-metrics-agent-new'
    
    # Get logs from the last 10 minutes
    end_time = datetime.now()
    start_time = end_time - timedelta(minutes=10)
    
    print(f"🔍 Checking CloudWatch logs for detailed query information")
    print(f"Log Group: {log_group}")
    print(f"Time Range: {start_time.strftime('%H:%M:%S')} - {end_time.strftime('%H:%M:%S')}")
    print(f"{'='*80}")
    
    try:
        # Get log events
        response = logs_client.filter_log_events(
            logGroupName=log_group,
            startTime=int(start_time.timestamp() * 1000),
            endTime=int(end_time.timestamp() * 1000),
            filterPattern="INTEGRATION_TEST_QUERY"
        )
        
        events = response.get('events', [])
        print(f"Found {len(events)} log events with INTEGRATION_TEST_QUERY")
        print()
        
        for event in events:
            timestamp = datetime.fromtimestamp(event['timestamp'] / 1000)
            message = event['message']
            print(f"[{timestamp.strftime('%H:%M:%S')}] {message}")
            print()
        
        if not events:
            print("❌ No INTEGRATION_TEST_QUERY log events found!")
            print("This could mean:")
            print("1. The logs haven't propagated yet (wait a few minutes)")
            print("2. The function didn't execute our new logging code")
            print("3. There was an error before the logging started")
            
    except Exception as e:
        print(f"❌ Error checking CloudWatch logs: {e}")
        print("You may need to check the logs manually in the AWS Console")

def test_direct_opensearch_query():
    """Test a direct OpenSearch query to see what we should be getting"""
    
    print(f"\n🔍 Testing Direct OpenSearch Query")
    print(f"{'='*80}")
    
    # Let's create a test that calls our Lambda with more detailed logging
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    
    # Test with a simpler query first - just version filter
    test_payload = {
        'actionGroup': 'integration-test-metrics-actions',
        'function': 'get_integration_test_metrics',
        'parameters': [
            {'name': 'version', 'value': '3.2.0'}
        ]
    }
    
    print(f"🧪 Testing with version-only filter (should get more results)")
    print(f"Payload: {json.dumps(test_payload, indent=2)}")
    
    try:
        response = lambda_client.invoke(
            FunctionName='oscar-test-metrics-agent-new',
            InvocationType='RequestResponse',
            Payload=json.dumps(test_payload)
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
                print(f"✅ Version-only query returned: {total_results} results")
                
                if total_results > 0:
                    results = body_data.get('results', [])
                    
                    # Count RC numbers in version-only results
                    rc_counts = {}
                    for result in results:
                        rc = result.get('rc_number')
                        if rc:
                            rc_counts[rc] = rc_counts.get(rc, 0) + 1
                    
                    print(f"📊 RC breakdown in version-only results: {rc_counts}")
                    
                    # Check if RC 6 exists
                    rc6_count = rc_counts.get(6, 0) + rc_counts.get('6', 0)
                    print(f"🎯 RC 6 count in version-only results: {rc6_count}")
                    
                    if rc6_count == 0:
                        print(f"❌ No RC 6 results found even in version-only query!")
                        print(f"This suggests the data might be stored differently than expected")
                        
                        # Show sample RC values
                        sample_rcs = list(rc_counts.keys())[:10]
                        print(f"📋 Sample RC values found: {sample_rcs}")
                    else:
                        print(f"✅ RC 6 exists in the data, so the filtering issue is in our RC filter")
                
    except Exception as e:
        print(f"❌ Error testing direct query: {e}")

def analyze_query_structure():
    """Analyze what our query structure should look like"""
    
    print(f"\n🔍 Analyzing Query Structure Issues")
    print(f"{'='*80}")
    
    print(f"Expected query structure for RC 6, Version 3.2.0:")
    print(f"1. Version filter: match_phrase on 'version' field with '3.2.0'")
    print(f"2. RC filter: match_phrase on 'rc_number' field with '6' (as string)")
    print(f"3. Size: 1000 (should be enough for 360 results)")
    print(f"4. Sort: by build_start_time desc (newest first)")
    print()
    
    print(f"Potential issues:")
    print(f"1. RC number field might be stored as integer, not string")
    print(f"2. RC number field might have a different name")
    print(f"3. Version field might have different format")
    print(f"4. There might be additional implicit filters")
    print(f"5. The index might have different data than the dashboard")
    print()
    
    print(f"Next steps:")
    print(f"1. Check CloudWatch logs for the exact query sent to OpenSearch")
    print(f"2. Check what OpenSearch actually returned")
    print(f"3. Test with different RC number formats (string vs int)")
    print(f"4. Test without RC filter to see total available data")

if __name__ == "__main__":
    check_cloudwatch_logs_detailed()
    test_direct_opensearch_query()
    analyze_query_structure()