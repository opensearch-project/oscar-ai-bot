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
        
        agent_type = os.getenv('AGENT_TYPE', 'integration-test') # --> How does this work?
        
        logger.info(f"Function: {function_name}, Agent: {agent_type}")
        
        # Route based on function name
        if function_name == 'test_basic':
            result = {'status': 'success', 'message': 'Enhanced Lambda function is working', 'agent_type': agent_type}
        elif function_name == 'test_role_only':
            result = test_role_assumption()
        elif function_name == 'test_opensearch':
            result = test_opensearch_connectivity()
        elif function_name in ['get_integration_test_metrics', 'get_test_metrics', 'get_build_metrics', 'get_release_metrics', 'get_metrics', 'query_integration_test_failures', 'resolve_components_from_builds', 'get_rc_build_mapping'] or not function_name:
            result = handle_metrics_query(agent_type, function_name, params)
        elif function_name == 'resolve_components_from_builds':
            result = handle_component_resolution(params)
        elif function_name == 'get_rc_build_mapping':
            result = handle_rc_build_mapping(params)
        else:
            result = {'error': f'Unknown function: {function_name}'}
        
        return create_response(event, result)
        
    except Exception as e:
        logger.error(f"Lambda handler error: {e}", exc_info=True)
        return create_response(event, {'error': str(e), 'type': 'lambda_error'})

def handle_metrics_query(agent_type, function_name, params):
    """Enhanced metrics query handler with natural language support."""
    try:
        query_text = params.get('query', '')
        
        # Parse query intent for all queries
        intent = parse_query_intent(query_text, params)
        
        # Route to appropriate agent with enhanced logic
        if agent_type in ['integration-test', 'test-metrics', 'test']:
            return handle_integration_test_queries(intent, params)
        elif agent_type in ['build-metrics', 'build']:
            return handle_build_queries(intent, params)
        elif agent_type in ['release-metrics', 'release']:
            return handle_release_queries(intent, params)
        else:
            return {'error': f'Unknown agent type: {agent_type}'}
            
    except Exception as e:
        logger.error(f"Enhanced metrics query failed: {e}")
        return {'error': str(e), 'type': 'enhanced_metrics_error'}

def handle_integration_test_queries(intent, params):
    """Handle integration test queries using opensearch-integration-test-results index."""
    try:
        version = intent.get('version')
        if not version:
            return {'error': 'Version is required for integration test queries'}
        
        # Execute multi-strategy query
        results = execute_integration_test_strategy(intent)
        
        return {
            'agent_type': 'integration_test',
            'query_intent': intent,
            'results': results,
            'summary': generate_integration_summary(results),
            'data_source': 'opensearch-integration-test-results'
        }
        
    except Exception as e:
        logger.error(f"Integration test query failed: {e}")
        return {'error': str(e), 'type': 'integration_test_error'}

def handle_build_queries(intent, params):
    """Handle build queries using opensearch-distribution-build-results index."""
    try:
        version = intent.get('version')
        if not version:
            return {'error': 'Version is required for build queries'}
        
        results = execute_build_strategy(intent)
        
        return {
            'agent_type': 'build',
            'query_intent': intent,
            'results': results,
            'summary': generate_build_summary(results),
            'data_source': 'opensearch-distribution-build-results'
        }
        
    except Exception as e:
        logger.error(f"Build query failed: {e}")
        return {'error': str(e), 'type': 'build_error'}

def handle_release_queries(intent, params):
    """Handle release queries using opensearch_release_metrics index."""
    try:
        version = intent.get('version')
        if not version:
            return {'error': 'Version is required for release queries'}
        
        results = execute_release_strategy(intent)
        
        return {
            'agent_type': 'release',
            'query_intent': intent,
            'results': results,
            'summary': generate_release_summary(results),
            'data_source': 'opensearch_release_metrics'
        }
        
    except Exception as e:
        logger.error(f"Release query failed: {e}")
        return {'error': str(e), 'type': 'release_error'}

