#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.

"""
Configuration Management for OSCAR Agent.

This module provides centralized configuration management for the OSCAR agent
implementation, handling environment variables, validation, and default values.

Classes:
    Config: Main configuration class with validation and environment variable handling
"""

import json
import logging
import os
from typing import Dict

import boto3

logger = logging.getLogger(__name__)


class Config:
    """Centralized configuration management for OSCAR Agent.

    This class handles all configuration aspects including environment variables,
    validation, and default values. It supports both Phase 1 (single agent) and
    Phase 2 (multi-agent) configurations.
    """

    def __init__(self, validate_required: bool = True) -> None:
        """Initialize configuration with environment variables.

        Args:
            validate_required: Whether to validate required environment variables

        Raises:
            ValueError: If required environment variables are missing
        """
        # Load credentials + auth config from central secret
        secrets = self._load_from_central_secret()
        self.slack_bot_token = secrets.get('SLACK_BOT_TOKEN', '')
        self.slack_signing_secret = secrets.get('SLACK_SIGNING_SECRET', '')
        self.dm_authorized_users = [u.strip() for u in secrets.get('DM_AUTHORIZED_USERS', '').split(',') if u.strip()]
        self.fully_authorized_users = [u.strip() for u in secrets.get('FULLY_AUTHORIZED_USERS', '').split(',') if u.strip()]
        self.channel_allow_list = [c.strip() for c in secrets.get('CHANNEL_ALLOW_LIST', '').split(',') if c.strip()]

        if validate_required and not self.slack_bot_token:
            raise ValueError("SLACK_BOT_TOKEN not found in central secret")
        if validate_required and not self.slack_signing_secret:
            raise ValueError("SLACK_SIGNING_SECRET not found in central secret")

        # AWS region
        self.region = os.environ.get('AWS_REGION', 'us-east-1')

        # Bedrock agent IDs from SSM
        self._load_agent_config_from_ssm()

        if validate_required and not self.oscar_privileged_bedrock_agent_id:
            raise ValueError("OSCAR_PRIVILEGED_BEDROCK_AGENT_ID is required")
        if validate_required and not self.oscar_privileged_bedrock_agent_alias_id:
            raise ValueError("OSCAR_PRIVILEGED_BEDROCK_AGENT_ALIAS_ID is required")
        if validate_required and not self.oscar_limited_bedrock_agent_id:
            raise ValueError("OSCAR_LIMITED_BEDROCK_AGENT_ID is required")
        if validate_required and not self.oscar_limited_bedrock_agent_alias_id:
            raise ValueError("OSCAR_LIMITED_BEDROCK_AGENT_ALIAS_ID is required")

        # Infrastructure (set by CDK)
        self.context_table_name = os.environ.get('CONTEXT_TABLE_NAME')
        if validate_required and not self.context_table_name:
            raise ValueError("CONTEXT_TABLE_NAME is required")

        # Config (set by CDK from .env or defaults)
        self.context_ttl = int(os.environ.get('CONTEXT_TTL', 604800))

        # Feature flags
        self.enable_dm = os.environ.get('ENABLE_DM', 'false').lower() == 'true'

        # Agent timeout and retry settings
        self.agent_timeout = int(os.environ.get('AGENT_TIMEOUT', 90))
        self.agent_max_retries = int(os.environ.get('AGENT_MAX_RETRIES', 2))

        # Timeout thresholds
        self.hourglass_threshold = int(os.environ.get('HOURGLASS_THRESHOLD_SECONDS', 45))
        self.timeout_threshold = int(os.environ.get('TIMEOUT_THRESHOLD_SECONDS', 120))

        # Thread pool settings
        self.max_workers = int(os.environ.get('MAX_WORKERS', 100))
        self.max_active_queries = int(os.environ.get('MAX_ACTIVE_QUERIES', 100))
        self.monitor_interval = int(os.environ.get('MONITOR_INTERVAL_SECONDS', 15))

        # Thread naming
        self.slack_handler_thread_prefix = os.environ.get('SLACK_HANDLER_THREAD_NAME_PREFIX', 'oscar-agent')

        # Agent query templates
        self.agent_queries = {
            'announce': os.environ.get('AGENT_QUERY_ANNOUNCE', ''),
            'assign_owner': os.environ.get('AGENT_QUERY_ASSIGN_OWNER', ''),
            'request_owner': os.environ.get('AGENT_QUERY_REQUEST_OWNER', ''),
            'rc_details': os.environ.get('AGENT_QUERY_RC_DETAILS', ''),
            'missing_notes': os.environ.get('AGENT_QUERY_MISSING_NOTES', ''),
            'integration_test': os.environ.get('AGENT_QUERY_INTEGRATION_TEST', ''),
            'broadcast': os.environ.get('AGENT_QUERY_BROADCAST', '')
        }

        # Regex patterns
        self.patterns = {
            'channel_id': os.environ.get('CHANNEL_ID_PATTERN', r'\b(C[A-Z0-9]{10,})\b'),
            'channel_ref': os.environ.get('CHANNEL_REF_PATTERN', r'#([a-z0-9-]+)'),
            'at_symbol': os.environ.get('AT_SYMBOL_PATTERN', r'@([a-zA-Z0-9_-]+)'),
            'mention': os.environ.get('MENTION_PATTERN', r'<@[A-Z0-9]+>'),
            'heading': os.environ.get('HEADING_PATTERN', r'^#{1,6}\s+(.+)$'),
            'bold': os.environ.get('BOLD_PATTERN', r'\*\*(.+?)\*\*'),
            'italic': os.environ.get('ITALIC_PATTERN', r'(?<!\*)\*([^*]+?)\*(?!\*)'),
            'link': os.environ.get('LINK_PATTERN', r'\[([^\]]+)\]\(([^)]+)\)'),
            'bullet': os.environ.get('BULLET_PATTERN', r'^[\*\-]\s+'),
            'channel_mention': os.environ.get('CHANNEL_MENTION_PATTERN', r'(?<!<)#([a-zA-Z0-9_-]+)(?!>)'),
            'version': os.environ.get('VERSION_PATTERN', r'version\s+(\d+\.\d+\.\d+)')
        }

        # Logging
        self.log_query_preview_length = int(os.environ.get('LOG_QUERY_PREVIEW_LENGTH', 100))

    def _load_from_central_secret(self) -> Dict[str, str]:
        """Load credentials and auth config from the central secret (JSON format).

        Returns only the keys we need. Does NOT inject anything into os.environ.
        """
        keys_to_extract = {
            'SLACK_BOT_TOKEN', 'SLACK_SIGNING_SECRET',
            'DM_AUTHORIZED_USERS', 'FULLY_AUTHORIZED_USERS', 'CHANNEL_ALLOW_LIST',
        }
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

    def _load_agent_config_from_ssm(self) -> None:
        """Load Bedrock agent IDs and aliases from SSM Parameter Store."""
        try:
            ssm_client = boto3.client('ssm', region_name=self.region)

            # Get parameter paths from environment
            privileged_id_param = os.environ.get('OSCAR_PRIVILEGED_BEDROCK_AGENT_ID_PARAM_PATH')
            privileged_alias_param = os.environ.get('OSCAR_PRIVILEGED_BEDROCK_AGENT_ALIAS_PARAM_PATH')
            limited_id_param = os.environ.get('OSCAR_LIMITED_BEDROCK_AGENT_ID_PARAM_PATH')
            limited_alias_param = os.environ.get('OSCAR_LIMITED_BEDROCK_AGENT_ALIAS_PARAM_PATH')

            # Fetch from SSM
            if privileged_id_param:
                self.oscar_privileged_bedrock_agent_id = ssm_client.get_parameter(Name=privileged_id_param)['Parameter']['Value']
            else:
                self.oscar_privileged_bedrock_agent_id = None

            if privileged_alias_param:
                self.oscar_privileged_bedrock_agent_alias_id = ssm_client.get_parameter(Name=privileged_alias_param)['Parameter']['Value']
            else:
                self.oscar_privileged_bedrock_agent_alias_id = None

            if limited_id_param:
                self.oscar_limited_bedrock_agent_id = ssm_client.get_parameter(Name=limited_id_param)['Parameter']['Value']
            else:
                self.oscar_limited_bedrock_agent_id = None

            if limited_alias_param:
                self.oscar_limited_bedrock_agent_alias_id = ssm_client.get_parameter(Name=limited_alias_param)['Parameter']['Value']
            else:
                self.oscar_limited_bedrock_agent_alias_id = None

            logger.info("Successfully loaded agent configuration from SSM Parameter Store")

        except Exception as e:
            logger.error(f"Error loading agent config from SSM: {e}")


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
            self._cached_config = Config(validate_required=True)
            self._lambda_request_id = self.aws_request_id

        return getattr(self._cached_config, name)


# Global configuration proxy
config = _ConfigProxy()
