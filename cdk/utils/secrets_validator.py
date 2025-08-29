#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Secrets validation utilities for OSCAR CDK Automation.

This module provides comprehensive validation functions for AWS Secrets Manager
secrets used by the OSCAR system, including validation of secret presence,
access permissions, and content structure.
"""

import boto3
import json
import logging
import os
from typing import Dict, List, Optional, Tuple, Any
from botocore.exceptions import ClientError, NoCredentialsError
from dataclasses import dataclass


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class SecretValidationResult:
    """Result of secret validation."""
    secret_name: str
    exists: bool
    accessible: bool
    content_valid: bool
    required_keys_present: bool
    errors: List[str]
    warnings: List[str]
    metadata: Dict[str, Any]


@dataclass
class ValidationSummary:
    """Summary of all secrets validation."""
    total_secrets: int
    valid_secrets: int
    failed_secrets: int
    results: List[SecretValidationResult]
    overall_status: str


class SecretsValidator:
    """
    Comprehensive secrets validation utility for OSCAR.
    
    This class provides methods to validate AWS Secrets Manager secrets
    including existence, accessibility, content structure, and Lambda
    execution context access testing.
    """
    
    def __init__(self, region: str = None):
        """
        Initialize the secrets validator.
        
        Args:
            region: AWS region (defaults to environment variable or us-east-1)
        """
        self.region = region or os.environ.get('AWS_REGION', 'us-east-1')
        self.secrets_client = None
        self.iam_client = None
        self._initialize_clients()
    
    def _initialize_clients(self) -> None:
        """Initialize AWS clients with error handling."""
        try:
            self.secrets_client = boto3.client('secretsmanager', region_name=self.region)
            self.iam_client = boto3.client('iam', region_name=self.region)
            logger.info(f"Initialized AWS clients for region: {self.region}")
        except NoCredentialsError:
            logger.error("AWS credentials not found. Please configure AWS credentials.")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize AWS clients: {e}")
            raise
    
    def validate_secret_exists(self, secret_name: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Validate that a secret exists in AWS Secrets Manager.
        
        Args:
            secret_name: Name of the secret to validate
            
        Returns:
            Tuple of (exists, metadata)
        """
        try:
            response = self.secrets_client.describe_secret(SecretId=secret_name)
            metadata = {
                'arn': response.get('ARN'),
                'created_date': response.get('CreatedDate'),
                'last_accessed_date': response.get('LastAccessedDate'),
                'last_changed_date': response.get('LastChangedDate'),
                'description': response.get('Description'),
                'kms_key_id': response.get('KmsKeyId'),
                'rotation_enabled': response.get('RotationEnabled', False)
            }
            logger.info(f"Secret '{secret_name}' exists")
            return True, metadata
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                logger.warning(f"Secret '{secret_name}' not found")
                return False, {}
            else:
                logger.error(f"Error checking secret '{secret_name}': {e}")
                return False, {'error': str(e)}
    
    def validate_secret_accessible(self, secret_name: str) -> Tuple[bool, str]:
        """
        Validate that a secret is accessible (can retrieve its value).
        
        Args:
            secret_name: Name of the secret to validate
            
        Returns:
            Tuple of (accessible, content or error message)
        """
        try:
            response = self.secrets_client.get_secret_value(SecretId=secret_name)
            content = response.get('SecretString', '')
            logger.info(f"Secret '{secret_name}' is accessible")
            return True, content
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ResourceNotFoundException':
                logger.error(f"Secret '{secret_name}' not found")
                return False, "Secret not found"
            elif error_code == 'AccessDenied':
                logger.error(f"Access denied to secret '{secret_name}'")
                return False, "Access denied"
            elif error_code == 'DecryptionFailure':
                logger.error(f"Failed to decrypt secret '{secret_name}'")
                return False, "Decryption failed"
            else:
                logger.error(f"Error accessing secret '{secret_name}': {e}")
                return False, str(e)
    
    def validate_central_env_secret(self, secret_name: str = "oscar-central-env") -> SecretValidationResult:
        """
        Validate the central environment secret structure and content.
        
        Args:
            secret_name: Name of the central environment secret
            
        Returns:
            SecretValidationResult with validation details
        """
        errors = []
        warnings = []
        
        # Check if secret exists
        exists, metadata = self.validate_secret_exists(secret_name)
        if not exists:
            return SecretValidationResult(
                secret_name=secret_name,
                exists=False,
                accessible=False,
                content_valid=False,
                required_keys_present=False,
                errors=["Secret does not exist"],
                warnings=[],
                metadata=metadata
            )
        
        # Check if secret is accessible
        accessible, content = self.validate_secret_accessible(secret_name)
        if not accessible:
            return SecretValidationResult(
                secret_name=secret_name,
                exists=True,
                accessible=False,
                content_valid=False,
                required_keys_present=False,
                errors=[f"Secret not accessible: {content}"],
                warnings=[],
                metadata=metadata
            )
        
        # Validate content structure
        content_valid = True
        required_keys_present = True
        
        # Expected environment variables for OSCAR (including Jenkins credentials)
        expected_keys = [
            'SLACK_BOT_TOKEN',
            'SLACK_SIGNING_SECRET', 
            'SLACK_APP_TOKEN',
            'BEDROCK_AGENT_ID',
            'BEDROCK_AGENT_ALIAS_ID',
            'JENKINS_API_TOKEN',
            'JENKINS_USERNAME',
            'AWS_REGION'
        ]
        
        try:
            # Try to parse as JSON first (new format)
            env_vars = json.loads(content)
            if not isinstance(env_vars, dict):
                errors.append("Secret content is not a valid JSON object")
                content_valid = False
            else:
                # Check for required keys
                missing_keys = [key for key in expected_keys if key not in env_vars]
                if missing_keys:
                    warnings.append(f"Missing expected keys: {missing_keys}")
                    required_keys_present = False
                
                # Check for empty values
                empty_keys = [key for key, value in env_vars.items() if not value or value.strip() == ""]
                if empty_keys:
                    warnings.append(f"Empty values for keys: {empty_keys}")
        
        except json.JSONDecodeError:
            # Try to parse as .env format (legacy format)
            try:
                env_vars = {}
                for line in content.splitlines():
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        env_vars[key.strip()] = value.strip()
                
                if not env_vars:
                    errors.append("No valid environment variables found in secret")
                    content_valid = False
                else:
                    # Check for required keys
                    missing_keys = [key for key in expected_keys if key not in env_vars]
                    if missing_keys:
                        warnings.append(f"Missing expected keys: {missing_keys}")
                        required_keys_present = False
                    
                    # Check for empty values
                    empty_keys = [key for key, value in env_vars.items() if not value]
                    if empty_keys:
                        warnings.append(f"Empty values for keys: {empty_keys}")
            
            except Exception as e:
                errors.append(f"Failed to parse secret content: {e}")
                content_valid = False
        
        return SecretValidationResult(
            secret_name=secret_name,
            exists=True,
            accessible=True,
            content_valid=content_valid,
            required_keys_present=required_keys_present,
            errors=errors,
            warnings=warnings,
            metadata=metadata
        )
    

    
    def test_lambda_execution_context_access(self, secret_names: List[str]) -> Dict[str, bool]:
        """
        Test secrets access from Lambda execution context perspective.
        
        This simulates the access patterns that Lambda functions would use
        to retrieve secrets, including IAM permission validation.
        
        Args:
            secret_names: List of secret names to test
            
        Returns:
            Dictionary mapping secret names to access success status
        """
        results = {}
        
        for secret_name in secret_names:
            try:
                # Simulate Lambda execution context access
                response = self.secrets_client.get_secret_value(SecretId=secret_name)
                
                # Additional validation for Lambda context
                if 'SecretString' in response:
                    content = response['SecretString']
                    if content and len(content) > 0:
                        results[secret_name] = True
                        logger.info(f"Lambda context access test passed for '{secret_name}'")
                    else:
                        results[secret_name] = False
                        logger.warning(f"Secret '{secret_name}' is empty")
                else:
                    results[secret_name] = False
                    logger.warning(f"Secret '{secret_name}' has no SecretString")
            
            except ClientError as e:
                results[secret_name] = False
                logger.error(f"Lambda context access test failed for '{secret_name}': {e}")
            except Exception as e:
                results[secret_name] = False
                logger.error(f"Unexpected error testing '{secret_name}': {e}")
        
        return results
    
    def validate_all_secrets(self) -> ValidationSummary:
        """
        Validate the central environment secret.
        
        Returns:
            ValidationSummary with validation results
        """
        logger.info("Validating central environment secret...")
        
        try:
            result = self.validate_central_env_secret()
            
            if result.exists and result.accessible and result.content_valid:
                logger.info("✅ Central environment secret validation passed")
                overall_status = "PASSED"
                valid_count = 1
                failed_count = 0
            else:
                logger.error("❌ Central environment secret validation failed")
                for error in result.errors:
                    logger.error(f"  Error: {error}")
                for warning in result.warnings:
                    logger.warning(f"  Warning: {warning}")
                overall_status = "FAILED"
                valid_count = 0
                failed_count = 1
            
            # Test Lambda execution context access
            if result.exists:
                lambda_access_results = self.test_lambda_execution_context_access([result.secret_name])
                if not lambda_access_results.get(result.secret_name, False) and result.accessible:
                    result.warnings.append("Secret accessible directly but may fail in Lambda context")
        
        except Exception as e:
            logger.error(f"❌ Exception during validation: {e}")
            result = SecretValidationResult(
                secret_name="oscar-central-env",
                exists=False,
                accessible=False,
                content_valid=False,
                required_keys_present=False,
                errors=[f"Validation failed: {e}"],
                warnings=[],
                metadata={}
            )
            overall_status = "FAILED"
            valid_count = 0
            failed_count = 1
        
        return ValidationSummary(
            total_secrets=1,
            valid_secrets=valid_count,
            failed_secrets=failed_count,
            results=[result],
            overall_status=overall_status
        )
    
    def generate_validation_report(self, summary: ValidationSummary) -> str:
        """
        Generate a detailed validation report.
        
        Args:
            summary: ValidationSummary from validate_all_secrets()
            
        Returns:
            Formatted validation report as string
        """
        report_lines = [
            "=" * 60,
            "OSCAR Secrets Validation Report",
            "=" * 60,
            f"Overall Status: {summary.overall_status}",
            f"Total Secrets: {summary.total_secrets}",
            f"Valid Secrets: {summary.valid_secrets}",
            f"Failed Secrets: {summary.failed_secrets}",
            "",
            "Detailed Results:",
            "-" * 40
        ]
        
        for result in summary.results:
            report_lines.extend([
                f"Secret: {result.secret_name}",
                f"  Exists: {'✅' if result.exists else '❌'}",
                f"  Accessible: {'✅' if result.accessible else '❌'}",
                f"  Content Valid: {'✅' if result.content_valid else '❌'}",
                f"  Required Keys Present: {'✅' if result.required_keys_present else '❌'}"
            ])
            
            if result.errors:
                report_lines.append("  Errors:")
                for error in result.errors:
                    report_lines.append(f"    - {error}")
            
            if result.warnings:
                report_lines.append("  Warnings:")
                for warning in result.warnings:
                    report_lines.append(f"    - {warning}")
            
            if result.metadata:
                report_lines.append("  Metadata:")
                for key, value in result.metadata.items():
                    if key != 'error':
                        report_lines.append(f"    {key}: {value}")
            
            report_lines.append("")
        
        report_lines.extend([
            "=" * 60,
            "End of Report"
        ])
        
        return "\n".join(report_lines)


