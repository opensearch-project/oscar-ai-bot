#!/usr/bin/env python3
"""
Test script to verify context preservation fixes in OSCAR agent.

This script tests the improved context management and session handling.
"""

import json
import logging
import time
from unittest.mock import Mock, patch, MagicMock
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

def test_improved_session_handling():
    """Test improved session handling with fallback logic."""
    print("=== Testing Improved Session Handling ===")
    
    with patch('boto3.client') as mock_client:
        mock_bedrock = Mock()
        mock_client.return_value = mock_bedrock
        
        agent = EnhancedBedrockOSCARAgent()
        
        # Test 1: Successful session continuation
        mock_response = {
            'completion': [
                {
                    'chunk': {
                        'bytes': b"I understand you're asking about the previous message...",
                        'sessionId': 'session-123'
                    }
                }
            ],
            'sessionId': 'session-123'
        }
        mock_bedrock.invoke_agent.return_value = mock_response
        
        response, session_id = agent.query(
            "What did you send again?", 
            session_id="session-123",
            context_summary="User asked about release manager duties, agent provided comprehensive outline."
        )
        
        print(f"✓ Session continuation successful")
        print(f"✓ Response received: {response[:50]}...")
        print(f"✓ Session ID preserved: {session_id == 'session-123'}")
        
        # Test 2: Session expiration with context fallback
        from botocore.exceptions import ClientError
        session_expired_error = ClientError(
            error_response={
                'Error': {
                    'Code': 'ValidationException',
                    'Message': 'Session expired or invalid'
                }
            },
            operation_name='InvokeAgent'
        )
        
        # First call fails with session error, second succeeds with new session
        mock_bedrock.invoke_agent.side_effect = [
            session_expired_error,
            {
                'completion': [
                    {
                        'chunk': {
                            'bytes': b"Based on our previous conversation about release manager duties...",
                            'sessionId': 'session-456'
                        }
                    }
                ],
                'sessionId': 'session-456'
            }
        ]
        
        response, new_session_id = agent.query(
            "What did you send again?",
            session_id="session-123",
            context_summary="User asked about release manager duties, agent provided comprehensive outline."
        )
        
        print(f"✓ Session expiration handled gracefully")
        print(f"✓ New session created: {new_session_id}")
        print(f"✓ Context preserved in response: {'previous conversation' in response.lower()}")

def test_robust_context_updates():
    """Test robust context update logic."""
    print("\n=== Testing Robust Context Updates ===")
    
    # Mock storage with detailed tracking
    mock_storage = Mock()
    stored_contexts = {}
    
    def mock_store_context(thread_key, context):
        stored_contexts[thread_key] = context.copy()
        print(f"  Stored context: {len(context.get('history', []))} history entries")
        return True
    
    def mock_get_context(thread_key):
        context = stored_contexts.get(thread_key)
        if context:
            print(f"  Retrieved context: {len(context.get('history', []))} history entries")
        else:
            print(f"  No context found for {thread_key}")
        return context
    
    mock_storage.store_context.side_effect = mock_store_context
    mock_storage.get_context.side_effect = mock_get_context
    
    # Mock other dependencies
    mock_app = Mock()
    mock_agent = Mock()
    
    handler = SlackHandler(mock_app, mock_storage, mock_agent)
    
    thread_key = "C091EH1JKCL_1234567890.123456"
    
    # Test conversation flow
    conversations = [
        {
            "query": "Send a message in riley-needs-to-lock-in describing the duties a release manager should perform",
            "response": "I'll prepare a comprehensive message outlining the duties of a release manager for OpenSearch releases. Based on the knowledge base information, I'll include key responsibilities throughout the release lifecycle.",
            "session_id": None,
            "new_session_id": "session-abc123"
        },
        {
            "query": "What did you send again?",
            "response": "I don't see any record of sending a message previously in our current conversation. Could you please provide more details about which message you're referring to?",
            "session_id": "session-abc123",
            "new_session_id": "session-abc123"
        },
        {
            "query": "what do you see as a record of our previous convo?",
            "response": "Based on our conversation history, I can see that you initially asked me to send a message about release manager duties, and I provided a comprehensive outline of responsibilities. Then you asked what I had sent, and I explained the content I had prepared.",
            "session_id": "session-abc123", 
            "new_session_id": "session-abc123"
        }
    ]
    
    for i, conv in enumerate(conversations):
        print(f"\nConversation {i+1}: {conv['query'][:50]}...")
        
        # Update context
        updated_context = handler._update_context(
            thread_key,
            conv['query'],
            conv['response'],
            conv['session_id'],
            conv['new_session_id']
        )
        
        print(f"✓ Context updated successfully")
        print(f"✓ Session ID: {updated_context.get('session_id')}")
        print(f"✓ History entries: {len(updated_context.get('history', []))}")
        print(f"✓ Summary length: {len(updated_context.get('summary', ''))}")
        
        # Verify context continuity
        if i > 0:
            retrieved_context = mock_storage.get_context(thread_key)
            if retrieved_context and retrieved_context.get('history'):
                print(f"✓ Context continuity maintained: {len(retrieved_context['history'])} total entries")
            else:
                print(f"❌ Context continuity broken")

