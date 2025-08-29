#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Simple Environment Migration Script for OSCAR CDK Automation.

This script migrates .env file contents to AWS Secrets Manager.

Usage:
    python migrate_env_to_secrets.py --env-file .env --secret-name oscar-central-env
    python migrate_env_to_secrets.py --validate --secret-name oscar-central-env
"""

import argparse
import boto3
import logging
import os
import sys
from botocore.exceptions import ClientError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def migrate_env_to_secrets(env_file_path: str, secret_name: str, region: str = 'us-east-1') -> bool:
    """Migrate .env file contents to AWS Secrets Manager.
    
    Args:
        env_file_path: Path to the .env file
        secret_name: Name of the secret in AWS Secrets Manager
        region: AWS region
        
    Returns:
        True if migration successful, False otherwise
    """
    try:
        # Check if .env file exists
        if not os.path.exists(env_file_path):
            logger.error(f"Environment file not found: {env_file_path}")
            return False
        
        # Read the .env file content
        with open(env_file_path, 'r') as f:
            env_content = f.read()
        
        if not env_content.strip():
            logger.error(f"Environment file is empty: {env_file_path}")
            return False
        
        # Initialize AWS Secrets Manager client
        secrets_client = boto3.client('secretsmanager', region_name=region)
        
        # Check if secret already exists
        try:
            secrets_client.describe_secret(SecretId=secret_name)
            logger.info(f"Secret '{secret_name}' already exists. Updating...")
            
            # Update existing secret
            response = secrets_client.update_secret(
                SecretId=secret_name,
                SecretString=env_content,
                Description=f"OSCAR environment variables migrated from {env_file_path}"
            )
            logger.info(f"Successfully updated secret '{secret_name}'")
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                logger.info(f"Creating new secret '{secret_name}'...")
                
                # Create new secret
                response = secrets_client.create_secret(
                    Name=secret_name,
                    SecretString=env_content,
                    Description=f"OSCAR environment variables migrated from {env_file_path}"
                )
                logger.info(f"Successfully created secret '{secret_name}'")
            else:
                logger.error(f"AWS error: {e}")
                return False
        
        # Log the secret ARN for reference
        secret_arn = response.get('ARN', 'Unknown')
        logger.info(f"Secret ARN: {secret_arn}")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to migrate environment to secrets: {e}")
        return False
def validate_migration(secret_name: str, region: str = 'us-east-1') -> bool:
    """Validate that secrets migration is complete.
    
    Args:
        secret_name: Name of the secret in AWS Secrets Manager
        region: AWS region
        
    Returns:
        True if validation passes, False otherwise
    """
    try:
        logger.info(f"Validating migration for secret '{secret_name}'...")
        
        # Initialize AWS Secrets Manager client
        secrets_client = boto3.client('secretsmanager', region_name=region)
        
        # Retrieve secret from AWS
        response = secrets_client.get_secret_value(SecretId=secret_name)
        secret_content = response['SecretString']
        
        if not secret_content:
            logger.error(f"Secret '{secret_name}' is empty")
            return False
        
        # Count variables in secret
        var_count = 0
        for line in secret_content.splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                var_count += 1
        
        logger.info(f"Found {var_count} variables in secret")
        logger.info(f"Migration validation passed for secret '{secret_name}'")
        return True
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            logger.error(f"Secret '{secret_name}' not found")
        else:
            logger.error(f"AWS error validating migration: {e}")
        return False
    except Exception as e:
        logger.error(f"Failed to validate migration: {e}")
        return False


def main():
    """Main function for command-line usage."""
    parser = argparse.ArgumentParser(
        description='Migrate environment variables to AWS Secrets Manager'
    )
    parser.add_argument(
        '--env-file',
        default='.env',
        help='Path to .env file (default: .env)'
    )
    parser.add_argument(
        '--secret-name',
        default='oscar-central-env',
        help='Name of the secret in AWS Secrets Manager (default: oscar-central-env)'
    )
    parser.add_argument(
        '--region',
        default='us-east-1',
        help='AWS region (default: us-east-1)'
    )
    parser.add_argument(
        '--validate',
        action='store_true',
        help='Validate existing migration instead of migrating'
    )
    
    args = parser.parse_args()
    
    try:
        if args.validate:
            # Validate existing migration
            success = validate_migration(args.secret_name, args.region)
            if success:
                logger.info("✅ Migration validation passed")
                sys.exit(0)
            else:
                logger.error("❌ Migration validation failed")
                sys.exit(1)
        else:
            # Perform migration
            success = migrate_env_to_secrets(args.env_file, args.secret_name, args.region)
            if success:
                logger.info("✅ Environment migration completed successfully")
                
                # Automatically validate the migration
                logger.info("Validating migration...")
                if validate_migration(args.secret_name, args.region):
                    logger.info("✅ Migration validation passed")
                    sys.exit(0)
                else:
                    logger.error("❌ Migration validation failed")
                    sys.exit(1)
            else:
                logger.error("❌ Environment migration failed")
                sys.exit(1)
    
    except KeyboardInterrupt:
        logger.info("Migration cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Migration failed with error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()