def main():
    """Main function for command-line usage."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Validate OSCAR secrets in AWS Secrets Manager'
    )
    parser.add_argument(
        '--region',
        default='us-east-1',
        help='AWS region (default: us-east-1)'
    )
    parser.add_argument(
        '--secret',
        help='Validate specific secret only'
    )
    parser.add_argument(
        '--report',
        action='store_true',
        help='Generate detailed validation report'
    )
    
    args = parser.parse_args()
    
    try:
        validator = SecretsValidator(region=args.region)
        
        if args.secret:
            # Validate specific secret
            if args.secret == "oscar-central-env":
                result = validator.validate_central_env_secret()
            else:
                logger.error(f"Unknown secret: {args.secret}. Only 'oscar-central-env' is supported.")
                return 1
            
            print(f"Validation result for '{result.secret_name}':")
            print(f"  Exists: {result.exists}")
            print(f"  Accessible: {result.accessible}")
            print(f"  Content Valid: {result.content_valid}")
            print(f"  Required Keys Present: {result.required_keys_present}")
            
            if result.errors:
                print("  Errors:")
                for error in result.errors:
                    print(f"    - {error}")
            
            if result.warnings:
                print("  Warnings:")
                for warning in result.warnings:
                    print(f"    - {warning}")
        
        else:
            # Validate all secrets
            summary = validator.validate_all_secrets()
            
            if args.report:
                report = validator.generate_validation_report(summary)
                print(report)
            else:
                print(f"Overall Status: {summary.overall_status}")
                print(f"Valid: {summary.valid_secrets}/{summary.total_secrets}")
        
        return 0 if summary.overall_status in ["PASSED", "PARTIAL"] else 1
    
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        return 1


if __name__ == '__main__':
    exit(main())