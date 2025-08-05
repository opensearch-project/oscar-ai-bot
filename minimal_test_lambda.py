#!/usr/bin/env python3
"""Minimal test Lambda to isolate import issues."""

import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def lambda_handler(event, context):
    """Minimal Lambda handler to test basic functionality."""
    print("[DEBUG] Minimal Lambda - START")
    logger.info("[DEBUG] Minimal Lambda - START")
    
    try:
        print("[DEBUG] Testing basic imports...")
        logger.info("[DEBUG] Testing basic imports...")
        
        # Test 1: Basic imports
        import boto3
        print("[DEBUG] boto3 import - SUCCESS")
        
        # Test 2: Config import
        print("[DEBUG] About to import config...")
        from config import Config
        print("[DEBUG] config import - SUCCESS")
        
        # Test 3: Config creation
        print("[DEBUG] About to create Config...")
        config = Config()
        print("[DEBUG] Config creation - SUCCESS")
        
        # Test 4: Role manager import
        print("[DEBUG] About to import role_manager...")
        from role_manager import RoleManager
        print("[DEBUG] role_manager import - SUCCESS")
        
        # Test 5: OpenSearch client import
        print("[DEBUG] About to import opensearch_client...")
        from opensearch_client import OpenSearchClient
        print("[DEBUG] opensearch_client import - SUCCESS")
        
        print("[DEBUG] All imports successful!")
        logger.info("[DEBUG] All imports successful!")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'All imports successful',
                'agent_type': config.agent_type
            })
        }
        
    except Exception as e:
        print(f"[DEBUG] ERROR: {e}")
        logger.error(f"[DEBUG] ERROR: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e),
                'message': 'Import failed'
            })
        }