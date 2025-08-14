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
        
        # Convert parameters to dict with proper array handling
        params = {}
        for param in parameters:
            if isinstance(param, dict) and 'name' in param and 'value' in param:
                value = param['value']
                # Handle array parameters that might be passed as JSON strings
                if isinstance(value, str) and value.startswith('[') and value.endswith(']'):
                    try:
                        value = json.loads(value)
                    except json.JSONDecodeError:
                        pass  # Keep as string if not valid JSON
                elif isinstance(value, str) and ',' in value and param['name'] in ['rc_numbers', 'build_numbers', 'components']:
                    # Handle comma-separated values for array parameters
                    value = [item.strip() for item in value.split(',')]
                params[param['name']] = value
        
        # Get agent_type from parameters - this should be passed by the supervisor agent
        agent_type = params.get('agent_type')
        
        # If agent_type is not provided, try to infer it from the function name
        if not agent_type:
            if function_name in ['get_integration_test_metrics', 'get_test_metrics', 'query_integration_test_failures']:
                agent_type = 'integration-test'
            elif function_name in ['get_build_metrics', 'resolve_components_from_builds']:
                agent_type = 'build-metrics'
            elif function_name in ['get_release_metrics', 'get_rc_build_mapping']:
                agent_type = 'release-metrics'
            else:
                agent_type = 'integration-test'  # Default fallback
                logger.warning(f"Could not determine agent_type from function '{function_name}', using default: {agent_type}")
        
        logger.info(f"Function: {function_name}, Agent: {agent_type}")
        
        # Route based on function name
        if function_name == 'test_basic':
            result = {'status': 'success', 'message': 'Enhanced Lambda function is working', 'agent_type': agent_type}
        elif function_name == 'test_role_only':
            result = test_role_assumption()
        elif function_name == 'test_opensearch':
            result = test_opensearch_connectivity()
        #based on action group functions that get called, so names not matching concrete implementations here is fine
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
        
        # Validate and normalize parameters
        intent = validate_and_normalize_intent(intent)
        
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
        'integ_test_build_numbers': params.get('integ_test_build_numbers', []),
        'components': params.get('components', []),
        'status_filter': params.get('status_filter'),
        'distribution': params.get('distribution', 'tar'),
        'architecture': params.get('architecture', 'x64'),
        'platform': params.get('platform', 'linux'),
        'with_security': params.get('with_security'),
        'without_security': params.get('without_security'),
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
    
    # Extract build numbers - handle both distribution and integration test build numbers
    if not intent['build_numbers']:
        build_matches = re.findall(r'(?:distribution\s+)?build\s+numbers?\s+(\d+(?:,\s*\d+)*)', query_text, re.IGNORECASE)
        if build_matches:
            # Handle comma-separated build numbers
            build_nums = []
            for match in build_matches:
                nums = [int(n.strip()) for n in match.split(',')]
                build_nums.extend(nums)
            intent['build_numbers'] = build_nums
        else:
            # Fallback to individual build number pattern
            single_matches = re.findall(r'(?:distribution\s+)?build\s+(?:number\s+)?(\d+)', query_text, re.IGNORECASE)
            intent['build_numbers'] = [int(build) for build in single_matches]
    
    # Extract integration test build numbers
    if not intent['integ_test_build_numbers']:
        integ_matches = re.findall(r'(?:integ|integration)\s+test\s+build\s+numbers?\s+(\d+(?:,\s*\d+)*)', query_text, re.IGNORECASE)
        if integ_matches:
            integ_nums = []
            for match in integ_matches:
                nums = [int(n.strip()) for n in match.split(',')]
                integ_nums.extend(nums)
            intent['integ_test_build_numbers'] = integ_nums
    
    # Extract components with improved Dashboards plugin detection
    if not intent['components']:
        if 'opensearch-dashboards' in query_lower or 'dashboards' in query_lower:
            intent['components'].append('OpenSearch-Dashboards')
        if 'opensearch' in query_lower and 'dashboards' not in query_lower:
            intent['components'].append('OpenSearch')
        
        # Generic detection for dashboards-related components
        if 'dashboards' in query_lower and 'opensearch-dashboards' not in query_lower:
            # This will be handled by the improved component filtering in the query
            pass
    
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
    
    # Extract platform/architecture/distribution
    if 'arm64' in query_lower:
        intent['architecture'] = 'arm64'
    if 'windows' in query_lower:
        intent['platform'] = 'windows'
    if 'rpm' in query_lower:
        intent['distribution'] = 'rpm'
    elif 'deb' in query_lower:
        intent['distribution'] = 'deb'
    
    # Extract security test filters
    if 'with security' in query_lower:
        if 'failed' in query_lower or 'fail' in query_lower:
            intent['with_security'] = 'fail'
        elif 'passed' in query_lower or 'pass' in query_lower:
            intent['with_security'] = 'pass'
    
    if 'without security' in query_lower:
        if 'failed' in query_lower or 'fail' in query_lower:
            intent['without_security'] = 'fail'
        elif 'passed' in query_lower or 'pass' in query_lower:
            intent['without_security'] = 'pass'
    
    return intent

