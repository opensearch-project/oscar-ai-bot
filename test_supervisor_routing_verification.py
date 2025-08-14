#!/usr/bin/env python3

import json
import boto3
import os
import time
from datetime import datetime, timedelta

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

def test_supervisor_routing_with_cloudwatch():
    """Test supervisor agent routing by monitoring CloudWatch logs to see which Lambda functions are invoked."""
    
    bedrock_client = boto3.client('bedrock-agent-runtime', region_name='us-east-1')
    logs_client = boto3.client('logs', region_name='us-east-1')
    
    # Get supervisor agent configuration from environment
    supervisor_agent_id = os.getenv('OSCAR_BEDROCK_AGENT_ID')
    supervisor_agent_alias_id = os.getenv('OSCAR_BEDROCK_AGENT_ALIAS_ID')
    
    if not supervisor_agent_id or not supervisor_agent_alias_id:
        print("❌ ERROR: OSCAR_BEDROCK_AGENT_ID and OSCAR_BEDROCK_AGENT_ALIAS_ID must be set")
        return
    
    # Lambda function names to monitor
    lambda_functions = [
        'oscar-test-metrics-agent-new',
        'oscar-build-metrics-agent-new', 
        'oscar-release-metrics-agent-new',
        'oscar-deployment-metrics-agent-new'
    ]
    
    test_queries = [
        {
            'name': 'Integration Test Query',
            'query': 'Show me integration test results for version 3.2.0',
            'expected_lambda': 'oscar-test-metrics-agent-new'
        },
        {
            'name': 'Build Metrics Query', 
            'query': 'Show me build results for version 3.2.0',
            'expected_lambda': 'oscar-build-metrics-agent-new'
        },
        {
            'name': 'Release Readiness Query',
            'query': 'Show me release readiness for version 3.2.0', 
            'expected_lambda': 'oscar-release-metrics-agent-new'
        }
    ]
    
    print(f"🔍 Testing Supervisor Agent Routing via CloudWatch Logs")
    print(f"{'='*70}")
    print(f"Supervisor Agent ID: {supervisor_agent_id}")
    print(f"Supervisor Agent Alias: {supervisor_agent_alias_id}")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()
    
    results = []
    
    for i, test_query in enumerate(test_queries, 1):
        print(f"Test {i}: {test_query['name']}")
        print(f"Query: {test_query['query']}")
        print(f"Expected Lambda: {test_query['expected_lambda']}")
        
        # Record start time for log filtering
        start_time = datetime.now()
        
        try:
            # Invoke the supervisor agent
            session_id = f"routing-test-{i}-{int(start_time.timestamp())}"
            print(f"🤖 Invoking supervisor agent with session: {session_id}")
            
            response = bedrock_client.invoke_agent(
                agentId=supervisor_agent_id,
                agentAliasId=supervisor_agent_alias_id,
                inputText=test_query['query'],
                sessionId=session_id
            )
            
            # Process the streaming response
            response_text = ""
            if 'completion' in response:
                for event in response['completion']:
                    if 'chunk' in event:
                        chunk = event['chunk']
                        if 'bytes' in chunk:
                            chunk_text = chunk['bytes'].decode('utf-8')
                            response_text += chunk_text
            
            print(f"✅ Agent responded with {len(response_text)} characters")
            
            # Wait a moment for logs to propagate
            print("⏳ Waiting for CloudWatch logs to propagate...")
            time.sleep(5)
            
            # Check CloudWatch logs for Lambda invocations
            end_time = datetime.now()
            invoked_lambdas = []
            
            for lambda_name in lambda_functions:
                log_group = f"/aws/lambda/{lambda_name}"
                
                try:
                    # Query logs for this time period
                    response = logs_client.filter_log_events(
                        logGroupName=log_group,
                        startTime=int((start_time - timedelta(minutes=1)).timestamp() * 1000),
                        endTime=int((end_time + timedelta(minutes=1)).timestamp() * 1000),
                        filterPattern="START RequestId"  # Look for function starts
                    )
                    
                    if response['events']:
                        # Check if any events occurred during our test window
                        for event in response['events']:
                            event_time = datetime.fromtimestamp(event['timestamp'] / 1000)
                            if start_time <= event_time <= end_time:
                                invoked_lambdas.append(lambda_name)
                                print(f"📋 Found invocation: {lambda_name} at {event_time}")
                                break
                
                except Exception as e:
                    if "ResourceNotFoundException" not in str(e):
                        print(f"⚠️ Warning: Could not check logs for {lambda_name}: {e}")
            
            # Verify routing
            if test_query['expected_lambda'] in invoked_lambdas:
                print(f"✅ PASSED - Correct Lambda invoked: {test_query['expected_lambda']}")
                results.append({
                    'test': test_query['name'],
                    'status': 'PASSED',
                    'expected_lambda': test_query['expected_lambda'],
                    'invoked_lambdas': invoked_lambdas
                })
            else:
                print(f"❌ FAILED - Expected: {test_query['expected_lambda']}, Invoked: {invoked_lambdas}")
                results.append({
                    'test': test_query['name'],
                    'status': 'FAILED',
                    'expected_lambda': test_query['expected_lambda'],
                    'invoked_lambdas': invoked_lambdas,
                    'response_preview': response_text[:200]
                })
            
        except Exception as e:
            print(f"❌ ERROR: {str(e)}")
            results.append({
                'test': test_query['name'],
                'status': 'ERROR',
                'error': str(e)
            })
        
        print("-" * 50)
        print()
    
    # Summary
    passed = len([r for r in results if r['status'] == 'PASSED'])
    failed = len([r for r in results if r['status'] == 'FAILED'])
    errors = len([r for r in results if r['status'] == 'ERROR'])
    
    print(f"📊 Supervisor Agent Routing Verification Summary:")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"🚨 Errors: {errors}")
    print(f"📈 Success Rate: {passed}/{len(results)} ({passed/len(results)*100:.1f}%)")
    
    return results

if __name__ == "__main__":
    test_supervisor_routing_with_cloudwatch()