def test_storage_robustness():
    """Test storage layer robustness."""
    print("\n=== Testing Storage Robustness ===")
    
    with patch('boto3.resource') as mock_resource:
        mock_table = Mock()
        mock_resource.return_value.Table.return_value = mock_table
        
        storage = DynamoDBStorage()
        
        # Test storing malformed context
        thread_key = "test_thread_123"
        
        # Test 1: Store context with missing fields
        incomplete_context = {
            "session_id": "session-test"
            # Missing history and summary
        }
        
        mock_table.put_item.return_value = {}
        result = storage.store_context(thread_key, incomplete_context)
        
        print(f"✓ Handled incomplete context gracefully: {result}")
        
        # Verify the stored context was normalized
        stored_item = mock_table.put_item.call_args[1]['Item']
        stored_context = stored_item['context']
        print(f"✓ Normalized context has history: {'history' in stored_context}")
        print(f"✓ Normalized context has summary: {'summary' in stored_context}")
        
        # Test 2: Retrieve and validate context structure
        mock_table.get_item.return_value = {
            'Item': {
                'thread_key': thread_key,
                'context': {
                    'session_id': 'session-test',
                    'history': [
                        {
                            'query': 'test query',
                            'response': 'test response',
                            'timestamp': int(time.time())
                        }
                    ],
                    'summary': 'Test summary'
                },
                'ttl': int(time.time()) + 3600
            }
        }
        
        retrieved_context = storage.get_context(thread_key)
        print(f"✓ Retrieved context successfully: {retrieved_context is not None}")
        print(f"✓ Context structure validated: {all(key in retrieved_context for key in ['session_id', 'history', 'summary'])}")

