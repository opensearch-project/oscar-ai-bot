#!/usr/bin/env python3

import sys
import os
import time

# Load environment variables first
from dotenv import load_dotenv
load_dotenv('/Users/divsen/Desktop/OSCAR/OSCAR/.env')

sys.path.append('/Users/divsen/Desktop/OSCAR/OSCAR/oscar-agent')

from oscar_agent import EnhancedBedrockOSCARAgent
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_with_delays():
    """Test release queries with proper delays to avoid throttling."""
    
    agent = EnhancedBedrockOSCARAgent()
    
    test_queries = [
        ("NON-RELEASE", "What is OpenSearch?"),
        ("RELEASE", "What is the current release status?"),
        ("RELEASE", "Show me release metrics")
    ]
    
    for i, (query_type, query) in enumerate(test_queries):
        print(f"\n{'='*60}")
        print(f"Test {i+1} ({query_type}): {query}")
        print('='*60)
        
        try:
            response, session_id = agent.query(query)
            
            print(f"Response is None: {response is None}")
            print(f"Response length: {len(response) if response else 0}")
            
            if response is None:
                print("❌ RESPONSE IS NONE - This causes Slack issue!")
            else:
                print("✅ Response received successfully")
                print(f"Preview: {response[:100]}...")
                
        except Exception as e:
            print(f"❌ ERROR: {e}")
        
        # Wait 10 seconds between requests to avoid throttling
        if i < len(test_queries) - 1:
            print("Waiting 10 seconds to avoid throttling...")
            time.sleep(10)

if __name__ == "__main__":
    test_with_delays()