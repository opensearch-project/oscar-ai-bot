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

def test_all_metrics():
    """Test all metrics types to see which ones get throttled."""
    
    agent = EnhancedBedrockOSCARAgent()
    
    test_queries = [
        ("TEST", "Show me test metrics"),
        ("BUILD", "Show me build metrics"), 
        ("DEPLOYMENT", "Show me deployment metrics"),
        ("RELEASE", "Show me release metrics")
    ]
    
    results = {}
    
    for i, (metric_type, query) in enumerate(test_queries):
        print(f"\n{'='*60}")
        print(f"Test {i+1} ({metric_type}): {query}")
        print('='*60)
        
        try:
            start_time = time.time()
            response, session_id = agent.query(query)
            end_time = time.time()
            
            success = response is not None and response.strip() != ""
            duration = end_time - start_time
            
            results[metric_type] = {
                'success': success,
                'duration': duration,
                'response_length': len(response) if response else 0,
                'error': None
            }
            
            print(f"Success: {success}")
            print(f"Duration: {duration:.2f}s")
            print(f"Response length: {len(response) if response else 0}")
            
            if not success:
                print("❌ FAILED - This causes Slack issue!")
            else:
                print("✅ SUCCESS")
                
        except Exception as e:
            results[metric_type] = {
                'success': False,
                'duration': 0,
                'response_length': 0,
                'error': str(e)
            }
            print(f"❌ ERROR: {e}")
        
        # Wait between requests
        if i < len(test_queries) - 1:
            print("Waiting 15 seconds...")
            time.sleep(15)
    
    print(f"\n{'='*60}")
    print("SUMMARY")
    print('='*60)
    for metric_type, result in results.items():
        status = "✅ SUCCESS" if result['success'] else "❌ FAILED"
        print(f"{metric_type:12} {status:12} {result['duration']:6.2f}s")
        if result['error']:
            print(f"             Error: {result['error']}")

if __name__ == "__main__":
    test_all_metrics()