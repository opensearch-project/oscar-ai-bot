#!/usr/bin/env python3

import json
import boto3
import os
from datetime import datetime

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

def test_simple_rc_query():
    """Test a simple RC query to see if our fix worked"""
    
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    
    print(f"🧪 Testing Simple RC Query After Fix")
    print(f"{'='*60}")
    
    # Test the basic RC 6 query
    test_payload = {
        'actionGroup': 'integration-test-metrics-actions',
        'function': 'get_integration_test_metrics',
        'parameters': [
            {'name': 'version', 'value': '3.2.0'},
            {'name': 'rc_numbers', 'value': '6'}
        ]
    }
    
    print(f"🚀 Testing RC 6 query...")
    
    try:
        response = lambda_client.invoke(
            FunctionName='oscar-test-metrics-agent-new',
            InvocationType='RequestResponse',
            Payload=json.dumps(test_payload)
        )
        
        response_payload = json.loads(response['Payload'].read())
        
        print(f"📋 Raw response keys: {list(response_payload.keys())}")
        
        if response.get('FunctionError'):
            print(f"❌ Function Error: {response_payload}")
            
            # Check if it's a syntax error or runtime error
            error_type = response_payload.get('errorType', 'Unknown')
            error_message = response_payload.get('errorMessage', 'No message')
            
            print(f"Error Type: {error_type}")
            print(f"Error Message: {error_message}")
            
            if 'stackTrace' in response_payload:
                print(f"Stack Trace:")
                for line in response_payload['stackTrace']:
                    print(f"  {line}")
            
            return
        
        # Check response structure
        if 'response' in response_payload:
            print(f"✅ Response structure looks good")
            
            if 'functionResponse' in response_payload['response']:
                function_response = response_payload['response']['functionResponse']
                
                if 'responseBody' in function_response and 'TEXT' in function_response['responseBody']:
                    body_text = function_response['responseBody']['TEXT']['body']
                    print(f"📋 Response body length: {len(body_text)} characters")
                    
                    try:
                        body_data = json.loads(body_text)
                        
                        print(f"✅ Successfully parsed response JSON")
                        print(f"📊 Response keys: {list(body_data.keys())}")
                        
                        total_results = body_data.get('total_results', 0)
                        agent_type = body_data.get('agent_type')
                        data_source = body_data.get('data_source')
                        
                        print(f"📊 Results Summary:")
                        print(f"   Agent Type: {agent_type}")
                        print(f"   Data Source: {data_source}")
                        print(f"   Total Results: {total_results}")
                        
                        if total_results > 0:
                            print(f"🎉 SUCCESS! Got {total_results} RC 6 results!")
                            
                            results = body_data.get('results', [])
                            if results:
                                # Check first result
                                first_result = results[0]
                                print(f"📋 First result:")
                                print(f"   Component: {first_result.get('component')}")
                                print(f"   RC Number: {first_result.get('rc_number')}")
                                print(f"   Version: {first_result.get('version')}")
                                print(f"   Build Result: {first_result.get('component_build_result')}")
                        else:
                            print(f"❌ No results returned")
                            
                            # Check if there's an error in the response
                            if 'error' in body_data:
                                print(f"❌ Error in response: {body_data['error']}")
                        
                    except json.JSONDecodeError as e:
                        print(f"❌ Failed to parse response JSON: {e}")
                        print(f"📋 Raw response body: {body_text[:500]}...")
                else:
                    print(f"❌ Unexpected response structure - no responseBody/TEXT")
            else:
                print(f"❌ Unexpected response structure - no functionResponse")
        else:
            print(f"❌ Unexpected response structure - no response")
            print(f"📋 Full response: {json.dumps(response_payload, indent=2)}")
        
    except Exception as e:
        print(f"❌ Exception during test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_simple_rc_query()