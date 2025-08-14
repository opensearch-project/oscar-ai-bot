#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Comprehensive debugging script for OSCAR context preservation issues.

This script tests all aspects of context storage and retrieval to identify
where the context preservation is failing.
"""

import json
import os
import sys
import time
import boto3
from typing import Dict, Any, Optional

# Add oscar-agent to path
sys.path.append('oscar-agent')

def test_dynamodb_connection():
    """Test basic DynamoDB connectivity and table access."""
    print("🔍 Testing DynamoDB Connection...")
    
    try:
        # Test with environment variables
        region = os.environ.get('AWS_REGION', 'us-east-1')
        context_table_name = os.environ.get('CONTEXT_TABLE_NAME', 'oscar-agent-context')
        sessions_table_name = os.environ.get('SESSIONS_TABLE_NAME', 'oscar-agent-sessions')
        
        print(f"   Region: {region}")
        print(f"   Context Table: {context_table_name}")
        print(f"   Sessions Table: {sessions_table_name}")
        
        # Initialize DynamoDB
        dynamodb = boto3.resource('dynamodb', region_name=region)
        
        # Test context table
        context_table = dynamodb.Table(context_table_name)
        context_table.load()
        print(f"✅ Context table accessible: {context_table.table_status}")
        
        # Test sessions table
        sessions_table = dynamodb.Table(sessions_table_name)
        sessions_table.load()
        print(f"✅ Sessions table accessible: {sessions_table.table_status}")
        
        return True
        
    except Exception as e:
        print(f"❌ DynamoDB connection failed: {e}")
        return False

def test_storage_interface():
    """Test the storage interface directly."""
    print("\n🔍 Testing Storage Interface...")
    
    try:
        from storage import DynamoDBStorage
        
        # Initialize storage
        storage = DynamoDBStorage()
        print("✅ Storage interface initialized")
        
        # Test basic storage operations
        test_thread_key = f"test_channel_123456789.123456"
        test_context = {
            "session_id": "test-session-123",
            "history": [
                {
                    "query": "Test query",
                    "response": "Test response",
                    "timestamp": int(time.time())
                }
            ]
        }
        
        # Store context
        success = storage.store_context(test_thread_key, test_context)
        print(f"✅ Context storage: {success}")
        
        # Retrieve context
        retrieved = storage.get_context(test_thread_key)
        if retrieved:
            print(f"✅ Context retrieval: {len(retrieved.get('history', []))} entries")
            print(f"   Session ID: {retrieved.get('session_id')}")
        else:
            print("❌ Context retrieval failed")
            return False
        
        # Test context formatting
        formatted = storage.get_context_for_query(test_thread_key)
        print(f"✅ Context formatting: {len(formatted)} characters")
        
        # Clean up test data
        try:
            storage.context_table.delete_item(Key={'thread_key': test_thread_key})
            print("✅ Test cleanup completed")
        except:
            pass
        
        return True
        
    except Exception as e:
        print(f"❌ Storage interface test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_thread_key_generation():
    """Test thread key generation logic."""
    print("\n🔍 Testing Thread Key Generation...")
    
    # Test various scenarios
    test_cases = [
        {
            "channel": "C096MV7JZ0T",
            "thread_ts": "1234567890.123456",
            "expected": "C096MV7JZ0T_1234567890.123456"
        },
        {
            "channel": "C09827S7CEB",
            "thread_ts": "1234567890.654321",
            "expected": "C09827S7CEB_1234567890.654321"
        }
    ]
    
    for case in test_cases:
        thread_key = f"{case['channel']}_{case['thread_ts']}"
        if thread_key == case['expected']:
            print(f"✅ Thread key generation: {thread_key}")
        else:
            print(f"❌ Thread key mismatch: got {thread_key}, expected {case['expected']}")
            return False
    
    return True

def test_context_update_logic():
    """Test the context update logic from slack_handler."""
    print("\n🔍 Testing Context Update Logic...")
    
    try:
        from storage import DynamoDBStorage
        
        storage = DynamoDBStorage()
        test_thread_key = f"test_update_channel_123456789.123456"
        
        # Simulate first message
        print("   Testing first message (new context)...")
        query1 = "What is OpenSearch?"
        response1 = "OpenSearch is an open-source search and analytics suite."
        session_id1 = "session-123"
        
        # Create new context
        context = storage.get_context(test_thread_key)
        if not context:
            context = {
                "session_id": session_id1,
                "history": []
            }
        
        # Add first entry
        context["history"].append({
            "query": query1,
            "response": response1,
            "timestamp": int(time.time())
        })
        
        success = storage.store_context(test_thread_key, context)
        print(f"   ✅ First message stored: {success}")
        
        # Simulate second message
        print("   Testing second message (update context)...")
        query2 = "How do I install it?"
        response2 = "You can install OpenSearch using Docker, packages, or from source."
        session_id2 = "session-456"  # New session ID
        
        # Get existing context
        context = storage.get_context(test_thread_key)
        if context:
            print(f"   ✅ Retrieved existing context: {len(context.get('history', []))} entries")
            
            # Update session ID
            context["session_id"] = session_id2
            
            # Add second entry
            context["history"].append({
                "query": query2,
                "response": response2,
                "timestamp": int(time.time())
            })
            
            success = storage.store_context(test_thread_key, context)
            print(f"   ✅ Second message stored: {success}")
            
            # Verify final context
            final_context = storage.get_context(test_thread_key)
            if final_context:
                history_count = len(final_context.get('history', []))
                session_id = final_context.get('session_id')
                print(f"   ✅ Final context: {history_count} entries, session: {session_id}")
                
                if history_count == 2 and session_id == session_id2:
                    print("   ✅ Context update logic working correctly")
                    result = True
                else:
                    print(f"   ❌ Context update failed: expected 2 entries and session {session_id2}")
                    result = False
            else:
                print("   ❌ Failed to retrieve final context")
                result = False
        else:
            print("   ❌ Failed to retrieve existing context")
            result = False
        
        # Clean up
        try:
            storage.context_table.delete_item(Key={'thread_key': test_thread_key})
        except:
            pass
        
        return result
        
    except Exception as e:
        print(f"❌ Context update logic test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_cross_channel_context():
    """Test cross-channel context storage from communication handler."""
    print("\n🔍 Testing Cross-Channel Context Storage...")
    
    try:
        # Test the communication handler function
        sys.path.append('oscar-agent')
        
        # Set up environment for communication handler
        os.environ['CONTEXT_TABLE_NAME'] = os.environ.get('CONTEXT_TABLE_NAME', 'oscar-agent-context')
        
        # Import and test the function
        from communication_handler import store_cross_channel_context
        
        # Test parameters
        channel = "C09827S7CEB"
        message_ts = f"1234567890.{int(time.time())}"
        original_query = "Send missing release notes message to test channel"
        sent_message = "Hi, this component is missing release notes..."
        
        print(f"   Testing with channel: {channel}, ts: {message_ts}")
        
        # Call the function
        store_cross_channel_context(channel, message_ts, original_query, sent_message)
        print("   ✅ Cross-channel context storage completed")
        
        # Verify it was stored
        from storage import DynamoDBStorage
        storage = DynamoDBStorage()
        thread_key = f"{channel}_{message_ts}"
        context = storage.get_context(thread_key)
        
        if context:
            history = context.get('history', [])
            if len(history) == 1:
                entry = history[0]
                if "[Automated message - original request details redacted for privacy]" in entry.get('query', ''):
                    print("   ✅ Context stored with redacted query")
                    print(f"   ✅ Response preserved: {len(entry.get('response', ''))} characters")
                    result = True
                else:
                    print(f"   ❌ Query not properly redacted: {entry.get('query')}")
                    result = False
            else:
                print(f"   ❌ Expected 1 history entry, got {len(history)}")
                result = False
        else:
            print("   ❌ Context was not found after storage")
            result = False
        
        # Clean up
        try:
            storage.context_table.delete_item(Key={'thread_key': thread_key})
        except:
            pass
        
        return result
        
    except Exception as e:
        print(f"❌ Cross-channel context test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_agent_session_handling():
    """Test how the agent handles session IDs."""
    print("\n🔍 Testing Agent Session Handling...")
    
    try:
        from oscar_agent import get_oscar_agent
        
        # Initialize agent
        agent = get_oscar_agent()
        print("   ✅ Agent initialized")
        
        # Test query without session ID
        print("   Testing query without session ID...")
        try:
            response1, session_id1 = agent.query("What is OpenSearch?")
            print(f"   ✅ First query successful, session: {session_id1}")
            print(f"   Response length: {len(response1)} characters")
            
            # Test query with session ID
            print("   Testing query with session ID...")
            response2, session_id2 = agent.query("Tell me more about it", session_id=session_id1)
            print(f"   ✅ Second query successful, session: {session_id2}")
            print(f"   Response length: {len(response2)} characters")
            
            # Check if session IDs are consistent
            if session_id1 and session_id2:
                print(f"   Session consistency: {session_id1 == session_id2}")
                return True
            else:
                print("   ❌ Session IDs are None")
                return False
                
        except Exception as e:
            print(f"   ❌ Agent query failed: {e}")
            return False
        
    except Exception as e:
        print(f"❌ Agent session handling test failed: {e}")
        return False

def check_environment_variables():
    """Check all required environment variables."""
    print("\n🔍 Checking Environment Variables...")
    
    required_vars = [
        'AWS_REGION',
        'OSCAR_BEDROCK_AGENT_ID',
        'OSCAR_BEDROCK_AGENT_ALIAS_ID',
        'SLACK_BOT_TOKEN',
        'SLACK_SIGNING_SECRET'
    ]
    
    optional_vars = [
        'CONTEXT_TABLE_NAME',
        'SESSIONS_TABLE_NAME',
        'CONTEXT_TTL',
        'DEDUP_TTL'
    ]
    
    all_good = True
    
    for var in required_vars:
        value = os.environ.get(var)
        if value:
            print(f"   ✅ {var}: {'*' * min(len(value), 20)}")
        else:
            print(f"   ❌ {var}: NOT SET")
            all_good = False
    
    for var in optional_vars:
        value = os.environ.get(var)
        if value:
            print(f"   ✅ {var}: {value}")
        else:
            print(f"   ⚠️  {var}: using default")
    
    return all_good

def main():
    """Run all debugging tests."""
    print("🚀 Starting OSCAR Context Preservation Debug Suite...\n")
    
    # Set default environment if not set
    if not os.environ.get('AWS_REGION'):
        os.environ['AWS_REGION'] = 'us-east-1'
    
    tests = [
        ("Environment Variables", check_environment_variables),
        ("DynamoDB Connection", test_dynamodb_connection),
        ("Thread Key Generation", test_thread_key_generation),
        ("Storage Interface", test_storage_interface),
        ("Context Update Logic", test_context_update_logic),
        ("Cross-Channel Context", test_cross_channel_context),
        ("Agent Session Handling", test_agent_session_handling),
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results[test_name] = result
        except Exception as e:
            print(f"❌ {test_name} crashed: {e}")
            results[test_name] = False
    
    # Summary
    print(f"\n📊 Test Results Summary:")
    print("=" * 50)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {test_name}: {status}")
        if result:
            passed += 1
    
    print("=" * 50)
    print(f"   Total: {passed}/{total} tests passed")
    
    if passed == total:
        print(f"\n🎉 All tests passed! Context preservation should be working.")
        return 0
    else:
        print(f"\n❌ {total - passed} tests failed. Context preservation has issues.")
        print(f"\n🔧 Troubleshooting suggestions:")
        
        if not results.get("Environment Variables"):
            print("   - Check that all required environment variables are set")
        
        if not results.get("DynamoDB Connection"):
            print("   - Verify DynamoDB tables exist and are accessible")
            print("   - Check AWS credentials and permissions")
        
        if not results.get("Storage Interface"):
            print("   - Check DynamoDB table schema and permissions")
            print("   - Verify table names match configuration")
        
        if not results.get("Context Update Logic"):
            print("   - Check context storage and retrieval logic")
            print("   - Verify session ID handling")
        
        if not results.get("Cross-Channel Context"):
            print("   - Check communication handler deployment")
            print("   - Verify Lambda has DynamoDB permissions")
        
        if not results.get("Agent Session Handling"):
            print("   - Check Bedrock agent configuration")
            print("   - Verify agent permissions and availability")
        
        return 1

if __name__ == "__main__":
    exit(main())