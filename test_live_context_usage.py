#!/usr/bin/env python3
"""
Test live context usage by simulating a conversation and checking if context is preserved.
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

def test_conversation_context():
    """Test that context is actually being used in conversations"""
    print("🧪 Testing Live Conversation Context Usage...")
    
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
    
    # Use a unique thread key for this test
    thread_key = f"test_context_usage_{int(time.time())}"
    
    print(f"📝 Starting conversation in thread: {thread_key}")
    
    # First query - establish context
    print("\n1️⃣ First query: 'My name is Alice and I work on OpenSearch security features.'")
    response1, session_id1 = agent.query("My name is Alice and I work on OpenSearch security features.")
    print(f"✅ Response 1: {response1[:100]}...")
    
    # Store context
    context1 = {
        "session_id": session_id1,
        "history": [
            {
                "query": "My name is Alice and I work on OpenSearch security features.",
                "response": response1,
                "timestamp": int(time.time())
            }
        ]
    }
    storage.store_context(thread_key, context1)
    print(f"✅ Context stored with session: {session_id1}")
    
    # Wait a moment
    time.sleep(2)
    
    # Second query - test if context is used
    print("\n2️⃣ Second query: 'What is my name?'")
    
    # Get formatted context
    formatted_context = storage.get_context_for_query(thread_key)
    print(f"📄 Formatted context length: {len(formatted_context)} characters")
    
    # Query with context
    response2, session_id2 = agent.query(
        "What is my name?", 
        session_id=session_id1,
        context_summary=formatted_context
    )
    print(f"✅ Response 2: {response2[:200]}...")
    
    # Check if the response mentions "Alice"
    if "Alice" in response2 or "alice" in response2.lower():
        print("🎉 SUCCESS: Agent remembered the name from context!")
        context_working = True
    else:
        print("❌ FAILURE: Agent did not remember the name from context")
        print(f"   Full response: {response2}")
        context_working = False
    
    # Third query - test work context
    print("\n3️⃣ Third query: 'What do I work on?'")
    
    # Update context with second query
    retrieved_context = storage.get_context(thread_key)
    if retrieved_context:
        retrieved_context["history"].append({
            "query": "What is my name?",
            "response": response2,
            "timestamp": int(time.time())
        })
        if session_id2:
            retrieved_context["session_id"] = session_id2
        storage.store_context(thread_key, retrieved_context)
    
    # Get updated formatted context
    formatted_context = storage.get_context_for_query(thread_key)
    
    response3, session_id3 = agent.query(
        "What do I work on?", 
        session_id=session_id2 or session_id1,
        context_summary=formatted_context
    )
    print(f"✅ Response 3: {response3[:200]}...")
    
    # Check if the response mentions security
    if "security" in response3.lower():
        print("🎉 SUCCESS: Agent remembered work context!")
        work_context_working = True
    else:
        print("❌ FAILURE: Agent did not remember work context")
        print(f"   Full response: {response3}")
        work_context_working = False
    
    # Final verification - check stored context
    final_context = storage.get_context(thread_key)
    if final_context:
        print(f"\n📊 Final context verification:")
        print(f"   Session ID: {final_context.get('session_id')}")
        print(f"   History entries: {len(final_context.get('history', []))}")
        for i, entry in enumerate(final_context.get('history', []), 1):
            print(f"   Entry {i}: {entry['query'][:50]}...")
    
    return context_working and work_context_working

def main():
    """Run the live context test"""
    print("🚀 Testing Live Context Usage")
    print("=" * 50)
    
    try:
        success = test_conversation_context()
        
        print("\n" + "=" * 50)
        if success:
            print("🎉 CONTEXT IS WORKING CORRECTLY!")
            print("The agent is successfully using conversation context.")
        else:
            print("⚠️  CONTEXT MAY NOT BE WORKING PROPERLY")
            print("The agent may not be using context as expected.")
            print("\nPossible issues:")
            print("1. Agent is not processing context properly")
            print("2. Context format is not optimal")
            print("3. Agent session management issues")
        
        return success
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        logger.exception("Test error")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)