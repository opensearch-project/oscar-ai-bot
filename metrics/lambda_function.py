#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
AWS Lambda handler for OSCAR multi-agent metrics system.
Optimized for VPC deployment with OpenSearch connectivity.
"""

import json
import logging
import os
from typing import Dict, Any

from config import Config
from opensearch_client import OpenSearchClient
from metrics_service import MetricsService

# Configure logging
logger = logging.getLogger(__name__)

# Global instances for Lambda container reuse
config = None
opensearch_client = None
metrics_service = None


def initialize():
    """Initialize global instances for Lambda container reuse."""
    global config, opensearch_client, metrics_service
    
    if config is None:
        logger.info("Creating config instance")
        config = Config()
        logger.info(f"Initialized config for agent type: {config.agent_type}")
        
    if opensearch_client is None:
        logger.info("Creating OpenSearch client - potential timeout point")
        opensearch_client = OpenSearchClient(config)
        logger.info("OpenSearch client created successfully")
        
    if metrics_service is None:
        logger.info("Creating metrics service")
        metrics_service = MetricsService(opensearch_client)
        logger.info("Metrics service created successfully")


def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    AWS Lambda handler for Bedrock agent function calls.
    
    Expected event format from Bedrock:
    {
        "function": "function_name",
        "parameters": [
            {"name": "param1", "value": "value1"},
            {"name": "param2", "value": "value2"}
        ]
    }
    """
    try:
        logger.info("Lambda handler started")
        # Initialize components
        initialize()
        logger.info("Initialization completed")
        
        logger.info(f"Processing request for agent type: {config.agent_type}")
        logger.debug(f"Event: {json.dumps(event, default=str)}")
        
        # Handle mock mode for testing
        if config.mock_mode:
            logger.info("Using mock mode for response")
            return handle_mock_response(event)
        
        # Try to proceed with OpenSearch queries even if connection test fails
        # The connection test might fail due to permissions, but actual queries might work
        try:
            connection_ok = opensearch_client.test_connection()
            if connection_ok:
                logger.info("OpenSearch connectivity test passed")
            else:
                logger.warning("OpenSearch connectivity test failed, but proceeding with query attempt")
        except Exception as conn_e:
            logger.warning(f"OpenSearch connection test error, but proceeding with query attempt: {conn_e}")
        
        # Extract function name and parameters
        function_name = event.get('function', '')
        parameters = event.get('parameters', [])
        
        # Convert parameters to dict
        params = {}
        for param in parameters:
            if isinstance(param, dict) and 'name' in param and 'value' in param:
                params[param['name']] = param['value']
        
        logger.info(f"Function: {function_name}, Parameters: {params}")
        
        # Route to appropriate handler based on agent type
        result = route_request(config.agent_type, function_name, params)
        
        # Create Bedrock response
        response = create_bedrock_response(result)
        
        logger.info("Request processed successfully")
        return response
        
    except Exception as e:
        logger.error(f"Lambda handler error: {str(e)}", exc_info=True)
        return create_error_response(str(e))


