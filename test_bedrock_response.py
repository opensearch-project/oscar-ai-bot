#!/usr/bin/env python3
"""
Test script to verify Bedrock response format compatibility.
"""

import boto3
import json
import time
from datetime import datetime

def test_lambda_with_different_versions():
    """Test the Lambda function with different message versions."""
    
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    
    # Test functions to try
    test_functions = [
        'test_basic',
        'test_message_version', 
        'test_response_format'
    ]
    
    # Lambda functions to test
    lambda_functions = [
        'oscar-test-metrics-agent-new',
        'oscar-build-metrics-agent-new', 
        'oscar-release-metrics-agent-new'
    ]
    
    for lambda_func in lambda_functions:
        print(f"\n{'='*60}")
        print(f"Testing Lambda Function: {lambda_func}")
        print(f"{'='*60}")
        
        for test_func in test_functions:
            print(f"\n--- Testing function: {test_func} ---")
            
            # Create test event
            test_event = {
                "actionGroup": "metrics-agent",
                "function": test_func,
                "parameters": []
            }
            
            try:
                # Invoke the Lambda function
                response = lambda_client.invoke(
                    FunctionName=lambda_func,
                    Payload=json.dumps(test_event),
                    InvocationType='RequestResponse'
                )
                
                # Read the response
                payload = json.loads(response['Payload'].read())
                
                print(f"✅ Status Code: {response['StatusCode']}")
                
                if 'errorMessage' in payload:
                    print(f"❌ Error: {payload['errorMessage']}")
                    if 'errorType' in payload:
                        print(f"   Type: {payload['errorType']}")
                    if 'stackTrace' in payload:
                        print(f"   Stack: {payload['stackTrace'][:200]}...")
                else:
                    print(f"✅ Success!")
                    if 'messageVersion' in payload:
                        print(f"   Message Version: {payload['messageVersion']}")
                    if 'response' in payload:
                        response_body = payload['response'].get('functionResponse', {}).get('responseBody', {}).get('TEXT', {}).get('body', '')
                        if response_body:
                            try:
                                body_data = json.loads(response_body)
                                print(f"   Response: {json.dumps(body_data, indent=2)[:200]}...")
                            except:
                                print(f"   Response: {response_body[:200]}...")
                
            except Exception as e:
                print(f"❌ Exception: {e}")
            
            time.sleep(1)  # Brief pause between tests

def test_working_lambda_format():
    """Test a known working Lambda to see its response format."""
    
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    
    # Test the Jenkins Lambda which we know works
    jenkins_functions = [
        'oscar-jenkins-agent'  # Update this to the actual Jenkins Lambda name
    ]
    
    for func_name in jenkins_functions:
        print(f"\n{'='*60}")
        print(f"Testing Working Lambda: {func_name}")
        print(f"{'='*60}")
        
        test_event = {
            "actionGroup": "jenkins-agent",
            "function": "list_jobs",
            "parameters": []
        }
        
        try:
            response = lambda_client.invoke(
                FunctionName=func_name,
                Payload=json.dumps(test_event),
                InvocationType='RequestResponse'
            )
            
            payload = json.loads(response['Payload'].read())
            
            print(f"Status Code: {response['StatusCode']}")
            print(f"Response Structure:")
            print(json.dumps(payload, indent=2)[:500] + "...")
            
        except Exception as e:
            print(f"❌ Could not test {func_name}: {e}")

if __name__ == "__main__":
    print(f"Bedrock Response Format Test - {datetime.now()}")
    
    # Test our metrics functions
    test_lambda_with_different_versions()
    
    # Test a working function for comparison
    test_working_lambda_format()