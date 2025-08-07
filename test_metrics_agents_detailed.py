#!/usr/bin/env python3
"""
Detailed test script for metrics agents with comprehensive logging.
Tests multiple natural language queries per agent type with parameter variations.
"""

import json
import time
import boto3
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple

# Comprehensive test queries organized by metrics agent type
METRICS_TEST_QUERIES = {
    "test_metrics": [
        "What is the test status today?",
        "Show me test failures from the last week",
        "What's the test coverage for OpenSearch core?",
        "Are there any flaky tests in the main branch?",
        "How many tests passed in the latest build?",
        "What test suites are failing most frequently?"
    ],
    "build_metrics": [
        "What is the build status today?", 
        "Show me recent build failures",
        "How long did the last build take?",
        "Which builds failed in the past 24 hours?",
        "What's the build success rate this week?",
        "Are there any build performance issues?"
    ],
    "release_metrics": [
        "What is the release status today?",
        "Show me recent release information", 
        "When was the last OpenSearch release?",
        "What releases are planned for this month?",
        "How many releases were completed last quarter?",
        "What's the current release pipeline status?"
    ],
    "deployment_metrics": [
        "What is the deployment status today?",
        "Show me recent deployment metrics",
        "How many deployments succeeded this week?", 
        "What environments had deployment failures?",
        "What's the average deployment time?",
        "Are there any deployment rollbacks?"
    ]
}

WEBHOOK_URL = "https://x7b5urlaof.execute-api.us-east-1.amazonaws.com/prod/slack/events"

def create_slack_event(query: str, channel: str = "C09827S7CEB", user: str = "U091B0QH1QD") -> Dict[str, Any]:
    """Create a mock Slack app_mention event."""
    timestamp = str(time.time())
    return {
        "token": "verification_token",
        "team_id": "T123456",
        "api_app_id": "A123456", 
        "event": {
            "type": "app_mention",
            "user": user,
            "text": f"<@UBOT123456> {query}",
            "ts": timestamp,
            "channel": channel,
            "event_ts": timestamp
        },
        "type": "event_callback",
        "event_id": f"Ev{int(time.time())}",
        "event_time": int(time.time())
    }

def test_bedrock_agent_invocation(agent_type: str, query: str) -> Dict[str, Any]:
    """Test direct Bedrock agent invocation."""
    print(f"    🤖 Testing Bedrock agent invocation for {agent_type}")
    
    # Map agent types to Bedrock agent IDs (from your .env)
    agent_map = {
        "test_metrics": "YXSZJ659S7",
        "build_metrics": "0NBATJIVCH", 
        "release_metrics": "4FCARBPEYB",
        "deployment_metrics": "BIHPD6OLO0"
    }
    
    agent_id = agent_map.get(agent_type)
    if not agent_id:
        return {"error": f"Unknown agent type: {agent_type}"}
    
    try:
        bedrock_client = boto3.client('bedrock-agent-runtime', region_name='us-east-1')
        
        response = bedrock_client.invoke_agent(
            agentId=agent_id,
            agentAliasId='TSTALIASID',  # Test alias
            sessionId=f'test-session-{int(time.time())}',
            inputText=query
        )
        
        # Process streaming response
        response_text = ""
        if 'completion' in response:
            for event in response['completion']:
                if 'chunk' in event:
                    chunk = event['chunk']
                    if 'bytes' in chunk:
                        chunk_text = chunk['bytes'].decode('utf-8')
                        response_text += chunk_text
        
        return {
            "bedrock_agent_test": {
                "success": True,
                "agent_id": agent_id,
                "response_length": len(response_text),
                "response_preview": response_text[:200] + "..." if len(response_text) > 200 else response_text
            }
        }
        
    except Exception as e:
        return {
            "bedrock_agent_test": {
                "success": False,
                "agent_id": agent_id,
                "error": str(e)
            }
        }