def parse_query_intent(query_text, params=None):
    """Enhanced query parsing to extract comprehensive parameters."""
    import re
    
    if params is None:
        params = {}
    
    intent = {
        'version': params.get('version'),
        'rc_numbers': params.get('rc_numbers', []),
        'build_numbers': params.get('build_numbers', []),
        'components': params.get('components', []),
        'status_filter': params.get('status_filter'),
        'distribution': params.get('distribution', 'tar'),
        'architecture': params.get('architecture', 'x64'),
        'platform': params.get('platform', 'linux'),
        'time_range': params.get('time_range', '7d'),
        'query_type': 'general'
    }
    
    if not query_text:
        return intent
    
    query_lower = query_text.lower()
    
    # Extract version
    if not intent['version']:
        version_match = re.search(r'version\s+(\d+\.\d+\.\d+)', query_text, re.IGNORECASE)
        if version_match:
            intent['version'] = version_match.group(1)
    
    # Extract RC numbers
    if not intent['rc_numbers']:
        rc_matches = re.findall(r'RC\s+(?:number\s+)?(\d+)', query_text, re.IGNORECASE)
        intent['rc_numbers'] = [int(rc) for rc in rc_matches]
    
    # Extract build numbers - handle both singular and plural
    if not intent['build_numbers']:
        build_matches = re.findall(r'build\s+numbers?\s+(\d+(?:,\s*\d+)*)', query_text, re.IGNORECASE)
        if build_matches:
            # Handle comma-separated build numbers
            build_nums = []
            for match in build_matches:
                nums = [int(n.strip()) for n in match.split(',')]
                build_nums.extend(nums)
            intent['build_numbers'] = build_nums
        else:
            # Fallback to individual build number pattern
            single_matches = re.findall(r'build\s+(?:number\s+)?(\d+)', query_text, re.IGNORECASE)
            intent['build_numbers'] = [int(build) for build in single_matches]
    
    # Extract components
    if not intent['components']:
        if 'opensearch-dashboards' in query_lower or 'dashboards' in query_lower:
            intent['components'].append('OpenSearch-Dashboards')
        if 'opensearch' in query_lower and 'dashboards' not in query_lower:
            intent['components'].append('OpenSearch')
    
    # Determine query type
    if 'failed' in query_lower or 'failure' in query_lower:
        intent['status_filter'] = 'failed'
        intent['query_type'] = 'failure_analysis'
    elif 'passed' in query_lower or 'success' in query_lower:
        intent['status_filter'] = 'passed'
        intent['query_type'] = 'success_analysis'
    elif 'integration test' in query_lower:
        intent['query_type'] = 'integration_test'
    elif 'build' in query_lower:
        intent['query_type'] = 'build_analysis'
    elif 'release' in query_lower:
        intent['query_type'] = 'release_analysis'
    
    # Extract platform/architecture
    if 'arm64' in query_lower:
        intent['architecture'] = 'arm64'
    if 'windows' in query_lower:
        intent['platform'] = 'windows'
    if 'rpm' in query_lower:
        intent['distribution'] = 'rpm'
    elif 'deb' in query_lower:
        intent['distribution'] = 'deb'
    
    return intent

