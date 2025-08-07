#!/usr/bin/env python3
import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """Minimal handler for debugging webhook issues."""
    logger.info(f"Received event: {json.dumps(event)}")
    
    # Extract body
    body = None
    if event.get('body'):
        try:
            body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
            logger.info(f"Parsed body: {json.dumps(body)}")
        except Exception as e:
            logger.error(f"Error parsing body: {e}")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Invalid JSON'})
            }
    
    # Handle URL verification
    if body and body.get('type') == 'url_verification':
        challenge = body.get('challenge')
        logger.info(f"URL verification challenge: {challenge}")
        
        response = {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'challenge': challenge})
        }
        logger.info(f"Returning response: {json.dumps(response)}")
        return response
    
    # Default response
    return {
        'statusCode': 200,
        'body': json.dumps({'message': 'OK'})
    }