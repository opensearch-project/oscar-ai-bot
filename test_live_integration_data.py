#!/usr/bin/env python3
"""
Test script to call the actual metrics Lambda and show real integration test data.
This will show you exactly what parameters and results the integration tests are pulling.
"""

import json
import sys
import os
from unittest.mock import patch

# Add metrics directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'metrics'))

def test_real_integration_data():
    """Test with real integration test data by calling the metrics Lambda."""
    print("🔍 Testing Real Integration Test Data")
    print("=" * 60)
    
    # Import the lambda function
    from lambda_function import lambda_handler
    
    # Test scenarios with different parameters
    test_scenarios = [
        {
            "name": "RC-based query for version 2.18.0",
            "event": {
                "actionGroup": "metrics-query",
                "function": "get_integration_test_metrics",
                "parameters": [
                    {"name": "query", "value": "get integration test results for version 2.18.0 RC 1"},
                    {"name": "version", "value": "2.18.0"},
                    {"name": "rc_numbers", "value": [1]}
                ]
            }
        },
        {
            "name": "Failed tests query for version 2.18.0",
            "event": {
                "actionGroup": "metrics-query", 
                "function": "get_integration_test_metrics",
                "parameters": [
                    {"name": "query", "value": "show failed integration tests for version 2.18.0"},
                    {"name": "version", "value": "2.18.0"},
                    {"name": "status_filter", "value": "failed"}
                ]
            }
        },
        {
            "name": "OpenSearch-Dashboards tests for version 2.18.0",
            "event": {
                "actionGroup": "metrics-query",
                "function": "get_integration_test_metrics", 
                "parameters": [
                    {"name": "query", "value": "integration test status for OpenSearch-Dashboards version 2.18.0"},
                    {"name": "version", "value": "2.18.0"},
                    {"name": "components", "value": ["OpenSearch-Dashboards"]}
                ]
            }
        },
        {
            "name": "Build number specific query",
            "event": {
                "actionGroup": "metrics-query",
                "function": "get_integration_test_metrics",
                "parameters": [
                    {"name": "query", "value": "integration test results for version 2.18.0 build numbers 4800, 4801"},
                    {"name": "version", "value": "2.18.0"},
                    {"name": "build_numbers", "value": [4800, 4801]}
                ]
            }
        }
    ]
    
    for i, scenario in enumerate(test_scenarios, 1):
        print(f"📊 Test Scenario {i}: {scenario['name']}")
        print("-" * 50)
        
        try:
            # Set environment variable for integration test agent
            os.environ['AGENT_TYPE'] = 'integration-test'
            
            # Call the lambda handler
            result = lambda_handler(scenario['event'], None)
            
            # Extract the response body
            response_body = result.get('response', {}).get('functionResponse', {}).get('responseBody', {}).get('TEXT', {}).get('body')
            
            if response_body:
                parsed_response = json.loads(response_body)
                
                print("Query Intent:")
                query_intent = parsed_response.get('query_intent', {})
                print(json.dumps(query_intent, indent=2))
                print()
                
                print("Summary:")
                summary = parsed_response.get('summary', {})
                print(json.dumps(summary, indent=2))
                print()
                
                # Show first few actual results
                results = parsed_response.get('results', [])
                if results and len(results) > 0:
                    first_result_set = results[0]
                    test_results = first_result_set.get('test_results', [])
                    
                    print(f"Strategy: {first_result_set.get('strategy', 'unknown')}")
                    print(f"Total Results: {len(test_results)}")
                    
                    if test_results:
                        print("\nFirst 3 Test Results:")
                        for j, test_result in enumerate(test_results[:3]):
                            print(f"  Result {j+1}:")
                            print(f"    Component: {test_result.get('component')}")
                            print(f"    Status: {test_result.get('status')}")
                            print(f"    Build Number: {test_result.get('build_number')}")
                            print(f"    RC Number: {test_result.get('rc_number')}")
                            print(f"    Platform: {test_result.get('platform')}")
                            print(f"    Architecture: {test_result.get('architecture')}")
                            print(f"    Distribution: {test_result.get('distribution')}")
                            print(f"    Timestamp: {test_result.get('timestamp')}")
                            if test_result.get('test_report'):
                                print(f"    Test Report: {test_result.get('test_report')[:80]}...")
                            print()
                    
                    # Show unique components found
                    unique_components = list(set(r.get('component') for r in test_results if r.get('component')))
                    print(f"Unique Components Found: {unique_components}")
                    
                    # Show status distribution
                    status_counts = {}
                    for result in test_results:
                        status = result.get('status', 'unknown')
                        status_counts[status] = status_counts.get(status, 0) + 1
                    print(f"Status Distribution: {status_counts}")
                    
                else:
                    print("No test results found")
                
                # Check for errors
                if 'error' in parsed_response:
                    print(f"❌ Error: {parsed_response['error']}")
                    if 'type' in parsed_response:
                        print(f"Error Type: {parsed_response['type']}")
            else:
                print("❌ No response body found")
                print("Full result:")
                print(json.dumps(result, indent=2))
                
        except Exception as e:
            print(f"❌ Test failed: {e}")
            import traceback
            traceback.print_exc()
        
        print("\n" + "="*60 + "\n")

