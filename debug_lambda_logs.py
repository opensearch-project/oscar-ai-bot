#!/usr/bin/env python3
"""
Debug script to query CloudWatch logs for Lambda errors.
"""

import boto3
import json
from datetime import datetime, timedelta

def query_lambda_logs(function_name, hours_back=1):
    """Query CloudWatch logs for Lambda function errors."""
    
    logs_client = boto3.client('logs', region_name='us-east-1')
    
    # Calculate time range
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=hours_back)
    
    log_group_name = f'/aws/lambda/{function_name}'
    
    # Query for errors and exceptions
    query = """
    fields @timestamp, @message
    | filter @message like /ERROR/ or @message like /Exception/ or @message like /Traceback/
    | sort @timestamp desc
    | limit 50
    """
    
    try:
        # Start the query
        response = logs_client.start_query(
            logGroupName=log_group_name,
            startTime=int(start_time.timestamp()),
            endTime=int(end_time.timestamp()),
            queryString=query
        )
        
        query_id = response['queryId']
        print(f"Started query {query_id} for log group {log_group_name}")
        
        # Wait for query to complete
        import time
        while True:
            result = logs_client.get_query_results(queryId=query_id)
            if result['status'] == 'Complete':
                break
            elif result['status'] == 'Failed':
                print(f"Query failed: {result}")
                return
            time.sleep(1)
        
        # Print results
        print(f"\nFound {len(result['results'])} log entries:")
        print("=" * 80)
        
        for entry in result['results']:
            timestamp = entry[0]['value']
            message = entry[1]['value']
            print(f"\n[{timestamp}]")
            print(message)
            print("-" * 40)
            
    except Exception as e:
        print(f"Error querying logs: {e}")

def query_response_creation_logs(function_name, hours_back=1):
    """Query for response creation specific logs."""
    
    logs_client = boto3.client('logs', region_name='us-east-1')
    
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=hours_back)
    
    log_group_name = f'/aws/lambda/{function_name}'
    
    # Query for response creation logs
    query = """
    fields @timestamp, @message
    | filter @message like /CREATE_RESPONSE/ or @message like /Response/ or @message like /JSON/
    | sort @timestamp desc
    | limit 30
    """
    
    try:
        response = logs_client.start_query(
            logGroupName=log_group_name,
            startTime=int(start_time.timestamp()),
            endTime=int(end_time.timestamp()),
            queryString=query
        )
        
        query_id = response['queryId']
        print(f"Started response query {query_id}")
        
        import time
        while True:
            result = logs_client.get_query_results(queryId=query_id)
            if result['status'] == 'Complete':
                break
            elif result['status'] == 'Failed':
                print(f"Query failed: {result}")
                return
            time.sleep(1)
        
        print(f"\nResponse creation logs ({len(result['results'])} entries):")
        print("=" * 80)
        
        for entry in result['results']:
            timestamp = entry[0]['value']
            message = entry[1]['value']
            print(f"[{timestamp}] {message}")
            
    except Exception as e:
        print(f"Error querying response logs: {e}")

if __name__ == "__main__":
    # Replace with your actual Lambda function name
    function_name = "oscar-metrics-lambda"  # Update this
    
    print("Querying for errors...")
    query_lambda_logs(function_name, hours_back=2)
    
    print("\n" + "="*80)
    print("Querying for response creation logs...")
    query_response_creation_logs(function_name, hours_back=2)