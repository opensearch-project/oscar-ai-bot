#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.

"""
Main Lambda Function for Metrics Processing.

This module provides the main Lambda handler for metrics processing,
using agentic search for natural language query handling.

Functions:
    lambda_handler: Main Lambda handler for metrics processing
"""

import json
import logging
import traceback
import uuid
from typing import Any, Dict

from config import config
# Pre-agentic fallback: uncomment if direct DSL routing is needed
# from helper_functions import (handle_component_resolution,
#                               handle_rc_build_mapping)
from metrics_handler import handle_metrics_query
from response_builder import create_response

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main Lambda handler for metrics processing.

    Routes requests to appropriate handlers:
    - query_metrics: Unified metrics query using agentic search
    - resolve_components_from_builds: Map build numbers to components
    - get_rc_build_mapping: Map RC numbers to build numbers

    Args:
        event: Lambda event containing the action group request
        context: Lambda context

    Returns:
        Response for the Bedrock agent
    """
    # Set the Lambda request ID for config caching
    if context and hasattr(context, 'aws_request_id'):
        config.set_request_id(context.aws_request_id)

    request_id = str(uuid.uuid4())[:8]

    try:
        logger.info(f"LAMBDA_HANDLER [{request_id}]: Starting Lambda execution")

        function_name = event.get('function', '')
        parameters = event.get('parameters', [])
        logger.info(f"LAMBDA_HANDLER [{request_id}]: Function: '{function_name}', Params count: {len(parameters)}")

        # Convert parameters to dict with proper array handling
        params = {}
        for param in parameters:
            if isinstance(param, dict) and 'name' in param and 'value' in param:
                value = param['value']
                param_name = param['name']

                # Handle array parameters that might be passed as JSON strings
                if isinstance(value, str) and value.startswith('[') and value.endswith(']'):
                    try:
                        value = json.loads(value)
                    except json.JSONDecodeError:
                        pass  # Keep as string if not valid JSON
                elif isinstance(value, str) and ',' in value and param_name in ['rc_numbers', 'build_numbers', 'components']:
                    # Handle comma-separated values for array parameters
                    value = [item.strip() for item in value.split(',') if item.strip()]
                elif isinstance(value, str) and param_name in ['rc_numbers', 'build_numbers', 'components'] and value.strip():
                    # Single value for array parameter - convert to list
                    value = [value.strip()]

                params[param_name] = value

        logger.info(f"LAMBDA_HANDLER [{request_id}]: Parsed params: {list(params.keys())}")

        # Route based on function name
        # --- Pre-agentic fallback: unreachable via Bedrock action group ---
        # if function_name == 'resolve_components_from_builds':
        #     logger.info(f"LAMBDA_HANDLER [{request_id}]: Routing to handle_component_resolution")
        #     result = handle_component_resolution(params)
        # elif function_name == 'get_rc_build_mapping':
        #     logger.info(f"LAMBDA_HANDLER [{request_id}]: Routing to handle_rc_build_mapping")
        #     result = handle_rc_build_mapping(params)

        if function_name == 'query_metrics' or function_name == '' or function_name is None:
            # Unified metrics query handler - routes all metrics queries through agentic search
            logger.info(f"LAMBDA_HANDLER [{request_id}]: Routing to handle_metrics_query (agentic search)")
            result = handle_metrics_query(params, request_id)

        else:
            result = {'error': f'Unknown function: {function_name}'}

        response = create_response(event, result)
        logger.info(f"LAMBDA_HANDLER [{request_id}]: Response created successfully")
        return response

    except Exception as e:
        logger.error(f"LAMBDA_HANDLER [{request_id}]: Exception occurred: {e}")
        logger.error(f"LAMBDA_HANDLER [{request_id}]: Stack trace: {traceback.format_exc()}")
        return create_response(event, {'error': str(e), 'type': 'lambda_error'})
