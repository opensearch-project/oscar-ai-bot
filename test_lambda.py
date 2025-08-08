#!/usr/bin/env python3
"""
Simple test script for the communication handler Lambda function.
"""

import json
import sys
import os

# Add the oscar-agent directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'oscar-agent'))

from communication_handler import lambda_handler

def test_lambda():
    """Test the Lambda function locally."""
    
    # Test event
    event = {
        "actionGroup": "communication-orchestration",
        "apiPath": "/send_automated_message",
        "parameters": [
            {
                "name": "query",
                "value": "send missing release notes message to riley-needs-to-lock-in channel for version 3.2.0"
            }
        ]
    }
    
    print("Testing Lambda function with event:")
    print(json.dumps(event, indent=2))
    print("\n" + "="*50 + "\n")
    
    # Call the handler
    try:
        result = lambda_handler(event, None)
        print("Lambda function result:")
        print(json.dumps(result, indent=2))
        
        # Extract the actual response
        response_body = result.get('response', {}).get('responseBody', {}).get('application/json', {}).get('body')
        if response_body:
            parsed_body = json.loads(response_body)
            print("\nParsed response body:")
            print(json.dumps(parsed_body, indent=2))
            
            if parsed_body.get('success'):
                print("\n✅ SUCCESS: Message would be sent to Slack")
            else:
                print(f"\n❌ ERROR: {parsed_body.get('error')}")
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_lambda()