def analyze_parameter_issues():
    """Analyze potential parameter and data issues."""
    print("🔧 Parameter and Data Issue Analysis")
    print("=" * 50)
    
    issues_to_check = [
        {
            "issue": "Build number string vs integer handling",
            "description": "Build numbers might be stored as strings in OpenSearch but parsed as integers in queries"
        },
        {
            "issue": "RC number consistency", 
            "description": "RC numbers might be stored inconsistently (with/without 'RC' prefix, as strings vs integers)"
        },
        {
            "issue": "Component name variations",
            "description": "OpenSearch-Dashboards components might have different naming patterns (ci-group-1, ci-group-2, etc.)"
        },
        {
            "issue": "Status value standardization",
            "description": "Status might be 'passed'/'failed' vs 'success'/'failure' vs other variations"
        },
        {
            "issue": "Date/timestamp format",
            "description": "Timestamps might be in different formats affecting sorting and filtering"
        },
        {
            "issue": "Distribution/architecture defaults",
            "description": "Default values for distribution (tar) and architecture (x64) might not match actual data"
        },
        {
            "issue": "Version format matching",
            "description": "Version strings might have different formats (2.18.0 vs 2.18.0-SNAPSHOT vs 2.18.0-alpha1)"
        }
    ]
    
    print("Potential Issues to Investigate:")
    for i, issue in enumerate(issues_to_check, 1):
        print(f"{i}. {issue['issue']}")
        print(f"   {issue['description']}")
        print()
    
    print("Recommended Debugging Steps:")
    print("1. Check the actual field names and values in the OpenSearch index")
    print("2. Verify that query parameters match the data format exactly")
    print("3. Test with known good build numbers and RC numbers")
    print("4. Check if the deduplication logic is removing valid results")
    print("5. Verify that the OpenSearch query syntax is correct for the index mapping")

def show_opensearch_index_mapping():
    """Show what we expect the OpenSearch index mapping to look like."""
    print("📋 Expected OpenSearch Index Structure")
    print("=" * 40)
    
    expected_fields = {
        "component": "string - Component name (e.g., 'OpenSearch', 'security', 'OpenSearch-Dashboards-ci-group-1')",
        "component_build_result": "string - Test result status ('passed', 'failed', etc.)",
        "distribution_build_number": "string/number - Build number (e.g., '4891')",
        "rc_number": "string/number - Release candidate number (e.g., '1')",
        "version": "string - Version number (e.g., '2.18.0')",
        "platform": "string - Platform (e.g., 'linux', 'windows')",
        "architecture": "string - Architecture (e.g., 'x64', 'arm64')",
        "distribution": "string - Distribution type (e.g., 'tar', 'rpm', 'deb')",
        "test_report_manifest_yml": "string - URL to test report",
        "integ_test_build_url": "string - URL to build",
        "build_start_time": "date - Timestamp of build start",
        "component_category": "string - Category (e.g., 'OpenSearch', 'OpenSearch-Dashboards')",
        "qualifier": "string - Version qualifier (e.g., 'alpha1', 'beta1')"
    }
    
    print("Expected Fields in opensearch-integration-test-results index:")
    for field, description in expected_fields.items():
        print(f"  {field}: {description}")
    
    print("\nKey Questions:")
    print("1. Are all these fields actually present in the index?")
    print("2. Are the field types (string vs number) consistent with the queries?")
    print("3. Are there any additional fields that might be useful?")
    print("4. Is the index name 'opensearch-integration-test-results' correct?")

if __name__ == "__main__":
    print("Live Integration Test Data Analysis")
    print("=" * 60)
    
    try:
        test_real_integration_data()
        analyze_parameter_issues()
        show_opensearch_index_mapping()
        
        print("=" * 60)
        print("🎯 Summary")
        print("This test shows you exactly what data the integration tests are pulling.")
        print("Look for:")
        print("- Unexpected empty results")
        print("- Mismatched parameter formats")
        print("- Inconsistent field values")
        print("- Query syntax issues")
        print("- Data type mismatches")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()