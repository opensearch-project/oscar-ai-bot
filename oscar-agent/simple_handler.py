#!/usr/bin/env python
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Simple Lambda handler for testing basic functionality.
"""

import json
import logging
import os
from typing import Dict, Any, Optional

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event: Dict[str, Any], context: Optional[object]) -> Dict[str, Any]:
    """
    Simple AWS Lambda handler for testing.
    
    Args:
        event: The event dict from API Gateway
        context: The Lambda context object
        
    Returns:
        API Gateway response object
    """
    logger.info("Received event")
    logger.info(f"Event: {json.dumps(event)}")
    
    try:
        # Extract event body for processing
        body = None
        if event.get('body'):
            if isinstance(event['body'], str):
                body = json.loads(event['body'])
            else:
                body = event['body']
        
        logger.info(f"Parsed body: {body}")
        
        # Handle URL verification challenge immediately
        if body and body.get('type') == 'url_verification':
            logger.info("Received URL verification challenge")
            challenge = body.get('challenge')
            logger.info(f"Challenge: {challenge}")
            
            response = {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json'
                },
                'body': json.dumps({'challenge': challenge})
            }
            logger.info(f"Returning response: {response}")
            return response
        
        # For other events, return a simple acknowledgment
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json'
            },
            'body': json.dumps({'message': 'Event received'})
        }
        
    except Exception as e:
        logger.error(f"Error processing event: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json'
            },
            'body': json.dumps({'error': str(e)})
        }