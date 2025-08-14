#!/usr/bin/env python3
"""
Test script for the simplified storage implementation.
"""

import sys
import os
sys.path.append('oscar-agent')

# Set minimal environment variables to avoid config validation errors
os.environ['OSCAR_BEDROCK_AGENT_ID'] = 'test-agent-id'
os.environ['OSCAR_BEDROCK_AGENT_ALIAS_ID'] = 'test-alias-id'
os.environ['SLACK_BOT_TOKEN'] = 'test-token'
os.environ['SLACK_SIGNING_SECRET'] = 'test-secret'

from storage import DynamoDBStorage
import time

def test_simplified_storage():
    """Test the simplified storage implementation."""
    print("Testing simplified storage implementation...")
    
    # Create storage instance (this will fail without AWS credentials, but we can test the logic)
    try:
        storage = DynamoDBStorage()
        print("✓ Storage instance created")
    except Exception as e:
        print(f"⚠ Storage creation failed (expected without AWS): {e}")
        return
    
    # Test context structure
    thread_key = "test_channel_123456"
    
    # Test 1: Store initial context
    context = {
        "session_id": "session-123",
        "history": [
            {
                "query": "What is OpenSearch?",
                "response": "OpenSearch is an open-source search and analytics suite.",
                "timestamp": int(time.time())
            }
        ]
    }
    
    try:
        success = storage.store_context(thread_key, context)
        print(f"✓ Store context result: {success}")
    except Exception as e:
        print(f"⚠ Store context failed (expected without AWS): {e}")
    
    # Test 2: Get context for query formatting
    try:
        formatted_context = storage.get_context_for_query(thread_key)
        print(f"✓ Formatted context length: {len(formatted_context)}")
        print("Sample formatted context:")
        print(formatted_context[:200] + "..." if len(formatted_context) > 200 else formatted_context)
    except Exception as e:
        print(f"⚠ Get context for query failed (expected without AWS): {e}")
    
    print("\nSimplified storage test completed!")

if __name__ == "__main__":
    test_simplified_storage()