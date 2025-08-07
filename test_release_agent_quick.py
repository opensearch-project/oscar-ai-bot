#!/usr/bin/env python3

import json
import boto3
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_release_lambda_direct():
    """Test the release metrics Lambda function directly."""
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    
    # Test the get_metrics function specifically
    test_payload = {
        "actionGroup": "ReleaseMetricsActionGroup",
        "function": "get_metrics",
        "parameters": [
            {"name": "metric_type", "value": "execution"},
            {"name": "time_range", "value": "7d"}
        ]
    }
    
    try:
        response = lambda_client.invoke(
            FunctionName='oscar-release-metrics-agent-new',
            InvocationType='RequestResponse',
            Payload=json.dumps(test_payload)
        )
        
        result = json.loads(response['Payload'].read())
        print("=== DIRECT LAMBDA TEST ===")
        print(f"Status Code: {response['StatusCode']}")
        print(f"Function Error: {response.get('FunctionError', 'None')}")
        print(f"Response: {json.dumps(result, indent=2)}")
        
        return result
        
    except Exception as e:
        print(f"Direct Lambda test failed: {e}")
        return None

def test_bedrock_agent():
    """Test the Bedrock agent with a simple release query."""
    bedrock_client = boto3.client('bedrock-agent-runtime', region_name='us-east-1')
    
    # Simple release query
    query = "What is the current release status?"
    
    try:
        response = bedrock_client.invoke_agent(
            agentId='TSTALIASID',  # Replace with actual agent ID
            agentAliasId='TSTALIASID',  # Replace with actual alias ID
            inputText=query,
            sessionId=f"test-session-{int(time.time())}"
        )
        
        # Process streaming response
        response_text = ""
        if 'completion' in response:
            for event in response['completion']:
                if 'chunk' in event and 'bytes' in event['chunk']:
                    chunk_text = event['chunk']['bytes'].decode('utf-8')
                    response_text += chunk_text
        
        print("=== BEDROCK AGENT TEST ===")
        print(f"Query: {query}")
        print(f"Response: {response_text}")
        print(f"Response Length: {len(response_text)}")
        print(f"Is None: {response_text is None}")
        print(f"Is Empty: {response_text.strip() == ''}")
        
        return response_text
        
    except Exception as e:
        print(f"Bedrock agent test failed: {e}")
        return None

if __name__ == "__main__":
    import time
    
    print("Testing Release Agent Issues...")
    print("=" * 50)
    
    # Test 1: Direct Lambda function
    lambda_result = test_release_lambda_direct()
    
    print("\n" + "=" * 50)
    
    # Test 2: Bedrock agent (commented out since we need actual IDs)
    # bedrock_result = test_bedrock_agent()
    
    print("\nTest completed. Check results above.")