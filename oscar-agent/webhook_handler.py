#!/usr/bin/env python3
import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """Minimal webhook handler for Slack URL verification."""
    logger.info(f"Received event: {json.dumps(event, default=str)}")
    
    try:
        # Handle direct invocation (for testing)
        if 'body' in event and not event.get('httpMethod'):
            # Direct Lambda invocation
            body_str = event['body']
            body = json.loads(body_str) if isinstance(body_str, str) else body_str
        else:
            # API Gateway invocation
            body_str = event.get('body', '{}')
            body = json.loads(body_str) if isinstance(body_str, str) else body_str
        
        logger.info(f"Parsed body: {json.dumps(body)}")
        
        # Handle URL verification
        if body and body.get('type') == 'url_verification':
            challenge = body.get('challenge')
            logger.info(f"URL verification challenge: {challenge}")
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'challenge': challenge})
            }
        
        # Handle other events
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Event received'})
        }
        
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }