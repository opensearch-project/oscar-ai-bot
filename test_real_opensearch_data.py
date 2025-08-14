#!/usr/bin/env python3
"""
Test script to connect to the real OpenSearch instance and show actual integration test data.
This will reveal what parameters might be wrong and show raw data examples.
"""

import json
import sys
import os
from unittest.mock import patch

# Set environment variables from .env
os.environ['OPENSEARCH_HOST'] = 'https://aos-a4f4c9d2accb-brkjnnuiccoheln4bmcpzv4auq.us-east-1.es.amazonaws.com'
os.environ['AWS_REGION'] = 'us-east-1'
os.environ['AGENT_TYPE'] = 'integration-test'

# Add metrics directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'metrics'))

def test_opensearch_connectivity():
    """Test basic OpenSearch connectivity and show index structure."""
    print("🔗 Testing OpenSearch Connectivity")
    print("=" * 50)
    
    try:
        from lambda_function import opensearch_request, test_opensearch_connectivity
        
        # Test basic connectivity
        print("Testing basic connectivity...")
        connectivity_result = test_opensearch_connectivity()
        print("Connectivity Result:")
        print(json.dumps(connectivity_result, indent=2))
        print()
        
        # Get index information
        print("Getting index information...")
        try:
            indices_info = opensearch_request('GET', '/_cat/indices/opensearch-integration-test-results?format=json')
            print("Index Info:")
            print(json.dumps(indices_info, indent=2))
        except Exception as e:
            print(f"Could not get index info: {e}")
        print()
        
        # Get index mapping
        print("Getting index mapping...")
        try:
            mapping = opensearch_request('GET', '/opensearch-integration-test-results/_mapping')
            print("Index Mapping (first 1000 chars):")
            mapping_str = json.dumps(mapping, indent=2)
            print(mapping_str[:1000] + "..." if len(mapping_str) > 1000 else mapping_str)
        except Exception as e:
            print(f"Could not get mapping: {e}")
        print()
        
        return True
        
    except Exception as e:
        print(f"❌ Connectivity test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def show_sample_integration_data():
    """Show sample integration test data from the actual index."""
    print("📊 Sample Integration Test Data")
    print("=" * 50)
    
    try:
        from lambda_function import opensearch_request
        
        # Get a few sample documents
        sample_query = {
            "size": 5,
            "sort": [{"build_start_time": {"order": "desc"}}],
            "query": {"match_all": {}}
        }
        
        print("Fetching sample documents...")
        result = opensearch_request('POST', '/opensearch-integration-test-results/_search', sample_query)
        
        hits = result.get('hits', {}).get('hits', [])
        total = result.get('hits', {}).get('total', {})
        
        print(f"Total documents in index: {total}")
        print(f"Sample documents retrieved: {len(hits)}")
        print()
        
        for i, hit in enumerate(hits):
            source = hit['_source']
            print(f"Document {i+1}:")
            print(f"  Component: {source.get('component')}")
            print(f"  Status: {source.get('component_build_result')}")
            print(f"  Version: {source.get('version')}")
            print(f"  Build Number: {source.get('distribution_build_number')}")
            print(f"  RC Number: {source.get('rc_number')}")
            print(f"  Platform: {source.get('platform')}")
            print(f"  Architecture: {source.get('architecture')}")
            print(f"  Distribution: {source.get('distribution')}")
            print(f"  Timestamp: {source.get('build_start_time')}")
            print(f"  Category: {source.get('component_category')}")
            print(f"  Qualifier: {source.get('qualifier')}")
            print()
        
        # Show all available fields in the first document
        if hits:
            print("All fields in first document:")
            all_fields = list(hits[0]['_source'].keys())
            print(f"Fields: {sorted(all_fields)}")
            print()
        
        return hits
        
    except Exception as e:
        print(f"❌ Failed to get sample data: {e}")
        import traceback
        traceback.print_exc()
        return []

def test_specific_queries():
    """Test specific queries that might be problematic."""
    print("🔍 Testing Specific Queries")
    print("=" * 50)
    
    try:
        from lambda_function import opensearch_request
        
        # Test queries that might reveal issues
        test_queries = [
            {
                "name": "Recent versions",
                "query": {
                    "size": 10,
                    "query": {"range": {"version": {"gte": "2.0.0"}}},
                    "_source": ["version", "component", "component_build_result"],
                    "aggs": {
                        "versions": {"terms": {"field": "version.keyword", "size": 10}},
                        "components": {"terms": {"field": "component.keyword", "size": 20}},
                        "statuses": {"terms": {"field": "component_build_result.keyword", "size": 10}}
                    }
                }
            },
            {
                "name": "RC numbers analysis",
                "query": {
                    "size": 0,
                    "aggs": {
                        "rc_numbers": {"terms": {"field": "rc_number.keyword", "size": 20}},
                        "rc_number_types": {"terms": {"script": "doc['rc_number.keyword'].value.class.simpleName"}}
                    }
                }
            },
            {
                "name": "Build numbers analysis", 
                "query": {
                    "size": 0,
                    "aggs": {
                        "build_number_range": {"stats": {"script": "Integer.parseInt(doc['distribution_build_number.keyword'].value)"}},
                        "build_number_types": {"terms": {"script": "doc['distribution_build_number.keyword'].value.class.simpleName"}}
                    }
                }
            }
        ]
        
        for test_query in test_queries:
            print(f"Query: {test_query['name']}")
            try:
                result = opensearch_request('POST', '/opensearch-integration-test-results/_search', test_query['query'])
                
                # Show aggregations if present
                aggs = result.get('aggregations', {})
                if aggs:
                    print("Aggregation Results:")
                    for agg_name, agg_result in aggs.items():
                        if 'buckets' in agg_result:
                            print(f"  {agg_name}:")
                            for bucket in agg_result['buckets'][:10]:  # Show first 10
                                print(f"    {bucket.get('key')}: {bucket.get('doc_count')}")
                        elif 'value' in agg_result:
                            print(f"  {agg_name}: {agg_result['value']}")
                        else:
                            print(f"  {agg_name}: {agg_result}")
                
                # Show hits if present
                hits = result.get('hits', {}).get('hits', [])
                if hits:
                    print(f"Sample hits: {len(hits)}")
                    for hit in hits[:3]:
                        source = hit['_source']
                        print(f"  {source.get('component')} - {source.get('component_build_result')} - {source.get('version')}")
                
            except Exception as e:
                print(f"  ❌ Query failed: {e}")
            
            print()
    
    except Exception as e:
        print(f"❌ Query testing failed: {e}")
        import traceback
        traceback.print_exc()

def test_integration_lambda_with_real_data():
    """Test the integration test lambda with real data."""
    print("🧪 Testing Integration Lambda with Real Data")
    print("=" * 50)
    
    try:
        from lambda_function import lambda_handler
        
        # Test with a recent version that should have data
        test_events = [
            {
                "name": "General query for version 2.18.0",
                "event": {
                    "actionGroup": "metrics-query",
                    "function": "get_integration_test_metrics",
                    "parameters": [
                        {"name": "query", "value": "integration test results for version 2.18.0"},
                        {"name": "version", "value": "2.18.0"}
                    ]
                }
            },
            {
                "name": "Failed tests for version 2.17.0",
                "event": {
                    "actionGroup": "metrics-query",
                    "function": "get_integration_test_metrics", 
                    "parameters": [
                        {"name": "query", "value": "failed integration tests for version 2.17.0"},
                        {"name": "version", "value": "2.17.0"},
                        {"name": "status_filter", "value": "failed"}
                    ]
                }
            }
        ]
        
        for test_event in test_events:
            print(f"Test: {test_event['name']}")
            print("-" * 30)
            
            try:
                result = lambda_handler(test_event['event'], None)
                
                # Extract response
                response_body = result.get('response', {}).get('functionResponse', {}).get('responseBody', {}).get('TEXT', {}).get('body')
                
                if response_body:
                    parsed_response = json.loads(response_body)
                    
                    # Show summary
                    summary = parsed_response.get('summary', {})
                    print(f"Summary: {summary}")
                    
                    # Show query intent
                    query_intent = parsed_response.get('query_intent', {})
                    print(f"Query Intent: {query_intent}")
                    
                    # Show results count
                    results = parsed_response.get('results', [])
                    total_results = 0
                    for result_set in results:
                        test_results = result_set.get('test_results', [])
                        total_results += len(test_results)
                        print(f"Strategy '{result_set.get('strategy')}': {len(test_results)} results")
                        
                        # Show sample results
                        if test_results:
                            print("Sample results:")
                            for i, test_result in enumerate(test_results[:3]):
                                print(f"  {i+1}. {test_result.get('component')} - {test_result.get('status')} - Build {test_result.get('build_number')}")
                    
                    print(f"Total results: {total_results}")
                    
                    # Check for errors
                    if 'error' in parsed_response:
                        print(f"❌ Error: {parsed_response['error']}")
                
                else:
                    print("❌ No response body")
                    print(f"Full result: {result}")
                
            except Exception as e:
                print(f"❌ Test failed: {e}")
                import traceback
                traceback.print_exc()
            
            print()
    
    except Exception as e:
        print(f"❌ Lambda testing failed: {e}")
        import traceback
        traceback.print_exc()

def identify_data_issues(sample_data):
    """Identify potential issues in the actual data."""
    print("⚠️  Data Issue Analysis")
    print("=" * 30)
    
    if not sample_data:
        print("No sample data available for analysis")
        return
    
    issues = []
    
    # Analyze the sample data
    for i, hit in enumerate(sample_data):
        source = hit['_source']
        
        # Check for missing critical fields
        critical_fields = ['component', 'component_build_result', 'version', 'distribution_build_number']
        missing_fields = [field for field in critical_fields if not source.get(field)]
        if missing_fields:
            issues.append(f"Document {i+1}: Missing fields {missing_fields}")
        
        # Check data types and formats
        build_number = source.get('distribution_build_number')
        if build_number and not str(build_number).isdigit():
            issues.append(f"Document {i+1}: Non-numeric build number: {build_number}")
        
        rc_number = source.get('rc_number')
        if rc_number and not str(rc_number).replace('.', '').isdigit():
            issues.append(f"Document {i+1}: Unexpected RC number format: {rc_number}")
        
        # Check status values
        status = source.get('component_build_result')
        expected_statuses = ['passed', 'failed', 'success', 'failure', 'PASSED', 'FAILED', 'SUCCESS', 'FAILURE']
        if status and status not in expected_statuses:
            issues.append(f"Document {i+1}: Unexpected status value: {status}")
        
        # Check version format
        version = source.get('version')
        if version and not any(char.isdigit() for char in version):
            issues.append(f"Document {i+1}: Unexpected version format: {version}")
    
    # Show unique values for key fields
    print("Unique values analysis:")
    
    components = list(set(hit['_source'].get('component') for hit in sample_data if hit['_source'].get('component')))
    print(f"Components: {components}")
    
    statuses = list(set(hit['_source'].get('component_build_result') for hit in sample_data if hit['_source'].get('component_build_result')))
    print(f"Statuses: {statuses}")
    
    versions = list(set(hit['_source'].get('version') for hit in sample_data if hit['_source'].get('version')))
    print(f"Versions: {versions}")
    
    platforms = list(set(hit['_source'].get('platform') for hit in sample_data if hit['_source'].get('platform')))
    print(f"Platforms: {platforms}")
    
    architectures = list(set(hit['_source'].get('architecture') for hit in sample_data if hit['_source'].get('architecture')))
    print(f"Architectures: {architectures}")
    
    distributions = list(set(hit['_source'].get('distribution') for hit in sample_data if hit['_source'].get('distribution')))
    print(f"Distributions: {distributions}")
    
    print()
    
    if issues:
        print("Issues found:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("✅ No obvious data issues detected")

if __name__ == "__main__":
    print("Real OpenSearch Integration Test Data Analysis")
    print("=" * 60)
    
    try:
        # Test connectivity first
        if test_opensearch_connectivity():
            print()
            
            # Get sample data
            sample_data = show_sample_integration_data()
            print()
            
            # Test specific queries
            test_specific_queries()
            print()
            
            # Test the lambda with real data
            test_integration_lambda_with_real_data()
            print()
            
            # Analyze data issues
            identify_data_issues(sample_data)
            
            print("=" * 60)
            print("🎯 Analysis Complete!")
            print("\nThis shows you the actual data structure and potential issues.")
            print("Check the output above for:")
            print("- Field names and data types")
            print("- Status value variations")
            print("- Component naming patterns")
            print("- Version formats")
            print("- Build/RC number formats")
        else:
            print("❌ Could not connect to OpenSearch - check credentials and network access")
        
    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        import traceback
        traceback.print_exc()