def execute_integration_test_strategy(intent):
    """Execute integration test queries with multiple strategies."""
    version = intent['version']
    rc_numbers = intent['rc_numbers']
    build_numbers = intent['build_numbers']
    components = intent['components']
    status_filter = intent.get('status_filter')
    
    results = []
    
    # Strategy 1: RC-based queries
    if rc_numbers:
        for rc_num in rc_numbers:
            if components:
                for component in components:
                    build_num = get_rc_distribution_build_number(version, rc_num, component)
                    if build_num:
                        result = query_integration_test_results(
                            version=version,
                            rc_number=rc_num,
                            build_numbers=[build_num],
                            components=[component],
                            status_filter=status_filter,
                            distribution=intent.get('distribution'),
                            architecture=intent.get('architecture')
                        )
                        results.append({
                            'strategy': 'rc_component_based',
                            'rc_number': rc_num,
                            'component': component,
                            'build_number': build_num,
                            'test_results': extract_test_results(result)
                        })
            else:
                # Query all components for this RC
                result = query_integration_test_results(
                    version=version,
                    rc_number=rc_num,
                    status_filter=status_filter,
                    distribution=intent.get('distribution'),
                    architecture=intent.get('architecture')
                )
                results.append({
                    'strategy': 'rc_based',
                    'rc_number': rc_num,
                    'test_results': extract_test_results(result)
                })
    
    # Strategy 2: Direct build number queries
    elif build_numbers:
        if not components:
            component_map = resolve_components_from_build_numbers(version, build_numbers)
            all_components = []
            for comps in component_map.values():
                all_components.extend(comps)
            components = list(set(all_components))
        
        result = query_integration_test_results(
            version=version,
            build_numbers=build_numbers,
            components=components,
            status_filter=status_filter,
            distribution=intent.get('distribution'),
            architecture=intent.get('architecture')
        )
        results.append({
            'strategy': 'build_number_based',
            'build_numbers': build_numbers,
            'components': components,
            'test_results': extract_test_results(result)
        })
    
    # Strategy 3: Component-only queries (latest builds)
    elif components:
        result = query_integration_test_results(
            version=version,
            components=components,
            status_filter=status_filter,
            distribution=intent.get('distribution'),
            architecture=intent.get('architecture')
        )
        results.append({
            'strategy': 'component_based',
            'components': components,
            'test_results': extract_test_results(result)
        })
    
    # Strategy 4: General query (all recent results)
    else:
        result = query_integration_test_results(
            version=version,
            status_filter=status_filter,
            distribution=intent.get('distribution'),
            architecture=intent.get('architecture')
        )
        results.append({
            'strategy': 'general',
            'test_results': extract_test_results(result)
        })
    
    return results

def execute_build_strategy(intent):
    """Execute build queries using distribution build results."""
    version = intent['version']
    build_numbers = intent['build_numbers']
    components = intent['components']
    status_filter = intent.get('status_filter')
    
    # For consistency, always query all results first, then filter in summary
    result = query_distribution_build_results(
        version=version,
        build_numbers=build_numbers,
        components=components,
        status_filter=None  # Don't filter at query level for consistency
    )
    
    build_results = extract_build_results(result)
    
    # Apply status filter after extraction if needed
    if status_filter:
        build_results = [r for r in build_results if r.get('status') == status_filter]
    
    return [{
        'strategy': 'build_analysis',
        'build_results': build_results,
        'data_source': 'opensearch-distribution-build-results'
    }]

def execute_release_strategy(intent):
    """Execute release queries using release metrics."""
    version = intent['version']
    components = intent['components']
    
    result = query_release_readiness(
        version=version,
        components=components
    )
    
    return [{
        'strategy': 'release_readiness',
        'release_results': extract_release_results(result)
    }]

