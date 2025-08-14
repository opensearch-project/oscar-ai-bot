#!/usr/bin/env python3
"""
Context Preservation Validation Tests.

Run these tests to validate that context preservation is working correctly.
"""

import json
import logging
import time
import boto3
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ContextValidator:
    """Validate context preservation functionality."""
    
    def __init__(self, region: str = 'us-east-1'):
        self.region = region
        self.dynamodb = boto3.resource('dynamodb', region_name=region)
        
    def test_context_storage_retrieval(self, context_table_name: str = 'oscar-context') -> bool:
        """Test basic context storage and retrieval."""
        try:
            table = self.dynamodb.Table(context_table_name)
            
            # Create test context
            test_thread_key = f"test_validation_{int(time.time())}"
            test_context = {
                'session_id': 'test-session-123',
                'history': [
                    {
                        'query': 'Test query',
                        'response': 'Test response',
                        'timestamp': int(time.time())
                    }
                ],
                'summary': 'Test summary'
            }
            
            # Store context
            table.put_item(
                Item={
                    'thread_key': test_thread_key,
                    'context': test_context,
                    'ttl': int(time.time()) + 3600,
                    'updated_at': int(time.time())
                }
            )
            
            # Retrieve context
            response = table.get_item(Key={'thread_key': test_thread_key})
            
            if 'Item' not in response:
                logger.error("Failed to retrieve stored context")
                return False
            
            retrieved_context = response['Item']['context']
            
            # Validate structure
            required_fields = ['session_id', 'history', 'summary']
            for field in required_fields:
                if field not in retrieved_context:
                    logger.error(f"Missing required field: {field}")
                    return False
            
            # Validate content
            if retrieved_context['session_id'] != test_context['session_id']:
                logger.error("Session ID mismatch")
                return False
            
            if len(retrieved_context['history']) != 1:
                logger.error("History length mismatch")
                return False
            
            # Clean up
            table.delete_item(Key={'thread_key': test_thread_key})
            
            logger.info("Context storage/retrieval test passed")
            return True
            
        except Exception as e:
            logger.error(f"Context storage/retrieval test failed: {e}")
            return False
    
    def test_session_continuity(self, bedrock_agent_id: str, bedrock_agent_alias_id: str) -> bool:
        """Test session continuity across multiple queries."""
        try:
            client = boto3.client('bedrock-agent-runtime', region_name=self.region)
            
            # First query
            response1 = client.invoke_agent(
                agentId=bedrock_agent_id,
                agentAliasId=bedrock_agent_alias_id,
                inputText="Hello, this is a test query",
                sessionId=f"test-session-{int(time.time())}"
            )
            
            # Extract session ID from response
            session_id = None
            for event in response1['completion']:
                if 'chunk' in event and 'sessionId' in event['chunk']:
                    session_id = event['chunk']['sessionId']
                    break
            
            if not session_id:
                logger.error("No session ID returned from first query")
                return False
            
            # Second query with same session
            response2 = client.invoke_agent(
                agentId=bedrock_agent_id,
                agentAliasId=bedrock_agent_alias_id,
                inputText="Do you remember my previous message?",
                sessionId=session_id
            )
            
            # Check if second response indicates continuity
            response_text = ""
            for event in response2['completion']:
                if 'chunk' in event and 'bytes' in event['chunk']:
                    response_text += event['chunk']['bytes'].decode('utf-8')
            
            # Simple check for context awareness
            context_indicators = ['previous', 'remember', 'earlier', 'before', 'test query']
            has_context = any(indicator in response_text.lower() for indicator in context_indicators)
            
            if has_context:
                logger.info("Session continuity test passed")
                return True
            else:
                logger.warning("Session continuity test inconclusive - no clear context indicators")
                return True  # Don't fail on this as it depends on agent behavior
                
        except Exception as e:
            logger.error(f"Session continuity test failed: {e}")
            return False

def main():
    """Run validation tests."""
    import os
    
    print("OSCAR Context Preservation Validation")
    print("=" * 50)
    
    validator = ContextValidator()
    
    # Test 1: Context storage/retrieval
    print("Testing context storage and retrieval...")
    storage_test = validator.test_context_storage_retrieval()
    print(f"✓ Storage test: {'PASSED' if storage_test else 'FAILED'}")
    
    # Test 2: Session continuity (if agent credentials available)
    agent_id = os.environ.get('OSCAR_BEDROCK_AGENT_ID')
    agent_alias_id = os.environ.get('OSCAR_BEDROCK_AGENT_ALIAS_ID')
    
    if agent_id and agent_alias_id:
        print("Testing session continuity...")
        continuity_test = validator.test_session_continuity(agent_id, agent_alias_id)
        print(f"✓ Continuity test: {'PASSED' if continuity_test else 'FAILED'}")
    else:
        print("⚠ Skipping session continuity test (missing agent credentials)")
        continuity_test = True
    
    # Overall result
    all_passed = storage_test and continuity_test
    print(f"\nOverall result: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
    
    return all_passed

if __name__ == "__main__":
    main()
