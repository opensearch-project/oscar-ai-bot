#!/usr/bin/env python3

import json
import boto3
import os
from datetime import datetime

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

def test_index_pattern_debug():
    """Debug if we're querying the right index pattern"""
    
    print(f"🔍 Debugging Index Pattern Issue")
    print(f"{'='*80}")
    print(f"From the earlier error, we saw multiple indices:")
    print(f"- opensearch-integration-test-results-08-2025")
    print(f"- opensearch-integration-test-results-07-2025")
    print(f"- etc.")
    print()
    print(f"But we're querying: /opensearch-integration-test-results/_search")
    print(f"This might be an index pattern that doesn't include all the data!")
    print()
    
    # Let's check what happens if we query with a wildcard pattern
    # We'll need to modify our Lambda function to test this
    
    print(f"💡 Hypothesis:")
    print(f"The dashboard queries ALL monthly indices (opensearch-integration-test-results-*)")
    print(f"But we're only querying the main index (opensearch-integration-test-results)")
    print(f"The main index might only have a subset of the data!")
    print()
    
    print(f"🔍 Evidence from earlier error message:")
    print(f"The OpenSearch error showed these indices being queried:")
    indices = [
        "opensearch-integration-test-results-08-2025",
        "opensearch-integration-test-results-07-2025", 
        "opensearch-integration-test-results-06-2025",
        "opensearch-integration-test-results-05-2025",
        "opensearch-integration-test-results-04-2025",
        "opensearch-integration-test-results-03-2025",
        "opensearch-integration-test-results-02-2025",
        "opensearch-integration-test-results-01-2025",
        "opensearch-integration-test-results-12-2024",
        "opensearch-integration-test-results-11-2024",
        "opensearch-integration-test-results-10-2024",
        "opensearch-integration-test-results-09-2024",
        "opensearch-integration-test-results-08-2024",
        "opensearch-integration-test-results-07-2024"
    ]
    
    for index in indices:
        print(f"   - {index}")
    
    print(f"\n🎯 Solution:")
    print(f"We need to modify our query to use the wildcard pattern:")
    print(f"From: /opensearch-integration-test-results/_search")
    print(f"To:   /opensearch-integration-test-results-*/_search")
    print()
    print(f"This would query ALL monthly indices and give us the complete dataset!")
    print(f"That's likely why the dashboard shows 377 results and we only get 49.")

def check_current_month_data():
    """Check if current month data is in a separate index"""
    print(f"\n📅 Current Month Analysis:")
    print(f"{'='*80}")
    
    now = datetime.now()
    current_month_index = f"opensearch-integration-test-results-{now.strftime('%m-%Y')}"
    
    print(f"Current date: {now.strftime('%Y-%m-%d')}")
    print(f"Expected current month index: {current_month_index}")
    print()
    print(f"If RC 6 data is recent (last 24 hours), it's likely in:")
    print(f"   - {current_month_index}")
    print(f"   - opensearch-integration-test-results-08-2025 (August 2025)")
    print()
    print(f"But we're querying the base index which might not have the latest data!")

if __name__ == "__main__":
    test_index_pattern_debug()
    check_current_month_data()