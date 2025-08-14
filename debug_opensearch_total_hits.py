#!/usr/bin/env python3

import json
import boto3
import os
from datetime import datetime

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

def debug_opensearch_total_hits():
    """Debug what OpenSearch actually returns for total hits vs returned results"""
    
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    
    print(f"🔍 Debugging OpenSearch Total Hits vs Returned Results")
    print(f"{'='*80}")
    print(f"Goal: Check if OpenSearch finds 360 RC 6 results but only returns 49,")
    print(f"or if OpenSearch only finds 49 RC 6 results total.")
    print()
    
    # We need to check the CloudWatch logs to see the actual OpenSearch response
    # But first, let's trigger a query and then check the logs
    
    test_payload = {
        'actionGroup': 'integration-test-metrics-actions',
        'function': 'get_integration_test_metrics',
        'parameters': [
            {'name': 'version', 'value': '3.2.0'},
            {'name': 'rc_numbers', 'value': '6'}
        ]
    }
    
    print(f"🚀 Triggering RC 6 query to generate fresh logs...")
    
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
        
        print(f"✅ Query executed successfully")
        
        # Now check CloudWatch logs for the detailed query information
        print(f"\n🔍 Checking CloudWatch logs for OpenSearch response details...")
        
        logs_client = boto3.client('logs', region_name='us-east-1')
        log_group = '/aws/lambda/oscar-test-metrics-agent-new'
        
        # Get logs from the last 2 minutes
        end_time = datetime.now()
        start_time = end_time - timedelta(minutes=2)
        
        try:
            # Get log events with our detailed logging
            response = logs_client.filter_log_events(
                logGroupName=log_group,
                startTime=int(start_time.timestamp() * 1000),
                endTime=int(end_time.timestamp() * 1000),
                filterPattern="INTEGRATION_TEST_QUERY"
            )
            
            events = response.get('events', [])
            print(f"Found {len(events)} log events")
            
            # Look for the specific log that shows total matches vs returned
            total_matches = None
            returned_results = None
            query_body = None
            
            for event in events:
                message = event['message']
                timestamp = datetime.fromtimestamp(event['timestamp'] / 1000)
                
                if "Query completed - Total matches:" in message:
                    # Extract total matches and returned results
                    parts = message.split("Total matches: ")[1]
                    total_part = parts.split(", Returned: ")[0]
                    returned_part = parts.split(", Returned: ")[1]
                    
                    total_matches = total_part
                    returned_results = returned_part
                    
                    print(f"\n🎯 FOUND KEY INFO:")
                    print(f"   Total matches in OpenSearch: {total_matches}")
                    print(f"   Results returned to us: {returned_results}")
                
                elif "Complete query body:" in message:
                    # Extract the query body
                    query_start = message.find('{"size"')
                    if query_start != -1:
                        query_body = message[query_start:]
                        print(f"\n📋 QUERY SENT TO OPENSEARCH:")
                        try:
                            # Try to parse and pretty print the query
                            query_json = json.loads(query_body)
                            print(json.dumps(query_json, indent=2))
                        except:
                            print(query_body[:500] + "..." if len(query_body) > 500 else query_body)
            
            if total_matches and returned_results:
                print(f"\n🔍 ANALYSIS:")
                if total_matches == returned_results:
                    print(f"✅ OpenSearch found exactly {total_matches} RC 6 results")
                    print(f"✅ We received all available results")
                    print(f"❗ This means there are only {total_matches} RC 6 results in the index")
                    print(f"❗ The dashboard might be:")
                    print(f"   - Querying a different index")
                    print(f"   - Using different filters")
                    print(f"   - Showing historical data")
                    print(f"   - Including different RC formats")
                else:
                    print(f"❌ OpenSearch found {total_matches} results but only returned {returned_results}")
                    print(f"❌ This suggests our size limit is too small")
            else:
                print(f"❌ Could not find the key log entries")
                print(f"❌ The detailed logging might not be working")
                
                # Show all log messages for debugging
                print(f"\n📋 All log messages:")
                for event in events:
                    timestamp = datetime.fromtimestamp(event['timestamp'] / 1000)
                    message = event['message']
                    print(f"[{timestamp.strftime('%H:%M:%S')}] {message}")
                
        except Exception as e:
            print(f"❌ Error checking CloudWatch logs: {e}")
            
    except Exception as e:
        print(f"❌ Error executing query: {e}")

def suggest_next_steps():
    """Suggest next steps based on findings"""
    print(f"\n💡 Next Steps:")
    print(f"{'='*80}")
    print(f"If OpenSearch only finds 49 RC 6 results:")
    print(f"1. Check if RC number field has different values (6 vs '6' vs 'RC6')")
    print(f"2. Check if version field has different formats")
    print(f"3. Verify we're querying the same index as the dashboard")
    print(f"4. Check if there are additional implicit filters")
    print()
    print(f"If OpenSearch finds 360 but only returns 49:")
    print(f"1. Increase the size limit in our query")
    print(f"2. Check if there are query timeout issues")
    print(f"3. Use scroll API for large result sets")

if __name__ == "__main__":
    from datetime import timedelta
    debug_opensearch_total_hits()
    suggest_next_steps()