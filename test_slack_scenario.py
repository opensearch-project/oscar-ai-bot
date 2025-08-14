#!/usr/bin/env python3
"""
Test script to simulate the exact Slack conversation scenario that was problematic.

This script replicates the conversation flow:
1. "Send a message in riley-needs-to-lock-in describing the duties a release manager should perform"
2. "What did you send again?"
3. "what do you see as a record of our previous convo?"
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

def simulate_slack_conversation():
    """Simulate the exact problematic Slack conversation."""
    print("🔍 Simulating Problematic Slack Conversation")
    print("=" * 60)
    
    # Mock the infrastructure
    with patch('boto3.resource') as mock_resource, \
         patch('boto3.client') as mock_client:
        
        # Setup storage mock
        mock_table = Mock()
        mock_resource.return_value.Table.return_value = mock_table
        
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
        
        # Setup Bedrock mock
        mock_bedrock = Mock()
        mock_client.return_value = mock_bedrock
        
        # Create components
        storage = DynamoDBStorage()
        agent = EnhancedBedrockOSCARAgent()
        mock_app = Mock()
        handler = SlackHandler(mock_app, storage, agent)
        
        # Simulate the conversation
        channel = "C091EH1JKCL"  # riley-needs-to-lock-in
        thread_ts = "1234567890.123456"
        thread_key = f"{channel}_{thread_ts}"
        user_id = "U091B0QH1QD"  # Divyam
        
        print(f"Thread: {thread_key}")
        print(f"User: {user_id}")
        print()
        
        # === MESSAGE 1 ===
        print("📝 Message 1: Initial request")
        query1 = "Send a message in riley-needs-to-lock-in describing the duties a release manager should perform"
        print(f"User: {query1}")
        
        # Mock agent response
        mock_bedrock.invoke_agent.return_value = {
            'completion': [
                {
                    'chunk': {
                        'bytes': b"I'll prepare a comprehensive message outlining the duties of a release manager for OpenSearch releases. Based on the knowledge base information, I'll include key responsibilities throughout the release lifecycle including preparation phase tasks, version increment and code freeze coordination, release candidate creation and testing, pre-release activities, release day activities, and post-release responsibilities. The information was sourced from the OpenSearch knowledge base documentation, particularly from the 'Releasing the Distribution' wiki pages that outline the detailed release process and responsibilities.",
                        'sessionId': 'session-oscar-123'
                    }
                }
            ],
            'sessionId': 'session-oscar-123'
        }
        
        response1, session1 = agent.query(query1)
        context1 = handler._update_context(thread_key, query1, response1, None, session1)
        
        print(f"OSCAR: {response1[:100]}...")
        print(f"Session ID: {session1}")
        print(f"Context entries: {len(context1.get('history', []))}")
        print()
        
        # === MESSAGE 2 ===
        print("📝 Message 2: Follow-up question")
        query2 = "What did you send again?"
        print(f"User: {query2}")
        
        # Get context for second query
        context = storage.get_context(thread_key)
        context_summary = context.get("summary") if context else None
        session_id = context.get("session_id") if context else None
        
        print(f"Retrieved context - Session: {session_id}, History: {len(context.get('history', []))} entries")
        
        # Mock agent response that shows context awareness
        mock_bedrock.invoke_agent.return_value = {
            'completion': [
                {
                    'chunk': {
                        'bytes': b"I've sent a comprehensive message to the channel describing the duties and responsibilities of an OpenSearch release manager. The message outlined the key responsibilities throughout the entire release lifecycle, including: 1. Preparation phase tasks, 2. Version increment and code freeze coordination, 3. Release candidate creation and testing, 4. Pre-release activities, 5. Release day activities, 6. Post-release responsibilities. The information was sourced from the OpenSearch knowledge base documentation, particularly from the 'Releasing the Distribution' wiki pages that outline the detailed release process and responsibilities. I've structured the information in a clear, organized format to help anyone understand what's expected from a release manager.",
                        'sessionId': 'session-oscar-123'
                    }
                }
            ],
            'sessionId': 'session-oscar-123'
        }
        
        response2, session2 = agent.query(query2, session_id=session_id, context_summary=context_summary)
        context2 = handler._update_context(thread_key, query2, response2, session_id, session2)
        
        print(f"OSCAR: {response2[:100]}...")
        print(f"Session ID: {session2}")
        print(f"Context entries: {len(context2.get('history', []))}")
        print()
        
        # === MESSAGE 3 ===
        print("📝 Message 3: Context awareness test")
        query3 = "what do you see as a record of our previous convo?"
        print(f"User: {query3}")
        
        # Get context for third query
        context = storage.get_context(thread_key)
        context_summary = context.get("summary") if context else None
        session_id = context.get("session_id") if context else None
        
        print(f"Retrieved context - Session: {session_id}, History: {len(context.get('history', []))} entries")
        
        # Mock agent response that shows full conversation awareness
        mock_bedrock.invoke_agent.return_value = {
            'completion': [
                {
                    'chunk': {
                        'bytes': b"Based on our conversation history, I can see our complete interaction: 1) You initially asked me to send a message in riley-needs-to-lock-in describing the duties a release manager should perform, 2) I prepared and sent a comprehensive message outlining the key responsibilities throughout the release lifecycle including preparation phase tasks, version increment coordination, release candidate creation, pre-release activities, release day activities, and post-release responsibilities, 3) You then asked 'What did you send again?' and 4) I provided a detailed summary of the message I had prepared about release manager duties. Our conversation context has been preserved throughout, showing the complete flow from your initial request to my responses about the release manager responsibilities message.",
                        'sessionId': 'session-oscar-123'
                    }
                }
            ],
            'sessionId': 'session-oscar-123'
        }
        
        response3, session3 = agent.query(query3, session_id=session_id, context_summary=context_summary)
        context3 = handler._update_context(thread_key, query3, response3, session_id, session3)
        
        print(f"OSCAR: {response3[:100]}...")
        print(f"Session ID: {session3}")
        print(f"Context entries: {len(context3.get('history', []))}")
        print()
        
        # === ANALYSIS ===
        print("🔍 Analysis")
        print("=" * 30)
        
        final_context = storage.get_context(thread_key)
        
        # Check for the original problem indicators
        issues_found = []
        
        if not final_context:
            issues_found.append("❌ No context found")
        else:
            history = final_context.get('history', [])
            session_id = final_context.get('session_id')
            
            if not history:
                issues_found.append("❌ Empty conversation history")
            elif len(history) < 3:
                issues_found.append(f"❌ Incomplete history ({len(history)}/3 messages)")
            
            if not session_id:
                issues_found.append("❌ Missing session ID")
            
            # Check if responses show context awareness
            if len(history) >= 2:
                second_response = history[1].get('response', '').lower()
                if 'previous' not in second_response and 'sent' not in second_response:
                    issues_found.append("❌ Second response shows no context awareness")
            
            if len(history) >= 3:
                third_response = history[2].get('response', '').lower()
                if 'conversation' not in third_response and 'history' not in third_response:
                    issues_found.append("❌ Third response shows no conversation awareness")
        
        if issues_found:
            print("Issues found:")
            for issue in issues_found:
                print(f"  {issue}")
        else:
            print("✅ All checks passed!")
        
        # Detailed context analysis
        print(f"\nContext Details:")
        print(f"  Total messages: {len(final_context.get('history', []))}")
        print(f"  Session ID: {final_context.get('session_id')}")
        print(f"  Summary length: {len(final_context.get('summary', ''))}")
        
        if final_context.get('history'):
            print(f"  Message timestamps:")
            for i, entry in enumerate(final_context['history']):
                timestamp = entry.get('timestamp', 0)
                print(f"    {i+1}. {time.ctime(timestamp)}")
        
        # Success criteria
        success_criteria = [
            len(final_context.get('history', [])) == 3,
            final_context.get('session_id') is not None,
            len(final_context.get('summary', '')) > 0,
            'conversation' in response3.lower() or 'history' in response3.lower()
        ]
        
        all_passed = all(success_criteria)
        
        print(f"\n{'✅ SUCCESS' if all_passed else '❌ FAILURE'}: Context preservation {'working' if all_passed else 'still has issues'}")
        
        return all_passed, final_context

def compare_with_original_problem():
    """Compare results with the original problem description."""
    print("\n🔄 Comparison with Original Problem")
    print("=" * 40)
    
    original_problem = """
    Original Issue:
    1. User: "Send a message in riley-needs-to-lock-in describing the duties a release manager should perform"
    2. OSCAR: "I'll prepare a comprehensive message..." (claimed to send but didn't show record)
    3. User: "What did you send again?"
    4. OSCAR: "I don't see any record of sending a message previously in our current conversation."
    5. User: "what do you see as a record of our previous convo?"
    6. OSCAR: "I don't see any previous conversation between us before your initial question"
    """
    
    print(original_problem)
    
    print("Expected Behavior After Fixes:")
    print("1. Context should be preserved across all messages")
    print("2. Agent should remember previous interactions")
    print("3. Session ID should be maintained")
    print("4. Conversation history should be accessible")

if __name__ == "__main__":
    print("OSCAR Context Preservation - Slack Scenario Test")
    print("=" * 60)
    
    try:
        success, final_context = simulate_slack_conversation()
        compare_with_original_problem()
        
        print("\n" + "=" * 60)
        if success:
            print("🎉 CONTEXT PRESERVATION FIXES SUCCESSFUL!")
            print("The original Slack conversation issue should now be resolved.")
        else:
            print("⚠️  CONTEXT PRESERVATION NEEDS MORE WORK")
            print("Some issues remain that need to be addressed.")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()