def query_integration_test_results(version, rc_number=None, build_numbers=None, components=None, status_filter=None, distribution="tar", architecture="x64"):
    """Comprehensive integration test results query."""
    query_body = {
        "size": 100,
        "sort": [{"build_start_time": {"order": "desc"}}],
        "_source": [
            "component", "component_build_result", "distribution_build_number",
            "rc_number", "platform", "architecture", "distribution",
            "test_report_manifest_yml", "integ_test_build_url", "build_start_time",
            "component_category", "qualifier"
        ],
        "query": {
            "bool": {
                "must": [
                    {"match_phrase": {"version": version}}
                ]
            }
        }
    }
    
    # Add status filter if specified
    if status_filter:
        query_body["query"]["bool"]["must"].append(
            {"match_phrase": {"component_build_result": status_filter}}
        )
    
    # Add RC number filter
    if rc_number:
        query_body["query"]["bool"]["must"].append(
            {"match_phrase": {"rc_number": str(rc_number)}}
        )
    
    # Add build numbers filter
    if build_numbers:
        query_body["query"]["bool"]["must"].append(
            {"terms": {"distribution_build_number": [str(bn) for bn in build_numbers]}}
        )
    
    # Add component filter with OpenSearch-Dashboards special handling
    if components:
        if "OpenSearch-Dashboards" in components:
            query_body["query"]["bool"]["must"].append({
                "bool": {
                    "should": [
                        {"regexp": {"component": "OpenSearch-Dashboards-ci-group-.*"}},
                        {"terms": {"component": components}}
                    ]
                }
            })
        else:
            query_body["query"]["bool"]["must"].append(
                {"terms": {"component": components}}
            )
    
    # Add platform/architecture filters
    if distribution:
        query_body["query"]["bool"]["must"].append(
            {"match_phrase": {"distribution": distribution}}
        )
    if architecture:
        query_body["query"]["bool"]["must"].append(
            {"match_phrase": {"architecture": architecture}}
        )
    
    # Remove collapse since component.keyword mapping doesn't exist
    # query_body["collapse"] = {"field": "component.keyword"}
    
    return opensearch_request('POST', '/opensearch-integration-test-results/_search', query_body)

def query_distribution_build_results(version, build_numbers=None, components=None, status_filter=None):
    """Query distribution build results."""
    query_body = {
        "size": 100,
        "sort": [{"build_start_time": {"order": "desc"}}],
        "_source": [
            "component", "component_build_result", "distribution_build_number",
            "build_start_time", "component_category", "qualifier", "version"
        ],
        "query": {
            "bool": {
                "must": [
                    {"match_phrase": {"version": version}}
                ]
            }
        }
    }
    
    if status_filter:
        query_body["query"]["bool"]["must"].append(
            {"match_phrase": {"component_build_result": status_filter}}
        )
    
    if build_numbers:
        query_body["query"]["bool"]["must"].append(
            {"terms": {"distribution_build_number": [str(bn) for bn in build_numbers]}}
        )
    
    if components:
        query_body["query"]["bool"]["must"].append(
            {"terms": {"component": components}}
        )
    
    return opensearch_request('POST', '/opensearch-distribution-build-results/_search', query_body)

def query_release_readiness(version, components=None):
    """Query release readiness metrics."""
    query_body = {
        "size": 100,
        "sort": [{"current_date": {"order": "desc"}}],
        "_source": [
            "component", "repository", "version", "current_date",
            "release_state", "release_branch", "release_issue_exists",
            "release_notes", "version_increment", "release_owners",
            "issues_open", "issues_closed", "pulls_open", "pulls_closed"
        ],
        "query": {
            "bool": {
                "must": [
                    {"match_phrase": {"version": version}}
                ]
            }
        }
    }
    
    if components:
        query_body["query"]["bool"]["must"].append(
            {"terms": {"component": components}}
        )
    
    return opensearch_request('POST', '/opensearch_release_metrics/_search', query_body)

def resolve_components_from_build_numbers(version, build_numbers):
    """Resolve components from build numbers."""
    query_body = {
        "size": 1000,
        "_source": ["component", "distribution_build_number"],
        "query": {
            "bool": {
                "must": [
                    {"match_phrase": {"version": version}},
                    {"terms": {"distribution_build_number": [str(bn) for bn in build_numbers]}}
                ]
            }
        }
    }
    
    result = opensearch_request('POST', '/opensearch-distribution-build-results/_search', query_body)
    
    build_component_map = {}
    for hit in result.get('hits', {}).get('hits', []):
        source = hit['_source']
        build_num = source['distribution_build_number']
        component = source['component']
        
        if build_num not in build_component_map:
            build_component_map[build_num] = []
        if component not in build_component_map[build_num]:
            build_component_map[build_num].append(component)
    
    return build_component_map

