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

import logging
import os
from typing import Optional, Tuple

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
        # AWS region
        self.region = os.environ.get('AWS_REGION', 'us-east-1')
        
        # Bedrock Agent configuration (Phase 1)
        self.oscar_bedrock_agent_id = os.environ.get('OSCAR_BEDROCK_AGENT_ID')
        if validate_required and not self.oscar_bedrock_agent_id:
            logger.error("OSCAR_BEDROCK_AGENT_ID environment variable is required")
            raise ValueError("OSCAR_BEDROCK_AGENT_ID environment variable is required")
            
        self.oscar_bedrock_agent_alias_id = os.environ.get('OSCAR_BEDROCK_AGENT_ALIAS_ID')
        if validate_required and not self.oscar_bedrock_agent_alias_id:
            logger.error("OSCAR_BEDROCK_AGENT_ALIAS_ID environment variable is required")
            raise ValueError("OSCAR_BEDROCK_AGENT_ALIAS_ID environment variable is required")
        
        # DynamoDB tables
        self.sessions_table_name = os.environ.get('SESSIONS_TABLE_NAME', 'oscar-sessions-v2')
        self.context_table_name = os.environ.get('CONTEXT_TABLE_NAME', 'oscar-context')
        
        # Slack credentials
        self.slack_bot_token = os.environ.get('SLACK_BOT_TOKEN')
        if validate_required and not self.slack_bot_token:
            logger.error("SLACK_BOT_TOKEN environment variable is required")
            raise ValueError("SLACK_BOT_TOKEN environment variable is required")
            
        self.slack_signing_secret = os.environ.get('SLACK_SIGNING_SECRET')
        if validate_required and not self.slack_signing_secret:
            logger.error("SLACK_SIGNING_SECRET environment variable is required")
            raise ValueError("SLACK_SIGNING_SECRET environment variable is required")
        
        # TTL settings
        self.dedup_ttl = int(os.environ.get('DEDUP_TTL', 300))  # 5 minutes
        self.session_ttl = int(os.environ.get('SESSION_TTL', 3600))  # 1 hour
        self.context_ttl = int(os.environ.get('CONTEXT_TTL', 604800))  # 7 days
        
        # Context settings
        self.max_context_length = int(os.environ.get('MAX_CONTEXT_LENGTH', 3000))
        self.context_summary_length = int(os.environ.get('CONTEXT_SUMMARY_LENGTH', 500))
        
        # Feature flags
        self.enable_dm = os.environ.get('ENABLE_DM', 'false').lower() == 'true'
        
        # Agent timeout and retry settings
        self.agent_timeout = int(os.environ.get('AGENT_TIMEOUT', 60))  # 60 seconds
        self.agent_max_retries = int(os.environ.get('AGENT_MAX_RETRIES', 2))
        
        # Phase 2: Multi-agent configuration (for future use)
        self.oscar_knowledge_agent_id = os.environ.get('OSCAR_KNOWLEDGE_AGENT_ID')
        self.oscar_knowledge_agent_alias_id = os.environ.get('OSCAR_KNOWLEDGE_AGENT_ALIAS_ID')
        self.oscar_metrics_agent_id = os.environ.get('OSCAR_METRICS_AGENT_ID')
        self.oscar_metrics_agent_alias_id = os.environ.get('OSCAR_METRICS_AGENT_ALIAS_ID')
        self.oscar_build_agent_id = os.environ.get('OSCAR_BUILD_AGENT_ID')
        self.oscar_build_agent_alias_id = os.environ.get('OSCAR_BUILD_AGENT_ALIAS_ID')
        self.oscar_test_agent_id = os.environ.get('OSCAR_TEST_AGENT_ID')
        self.oscar_test_agent_alias_id = os.environ.get('OSCAR_TEST_AGENT_ALIAS_ID')
        
        # Agent routing configuration (Phase 2)
        self.enable_multi_agent = os.environ.get('ENABLE_MULTI_AGENT', 'false').lower() == 'true'
        self.default_agent = os.environ.get('DEFAULT_AGENT', 'knowledge')
    
    def get_slack_credentials(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Get Slack credentials from environment variables.
        
        Returns:
            A tuple containing (slack_bot_token, slack_signing_secret)
        """
        return self.slack_bot_token, self.slack_signing_secret

# Create a singleton instance with validation enabled for production use
config = Config(validate_required=True)