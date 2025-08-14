#!/usr/bin/env python3
"""
Comprehensive Context Storage Test for OSCAR Agent

This script tests all three context storage scenarios:
1. Standard thread context (same thread, same channel)
2. Cross-message context (different message, same channel)
3. Cross-channel context (different channel via communication handler)
"""

import json
import logging
import os
import sys
import time
from typing import Dict, Any, Optional

# Add oscar-agent to path
sys.path.insert(0, 'oscar-agent')

import boto3
from storage import DynamoDBStorage
from oscar_agent import EnhancedBedrockOSCARAgent
from config import Config

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_storage_operations():
    """Test basic storage operations"""
    print("🧪 Testing Basic Storage Operations...")
    
    try:
        # Initialize storage
        storage = DynamoDBStorage()
        
        # Test 1: Store and retrieve context
        thread_key = "test_channel_123456789"
        test_context = {
            "session_id": "test-session-123",
            "history": [
                {
                    "query": "What is OpenSearch?",
                    "response": "OpenSearch is a distributed search and analytics engine.",
                    "timestamp": int(time.time())
                }
            ]
        }
        
        print(f"📝 Storing test context for thread: {thread_key}")
        success = storage.store_context(thread_key, test_context)
        if success:
            print("✅ Context stored successfully")
        else:
            print("❌ Failed to store context")
            return False
        
        # Test 2: Retrieve context
        print(f"📖 Retrieving context for thread: {thread_key}")
        retrieved_context = storage.get_context(thread_key)
        if retrieved_context:
            print(f"✅ Context retrieved successfully: {len(retrieved_context.get('history', []))} entries")
            print(f"   Session ID: {retrieved_context.get('session_id')}")
        else:
            print("❌ Failed to retrieve context")
            return False
        
        # Test 3: Get formatted context for query
        print(f"📄 Getting formatted context for query...")
        formatted_context = storage.get_context_for_query(thread_key)
        if formatted_context:
            print(f"✅ Formatted context generated: {len(formatted_context)} characters")
            print(f"   Preview: {formatted_context[:100]}...")
        else:
            print("⚠️  No formatted context (this is OK for empty history)")
        
        # Test 4: Event deduplication
        event_id = "test-event-123"
        print(f"🔄 Testing event deduplication with ID: {event_id}")
        
        # First check - should be False
        seen_before = storage.has_seen_event(event_id)
        print(f"   First check (should be False): {seen_before}")
        
        # Mark as seen
        marked = storage.mark_event_seen(event_id)
        print(f"   Marked as seen: {marked}")
        
        # Second check - should be True
        seen_after = storage.has_seen_event(event_id)
        print(f"   Second check (should be True): {seen_after}")
        
        if not seen_before and marked and seen_after:
            print("✅ Event deduplication working correctly")
        else:
            print("❌ Event deduplication failed")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Storage test failed: {e}")
        logger.exception("Storage test error")
        return False

def test_agent_integration():
    """Test agent integration with context"""
    print("\n🤖 Testing Agent Integration with Context...")
    
    try:
        # Initialize components
        storage = DynamoDBStorage()
        agent = EnhancedBedrockOSCARAgent()
        
        # Simulate a conversation thread
        thread_key = "test_agent_channel_987654321"
        
        # First query
        print("📝 First query: 'What is OpenSearch?'")
        response1, session_id1 = agent.query("What is OpenSearch?")
        print(f"✅ First response received (session: {session_id1})")
        print(f"   Response preview: {response1[:100]}...")
        
        # Store context after first query
        context1 = {
            "session_id": session_id1,
            "history": [
                {
                    "query": "What is OpenSearch?",
                    "response": response1,
                    "timestamp": int(time.time())
                }
            ]
        }
        storage.store_context(thread_key, context1)
        print("✅ First context stored")
        
        # Second query with context
        print("\n📝 Second query with context: 'What are its main features?'")
        
        # Get formatted context for the second query
        formatted_context = storage.get_context_for_query(thread_key)
        
        # Query with context
        response2, session_id2 = agent.query(
            "What are its main features?", 
            session_id=session_id1,
            context_summary=formatted_context
        )
        print(f"✅ Second response received (session: {session_id2})")
        print(f"   Response preview: {response2[:100]}...")
        
        # Update context after second query
        retrieved_context = storage.get_context(thread_key)
        if retrieved_context:
            retrieved_context["history"].append({
                "query": "What are its main features?",
                "response": response2,
                "timestamp": int(time.time())
            })
            if session_id2:
                retrieved_context["session_id"] = session_id2
            
            storage.store_context(thread_key, retrieved_context)
            print("✅ Updated context stored")
            
            # Verify final context
            final_context = storage.get_context(thread_key)
            if final_context and len(final_context.get("history", [])) == 2:
                print(f"✅ Final context verified: {len(final_context['history'])} entries")
                return True
            else:
                print("❌ Final context verification failed")
                return False
        else:
            print("❌ Failed to retrieve context for update")
            return False
        
    except Exception as e:
        print(f"❌ Agent integration test failed: {e}")
        logger.exception("Agent integration test error")
        return False

