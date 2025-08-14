#!/usr/bin/env python3

import json
import boto3
import os
from datetime import datetime

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

def debug_rc_parsing():
    """Debug RC parsing to see if RC 6 results are being misclassified as RC 0"""
    
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    
    print(f"🔍 Debugging RC Parsing - Are RC 6 results misclassified as RC 0?")
    print(f"{'='*80}")
    print(f"Theory: Some of the 683 RC 0 results might actually be RC 6 results")
    print(f"that are being parsed incorrectly or have different field formats.")
    print()
    
    # Get all version 3.2.0 results to examine RC 0 entries
    test_payload = {
        'actionGroup': 'integration-test-metrics-actions',
        'function': 'get_integration_test_metrics',
        'parameters': [
            {'name': 'version', 'value': '3.2.0'}
        ]
    }
    
    print(f"🚀 Getting all version 3.2.0 results to examine RC fields...")
    
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
                
                # Analyze RC 0 results in detail
                rc0_results = [r for r in results if r.get('rc_number') == 0]
                rc6_results = [r for r in results if r.get('rc_number') == 6]
                
                print(f"📊 RC 0 results: {len(rc0_results)}")
                print(f"📊 RC 6 results: {len(rc6_results)}")
                print()
                
                # Examine RC 0 results for potential RC 6 data
                print(f"🔍 Examining RC 0 results for potential RC 6 data...")
                
                potential_rc6_in_rc0 = []
                rc_field_analysis = {}
                
                for i, result in enumerate(rc0_results[:50]):  # Check first 50 RC 0 results
                    # Check all RC-related fields
                    rc_number = result.get('rc_number')
                    rc_field = result.get('rc')  # Alternative RC field
                    
                    # Look for RC 6 in other fields
                    component = result.get('component', '')
                    build_url = result.get('distribution_build_url', '')
                    integ_url = result.get('integ_test_build_url', '')
                    
                    # Check if any field contains "6" or "RC6" or similar
                    fields_with_6 = []
                    if '6' in str(component):
                        fields_with_6.append(f"component: {component}")
                    if '6' in str(build_url):
                        fields_with_6.append(f"build_url: {build_url}")
                    if '6' in str(integ_url):
                        fields_with_6.append(f"integ_url: {integ_url}")
                    if rc_field and '6' in str(rc_field):
                        fields_with_6.append(f"rc_field: {rc_field}")
                    
                    # Collect RC field variations
                    rc_key = f"rc_number={rc_number}, rc={rc_field}"
                    if rc_key not in rc_field_analysis:
                        rc_field_analysis[rc_key] = 0
                    rc_field_analysis[rc_key] += 1
                    
                    if fields_with_6:
                        potential_rc6_in_rc0.append({
                            'index': i,
                            'rc_number': rc_number,
                            'rc_field': rc_field,
                            'fields_with_6': fields_with_6,
                            'build_start_time': result.get('build_start_time'),
                            'component': component
                        })
                
                print(f"📋 RC field variations in RC 0 results:")
                for rc_combo, count in sorted(rc_field_analysis.items()):
                    print(f"   {rc_combo}: {count} results")
                
                print(f"\n🎯 Potential RC 6 data in RC 0 results: {len(potential_rc6_in_rc0)}")
                
                if potential_rc6_in_rc0:
                    print(f"📋 Examples of RC 0 results that might be RC 6:")
                    for item in potential_rc6_in_rc0[:10]:  # Show first 10
                        timestamp = item['build_start_time']
                        date_str = datetime.fromtimestamp(timestamp / 1000).strftime('%Y-%m-%d %H:%M:%S') if timestamp else 'N/A'
                        print(f"   {item['index']:2d}. RC fields: rc_number={item['rc_number']}, rc={item['rc_field']}")
                        print(f"       Component: {item['component']}")
                        print(f"       Date: {date_str}")
                        print(f"       Fields with '6': {item['fields_with_6']}")
                        print()
                
                # Check if RC 0 results have recent timestamps (last 24 hours)
                now = datetime.now()
                recent_rc0 = []
                
                for result in rc0_results:
                    timestamp = result.get('build_start_time')
                    if timestamp:
                        result_date = datetime.fromtimestamp(timestamp / 1000)
                        hours_diff = (now - result_date).total_seconds() / 3600
                        
                        if hours_diff <= 24:
                            recent_rc0.append({
                                'component': result.get('component'),
                                'rc_number': result.get('rc_number'),
                                'rc_field': result.get('rc'),
                                'date': result_date,
                                'hours_ago': hours_diff
                            })
                
                print(f"⏰ RC 0 results in last 24 hours: {len(recent_rc0)}")
                
                if recent_rc0:
                    print(f"📋 Recent RC 0 results (might be misclassified RC 6):")
                    for item in recent_rc0[:10]:
                        print(f"   Component: {item['component']}")
                        print(f"   RC fields: rc_number={item['rc_number']}, rc={item['rc_field']}")
                        print(f"   Date: {item['date']} ({item['hours_ago']:.1f}h ago)")
                        print()
                
                # Compare timestamps between RC 0 and RC 6
                if rc6_results and recent_rc0:
                    rc6_timestamps = [r.get('build_start_time') for r in rc6_results if r.get('build_start_time')]
                    rc0_recent_timestamps = [item['date'].timestamp() * 1000 for item in recent_rc0]
                    
                    if rc6_timestamps and rc0_recent_timestamps:
                        rc6_avg = sum(rc6_timestamps) / len(rc6_timestamps)
                        rc0_avg = sum(rc0_recent_timestamps) / len(rc0_recent_timestamps)
                        
                        print(f"📊 Timestamp comparison:")
                        print(f"   RC 6 average timestamp: {datetime.fromtimestamp(rc6_avg / 1000)}")
                        print(f"   Recent RC 0 average timestamp: {datetime.fromtimestamp(rc0_avg / 1000)}")
                        
                        if abs(rc6_avg - rc0_avg) < 3600000:  # Within 1 hour
                            print(f"❗ RC 6 and recent RC 0 timestamps are very close!")
                            print(f"❗ This suggests RC 0 might contain misclassified RC 6 data!")
                
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

def suggest_rc_parsing_fixes():
    """Suggest fixes for RC parsing issues"""
    print(f"\n💡 Potential RC Parsing Issues and Fixes:")
    print(f"{'='*80}")
    print(f"1. Alternative RC field: Check if 'rc' field has different values than 'rc_number'")
    print(f"2. String vs Integer: RC might be stored as string in some records")
    print(f"3. RC format variations: 'RC6', 'rc6', '6.0', etc.")
    print(f"4. Null/missing RC: Records without RC might default to 0")
    print(f"5. Data corruption: RC field might be corrupted or incorrectly indexed")
    print()
    print(f"Fixes to try:")
    print(f"1. Query both 'rc_number' and 'rc' fields")
    print(f"2. Use 'should' clause to match multiple RC formats")
    print(f"3. Check for string representations of RC 6")
    print(f"4. Filter by timestamp range instead of RC for recent data")

if __name__ == "__main__":
    debug_rc_parsing()
    suggest_rc_parsing_fixes()