def test_direct_lambda_invocation(agent_type: str, query: str) -> Dict[str, Any]:
    """Test direct Lambda function invocation with proper Bedrock format."""
    print(f"    🔧 Testing direct Lambda invocation for {agent_type}")
    
    # Map agent types to function names
    function_map = {
        "test_metrics": "oscar-test-metrics-agent-new",
        "build_metrics": "oscar-build-metrics-agent-new", 
        "release_metrics": "oscar-release-metrics-agent-new",
        "deployment_metrics": "oscar-deployment-metrics-agent-new"
    }
    
    function_name = function_map.get(agent_type)
    if not function_name:
        return {"error": f"Unknown agent type: {agent_type}"}
    
    try:
        lambda_client = boto3.client('lambda', region_name='us-east-1')
        
        # Test with Bedrock agent format (what the Lambda actually expects)
        payloads_to_test = [
            {
                "actionGroup": "MetricsActionGroup",
                "function": "get_metrics", 
                "parameters": [{"name": "metric_type", "value": "status"}]
            },
            {
                "actionGroup": "MetricsActionGroup",
                "function": "get_test_metrics" if agent_type == "test_metrics" else f"get_{agent_type.replace('_', '_')}",
                "parameters": [{"name": "query", "value": query}]
            },
            {
                "actionGroup": "MetricsActionGroup", 
                "function": "get_metrics",
                "parameters": [
                    {"name": "metric_type", "value": "execution"},
                    {"name": "time_range", "value": "7d"}
                ]
            }
        ]
        
        results = []
        for i, payload in enumerate(payloads_to_test):
            try:
                response = lambda_client.invoke(
                    FunctionName=function_name,
                    Payload=json.dumps(payload),
                    InvocationType='RequestResponse'
                )
                
                response_payload = json.loads(response['Payload'].read())
                results.append({
                    "payload_index": i,
                    "payload": payload,
                    "response": response_payload,
                    "success": "errorMessage" not in response_payload
                })
                
            except Exception as e:
                results.append({
                    "payload_index": i,
                    "payload": payload,
                    "error": str(e),
                    "success": False
                })
        
        return {"direct_lambda_results": results}
        
    except Exception as e:
        return {"error": f"Direct Lambda test failed: {e}"}

def send_test_query(query: str, agent_type: str, test_id: int) -> Dict[str, Any]:
    """Send a test query and measure response with detailed logging."""
    print(f"\n🧪 Test {test_id} ({agent_type}): '{query}'")
    
    start_time = time.time()
    event = create_slack_event(query)
    
    # Test both direct Lambda and Bedrock agent invocation
    direct_test = test_direct_lambda_invocation(agent_type, query)
    bedrock_test = test_bedrock_agent_invocation(agent_type, query)
    
    try:
        # Test via webhook
        response = requests.post(
            WEBHOOK_URL,
            json=event,
            headers={
                "Content-Type": "application/json",
                "X-Slack-Request-Timestamp": str(int(time.time())),
                "X-Slack-Signature": f"v0=test_signature_{test_id}"
            },
            timeout=15
        )
        
        response_time = time.time() - start_time
        
        result = {
            "test_id": test_id,
            "query": query,
            "agent_type": agent_type,
            "webhook_status_code": response.status_code,
            "webhook_response_time": response_time,
            "webhook_response_body": response.text,
            "webhook_success": response.status_code == 200,
            "direct_lambda_test": direct_test,
            "bedrock_agent_test": bedrock_test,
            "timestamp": datetime.now().isoformat()
        }
        
        status_icon = "✅" if response.status_code == 200 else "❌"
        print(f"   {status_icon} Webhook Status: {response.status_code}, Time: {response_time:.2f}s")
        
        # Print direct Lambda results summary
        if "direct_lambda_results" in direct_test:
            successful_direct = len([r for r in direct_test["direct_lambda_results"] if r["success"]])
            total_direct = len(direct_test["direct_lambda_results"])
            print(f"   🔧 Direct Lambda: {successful_direct}/{total_direct} payloads successful")
        
        # Print Bedrock agent results
        if "bedrock_agent_test" in bedrock_test:
            bedrock_success = bedrock_test["bedrock_agent_test"]["success"]
            bedrock_icon = "✅" if bedrock_success else "❌"
            print(f"   🤖 Bedrock Agent: {bedrock_icon} {'Success' if bedrock_success else 'Failed'}")
        
        return result
        
    except Exception as e:
        response_time = time.time() - start_time
        result = {
            "test_id": test_id,
            "query": query,
            "agent_type": agent_type,
            "webhook_error": str(e),
            "webhook_response_time": response_time,
            "webhook_success": False,
            "direct_lambda_test": direct_test,
            "bedrock_agent_test": bedrock_test,
            "timestamp": datetime.now().isoformat()
        }
        
        print(f"   ❌ Webhook Error: {e}")
        return result

