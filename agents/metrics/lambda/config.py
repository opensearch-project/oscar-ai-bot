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

        # Build and test index names are not needed — the conversational agent handles
        # that routing via ListIndexTool/IndexMappingTool. The release indices are named
        # explicitly because the deterministic release handlers build their own DSL and
        # the release flow agent needs the index in the request path.
        self.release_state_index = os.environ.get('RELEASE_STATE_INDEX', 'opensearch_release_state')
        self.release_schedule_index = os.environ.get('RELEASE_SCHEDULE_INDEX', 'opensearch_release_schedule')

        # Response configuration
        self.bedrock_message_version = os.environ.get('BEDROCK_RESPONSE_MESSAGE_VERSION', '1.0')

        # Agentic search pipeline configuration. The metrics pipeline is backed by a
        # conversational agent (index routing + memory); the release pipeline by a flow
        # agent (single QueryPlanningTool, index supplied per request, no memory).
        self.agentic_pipeline = os.environ.get('AGENTIC_PIPELINE', 'metrics-agentic-pipeline')
        self.release_agentic_pipeline = os.environ.get(
            'RELEASE_AGENTIC_PIPELINE', 'release-flow-agentic-pipeline'
        )

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