def validate_and_normalize_intent(intent):
    """Validate and normalize intent parameters."""
    # Ensure arrays are properly formatted
    for array_field in ['rc_numbers', 'build_numbers', 'integ_test_build_numbers', 'components']:
        value = intent.get(array_field, [])
        if isinstance(value, str):
            # Handle comma-separated values or single values
            if ',' in value:
                intent[array_field] = [item.strip() for item in value.split(',') if item.strip()]
            elif value.strip():
                intent[array_field] = [value.strip()]
            else:
                intent[array_field] = []
        elif not isinstance(value, list):
            # Convert other types to list
            intent[array_field] = [value] if value is not None else []
    
    # Convert RC and build numbers to appropriate types
    if intent.get('rc_numbers'):
        intent['rc_numbers'] = [int(rc) if str(rc).isdigit() else rc for rc in intent['rc_numbers']]
    
    if intent.get('build_numbers'):
        intent['build_numbers'] = [str(bn) for bn in intent['build_numbers']]  # Keep as strings for OpenSearch
    
    if intent.get('integ_test_build_numbers'):
        intent['integ_test_build_numbers'] = [str(bn) for bn in intent['integ_test_build_numbers']]
    
    # Validate security test parameters
    for security_field in ['with_security', 'without_security']:
        value = intent.get(security_field)
        if value and value not in ['pass', 'fail']:
            intent[security_field] = None  # Invalid value, clear it
    
    return intent

