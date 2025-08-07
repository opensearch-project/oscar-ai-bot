#!/usr/bin/env python3

import json
import logging
import os
import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

logger = logging.getLogger(__name__)

def get_opensearch_session():
    """Get boto3 session with assumed cross-account role."""
    sts_client = boto3.client('sts')
    response = sts_client.assume_role(
        RoleArn='arn:aws:iam::979020455945:role/OpenSearchOscarAccessRole',
        RoleSessionName='oscar-metrics-session'
    )
    
    return boto3.Session(
        aws_access_key_id=response['Credentials']['AccessKeyId'],
        aws_secret_access_key=response['Credentials']['SecretAccessKey'],
        aws_session_token=response['Credentials']['SessionToken']
    )

def opensearch_request(method, path, body=None):
    """Make signed HTTP request to OpenSearch."""
    opensearch_host = os.getenv('OPENSEARCH_HOST', '').replace('https://', '')
    if not opensearch_host:
        raise ValueError("OPENSEARCH_HOST not configured")
    
    url = f'https://{opensearch_host}{path}'
    session = get_opensearch_session()
    
    # Create signed request
    request = AWSRequest(
        method=method,
        url=url,
        data=json.dumps(body) if body else None,
        headers={'Content-Type': 'application/json'} if body else {}
    )
    
    # Sign the request
    credentials = session.get_credentials()
    SigV4Auth(credentials, 'es', 'us-east-1').add_auth(request)
    
    # Make the request
    response = requests.request(
        method=request.method,
        url=request.url,
        data=request.body,
        headers=dict(request.headers),
        timeout=30
    )
    
    if response.status_code in [200, 201]:
        return response.json()
    else:
        raise Exception(f'OpenSearch request failed: {response.status_code} - {response.text}')

def lambda_handler(event, context):
    """Main Lambda handler."""
    try:
        logger.info("Lambda handler started")
        
        function_name = event.get('function', '')
        parameters = event.get('parameters', [])
        
        # Convert parameters to dict
        params = {}
        for param in parameters:
            if isinstance(param, dict) and 'name' in param and 'value' in param:
                params[param['name']] = param['value']
        
        agent_type = os.getenv('AGENT_TYPE', 'build-metrics')
        mock_mode = os.getenv('MOCK_MODE', 'false').lower() == 'true'
        
        logger.info(f"Function: {function_name}, Agent: {agent_type}")
        
        # Route based on function name
        if function_name == 'test_basic':
            result = {
                'status': 'success',
                'message': 'Lambda function is working',
                'agent_type': agent_type,
                'mock_mode': mock_mode
            }
        elif function_name == 'test_role_only':
            result = test_role_assumption()
        elif function_name == 'explore_indices':
            result = explore_opensearch_indices()
        elif function_name == 'test_opensearch':
            result = test_opensearch_connectivity()
        elif function_name == 'discover_indices':
            result = discover_all_indices_and_mappings()
        elif function_name in ['get_test_metrics', 'get_build_metrics', 'get_release_metrics', 'get_deployment_metrics', 'get_metrics'] or not function_name:
            # Handle metrics queries
            result = handle_metrics_query(agent_type, function_name, params)
        else:
            result = {'error': f'Unknown function: {function_name}'}
        
        return create_response(event, result)
        
    except Exception as e:
        logger.error(f"Lambda handler error: {e}", exc_info=True)
        return create_response(event, {'error': str(e), 'type': 'lambda_error'})