def get_rc_distribution_build_number(version, rc_number, component_name="OpenSearch"):
    """Get build number for RC."""
    query_body = {
        "_source": "distribution_build_number",
        "sort": [{"distribution_build_number": {"order": "desc"}}],
        "size": 1,
        "query": {
            "bool": {
                "filter": [
                    {"match_phrase": {"component": component_name}},
                    {"match_phrase": {"rc": "true"}},
                    {"match_phrase": {"version": version}},
                    {"match_phrase": {"rc_number": str(rc_number)}}
                ]
            }
        }
    }
    
    result = opensearch_request('POST', '/opensearch-integration-test-results/_search', query_body)
    hits = result.get('hits', {}).get('hits', [])
    
    if hits:
        return hits[0]['_source']['distribution_build_number']
    return None

def extract_test_results(opensearch_result):
    """Extract comprehensive test result information."""
    results = []
    hits = opensearch_result.get('hits', {}).get('hits', [])
    
    for hit in hits:
        source = hit['_source']
        results.append({
            'component': source.get('component'),
            'status': source.get('component_build_result'),
            'build_number': source.get('distribution_build_number'),
            'rc_number': source.get('rc_number'),
            'platform': source.get('platform'),
            'architecture': source.get('architecture'),
            'distribution': source.get('distribution'),
            'test_report': source.get('test_report_manifest_yml'),
            'build_url': source.get('integ_test_build_url'),
            'timestamp': source.get('build_start_time'),
            'category': source.get('component_category'),
            'qualifier': source.get('qualifier')
        })
    
    return results

def extract_build_results(opensearch_result):
    """Extract build result information."""
    results = []
    hits = opensearch_result.get('hits', {}).get('hits', [])
    
    for hit in hits:
        source = hit['_source']
        results.append({
            'component': source.get('component'),
            'status': source.get('component_build_result'),
            'build_number': source.get('distribution_build_number'),
            'timestamp': source.get('build_start_time'),
            'category': source.get('component_category'),
            'qualifier': source.get('qualifier'),
            'version': source.get('version')
        })
    
    return results

def extract_release_results(opensearch_result):
    """Extract release readiness information."""
    results = []
    hits = opensearch_result.get('hits', {}).get('hits', [])
    
    for hit in hits:
        source = hit['_source']
        
        # Calculate readiness score
        readiness_score = 0
        if source.get('release_issue_exists'): readiness_score += 1
        if source.get('release_notes'): readiness_score += 1
        if source.get('version_increment'): readiness_score += 1
        if source.get('release_state') == 'closed' or source.get('release_branch'): readiness_score += 1
        
        results.append({
            'component': source.get('component'),
            'repository': source.get('repository'),
            'version': source.get('version'),
            'release_state': source.get('release_state'),
            'release_branch': source.get('release_branch'),
            'release_issue_exists': source.get('release_issue_exists'),
            'release_notes': source.get('release_notes'),
            'version_increment': source.get('version_increment'),
            'release_owners': source.get('release_owners', []),
            'issues_open': source.get('issues_open'),
            'issues_closed': source.get('issues_closed'),
            'pulls_open': source.get('pulls_open'),
            'pulls_closed': source.get('pulls_closed'),
            'readiness_score': readiness_score,
            'is_ready': readiness_score >= 3,
            'timestamp': source.get('current_date')
        })
    
    return results

def generate_integration_summary(results):
    """Generate summary for integration test results."""
    all_results = []
    for result_set in results:
        all_results.extend(result_set.get('test_results', []))
    
    if not all_results:
        return {'total': 0, 'failed': 0, 'passed': 0, 'success_rate': 0}
    
    failed = len([r for r in all_results if r.get('status') == 'failed'])
    passed = len([r for r in all_results if r.get('status') == 'passed'])
    total = len(all_results)
    
    return {
        'total': total,
        'failed': failed,
        'passed': passed,
        'success_rate': round((passed / total * 100), 1) if total > 0 else 0,
        'unique_components': len(set(r.get('component') for r in all_results if r.get('component')))
    }