def route_request(agent_type: str, function_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Route request to appropriate metrics handler based on agent type."""
    
    if agent_type == 'test-metrics' or agent_type == 'test':
        return handle_test_metrics(function_name, params)
    elif agent_type == 'build-metrics' or agent_type == 'build':
        return handle_build_metrics(function_name, params)
    elif agent_type == 'release-metrics' or agent_type == 'release':
        return handle_release_metrics(function_name, params)
    elif agent_type == 'deployment-metrics' or agent_type == 'deployment':
        return handle_deployment_metrics(function_name, params)
    else:
        return {'error': f'Unknown agent type: {agent_type}', 'type': 'routing_error'}


def handle_test_metrics(function_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle test metrics function calls."""
    if function_name == 'get_test_metrics' or not function_name:
        return metrics_service.get_test_metrics(
            metric_type=params.get('metric_type', 'execution'),
            time_range=params.get('time_range', '7d'),
            project_filter=params.get('project_filter')
        )
    else:
        return {'error': f'Unknown test metrics function: {function_name}', 'type': 'function_error'}


def handle_build_metrics(function_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle build metrics function calls."""
    if function_name == 'get_build_metrics' or not function_name:
        return metrics_service.get_build_metrics(
            metric_type=params.get('metric_type', 'performance'),
            time_range=params.get('time_range', '7d'),
            branch_filter=params.get('branch_filter')
        )
    elif function_name == 'test_multiple_queries':
        return opensearch_client.test_multiple_queries()
    elif function_name == 'test_role_only':
        return opensearch_client.test_role_assumption_only()
    else:
        return {'error': f'Unknown build metrics function: {function_name}', 'type': 'function_error'}


def handle_release_metrics(function_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle release metrics function calls."""
    if function_name == 'get_release_metrics' or not function_name:
        return metrics_service.get_release_metrics(
            metric_type=params.get('metric_type', 'frequency'),
            time_range=params.get('time_range', '30d'),
            environment_filter=params.get('environment_filter')
        )
    else:
        return {'error': f'Unknown release metrics function: {function_name}', 'type': 'function_error'}


def handle_deployment_metrics(function_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle deployment metrics function calls."""
    if function_name == 'get_deployment_metrics' or not function_name:
        return metrics_service.get_deployment_metrics(
            metric_type=params.get('metric_type', 'performance'),
            time_range=params.get('time_range', '7d'),
            service_filter=params.get('service_filter')
        )
    else:
        return {'error': f'Unknown deployment metrics function: {function_name}', 'type': 'function_error'}


def handle_mock_response(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle mock responses for testing without OpenSearch connectivity."""
    agent_type = config.agent_type
    
    mock_data = {
        'test-metrics': {
            'type': 'test_metrics',
            'metric_type': 'execution',
            'time_range': '7d',
            'summary': {
                'total_failures': 42,
                'repositories_affected': 3,
                'top_failing_class': 'MockTestClass'
            },
            'top_failing_classes': [
                {'class_name': 'MockTestClass', 'failure_count': 15, 'percentage': 35.7}
            ],
            'mock_mode': True
        },
        'build-metrics': {
            'type': 'build_metrics',
            'metric_type': 'performance',
            'time_range': '7d',
            'summary': {
                'total_builds': 25,
                'active_builds': 20,
                'success_rate': 80.0
            },
            'mock_mode': True
        },
        'release-metrics': {
            'type': 'release_metrics',
            'metric_type': 'frequency',
            'time_range': '30d',
            'summary': {
                'total_releases': 10,
                'ready_components': 8,
                'overall_readiness': 80.0
            },
            'mock_mode': True
        },
        'deployment-metrics': {
            'type': 'deployment_metrics',
            'metric_type': 'performance',
            'time_range': '7d',
            'summary': {
                'total_deployments': 15,
                'active_deployments': 12,
                'overall_health': 80.0
            },
            'mock_mode': True
        }
    }
    
    # Normalize agent type
    normalized_type = agent_type.replace('-metrics', '').replace('-', '-')
    if not normalized_type.endswith('-metrics'):
        normalized_type += '-metrics'
    
    result = mock_data.get(normalized_type, {
        'type': 'mock_data', 
        'agent_type': agent_type,
        'mock_mode': True
    })
    
    return create_bedrock_response(result)


def create_bedrock_response(result: Dict[str, Any]) -> Dict[str, Any]:
    """Create properly formatted Bedrock response."""
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


def create_error_response(error_message: str) -> Dict[str, Any]:
    """Create error response for Bedrock."""
    error_result = {
        'error': error_message,
        'type': 'lambda_error',
        'agent_type': config.agent_type if config else 'unknown'
    }
    
    return create_bedrock_response(error_result)