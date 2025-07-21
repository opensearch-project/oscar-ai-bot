"""
Tests for the slack_handler module.
"""

import unittest
from unittest.mock import patch, MagicMock, call
import os
import sys

# Add the parent directory to sys.path to import the modules
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

# Import the SlackHandler class directly
from slack_handler import SlackHandler

class TestSlackHandler(unittest.TestCase):
    """Test cases for the SlackHandler class."""
    
    def setUp(self):
        """Set up test environment."""
        # Create mock app, storage, and knowledge base
        self.mock_app = MagicMock()
        self.mock_storage = MagicMock()
        self.mock_knowledge_base = MagicMock()
        
        # Set up mock app client
        self.mock_app.client = MagicMock()
        self.mock_app.client.auth_test.return_value = {"user_id": "test-bot-id"}
        
        # Create handler instance
        self.handler = SlackHandler(
            self.mock_app,
            self.mock_storage,
            self.mock_knowledge_base
        )
    
    def test_is_duplicate_event(self):
        """Test duplicate event detection."""
        # Set up mock
        self.mock_storage.has_seen_event.return_value = True
        
        event = {
            'event_ts': '1234567890.123456'
        }
        
        result = self.handler._is_duplicate_event(event)
        
        # Verify result
        self.assertTrue(result)
        
        # Verify storage check
        self.mock_storage.has_seen_event.assert_called_once_with('1234567890.123456')

if __name__ == '__main__':
    unittest.main()