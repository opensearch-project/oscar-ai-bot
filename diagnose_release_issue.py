#!/usr/bin/env python3

import sys
import os

# Load environment variables first
from dotenv import load_dotenv
load_dotenv('/Users/divsen/Desktop/OSCAR/OSCAR/.env')

sys.path.append('/Users/divsen/Desktop/OSCAR/OSCAR/oscar-agent')

from oscar_agent import EnhancedBedrockOSCARAgent
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def diagnose_release_issue():
    """Diagnose why release queries return None/empty responses."""
    
    # Create OSCAR agent (supervisor agent)
    agent = EnhancedBedrockOSCARAgent()
    
    # Test queries
    test_queries = [
        ("WORKING", "What is OpenSearch?"),
        ("FAILING", "What is the current release status?")
    ]
    
    for query_type, query in test_queries:
        print(f"\n{'='*60}")
        print(f"Testing {query_type}: {query}")
        print('='*60)
        
        try:
            response, session_id = agent.query(query)
            
            print(f"Response type: {type(response)}")
            print(f"Response is None: {response is None}")
            print(f"Response length: {len(response) if response else 0}")
            print(f"Response empty: {response.strip() == '' if response else 'N/A'}")
            print(f"Session ID: {session_id}")
            
            if response:
                print(f"Response preview: {response[:200]}...")
            else:
                print("❌ RESPONSE IS NONE - This is the Slack issue!")
                
        except Exception as e:
            print(f"❌ ERROR: {e}")
            logger.error(f"Query failed: {e}", exc_info=True)

if __name__ == "__main__":
    diagnose_release_issue()