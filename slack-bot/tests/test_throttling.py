#!/usr/bin/env python
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.

"""
Tests for the throttling module.
"""

import unittest
from unittest.mock import MagicMock, patch
import os
import sys
import time

# Add the parent directory to sys.path to import the modules
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

# Import the Throttler class directly
from throttling import Throttler

class TestThrottler(unittest.TestCase):
    """Test cases for the Throttler class."""
    
    def setUp(self):
        """Set up test environment."""
        self.mock_storage = MagicMock()
        self.throttler = Throttler(self.mock_storage, requests_per_minute=3, ttl_seconds=60)
    
    def test_first_request_not_throttled(self):
        """Test that the first request from a user is not throttled."""
        # Mock storage.get_throttle_count to return None (no previous requests)
        self.mock_storage.get_throttle_count.return_value = None
        
        # Call should_throttle
        result = self.throttler.should_throttle("U12345")
        
        # Verify result
        self.assertFalse(result)
        
        # Verify storage calls
        self.mock_storage.get_throttle_count.assert_called_once_with("throttle_U12345")
        self.mock_storage.update_throttle_count.assert_called_once()
    
    def test_under_limit_not_throttled(self):
        """Test that requests under the limit are not throttled."""
        # Mock storage.get_throttle_count to return a count under the limit
        self.mock_storage.get_throttle_count.return_value = {
            'count': 2,
            'ttl': int(time.time()) + 30  # TTL is 30 seconds in the future
        }
        
        # Call should_throttle
        result = self.throttler.should_throttle("U12345")
        
        # Verify result
        self.assertFalse(result)
        
        # Verify storage calls
        self.mock_storage.get_throttle_count.assert_called_once_with("throttle_U12345")
        self.mock_storage.update_throttle_count.assert_called_once()
    
    def test_over_limit_throttled(self):
        """Test that requests over the limit are throttled."""
        # Mock storage.get_throttle_count to return a count over the limit
        self.mock_storage.get_throttle_count.return_value = {
            'count': 3,  # Equal to the limit
            'ttl': int(time.time()) + 30  # TTL is 30 seconds in the future
        }
        
        # Call should_throttle
        result = self.throttler.should_throttle("U12345")
        
        # Verify result
        self.assertTrue(result)
        
        # Verify storage calls
        self.mock_storage.get_throttle_count.assert_called_once_with("throttle_U12345")
        self.mock_storage.update_throttle_count.assert_called_once()
    
    def test_expired_ttl_not_throttled(self):
        """Test that requests with expired TTL are not throttled."""
        # Mock storage.get_throttle_count to return a count with expired TTL
        self.mock_storage.get_throttle_count.return_value = {
            'count': 5,  # Over the limit
            'ttl': int(time.time()) - 10  # TTL is 10 seconds in the past
        }
        
        # Call should_throttle
        result = self.throttler.should_throttle("U12345")
        
        # Verify result
        self.assertFalse(result)
        
        # Verify storage calls
        self.mock_storage.get_throttle_count.assert_called_once_with("throttle_U12345")
        self.mock_storage.update_throttle_count.assert_called_once()

if __name__ == '__main__':
    unittest.main()