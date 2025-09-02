#!/usr/bin/env python
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Simple deployment validation script for OSCAR CDK infrastructure.

This script validates that the deployed infrastructure is working correctly.
"""

import argparse
import boto3
import json
import logging
import os
import sys
from typing import Dict, List, Optional

def setup_logging(verbose: bool = False) -> None:
    """Set up logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

def validate_cloudformation_stacks(region: str) -> bool:
    """Validate CloudFormation stacks are deployed successfully."""
    logger = logging.getLogger(__name__)
    
    try:
        cf = boto3.client('cloudformation', region_name=region)
        
        # Expected OSCAR stacks
        expected_stacks = [
            'OscarPermissionsStack',
            'OscarSecretsStack',
            'OscarStorageStack',
            'OscarApiGatewayStack',
            'OscarKnowledgeBaseStack',
            'OscarLambdaStack',
            'OscarAgentsStack'
        ]
        
        # Get all stacks
        response = cf.list_stacks(
            StackStatusFilter=['CREATE_COMPLETE', 'UPDATE_COMPLETE']
        )
        
        deployed_stacks = [stack['StackName'] for stack in response['StackSummaries']]
        
        # Check each expected stack
        missing_stacks = []
        for stack_name in expected_stacks:
            if stack_name not in deployed_stacks:
                missing_stacks.append(stack_name)
        
        if missing_stacks:
            logger.error(f"Missing stacks: {', '.join(missing_stacks)}")
            return False
        
        logger.info(f"All {len(expected_stacks)} stacks deployed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Failed to validate CloudFormation stacks: {e}")
        return False

def validate_lambda_functions(region: str) -> bool:
    """Validate Lambda functions are deployed and active."""
    logger = logging.getLogger(__name__)
    
    try:
        lambda_client = boto3.client('lambda', region_name=region)
        
        # Get all Lambda functions
        response = lambda_client.list_functions()
        
        # Find OSCAR functions
        oscar_functions = [
            func for func in response['Functions']
            if 'oscar' in func['FunctionName'].lower()
        ]
        
        if not oscar_functions:
            logger.error("No OSCAR Lambda functions found")
            return False
        
        # Check each function
        inactive_functions = []
        for func in oscar_functions:
            if func['State'] != 'Active':
                inactive_functions.append(func['FunctionName'])
        
        if inactive_functions:
            logger.error(f"Inactive functions: {', '.join(inactive_functions)}")
            return False
        
        logger.info(f"All {len(oscar_functions)} Lambda functions are active")
        return True
        
    except Exception as e:
        logger.error(f"Failed to validate Lambda functions: {e}")
        return False

def validate_dynamodb_tables(region: str) -> bool:
    """Validate DynamoDB tables are created and active."""
    logger = logging.getLogger(__name__)
    
    try:
        dynamodb = boto3.client('dynamodb', region_name=region)
        
        # Expected tables
        expected_tables = ['oscar-agent-context', 'oscar-agent-sessions']
        
        # Check each table
        missing_tables = []
        inactive_tables = []
        
        for table_name in expected_tables:
            try:
                response = dynamodb.describe_table(TableName=table_name)
                table_status = response['Table']['TableStatus']
                
                if table_status != 'ACTIVE':
                    inactive_tables.append(f"{table_name} ({table_status})")
                    
            except dynamodb.exceptions.ResourceNotFoundException:
                missing_tables.append(table_name)
        
        if missing_tables:
            logger.error(f"Missing tables: {', '.join(missing_tables)}")
            return False
        
        if inactive_tables:
            logger.error(f"Inactive tables: {', '.join(inactive_tables)}")
            return False
        
        logger.info(f"All {len(expected_tables)} DynamoDB tables are active")
        return True
        
    except Exception as e:
        logger.error(f"Failed to validate DynamoDB tables: {e}")
        return False

def validate_bedrock_agents(region: str) -> bool:
    """Validate Bedrock agents are created."""
    logger = logging.getLogger(__name__)
    
    try:
        bedrock_agent = boto3.client('bedrock-agent', region_name=region)
        
        # Get all agents
        response = bedrock_agent.list_agents()
        
        # Find OSCAR agents
        oscar_agents = [
            agent for agent in response['agentSummaries']
            if 'oscar' in agent['agentName'].lower()
        ]
        
        if not oscar_agents:
            logger.warning("No OSCAR Bedrock agents found")
            return True  # Not critical for basic functionality
        
        logger.info(f"Found {len(oscar_agents)} Bedrock agents")
        return True
        
    except Exception as e:
        logger.warning(f"Could not validate Bedrock agents: {e}")
        return True  # Not critical for basic functionality

def main():
    """Main entry point for validation."""
    parser = argparse.ArgumentParser(
        description='Validate OSCAR CDK deployment'
    )
    parser.add_argument(
        '--region',
        default=os.environ.get('CDK_DEFAULT_REGION', 'us-east-1'),
        help='AWS region to validate'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    # Set up logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    logger.info(f"🔍 Validating OSCAR deployment in region: {args.region}")
    
    # Run validations
    validations = [
        ("CloudFormation Stacks", lambda: validate_cloudformation_stacks(args.region)),
        ("Lambda Functions", lambda: validate_lambda_functions(args.region)),
        ("DynamoDB Tables", lambda: validate_dynamodb_tables(args.region)),
        ("Bedrock Agents", lambda: validate_bedrock_agents(args.region))
    ]
    
    failed_validations = []
    
    for validation_name, validation_func in validations:
        logger.info(f"Validating {validation_name}...")
        try:
            if validation_func():
                logger.info(f"✅ {validation_name} validation passed")
            else:
                logger.error(f"❌ {validation_name} validation failed")
                failed_validations.append(validation_name)
        except Exception as e:
            logger.error(f"❌ {validation_name} validation error: {e}")
            failed_validations.append(validation_name)
    
    # Summary
    if failed_validations:
        logger.error(f"❌ Validation failed for: {', '.join(failed_validations)}")
        sys.exit(1)
    else:
        logger.info("🎉 All validations passed!")
        sys.exit(0)

if __name__ == "__main__":
    main()