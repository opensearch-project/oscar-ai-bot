#!/usr/bin/env python
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Lambda stack deployment script for OSCAR CDK automation.

This script provides a focused interface to deploy only the Lambda stack.
"""

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

def setup_logging(verbose: bool = False) -> None:
    """Set up logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

def check_dependency_stacks() -> bool:
    """Check if dependency stacks are deployed and ready."""
    logger = logging.getLogger(__name__)
    
    try:
        cf = boto3.client('cloudformation')
        
        # Required dependency stacks for Lambda stack
        dependency_stacks = [
            'OscarPermissionsStack',
            'OscarSecretsStack'
        ]
        
        # Check each dependency
        for stack_name in dependency_stacks:
            try:
                response = cf.describe_stacks(StackName=stack_name)
                stack = response['Stacks'][0]
                status = stack['StackStatus']
                
                if status not in ['CREATE_COMPLETE', 'UPDATE_COMPLETE']:
                    logger.error(f"Dependency stack {stack_name} is not ready: {status}")
                    return False
                
                logger.info(f"Dependency stack {stack_name}: {status}")
                
            except ClientError as e:
                if e.response['Error']['Code'] == 'ValidationError':
                    logger.error(f"Dependency stack {stack_name} does not exist")
                    return False
                raise
        
        logger.info("All dependency stacks are ready")
        return True
        
    except Exception as e:
        logger.error(f"Failed to check dependency stacks: {e}")
        return False

def deploy_lambda_stack() -> bool:
    """Deploy the Lambda stack."""
    logger = logging.getLogger(__name__)
    
    try:
        # Change to CDK directory
        original_cwd = os.getcwd()
        cdk_dir = Path(__file__).parent.parent
        os.chdir(cdk_dir)
        
        logger.info("Deploying Lambda stack...")
        
        # Run CDK deploy for Lambda stack
        cmd = [
            'cdk', 'deploy', 'OscarLambdaStack',
            '--require-approval', 'never',
            '--progress', 'events'
        ]
        
        result = subprocess.run(cmd, timeout=1800)  # 30 minute timeout
        
        if result.returncode != 0:
            logger.error("Lambda stack deployment failed")
            return False
        
        logger.info("Lambda stack deployed successfully")
        return True
        
    except subprocess.TimeoutExpired:
        logger.error("Lambda stack deployment timed out")
        return False
    except Exception as e:
        logger.error(f"Lambda stack deployment failed: {e}")
        return False
    finally:
        try:
            os.chdir(original_cwd)
        except:
            pass

def main():
    """Main entry point for Lambda stack deployment."""
    parser = argparse.ArgumentParser(
        description='Deploy OSCAR Lambda stack with CDK'
    )
    parser.add_argument(
        '--skip-dependencies',
        action='store_true',
        help='Skip dependency stack validation'
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
    
    try:
        logger.info("🚀 Starting OSCAR Lambda stack deployment")
        
        # Check dependency stacks
        if not args.skip_dependencies:
            if not check_dependency_stacks():
                logger.error("❌ Dependency stacks are not ready")
                logger.info("Please deploy the following stacks first:")
                logger.info("  - OscarPermissionsStack")
                logger.info("  - OscarSecretsStack")
                sys.exit(1)
        
        # Deploy Lambda stack
        success = deploy_lambda_stack()
        
        if success:
            logger.info("🎉 Lambda stack deployment completed successfully!")
        else:
            logger.error("❌ Lambda stack deployment failed!")
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        logger.info("🛑 Deployment interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Deployment failed with unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()