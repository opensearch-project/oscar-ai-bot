#!/usr/bin/env python3

# Based on the discovery results, create specialized query functions for each metrics type

def create_test_metrics_query(metric_type='execution', time_range='7d', project_filter=None):
    """Create specialized query for test metrics."""
    
    # Test-related repositories and components
    test_repos = [
        'opensearch-dashboards-functional-test',
        'opensearch-build'  # Contains test-related build data
    ]
    
    test_components = [
        'functionalTestDashboards',
        'opensearch-build'
    ]
    
    query = {
        "size": 20,
        "_source": [
            "component", "repository", "version", "current_date",
            "release_state", "issues_open", "issues_closed", 
            "pulls_open", "pulls_closed", "release_owners"
        ],
        "query": {
            "bool": {
                "should": [
                    {"terms": {"repository.keyword": test_repos}},
                    {"terms": {"component.keyword": test_components}},
                    {"wildcard": {"repository.keyword": "*test*"}},
                    {"wildcard": {"component.keyword": "*test*"}}
                ],
                "minimum_should_match": 1
            }
        },
        "sort": [{"current_date": {"order": "desc"}}]
    }
    
    # Add project filter if specified
    if project_filter:
        query["query"]["bool"]["must"] = [
            {"match": {"repository": project_filter}}
        ]
    
    return query

def create_build_metrics_query(metric_type='execution', time_range='7d', branch_filter=None):
    """Create specialized query for build metrics."""
    
    # Build-related repositories and components
    build_repos = [
        'opensearch-build',
        'documentation-website',
        'project-website'
    ]
    
    build_components = [
        'opensearch-build',
        'documentation-website', 
        'project-website'
    ]
    
    query = {
        "size": 20,
        "_source": [
            "component", "repository", "version", "current_date",
            "release_state", "release_branch", "issues_open", "issues_closed",
            "pulls_open", "pulls_closed", "release_owners", "version_increment"
        ],
        "query": {
            "bool": {
                "should": [
                    {"terms": {"repository.keyword": build_repos}},
                    {"terms": {"component.keyword": build_components}},
                    {"wildcard": {"repository.keyword": "*build*"}},
                    {"wildcard": {"component.keyword": "*build*"}}
                ],
                "minimum_should_match": 1
            }
        },
        "sort": [{"current_date": {"order": "desc"}}]
    }
    
    # Add branch filter if specified
    if branch_filter:
        query["query"]["bool"]["must"] = [
            {"match": {"repository": branch_filter}}
        ]
    
    return query

def create_release_metrics_query(metric_type='execution', time_range='7d', environment_filter=None):
    """Create specialized query for release metrics - focus on release readiness."""
    
    query = {
        "size": 20,
        "_source": [
            "component", "repository", "version", "current_date",
            "release_state", "release_branch", "release_issue_exists",
            "release_notes", "version_increment", "release_owners",
            "issues_open", "issues_closed", "pulls_open", "pulls_closed",
            "autocut_issues_open"
        ],
        "query": {
            "bool": {
                "must": [
                    {"exists": {"field": "release_state"}},
                    {"exists": {"field": "version"}}
                ],
                "should": [
                    {"term": {"release_state.keyword": "open"}},
                    {"term": {"release_branch": True}},
                    {"exists": {"field": "release_issue_exists"}}
                ],
                "minimum_should_match": 1
            }
        },
        "sort": [{"current_date": {"order": "desc"}}]
    }
    
    # Add environment filter (map to repository since environment field doesn't exist)
    if environment_filter:
        query["query"]["bool"]["must"].append(
            {"match": {"repository": environment_filter}}
        )
    
    return query

def create_deployment_metrics_query(metric_type='execution', time_range='7d', service_filter=None):
    """Create specialized query for deployment metrics - focus on core services."""
    
    # Core service components that would be deployed
    core_services = [
        'OpenSearch',
        'OpenSearch-Dashboards', 
        'security',
        'alerting',
        'anomaly-detection',
        'ml-commons',
        'k-NN',
        'index-management'
    ]
    
    query = {
        "size": 20,
        "_source": [
            "component", "repository", "version", "current_date",
            "release_state", "release_branch", "issues_open", "issues_closed",
            "pulls_open", "pulls_closed", "release_owners"
        ],
        "query": {
            "bool": {
                "should": [
                    {"terms": {"component.keyword": core_services}},
                    {"term": {"release_state.keyword": "closed"}},  # Successfully released
                    {"term": {"release_branch": True}}  # Has release branch
                ],
                "minimum_should_match": 1
            }
        },
        "sort": [{"current_date": {"order": "desc"}}]
    }
    
    # Add service filter if specified
    if service_filter:
        query["query"]["bool"]["must"] = [
            {"match": {"component": service_filter}}
        ]
    
    return query

# Print the queries for review
if __name__ == "__main__":
    print("=== SPECIALIZED QUERY FUNCTIONS ===")
    
    print("\n1. TEST METRICS QUERY:")
    print(json.dumps(create_test_metrics_query(), indent=2))
    
    print("\n2. BUILD METRICS QUERY:")
    print(json.dumps(create_build_metrics_query(), indent=2))
    
    print("\n3. RELEASE METRICS QUERY:")
    print(json.dumps(create_release_metrics_query(), indent=2))
    
    print("\n4. DEPLOYMENT METRICS QUERY:")
    print(json.dumps(create_deployment_metrics_query(), indent=2))