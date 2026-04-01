#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.

"""
Configuration Management for Metrics Lambda Functions.

Credentials and sensitive config are selectively read from the metrics secret.
All other config comes from CDK Lambda environment variables.
"""

import json
import logging
import os
from datetime import datetime
from typing import Dict

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class MetricsConfig:
    """Centralized configuration management for Metrics Lambda Functions.

    This class handles all configuration aspects including environment variables,
    validation, and default values for the metrics processing system.
    """

    def __init__(self, validate_required: bool = True) -> None:
        """Initialize configuration with environment variables.

        Args:
            validate_required: Whether to validate required environment variables

        Raises:
            ValueError: If required environment variables are missing
        """
        # Cross-account role ARN from Lambda env var (set by CDK from .env)
        self.metrics_cross_account_role_arn = os.environ.get('METRICS_CROSS_ACCOUNT_ROLE_ARN', '')

        # Load remaining sensitive config from metrics secret
        secrets = self._load_from_metrics_secret()
        self.opensearch_host = secrets.get('OPENSEARCH_HOST', '')

        # Validate required config
        if validate_required and not self.metrics_cross_account_role_arn:
            raise ValueError("METRICS_CROSS_ACCOUNT_ROLE_ARN environment variable is not set")
        if validate_required and not self.opensearch_host:
            raise ValueError("OPENSEARCH_HOST not found in metrics secret")

        # AWS region
        self.region = os.environ.get('AWS_REGION', 'us-east-1')

        # OpenSearch configuration (set by CDK)
        self.opensearch_region = os.environ.get('OPENSEARCH_REGION', 'us-east-1')
        self.opensearch_service = os.environ.get('OPENSEARCH_SERVICE', 'es')

        # Query configuration (set by CDK)
        self.large_query_size = int(os.environ.get('OPENSEARCH_LARGE_QUERY_SIZE', 1000))
        self.opensearch_request_timeout = int(os.environ.get('OPENSEARCH_REQUEST_TIMEOUT', 60))

        # Index names (set by CDK or env vars).
        # These MUST match the concrete index (or alias) configured in the
        # OpenSearch flow agent's QueryPlanningTool — wildcards will cause
        # "Failed to extract index mapping" errors.
        # Build/test indices are month-year-based; default to current month-year.
        current_month_year = datetime.now().strftime('%m-%Y')
        self.integration_test_index = os.environ.get(
            'OPENSEARCH_INTEGRATION_TEST_INDEX',
            f'opensearch-integration-test-results-{current_month_year}'
        )
        self.build_results_index = os.environ.get(
            'OPENSEARCH_BUILD_RESULTS_INDEX',
            f'opensearch-distribution-build-results-{current_month_year}'
        )
        self.release_metrics_index = os.environ.get(
            'OPENSEARCH_RELEASE_METRICS_INDEX',
            'opensearch_release_metrics'
        )

        # Response configuration
        self.bedrock_message_version = os.environ.get('BEDROCK_RESPONSE_MESSAGE_VERSION', '1.0')

        # Agentic search pipeline configuration
        self.agentic_pipeline = os.environ.get('AGENTIC_PIPELINE', 'metrics-agentic-pipeline')

        logger.info(f"Initialized MetricsConfig - Region: {self.region}")

    def _load_from_metrics_secret(self) -> Dict[str, str]:
        """Load sensitive config from the metrics secret (JSON format).

        Returns only the keys we need. Does NOT inject anything into os.environ.
        """
        keys_to_extract = {
            'OPENSEARCH_HOST',
        }
        result: Dict[str, str] = {}

        secret_name = os.environ.get('METRICS_SECRET_NAME')
        if not secret_name:
            logger.error("METRICS_SECRET_NAME environment variable is not set")
            return result

        try:
            client = boto3.client(
                'secretsmanager',
                region_name=os.getenv('AWS_REGION', 'us-east-1')
            )
            response = client.get_secret_value(SecretId=secret_name)
            secret_data = json.loads(response['SecretString'])

            for key in keys_to_extract:
                if key in secret_data:
                    result[key] = str(secret_data[key])

            logger.info(f"Loaded {len(result)} keys from metrics secret")
        except Exception as e:
            logger.error(f"Failed to load metrics secret '{secret_name}': {e}")

        return result

    def get_opensearch_host_clean(self) -> str:
        """Get OpenSearch host with https:// prefix removed.

        Returns:
            Clean OpenSearch host without protocol prefix
        """
        return self.opensearch_host.replace('https://', '')

    # --- Pre-agentic fallback: wildcard patterns for direct DSL queries ---
    # def get_integration_test_index_pattern(self) -> str:
    #     """Wildcard pattern for direct DSL queries across monthly indices."""
    #     return "opensearch-integration-test-results-*"
    #
    # def get_build_results_index_pattern(self) -> str:
    #     """Wildcard pattern for direct DSL queries across monthly indices."""
    #     return "opensearch-distribution-build-results-*"


class _ConfigProxy:
    """Proxy that caches config per lambda execution."""
    def __init__(self):
        self._cached_config = None
        self.aws_request_id = None
        self._lambda_request_id = None

    def set_request_id(self, request_id: str) -> None:
        """Set the AWS Lambda request ID."""
        self.aws_request_id = request_id

    def __getattr__(self, name):
        # If no config cached yet or request ID changed, create fresh config
        if self._cached_config is None or (self.aws_request_id and self._lambda_request_id != self.aws_request_id):
            self._cached_config = MetricsConfig(validate_required=False)
            self._lambda_request_id = self.aws_request_id

        return getattr(self._cached_config, name)


# Global configuration proxy
config = _ConfigProxy()
