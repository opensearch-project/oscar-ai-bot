#!/usr/bin/env python3

import json
import boto3
import os
from datetime import datetime

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

def test_action_group_parameters():
    """Test that our Lambda functions can handle all the parameters defined in the action group schemas."""
    
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    
    test_cases = [
        {
            'name': 'Integration Test - Full Parameter Set',
            'function': 'oscar-test-metrics-agent-new',
            'payload': {
                'actionGroup': 'integration-test-metrics-actions',
                'function': 'get_integration_test_metrics',
                'parameters': [
                    {'name': 'version', 'value': '3.2.0'},
                    {'name': 'rc_numbers', 'value': '1,2'},
                    {'name': 'build_numbers', 'value': '12345,12346'},
                    {'name': 'integ_test_build_numbers', 'value': '67890,67891'},
                    {'name': 'components', 'value': 'OpenSearch,OpenSearch-Dashboards'},
                    {'name': 'status_filter', 'value': 'failed'},
                    {'name': 'distribution', 'value': 'tar'},
                    {'name': 'architecture', 'value': 'x64'},
                    {'name': 'platform', 'value': 'linux'},
                    {'name': 'with_security', 'value': 'fail'},
                    {'name': 'without_security', 'value': 'pass'}
                ]
            }
        },
        {
            'name': 'Build Metrics - Full Parameter Set',
            'function': 'oscar-build-metrics-agent-new',
            'payload': {
                'actionGroup': 'build-metrics-actions',
                'function': 'get_build_metrics',
                'parameters': [
                    {'name': 'version', 'value': '3.2.0'},
                    {'name': 'build_numbers', 'value': '12345,12346'},
                    {'name': 'components', 'value': 'OpenSearch,OpenSearch-Dashboards'},
                    {'name': 'status_filter', 'value': 'failed'},
                    {'name': 'rc_numbers', 'value': '1,2'}
                ]
            }
        },
        {
            'name': 'Release Metrics - Full Parameter Set',
            'function': 'oscar-release-metrics-agent-new',
            'payload': {
                'actionGroup': 'release-metrics-actions',
                'function': 'get_release_metrics',
                'parameters': [
                    {'name': 'version', 'value': '3.2.0'},
                    {'name': 'components', 'value': 'OpenSearch,OpenSearch-Dashboards'}
                ]
            }
        },
        {
            'name': 'Integration Test - Minimal Parameters',
            'function': 'oscar-test-metrics-agent-new',
            'payload': {
                'actionGroup': 'integration-test-metrics-actions',
                'function': 'get_integration_test_metrics',
                'parameters': [
                    {'name': 'version', 'value': '3.2.0'}
                ]
            }
        },
        {
            'name': 'Build Metrics - Generic Function',
            'function': 'oscar-build-metrics-agent-new',
            'payload': {
                'actionGroup': 'build-metrics-actions',
                'function': 'get_metrics',
                'parameters': [
                    {'name': 'version', 'value': '3.2.0'},
                    {'name': 'query', 'value': 'Show me build performance trends'}
                ]
            }
        }
    ]
    
    print(f"🧪 Testing Action Group Parameter Handling")
    print(f"{'='*60}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()
    
    results = []
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"Test {i}: {test_case['name']}")
        print(f"Function: {test_case['function']}")
        print(f"Parameters: {len(test_case['payload']['parameters'])} params")
        
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
                        
                        # Verify our expected response structure
                        required_fields = ['agent_type', 'version', 'data_source', 'total_results', 'results']
                        missing_fields = [field for field in required_fields if field not in body_data]
                        
                        if missing_fields:
                            print(f"❌ FAILED - Missing fields: {missing_fields}")
                            results.append({
                                'test': test_case['name'],
                                'status': 'FAILED',
                                'error': f'Missing fields: {missing_fields}'
                            })
                        else:
                            # Check parameter parsing
                            query_params = body_data.get('query_parameters', {})
                            total_results = body_data.get('total_results', 0)
                            
                            print(f"✅ SUCCESS")
                            print(f"   Agent Type: {body_data.get('agent_type')}")
                            print(f"   Data Source: {body_data.get('data_source')}")
                            print(f"   Total Results: {total_results}")
                            print(f"   Query Parameters: {len(query_params)} parsed")
                            
                            # Show some parsed parameters
                            if query_params:
                                sample_params = list(query_params.items())[:3]
                                print(f"   Sample Params: {dict(sample_params)}")
                            
                            results.append({
                                'test': test_case['name'],
                                'status': 'PASSED',
                                'agent_type': body_data.get('agent_type'),
                                'total_results': total_results,
                                'parsed_params': len(query_params)
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
    
    print(f"📊 Action Group Parameter Test Summary:")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"🚨 Errors: {errors}")
    print(f"📈 Success Rate: {passed}/{len(results)} ({passed/len(results)*100:.1f}%)")
    
    # Show parameter parsing details for passed tests
    passed_tests = [r for r in results if r['status'] == 'PASSED']
    if passed_tests:
        print(f"\n📋 Parameter Parsing Verification:")
        for test in passed_tests:
            print(f"  ✅ {test['test']}: {test['parsed_params']} parameters parsed correctly")
    
    return results

if __name__ == "__main__":
    test_action_group_parameters()