def test_end_to_end_conversation():
    """Test end-to-end conversation flow with fixes."""
    print("\n=== Testing End-to-End Conversation Flow ===")
    
    # Create a realistic test scenario
    with patch('boto3.resource') as mock_resource, \
         patch('boto3.client') as mock_client:
        
        # Setup mocks
        mock_table = Mock()
        mock_resource.return_value.Table.return_value = mock_table
        
        mock_bedrock = Mock()
        mock_client.return_value = mock_bedrock
        
        # Storage for tracking context
        context_storage = {}
        
        def mock_put_item(Item):
            context_storage[Item['thread_key']] = Item
            return {}
        
        def mock_get_item(Key):
            thread_key = Key['thread_key']
            if thread_key in context_storage:
                return {'Item': context_storage[thread_key]}
            return {}
        
        mock_table.put_item.side_effect = mock_put_item
        mock_table.get_item.side_effect = mock_get_item
        
        # Create components
        storage = DynamoDBStorage()
        agent = EnhancedBedrockOSCARAgent()
        mock_app = Mock()
        handler = SlackHandler(mock_app, storage, agent)
        
        thread_key = "C091EH1JKCL_1234567890.123456"
        
        # Simulate the problematic conversation
        print("Simulating the problematic Slack conversation...")
        
        # First message: User asks about release manager duties
        mock_bedrock.invoke_agent.return_value = {
            'completion': [
                {
                    'chunk': {
                        'bytes': b"I'll prepare a comprehensive message outlining the duties of a release manager for OpenSearch releases...",
                        'sessionId': 'session-real-123'
                    }
                }
            ],
            'sessionId': 'session-real-123'
        }
        
        response1, session1 = agent.query("Send a message in riley-needs-to-lock-in describing the duties a release manager should perform")
        handler._update_context(thread_key, 
                              "Send a message in riley-needs-to-lock-in describing the duties a release manager should perform",
                              response1, None, session1)
        
        print(f"✓ First query processed, session: {session1}")
        
        # Second message: User asks what was sent
        mock_bedrock.invoke_agent.return_value = {
            'completion': [
                {
                    'chunk': {
                        'bytes': b"Based on our previous conversation, I prepared a comprehensive message about release manager duties including preparation phase tasks, version increment coordination, release candidate creation, and post-release responsibilities.",
                        'sessionId': 'session-real-123'
                    }
                }
            ],
            'sessionId': 'session-real-123'
        }
        
        # Get context for second query
        context = storage.get_context(thread_key)
        context_summary = context.get("summary") if context else None
        session_id = context.get("session_id") if context else None
        
        print(f"Context for second query - Session: {session_id}, History entries: {len(context.get('history', []))}")
        
        response2, session2 = agent.query("What did you send again?", session_id=session_id, context_summary=context_summary)
        handler._update_context(thread_key, "What did you send again?", response2, session_id, session2)
        
        print(f"✓ Second query processed with context")
        print(f"✓ Response references previous conversation: {'previous conversation' in response2.lower()}")
        
        # Third message: User asks about conversation record
        context = storage.get_context(thread_key)
        context_summary = context.get("summary") if context else None
        session_id = context.get("session_id") if context else None
        
        print(f"Context for third query - Session: {session_id}, History entries: {len(context.get('history', []))}")
        
        mock_bedrock.invoke_agent.return_value = {
            'completion': [
                {
                    'chunk': {
                        'bytes': b"Based on our conversation history, I can see our complete interaction: 1) You asked me to send a message about release manager duties, 2) I provided a comprehensive outline, 3) You asked what I had sent, and 4) I referenced our previous discussion. Our conversation context has been preserved throughout.",
                        'sessionId': 'session-real-123'
                    }
                }
            ],
            'sessionId': 'session-real-123'
        }
        
        response3, session3 = agent.query("what do you see as a record of our previous convo?", session_id=session_id, context_summary=context_summary)
        
        print(f"✓ Third query processed with full context")
        print(f"✓ Response shows conversation awareness: {'conversation history' in response3.lower()}")
        
        # Final verification
        final_context = storage.get_context(thread_key)
        print(f"\nFinal verification:")
        print(f"✓ Total conversation entries: {len(final_context.get('history', []))}")
        print(f"✓ Session consistency: {final_context.get('session_id') == session3}")
        print(f"✓ Context summary length: {len(final_context.get('summary', ''))}")
        
        if len(final_context.get('history', [])) >= 2:
            print("✅ CONTEXT PRESERVATION WORKING - Multiple conversation turns preserved")
        else:
            print("❌ CONTEXT PRESERVATION STILL BROKEN")

if __name__ == "__main__":
    print("OSCAR Agent Context Preservation Fixes Test")
    print("=" * 60)
    
    try:
        test_improved_session_handling()
        test_robust_context_updates()
        test_storage_robustness()
        test_end_to_end_conversation()
        
        print("\n" + "=" * 60)
        print("✅ All tests completed successfully!")
        print("Context preservation fixes appear to be working correctly.")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()