#!/usr/bin/env python3
"""
Test delayed context retrieval to simulate the real-world issue where
context seems to be lost after waiting a long time between messages.
"""

import json
import logging
import os
import sys
import time

# Add oscar-agent to path
sys.path.insert(0, 'oscar-agent')

from storage import DynamoDBStorage
from oscar_agent import EnhancedBedrockOSCARAgent

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_delayed_context_scenario():
    """Test the exact scenario described: context loss after waiting"""
    print("🕐 Testing Delayed Context Retrieval Scenario...")
    
    # Load environment variables
    if os.path.exists('.env'):
        with open('.env', 'r') as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value
    
    # Initialize components
    storage = DynamoDBStorage()
    agent = EnhancedBedrockOSCARAgent()
    
    # Use a realistic thread key (simulating a real Slack conversation)
    thread_key = f"D096MTDUABV_{int(time.time())}.123456"  # DM channel format
    
    print(f"📝 Starting delayed context test in thread: {thread_key}")
    
    # Step 1: Initial conversation with context establishment
    print("\n1️⃣ Initial conversation - establishing context")
    print("User: 'My name is John and I'm working on the OpenSearch 3.2.0 release'")
    
    response1, session_id1 = agent.query("My name is John and I'm working on the OpenSearch 3.2.0 release")
    print(f"✅ Agent response: {response1[:100]}...")
    print(f"✅ Session ID: {session_id1}")
    
    # Store context (simulating what slack_handler does)
    context1 = {
        "session_id": session_id1,
        "history": [
            {
                "query": "My name is John and I'm working on the OpenSearch 3.2.0 release",
                "response": response1,
                "timestamp": int(time.time())
            }
        ]
    }
    storage.store_context(thread_key, context1)
    print("✅ Context stored")
    
    # Step 2: Follow-up question (immediate)
    print("\n2️⃣ Immediate follow-up question")
    print("User: 'What version am I working on?'")
    
    # Get context (simulating what slack_handler does)
    formatted_context = storage.get_context_for_query(thread_key)
    print(f"📄 Retrieved context length: {len(formatted_context)} characters")
    
    response2, session_id2 = agent.query(
        "What version am I working on?", 
        session_id=session_id1,
        context_summary=formatted_context
    )
    print(f"✅ Agent response: {response2[:100]}...")
    print(f"✅ Session ID: {session_id2}")
    
    # Check if agent remembered the version
    if "3.2.0" in response2:
        print("🎉 SUCCESS: Agent remembered the version immediately")
        immediate_success = True
    else:
        print("❌ FAILURE: Agent did not remember the version immediately")
        print(f"   Full response: {response2}")
        immediate_success = False
    
    # Update context
    retrieved_context = storage.get_context(thread_key)
    if retrieved_context:
        retrieved_context["history"].append({
            "query": "What version am I working on?",
            "response": response2,
            "timestamp": int(time.time())
        })
        if session_id2:
            retrieved_context["session_id"] = session_id2
        storage.store_context(thread_key, retrieved_context)
        print("✅ Context updated")
    
    # Step 3: Simulate waiting (this is where the issue might occur)
    print("\n3️⃣ Simulating delay (waiting 30 seconds)...")
    print("   In real usage, this would be minutes or hours")
    
    # Wait to simulate real-world delay
    time.sleep(30)  # 30 seconds to simulate delay
    
    # Step 4: Delayed follow-up question
    print("\n4️⃣ Delayed follow-up question (after 30 seconds)")
    print("User: 'What's my name again?'")
    
    # Get context again (simulating what slack_handler does after delay)
    print("📄 Retrieving context after delay...")
    delayed_formatted_context = storage.get_context_for_query(thread_key)
    print(f"📄 Retrieved context length: {len(delayed_formatted_context)} characters")
    
    # Check if context is still there
    if delayed_formatted_context:
        print("✅ Context still exists in storage")
        print(f"   Context preview: {delayed_formatted_context[:200]}...")
    else:
        print("❌ Context is missing from storage!")
        return False
    
    # Try with the stored session ID first
    stored_context = storage.get_context(thread_key)
    stored_session_id = stored_context.get("session_id") if stored_context else None
    print(f"📋 Stored session ID: {stored_session_id}")
    
    response3, session_id3 = agent.query(
        "What's my name again?", 
        session_id=stored_session_id,
        context_summary=delayed_formatted_context
    )
    print(f"✅ Agent response: {response3[:200]}...")
    print(f"✅ Session ID: {session_id3}")
    
    # Check if agent remembered the name after delay
    if "John" in response3 or "john" in response3.lower():
        print("🎉 SUCCESS: Agent remembered the name after delay!")
        delayed_success = True
    else:
        print("❌ FAILURE: Agent did not remember the name after delay")
        print(f"   Full response: {response3}")
        delayed_success = False
    
    # Step 5: Check what happened with sessions
    print("\n5️⃣ Session Analysis")
    print(f"   Initial session:  {session_id1}")
    print(f"   Second session:   {session_id2}")
    print(f"   Delayed session:  {session_id3}")
    print(f"   Stored session:   {stored_session_id}")
    
    if session_id1 == session_id2 == session_id3:
        print("✅ Session ID remained consistent throughout")
    elif session_id1 == session_id2 != session_id3:
        print("⚠️  Session ID changed after delay (possible session expiration)")
    else:
        print("⚠️  Session IDs were inconsistent")
    
    # Step 6: Final context verification
    print("\n6️⃣ Final Context Verification")
    final_context = storage.get_context(thread_key)
    if final_context:
        print(f"✅ Final context exists with {len(final_context.get('history', []))} entries")
        for i, entry in enumerate(final_context.get('history', [])):
            print(f"   Entry {i+1}: {entry['query'][:50]}...")
    else:
        print("❌ Final context is missing")
    
    return immediate_success and delayed_success

def main():
    """Run the delayed context test"""
    print("🚀 Testing Delayed Context Retrieval")
    print("=" * 60)
    print("This test simulates the real-world scenario where context")
    print("seems to be lost after waiting between messages.")
    print("=" * 60)
    
    try:
        success = test_delayed_context_scenario()
        
        print("\n" + "=" * 60)
        if success:
            print("🎉 DELAYED CONTEXT TEST PASSED!")
            print("Context is preserved even after delays.")
        else:
            print("⚠️  DELAYED CONTEXT TEST FAILED!")
            print("Context may not be working properly after delays.")
            print("\nPossible causes:")
            print("1. Bedrock agent session expiration")
            print("2. Context formatting issues")
            print("3. Agent not processing context correctly")
            print("4. DynamoDB TTL issues")
        
        return success
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        logger.exception("Test error")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)