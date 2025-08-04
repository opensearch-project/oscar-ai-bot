#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Minimal AWS Lambda handler for testing VPC connectivity.
This version doesn't require external network access.
"""

import json
import os
import logging

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Minimal Lambda handler for VPC connectivity testing.
    """
    try:
        # Get basic environment info
        agent_type = os.getenv('AGENT_TYPE', 'unknown')
        vpc_id = os.getenv('VPC_ID', 'unknown')
        mock_mode = os.getenv('MOCK_MODE', 'false')
        
        # Create response
        response_data = {
            'status': 'success',
            'message': 'Lambda function is working in VPC',
            'agent_type': agent_type,
            'vpc_id': vpc_id,
            'mock_mode': mock_mode,
            'event_received': event,
            'function_name': context.function_name if context else 'unknown',
            'aws_region': os.getenv('AWS_DEFAULT_REGION', 'unknown')
        }
        
        # Format for Bedrock if needed
        if 'function' in event:
            return {
                'response': {
                    'functionResponse': {
                        'responseBody': {
                            'TEXT': {
                                'body': json.dumps(response_data, indent=2)
                            }
                        }
                    }
                }
            }
        else:
            return response_data
            
    except Exception as e:
        error_response = {
            'status': 'error',
            'message': str(e),
            'type': 'lambda_error'
        }
        
        return error_response