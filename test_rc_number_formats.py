#!/usr/bin/env python3

import json
import boto3
import os
from datetime import datetime

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

def test_rc_number_formats():
    """Test different RC number formats to see if that's causing the issue"""
    
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    
    print(f"🔍 Testing Different RC Number Formats")
    print(f"{'='*80}")
    print(f"Hypothesis: The RC number might be stored in a different format")
    print(f"than what we're querying for (6 vs '6' vs 'RC6' vs 'rc6')")
    print()
    
    # Test different RC number formats
    test_cases = [
        {
            'name': 'RC as string "6"',
            'rc_value': '6'
        },
        {
            'name': 'RC as integer 6',
            'rc_value': 6
        },
        {
            'name': 'RC as "RC6"',
            'rc_value': 'RC6'
        },
        {
            'name': 'RC as "rc6"',
            'rc_value': 'rc6'
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"🧪 Test {i}: {test_case['name']}")
        
        test_payload = {
            'actionGroup': 'integration-test-metrics-actions',
            'function': 'get_integration_test_metrics',
            'parameters': [
                {'name': 'version', 'value': '3.2.0'},
                {'name': 'rc_numbers', 'value': str(test_case['rc_value'])}
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
                print(f"❌ Function Error: {response_payload}")
                continue
            
            # Extract results
            if 'response' in response_payload and 'functionResponse' in response_payload['response']:
                function_response = response_payload['response']['functionResponse']
                if 'responseBody' in function_response and 'TEXT' in function_response['responseBody']:
                    body_data = json.loads(function_response['responseBody']['TEXT']['body'])
                    
                    total_results = body_data.get('total_results', 0)
                    print(f"   Results: {total_results}")
                    
                    if total_results > 0:
                        results = body_data.get('results', [])
                        
                        # Check what RC values we actually got back
                        rc_values = set()
                        for result in results[:5]:  # Check first 5
                            rc = result.get('rc_number')
                            if rc is not None:
                                rc_values.add(str(rc))
                        
                        print(f"   Sample RC values returned: {sorted(rc_values)}")
                        
                        if total_results > 49:
                            print(f"   🎯 FOUND MORE RESULTS! This format works better!")
                    else:
                        print(f"   No results found")
                
        except Exception as e:
            print(f"❌ Error: {e}")
        
        print()
    
    # Also test without RC filter to see all RC formats in the data
    print(f"🔍 Testing without RC filter to see all RC formats in data...")
    
    test_payload_no_rc = {
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
            Payload=json.dumps(test_payload_no_rc)
        )
        
        response_payload = json.loads(response['Payload'].read())
        
        if not response.get('FunctionError'):
            if 'response' in response_payload and 'functionResponse' in response_payload['response']:
                function_response = response_payload['response']['functionResponse']
                if 'responseBody' in function_response and 'TEXT' in function_response['responseBody']:
                    body_data = json.loads(function_response['responseBody']['TEXT']['body'])
                    
                    results = body_data.get('results', [])
                    
                    # Collect all unique RC values and their types
                    rc_analysis = {}
                    
                    for result in results:
                        rc = result.get('rc_number')
                        if rc is not None:
                            rc_str = str(rc)
                            rc_type = type(rc).__name__
                            
                            if rc_str not in rc_analysis:
                                rc_analysis[rc_str] = {
                                    'count': 0,
                                    'type': rc_type,
                                    'sample_value': rc
                                }
                            rc_analysis[rc_str]['count'] += 1
                    
                    print(f"📊 RC Value Analysis from {len(results)} results:")
                    print(f"{'RC Value':<10} {'Type':<10} {'Count':<8} {'Sample'}")
                    print(f"-" * 40)
                    
                    for rc_str in sorted(rc_analysis.keys(), key=lambda x: int(x) if x.isdigit() else 999):
                        info = rc_analysis[rc_str]
                        print(f"{rc_str:<10} {info['type']:<10} {info['count']:<8} {repr(info['sample_value'])}")
                    
                    # Check if there are any RC 6 variants
                    rc6_variants = [k for k in rc_analysis.keys() if '6' in str(k)]
                    if rc6_variants:
                        print(f"\n🎯 RC 6 variants found: {rc6_variants}")
                        total_rc6 = sum(rc_analysis[k]['count'] for k in rc6_variants)
                        print(f"🎯 Total RC 6 results across all variants: {total_rc6}")
                        
                        if total_rc6 > 49:
                            print(f"✅ Found more RC 6 results! The issue might be RC format variants.")
                    
    except Exception as e:
        print(f"❌ Error in no-RC test: {e}")

if __name__ == "__main__":
    test_rc_number_formats()