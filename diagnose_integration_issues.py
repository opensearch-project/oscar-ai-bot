#!/usr/bin/env python3
"""
Diagnostic script to identify the specific issues with integration test data extraction.
Based on your analysis, there are several problems to investigate.
"""

import json
import sys
import os

# Add metrics directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'metrics'))

def analyze_status_field_issue():
    """Analyze the status field mapping issue."""
    print("🔍 Status Field Analysis")
    print("=" * 40)
    
    print("Current Implementation:")
    print("- OpenSearch field: 'component_build_result'")
    print("- Mapped to: 'status' in results")
    print("- Expected values: 'passed', 'failed'")
    print()
    
    print("Issues Identified:")
    print("1. Field Name Mismatch:")
    print("   - The code maps 'component_build_result' to 'status'")
    print("   - But your data shows 'status' field exists in results")
    print("   - Question: Is 'component_build_result' the correct OpenSearch field?")
    print()
    
    print("2. Potential Field Name Issues:")
    print("   - OpenSearch might use different field names")
    print("   - Common alternatives: 'test_result', 'result', 'build_result', 'outcome'")
    print()
    
    print("3. Status Value Standardization:")
    print("   - Code expects: 'passed'/'failed'")
    print("   - Might actually be: 'PASSED'/'FAILED', 'success'/'failure', etc.")
    print()

def analyze_build_number_issues():
    """Analyze build number handling issues."""
    print("🔢 Build Number Analysis")
    print("=" * 40)
    
    print("Current Implementation:")
    print("- OpenSearch field: 'distribution_build_number'")
    print("- Stored as: string in results")
    print("- Used in queries as: string (converted from int)")
    print()
    
    print("Issues from your data:")
    print("- neural-search: build 11327, RC 5")
    print("- alerting: build 11327, RC 5") 
    print("- alertingDashboards: build 8589, RC 5")
    print("- OpenSearch-Dashboards-ci-group-7: build 8589, RC 5")
    print("- anomalyDetectionDashboards: build 8588, RC 4")
    print()
    
    print("Observations:")
    print("1. Same RC can have different build numbers (8588, 8589, 11327 for RC 4-5)")
    print("2. Different components can share build numbers")
    print("3. Build numbers are much higher than expected (11327 vs ~4800)")
    print()
    
    print("Potential Issues:")
    print("- Build number filtering might be too restrictive")
    print("- RC-to-build-number mapping might be incorrect")
    print("- Deduplication logic might be removing valid results")

def analyze_component_naming_issues():
    """Analyze component naming patterns."""
    print("🏷️  Component Naming Analysis")
    print("=" * 40)
    
    components_from_data = [
        "neural-search",
        "alertingDashboards", 
        "OpenSearch-Dashboards-ci-group-7",
        "alerting",
        "anomalyDetectionDashboards"
    ]
    
    print("Components from your data:")
    for comp in components_from_data:
        print(f"  - {comp}")
    print()
    
    print("Naming Pattern Issues:")
    print("1. Inconsistent casing:")
    print("   - 'alertingDashboards' vs 'OpenSearch-Dashboards-ci-group-7'")
    print("   - Some use camelCase, others use kebab-case")
    print()
    
    print("2. OpenSearch-Dashboards variations:")
    print("   - 'OpenSearch-Dashboards-ci-group-7' (with group number)")
    print("   - 'alertingDashboards' (plugin-specific)")
    print("   - 'anomalyDetectionDashboards' (plugin-specific)")
    print()
    
    print("3. Query Impact:")
    print("   - Current code has special handling for 'OpenSearch-Dashboards'")
    print("   - Uses regex: 'OpenSearch-Dashboards-ci-group-.*'")
    print("   - But plugin-specific dashboards components might not match")

def analyze_rc_build_mapping_issues():
    """Analyze RC to build number mapping issues."""
    print("🔗 RC-Build Mapping Analysis")
    print("=" * 40)
    
    print("Your data shows:")
    print("- RC 4: build 8588 (anomalyDetectionDashboards)")
    print("- RC 5: builds 8589, 11327 (multiple components)")
    print()
    
    print("Current Implementation Issues:")
    print("1. get_rc_distribution_build_number() function:")
    print("   - Tries to find highest build number for an RC")
    print("   - But your data shows multiple valid build numbers per RC")
    print("   - This suggests the mapping logic is flawed")
    print()
    
    print("2. Deduplication Logic:")
    print("   - deduplicate_by_highest_build_number() keeps only highest build")
    print("   - But different components legitimately have different builds")
    print("   - This might be removing valid test results")
    print()
    
    print("3. Strategy Selection:")
    print("   - Code has multiple query strategies (RC-based, build-based, etc.)")
    print("   - Wrong strategy selection could miss results")

