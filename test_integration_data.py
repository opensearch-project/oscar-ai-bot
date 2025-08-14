#!/usr/bin/env python3
"""
Test script to show what integration test data is being pulled and the raw results.
This will help identify if parameters or data extraction might be wrong.
"""

import json
import sys
import os
from unittest.mock import Mock, patch

# Add metrics directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'metrics'))

def test_integration_test_data_extraction():
    """Test what data the integration tests are actually pulling."""
    print("🔍 Testing Integration Test Data Extraction")
    print("=" * 60)
    
    # Mock the OpenSearch response with realistic data
    mock_opensearch_response = {
        "hits": {
            "total": {"value": 15},
            "hits": [
                {
                    "_source": {
                        "component": "OpenSearch",
                        "component_build_result": "passed",
                        "distribution_build_number": "4891",
                        "rc_number": "1",
                        "version": "3.2.0",
                        "platform": "linux",
                        "architecture": "x64",
                        "distribution": "tar",
                        "test_report_manifest_yml": "https://ci.opensearch.org/ci/dbc/integ-test/3.2.0/4891/linux/x64/tar/test-results/4891/integ-test/test-report.yml",
                        "integ_test_build_url": "https://ci.opensearch.org/ci/dbc/integ-test/3.2.0/4891/linux/x64/tar/builds/4891/",
                        "build_start_time": "2024-12-15T10:30:00Z",
                        "component_category": "OpenSearch",
                        "qualifier": "alpha1"
                    }
                },
                {
                    "_source": {
                        "component": "OpenSearch-Dashboards-ci-group-1",
                        "component_build_result": "failed",
                        "distribution_build_number": "4892",
                        "rc_number": "1", 
                        "version": "3.2.0",
                        "platform": "linux",
                        "architecture": "x64",
                        "distribution": "tar",
                        "test_report_manifest_yml": "https://ci.opensearch.org/ci/dbc/integ-test/3.2.0/4892/linux/x64/tar/test-results/4892/integ-test/test-report.yml",
                        "integ_test_build_url": "https://ci.opensearch.org/ci/dbc/integ-test/3.2.0/4892/linux/x64/tar/builds/4892/",
                        "build_start_time": "2024-12-15T11:15:00Z",
                        "component_category": "OpenSearch-Dashboards",
                        "qualifier": "alpha1"
                    }
                },
                {
                    "_source": {
                        "component": "security",
                        "component_build_result": "passed",
                        "distribution_build_number": "4890",
                        "rc_number": "1",
                        "version": "3.2.0",
                        "platform": "linux",
                        "architecture": "x64", 
                        "distribution": "tar",
                        "test_report_manifest_yml": "https://ci.opensearch.org/ci/dbc/integ-test/3.2.0/4890/linux/x64/tar/test-results/4890/integ-test/test-report.yml",
                        "integ_test_build_url": "https://ci.opensearch.org/ci/dbc/integ-test/3.2.0/4890/linux/x64/tar/builds/4890/",
                        "build_start_time": "2024-12-15T09:45:00Z",
                        "component_category": "OpenSearch",
                        "qualifier": "alpha1"
                    }
                }
            ]
        }
    }
    
    # Import the lambda function
    from lambda_function import (
        handle_integration_test_queries, 
        extract_test_results,
        generate_integration_summary,
        parse_query_intent
    )
    
    # Test 1: Query Intent Parsing
    print("📝 Test 1: Query Intent Parsing")
    print("-" * 30)
    
    test_queries = [
        "get integration test results for version 3.2.0 RC 1",
        "show failed integration tests for version 3.2.0 build numbers 4891, 4892",
        "integration test status for OpenSearch-Dashboards version 3.2.0",
        "what are the integration test failures for version 3.2.0"
    ]
    
    for query in test_queries:
        intent = parse_query_intent(query)
        print(f"Query: {query}")
        print(f"Parsed Intent: {json.dumps(intent, indent=2)}")
        print()
    
    # Test 2: Raw Data Extraction
    print("📊 Test 2: Raw Data Extraction")
    print("-" * 30)
    
    extracted_results = extract_test_results(mock_opensearch_response)
    print("Extracted Test Results:")
    print(json.dumps(extracted_results, indent=2, default=str))
    print()
    
    # Test 3: Summary Generation
    print("📈 Test 3: Summary Generation")
    print("-" * 30)
    
    # Simulate results structure as returned by execute_integration_test_strategy
    mock_results = [{
        'strategy': 'rc_based',
        'rc_number': 1,
        'test_results': extracted_results
    }]
    
    summary = generate_integration_summary(mock_results)
    print("Generated Summary:")
    print(json.dumps(summary, indent=2))
    print()
    
    # Test 4: Full Integration Test Query Flow
    print("🔄 Test 4: Full Integration Test Query Flow")
    print("-" * 30)
    
    # Mock the opensearch_request function
    with patch('lambda_function.opensearch_request') as mock_request:
        mock_request.return_value = mock_opensearch_response
        
        # Test intent for RC-based query
        intent = {
            'version': '3.2.0',
            'rc_numbers': [1],
            'build_numbers': [],
            'components': [],
            'status_filter': None,
            'distribution': 'tar',
            'architecture': 'x64',
            'query_type': 'integration_test'
        }
        
        result = handle_integration_test_queries(intent, {})
        print("Full Query Result:")
        print(json.dumps(result, indent=2, default=str))
        print()
    
    # Test 5: Identify Potential Issues
    print("⚠️  Test 5: Potential Issues Analysis")
    print("-" * 30)
    
    issues = []
    
    # Check for data consistency issues
    for result in extracted_results:
        # Issue 1: Build number vs RC number consistency
        if result.get('build_number') and result.get('rc_number'):
            try:
                build_num = int(result['build_number'])
                rc_num = int(result['rc_number'])
                # Typically, higher RC numbers should have higher build numbers
                # This is just a heuristic check
                if rc_num > 1 and build_num < 4000:  # Arbitrary threshold
                    issues.append(f"Potential issue: RC {rc_num} has low build number {build_num}")
            except (ValueError, TypeError):
                issues.append(f"Non-numeric build/RC numbers: build={result['build_number']}, rc={result['rc_number']}")
        
        # Issue 2: Missing critical fields
        required_fields = ['component', 'status', 'version', 'build_number']
        missing_fields = [field for field in required_fields if not result.get(field)]
        if missing_fields:
            issues.append(f"Missing fields in {result.get('component', 'unknown')}: {missing_fields}")
        
        # Issue 3: Status value validation
        valid_statuses = ['passed', 'failed', 'success', 'failure']
        if result.get('status') and result['status'] not in valid_statuses:
            issues.append(f"Unexpected status value: {result['status']}")
    
    # Issue 4: Component name inconsistencies
    components = [r.get('component') for r in extracted_results if r.get('component')]
    dashboards_components = [c for c in components if 'dashboards' in c.lower()]
    if dashboards_components:
        print(f"Dashboards components found: {dashboards_components}")
        # Check if OpenSearch-Dashboards naming is consistent
        inconsistent_naming = [c for c in dashboards_components if not c.startswith('OpenSearch-Dashboards')]
        if inconsistent_naming:
            issues.append(f"Inconsistent Dashboards naming: {inconsistent_naming}")
    
    if issues:
        print("Potential Issues Found:")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
    else:
        print("✅ No obvious issues detected in the data structure")
    
    print()
    
    # Test 6: Parameter Validation
    print("🔧 Test 6: Parameter Validation")
    print("-" * 30)
    
    # Test edge cases that might cause issues
    edge_cases = [
        {'version': '3.2.0', 'rc_numbers': [999], 'components': []},  # Non-existent RC
        {'version': '3.2.0', 'rc_numbers': [], 'build_numbers': [1, 2, 3]},  # Very low build numbers
        {'version': '3.2.0', 'rc_numbers': [], 'components': ['NonExistentComponent']},  # Invalid component
        {'version': '999.999.999', 'rc_numbers': [1], 'components': []},  # Non-existent version
    ]
    
    for i, case in enumerate(edge_cases, 1):
        print(f"Edge Case {i}: {case}")
        try:
            with patch('lambda_function.opensearch_request') as mock_request:
                # Return empty results for edge cases
                mock_request.return_value = {"hits": {"total": {"value": 0}, "hits": []}}
                result = handle_integration_test_queries(case, {})
                summary = result.get('summary', {})
                print(f"  Result: {summary.get('total', 0)} results, Success Rate: {summary.get('success_rate', 0)}%")
        except Exception as e:
            print(f"  Error: {e}")
        print()

