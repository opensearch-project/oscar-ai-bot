#!/usr/bin/env python3

import boto3
import json
import os

# Load environment
if os.path.exists('.env'):
    with open('.env', 'r') as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                key, value = line.strip().split('=', 1)
                os.environ[key] = value

def test_lambda_direct(function_name, payload, test_name):
    """Test lambda function directly to see raw responses"""
    client = boto3.client('lambda', region_name='us-east-1')
    
    print(f"\n{'='*60}")
    print(f"TESTING: {test_name}")
    print(f"Function: {function_name}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    print(f"{'='*60}")
    
    try:
        response = client.invoke(
            FunctionName=function_name,
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )
        
        result = json.loads(response['Payload'].read())
        
        if response.get('FunctionError'):
            print(f"❌ LAMBDA ERROR: {result}")
            return False
        
        # Extract the actual response body
        response_body = result.get('response', {}).get('functionResponse', {}).get('responseBody', {}).get('TEXT', {}).get('body', '{}')
        data = json.loads(response_body)
        
        print(f"✅ SUCCESS")
        print(f"Response keys: {list(data.keys())}")
        
        # Check for specific issues
        if 'summary' in data:
            summary = data['summary']
            print(f"Summary: {summary}")
            
            # Check for the 0% success rate issue
            if summary.get('success_rate') == 0 and summary.get('total', 0) > 1:
                print(f"🚨 ISSUE: 0% success rate but {summary.get('total')} total builds")
        
        if 'results' in data:
            results = data['results']
            print(f"Results count: {len(results)}")
            for i, result in enumerate(results[:2]):  # Show first 2 results
                if 'build_results' in result:
                    print(f"  Result {i}: {len(result['build_results'])} build results")
                if 'test_results' in result:
                    print(f"  Result {i}: {len(result['test_results'])} test results")
        
        return True
        
    except Exception as e:
        print(f"❌ EXCEPTION: {e}")
        return False

def main():
    # Test the specific failing scenarios
    
    # 1. Build status consistency issue
    build_status_payload = {
        "actionGroup": "BuildMetricsActionGroup",
        "function": "get_build_metrics",
        "parameters": [
            {"name": "version", "value": "3.2.0"}
        ]
    }
    
    build_failures_payload = {
        "actionGroup": "BuildMetricsActionGroup", 
        "function": "get_build_metrics",
        "parameters": [
            {"name": "version", "value": "3.2.0"},
            {"name": "status_filter", "value": "failed"}
        ]
    }
    
    # 2. Integration test data conflict
    single_build_payload = {
        "actionGroup": "IntegrationTestActionGroup",
        "function": "get_integration_test_metrics",
        "parameters": [
            {"name": "version", "value": "3.2.0"},
            {"name": "build_numbers", "value": ["11323"]},
            {"name": "status_filter", "value": "failed"}
        ]
    }
    
    multiple_build_payload = {
        "actionGroup": "IntegrationTestActionGroup",
        "function": "get_integration_test_metrics", 
        "parameters": [
            {"name": "version", "value": "3.2.0"},
            {"name": "build_numbers", "value": ["11323", "8585", "9876"]}
        ]
    }
    
    tests = [
        ("oscar-build-metrics-agent-new", build_status_payload, "Build Status General"),
        ("oscar-build-metrics-agent-new", build_failures_payload, "Build Failures Only"),
        ("oscar-test-metrics-agent-new", single_build_payload, "Single Build 11323"),
        ("oscar-test-metrics-agent-new", multiple_build_payload, "Multiple Builds Including 11323")
    ]
    
    results = {}
    for function_name, payload, test_name in tests:
        success = test_lambda_direct(function_name, payload, test_name)
        results[test_name] = success
    
    print(f"\n{'='*60}")
    print("DIAGNOSTIC SUMMARY")
    print(f"{'='*60}")
    for test_name, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{test_name}: {status}")

if __name__ == "__main__":
    main()