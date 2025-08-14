#!/usr/bin/env python3

import json
import boto3
import os
from datetime import datetime

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

def debug_sorting_issue():
    """Debug the sorting issue - why are we getting RC 0 as the newest results?"""
    
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    
    print(f"🔍 Debugging Sorting Issue - RC 0 vs RC 6 Timestamps")
    print(f"{'='*80}")
    print(f"Hypothesis: RC 0 should be oldest, RC 6 should be newest.")
    print(f"If we're getting RC 0 as newest, there's a sorting or data issue.")
    print()
    
    # Get version-only results to analyze timestamps
    test_payload = {
        'actionGroup': 'integration-test-metrics-actions',
        'function': 'get_integration_test_metrics',
        'parameters': [
            {'name': 'version', 'value': '3.2.0'}
        ]
    }
    
    print(f"🚀 Getting version 3.2.0 results to analyze timestamps...")
    
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
                print(f"✅ Got {len(results)} results")
                
                if results:
                    # Analyze timestamps by RC
                    rc_timestamps = {}
                    
                    for result in results:
                        rc = result.get('rc_number')
                        timestamp = result.get('build_start_time')
                        
                        if rc is not None and timestamp:
                            if rc not in rc_timestamps:
                                rc_timestamps[rc] = []
                            rc_timestamps[rc].append(timestamp)
                    
                    print(f"\n📊 Timestamp Analysis by RC:")
                    print(f"{'RC':<4} {'Count':<6} {'Min Timestamp':<15} {'Max Timestamp':<15} {'Min Date':<20} {'Max Date':<20}")
                    print(f"-" * 100)
                    
                    for rc in sorted(rc_timestamps.keys()):
                        timestamps = rc_timestamps[rc]
                        min_ts = min(timestamps)
                        max_ts = max(timestamps)
                        min_date = datetime.fromtimestamp(min_ts / 1000).strftime('%Y-%m-%d %H:%M:%S')
                        max_date = datetime.fromtimestamp(max_ts / 1000).strftime('%Y-%m-%d %H:%M:%S')
                        
                        print(f"{rc:<4} {len(timestamps):<6} {min_ts:<15} {max_ts:<15} {min_date:<20} {max_date:<20}")
                    
                    # Check if results are actually sorted by timestamp
                    print(f"\n🔍 Sorting Verification:")
                    first_10_timestamps = []
                    first_10_rcs = []
                    
                    for i, result in enumerate(results[:10]):
                        timestamp = result.get('build_start_time')
                        rc = result.get('rc_number')
                        if timestamp:
                            first_10_timestamps.append(timestamp)
                            first_10_rcs.append(rc)
                            date_str = datetime.fromtimestamp(timestamp / 1000).strftime('%Y-%m-%d %H:%M:%S')
                            print(f"  {i+1:2d}. RC {rc:<2} - {timestamp} ({date_str})")
                    
                    # Check if timestamps are in descending order
                    is_sorted_desc = all(first_10_timestamps[i] >= first_10_timestamps[i+1] 
                                       for i in range(len(first_10_timestamps)-1))
                    
                    print(f"\n✅ Results sorted by timestamp DESC: {is_sorted_desc}")
                    
                    if is_sorted_desc:
                        print(f"✅ Sorting is working correctly")
                        print(f"❗ This means RC 0 entries genuinely have the newest timestamps!")
                        print(f"❗ This suggests RC 0 might represent:")
                        print(f"   - Latest development builds")
                        print(f"   - Post-release builds")
                        print(f"   - Builds that haven't been assigned an RC yet")
                    else:
                        print(f"❌ Sorting is NOT working correctly")
                        print(f"❌ This explains why we're not getting the right results")
                    
                    # Show the newest RC 6 result vs newest RC 0 result
                    rc6_results = [r for r in results if r.get('rc_number') == 6]
                    rc0_results = [r for r in results if r.get('rc_number') == 0]
                    
                    if rc6_results and rc0_results:
                        newest_rc6 = max(rc6_results, key=lambda x: x.get('build_start_time', 0))
                        newest_rc0 = max(rc0_results, key=lambda x: x.get('build_start_time', 0))
                        
                        rc6_date = datetime.fromtimestamp(newest_rc6['build_start_time'] / 1000)
                        rc0_date = datetime.fromtimestamp(newest_rc0['build_start_time'] / 1000)
                        
                        print(f"\n🆚 Newest Result Comparison:")
                        print(f"   Newest RC 6: {rc6_date} (timestamp: {newest_rc6['build_start_time']})")
                        print(f"   Newest RC 0: {rc0_date} (timestamp: {newest_rc0['build_start_time']})")
                        
                        if newest_rc0['build_start_time'] > newest_rc6['build_start_time']:
                            print(f"❗ RC 0 is indeed newer than RC 6!")
                            print(f"❗ This suggests RC 0 represents ongoing development builds")
                        else:
                            print(f"✅ RC 6 is newer than RC 0, as expected")
                
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

def suggest_solutions():
    """Suggest solutions based on the findings"""
    print(f"\n💡 Potential Solutions:")
    print(f"{'='*80}")
    print(f"If RC 0 represents ongoing development builds (newer than RC 6):")
    print(f"1. Filter out RC 0 when looking for specific RC results")
    print(f"2. Use a different sorting strategy for RC-specific queries")
    print(f"3. Query by RC first, then sort within that RC")
    print(f"4. Use aggregation to get counts by RC before limiting results")
    print()
    print(f"If the dashboard shows 360 RC 6 results, we need to:")
    print(f"1. Query ALL RC 6 results regardless of timestamp")
    print(f"2. Remove the global timestamp sorting when filtering by RC")
    print(f"3. Sort RC 6 results by their own timestamps")

if __name__ == "__main__":
    debug_sorting_issue()
    suggest_solutions()