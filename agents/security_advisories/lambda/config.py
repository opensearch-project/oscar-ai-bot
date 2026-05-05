#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Configuration management for security advisories Lambda function.

Credentials and sensitive config are selectively read from the advisories secret.
All other config comes from CDK Lambda environment variables.
"""

import json
import logging
import os
from typing import Dict

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class SecurityAdvisoriesConfig:
    """Centralized configuration management for Security Advisories Lambda.

    This class handles all configuration aspects including environment variables,
    Secrets Manager integration, validation, and default values for the
    security advisories processing system.
    """

    def __init__(self, validate_required: bool = True) -> None:
        """Initialize configuration with environment variables and secrets.

        Args:
            validate_required: Whether to validate required configuration values.

        Raises:
            ValueError: If required configuration values are missing.
        """
        # Cross-account role ARN from Lambda env var (set by CDK from .env)
        self.cross_account_role_arn = os.environ.get(
            'SECURITY_ADVISORIES_CROSS_ACCOUNT_ROLE_ARN', '',
        )

        # Load sensitive config from Secrets Manager
        secrets = self._load_secrets()
        self.opensearch_host = secrets.get('OPENSEARCH_HOST', '')

        # Validate required config
        if validate_required and not self.opensearch_host:
            raise ValueError('OPENSEARCH_HOST not found in secret')

        # AWS region
        self.region = os.environ.get('AWS_REGION', 'us-east-1')

        # OpenSearch configuration (set by CDK)
        self.opensearch_region = os.environ.get('OPENSEARCH_REGION', 'us-east-1')
        self.opensearch_service = os.environ.get('OPENSEARCH_SERVICE', 'es')
        self.request_timeout = int(os.environ.get('OPENSEARCH_REQUEST_TIMEOUT', '60'))

        # Index names (set by CDK)
        self.scans_index = os.environ.get('SCANS_INDEX', 'scans-000001')
        self.advisories_index = os.environ.get('ADVISORIES_INDEX', 'advisories')

        # Response configuration
        self.bedrock_message_version = os.environ.get(
            'BEDROCK_RESPONSE_MESSAGE_VERSION', '1.0',
        )

        # Agentic search pipeline configuration
        self.agentic_pipeline = os.environ.get(
            'AGENTIC_PIPELINE', 'oscar-agentic-pipeline',
        )

        logger.info(f'Initialized SecurityAdvisoriesConfig - Region: {self.region}')

    def _load_secrets(self) -> Dict[str, str]:
        """Load sensitive config from AWS Secrets Manager.

        Returns only the keys we need. Does NOT inject anything into os.environ.
        """
        keys_to_extract = {
            'OPENSEARCH_HOST',
        }
        result: Dict[str, str] = {}

        secret_name = os.environ.get('SECURITY_ADVISORIES_SECRET_NAME')
        if not secret_name:
            logger.warning('SECURITY_ADVISORIES_SECRET_NAME not set')
            return result

        try:
            client = boto3.client(
                'secretsmanager',
                region_name=os.getenv('AWS_REGION', 'us-east-1'),
            )
            response = client.get_secret_value(SecretId=secret_name)
            secret_data = json.loads(response['SecretString'])

            for key in keys_to_extract:
                if key in secret_data:
                    result[key] = str(secret_data[key])

            logger.info(f'Loaded {len(result)} keys from secret')
        except Exception as e:
            logger.error(f"Failed to load secret '{secret_name}': {e}")

        return result

    def get_opensearch_host_clean(self) -> str:
        """Get OpenSearch host with https:// prefix removed.

        Returns:
            Clean OpenSearch host without protocol prefix.
        """
        return self.opensearch_host.replace('https://', '')


class _ConfigProxy:
    """Proxy that caches config per Lambda invocation."""

    def __init__(self):
        self._cached_config = None
        self.aws_request_id = None
        self._lambda_request_id = None

    def set_request_id(self, request_id: str) -> None:
        """Set the AWS Lambda request ID."""
        self.aws_request_id = request_id

    def __getattr__(self, name):
        # If no config cached yet or request ID changed, create fresh config
        if self._cached_config is None or (
            self.aws_request_id and
            self._lambda_request_id != self.aws_request_id
        ):
            self._cached_config = SecurityAdvisoriesConfig(validate_required=False)
            self._lambda_request_id = self.aws_request_id

        return getattr(self._cached_config, name)


# Global configuration proxy
config = _ConfigProxy()
