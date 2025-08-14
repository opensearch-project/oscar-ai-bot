#!/usr/bin/env python3

import json
import boto3
import os
from datetime import datetime

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

def test_simplified_metrics():
    """Test the simplified metrics approach with direct parameter passing."""
    
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    
    test_cases = [
        {
            'name': 'Integration Test - Version Only',
            'function': 'oscar-test-metrics-agent-new',
            'payload': {
                'actionGroup': 'metrics-query',
                'function': 'get_integration_test_metrics',
                'parameters': [
                    {'name': 'version', 'value': '3.2.0'}
                ]
            }
        },
        {
            'name': 'Integration Test - With Status Filter',
            'function': 'oscar-test-metrics-agent-new',
            'payload': {
                'actionGroup': 'metrics-query',
                'function': 'get_integration_test_metrics',
                'parameters': [
                    {'name': 'version', 'value': '3.2.0'},
                    {'name': 'status_filter', 'value': 'failed'}
                ]
            }
        },
        {
            'name': 'Build Metrics - With Components',
            'function': 'oscar-build-metrics-agent-new',
            'payload': {
                'actionGroup': 'metrics-query',
                'function': 'get_build_metrics',
                'parameters': [
                    {'name': 'version', 'value': '3.2.0'},
                    {'name': 'components', 'value': 'OpenSearch,OpenSearch-Dashboards'}
                ]
            }
        },
        {
            'name': 'Release Metrics - Simple Query',
            'function': 'oscar-release-metrics-agent-new',
            'payload': {
                'actionGroup': 'metrics-query',
                'function': 'get_release_metrics',
                'parameters': [
                    {'name': 'version', 'value': '3.2.0'}
                ]
            }
        }
    ]
    
    print(f"🧪 Testing Simplified Metrics Approach")
    print(f"{'='*60}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()
    
    results = []
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"Test {i}: {test_case['name']}")
        print(f"Function: {test_case['function']}")
        
        try:
            # Invoke the Lambda function
            response = lambda_client.invoke(
                FunctionName=test_case['function'],
                InvocationType='RequestResponse',
                Payload=json.dumps(test_case['payload'])
            )
            
            # Parse response
            response_payload = json.loads(response['Payload'].read())
            
            # Check for errors
            if response.get('FunctionError'):
                print(f"❌ Function Error: {response_payload}")
                results.append({
                    'test': test_case['name'],
                    'status': 'FAILED',
                    'error': response_payload
                })
                continue
            
            # Extract the actual response from Bedrock format
            if 'response' in response_payload and 'functionResponse' in response_payload['response']:
                function_response = response_payload['response']['functionResponse']
                if 'responseBody' in function_response and 'TEXT' in function_response['responseBody']:
                    try:
                        body_data = json.loads(function_response['responseBody']['TEXT']['body'])
                        
                        # Check if we got results
                        total_results = body_data.get('total_results', 0)
                        agent_type = body_data.get('agent_type')
                        data_source = body_data.get('data_source')
                        
                        print(f"✅ SUCCESS")
                        print(f"   Agent Type: {agent_type}")
                        print(f"   Data Source: {data_source}")
                        print(f"   Total Results: {total_results}")
                        
                        if total_results > 0:
                            # Show sample of first result
                            first_result = body_data['results'][0]
                            print(f"   Sample Result Keys: {list(first_result.keys())[:5]}...")
                        
                        results.append({
                            'test': test_case['name'],
                            'status': 'PASSED',
                            'agent_type': agent_type,
                            'data_source': data_source,
                            'total_results': total_results
                        })
                        
                    except json.JSONDecodeError as e:
                        print(f"❌ JSON Parse Error: {e}")
                        results.append({
                            'test': test_case['name'],
                            'status': 'FAILED',
                            'error': f'JSON Parse Error: {e}'
                        })
                else:
                    print(f"❌ Unexpected response format")
                    results.append({
                        'test': test_case['name'],
                        'status': 'FAILED',
                        'error': 'Unexpected response format'
                    })
            else:
                print(f"❌ Invalid response structure")
                results.append({
                    'test': test_case['name'],
                    'status': 'FAILED',
                    'error': 'Invalid response structure'
                })
            
        except Exception as e:
            print(f"❌ ERROR: {str(e)}")
            results.append({
                'test': test_case['name'],
                'status': 'ERROR',
                'error': str(e)
            })
        
        print("-" * 40)
        print()
    
    # Summary
    passed = len([r for r in results if r['status'] == 'PASSED'])
    failed = len([r for r in results if r['status'] == 'FAILED'])
    errors = len([r for r in results if r['status'] == 'ERROR'])
    
    print(f"📊 Simplified Metrics Test Summary:")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"🚨 Errors: {errors}")
    print(f"📈 Success Rate: {passed}/{len(results)} ({passed/len(results)*100:.1f}%)")
    
    return results

if __name__ == "__main__":
    test_simplified_metrics()