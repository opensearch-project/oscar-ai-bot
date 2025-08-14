#!/usr/bin/env python3
"""
Test script to verify the updated release metrics field handling.
This script simulates the data structure you provided to ensure our functions work correctly.
"""

import json

def test_extract_release_results():
    """Test the extract_release_results function with the new field structure."""
    
    # Sample data based on your provided JSON structure
    sample_opensearch_result = {
        "hits": {
            "hits": [
                {
                    "_index": "opensearch_release_metrics",
                    "_id": "a24ccf0c-f26b-36cf-ad4d-3842f9e02a1a",
                    "_version": 7,
                    "_score": None,
                    "_source": {
                        "release_issue_exists": True,
                        "release_notes": True,
                        "version_increment": True,
                        "release_issue": "https://github.com/opensearch-project/cross-cluster-replication/issues/1553",
                        "autocut_issues_open": 0,
                        "repository": "cross-cluster-replication",
                        "release_state": "open",
                        "version": "3.2.0",
                        "pulls_open": 0,
                        "release_owner_exists": True,
                        "current_date": "2025-08-13T18:25:21.278238477",
                        "component": "cross-cluster-replication",
                        "release_branch": True,
                        "issues_closed": 2,
                        "pulls_closed": 1,
                        "id": "a24ccf0c-f26b-36cf-ad4d-3842f9e02a1a",
                        "issues_open": 1,
                        "release_version": "3.2.0",
                        "release_owners": [
                            "mohitamg"
                        ]
                    },
                    "fields": {
                        "current_date": [
                            "2025-08-13T18:25:21.278Z"
                        ]
                    },
                    "sort": [
                        1755109521278
                    ]
                }
            ]
        }
    }
    
    # Import the function (this would normally be from the lambda_function module)
    # For testing purposes, we'll define it inline
    def extract_release_results(opensearch_result):
        """Extract comprehensive release readiness information."""
        results = []
        hits = opensearch_result.get('hits', {}).get('hits', [])
        
        for hit in hits:
            source = hit['_source']
            
            # Calculate enhanced readiness score based on all available metrics
            readiness_score = 0
            readiness_checks = []
            
            # Core release readiness checks
            if source.get('release_issue_exists'):
                readiness_score += 1
                readiness_checks.append('release_issue_exists')
            if source.get('release_notes'):
                readiness_score += 1
                readiness_checks.append('release_notes')
            if source.get('version_increment'):
                readiness_score += 1
                readiness_checks.append('version_increment')
            if source.get('release_branch'):
                readiness_score += 1
                readiness_checks.append('release_branch')
            if source.get('release_owner_exists'):
                readiness_score += 1
                readiness_checks.append('release_owner_exists')
            
            # Additional quality checks
            issues_open = source.get('issues_open', 0)
            pulls_open = source.get('pulls_open', 0)
            autocut_issues_open = source.get('autocut_issues_open', 0)
            
            # Bonus points for clean state
            if issues_open == 0:
                readiness_score += 0.5
            if pulls_open == 0:
                readiness_score += 0.5
            if autocut_issues_open == 0:
                readiness_score += 0.5
            
            results.append({
                # Core identification
                'id': source.get('id'),
                'component': source.get('component'),
                'repository': source.get('repository'),
                'version': source.get('version'),
                'release_version': source.get('release_version'),
                'timestamp': source.get('current_date'),
                
                # Release state information
                'release_state': source.get('release_state'),
                'release_branch': source.get('release_branch'),
                'release_issue_exists': source.get('release_issue_exists'),
                'release_issue': source.get('release_issue'),
                'release_notes': source.get('release_notes'),
                'version_increment': source.get('version_increment'),
                'release_owner_exists': source.get('release_owner_exists'),
                'release_owners': source.get('release_owners', []),
                
                # Issue and PR metrics
                'issues_open': issues_open,
                'issues_closed': source.get('issues_closed', 0),
                'pulls_open': pulls_open,
                'pulls_closed': source.get('pulls_closed', 0),
                'autocut_issues_open': autocut_issues_open,
                
                # Calculated readiness metrics
                'readiness_score': round(readiness_score, 1),
                'readiness_checks_passed': readiness_checks,
                'is_ready': readiness_score >= 4,  # Adjusted threshold for enhanced scoring
                'readiness_percentage': round((readiness_score / 6.5) * 100, 1),  # Out of max possible score
                
                # Quality indicators
                'has_open_issues': issues_open > 0,
                'has_open_pulls': pulls_open > 0,
                'has_autocut_issues': autocut_issues_open > 0,
                'clean_state': issues_open == 0 and pulls_open == 0 and autocut_issues_open == 0
            })
        
        return results
    
    # Test the function
    results = extract_release_results(sample_opensearch_result)
    
    print("=== Release Metrics Field Test Results ===")
    print(f"Number of results: {len(results)}")
    
    if results:
        result = results[0]
        print(f"\nSample result for component: {result['component']}")
        print(f"ID: {result['id']}")
        print(f"Repository: {result['repository']}")
        print(f"Version: {result['version']} (Release Version: {result['release_version']})")
        print(f"Release State: {result['release_state']}")
        print(f"Release Issue: {result['release_issue']}")
        print(f"Release Owners: {result['release_owners']}")
        print(f"Readiness Score: {result['readiness_score']}/6.5 ({result['readiness_percentage']}%)")
        print(f"Is Ready: {result['is_ready']}")
        print(f"Readiness Checks Passed: {result['readiness_checks_passed']}")
        print(f"Issues Open/Closed: {result['issues_open']}/{result['issues_closed']}")
        print(f"PRs Open/Closed: {result['pulls_open']}/{result['pulls_closed']}")
        print(f"Autocut Issues Open: {result['autocut_issues_open']}")
        print(f"Clean State: {result['clean_state']}")
        
        # Verify all expected fields are present
        expected_fields = [
            'id', 'component', 'repository', 'version', 'release_version', 'timestamp',
            'release_state', 'release_branch', 'release_issue_exists', 'release_issue',
            'release_notes', 'version_increment', 'release_owner_exists', 'release_owners',
            'issues_open', 'issues_closed', 'pulls_open', 'pulls_closed', 'autocut_issues_open',
            'readiness_score', 'readiness_checks_passed', 'is_ready', 'readiness_percentage',
            'has_open_issues', 'has_open_pulls', 'has_autocut_issues', 'clean_state'
        ]
        
        missing_fields = [field for field in expected_fields if field not in result]
        if missing_fields:
            print(f"\n⚠️  Missing fields: {missing_fields}")
        else:
            print(f"\n✅ All expected fields are present!")
        
        # Test the enhanced scoring
        print(f"\n=== Scoring Breakdown ===")
        print(f"Core readiness checks (5 points max):")
        for check in result['readiness_checks_passed']:
            print(f"  ✅ {check}")
        
        bonus_points = 0
        if not result['has_open_issues']:
            bonus_points += 0.5
            print(f"  ✅ No open issues (+0.5)")
        if not result['has_open_pulls']:
            bonus_points += 0.5
            print(f"  ✅ No open PRs (+0.5)")
        if not result['has_autocut_issues']:
            bonus_points += 0.5
            print(f"  ✅ No autocut issues (+0.5)")
        
        print(f"Total bonus points: {bonus_points}")
        print(f"Final score: {result['readiness_score']}/6.5")

if __name__ == "__main__":
    test_extract_release_results()