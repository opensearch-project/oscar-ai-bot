#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Constants for Communication Handler.

This module loads configuration from environment variables via the config module.
All magic numbers and hardcoded values have been moved to configuration.
"""

from config import config

# Load configuration from environment variables
CHANNEL_ALLOW_LIST = config.channel_allow_list
CONTEXT_TTL = config.context_ttl
MESSAGE_TEMPLATES = config.message_templates