def handle_metrics_query(agent_type, function_name, params):
    """Handle metrics queries using boto3 HTTP requests."""
    try:
        # Default parameters
        metric_type = params.get('metric_type', 'execution')
        time_range = params.get('time_range', '7d')
        
        if agent_type in ['test-metrics', 'test']:
            return query_test_metrics(
                metric_type, time_range, 
                params.get('project_filter'),
                params.get('test_type'),
                params.get('status_filter')
            )
        elif agent_type in ['build-metrics', 'build']:
            return query_build_metrics(
                metric_type, time_range, 
                params.get('branch_filter'),
                params.get('build_type'),
                params.get('status_filter'),
                params.get('pipeline_stage')
            )
        elif agent_type in ['release-metrics', 'release']:
            return query_release_metrics(
                metric_type, time_range, 
                params.get('environment_filter'),
                params.get('release_state'),
                params.get('version_filter'),
                params.get('readiness_threshold')
            )
        elif agent_type in ['deployment-metrics', 'deployment']:
            return query_deployment_metrics(
                metric_type, time_range, 
                params.get('service_filter'),
                params.get('environment'),
                params.get('health_status'),
                params.get('deployment_type')
            )
        else:
            return {'error': f'Unknown agent type: {agent_type}'}
            
    except Exception as e:
        logger.error(f"Metrics query failed: {e}")
        return {'error': str(e), 'type': 'metrics_error'}

def query_test_metrics(metric_type, time_range, project_filter, test_type=None, status_filter=None):
    """Query test metrics from OpenSearch - specialized for test-related data."""
    try:
        # Test-related repositories and components based on discovery
        test_repos = [
            'opensearch-dashboards-functional-test',
            'opensearch-build'
        ]
        
        query_body = {
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
                        {"wildcard": {"repository.keyword": "*test*"}},
                        {"wildcard": {"component.keyword": "*test*"}}
                    ],
                    "minimum_should_match": 1
                }
            },
            "sort": [{"current_date": {"order": "desc"}}]
        }
        
        if project_filter:
            query_body["query"]["bool"]["must"] = [
                {"match": {"repository": project_filter}}
            ]
        
        result = opensearch_request('POST', '/opensearch_release_metrics/_search', query_body)
        
        hits = result.get('hits', {})
        total = hits.get('total', {}).get('value', 0)
        test_results = hits.get('hits', [])
        
        return {
            'type': 'test_metrics',
            'metric_type': metric_type,
            'time_range': time_range,
            'summary': {
                'total_results': total,
                'results_returned': len(test_results)
            },
            'recent_data': [
                {
                    'component': item.get('_source', {}).get('component', 'Unknown'),
                    'repository': item.get('_source', {}).get('repository', 'Unknown'),
                    'version': item.get('_source', {}).get('version', 'Unknown'),
                    'timestamp': item.get('_source', {}).get('current_date', 'Unknown')
                }
                for item in test_results[:10]
            ]
        }
    except Exception as e:
        return {'error': str(e), 'type': 'test_metrics_error'}

def query_build_metrics(metric_type, time_range, branch_filter, build_type=None, status_filter=None, pipeline_stage=None):
    """Query build metrics from OpenSearch - specialized for build-related data."""
    try:
        # Build-related repositories based on discovery
        build_repos = [
            'opensearch-build',
            'documentation-website',
            'project-website'
        ]
        
        query_body = {
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
                        {"wildcard": {"repository.keyword": "*build*"}},
                        {"wildcard": {"component.keyword": "*build*"}}
                    ],
                    "minimum_should_match": 1
                }
            },
            "sort": [{"current_date": {"order": "desc"}}]
        }
        
        if branch_filter:
            query_body["query"]["bool"]["must"] = [
                {"match": {"repository": branch_filter}}
            ]
        
        result = opensearch_request('POST', '/opensearch_release_metrics/_search', query_body)
        
        hits = result.get('hits', {})
        total = hits.get('total', {}).get('value', 0)
        build_results = hits.get('hits', [])
        
        return {
            'type': 'build_metrics',
            'metric_type': metric_type,
            'time_range': time_range,
            'summary': {
                'total_results': total,
                'recent_results': len(build_results)
            },
            'recent_data': [
                {
                    'component': item.get('_source', {}).get('component', 'Unknown'),
                    'repository': item.get('_source', {}).get('repository', 'Unknown'),
                    'version': item.get('_source', {}).get('version', 'Unknown'),
                    'owners': item.get('_source', {}).get('release_owners', []),
                    'timestamp': item.get('_source', {}).get('current_date', 'Unknown')
                }
                for item in build_results[:10]
            ]
        }
    except Exception as e:
        return {'error': str(e), 'type': 'build_metrics_error'}

