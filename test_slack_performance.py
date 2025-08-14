#!/usr/bin/env python3

import json
import boto3
import time
import os
from datetime import datetime

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

def test_slack_performance():
    """Test performance similar to Slack environment"""
    
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    
    print(f"🧪 Testing Slack Performance Simulation")
    print(f"{'='*60}")
    
    # Test the basic RC 6 query with timing
    test_payload = {
        'actionGroup': 'integration-test-metrics-actions',
        'function': 'get_integration_test_metrics',
        'parameters': [
            {'name': 'version', 'value': '3.2.0'},
            {'name': 'rc_numbers', 'value': '6'}
        ]
    }
    
    print(f"🚀 Testing RC 6 query with performance monitoring...")
    
    start_time = time.time()
    
    try:
        response = lambda_client.invoke(
            FunctionName='oscar-test-metrics-agent-new',
            Payload=json.dumps(test_payload),
            InvocationType='RequestResponse'  # Synchronous
        )
        
        end_time = time.time()
        duration = end_time - start_time
        
        print(f"⏱️ Lambda execution time: {duration:.2f} seconds")
        
        # Check if it's within reasonable limits for Slack
        if duration > 15:
            print(f"⚠️ WARNING: Query took {duration:.2f}s - may timeout in Slack")
        elif duration > 10:
            print(f"⚠️ CAUTION: Query took {duration:.2f}s - close to Slack limits")
        else:
            print(f"✅ GOOD: Query completed in {duration:.2f}s - should work in Slack")
        
        # Parse response
        response_payload = json.loads(response['Payload'].read())
        
        if 'errorMessage' in response_payload:
            print(f"❌ Lambda Error: {response_payload['errorMessage']}")
            return
            
        print(f"📋 Response size: {len(json.dumps(response_payload))} characters")
        print(f"📋 Top-level keys: {list(response_payload.keys())}")
        
        # Parse the actual response
        if 'response' in response_payload:
            actual_response = response_payload['response']
            if isinstance(actual_response, str):
                actual_response = json.loads(actual_response)
            
            print(f"📋 Response keys: {list(actual_response.keys()) if isinstance(actual_response, dict) else 'Not a dict'}")
            
            # Get the actual function response
            if 'functionResponse' in actual_response:
                function_response = actual_response['functionResponse']
                if isinstance(function_response, str):
                    function_response = json.loads(function_response)
                print(f"📋 Function response keys: {list(function_response.keys()) if isinstance(function_response, dict) else 'Not a dict'}")
                
                if 'responseBody' in function_response:
                    response_body = function_response['responseBody']
                    if isinstance(response_body, str):
                        response_body = json.loads(response_body)
                    print(f"📋 Response body keys: {list(response_body.keys()) if isinstance(response_body, dict) else 'Not a dict'}")
                    
                    if 'TEXT' in response_body:
                        text_response = response_body['TEXT']
                        if isinstance(text_response, dict) and 'body' in text_response:
                            # Extract the body field
                            body_content = text_response['body']
                            if isinstance(body_content, str):
                                actual_response = json.loads(body_content)
                            else:
                                actual_response = body_content
                            print(f"📋 Parsed body keys: {list(actual_response.keys()) if isinstance(actual_response, dict) else 'Not a dict'}")
                        else:
                            try:
                                # Try to parse as JSON
                                actual_response = json.loads(text_response)
                                print(f"📋 Parsed TEXT keys: {list(actual_response.keys()) if isinstance(actual_response, dict) else 'Not a dict'}")
                            except Exception as parse_error:
                                print(f"📋 TEXT content (first 200 chars): {str(text_response)[:200]}...")
                                print(f"📋 Parse error: {parse_error}")
                                actual_response = response_body
                    else:
                        actual_response = response_body
            
            if 'total_results' in actual_response:
                total_results = actual_response['total_results']
                print(f"📊 Total Results: {total_results}")
                
                if 'metadata' in actual_response:
                    metadata = actual_response['metadata']
                    print(f"📋 Metadata: {metadata}")
                else:
                    print(f"📋 No metadata found")
                
                # Check response size impact
                response_size_mb = len(json.dumps(response_payload)) / (1024 * 1024)
                print(f"📦 Response size: {response_size_mb:.2f} MB")
                
                if response_size_mb > 5:
                    print(f"⚠️ WARNING: Large response size may cause Slack issues")
                elif response_size_mb > 2:
                    print(f"⚠️ CAUTION: Response size is getting large")
                else:
                    print(f"✅ GOOD: Response size is reasonable")
                    
            else:
                print(f"❌ No total_results in response")
        else:
            print(f"❌ No response field in payload")
            
    except Exception as e:
        end_time = time.time()
        duration = end_time - start_time
        print(f"❌ Query failed after {duration:.2f}s: {e}")

if __name__ == "__main__":
    test_slack_performance()