#!/usr/bin/env python3

import boto3
import json

def test_integration_lambda():
    """Test integration test lambda with proper Bedrock event format"""
    client = boto3.client('lambda', region_name='us-east-1')
    
    # Test RC query
    payload = {
        "actionGroup": "IntegrationTestActionGroup",
        "function": "get_integration_test_metrics",
        "parameters": [
            {"name": "version", "value": "3.2.0"},
            {"name": "rc_numbers", "value": ["1"]},
            {"name": "status_filter", "value": "failed"}
        ]
    }
    
    print("Testing RC 1 query...")
    try:
        response = client.invoke(
            FunctionName='oscar-test-metrics-agent-new',
            Payload=json.dumps(payload)
        )
        result = json.loads(response['Payload'].read())
        
        if response.get('FunctionError'):
            print(f"❌ Error: {result}")
        else:
            print(f"✅ Success: {len(str(result))} chars")
            # Check if response contains actual data
            response_body = result.get('response', {}).get('functionResponse', {}).get('responseBody', {}).get('TEXT', {}).get('body', '{}')
            data = json.loads(response_body)
            print(f"Data keys: {list(data.keys())}")
            if 'error' in data:
                print(f"Error details: {data['error'][:500]}...")
            
    except Exception as e:
        print(f"❌ Exception: {e}")

if __name__ == "__main__":
    test_integration_lambda()