def query_release_metrics(metric_type, time_range, environment_filter, release_state=None, version_filter=None, readiness_threshold=None):
    """Query release metrics from OpenSearch - specialized for release readiness data."""
    try:
        # Focus on release readiness indicators
        query_body = {
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
        
        if environment_filter:
            query_body["query"]["bool"]["must"].append(
                {"match": {"repository": environment_filter}}
            )
        
        result = opensearch_request('POST', '/opensearch_release_metrics/_search', query_body)
        
        hits = result.get('hits', {})
        total = hits.get('total', {}).get('value', 0)
        release_results = hits.get('hits', [])
        
        # Calculate readiness based on actual release indicators
        ready_components = 0
        for item in release_results:
            source = item.get('_source', {})
            # A component is "ready" if it has:
            # - release_issue_exists: true
            # - release_notes: true  
            # - version_increment: true
            # - release_state: closed OR release_branch: true
            readiness_score = 0
            if source.get('release_issue_exists'): readiness_score += 1
            if source.get('release_notes'): readiness_score += 1
            if source.get('version_increment'): readiness_score += 1
            if source.get('release_state') == 'closed' or source.get('release_branch'): readiness_score += 1
            
            if readiness_score >= 3:  # At least 3 out of 4 criteria
                ready_components += 1
        
        overall_readiness = (ready_components / len(release_results) * 100) if release_results else 0
        
        return {
            'type': 'release_metrics',
            'metric_type': metric_type,
            'time_range': time_range,
            'summary': {
                'total_releases': total,
                'ready_components': ready_components,
                'overall_readiness': round(overall_readiness, 1)
            },
            'recent_releases': [
                {
                    'version': item.get('_source', {}).get('version', 'Unknown'),
                    'component': item.get('_source', {}).get('component', 'Unknown'),
                    'repository': item.get('_source', {}).get('repository', 'Unknown'),
                    'owners': item.get('_source', {}).get('release_owners', []),
                    'timestamp': item.get('_source', {}).get('current_date', 'Unknown')
                }
                for item in release_results[:10]
            ]
        }
    except Exception as e:
        return {'error': str(e), 'type': 'release_metrics_error'}

def query_deployment_metrics(metric_type, time_range, service_filter, environment=None, health_status=None, deployment_type=None):
    """Query deployment metrics from OpenSearch - specialized for core service deployment data."""
    try:
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
        
        query_body = {
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
                        {"term": {"release_state.keyword": "closed"}},
                        {"term": {"release_branch": True}}
                    ],
                    "minimum_should_match": 1
                }
            },
            "sort": [{"current_date": {"order": "desc"}}]
        }
        
        if service_filter:
            query_body["query"]["bool"]["must"] = [
                {"match": {"component": service_filter}}
            ]
        
        result = opensearch_request('POST', '/opensearch_release_metrics/_search', query_body)
        
        hits = result.get('hits', {})
        total = hits.get('total', {}).get('value', 0)
        deployment_results = hits.get('hits', [])
        
        return {
            'type': 'deployment_metrics',
            'metric_type': metric_type,
            'time_range': time_range,
            'summary': {
                'total_results': total,
                'recent_results': len(deployment_results)
            },
            'recent_data': [
                {
                    'component': item.get('_source', {}).get('component', 'Unknown'),
                    'repository': item.get('_source', {}).get('repository', 'Unknown'),
                    'version': item.get('_source', {}).get('version', 'Unknown'),
                    'owners': item.get('_source', {}).get('release_owners', []),
                    'timestamp': item.get('_source', {}).get('current_date', 'Unknown')
                }
                for item in deployment_results[:10]
            ]
        }
    except Exception as e:
        return {'error': str(e), 'type': 'deployment_metrics_error'}

def test_role_assumption():
    """Test cross-account role assumption."""
    try:
        import time
        
        logger.info("Testing role assumption")
        
        start_time = time.time()
        session = get_opensearch_session()
        end_time = time.time()
        
        # Test assumed identity
        sts_client = session.client('sts')
        assumed_identity = sts_client.get_caller_identity()
        
        return {
            'status': 'success',
            'duration_seconds': round(end_time - start_time, 3),
            'assumed_identity': {
                'account': assumed_identity.get('Account'),
                'arn': assumed_identity.get('Arn'),
                'user_id': assumed_identity.get('UserId')
            }
        }
        
    except Exception as e:
        return {
            'status': 'failed',
            'error': str(e),
            'error_type': type(e).__name__
        }

