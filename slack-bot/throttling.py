#!/usr/bin/env python
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.

"""
Throttling module for OSCAR.

This module provides throttling functionality to limit request rates.
"""

import time
import logging
from typing import Optional

from storage import StorageInterface
from config import config

# Configure logging
logger = logging.getLogger(__name__)

class Throttler:
    """Throttling implementation for rate limiting requests."""
    
    def __init__(self, storage: StorageInterface, 
                 requests_per_minute: int = None, 
                 ttl_seconds: int = None) -> None:
        """
        Initialize throttler with storage and rate limits.
        
        Args:
            storage: Storage implementation for tracking request counts
            requests_per_minute: Maximum number of requests allowed per minute per user
            ttl_seconds: Time window for rate limiting in seconds
        """
        self.storage = storage
        self.requests_per_minute = requests_per_minute or config.throttle_requests_per_minute
        self.ttl_seconds = ttl_seconds or config.throttle_window_seconds
    
    def should_throttle(self, user_id: str) -> bool:
        """
        Check if a request from the user should be throttled.
        
        Args:
            user_id: The Slack user ID
            
        Returns:
            True if the request should be throttled, False otherwise
        """
        # Generate throttle key for this user
        throttle_key = f"throttle_{user_id}"
        
        # Get current count for this user
        current_time = int(time.time())
        count_data = self.storage.get_throttle_count(throttle_key)
        
        if not count_data:
            # First request from this user in the current window
            self.storage.update_throttle_count(
                throttle_key, 
                1, 
                current_time + self.ttl_seconds
            )
            logger.info(f"First request from user {user_id} in current window")
            return False
        
        # Check if TTL has expired
        if count_data.get('ttl', 0) < current_time:
            # TTL expired, reset counter
            self.storage.update_throttle_count(
                throttle_key, 
                1, 
                current_time + self.ttl_seconds
            )
            logger.info(f"TTL expired for user {user_id}, resetting counter")
            return False
        
        # Increment counter
        count = count_data.get('count', 0) + 1
        self.storage.update_throttle_count(
            throttle_key, 
            count, 
            count_data.get('ttl')
        )
        
        # Check if over limit
        if count > self.requests_per_minute:
            logger.warning(f"User {user_id} exceeded rate limit: {count} requests in window")
            return True
        
        logger.info(f"User {user_id} request count: {count}/{self.requests_per_minute}")
        return False