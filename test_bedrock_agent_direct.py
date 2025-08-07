#!/usr/bin/env python3

import json
import boto3
import logging
import time
import os

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_bedrock_agent_direct():
    """Test the Bedrock agent directly with release queries."""
    
    # Use the supervisor agent directly - these are the actual working IDs from .env
    agent_id = 'NFCKXG7OIN'  # Supervisor agent ID
    agent_alias_id = 'KNFTCYYHPT'  # Supervisor agent alias ID
    
    print(f"Testing Supervisor Bedrock Agent: {agent_id} (alias: {agent_alias_id})")
    
    bedrock_client = boto3.client('bedrock-agent-runtime', region_name='us-east-1')
    
    # Test queries that should trigger release metrics
    test_queries = [
        "What is the current release status?",
        "Show me release metrics",
        "How many components are ready for release?",
        "What's the overall release readiness?"
    ]
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n{'='*60}")
        print(f"TEST {i}: {query}")
        print('='*60)
        
        try:
            session_id = f"test-session-{int(time.time())}-{i}"
            
            print(f"Invoking agent with session: {session_id}")
            
            response = bedrock_client.invoke_agent(
                agentId=agent_id,
                agentAliasId=agent_alias_id,
                inputText=query,
                sessionId=session_id
            )
            
            # Process streaming response
            response_text = ""
            session_id_returned = None
            
            if 'completion' in response:
                for event in response['completion']:
                    if 'chunk' in event:
                        chunk = event['chunk']
                        if 'bytes' in chunk:
                            chunk_text = chunk['bytes'].decode('utf-8')
                            response_text += chunk_text
                        
                        # Extract session ID from the chunk if available
                        if 'sessionId' in chunk:
                            session_id_returned = chunk['sessionId']
            
            # Also check for session ID at the top level
            if 'sessionId' in response:
                session_id_returned = response['sessionId']
            
            print(f"Session ID: {session_id_returned}")
            print(f"Response Length: {len(response_text)} characters")
            print(f"Response is None: {response_text is None}")
            print(f"Response is Empty: {response_text.strip() == ''}")
            print(f"Response Preview: {response_text[:200]}...")
            
            if response_text is None or response_text.strip() == "":
                print("❌ PROBLEM: Response is None or empty!")
            else:
                print("✅ Response received successfully")
                
        except Exception as e:
            print(f"❌ ERROR: {e}")
            logger.error(f"Bedrock agent test failed for query '{query}': {e}", exc_info=True)

if __name__ == "__main__":
    print("Testing Bedrock Agent Direct Invocation...")
    print("=" * 60)
    test_bedrock_agent_direct()