def test_opensearch_connectivity():
    """Test OpenSearch connectivity and basic queries."""
    try:
        # Test basic cluster health
        health = opensearch_request('GET', '/_cluster/health')
        
        # Test a simple search
        search_result = opensearch_request('POST', '/opensearch_release_metrics/_search', {
            "size": 1,
            "query": {"match_all": {}}
        })
        
        return {
            'status': 'success',
            'cluster_health': health.get('status', 'unknown'),
            'cluster_name': health.get('cluster_name', 'unknown'),
            'total_documents': search_result.get('hits', {}).get('total', {}).get('value', 0)
        }
        
    except Exception as e:
        return {
            'status': 'failed',
            'error': str(e),
            'error_type': type(e).__name__
        }

def explore_opensearch_indices():
    """Explore OpenSearch indices and their mappings."""
    try:
        # Get all indices
        indices = opensearch_request('GET', '/_cat/indices?format=json')
        
        # Focus on build-related indices
        build_indices = [idx for idx in indices if 'build' in idx.get('index', '').lower() or 'test' in idx.get('index', '').lower() or 'release' in idx.get('index', '').lower()]
        
        index_details = []
        for idx in build_indices[:5]:  # Limit to first 5 indices
            index_name = idx.get('index')
            try:
                # Get mapping for this index
                mapping = opensearch_request('GET', f'/{index_name}/_mapping')
                
                # Get sample document
                sample = opensearch_request('POST', f'/{index_name}/_search', {
                    "size": 1,
                    "query": {"match_all": {}}
                })
                
                index_details.append({
                    'index_name': index_name,
                    'doc_count': idx.get('docs.count', '0'),
                    'store_size': idx.get('store.size', '0'),
                    'mapping_fields': list(mapping.get(index_name, {}).get('mappings', {}).get('properties', {}).keys())[:10],
                    'sample_document': sample.get('hits', {}).get('hits', [{}])[0].get('_source', {}) if sample.get('hits', {}).get('hits') else {}
                })
            except Exception as e:
                index_details.append({
                    'index_name': index_name,
                    'error': str(e)
                })
        
        return {
            'status': 'success',
            'total_indices': len(indices),
            'build_related_indices': len(build_indices),
            'index_details': index_details
        }
        
    except Exception as e:
        return {
            'status': 'failed',
            'error': str(e),
            'error_type': type(e).__name__
        }

def create_response(event, result):
    """Create a response in the format expected by the Bedrock agent."""
    action_group = event['actionGroup']
    function = event['function']
    response_body_string = json.dumps(result, default=str)

    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": action_group,
            "function": function,
            "functionResponse": {
                "responseBody": {
                    "TEXT": {
                        "body": response_body_string
                    }
                }
            }
        }
    }

