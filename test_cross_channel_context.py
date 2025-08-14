#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Test script for cross-channel context preservation functionality.

This script tests the scenario where:
1. User requests to send a message to another channel
2. Message is sent via communication handler
3. Context is stored for the new channel/thread
4. Follow-up messages in that thread maintain context
"""

import json
import os
import sys
import time
from typing import Dict, Any

# Add oscar-agent to path
sys.path.append('oscar-agent')

import boto3
from storage import DynamoDBStorage

def test_cross_channel_context_storage():
    """Test that cross-channel context is properly stored and retrieved."""
    print("🧪 Testing cross-channel context preservation...")
    
    # Initialize storage
    storage = DynamoDBStorage()
    
    # Simulate the scenario
    original_channel = "C096MV7JZ0T"  # Original channel where user made request
    target_channel = "C09827S7CEB"    # Target channel where message was sent
    original_thread_ts = "1234567890.123456"  # Original thread
    sent_message_ts = "1234567890.654321"     # Timestamp of sent message
    
    # Original query and response in the first channel
    original_query = "Send missing release notes message to #private-oscar-test channel"
    original_response = "I'll send the missing release notes message to the specified channel."
    
    # Store original context
    original_thread_key = f"{original_channel}_{original_thread_ts}"
    original_context = {
        "session_id": "test-session-123",
        "history": [
            {
                "query": original_query,
                "response": original_response,
                "timestamp": int(time.time())
            }
        ]
    }
    
    success = storage.store_context(original_thread_key, original_context)
    print(f"✅ Stored original context: {success}")
    
    # Simulate cross-channel message being sent
    sent_message = "Hi, this component is missing release notes at 3.2.0 ref. Please add them on priority..."
    
    # Store cross-channel context (this is what the communication handler should do)
    target_thread_key = f"{target_channel}_{sent_message_ts}"
    cross_channel_context = {
        "session_id": None,  # New conversation thread
        "history": [
            {
                "query": "[Automated message - original request details redacted for privacy]",
                "response": sent_message,
                "timestamp": int(time.time())
            }
        ]
    }
    
    success = storage.store_context(target_thread_key, cross_channel_context)
    print(f"✅ Stored cross-channel context: {success}")
    
    # Test retrieval
    retrieved_context = storage.get_context(target_thread_key)
    if retrieved_context:
        print(f"✅ Retrieved cross-channel context successfully")
        print(f"   - Session ID: {retrieved_context.get('session_id')}")
        print(f"   - History entries: {len(retrieved_context.get('history', []))}")
        
        # Test context for query formatting
        formatted_context = storage.get_context_for_query(target_thread_key)
        print(f"✅ Formatted context length: {len(formatted_context)} characters")
        
        if formatted_context:
            print("📝 Context preview:")
            print(formatted_context[:200] + "..." if len(formatted_context) > 200 else formatted_context)
    else:
        print("❌ Failed to retrieve cross-channel context")
        return False
    
    # Simulate follow-up message in the target channel
    followup_query = "What version is this for?"
    followup_response = "This is for OpenSearch version 3.2.0. The missing release notes need to be added for this version."
    
    # Update context with follow-up
    retrieved_context["history"].append({
        "query": followup_query,
        "response": followup_response,
        "timestamp": int(time.time())
    })
    
    success = storage.store_context(target_thread_key, retrieved_context)
    print(f"✅ Updated context with follow-up: {success}")
    
    # Verify final context
    final_context = storage.get_context(target_thread_key)
    if final_context and len(final_context.get("history", [])) == 2:
        print(f"✅ Final context has {len(final_context['history'])} entries as expected")
        return True
    else:
        print(f"❌ Final context validation failed")
        return False

def test_communication_handler_integration():
    """Test the communication handler context storage function."""
    print("\n🧪 Testing communication handler integration...")
    
    # Import the function from communication handler
    sys.path.append('oscar-agent')
    from communication_handler import store_cross_channel_context
    
    # Test parameters
    channel = "C09827S7CEB"
    message_ts = "1234567890.999999"
    original_query = "Send code coverage message to build channel"
    sent_message = "Hi, OpenSearch is not reporting code-coverage for branch [3.2.0]..."
    
    # Call the function
    try:
        store_cross_channel_context(channel, message_ts, original_query, sent_message)
        print("✅ Communication handler context storage completed")
        
        # Verify it was stored
        storage = DynamoDBStorage()
        thread_key = f"{channel}_{message_ts}"
        context = storage.get_context(thread_key)
        
        if context:
            print("✅ Context successfully stored and retrieved")
            print(f"   - History entries: {len(context.get('history', []))}")
            return True
        else:
            print("❌ Context was not found after storage")
            return False
            
    except Exception as e:
        print(f"❌ Error in communication handler integration: {e}")
        return False

def main():
    """Run all tests."""
    print("🚀 Starting cross-channel context preservation tests...\n")
    
    # Check environment
    if not os.environ.get('AWS_REGION'):
        os.environ['AWS_REGION'] = 'us-east-1'
    
    try:
        # Test 1: Basic cross-channel context storage
        test1_success = test_cross_channel_context_storage()
        
        # Test 2: Communication handler integration
        test2_success = test_communication_handler_integration()
        
        # Summary
        print(f"\n📊 Test Results:")
        print(f"   Cross-channel context storage: {'✅ PASS' if test1_success else '❌ FAIL'}")
        print(f"   Communication handler integration: {'✅ PASS' if test2_success else '❌ FAIL'}")
        
        if test1_success and test2_success:
            print(f"\n🎉 All tests passed! Cross-channel context preservation is working correctly.")
            return 0
        else:
            print(f"\n❌ Some tests failed. Please check the implementation.")
            return 1
            
    except Exception as e:
        print(f"❌ Test execution failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())