def show_raw_opensearch_query():
    """Show what the actual OpenSearch query looks like."""
    print("🔍 Raw OpenSearch Query Structure")
    print("=" * 40)
    
    from lambda_function import query_integration_test_results
    
    # Mock opensearch_request to capture the query
    captured_queries = []
    
    def capture_query(method, path, body):
        captured_queries.append({
            'method': method,
            'path': path, 
            'body': body
        })
        return {"hits": {"total": {"value": 0}, "hits": []}}
    
    with patch('lambda_function.opensearch_request', side_effect=capture_query):
        # Test different query scenarios
        scenarios = [
            {
                'name': 'RC-based query',
                'params': {'version': '3.2.0', 'rc_number': 1}
            },
            {
                'name': 'Build number query',
                'params': {'version': '3.2.0', 'build_numbers': [4891, 4892]}
            },
            {
                'name': 'Component-specific query',
                'params': {'version': '3.2.0', 'components': ['OpenSearch-Dashboards']}
            },
            {
                'name': 'Failed tests only',
                'params': {'version': '3.2.0', 'status_filter': 'failed'}
            }
        ]
        
        for scenario in scenarios:
            print(f"Scenario: {scenario['name']}")
            query_integration_test_results(**scenario['params'])
            if captured_queries:
                latest_query = captured_queries[-1]
                print(f"OpenSearch Query:")
                print(json.dumps(latest_query['body'], indent=2))
                print()

if __name__ == "__main__":
    print("Integration Test Data Analysis")
    print("=" * 60)
    
    try:
        test_integration_test_data_extraction()
        show_raw_opensearch_query()
        
        print("=" * 60)
        print("✅ Analysis Complete!")
        print("\nKey Points to Check:")
        print("1. Are the extracted field names matching what's in OpenSearch?")
        print("2. Are build numbers and RC numbers being parsed correctly?")
        print("3. Are component names consistent (especially OpenSearch-Dashboards)?")
        print("4. Are status values standardized ('passed'/'failed' vs 'success'/'failure')?")
        print("5. Are the OpenSearch queries filtering correctly?")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()