def generate_build_summary(results):
    """Generate summary for build results."""
    all_results = []
    for result_set in results:
        all_results.extend(result_set.get('build_results', []))
    
    if not all_results:
        return {'total': 0, 'failed': 0, 'successful': 0, 'success_rate': 0}
    
    failed = len([r for r in all_results if r.get('status') == 'failed'])
    successful = len([r for r in all_results if r.get('status') == 'success'])
    total = len(all_results)
    
    # If we only have failed results (due to status filtering), note this
    filtered_query = len(set(r.get('status') for r in all_results)) == 1
    
    return {
        'total': total,
        'failed': failed,
        'successful': successful,
        'success_rate': round((successful / total * 100), 1) if total > 0 else 0,
        'unique_components': len(set(r.get('component') for r in all_results if r.get('component'))),
        'filtered_results': filtered_query,
        'note': 'Results filtered by status - success rate may not reflect overall build health' if filtered_query else None
    }

def generate_release_summary(results):
    """Generate summary for release results."""
    all_results = []
    for result_set in results:
        all_results.extend(result_set.get('release_results', []))
    
    if not all_results:
        return {'total': 0, 'ready': 0, 'not_ready': 0, 'readiness_rate': 0}
    
    ready = len([r for r in all_results if r.get('is_ready')])
    total = len(all_results)
    
    return {
        'total': total,
        'ready': ready,
        'not_ready': total - ready,
        'readiness_rate': round((ready / total * 100), 1) if total > 0 else 0,
        'unique_components': len(set(r.get('component') for r in all_results if r.get('component')))
    }

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

def handle_component_resolution(params):
    """Handle resolve_components_from_builds function."""
    try:
        version = params.get('version')
        build_numbers = params.get('build_numbers', [])
        
        if not version or not build_numbers:
            return {'error': 'Version and build_numbers are required for component resolution'}
        
        component_map = resolve_components_from_build_numbers(version, build_numbers)
        
        return {
            'function': 'resolve_components_from_builds',
            'version': version,
            'build_numbers': build_numbers,
            'component_mapping': component_map,
            'data_source': 'opensearch-distribution-build-results'
        }
        
    except Exception as e:
        logger.error(f"Component resolution failed: {e}")
        return {'error': str(e), 'type': 'component_resolution_error'}

def handle_rc_build_mapping(params):
    """Handle get_rc_build_mapping function."""
    try:
        version = params.get('version')
        rc_numbers = params.get('rc_numbers', [])
        component = params.get('component', 'OpenSearch')
        
        if not version or not rc_numbers:
            return {'error': 'Version and rc_numbers are required for RC build mapping'}
        
        rc_build_map = {}
        for rc_num in rc_numbers:
            build_num = get_rc_distribution_build_number(version, rc_num, component)
            rc_build_map[str(rc_num)] = build_num
        
        return {
            'function': 'get_rc_build_mapping',
            'version': version,
            'rc_numbers': rc_numbers,
            'component': component,
            'rc_build_mapping': rc_build_map,
            'data_source': 'opensearch-integration-test-results'
        }
        
    except Exception as e:
        logger.error(f"RC build mapping failed: {e}")
        return {'error': str(e), 'type': 'rc_mapping_error'}

def create_response(event, result):
    """Create a response in the format expected by the Bedrock agent."""
    action_group = event['actionGroup']
    function = event['function']
    
    # Add data source information to response if not present
    if isinstance(result, dict) and 'data_source' in result:
        result['response_footer'] = f"\n\n*Data retrieved from {result['data_source']} index*"
    
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