def execute_integration_test_strategy(intent):
    """Execute integration test queries with multiple strategies."""
    version = intent['version']
    rc_numbers = intent['rc_numbers']
    build_numbers = intent['build_numbers']
    components = intent['components']
    status_filter = intent.get('status_filter')
    
    results = []
    
    # Strategy 1: RC-based queries (improved to handle multiple builds per RC)
    if rc_numbers:
        for rc_num in rc_numbers:
            if components:
                # For specific components, query directly without build number restriction
                result = query_integration_test_results(
                    version=version,
                    rc_number=rc_num,
                    components=components,
                    status_filter=status_filter,
                    distribution=intent.get('distribution'),
                    architecture=intent.get('architecture'),
                    platform=intent.get('platform'),
                    with_security=intent.get('with_security'),
                    without_security=intent.get('without_security')
                )
                results.append({
                    'strategy': 'rc_component_based',
                    'rc_number': rc_num,
                    'components': components,
                    'test_results': extract_test_results(result)
                })
            else:
                # Query all components for this RC
                result = query_integration_test_results(
                    version=version,
                    rc_number=rc_num,
                    status_filter=status_filter,
                    distribution=intent.get('distribution'),
                    architecture=intent.get('architecture'),
                    platform=intent.get('platform'),
                    with_security=intent.get('with_security'),
                    without_security=intent.get('without_security')
                )
                results.append({
                    'strategy': 'rc_based',
                    'rc_number': rc_num,
                    'test_results': extract_test_results(result)
                })
    
    # Strategy 2: Direct build number queries (improved component resolution)
    elif build_numbers:
        # Convert build numbers to strings for consistency
        build_numbers = [str(bn) for bn in build_numbers]
        
        if not components:
            # Try to resolve components, but don't fail if we can't
            try:
                component_map = resolve_components_from_build_numbers(version, build_numbers)
                all_components = []
                for comps in component_map.values():
                    all_components.extend(comps)
                components = list(set(all_components)) if all_components else None
            except Exception as e:
                logger.warning(f"Could not resolve components from build numbers: {e}")
                components = None
        
        result = query_integration_test_results(
            version=version,
            build_numbers=build_numbers,
            components=components,
            status_filter=status_filter,
            distribution=intent.get('distribution'),
            architecture=intent.get('architecture'),
            platform=intent.get('platform'),
            with_security=intent.get('with_security'),
            without_security=intent.get('without_security'),
            integ_test_build_numbers=intent.get('integ_test_build_numbers')
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
            architecture=intent.get('architecture'),
            platform=intent.get('platform'),
            with_security=intent.get('with_security'),
            without_security=intent.get('without_security')
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
            architecture=intent.get('architecture'),
            platform=intent.get('platform'),
            with_security=intent.get('with_security'),
            without_security=intent.get('without_security')
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

def query_integration_test_results(version, rc_number=None, build_numbers=None, components=None, status_filter=None, distribution="tar", architecture="x64", platform="linux", with_security=None, without_security=None, integ_test_build_numbers=None):
    """Comprehensive integration test results query."""
    query_body = {
        "size": 100,
        "sort": [{"build_start_time": {"order": "desc"}}],
        "_source": [
            "component", "component_repo", "component_repo_url", "component_build_result", 
            "distribution_build_number", "distribution_build_url", "integ_test_build_number", 
            "integ_test_build_url", "rc_number", "rc", "version", "qualifier",
            "platform", "architecture", "distribution", "component_category",
            "test_report_manifest_yml", "build_start_time",
            "with_security", "with_security_build_yml", "with_security_test_stdout", "with_security_test_stderr",
            "without_security", "without_security_build_yml", "without_security_test_stdout", "without_security_test_stderr"
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
    
    # Add component filter with improved Dashboards handling
    if components:
        should_clauses = []
        regular_components = []
        
        for component in components:
            if component == "OpenSearch-Dashboards":
                # Match ci-group patterns and any dashboards-related components
                should_clauses.extend([
                    {"regexp": {"component": "OpenSearch-Dashboards-ci-group-.*"}},
                    {"regexp": {"component": ".*[Dd]ashboards.*"}}
                ])
            elif "dashboards" in component.lower():
                # Handle any dashboards-related components generically
                should_clauses.append({"match_phrase": {"component": component}})
            else:
                regular_components.append(component)
        
        # Add regular components
        if regular_components:
            should_clauses.append({"terms": {"component": regular_components}})
        
        if should_clauses:
            if len(should_clauses) == 1:
                query_body["query"]["bool"]["must"].append(should_clauses[0])
            else:
                query_body["query"]["bool"]["must"].append({
                    "bool": {"should": should_clauses}
                })
    
    # Add platform/architecture/distribution filters
    if distribution:
        query_body["query"]["bool"]["must"].append(
            {"match_phrase": {"distribution": distribution}}
        )
    if architecture:
        query_body["query"]["bool"]["must"].append(
            {"match_phrase": {"architecture": architecture}}
        )
    if platform:
        query_body["query"]["bool"]["must"].append(
            {"match_phrase": {"platform": platform}}
        )
    
    # Add security test filters
    if with_security is not None:
        query_body["query"]["bool"]["must"].append(
            {"match_phrase": {"with_security": with_security}}
        )
    if without_security is not None:
        query_body["query"]["bool"]["must"].append(
            {"match_phrase": {"without_security": without_security}}
        )
    
    # Add integration test build number filter
    if integ_test_build_numbers:
        query_body["query"]["bool"]["must"].append(
            {"terms": {"integ_test_build_number": [int(bn) for bn in integ_test_build_numbers]}}
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
            "component", "component_repo", "component_repo_url", "component_ref",
            "version", "qualifier", "distribution_build_number", "distribution_build_url",
            "build_start_time", "rc", "rc_number", "component_category", "component_build_result"
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
    """Query release readiness metrics with comprehensive field coverage."""
    query_body = {
        "size": 100,
        "sort": [{"current_date": {"order": "desc"}}],
        "_source": [
            # Core identification fields
            "id", "component", "repository", "version", "release_version", "current_date",
            # Release state and branch information
            "release_state", "release_branch", "release_issue_exists", "release_issue",
            "release_notes", "version_increment", "release_owner_exists", "release_owners",
            # Issue and PR metrics
            "issues_open", "issues_closed", "pulls_open", "pulls_closed",
            # Autocut metrics
            "autocut_issues_open"
        ],
        "query": {
            "bool": {
                "must": [
                    {"match_phrase": {"version": version}}
                ]
            }
        }
    }
    
    # Use match_phrase for component filtering to avoid terms query issues
    if components:
        if len(components) == 1:
            query_body["query"]["bool"]["must"].append(
                {"match_phrase": {"component": components[0]}}
            )
        else:
            # Use should clause with multiple match_phrase for multiple components
            query_body["query"]["bool"]["must"].append({
                "bool": {
                    "should": [
                        {"match_phrase": {"component": comp}} for comp in components
                    ]
                }
            })
    
    return opensearch_request('POST', '/opensearch_release_metrics/_search', query_body)

def deduplicate_by_highest_build_number(results):
    """Keep only highest build number for each (component, version, rc_number) combination.
    
    Updated logic: Only deduplicate when we have exact duplicate components for the same RC.
    Different components can legitimately have different build numbers for the same RC.
    """
    if not results:
        return results
    
    # Group by (component, version, rc_number) - only deduplicate exact component matches
    groups = {}
    ungrouped = []
    
    for result in results:
        component = result.get('component')
        version = result.get('version')
        rc_number = result.get('rc_number')
        build_number = result.get('build_number')
        
        # Only deduplicate if we have all required fields and it's the exact same component
        if component and version and rc_number is not None and build_number is not None:
            key = (component, str(version), str(rc_number))
            try:
                build_num_int = int(build_number)
                if key not in groups:
                    groups[key] = result
                elif build_num_int > int(groups[key]['build_number']):
                    # Only replace if it's a higher build number for the SAME component
                    groups[key] = result
                # If same component/RC but lower build number, skip (keep existing)
            except (ValueError, TypeError):
                # If build_number is not convertible to int, keep as ungrouped
                ungrouped.append(result)
        else:
            # Keep results without proper grouping keys
            ungrouped.append(result)
    
    return list(groups.values()) + ungrouped

def deduplicate_release_results(results):
    """Keep only most recent entry for each (component, version) combination.
    
    Release readiness data does not contain RC/build numbers, only timestamps.
    We deduplicate by timestamp to avoid showing outdated release readiness states
    when newer evaluations exist for the same component/version.
    """
    if not results:
        return results
    
    # Group by (component, version)
    groups = {}
    ungrouped = []
    
    for result in results:
        component = result.get('component')
        version = result.get('version')
        timestamp = result.get('timestamp')
        
        # Only group if we have required fields
        if component and version:
            key = (component, str(version))
            # Use timestamp for comparison, fallback to keeping first if no timestamp
            if key not in groups:
                groups[key] = result
            elif timestamp:
                existing_timestamp = groups[key].get('timestamp')
                if not existing_timestamp or timestamp > existing_timestamp:
                    groups[key] = result
        else:
            # Keep results without proper grouping keys
            ungrouped.append(result)
    
    return list(groups.values()) + ungrouped

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

def get_rc_distribution_build_number(version, rc_number, component_name=None):
    """Get build numbers for RC. Returns all builds, not just highest.
    
    Args:
        version: Version string
        rc_number: RC number
        component_name: Optional component filter
        
    Returns:
        If component_name specified: list of build numbers for that component
        If no component_name: dict of component -> list of build numbers
    """
    query_body = {
        "_source": ["distribution_build_number", "component"],
        "sort": [{"distribution_build_number": {"order": "desc"}}],
        "size": 1000,  # Increased to get all builds
        "query": {
            "bool": {
                "must": [
                    {"match_phrase": {"version": version}},
                    {"match_phrase": {"rc_number": str(rc_number)}}
                ]
            }
        }
    }
    
    # Add component filter if specified
    if component_name:
        query_body["query"]["bool"]["must"].append(
            {"match_phrase": {"component": component_name}}
        )
    
    result = opensearch_request('POST', '/opensearch-integration-test-results/_search', query_body)
    hits = result.get('hits', {}).get('hits', [])
    
    if not hits:
        return [] if component_name else {}
    
    # If single component requested, return all build numbers for that component
    if component_name:
        build_numbers = []
        for hit in hits:
            build_num = hit['_source'].get('distribution_build_number')
            if build_num and build_num not in build_numbers:
                build_numbers.append(build_num)
        return build_numbers
    
    # If multiple components, return dict of component -> all build numbers
    component_builds = {}
    for hit in hits:
        source = hit['_source']
        component = source.get('component')
        build_num = source.get('distribution_build_number')
        
        if component and build_num:
            if component not in component_builds:
                component_builds[component] = []
            if build_num not in component_builds[component]:
                component_builds[component].append(build_num)
    
    return component_builds

def extract_test_results(opensearch_result):
    """Extract comprehensive test result information based on real data structure."""
    results = []
    hits = opensearch_result.get('hits', {}).get('hits', [])
    
    for hit in hits:
        source = hit['_source']
        
        # Determine overall test status based on with_security and without_security results
        with_security = source.get('with_security', '')
        without_security = source.get('without_security', '')
        component_build_result = source.get('component_build_result', '')
        
        # Calculate overall status - if either security test fails, overall is failed
        overall_status = 'passed'
        if component_build_result == 'failed':
            overall_status = 'failed'
        elif with_security == 'fail' or without_security == 'fail':
            overall_status = 'failed'
        elif with_security == 'pass' and without_security == 'pass':
            overall_status = 'passed'
        elif component_build_result in ['passed', 'success']:
            overall_status = 'passed'
        
        results.append({
            'component': source.get('component'),
            'component_repo': source.get('component_repo'),
            'component_repo_url': source.get('component_repo_url'),
            'status': overall_status,
            'component_build_result': component_build_result,
            'build_number': source.get('distribution_build_number'),
            'distribution_build_url': source.get('distribution_build_url'),
            'integ_test_build_number': source.get('integ_test_build_number'),
            'integ_test_build_url': source.get('integ_test_build_url'),
            'rc_number': source.get('rc_number'),
            'rc': source.get('rc'),
            'version': source.get('version'),
            'qualifier': source.get('qualifier'),
            'platform': source.get('platform'),
            'architecture': source.get('architecture'),
            'distribution': source.get('distribution'),
            'category': source.get('component_category'),
            'test_report': source.get('test_report_manifest_yml'),
            'timestamp': source.get('build_start_time'),
            # Security test details
            'with_security': with_security,
            'with_security_build_yml': source.get('with_security_build_yml'),
            'with_security_test_stdout': source.get('with_security_test_stdout'),
            'with_security_test_stderr': source.get('with_security_test_stderr'),
            'without_security': without_security,
            'without_security_build_yml': source.get('without_security_build_yml'),
            'without_security_test_stdout': source.get('without_security_test_stdout'),
            'without_security_test_stderr': source.get('without_security_test_stderr')
        })
    
    return deduplicate_by_highest_build_number(results)

def extract_build_results(opensearch_result):
    """Extract build result information."""
    results = []
    hits = opensearch_result.get('hits', {}).get('hits', [])
    
    for hit in hits:
        source = hit['_source']
        results.append({
            'component': source.get('component'),
            'component_repo': source.get('component_repo'),
            'component_repo_url': source.get('component_repo_url'),
            'component_ref': source.get('component_ref'),
            'version': source.get('version'),
            'qualifier': source.get('qualifier'),
            'distribution_build_number': source.get('distribution_build_number'),
            'distribution_build_url': source.get('distribution_build_url'),
            'build_start_time': source.get('build_start_time'),
            'rc': source.get('rc'),
            'rc_number': source.get('rc_number'),
            'component_category': source.get('component_category'),
            'component_build_result': source.get('component_build_result'),
            # Legacy fields for backward compatibility
            'status': source.get('component_build_result'),
            'build_number': source.get('distribution_build_number'),
            'timestamp': source.get('build_start_time'),
            'category': source.get('component_category')
        })
    
    return deduplicate_by_highest_build_number(results)

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
    
    # Apply deduplication to avoid duplicate component entries
    return deduplicate_release_results(results)

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
    """Generate comprehensive summary for release results."""
    all_results = []
    for result_set in results:
        all_results.extend(result_set.get('release_results', []))
    
    if not all_results:
        return {'total': 0, 'ready': 0, 'not_ready': 0, 'readiness_rate': 0}
    
    ready = len([r for r in all_results if r.get('is_ready')])
    total = len(all_results)
    
    # Calculate additional metrics
    components_with_issues = len([r for r in all_results if r.get('has_open_issues')])
    components_with_pulls = len([r for r in all_results if r.get('has_open_pulls')])
    components_with_autocut_issues = len([r for r in all_results if r.get('has_autocut_issues')])
    components_in_clean_state = len([r for r in all_results if r.get('clean_state')])
    
    # Calculate average readiness score
    avg_readiness_score = sum(r.get('readiness_score', 0) for r in all_results) / total if total > 0 else 0
    avg_readiness_percentage = sum(r.get('readiness_percentage', 0) for r in all_results) / total if total > 0 else 0
    
    # Count by release state
    release_states = {}
    for result in all_results:
        state = result.get('release_state', 'unknown')
        release_states[state] = release_states.get(state, 0) + 1
    
    return {
        'total': total,
        'ready': ready,
        'not_ready': total - ready,
        'readiness_rate': round((ready / total * 100), 1) if total > 0 else 0,
        'average_readiness_score': round(avg_readiness_score, 2),
        'average_readiness_percentage': round(avg_readiness_percentage, 1),
        'unique_components': len(set(r.get('component') for r in all_results if r.get('component'))),
        
        # Quality metrics
        'components_with_open_issues': components_with_issues,
        'components_with_open_pulls': components_with_pulls,
        'components_with_autocut_issues': components_with_autocut_issues,
        'components_in_clean_state': components_in_clean_state,
        'clean_state_percentage': round((components_in_clean_state / total * 100), 1) if total > 0 else 0,
        
        # Release state breakdown
        'release_states': release_states,
        
        # Total issue/PR counts
        'total_open_issues': sum(r.get('issues_open', 0) for r in all_results),
        'total_closed_issues': sum(r.get('issues_closed', 0) for r in all_results),
        'total_open_pulls': sum(r.get('pulls_open', 0) for r in all_results),
        'total_closed_pulls': sum(r.get('pulls_closed', 0) for r in all_results),
        'total_autocut_issues': sum(r.get('autocut_issues_open', 0) for r in all_results)
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
        component = params.get('component')  # Optional now
        
        if not version or not rc_numbers:
            return {'error': 'Version and rc_numbers are required for RC build mapping'}
        
        # Ensure rc_numbers is a list
        if not isinstance(rc_numbers, list):
            rc_numbers = [rc_numbers]
        
        rc_build_map = {}
        for rc_num in rc_numbers:
            build_data = get_rc_distribution_build_number(version, rc_num, component)
            rc_build_map[str(rc_num)] = build_data
        
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