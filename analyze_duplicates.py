#!/usr/bin/env python3

import json
import boto3
import os
from collections import defaultdict

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

def analyze_duplicates():
    """Analyze the RC 6 results to see what duplicates exist"""
    
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    
    print(f"🔍 Analyzing RC 6 Results for Duplicates")
    print(f"{'='*60}")
    
    # Test the basic RC 6 query
    test_payload = {
        'actionGroup': 'integration-test-metrics-actions',
        'function': 'get_integration_test_metrics',
        'parameters': [
            {'name': 'version', 'value': '3.2.0'},
            {'name': 'rc_numbers', 'value': '6'}
        ]
    }
    
    try:
        response = lambda_client.invoke(
            FunctionName='oscar-test-metrics-agent-new',
            Payload=json.dumps(test_payload),
            InvocationType='RequestResponse'
        )
        
        response_payload = json.loads(response['Payload'].read())
        actual_response = response_payload['response']['functionResponse']['responseBody']['TEXT']['body']
        if isinstance(actual_response, str):
            actual_response = json.loads(actual_response)
        
        results = actual_response['results']
        print(f"📊 Total Results: {len(results)}")
        
        # Group by component to see duplicates
        component_groups = defaultdict(list)
        detailed_groups = defaultdict(list)
        
        for result in results:
            component = result.get('component', 'Unknown')
            platform = result.get('platform', 'Unknown')
            architecture = result.get('architecture', 'Unknown') 
            distribution = result.get('distribution', 'Unknown')
            
            component_groups[component].append(result)
            
            # More detailed grouping
            detailed_key = f"{component}|{platform}|{architecture}|{distribution}"
            detailed_groups[detailed_key].append(result)
        
        print(f"📊 Unique Components: {len(component_groups)}")
        print(f"📊 Unique Detailed Combinations: {len(detailed_groups)}")
        
        # Find components with multiple entries
        duplicates = {comp: entries for comp, entries in component_groups.items() if len(entries) > 1}
        detailed_duplicates = {key: entries for key, entries in detailed_groups.items() if len(entries) > 1}
        
        print(f"📊 Components with Multiple Entries: {len(duplicates)}")
        print(f"📊 Detailed Combinations with Multiple Entries: {len(detailed_duplicates)}")
        
        if detailed_duplicates:
            print(f"\n🔍 Sample Detailed Duplicates:")
            for key, entries in list(detailed_duplicates.items())[:5]:  # Show first 5
                print(f"\n  Key: {key}")
                print(f"  Entries: {len(entries)}")
                for i, entry in enumerate(entries[:3]):  # Show first 3 entries
                    build_time = entry.get('build_start_time', 'No timestamp')
                    build_num = entry.get('distribution_build_number', 'No build num')
                    status = entry.get('component_build_result', 'No status')
                    print(f"    Entry {i+1}: build_num={build_num}, time={build_time}, status={status}")
                if len(entries) > 3:
                    print(f"    ... and {len(entries) - 3} more")
        else:
            print(f"✅ No detailed duplicates found - all combinations are unique")
            
        # Check if all components are unique
        all_components = [result.get('component') for result in results]
        unique_components = set(all_components)
        print(f"\n📊 Component Analysis:")
        print(f"  Total entries: {len(all_components)}")
        print(f"  Unique components: {len(unique_components)}")
        print(f"  Expected reduction: {len(all_components) - len(unique_components)}")
        
    except Exception as e:
        print(f"❌ Analysis failed: {e}")

if __name__ == "__main__":
    analyze_duplicates()