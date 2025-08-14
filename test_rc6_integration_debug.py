#!/usr/bin/env python3

import json
import boto3
import os
from datetime import datetime

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

def test_rc6_integration_debug():
    """Test the specific query: integration test results for RC 6 on version 3.2.0"""
    
    lambda_client = boto3.client('lambda', region_name='us-east-1')
    
    # Test the exact query you mentioned
    test_payload = {
        'actionGroup': 'integration-test-metrics-actions',
        'function': 'get_integration_test_metrics',
        'parameters': [
            {'name': 'version', 'value': '3.2.0'},
            {'name': 'rc_numbers', 'value': '6'}
        ]
    }
    
    print(f"🧪 Testing RC 6 Integration Test Query")
    print(f"{'='*60}")
    print(f"Query: 'What are the integration test results for RC 6 on version 3.2.0?'")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()
    
    try:
        print(f"🚀 Invoking oscar-test-metrics-agent-new...")
        print(f"📋 Payload: {json.dumps(test_payload, indent=2)}")
        print()
        
        # Invoke the Lambda function
        response = lambda_client.invoke(
            FunctionName='oscar-test-metrics-agent-new',
            InvocationType='RequestResponse',
            Payload=json.dumps(test_payload)
        )
        
        # Parse response
        response_payload = json.loads(response['Payload'].read())
        
        # Check for errors
        if response.get('FunctionError'):
            print(f"❌ Function Error: {response_payload}")
            return
        
        # Extract the actual response from Bedrock format
        if 'response' in response_payload and 'functionResponse' in response_payload['response']:
            function_response = response_payload['response']['functionResponse']
            if 'responseBody' in function_response and 'TEXT' in function_response['responseBody']:
                try:
                    body_data = json.loads(function_response['responseBody']['TEXT']['body'])
                    
                    # Save raw data to file for manual inspection
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    raw_data_filename = f"raw_integration_test_data_rc6_v3.2.0_{timestamp}.json"
                    
                    raw_data_export = {
                        'query_metadata': {
                            'timestamp': datetime.now().isoformat(),
                            'query': 'Integration test results for RC 6 on version 3.2.0',
                            'lambda_function': 'oscar-test-metrics-agent-new',
                            'payload_sent': test_payload
                        },
                        'response_metadata': {
                            'agent_type': body_data.get('agent_type'),
                            'data_source': body_data.get('data_source'),
                            'version': body_data.get('version'),
                            'total_results': body_data.get('total_results'),
                            'query_parameters': body_data.get('query_parameters', {})
                        },
                        'raw_results': body_data.get('results', []),
                        'full_lambda_response': response_payload
                    }
                    
                    # Save to file
                    with open(raw_data_filename, 'w') as f:
                        json.dump(raw_data_export, f, indent=2, default=str)
                    
                    print(f"✅ Query executed successfully!")
                    print(f"💾 Raw data saved to: {raw_data_filename}")
                    print(f"📊 Results Summary:")
                    print(f"   Agent Type: {body_data.get('agent_type')}")
                    print(f"   Data Source: {body_data.get('data_source')}")
                    print(f"   Version: {body_data.get('version')}")
                    print(f"   Total Results: {body_data.get('total_results')}")
                    print()
                    
                    # Analyze query parameters
                    query_params = body_data.get('query_parameters', {})
                    print(f"📋 Query Parameters Used:")
                    for key, value in query_params.items():
                        print(f"   {key}: {value}")
                    print()
                    
                    # Analyze results
                    results = body_data.get('results', [])
                    if results:
                        print(f"📊 Results Analysis:")
                        
                        # Count by status
                        status_counts = {}
                        rc_counts = {}
                        component_counts = {}
                        failed_components = []
                        
                        for result in results:
                            # Status analysis
                            status = result.get('component_build_result', 'unknown')
                            status_counts[status] = status_counts.get(status, 0) + 1
                            
                            # RC analysis
                            rc = result.get('rc_number', 'unknown')
                            rc_counts[rc] = rc_counts.get(rc, 0) + 1
                            
                            # Component analysis
                            component = result.get('component', 'unknown')
                            component_counts[component] = component_counts.get(component, 0) + 1
                            
                            # Track failed components
                            if status == 'failed':
                                failed_info = {
                                    'component': component,
                                    'rc_number': rc,
                                    'distribution_build_number': result.get('distribution_build_number'),
                                    'integ_test_build_number': result.get('integ_test_build_number'),
                                    'with_security': result.get('with_security'),
                                    'without_security': result.get('without_security'),
                                    'platform': result.get('platform'),
                                    'architecture': result.get('architecture'),
                                    'distribution': result.get('distribution')
                                }
                                failed_components.append(failed_info)
                        
                        print(f"   Status Breakdown: {status_counts}")
                        print(f"   RC Number Breakdown: {rc_counts}")
                        print(f"   Total Unique Components: {len(component_counts)}")
                        print()
                        
                        # Show top components
                        top_components = sorted(component_counts.items(), key=lambda x: x[1], reverse=True)[:10]
                        print(f"📋 Top 10 Components by Test Count:")
                        for component, count in top_components:
                            print(f"   {component}: {count} tests")
                        print()
                        
                        # Show failed components details
                        if failed_components:
                            print(f"❌ Failed Components ({len(failed_components)} failures):")
                            for i, failure in enumerate(failed_components[:10], 1):  # Show first 10 failures
                                print(f"   {i}. {failure['component']}")
                                print(f"      RC: {failure['rc_number']}, Build: {failure['distribution_build_number']}")
                                print(f"      Platform: {failure['platform']}/{failure['architecture']}/{failure['distribution']}")
                                print(f"      Security Tests - With: {failure['with_security']}, Without: {failure['without_security']}")
                                print()
                            
                            if len(failed_components) > 10:
                                print(f"   ... and {len(failed_components) - 10} more failures")
                        else:
                            print(f"✅ No failed components found!")
                        
                        # Create detailed analysis file
                        analysis_filename = f"integration_test_analysis_rc6_v3.2.0_{timestamp}.txt"
                        with open(analysis_filename, 'w') as f:
                            f.write(f"Integration Test Results Analysis - RC 6, Version 3.2.0\n")
                            f.write(f"Generated: {datetime.now().isoformat()}\n")
                            f.write(f"="*80 + "\n\n")
                            
                            f.write(f"SUMMARY:\n")
                            f.write(f"Total Results: {len(results)}\n")
                            f.write(f"Status Breakdown: {status_counts}\n")
                            f.write(f"RC Breakdown: {rc_counts}\n")
                            f.write(f"Unique Components: {len(component_counts)}\n\n")
                            
                            f.write(f"ALL RESULTS (sorted by component name):\n")
                            f.write(f"-"*80 + "\n")
                            
                            # Sort results by component name for easier review
                            sorted_results = sorted(results, key=lambda x: x.get('component', ''))
                            
                            for i, result in enumerate(sorted_results, 1):
                                f.write(f"\n{i:3d}. Component: {result.get('component', 'N/A')}\n")
                                f.write(f"     Version: {result.get('version', 'N/A')}\n")
                                f.write(f"     RC Number: {result.get('rc_number', 'N/A')}\n")
                                f.write(f"     Build Result: {result.get('component_build_result', 'N/A')}\n")
                                f.write(f"     Distribution Build: {result.get('distribution_build_number', 'N/A')}\n")
                                f.write(f"     Integration Test Build: {result.get('integ_test_build_number', 'N/A')}\n")
                                f.write(f"     Platform: {result.get('platform', 'N/A')}/{result.get('architecture', 'N/A')}/{result.get('distribution', 'N/A')}\n")
                                f.write(f"     Security Tests - With: {result.get('with_security', 'N/A')}, Without: {result.get('without_security', 'N/A')}\n")
                                f.write(f"     Build Start Time: {result.get('build_start_time', 'N/A')}\n")
                                f.write(f"     Repository: {result.get('component_repo', 'N/A')}\n")
                                if result.get('component_build_result') == 'failed':
                                    f.write(f"     *** FAILED TEST ***\n")
                                f.write(f"     {'-'*60}\n")
                            
                            if failed_components:
                                f.write(f"\n\nFAILED COMPONENTS DETAILED ANALYSIS:\n")
                                f.write(f"="*80 + "\n")
                                for i, failure in enumerate(failed_components, 1):
                                    f.write(f"\nFailure {i}: {failure['component']}\n")
                                    f.write(f"  RC: {failure['rc_number']}\n")
                                    f.write(f"  Distribution Build: {failure['distribution_build_number']}\n")
                                    f.write(f"  Integration Test Build: {failure['integ_test_build_number']}\n")
                                    f.write(f"  Platform: {failure['platform']}/{failure['architecture']}/{failure['distribution']}\n")
                                    f.write(f"  Security Test Results:\n")
                                    f.write(f"    With Security: {failure['with_security']}\n")
                                    f.write(f"    Without Security: {failure['without_security']}\n")
                                    f.write(f"  Analysis: ")
                                    if failure['with_security'] == 'fail' and failure['without_security'] == 'pass':
                                        f.write("Security-specific failure - component works without security but fails with security enabled\n")
                                    elif failure['with_security'] == 'pass' and failure['without_security'] == 'fail':
                                        f.write("Non-security failure - component fails without security but works with security\n")
                                    elif failure['with_security'] == 'fail' and failure['without_security'] == 'fail':
                                        f.write("Complete failure - component fails both with and without security\n")
                                    else:
                                        f.write("Unclear failure pattern - needs investigation\n")
                                    f.write(f"\n")
                        
                        print(f"📄 Detailed analysis saved to: {analysis_filename}")
                        
                        # Show sample of first few results for debugging
                        print(f"🔍 Sample Results (first 3):")
                        for i, result in enumerate(results[:3], 1):
                            print(f"   Result {i}:")
                            print(f"      Component: {result.get('component')}")
                            print(f"      Version: {result.get('version')}")
                            print(f"      RC Number: {result.get('rc_number')}")
                            print(f"      Build Result: {result.get('component_build_result')}")
                            print(f"      Build Start Time: {result.get('build_start_time')}")
                            print(f"      Distribution Build: {result.get('distribution_build_number')}")
                            print(f"      Integration Test Build: {result.get('integ_test_build_number')}")
                            print()
                    else:
                        print(f"❌ No results found!")
                        print(f"   This could indicate:")
                        print(f"   - No data exists for RC 6 on version 3.2.0")
                        print(f"   - Query filters are too restrictive")
                        print(f"   - Data format issues")
                    
                except json.JSONDecodeError as e:
                    print(f"❌ JSON Parse Error: {e}")
                    print(f"Raw response body: {function_response['responseBody']['TEXT']['body'][:500]}...")
            else:
                print(f"❌ Unexpected response format")
                print(f"Response structure: {list(response_payload.keys())}")
        else:
            print(f"❌ Invalid response structure")
            print(f"Response: {json.dumps(response_payload, indent=2)[:500]}...")
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()

