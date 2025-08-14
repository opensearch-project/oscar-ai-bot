#!/usr/bin/env python3
"""
Test script to verify context preservation issues in OSCAR agent.

This script simulates the conversation flow described in the Slack interaction
to identify where context is being lost.
"""

import json
import logging
import time
from unittest.mock import Mock, patch
import sys
import os

# Set required environment variables for testing
os.environ['OSCAR_BEDROCK_AGENT_ID'] = 'test-agent-id'
os.environ['OSCAR_BEDROCK_AGENT_ALIAS_ID'] = 'test-alias-id'
os.environ['SLACK_BOT_TOKEN'] = 'test-token'
os.environ['SLACK_SIGNING_SECRET'] = 'test-secret'

# Add oscar-agent to path
sys.path.append('oscar-agent')

from storage import DynamoDBStorage
from oscar_agent import EnhancedBedrockOSCARAgent
from slack_handler import SlackHandler

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_context_storage_retrieval():
    """Test basic context storage and retrieval functionality."""
    print("=== Testing Context Storage and Retrieval ===")
    
    # Mock DynamoDB for testing
    with patch('boto3.resource') as mock_resource:
        mock_table = Mock()
        mock_resource.return_value.Table.return_value = mock_table
        
        storage = DynamoDBStorage()
        
        # Test storing context
        thread_key = "C091EH1JKCL_1234567890.123456"
        test_context = {
            "session_id": "session-test-123",
            "history": [
                {
                    "query": "Send a message in riley-needs-to-lock-in describing the duties a release manager should perform",
                    "response": "I'll prepare a comprehensive message outlining the duties of a release manager for OpenSearch releases...",
                    "timestamp": int(time.time())
                }
            ],
            "summary": "User asked about release manager duties, agent responded with comprehensive outline."
        }
        
        # Mock successful storage
        mock_table.put_item.return_value = {}
        result = storage.store_context(thread_key, test_context)
        print(f"✓ Context storage result: {result}")
        
        # Mock successful retrieval
        mock_table.get_item.return_value = {
            'Item': {
                'thread_key': thread_key,
                'context': test_context,
                'ttl': int(time.time()) + 3600
            }
        }
        
        retrieved_context = storage.get_context(thread_key)
        print(f"✓ Retrieved context: {retrieved_context is not None}")
        print(f"✓ Session ID preserved: {retrieved_context.get('session_id') == test_context['session_id']}")
        print(f"✓ History preserved: {len(retrieved_context.get('history', [])) == 1}")

def test_session_id_propagation():
    """Test session ID propagation through the agent chain."""
    print("\n=== Testing Session ID Propagation ===")
    
    with patch('boto3.client') as mock_client:
        # Mock Bedrock agent response
        mock_bedrock = Mock()
        mock_client.return_value = mock_bedrock
        
        # Simulate agent response with session ID
        mock_response = {
            'completion': [
                {
                    'chunk': {
                        'bytes': b"I'll prepare a comprehensive message...",
                        'sessionId': 'bedrock-session-456'
                    }
                }
            ],
            'sessionId': 'bedrock-session-456'
        }
        mock_bedrock.invoke_agent.return_value = mock_response
        
        agent = EnhancedBedrockOSCARAgent()
        
        # Test query with no session ID
        response, session_id = agent.query("Test query")
        print(f"✓ Agent response received: {response is not None}")
        print(f"✓ Session ID returned: {session_id}")
        
        # Test query with existing session ID
        response2, session_id2 = agent.query("Follow-up query", session_id=session_id)
        print(f"✓ Follow-up response received: {response2 is not None}")
        print(f"✓ Session ID maintained: {session_id2 == session_id}")

