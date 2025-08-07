#!/usr/bin/env python3

import json
import boto3
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_release_vs_other():
    """Compare release queries vs other queries to identify the specific issue."""
    
    agent_id = 'NFCKXG7OIN'
    agent_alias_id = 'KNFTCYYHPT'
    bedrock_client = boto3.client('bedrock-agent-runtime', region_name='us-east-1')
    
    # Test pairs: (query_type, query)
    test_queries = [
        ("NON-RELEASE", "What is OpenSearch?"),
        ("RELEASE", "What is the current release status?"),
        ("NON-RELEASE", "How do I configure OpenSearch?"),
        ("RELEASE", "Show me release metrics")
    ]
    
    for i, (query_type, query) in enumerate(test_queries, 1):
        print(f"\n{'='*60}")
        print(f"TEST {i} ({query_type}): {query}")
        print('='*60)
        
        try:
            session_id = f"test-{int(time.time())}-{i}"
            
            response = bedrock_client.invoke_agent(
                agentId=agent_id,
                agentAliasId=agent_alias_id,
                inputText=query,
                sessionId=session_id
            )
            
            response_text = ""
            if 'completion' in response:
                for event in response['completion']:
                    if 'chunk' in event and 'bytes' in event['chunk']:
                        response_text += event['chunk']['bytes'].decode('utf-8')
            
            print(f"Response Length: {len(response_text)}")
            print(f"Is None/Empty: {response_text is None or response_text.strip() == ''}")
            
            if response_text is None or response_text.strip() == "":
                print("❌ PROBLEM: Response is None or empty!")
            else:
                print("✅ Response received successfully")
                print(f"Preview: {response_text[:100]}...")
                
        except Exception as e:
            print(f"❌ ERROR: {e}")
        
        # Add delay to avoid throttling
        time.sleep(5)

if __name__ == "__main__":
    test_release_vs_other()