def test_cross_channel_context():
    """Test cross-channel context storage (communication handler scenario)"""
    print("\n🌐 Testing Cross-Channel Context Storage...")
    
    try:
        storage = DynamoDBStorage()
        
        # Simulate a message sent to a different channel
        target_channel = "C096MV7JZ0T"  # From allow list
        message_ts = str(int(time.time() * 1000))  # Simulate Slack timestamp
        thread_key = f"{target_channel}_{message_ts}"
        
        original_query = "[Automated message - original request details redacted for privacy]"
        sent_message = "Hi, this is an automated notification about missing release notes for version 3.2.0."
        
        # Store cross-channel context (simulating communication_handler.py)
        context = {
            "session_id": None,  # New conversation thread
            "history": [
                {
                    "query": original_query,
                    "response": sent_message,
                    "timestamp": int(time.time())
                }
            ]
        }
        
        print(f"📝 Storing cross-channel context for thread: {thread_key}")
        success = storage.store_context(thread_key, context)
        if success:
            print("✅ Cross-channel context stored successfully")
        else:
            print("❌ Failed to store cross-channel context")
            return False
        
        # Simulate a follow-up question in that channel
        print("📖 Simulating follow-up question retrieval...")
        retrieved_context = storage.get_context(thread_key)
        if retrieved_context:
            print(f"✅ Cross-channel context retrieved: {len(retrieved_context.get('history', []))} entries")
            
            # Get formatted context for follow-up
            formatted_context = storage.get_context_for_query(thread_key)
            if formatted_context:
                print(f"✅ Formatted context available: {len(formatted_context)} characters")
                return True
            else:
                print("❌ Failed to generate formatted context")
                return False
        else:
            print("❌ Failed to retrieve cross-channel context")
            return False
        
    except Exception as e:
        print(f"❌ Cross-channel context test failed: {e}")
        logger.exception("Cross-channel context test error")
        return False

def check_dynamodb_permissions():
    """Check DynamoDB permissions and table access"""
    print("\n🔐 Checking DynamoDB Permissions...")
    
    try:
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        
        # Check context table
        context_table = dynamodb.Table('oscar-agent-context')
        print("📊 Checking context table...")
        
        # Try to scan (limited) to check read permissions
        response = context_table.scan(Limit=1)
        print(f"✅ Context table accessible, current items: {response.get('Count', 0)}")
        
        # Check sessions table
        sessions_table = dynamodb.Table('oscar-agent-sessions')
        print("📊 Checking sessions table...")
        
        response = sessions_table.scan(Limit=1)
        print(f"✅ Sessions table accessible, current items: {response.get('Count', 0)}")
        
        return True
        
    except Exception as e:
        print(f"❌ DynamoDB permissions check failed: {e}")
        logger.exception("DynamoDB permissions error")
        return False

def main():
    """Run all context storage tests"""
    print("🚀 Starting Comprehensive Context Storage Tests")
    print("=" * 60)
    
    # Load environment variables
    if os.path.exists('.env'):
        with open('.env', 'r') as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value
        print("✅ Environment variables loaded from .env")
    else:
        print("⚠️  No .env file found, using system environment variables")
    
    # Initialize config to validate environment
    try:
        config = Config(validate_required=True)
        print("✅ Configuration validated")
    except Exception as e:
        print(f"❌ Configuration validation failed: {e}")
        return False
    
    # Run tests
    tests = [
        ("DynamoDB Permissions", check_dynamodb_permissions),
        ("Basic Storage Operations", test_storage_operations),
        ("Agent Integration", test_agent_integration),
        ("Cross-Channel Context", test_cross_channel_context),
    ]
    
    results = {}
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            logger.exception(f"{test_name} exception")
            results[test_name] = False
    
    # Summary
    print("\n" + "="*60)
    print("📊 TEST RESULTS SUMMARY")
    print("="*60)
    
    all_passed = True
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} {test_name}")
        if not passed:
            all_passed = False
    
    print("="*60)
    if all_passed:
        print("🎉 ALL TESTS PASSED! Context storage is working correctly.")
    else:
        print("⚠️  SOME TESTS FAILED. Context storage needs attention.")
        print("\nNext steps:")
        print("1. Check CloudWatch logs for detailed error messages")
        print("2. Verify DynamoDB table permissions")
        print("3. Test with actual Slack messages")
    
    return all_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)