def discover_all_indices_and_mappings():
    """Discover field structure using search queries since we can't access mappings."""
    try:
        # We know opensearch_release_metrics exists, let's analyze its structure
        index_name = 'opensearch_release_metrics'
        
        # Get sample documents to understand field structure
        sample_query = {
            "size": 10,
            "query": {"match_all": {}},
            "sort": [{"current_date": {"order": "desc"}}]
        }
        
        sample_result = opensearch_request('POST', f'/{index_name}/_search', sample_query)
        hits = sample_result.get('hits', {}).get('hits', [])
        total_docs = sample_result.get('hits', {}).get('total', {}).get('value', 0)
        
        # Analyze field structure from sample documents
        all_fields = set()
        field_examples = {}
        
        for hit in hits:
            source = hit.get('_source', {})
            for field, value in source.items():
                all_fields.add(field)
                if field not in field_examples:
                    field_examples[field] = value
        
        # Try to find different types of data by searching for specific patterns
        analysis_queries = {
            'build_related': {
                "query": {"bool": {"should": [
                    {"wildcard": {"component.keyword": "*build*"}},
                    {"wildcard": {"repository.keyword": "*build*"}},
                    {"match": {"component": "build"}}
                ]}},
                "size": 5
            },
            'test_related': {
                "query": {"bool": {"should": [
                    {"wildcard": {"component.keyword": "*test*"}},
                    {"wildcard": {"repository.keyword": "*test*"}},
                    {"match": {"component": "test"}}
                ]}},
                "size": 5
            },
            'deployment_related': {
                "query": {"bool": {"should": [
                    {"wildcard": {"component.keyword": "*deploy*"}},
                    {"wildcard": {"repository.keyword": "*deploy*"}},
                    {"match": {"component": "deploy"}}
                ]}},
                "size": 5
            },
            'unique_components': {
                "size": 0,
                "aggs": {
                    "components": {"terms": {"field": "component.keyword", "size": 50}}
                }
            },
            'unique_repositories': {
                "size": 0,
                "aggs": {
                    "repositories": {"terms": {"field": "repository.keyword", "size": 50}}
                }
            },
            'version_patterns': {
                "size": 0,
                "aggs": {
                    "versions": {"terms": {"field": "version.keyword", "size": 20}}
                }
            }
        }
        
        analysis_results = {}
        for analysis_name, query in analysis_queries.items():
            try:
                result = opensearch_request('POST', f'/{index_name}/_search', query)
                analysis_results[analysis_name] = result
            except Exception as e:
                analysis_results[analysis_name] = {'error': str(e)}
        
        return {
            'status': 'success',
            'index_analysis': {
                'index_name': index_name,
                'total_documents': total_docs,
                'discovered_fields': list(all_fields),
                'field_examples': field_examples,
                'sample_documents': [hit.get('_source', {}) for hit in hits],
                'specialized_analysis': analysis_results
            }
        }
        
    except Exception as e:
        return {
            'status': 'failed',
            'error': str(e),
            'error_type': type(e).__name__
        }