def test_context_update_flow():
    """Test the complete context update flow in SlackHandler."""
    print("\n=== Testing Context Update Flow ===")
    
    # Mock dependencies
    mock_app = Mock()
    mock_storage = Mock()
    mock_agent = Mock()
    
    # Set up mock responses
    mock_storage.get_context.return_value = {
        "session_id": "existing-session-123",
        "history": [
            {
                "query": "Previous query",
                "response": "Previous response",
                "timestamp": int(time.time()) - 300
            }
        ],
        "summary": "Previous conversation context"
    }
    
    mock_agent.query.return_value = ("Agent response", "new-session-456")
    
    handler = SlackHandler(mock_app, mock_storage, mock_agent)
    
    # Test context update
    thread_key = "C091EH1JKCL_1234567890.123456"
    query = "What did you send again?"
    response = "Agent response"
    old_session_id = "existing-session-123"
    new_session_id = "new-session-456"
    
    updated_context = handler._update_context(
        thread_key, query, response, old_session_id, new_session_id
    )
    
    print(f"✓ Context updated: {updated_context is not None}")
    print(f"✓ Session ID updated: {updated_context.get('session_id') == new_session_id}")
    print(f"✓ History length: {len(updated_context.get('history', []))}")
    print(f"✓ Latest query in history: {updated_context['history'][-1]['query'] == query}")

def test_conversation_scenario():
    """Test the specific conversation scenario from the Slack interaction."""
    print("\n=== Testing Conversation Scenario ===")
    
    # Simulate the conversation flow
    conversations = [
        {
            "query": "Send a message in riley-needs-to-lock-in describing the duties a release manager should perform",
            "expected_response": "I'll prepare a comprehensive message...",
            "session_id": None
        },
        {
            "query": "What did you send again?",
            "expected_context": True,  # Should have context from previous message
            "session_id": "session-from-first-query"
        },
        {
            "query": "what do you see as a record of our previous convo?",
            "expected_context": True,  # Should still have context
            "session_id": "session-from-first-query"
        }
    ]
    
    # Mock storage to simulate the issue
    mock_storage = Mock()
    
    # First call - no context
    mock_storage.get_context.side_effect = [
        None,  # First query - no existing context
        {      # Second query - should have context but might be missing
            "session_id": "session-from-first-query",
            "history": [],  # Empty history indicates the problem
            "summary": ""
        },
        {      # Third query - still no proper context
            "session_id": "session-from-first-query", 
            "history": [],
            "summary": ""
        }
    ]
    
    for i, conv in enumerate(conversations):
        context = mock_storage.get_context(f"thread_{i}")
        print(f"Query {i+1}: {conv['query'][:50]}...")
        print(f"  Context available: {context is not None}")
        if context:
            print(f"  Session ID: {context.get('session_id')}")
            print(f"  History entries: {len(context.get('history', []))}")
            print(f"  Summary length: {len(context.get('summary', ''))}")
        
        if conv.get('expected_context') and (not context or not context.get('history')):
            print(f"  ❌ ISSUE: Expected context but none found or history is empty")
        else:
            print(f"  ✓ Context state as expected")

def identify_potential_issues():
    """Identify potential issues in the current implementation."""
    print("\n=== Identifying Potential Issues ===")
    
    issues = []
    
    # Issue 1: Session ID handling in agent
    print("1. Session ID Handling:")
    print("   - Agent creates new session if none provided")
    print("   - Session ID extraction from streaming response may be inconsistent")
    print("   - Fallback logic might not preserve session continuity")
    
    # Issue 2: Context storage timing
    print("\n2. Context Storage Timing:")
    print("   - Context is stored after agent response")
    print("   - If agent fails, context might not be updated")
    print("   - Race conditions possible with concurrent requests")
    
    # Issue 3: Context retrieval and session management
    print("\n3. Context Retrieval Issues:")
    print("   - Session ID might expire on Bedrock side")
    print("   - Context summary might not be properly formatted")
    print("   - Enhanced query construction might fail")
    
    # Issue 4: Error handling
    print("\n4. Error Handling:")
    print("   - Session failures fall back to context summary")
    print("   - Context summary failures fall back to plain query")
    print("   - Each fallback loses more context")
    
    return issues

if __name__ == "__main__":
    print("OSCAR Agent Context Preservation Test")
    print("=" * 50)
    
    try:
        test_context_storage_retrieval()
        test_session_id_propagation()
        test_context_update_flow()
        test_conversation_scenario()
        identify_potential_issues()
        
        print("\n" + "=" * 50)
        print("Test completed. Check output above for issues.")
        
    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()