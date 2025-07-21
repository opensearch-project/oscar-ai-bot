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

# Mock the config before importing slack_handler
with patch('config.Config') as MockConfig:
    # Create a mock config instance that doesn't validate required variables
    mock_config_instance = MockConfig.return_value
    mock_config_instance.enable_dm = False
    mock_config_instance.context_summary_length = 500
    
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
    
    def test_check_bot_already_responded(self):
        """Test checking if bot has already responded."""
        # Set up mock
        self.mock_app.client.conversations_replies.return_value = {
            'messages': [
                {'ts': '1234567890.123456', 'user': 'some-user'},  # Original message
                {'ts': '1234567890.123457', 'user': 'test-bot-id'}  # Bot response
            ]
        }
        
        result = self.handler._check_bot_already_responded('C12345', '1234567890.123456')
        
        # Verify result
        self.assertTrue(result)
        
        # Verify API call
        self.mock_app.client.conversations_replies.assert_called_once_with(
            channel='C12345',
            ts='1234567890.123456'
        )

if __name__ == '__main__':
    unittest.main()