def analyze_api_errors():
    """Analyze the 400 errors mentioned."""
    print("❌ API Error Analysis")
    print("=" * 30)
    
    print("You mentioned 400 errors for:")
    print("- RC build mappings")
    print("- Filtered metrics")
    print()
    
    print("Likely causes:")
    print("1. Array Parameter Parsing:")
    print("   - Parameters like 'rc_numbers', 'build_numbers' expect arrays")
    print("   - But might be passed as strings or single values")
    print("   - Lambda parameter conversion might be incorrect")
    print()
    
    print("2. Parameter Validation:")
    print("   - Missing required parameters")
    print("   - Invalid parameter formats")
    print("   - Type mismatches (string vs int)")
    print()
    
    # Show the parameter parsing code
    from lambda_function import lambda_handler
    
    print("Current parameter parsing:")
    print("```python")
    print("params = {}")
    print("for param in parameters:")
    print("    if isinstance(param, dict) and 'name' in param and 'value' in param:")
    print("        params[param['name']] = param['value']")
    print("```")
    print()
    print("Issue: This doesn't handle array parameters correctly!")

def show_recommended_fixes():
    """Show recommended fixes for the identified issues."""
    print("🔧 Recommended Fixes")
    print("=" * 30)
    
    fixes = [
        {
            "issue": "Status Field Mapping",
            "fix": "Verify the correct OpenSearch field name for test status",
            "code": "Check if it's 'component_build_result', 'test_result', or something else"
        },
        {
            "issue": "Build Number Handling", 
            "fix": "Don't assume one build number per RC",
            "code": "Allow multiple build numbers per RC and component"
        },
        {
            "issue": "Component Name Matching",
            "fix": "Improve component filtering for Dashboards plugins",
            "code": "Add patterns for 'alertingDashboards', 'anomalyDetectionDashboards', etc."
        },
        {
            "issue": "Parameter Parsing",
            "fix": "Handle array parameters correctly",
            "code": "Parse JSON arrays in parameter values"
        },
        {
            "issue": "Deduplication Logic",
            "fix": "Review deduplication strategy",
            "code": "Don't remove valid results from different components"
        },
        {
            "issue": "Query Strategy",
            "fix": "Improve query strategy selection",
            "code": "Better logic for choosing RC vs build vs component queries"
        }
    ]
    
    for i, fix in enumerate(fixes, 1):
        print(f"{i}. {fix['issue']}")
        print(f"   Fix: {fix['fix']}")
        print(f"   Action: {fix['code']}")
        print()

def create_test_queries():
    """Create test queries to validate the fixes."""
    print("🧪 Test Queries to Validate Fixes")
    print("=" * 40)
    
    test_queries = [
        {
            "name": "Verify status field",
            "query": {
                "size": 1,
                "_source": ["component_build_result", "test_result", "result", "status"],
                "query": {"match_all": {}}
            },
            "purpose": "Check what status fields actually exist"
        },
        {
            "name": "Check component patterns",
            "query": {
                "size": 0,
                "aggs": {
                    "components": {
                        "terms": {"field": "component.keyword", "size": 100}
                    }
                }
            },
            "purpose": "See all component naming patterns"
        },
        {
            "name": "RC-Build relationship",
            "query": {
                "size": 0,
                "query": {"term": {"version.keyword": "3.2.0"}},
                "aggs": {
                    "rc_builds": {
                        "terms": {"field": "rc_number.keyword"},
                        "aggs": {
                            "builds": {"terms": {"field": "distribution_build_number.keyword"}}
                        }
                    }
                }
            },
            "purpose": "Understand RC to build number relationships"
        }
    ]
    
    for query in test_queries:
        print(f"Query: {query['name']}")
        print(f"Purpose: {query['purpose']}")
        print(f"OpenSearch Query:")
        print(json.dumps(query['query'], indent=2))
        print()

if __name__ == "__main__":
    print("Integration Test Issues Diagnostic")
    print("=" * 50)
    print("Based on your analysis of the raw data...")
    print()
    
    analyze_status_field_issue()
    print()
    
    analyze_build_number_issues()
    print()
    
    analyze_component_naming_issues()
    print()
    
    analyze_rc_build_mapping_issues()
    print()
    
    analyze_api_errors()
    print()
    
    show_recommended_fixes()
    print()
    
    create_test_queries()
    
    print("=" * 50)
    print("🎯 Key Findings:")
    print("1. The 'status' field mapping might be incorrect")
    print("2. RC-to-build-number relationships are more complex than assumed")
    print("3. Component naming patterns need better handling")
    print("4. Parameter parsing for arrays is broken")
    print("5. Deduplication logic might be too aggressive")
    print()
    print("Next steps: Verify the actual OpenSearch field names and fix the parameter parsing.")