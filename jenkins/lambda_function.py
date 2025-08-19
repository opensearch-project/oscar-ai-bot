#!/usr/bin/env python3
"""
Jenkins Lambda Function

AWS Lambda handler for Jenkins operations. This function provides the interface
between Bedrock agents and the Jenkins client, handling job triggers and status checks.
"""

import json
import logging
import os
from typing import Dict, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import Jenkins client components
from jenkins_client import JenkinsClient
from job_definitions import job_registry
from config import config

def extract_user_id(event: Dict[str, Any]) -> Optional[str]:
    """
    Extract user ID from the Lambda event.
    
    Args:
        event: Lambda event from Bedrock agent
        
    Returns:
        User ID string or None if not found
    """
    try:
        # Try to extract user ID from various possible locations in the event
        
        # Method 1: Check if user_id is in parameters
        parameters = event.get('parameters', [])
        for param in parameters:
            if isinstance(param, dict) and param.get('name') == 'user_id':
                return param.get('value')
        
        # Method 2: Check sessionAttributes (common in Bedrock events)
        session_attrs = event.get('sessionAttributes', {})
        if 'user_id' in session_attrs:
            return session_attrs['user_id']
        
        # Method 3: Check requestContext (API Gateway style)
        request_context = event.get('requestContext', {})
        if 'user_id' in request_context:
            return request_context['user_id']
        
        # Method 4: Check identity in requestContext
        identity = request_context.get('identity', {})
        if 'user' in identity:
            return identity['user']
        
        # Method 5: Check for Slack user ID in event metadata
        if 'slack_user_id' in event:
            return event['slack_user_id']
        
        # Method 6: Check agent context for user information
        agent_context = event.get('agentContext', {})
        if 'userId' in agent_context:
            return agent_context['userId']
        
        logger.warning("Could not extract user_id from event")
        return None
        
    except Exception as e:
        logger.error(f"Error extracting user_id from event: {e}")
        return None

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Main Lambda handler for Jenkins operations.
    
    Args:
        event: Lambda event containing function name and parameters
        context: Lambda context object
        
    Returns:
        Response dictionary with results
    """
    try:
        logger.info("🚀 JENKINS LAMBDA: Handler started")
        logger.info(f"🚀 JENKINS LAMBDA: Full event received: {json.dumps(event, indent=2)}")
        
        # Extract function and parameters from event
        function_name = event.get('function', '')
        parameters = event.get('parameters', [])
        
        logger.info(f"🚀 JENKINS LAMBDA: Extracted function_name='{function_name}'")
        logger.info(f"🚀 JENKINS LAMBDA: Raw parameters: {parameters}")
        
        # Convert parameters list to dictionary
        params = {}
        for param in parameters:
            if isinstance(param, dict) and 'name' in param and 'value' in param:
                params[param['name']] = param['value']
        
        logger.info(f"🚀 JENKINS LAMBDA: Converted parameters: {params}")
        
        # Extract user information for access control
        user_id = extract_user_id(event)
        logger.info(f"🔐 JENKINS LAMBDA: Extracted user_id: {user_id}")
        
        # Check user authorization - ALWAYS required for security
        if not config.is_user_authorized(user_id):
            logger.warning(f"❌ JENKINS LAMBDA: Access denied for user: {user_id}")
            return create_response(event, {
                'status': 'error',
                'message': 'Access denied. You are not authorized to use Jenkins functions.',
                'error_type': 'authorization_error',
                'user_id': user_id
            })
        
        logger.info(f"✅ JENKINS LAMBDA: Access granted for user: {user_id}")
        
        
        logger.info(f"🚀 JENKINS LAMBDA: About to initialize JenkinsClient")
        
        # Initialize Jenkins client
        jenkins_client = JenkinsClient()
        logger.info(f"🚀 JENKINS LAMBDA: JenkinsClient initialized successfully")
        
        # Route to appropriate handler
        print(f"🔀 JENKINS LAMBDA: Routing to function '{function_name}'")
        logger.info(f"🔀 JENKINS LAMBDA: Routing to function '{function_name}'")
        
        if function_name == 'trigger_job':
            print("🔀 JENKINS LAMBDA: *** CALLING TRIGGER_JOB - THIS WILL EXECUTE THE JOB ***")
            logger.info("🔀 JENKINS LAMBDA: Routing to handle_trigger_job")
            result = handle_trigger_job(jenkins_client, params)
        elif function_name == 'test_connection':
            print("🔀 JENKINS LAMBDA: Routing to handle_test_connection")
            logger.info("🔀 JENKINS LAMBDA: Routing to handle_test_connection")
            result = handle_test_connection(jenkins_client)
        elif function_name == 'get_job_info':
            print("🔀 JENKINS LAMBDA: *** CALLING GET_JOB_INFO - INFORMATION ONLY ***")
            logger.info("🔀 JENKINS LAMBDA: Routing to handle_get_job_info")
            result = handle_get_job_info(jenkins_client, params)
        elif function_name == 'list_jobs':
            logger.info("🔀 JENKINS LAMBDA: Routing to handle_list_jobs")
            result = handle_list_jobs(jenkins_client)
        else:
            logger.error(f"❌ JENKINS LAMBDA: Unknown function '{function_name}'")
            result = {
                'status': 'error',
                'message': f'Unknown function: {function_name}',
                'available_functions': [
                    'trigger_job', 'test_connection', 
                    'get_job_info', 'list_jobs'
                ]
            }
        
        logger.info(f"✅ JENKINS LAMBDA: Function '{function_name}' completed with status: {result.get('status', 'unknown')}")
        
        return create_response(event, result)
        
    except Exception as e:
        logger.error(f"Lambda handler error: {e}", exc_info=True)
        return create_response(event, {
            'status': 'error',
            'message': 'Internal Lambda error',
            'error': str(e),
            'type': 'lambda_error'
        })

def handle_trigger_job(jenkins_client: JenkinsClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle generic job triggering.
    
    Args:
        jenkins_client: Jenkins client instance
        params: Parameters including job_name and individual job parameters
        
    Returns:
        Job trigger result
    """
    job_name = params.get('job_name')
    logger.info(f"🚀 JENKINS LAMBDA: handle_trigger_job called with job_name='{job_name}'")
    logger.info(f"🚀 JENKINS LAMBDA: This function WILL make HTTP requests to Jenkins")
    
    if not job_name:
        logger.error("❌ JENKINS LAMBDA: Missing job_name parameter")
        return {
            'status': 'error',
            'message': 'job_name parameter is required for trigger_job function',
            'available_jobs': job_registry.list_jobs()
        }
    
    # Extract job parameters (all params except job_name)
    job_params = {k: v for k, v in params.items() if k != 'job_name'}
    logger.info(f"🚀 JENKINS LAMBDA: Extracted job parameters: {job_params}")
    
    # Handle legacy job_parameters JSON string if provided
    job_parameters_json = params.get('job_parameters')
    if job_parameters_json:
        logger.info(f"🚀 JENKINS LAMBDA: Found legacy job_parameters JSON: {job_parameters_json}")
        try:
            import json
            parsed_params = json.loads(job_parameters_json)
            job_params.update(parsed_params)
            logger.info(f"🚀 JENKINS LAMBDA: Updated job_params with JSON: {job_params}")
        except json.JSONDecodeError:
            logger.error("❌ JENKINS LAMBDA: Invalid JSON in job_parameters field")
            return {
                'status': 'error',
                'message': 'Invalid JSON in job_parameters field',
                'job_name': job_name
            }
    
    logger.info(f"🚀 JENKINS LAMBDA: About to call jenkins_client.trigger_job with job_name='{job_name}', params={job_params}")
    result = jenkins_client.trigger_job(job_name, job_params)
    logger.info(f"🚀 JENKINS LAMBDA: trigger_job returned status: {result.get('status', 'unknown')}")
    return result

