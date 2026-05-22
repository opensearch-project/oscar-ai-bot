#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Security Advisories Lambda Function — Request Router.

Entry point for Bedrock action group invocations. Routes requests to the
appropriate handler based on the function name in the event:

- ``query_vulnerabilities`` → vulnerabilities_handler
- ``list_projects`` → projects_handler

All results are wrapped in the Bedrock response envelope via
``create_response()``.
"""

import logging
import traceback
import uuid
from typing import Any, Dict, List

from config import config
from constants import DASHBOARD_URL, LIMITED_ACCESS_MESSAGE
from projects_handler import handle_list_projects
from response_builder import create_response
from vulnerabilities_handler import handle_query_vulnerabilities

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

AVAILABLE_FUNCTIONS = ['query_vulnerabilities', 'list_projects']


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main Lambda handler for security advisories queries.

    Parses the Bedrock action group event, routes to the correct handler,
    and wraps the result in the Bedrock response envelope.

    Args:
        event: Bedrock action group event containing function name and parameters.
        context: Lambda context object.

    Returns:
        Bedrock-formatted response dict.
    """
    if context and hasattr(context, 'aws_request_id'):
        config.set_request_id(context.aws_request_id)

    request_id = str(uuid.uuid4())[:8]

    try:
        function_name = event.get('function', '')
        parameters = event.get('parameters', [])

        # Extract access_tier from session attributes (code-controlled, not LLM-set)
        session_attributes = event.get('sessionAttributes', {})
        access_tier = str(session_attributes.get('access_tier', 'limited')).lower().strip()

        params = _parse_parameters(parameters)
        params['_access_tier'] = access_tier  # underscore prefix = internal, not from LLM

        logger.info(
            f"[{request_id}] Function: {function_name}, Params: {params}, "
            f"Access tier: {access_tier}",
        )

        # Short-circuit ALL functions for limited-access requests at the router level
        if access_tier != 'privileged':
            logger.info(f"[{request_id}] Limited access — returning dashboard link only")
            result = {
                'status': 'success',
                'access_tier': 'limited',
                'message': LIMITED_ACCESS_MESSAGE,
                'dashboard_url': DASHBOARD_URL,
                'results': [],
            }
            return create_response(event, result)

        if function_name == 'query_vulnerabilities':
            result = handle_query_vulnerabilities(params, request_id)
        elif function_name == 'list_projects':
            result = handle_list_projects(request_id)
        else:
            result = {
                'status': 'error',
                'message': f'Unknown function: {function_name}',
                'available_functions': AVAILABLE_FUNCTIONS,
            }

        return create_response(event, result)

    except Exception as e:
        logger.error(f"[{request_id}] Error: {e}")
        logger.error(f"[{request_id}] Traceback: {traceback.format_exc()}")
        return create_response(
            event, {'status': 'error', 'message': str(e)},
        )


def _parse_parameters(parameters: List[Dict[str, Any]]) -> Dict[str, str]:
    """Convert Bedrock parameter list to a flat dict.

    Args:
        parameters: List of ``{"name": ..., "value": ...}`` dicts from Bedrock.

    Returns:
        Flat dict mapping parameter names to values.
    """
    params: Dict[str, str] = {}
    for param in parameters:
        if isinstance(param, dict) and 'name' in param and 'value' in param:
            params[param['name']] = param['value']
    return params