def get_detailed_lambda_logs(agent_type: str, minutes: int = 10) -> List[Dict[str, Any]]:
    """Get detailed Lambda logs for specific agent type."""
    print(f"\n📋 Checking Lambda logs for {agent_type} from last {minutes} minutes...")
    
    function_map = {
        "test_metrics": "oscar-test-metrics-agent-new",
        "build_metrics": "oscar-build-metrics-agent-new",
        "release_metrics": "oscar-release-metrics-agent-new", 
        "deployment_metrics": "oscar-deployment-metrics-agent-new"
    }
    
    function_name = function_map.get(agent_type)
    if not function_name:
        return []
    
    try:
        logs_client = boto3.client('logs', region_name='us-east-1')
        log_group_name = f"/aws/lambda/{function_name}"
        
        # Calculate start time
        start_time = int((time.time() - (minutes * 60)) * 1000)
        
        # Get log events
        response = logs_client.filter_log_events(
            logGroupName=log_group_name,
            startTime=start_time
        )
        
        log_entries = []
        for event in response.get('events', []):
            message = event['message']
            log_entries.append({
                'timestamp': event['timestamp'],
                'message': message,
                'is_error': 'ERROR' in message,
                'is_timeout': 'timeout' in message.lower() or 'timed out' in message.lower(),
                'is_throttle': 'throttl' in message.lower(),
                'is_none_response': 'none' in message.lower() and 'response' in message.lower()
            })
            
        return log_entries
        
    except Exception as e:
        print(f"   ❌ Error checking logs for {agent_type}: {e}")
        return []

def analyze_agent_performance(results: List[Dict[str, Any]], agent_type: str) -> Dict[str, Any]:
    """Analyze performance for a specific agent type."""
    agent_results = [r for r in results if r['agent_type'] == agent_type]
    
    if not agent_results:
        return {"error": "No results for agent type"}
    
    webhook_successful = len([r for r in agent_results if r['webhook_success']])
    total_tests = len(agent_results)
    
    # Analyze direct Lambda results
    direct_lambda_stats = {"total_payloads_tested": 0, "successful_payloads": 0}
    for result in agent_results:
        if "direct_lambda_results" in result.get("direct_lambda_test", {}):
            direct_results = result["direct_lambda_test"]["direct_lambda_results"]
            direct_lambda_stats["total_payloads_tested"] += len(direct_results)
            direct_lambda_stats["successful_payloads"] += len([r for r in direct_results if r["success"]])
    
    # Get recent logs
    logs = get_detailed_lambda_logs(agent_type, 15)
    
    analysis = {
        "agent_type": agent_type,
        "webhook_success_rate": f"{webhook_successful}/{total_tests} ({webhook_successful/total_tests*100:.1f}%)",
        "direct_lambda_stats": direct_lambda_stats,
        "log_analysis": {
            "total_log_entries": len(logs),
            "error_entries": len([l for l in logs if l['is_error']]),
            "timeout_entries": len([l for l in logs if l['is_timeout']]),
            "throttle_entries": len([l for l in logs if l['is_throttle']]),
            "none_response_entries": len([l for l in logs if l['is_none_response']])
        },
        "sample_queries_tested": [r['query'] for r in agent_results[:3]]
    }
    
    return analysis

