#!/usr/bin/env python3

import json
import boto3
import os
from datetime import datetime

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

def test_agent_type_parameter():
    """Test that agent_type parameter is correctly handled in metrics functions."""
    
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    
    test_cases = [
        {
            'name': 'Test Metrics Agent with explicit agent_type',
            'function': 'oscar-test-metrics-agent-new',
            'payload': {
                'actionGroup': 'metrics-query',
                'function': 'get_integration_test_metrics',
                'parameters': [
                    {'name': 'agent_type', 'value': 'integration-test'},
                    {'name': 'version', 'value': '2.18.0'},
                    {'name': 'query', 'value': 'Show me integration test results for version 2.18.0'}
                ]
            },
            'expected_agent_type': 'integration_test'
        },
        {
            'name': 'Build Metrics Agent with explicit agent_type',
            'function': 'oscar-build-metrics-agent-new',
            'payload': {
                'actionGroup': 'metrics-query',
                'function': 'get_build_metrics',
                'parameters': [
                    {'name': 'agent_type', 'value': 'build-metrics'},
                    {'name': 'version', 'value': '2.18.0'},
                    {'name': 'query', 'value': 'Show me build results for version 2.18.0'}
                ]
            },
            'expected_agent_type': 'build'
        },
        {
            'name': 'Release Metrics Agent with explicit agent_type',
            'function': 'oscar-release-metrics-agent-new',
            'payload': {
                'actionGroup': 'metrics-query',
                'function': 'get_release_metrics',
                'parameters': [
                    {'name': 'agent_type', 'value': 'release-metrics'},
                    {'name': 'version', 'value': '2.18.0'},
                    {'name': 'query', 'value': 'Show me release readiness for version 2.18.0'}
                ]
            },
            'expected_agent_type': 'release'
        },
        {
            'name': 'Test function inference without agent_type (integration test)',
            'function': 'oscar-test-metrics-agent-new',
            'payload': {
                'actionGroup': 'metrics-query',
                'function': 'get_integration_test_metrics',
                'parameters': [
                    {'name': 'version', 'value': '2.18.0'},
                    {'name': 'query', 'value': 'Show me integration test results for version 2.18.0'}
                ]
            },
            'expected_agent_type': 'integration_test'  # Should be inferred from function name
        },
        {
            'name': 'Test function inference without agent_type (build)',
            'function': 'oscar-build-metrics-agent-new',
            'payload': {
                'actionGroup': 'metrics-query',
                'function': 'get_build_metrics',
                'parameters': [
                    {'name': 'version', 'value': '2.18.0'},
                    {'name': 'query', 'value': 'Show me build results for version 2.18.0'}
                ]
            },
            'expected_agent_type': 'build'  # Should be inferred from function name
        },
        {
            'name': 'Test basic function (should work with any agent)',
            'function': 'oscar-test-metrics-agent-new',
            'payload': {
                'actionGroup': 'metrics-query',
                'function': 'test_basic',
                'parameters': []
            },
            'expected_agent_type': 'integration-test'  # Default fallback
        }
    ]
    
    print(f"🧪 Testing Agent Type Parameter Handling")
    print(f"{'='*60}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()
    
    results = []
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"Test {i}: {test_case['name']}")
        print(f"Function: {test_case['function']}")
        print(f"Expected agent_type: {test_case['expected_agent_type']}")
        
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
            
            # Extract agent_type from Bedrock agent response format
            actual_agent_type = None
            if isinstance(response_payload, dict):
                # Check if it's in the main response (direct invocation)
                actual_agent_type = response_payload.get('agent_type')
                
                # Check if it's in Bedrock agent format
                if not actual_agent_type and 'response' in response_payload:
                    bedrock_response = response_payload['response']
                    if 'functionResponse' in bedrock_response:
                        function_response = bedrock_response['functionResponse']
                        if 'responseBody' in function_response:
                            response_body = function_response['responseBody']
                            if 'TEXT' in response_body and 'body' in response_body['TEXT']:
                                try:
                                    # Parse the JSON string in the body
                                    body_data = json.loads(response_body['TEXT']['body'])
                                    actual_agent_type = body_data.get('agent_type')
                                except json.JSONDecodeError:
                                    pass
                
                # Check if it's nested in results
                if not actual_agent_type and 'results' in response_payload:
                    for result in response_payload['results']:
                        if 'agent_type' in result:
                            actual_agent_type = result['agent_type']
                            break
            
            # Debug: Print the actual response structure
            print(f"📋 Response keys: {list(response_payload.keys()) if isinstance(response_payload, dict) else 'Not a dict'}")
            if isinstance(response_payload, dict) and 'results' in response_payload:
                print(f"📋 Results structure: {type(response_payload['results'])}")
                if isinstance(response_payload['results'], list) and response_payload['results']:
                    print(f"📋 First result keys: {list(response_payload['results'][0].keys()) if isinstance(response_payload['results'][0], dict) else 'Not a dict'}")
            
            # Verify agent_type matches expected
            if actual_agent_type == test_case['expected_agent_type']:
                print(f"✅ PASSED - Agent type: {actual_agent_type}")
                results.append({
                    'test': test_case['name'],
                    'status': 'PASSED',
                    'expected': test_case['expected_agent_type'],
                    'actual': actual_agent_type
                })
            else:
                print(f"❌ FAILED - Expected: {test_case['expected_agent_type']}, Got: {actual_agent_type}")
                print(f"📋 Full response: {json.dumps(response_payload, indent=2)[:500]}...")
                results.append({
                    'test': test_case['name'],
                    'status': 'FAILED',
                    'expected': test_case['expected_agent_type'],
                    'actual': actual_agent_type,
                    'response': response_payload
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
    
    print(f"📊 Test Summary:")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"🚨 Errors: {errors}")
    print(f"📈 Success Rate: {passed}/{len(results)} ({passed/len(results)*100:.1f}%)")
    
    # Show failed tests details
    failed_tests = [r for r in results if r['status'] in ['FAILED', 'ERROR']]
    if failed_tests:
        print(f"\n🔍 Failed Test Details:")
        for test in failed_tests:
            print(f"  - {test['test']}: {test.get('error', 'Agent type mismatch')}")
    
    return results

if __name__ == "__main__":
    test_agent_type_parameter()