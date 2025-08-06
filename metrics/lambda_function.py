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
        elif function_name in ['get_test_metrics', 'get_build_metrics', 'get_release_metrics', 'get_deployment_metrics'] or not function_name:
            # Handle metrics queries
            result = handle_metrics_query(agent_type, function_name, params)
        else:
            result = {'error': f'Unknown function: {function_name}'}
        
        return create_response(result)
        
    except Exception as e:
        logger.error(f"Lambda handler error: {e}", exc_info=True)
        return create_response({'error': str(e), 'type': 'lambda_error'})

def handle_metrics_query(agent_type, function_name, params):
    """Handle metrics queries using boto3 HTTP requests."""
    try:
        # Default parameters
        metric_type = params.get('metric_type', 'execution')
        time_range = params.get('time_range', '7d')
        
        if agent_type in ['test-metrics', 'test']:
            return query_test_metrics(metric_type, time_range, params.get('project_filter'))
        elif agent_type in ['build-metrics', 'build']:
            return query_build_metrics(metric_type, time_range, params.get('branch_filter'))
        elif agent_type in ['release-metrics', 'release']:
            return query_release_metrics(metric_type, time_range, params.get('environment_filter'))
        elif agent_type in ['deployment-metrics', 'deployment']:
            return query_deployment_metrics(metric_type, time_range, params.get('service_filter'))
        else:
            return {'error': f'Unknown agent type: {agent_type}'}
            
    except Exception as e:
        logger.error(f"Metrics query failed: {e}")
        return {'error': str(e), 'type': 'metrics_error'}

def query_test_metrics(metric_type, time_range, project_filter):
    """Query test metrics from OpenSearch."""
    try:
        # Use the known working fields from opensearch_release_metrics
        query_body = {
            "size": 20,
            "_source": ["version", "component", "repository", "release_owners", "current_date"],
            "query": {"match_all": {}},
            "sort": [{"current_date": {"order": "desc"}}]
        }
        
        if project_filter:
            query_body["query"] = {
                "bool": {
                    "must": [{"match": {"repository": project_filter}}]
                }
            }
        
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

def query_build_metrics(metric_type, time_range, branch_filter):
    """Query build metrics from OpenSearch."""
    try:
        # Use the known working fields from opensearch_release_metrics
        query_body = {
            "size": 20,
            "_source": ["version", "component", "repository", "release_owners", "current_date"],
            "query": {"match_all": {}},
            "sort": [{"current_date": {"order": "desc"}}]
        }
        
        if branch_filter:
            query_body["query"] = {
                "bool": {
                    "must": [{"match": {"repository": branch_filter}}]
                }
            }
        
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

def query_release_metrics(metric_type, time_range, environment_filter):
    """Query release metrics from OpenSearch."""
    try:
        # Query release status data
        query_body = {
            "size": 20,
            "_source": ["version", "component", "repository", "release_owners", "current_date", "status"],
            "query": {"match_all": {}},
            "sort": [{"current_date": {"order": "desc"}}]
        }
        
        if environment_filter:
            query_body["query"] = {
                "bool": {
                    "must": [{"match": {"environment": environment_filter}}]
                }
            }
        
        result = opensearch_request('POST', '/opensearch_release_metrics/_search', query_body)
        
        hits = result.get('hits', {})
        total = hits.get('total', {}).get('value', 0)
        release_results = hits.get('hits', [])
        
        # Calculate readiness
        ready_components = sum(1 for item in release_results if item.get('_source', {}).get('status') == 'ready')
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

def query_deployment_metrics(metric_type, time_range, service_filter):
    """Query deployment metrics from OpenSearch."""
    try:
        # Use the known working fields from opensearch_release_metrics
        query_body = {
            "size": 20,
            "_source": ["version", "component", "repository", "release_owners", "current_date"],
            "query": {"match_all": {}},
            "sort": [{"current_date": {"order": "desc"}}]
        }
        
        if service_filter:
            query_body["query"] = {
                "bool": {
                    "must": [{"match": {"component": service_filter}}]
                }
            }
        
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

def create_response(result):
    """Create response in appropriate format based on invocation context."""
    # Check if this is a Bedrock agent invocation by looking for specific event structure
    # For now, return clean JSON for easier consumption
    return {
        'statusCode': 200,
        'body': result,
        'headers': {
            'Content-Type': 'application/json'
        }
    }

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