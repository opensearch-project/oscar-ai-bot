#!/usr/bin/env python3

import json
import boto3
import os
from datetime import datetime, timedelta

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

def test_version_formats():
    """Test different version formats to see if that's the issue"""
    
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    
    print(f"🔍 Testing Different Version Formats")
    print(f"{'='*80}")
    print(f"Theory: Dashboard might use different version format")
    print(f"Testing: 3.2.0, 3.2, 3.2.0-SNAPSHOT, etc.")
    print()
    
    version_formats = [
        '3.2.0',
        '3.2',
        '3.2.0-SNAPSHOT',
        '3.2-SNAPSHOT',
        '3.2.0-rc6',
        '3.2.0-RC6'
    ]
    
    for version in version_formats:
        print(f"🧪 Testing version: '{version}'")
        
        test_payload = {
            'actionGroup': 'integration-test-metrics-actions',
            'function': 'get_integration_test_metrics',
            'parameters': [
                {'name': 'version', 'value': version},
                {'name': 'rc_numbers', 'value': '6'}
            ]
        }
        
        try:
            response = lambda_client.invoke(
                FunctionName='oscar-test-metrics-agent-new',
                InvocationType='RequestResponse',
                Payload=json.dumps(test_payload)
            )
            
            response_payload = json.loads(response['Payload'].read())
            
            if response.get('FunctionError'):
                print(f"   ❌ Error: {response_payload.get('errorMessage', 'Unknown error')}")
                continue
            
            # Extract results
            if 'response' in response_payload and 'functionResponse' in response_payload['response']:
                function_response = response_payload['response']['functionResponse']
                if 'responseBody' in function_response and 'TEXT' in function_response['responseBody']:
                    body_data = json.loads(function_response['responseBody']['TEXT']['body'])
                    
                    total_results = body_data.get('total_results', 0)
                    print(f"   ✅ Results: {total_results}")
                    
                    if total_results > 49:
                        print(f"   🎯 FOUND MORE RESULTS! Version '{version}' has {total_results} RC 6 results!")
                        
                        # Analyze the results
                        results = body_data.get('results', [])
                        if results:
                            # Check timestamp range
                            timestamps = [r.get('build_start_time') for r in results if r.get('build_start_time')]
                            if timestamps:
                                min_ts = min(timestamps)
                                max_ts = max(timestamps)
                                min_date = datetime.fromtimestamp(min_ts / 1000)
                                max_date = datetime.fromtimestamp(max_ts / 1000)
                                
                                print(f"   📅 Date range: {min_date} to {max_date}")
                                
                                # Check how many in last 24h
                                now = datetime.now()
                                hours_ago_24 = now - timedelta(hours=24)
                                recent_count = sum(1 for ts in timestamps 
                                                 if datetime.fromtimestamp(ts / 1000) >= hours_ago_24)
                                print(f"   ⏰ In last 24h: {recent_count}")
                    
                    elif total_results == 0:
                        print(f"   ❌ No results for version '{version}'")
                    else:
                        print(f"   ✅ Same as 3.2.0: {total_results} results")
            
        except Exception as e:
            print(f"   ❌ Exception: {e}")
        
        print()
    
    # Also test without version filter to see all available versions
    print(f"🔍 Testing without version filter to see all available versions...")
    
    test_payload_no_version = {
        'actionGroup': 'integration-test-metrics-actions',
        'function': 'get_integration_test_metrics',
        'parameters': [
            {'name': 'rc_numbers', 'value': '6'}
        ]
    }
    
    try:
        response = lambda_client.invoke(
            FunctionName='oscar-test-metrics-agent-new',
            InvocationType='RequestResponse',
            Payload=json.dumps(test_payload_no_version)
        )
        
        response_payload = json.loads(response['Payload'].read())
        
        if not response.get('FunctionError'):
            if 'response' in response_payload and 'functionResponse' in response_payload['response']:
                function_response = response_payload['response']['functionResponse']
                if 'responseBody' in function_response and 'TEXT' in function_response['responseBody']:
                    body_data = json.loads(function_response['responseBody']['TEXT']['body'])
                    
                    total_results = body_data.get('total_results', 0)
                    results = body_data.get('results', [])
                    
                    print(f"✅ RC 6 results (all versions): {total_results}")
                    
                    if results:
                        # Analyze version distribution
                        version_counts = {}
                        for result in results:
                            version = result.get('version')
                            if version:
                                version_counts[version] = version_counts.get(version, 0) + 1
                        
                        print(f"📊 Version distribution in RC 6 results:")
                        for version, count in sorted(version_counts.items()):
                            print(f"   {version}: {count} results")
                        
                        if total_results > 49:
                            print(f"\n🎯 FOUND THE ISSUE! There are {total_results} total RC 6 results")
                            print(f"🎯 But only 49 are for version 3.2.0")
                            print(f"🎯 The dashboard might be showing ALL RC 6 results, not just 3.2.0!")
    
    except Exception as e:
        print(f"❌ Error in no-version test: {e}")

if __name__ == "__main__":
    test_version_formats()