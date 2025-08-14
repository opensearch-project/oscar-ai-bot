#!/usr/bin/env python3

import json
import boto3
import os
from datetime import datetime, timedelta

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

def debug_timestamp_query():
    """Query by timestamp range to find missing RC 6 data"""
    
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    
    print(f"🔍 Debugging with Timestamp Range Query")
    print(f"{'='*80}")
    print(f"Strategy: Query for all version 3.2.0 results in the last 24 hours")
    print(f"to see if we can find the missing 377 RC 6 results")
    print()
    
    # Calculate 24 hours ago timestamp
    now = datetime.now()
    hours_ago_24 = now - timedelta(hours=24)
    timestamp_24h_ago = int(hours_ago_24.timestamp() * 1000)
    
    print(f"Current time: {now}")
    print(f"24 hours ago: {hours_ago_24}")
    print(f"Timestamp (24h ago): {timestamp_24h_ago}")
    print()
    
    # We need to modify our Lambda function to support timestamp range queries
    # For now, let's get all results and filter by timestamp in our analysis
    
    test_payload = {
        'actionGroup': 'integration-test-metrics-actions',
        'function': 'get_integration_test_metrics',
        'parameters': [
            {'name': 'version', 'value': '3.2.0'}
        ]
    }
    
    print(f"🚀 Getting all version 3.2.0 results to analyze by timestamp...")
    
    try:
        response = lambda_client.invoke(
            FunctionName='oscar-test-metrics-agent-new',
            InvocationType='RequestResponse',
            Payload=json.dumps(test_payload)
        )
        
        response_payload = json.loads(response['Payload'].read())
        
        if response.get('FunctionError'):
            print(f"❌ Function Error: {response_payload}")
            return
        
        # Extract results
        if 'response' in response_payload and 'functionResponse' in response_payload['response']:
            function_response = response_payload['response']['functionResponse']
            if 'responseBody' in function_response and 'TEXT' in function_response['responseBody']:
                body_data = json.loads(function_response['responseBody']['TEXT']['body'])
                
                results = body_data.get('results', [])
                print(f"✅ Got {len(results)} total results")
                
                # Filter by last 24 hours
                recent_results = []
                rc_counts_recent = {}
                
                for result in results:
                    timestamp = result.get('build_start_time')
                    if timestamp and timestamp >= timestamp_24h_ago:
                        recent_results.append(result)
                        
                        rc = result.get('rc_number')
                        if rc is not None:
                            rc_counts_recent[rc] = rc_counts_recent.get(rc, 0) + 1
                
                print(f"📊 Results in last 24 hours: {len(recent_results)}")
                print(f"📊 RC distribution in last 24h: {dict(sorted(rc_counts_recent.items()))}")
                
                # Check if we're missing data by comparing with our known RC 6 count
                rc6_recent = rc_counts_recent.get(6, 0)
                print(f"🎯 RC 6 results in last 24h from our query: {rc6_recent}")
                print(f"🎯 RC 6 results expected from dashboard: 377")
                print(f"🎯 Missing RC 6 results: {377 - rc6_recent}")
                
                if rc6_recent < 377:
                    print(f"\n❗ CONFIRMED: We're missing {377 - rc6_recent} RC 6 results!")
                    print(f"❗ This suggests our query is not accessing all the data")
                    
                    # Check what we are getting
                    if recent_results:
                        print(f"\n📋 What we ARE getting in last 24h:")
                        for rc, count in sorted(rc_counts_recent.items()):
                            print(f"   RC {rc}: {count} results")
                        
                        # Show timestamp range of what we got
                        timestamps = [r.get('build_start_time') for r in recent_results if r.get('build_start_time')]
                        if timestamps:
                            min_ts = min(timestamps)
                            max_ts = max(timestamps)
                            min_date = datetime.fromtimestamp(min_ts / 1000)
                            max_date = datetime.fromtimestamp(max_ts / 1000)
                            
                            print(f"\n⏰ Timestamp range of our results:")
                            print(f"   Oldest: {min_date}")
                            print(f"   Newest: {max_date}")
                            print(f"   Span: {(max_ts - min_ts) / (1000 * 60 * 60):.1f} hours")
                    
                    print(f"\n🔍 Possible reasons for missing data:")
                    print(f"1. Index pattern issue - not querying all monthly indices")
                    print(f"2. Permission issue - can't access some indices")
                    print(f"3. Size limit issue - hitting 10,000 result limit")
                    print(f"4. Time zone issue - dashboard uses different time zone")
                    print(f"5. Different version format - dashboard might use different version string")
                
                # Check if we're hitting size limits
                if len(results) >= 1000:
                    print(f"\n❗ We hit our size limit of {len(results)} results")
                    print(f"❗ There might be more data beyond what we're seeing")
                    print(f"❗ The missing RC 6 results might be in the data we're not retrieving")
                
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

def suggest_next_steps():
    """Suggest next steps to find the missing data"""
    print(f"\n🚀 Next Steps to Find Missing RC 6 Data:")
    print(f"{'='*80}")
    print(f"1. Increase size limit to maximum (10,000) for version-only queries")
    print(f"2. Add timestamp range filtering to get recent data first")
    print(f"3. Check if dashboard uses different version format (3.2.0 vs 3.2)")
    print(f"4. Verify index permissions for wildcard pattern")
    print(f"5. Check if dashboard includes different data sources")
    print(f"6. Try querying specific monthly indices directly")

if __name__ == "__main__":
    debug_timestamp_query()
    suggest_next_steps()