def run_comprehensive_metrics_test():
    """Run comprehensive test of all metrics agents."""
    print("🚀 Starting Comprehensive Metrics Agent Test")
    print("=" * 70)
    
    start_time = datetime.now()
    results = []
    test_id = 1
    
    # Test each agent type
    for agent_type, queries in METRICS_TEST_QUERIES.items():
        print(f"\n📊 Testing {agent_type.replace('_', ' ').title()} Agent")
        print("-" * 50)
        
        for query in queries:
            result = send_test_query(query, agent_type, test_id)
            results.append(result)
            test_id += 1
            time.sleep(2)  # Brief pause between queries
    
    # Wait for async processing
    print(f"\n⏳ Waiting 60 seconds for async processing to complete...")
    time.sleep(60)
    
    # Analyze results by agent type
    print(f"\n📊 DETAILED ANALYSIS BY AGENT TYPE")
    print("=" * 70)
    
    agent_analyses = {}
    for agent_type in METRICS_TEST_QUERIES.keys():
        analysis = analyze_agent_performance(results, agent_type)
        agent_analyses[agent_type] = analysis
        
        print(f"\n🔍 {agent_type.replace('_', ' ').title()} Analysis:")
        print(f"   Webhook Success Rate: {analysis['webhook_success_rate']}")
        print(f"   Direct Lambda Success: {analysis['direct_lambda_stats']['successful_payloads']}/{analysis['direct_lambda_stats']['total_payloads_tested']} payloads")
        print(f"   Log Errors: {analysis['log_analysis']['error_entries']}")
        print(f"   Log Timeouts: {analysis['log_analysis']['timeout_entries']}")
        print(f"   Log Throttles: {analysis['log_analysis']['throttle_entries']}")
        print(f"   None Responses: {analysis['log_analysis']['none_response_entries']}")
    
    # Overall summary
    total_tests = len(results)
    webhook_successful = len([r for r in results if r['webhook_success']])
    
    print(f"\n📈 OVERALL SUMMARY")
    print("=" * 70)
    print(f"Total Tests: {total_tests}")
    print(f"Webhook Success: {webhook_successful}/{total_tests} ({webhook_successful/total_tests*100:.1f}%)")
    
    # Identify problematic agents
    problematic_agents = []
    for agent_type, analysis in agent_analyses.items():
        if analysis['log_analysis']['error_entries'] > 0 or analysis['log_analysis']['none_response_entries'] > 0:
            problematic_agents.append(agent_type)
    
    if problematic_agents:
        print(f"\n⚠️  Problematic Agents: {', '.join(problematic_agents)}")
    else:
        print(f"\n✅ All agents appear to be functioning normally")
    
    # Save detailed results
    detailed_results = {
        'test_results': results,
        'agent_analyses': agent_analyses,
        'summary': {
            'total_tests': total_tests,
            'webhook_successful': webhook_successful,
            'problematic_agents': problematic_agents,
            'start_time': start_time.isoformat(),
            'end_time': datetime.now().isoformat()
        }
    }
    
    with open('detailed_metrics_test_results.json', 'w') as f:
        json.dump(detailed_results, f, indent=2)
    
    print(f"\n💾 Detailed results saved to: detailed_metrics_test_results.json")
    
    # Specific recommendations
    print(f"\n💡 RECOMMENDATIONS:")
    for agent_type in problematic_agents:
        analysis = agent_analyses[agent_type]
        if analysis['log_analysis']['none_response_entries'] > 0:
            print(f"   - {agent_type}: Investigate None response issue - check agent configuration")
        if analysis['log_analysis']['error_entries'] > 0:
            print(f"   - {agent_type}: Check error logs for specific failure patterns")
        if analysis['log_analysis']['throttle_entries'] > 0:
            print(f"   - {agent_type}: Implement throttling protection")

if __name__ == "__main__":
    run_comprehensive_metrics_test()