def discover_all_indices_and_mappings_old():
    """Old discovery function - kept for reference."""
    results = {
        'discovery_methods': [],
        'successful_indices': [],
        'failed_attempts': []
    }
    
    # Method 1: Try known index patterns from our existing queries
    known_patterns = [
        'opensearch_release_metrics',
        'opensearch_build_metrics', 
        'opensearch_test_metrics',
        'opensearch_deployment_metrics',
        'build_metrics',
        'test_metrics',
        'release_metrics',
        'deployment_metrics',
        'ci_metrics',
        'pipeline_metrics'
    ]
    
    results['discovery_methods'].append('known_patterns')
    for pattern in known_patterns:
        try:
            # Try to get mapping first
            mapping = opensearch_request('GET', f'/{pattern}/_mapping')
            
            # If mapping succeeds, get sample data
            sample = opensearch_request('POST', f'/{pattern}/_search', {
                "size": 3,
                "query": {"match_all": {}}
            })
            
            properties = mapping.get(pattern, {}).get('mappings', {}).get('properties', {})
            hits = sample.get('hits', {}).get('hits', [])
            total_docs = sample.get('hits', {}).get('total', {}).get('value', 0)
            
            results['successful_indices'].append({
                'index_name': pattern,
                'method': 'known_pattern',
                'total_documents': total_docs,
                'fields': list(properties.keys()),
                'field_types': {k: v.get('type', 'unknown') for k, v in properties.items()},
                'sample_documents': [hit.get('_source', {}) for hit in hits],
                'metrics_relevance': analyze_metrics_relevance(properties, [hit.get('_source', {}) for hit in hits])
            })
            
        except Exception as e:
            results['failed_attempts'].append({
                'index_pattern': pattern,
                'method': 'known_pattern',
                'error': str(e)
            })
    
    # Method 2: Try wildcard searches on known working index
    results['discovery_methods'].append('wildcard_search')
    try:
        # Use the known working index to search for similar patterns
        base_search = opensearch_request('POST', '/opensearch_release_metrics/_search', {
            "size": 0,
            "aggs": {
                "unique_indices": {
                    "terms": {
                        "field": "_index",
                        "size": 100
                    }
                }
            }
        })
        
        # This might reveal other indices if they exist
        results['wildcard_search_result'] = base_search.get('aggregations', {})
        
    except Exception as e:
        results['failed_attempts'].append({
            'method': 'wildcard_search',
            'error': str(e)
        })
    
    # Method 3: Try different index naming conventions
    results['discovery_methods'].append('naming_conventions')
    naming_conventions = [
        'metrics-build',
        'metrics-test', 
        'metrics-release',
        'metrics-deployment',
        'build-*',
        'test-*',
        'release-*',
        'deploy-*'
    ]
    
    for convention in naming_conventions:
        try:
            search_result = opensearch_request('POST', f'/{convention}/_search', {
                "size": 1,
                "query": {"match_all": {}}
            })
            
            if search_result.get('hits', {}).get('total', {}).get('value', 0) > 0:
                # Get mapping for this index
                mapping = opensearch_request('GET', f'/{convention}/_mapping')
                
                results['successful_indices'].append({
                    'index_name': convention,
                    'method': 'naming_convention',
                    'total_documents': search_result.get('hits', {}).get('total', {}).get('value', 0),
                    'mapping': mapping
                })
                
        except Exception as e:
            results['failed_attempts'].append({
                'index_pattern': convention,
                'method': 'naming_convention', 
                'error': str(e)
            })
    
    # Method 4: Analyze the working index in detail
    results['discovery_methods'].append('detailed_analysis')
    try:
        # Deep dive into opensearch_release_metrics
        detailed_mapping = opensearch_request('GET', '/opensearch_release_metrics/_mapping')
        
        # Get field statistics
        field_stats = opensearch_request('POST', '/opensearch_release_metrics/_search', {
            "size": 0,
            "aggs": {
                "component_types": {
                    "terms": {"field": "component.keyword", "size": 20}
                },
                "repository_types": {
                    "terms": {"field": "repository.keyword", "size": 20}
                },
                "version_types": {
                    "terms": {"field": "version.keyword", "size": 10}
                }
            }
        })
        
        results['detailed_analysis'] = {
            'mapping': detailed_mapping,
            'field_statistics': field_stats.get('aggregations', {}),
            'total_documents': field_stats.get('hits', {}).get('total', {}).get('value', 0)
        }
        
    except Exception as e:
        results['failed_attempts'].append({
            'method': 'detailed_analysis',
            'error': str(e)
        })
    
    return {
        'status': 'success',
        'discovery_results': results,
        'summary': {
            'methods_tried': len(results['discovery_methods']),
            'successful_indices': len(results['successful_indices']),
            'failed_attempts': len(results['failed_attempts'])
        }
    }

def analyze_metrics_relevance(fields, sample_docs):
    """Analyze how relevant an index is for different metrics types."""
    relevance = {
        'test': 0,
        'build': 0, 
        'release': 0,
        'deployment': 0
    }
    
    # Keywords for each metrics type
    keywords = {
        'test': ['test', 'result', 'status', 'coverage', 'failure', 'success', 'execution', 'junit', 'spec'],
        'build': ['build', 'pipeline', 'job', 'branch', 'commit', 'duration', 'ci', 'jenkins', 'gradle'],
        'release': ['release', 'version', 'deploy', 'environment', 'rollback', 'readiness', 'component'],
        'deployment': ['deploy', 'service', 'environment', 'health', 'uptime', 'performance', 'infrastructure']
    }
    
    # Check field names
    for field_name in fields.keys():
        field_lower = field_name.lower()
        for metrics_type, type_keywords in keywords.items():
            if any(keyword in field_lower for keyword in type_keywords):
                relevance[metrics_type] += 1
    
    # Check sample document content
    for doc in sample_docs:
        doc_str = json.dumps(doc).lower()
        for metrics_type, type_keywords in keywords.items():
            if any(keyword in doc_str for keyword in type_keywords):
                relevance[metrics_type] += 0.5
    
    return relevance

def create_bedrock_response(result):
    """Create Bedrock agent compatible response when needed."""
    return {
        'response': {
            'functionResponse': {
                'responseBody': {
                    'TEXT': {
                        'body': json.dumps(result, indent=2, default=str)
                    }
                }
            }
        }
    }