def handle_docker_scan(jenkins_client: JenkinsClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle Docker scan job (convenience function).
    
    Args:
        jenkins_client: Jenkins client instance
        params: Parameters including image_name
        
    Returns:
        Docker scan job result
    """
    image_name = params.get('image_name')
    if not image_name:
        return {
            'status': 'error',
            'message': 'image_name parameter is required for docker_scan function',
            'example': 'image_name=alpine:3.19'
        }
    
    # Map to the correct parameter name for the Jenkins job
    job_params = {'IMAGE_FULL_NAME': image_name}
    
    result = jenkins_client.trigger_job('docker-scan', job_params)
    
    # Add convenience information for Docker scan
    if result.get('status') == 'success':
        result['scan_info'] = {
            'image_scanned': image_name,
            'scan_type': 'security_scan',
            'note': 'Scan results will be available in Jenkins once the job completes'
        }
    
    return result


def handle_test_connection(jenkins_client: JenkinsClient) -> Dict[str, Any]:
    """
    Handle Jenkins connection test.
    
    Args:
        jenkins_client: Jenkins client instance
        
    Returns:
        Connection test result
    """
    return jenkins_client.test_connection()

def handle_get_job_info(jenkins_client: JenkinsClient, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle getting job information.
    
    Args:
        jenkins_client: Jenkins client instance
        params: Parameters including job_name
        
    Returns:
        Job information result
    """
    job_name = params.get('job_name', 'docker-scan')  # Default to docker-scan
    logger.info(f"📋 JENKINS LAMBDA: handle_get_job_info called with job_name='{job_name}'")
    logger.info(f"📋 JENKINS LAMBDA: This function should NOT make HTTP requests to Jenkins")
    
    result = jenkins_client.get_job_info(job_name)
    logger.info(f"📋 JENKINS LAMBDA: get_job_info returned status: {result.get('status', 'unknown')}")
    return result

def handle_list_jobs(jenkins_client: JenkinsClient) -> Dict[str, Any]:
    """
    Handle listing available jobs.
    
    Args:
        jenkins_client: Jenkins client instance
        
    Returns:
        Available jobs list
    """
    return jenkins_client.list_available_jobs()

def create_response(event: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a standardized Lambda response for Bedrock action groups.
    
    Args:
        event: Original Lambda event
        result: Result dictionary to return
        
    Returns:
        Properly formatted Bedrock action group response
    """
    action_group = event.get('actionGroup', 'jenkins-operations')
    function = event.get('function', 'unknown')
    
    logger.info(f"Creating Bedrock response for action_group={action_group}, function={function}")
    
    # Serialize result to JSON string as required by Bedrock
    response_body_string = json.dumps(result, default=str)
    
    # Create the proper Bedrock action group response format
    bedrock_response = {
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
    
    logger.info(f"Created Bedrock response with body length: {len(response_body_string)}")
    return bedrock_response

# For local testing
if __name__ == "__main__":
    # Test event for central release promotion
    test_event = {
        "function": "trigger_job",
        "parameters": [
            {"name": "job_name", "value": "Pipeline central-release-promotion"},
            {"name": "RELEASE_VERSION", "value": "2.11.0"},
            {"name": "OPENSEARCH_RC_BUILD_NUMBER", "value": "123"},
            {"name": "OPENSEARCH_DASHBOARDS_RC_BUILD_NUMBER", "value": "456"}
        ]
    }
    
    class MockContext:
        pass
    
    result = lambda_handler(test_event, MockContext())
    print(json.dumps(result, indent=2))