def check_cloudwatch_logs():
    """Check CloudWatch logs for the detailed logging we added"""
    print(f"\n🔍 CloudWatch Logs Check:")
    print(f"To see the detailed logging, check CloudWatch logs for:")
    print(f"   Log Group: /aws/lambda/oscar-test-metrics-agent-new")
    print(f"   Look for log entries with prefixes:")
    print(f"   - 🎯 METRICS_QUERY:")
    print(f"   - 🔍 INTEGRATION_TEST_QUERY:")
    print(f"   - 🔧 INTEGRATION_TEST_QUERY:")
    print(f"   - 📊 INTEGRATION_TEST_QUERY:")
    print(f"   - ✅ INTEGRATION_TEST_QUERY:")
    print(f"   - 📋 INTEGRATION_TEST_QUERY:")

def print_file_summary():
    """Print summary of files created"""
    print(f"\n📁 Files Created for Manual Verification:")
    print(f"   1. raw_integration_test_data_rc6_v3.2.0_[timestamp].json")
    print(f"      - Complete raw JSON data from Lambda response")
    print(f"      - All query metadata and parameters")
    print(f"      - Full OpenSearch results before any processing")
    print(f"   ")
    print(f"   2. integration_test_analysis_rc6_v3.2.0_[timestamp].txt")
    print(f"      - Human-readable analysis of all results")
    print(f"      - Sorted by component name for easy review")
    print(f"      - Detailed breakdown of failed components")
    print(f"      - Summary statistics and patterns")
    print(f"   ")
    print(f"💡 Use these files to manually verify:")
    print(f"   - Are the RC numbers correct in all results?")
    print(f"   - Are the versions correct?")
    print(f"   - Do the build timestamps make sense?")
    print(f"   - Are there any unexpected patterns in the data?")

if __name__ == "__main__":
    test_rc6_integration_debug()
    check_cloudwatch_logs()
    print_file_summary()