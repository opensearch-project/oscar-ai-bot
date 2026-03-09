#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.

"""
Configuration for OSCAR Communication Handler.

Credentials and auth config are selectively read from the central secret.
All other config comes from CDK Lambda environment variables.
"""

import json
import logging
import os
from typing import Any, Dict

import boto3

logger = logging.getLogger(__name__)


class Config:
    """Configuration for the communication handler Lambda."""

    def __init__(self) -> None:
        # Credentials + auth from central secret
        secrets = self._load_from_central_secret()
        self.slack_bot_token = secrets.get('SLACK_BOT_TOKEN', '')
        self.slack_signing_secret = secrets.get('SLACK_SIGNING_SECRET', '')
        self.channel_allow_list = [c.strip() for c in secrets.get('CHANNEL_ALLOW_LIST', '').split(',') if c.strip()]

        if not self.slack_bot_token:
            raise ValueError("SLACK_BOT_TOKEN not found in central secret")
        if not self.channel_allow_list:
            raise ValueError("CHANNEL_ALLOW_LIST not found in central secret")

        # Infrastructure (set by CDK)
        self.region = os.environ.get('AWS_REGION', 'us-east-1')
        self.context_table_name = os.environ.get('CONTEXT_TABLE_NAME')
        if not self.context_table_name:
            raise ValueError("CONTEXT_TABLE_NAME is required")
        self.context_ttl = int(os.environ.get('CONTEXT_TTL', 604800))

        # Config (set by CDK)
        self.bedrock_message_version = os.environ.get('BEDROCK_RESPONSE_MESSAGE_VERSION', '1.0')

        channel_mappings_str = os.environ.get('CHANNEL_MAPPINGS', '{}')
        try:
            self.channel_mappings: Dict[str, Any] = json.loads(channel_mappings_str)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse CHANNEL_MAPPINGS: {e}")
            self.channel_mappings = {}

        self.patterns = {
            'channel_id': os.environ.get('CHANNEL_ID_PATTERN', r'\b(C[A-Z0-9]{10,})\b'),
            'channel_ref': os.environ.get('CHANNEL_REF_PATTERN', r'#([a-z0-9-]+)'),
        }

    def _load_from_central_secret(self) -> Dict[str, str]:
        """Selectively read credentials and auth config from the central secret (JSON format)."""
        keys_to_extract = {'SLACK_BOT_TOKEN', 'SLACK_SIGNING_SECRET', 'CHANNEL_ALLOW_LIST'}
        result: Dict[str, str] = {}

        secret_name = os.environ.get('CENTRAL_SECRET_NAME')
        if not secret_name:
            logger.error("CENTRAL_SECRET_NAME environment variable is not set")
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

            logger.info(f"Loaded {len(result)} keys from central secret")
        except Exception as e:
            logger.error(f"Failed to load central secret '{secret_name}': {e}")

        return result


class _ConfigProxy:
    """Proxy that lazily initializes and caches config per Lambda invocation."""

    def __init__(self) -> None:
        self._cached_config = None
        self._lambda_request_id = None
        self.aws_request_id = None

    def set_request_id(self, request_id: str) -> None:
        self.aws_request_id = request_id

    def __getattr__(self, name: str) -> Any:
        if self._cached_config is None or (
            self.aws_request_id and self._lambda_request_id != self.aws_request_id
        ):
            self._cached_config = Config()
            self._lambda_request_id = self.aws_request_id
        return getattr(self._cached_config, name)


config = _ConfigProxy()
