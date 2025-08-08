#!/usr/bin/env python3

import boto3
import json
import time

# Test queries based on the failing Slack interactions
TEST_QUERIES = {
    'integration_test': [
        {
            'name': 'RC_1_version_3.2.0',
            'payload': {
                'actionGroup': 'IntegrationTestActionGroup',
                'function': 'get_integration_test_metrics',
                'parameters': [
                    {'name': 'version', 'value': '3.2.0'},
                    {'name': 'rc_numbers', 'value': ['1']},
                    {'name': 'status_filter', 'value': 'failed'}
                ]
            }
        },
        {
            'name': 'build_numbers_11323_8585',
            'payload': {
                'actionGroup': 'IntegrationTestActionGroup',
                'function': 'get_integration_test_metrics',
                'parameters': [
                    {'name': 'version', 'value': '3.2.0'},
                    {'name': 'build_numbers', 'value': ['11323', '8585']},
                    {'name': 'status_filter', 'value': 'failed'}
                ]
            }
        },
        {
            'name': 'RC_1_both_components',
            'payload': {
                'actionGroup': 'IntegrationTestActionGroup',
                'function': 'get_integration_test_metrics',
                'parameters': [
                    {'name': 'version', 'value': '3.2.0'},
                    {'name': 'rc_numbers', 'value': ['1']},
                    {'name': 'components', 'value': ['OpenSearch', 'OpenSearch-Dashboards']},
                    {'name': 'status_filter', 'value': 'failed'}
                ]
            }
        }
    ],
    'build_metrics': [
        {
            'name': 'build_status_3.2.0',
            'payload': {
                'actionGroup': 'BuildMetricsActionGroup',
                'function': 'get_build_metrics',
                'parameters': [
                    {'name': 'version', 'value': '3.2.0'},
                    {'name': 'status_filter', 'value': 'failed'}
                ]
            }
        },
        {
            'name': 'build_numbers_11323_8585',
            'payload': {
                'actionGroup': 'BuildMetricsActionGroup',
                'function': 'get_build_metrics',
                'parameters': [
                    {'name': 'version', 'value': '3.2.0'},
                    {'name': 'build_numbers', 'value': ['11323', '8585']}
                ]
            }
        }
    ],
    'release_metrics': [
        {
            'name': 'release_readiness_3.2.0',
            'payload': {
                'parameters': [
                    {'name': 'version', 'value': '3.2.0'}
                ]
            }
        },
        {
            'name': 'component_readiness',
            'payload': {
                'parameters': [
                    {'name': 'version', 'value': '3.2.0'},
                    {'name': 'components', 'value': ['OpenSearch', 'OpenSearch-Dashboards']}
                ]
            }
        }
    ]
}

LAMBDA_FUNCTIONS = {
    'integration_test': 'oscar-test-metrics-agent-new',
    'build_metrics': 'oscar-build-metrics-agent-new', 
    'release_metrics': 'oscar-release-metrics-agent-new'
}

def test_lambda_function(client, function_name, test_name, payload):
    """Test a single lambda function with given payload"""
    print(f"\n🧪 Testing {function_name} - {test_name}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    try:
        response = client.invoke(
            FunctionName=function_name,
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )
        
        result = json.loads(response['Payload'].read())
        
        if response.get('FunctionError'):
            print(f"❌ Function Error: {result}")
            return False
        
        print(f"✅ Success: {len(str(result))} chars response")
        if 'error' in str(result).lower():
            print(f"⚠️  Response contains error: {str(result)[:200]}...")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False

def main():
    client = boto3.client('lambda', region_name='us-east-1')
    
    results = {}
    
    for agent_type, queries in TEST_QUERIES.items():
        function_name = LAMBDA_FUNCTIONS[agent_type]
        results[agent_type] = {'passed': 0, 'failed': 0}
        
        print(f"\n{'='*60}")
        print(f"Testing {agent_type.upper()} Agent: {function_name}")
        print(f"{'='*60}")
        
        for query in queries:
            success = test_lambda_function(client, function_name, query['name'], query['payload'])
            if success:
                results[agent_type]['passed'] += 1
            else:
                results[agent_type]['failed'] += 1
            
            time.sleep(1)  # Brief pause between tests
    
    # Summary
    print(f"\n{'='*60}")
    print("TEST SUMMARY")
    print(f"{'='*60}")
    
    for agent_type, result in results.items():
        total = result['passed'] + result['failed']
        print(f"{agent_type}: {result['passed']}/{total} passed")
    
    total_passed = sum(r['passed'] for r in results.values())
    total_tests = sum(r['passed'] + r['failed'] for r in results.values())
    print(f"\nOverall: {total_passed}/{total_tests} tests passed")

if __name__ == "__main__":
    main()