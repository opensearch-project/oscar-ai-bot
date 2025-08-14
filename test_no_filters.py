#!/usr/bin/env python3

import json
import boto3
import os
from datetime import datetime, timedelta

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

def test_no_filters():
    """Test with no filters to see what data we can access"""
    
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    
    print(f"🔍 Testing with No Filters")
    print(f"{'='*80}")
    print(f"Goal: See what data we can actually access")
    print()
    
    # Test with absolutely no filters
    test_payload = {
        'actionGroup': 'integration-test-metrics-actions',
        'function': 'get_integration_test_metrics',
        'parameters': []
    }
    
    print(f"🚀 Testing with no filters at all...")
    
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
                
                total_results = body_data.get('total_results', 0)
                results = body_data.get('results', [])
                
                print(f"✅ Total results with no filters: {total_results}")
                
                if results:
                    # Analyze what we got
                    version_counts = {}
                    rc_counts = {}
                    recent_count = 0
                    
                    now = datetime.now()
                    hours_ago_24 = now - timedelta(hours=24)
                    
                    for result in results:
                        version = result.get('version')
                        rc = result.get('rc_number')
                        timestamp = result.get('build_start_time')
                        
                        if version:
                            version_counts[version] = version_counts.get(version, 0) + 1
                        
                        if rc is not None:
                            rc_counts[rc] = rc_counts.get(rc, 0) + 1
                        
                        if timestamp:
                            result_date = datetime.fromtimestamp(timestamp / 1000)
                            if result_date >= hours_ago_24:
                                recent_count += 1
                    
                    print(f"\n📊 Analysis of {len(results)} results:")
                    print(f"   Results in last 24h: {recent_count}")
                    
                    print(f"\n📊 Top 10 versions:")
                    sorted_versions = sorted(version_counts.items(), key=lambda x: x[1], reverse=True)
                    for version, count in sorted_versions[:10]:
                        print(f"   {version}: {count} results")
                    
                    print(f"\n📊 RC distribution:")
                    for rc in sorted(rc_counts.keys()):
                        count = rc_counts[rc]
                        print(f"   RC {rc}: {count} results")
                    
                    # Check for RC 6 specifically
                    rc6_count = rc_counts.get(6, 0)
                    print(f"\n🎯 RC 6 results found: {rc6_count}")
                    
                    if rc6_count > 0:
                        print(f"✅ RC 6 data exists! Our RC filter should work.")
                        
                        # Find RC 6 results and analyze them
                        rc6_results = [r for r in results if r.get('rc_number') == 6]
                        
                        if rc6_results:
                            rc6_versions = {}
                            rc6_recent = 0
                            
                            for result in rc6_results:
                                version = result.get('version')
                                timestamp = result.get('build_start_time')
                                
                                if version:
                                    rc6_versions[version] = rc6_versions.get(version, 0) + 1
                                
                                if timestamp:
                                    result_date = datetime.fromtimestamp(timestamp / 1000)
                                    if result_date >= hours_ago_24:
                                        rc6_recent += 1
                            
                            print(f"📊 RC 6 version distribution:")
                            for version, count in sorted(rc6_versions.items()):
                                print(f"   {version}: {count} results")
                            
                            print(f"⏰ RC 6 results in last 24h: {rc6_recent}")
                            
                            if rc6_recent > 49:
                                print(f"🎯 FOUND THE ISSUE! There are {rc6_recent} RC 6 results in last 24h")
                                print(f"🎯 But our filtered query only returns 49!")
                                print(f"🎯 This suggests our filtering logic has a bug!")
                    else:
                        print(f"❌ No RC 6 data found even with no filters!")
                        print(f"❌ This suggests a fundamental data access issue")
                
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_no_filters()