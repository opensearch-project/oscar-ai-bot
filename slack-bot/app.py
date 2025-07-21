#!/usr/bin/env python
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.

"""
OSCAR - OpenSearch Conversational Automation for Release 

Lambda handler for Slack events.
"""

import logging
import json
from typing import Dict, Any, Optional
from slack_bolt import App
from slack_bolt.adapter.aws_lambda import SlackRequestHandler
from config import config
from storage import get_storage
from bedrock import get_knowledge_base
from slack_handler import SlackHandler

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Get Slack credentials
slack_token, slack_signing_secret = config.get_slack_credentials()

# Initialize Slack app
app = App(
    token=slack_token,
    signing_secret=slack_signing_secret,
    process_before_response=True
)

# Initialize storage and knowledge base
storage_instance = get_storage()
knowledge_base = get_knowledge_base()

# Initialize and register Slack handler
handler = SlackHandler(app, storage_instance, knowledge_base)
handler.register_handlers()

def lambda_handler(event: Dict[str, Any], context: Optional[object]) -> Dict[str, Any]:
    """
    AWS Lambda handler for Slack events.
    
    Args:
        event: The event dict from API Gateway
        context: The Lambda context object
        
    Returns:
        API Gateway response object
    """
    logger.info("Received event from API Gateway")
    
    # Handle URL verification challenge
    if event.get('body'):
        body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
        
        # Check if this is a URL verification challenge
        if body.get('type') == 'url_verification':
            logger.info("Received URL verification challenge")
            return {
                'statusCode': 200,
                'body': json.dumps({'challenge': body['challenge']})
            }
    
    # Handle regular Slack events
    slack_handler = SlackRequestHandler(app=app)
    return slack_handler.handle(event, context)