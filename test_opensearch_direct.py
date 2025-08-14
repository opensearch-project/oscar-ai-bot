#!/usr/bin/env python3

import json
import boto3
import os
from datetime import datetime

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

def test_opensearch_direct_query():
    """Test OpenSearch directly to understand the data structure"""
    
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    
    print(f"🔍 Testing OpenSearch Direct Query to Understand Data Structure")
    print(f"{'='*80}")
    
    # Let's create a custom test that bypasses our filtering logic
    # and queries OpenSearch more directly
    
    test_cases = [
        {
            'name': 'Count all version 3.2.0 results',
            'payload': {
                'actionGroup': 'integration-test-metrics-actions',
                'function': 'get_integration_test_metrics',
                'parameters': [
                    {'name': 'version', 'value': '3.2.0'}
                ]
            }
        },
        {
            'name': 'Test RC as integer instead of string',
            'payload': {
                'actionGroup': 'integration-test-metrics-actions',
                'function': 'get_integration_test_metrics',
                'parameters': [
                    {'name': 'version', 'value': '3.2.0'},
                    {'name': 'rc_numbers', 'value': '6'}
                ]
            }
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n🧪 Test {i}: {test_case['name']}")
        print(f"Payload: {json.dumps(test_case['payload'], indent=2)}")
        
        try:
            response = lambda_client.invoke(
                FunctionName='oscar-test-metrics-agent-new',
                InvocationType='RequestResponse',
                Payload=json.dumps(test_case['payload'])
            )
            
            response_payload = json.loads(response['Payload'].read())
            
            if response.get('FunctionError'):
                print(f"❌ Function Error: {response_payload}")
                continue
            
            # Extract results
            if 'response' in response_payload and 'functionResponse' in response_payload['response']:
                function_response = response_payload['response']['functionResponse']
                if 'responseBody' in function_response and 'TEXT' in function_response['responseBody']:
                    body_data = json.loads(function_response['responseBody']['TEXT']['body'])
                    
                    total_results = body_data.get('total_results', 0)
                    results = body_data.get('results', [])
                    
                    print(f"✅ Total Results: {total_results}")
                    
                    if results:
                        # Analyze RC distribution
                        rc_counts = {}
                        version_counts = {}
                        
                        for result in results:
                            rc = result.get('rc_number')
                            version = result.get('version')
                            
                            if rc is not None:
                                rc_counts[rc] = rc_counts.get(rc, 0) + 1
                            if version:
                                version_counts[version] = version_counts.get(version, 0) + 1
                        
                        print(f"📊 RC Distribution: {dict(sorted(rc_counts.items()))}")
                        print(f"📊 Version Distribution: {version_counts}")
                        
                        # Show RC 6 specifically
                        rc6_count = rc_counts.get(6, 0) + rc_counts.get('6', 0)
                        print(f"🎯 RC 6 Count: {rc6_count}")
                        
                        # If this is the version-only query, let's see what the total possible RC 6 count could be
                        if test_case['name'] == 'Count all version 3.2.0 results':
                            print(f"📈 If we had unlimited size, RC 6 could have up to {rc6_count} results in the first {total_results} results")
                            
                            # Check if we hit the size limit
                            if total_results >= 5000:
                                print(f"⚠️  Hit size limit of 5000 - there might be more results")
                            
                            # Estimate total RC 6 results
                            if rc6_count > 0:
                                rc6_percentage = rc6_count / total_results
                                print(f"📊 RC 6 represents {rc6_percentage:.1%} of results")
                                print(f"💡 If dashboard shows 360 RC 6 results, total dataset might be ~{360/rc6_percentage:.0f} results")
                    
        except Exception as e:
            print(f"❌ Error: {e}")
    
    print(f"\n🔍 Analysis:")
    print(f"The issue might be:")
    print(f"1. Our size limit is still too small")
    print(f"2. The dashboard is querying a different index or time range")
    print(f"3. There are additional filters we're not seeing")
    print(f"4. The RC number field format is different than expected")

def check_actual_opensearch_response():
    """Check what OpenSearch actually returns vs what we process"""
    print(f"\n🔍 Checking Actual OpenSearch Response")
    print(f"{'='*80}")
    print(f"We need to check the CloudWatch logs to see:")
    print(f"1. The exact query sent to OpenSearch")
    print(f"2. The raw response from OpenSearch")
    print(f"3. How many total hits OpenSearch found")
    print(f"4. Whether we're processing all the results correctly")
    print()
    print(f"Look for these log entries in CloudWatch:")
    print(f"- 📋 INTEGRATION_TEST_QUERY: Complete query body")
    print(f"- ✅ INTEGRATION_TEST_QUERY: Query completed - Total matches: X, Returned: Y")
    print(f"- 📋 INTEGRATION_TEST_QUERY: RC numbers found in first 10 results")

if __name__ == "__main__":
    test_opensearch_direct_query()
    check_actual_opensearch_response()