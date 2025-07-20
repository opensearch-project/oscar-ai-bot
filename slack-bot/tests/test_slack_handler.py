"""
Tests for the slack_handler module.
"""

import unittest
from unittest.mock import patch, MagicMock, call
from slack_bot.slack_handler import SlackHandler

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
    
    def test_register_handlers(self):
        """Test registering event handlers."""
        # Mock config with DM enabled
        with patch('slack_bot.slack_handler.config') as mock_config:
            mock_config.enable_dm = True
            
            self.handler.register_handlers()
            
            # Verify event handlers registered
            self.mock_app.event.assert_called_with("app_mention")
    
    def test_handle_app_mention(self):
        """Test handling app_mention event."""
        # Set up mock for _process_message
        with patch.object(self.handler, '_process_message') as mock_process:
            with patch.object(self.handler, '_is_duplicate_event', return_value=False):
                event = {
                    'channel': 'C12345',
                    'user': 'U12345',
                    'ts': '1234567890.123456',
                    'text': '<@test-bot-id> test message',
                    'thread_ts': '1234567890.000001'
                }
                mock_say = MagicMock()
                
                self.handler.handle_app_mention(event, mock_say)
                
                # Verify _process_message called with correct parameters
                mock_process.assert_called_once_with(
                    'C12345', 
                    '1234567890.000001', 
                    'U12345', 
                    '<@test-bot-id> test message', 
                    mock_say
                )
    
    def test_handle_message(self):
        """Test handling direct message event."""
        # Set up mock for _process_message
        with patch.object(self.handler, '_process_message') as mock_process:
            with patch.object(self.handler, '_is_duplicate_event', return_value=False):
                message = {
                    'channel': 'D12345',
                    'channel_type': 'im',
                    'user': 'U12345',
                    'ts': '1234567890.123456',
                    'text': 'test message',
                    'thread_ts': '1234567890.000001'
                }
                mock_say = MagicMock()
                
                self.handler.handle_message(message, mock_say)
                
                # Verify _process_message called with correct parameters
                mock_process.assert_called_once_with(
                    'D12345', 
                    '1234567890.000001', 
                    'U12345', 
                    'test message', 
                    mock_say
                )
    
    def test_handle_message_not_dm(self):
        """Test handling message event that is not a DM."""
        # Set up mock for _process_message
        with patch.object(self.handler, '_process_message') as mock_process:
            message = {
                'channel': 'C12345',
                'channel_type': 'channel',  # Not 'im'
                'user': 'U12345',
                'ts': '1234567890.123456',
                'text': 'test message'
            }
            mock_say = MagicMock()
            
            self.handler.handle_message(message, mock_say)
            
            # Verify _process_message not called
            mock_process.assert_not_called()
    
    def test_process_message_success(self):
        """Test successful message processing."""
        # Set up mocks
        self.mock_storage.get_context.return_value = {
            'session_id': 'test-session',
            'summary': 'test summary',
            'history': []
        }
        self.mock_knowledge_base.query.return_value = ('test response', 'new-session')
        
        # Mock reactions
        with patch.object(self.handler.client, 'reactions_add') as mock_add:
            with patch.object(self.handler.client, 'reactions_remove') as mock_remove:
                mock_say = MagicMock()
                
                self.handler._process_message(
                    'C12345', 
                    '1234567890.000001', 
                    'U12345', 
                    'test message', 
                    mock_say
                )
                
                # Verify reactions
                mock_add.assert_any_call(
                    channel='C12345',
                    timestamp='1234567890.000001',
                    name='thinking_face'
                )
                mock_remove.assert_called_with(
                    channel='C12345',
                    timestamp='1234567890.000001',
                    name='thinking_face'
                )
                mock_add.assert_any_call(
                    channel='C12345',
                    timestamp='1234567890.000001',
                    name='white_check_mark'
                )
                
                # Verify knowledge base query
                self.mock_knowledge_base.query.assert_called_once_with(
                    'test message',
                    session_id='test-session',
                    context_summary='test summary'
                )
                
                # Verify response sent
                mock_say.assert_called_once_with(
                    text='test response',
                    thread_ts='1234567890.000001'
                )
                
                # Verify context stored
                self.mock_storage.store_context.assert_called_once()
    
    def test_process_message_error(self):
        """Test error handling in message processing."""
        # Set up mocks
        self.mock_storage.get_context.return_value = None
        self.mock_knowledge_base.query.side_effect = Exception("Test error")
        
        # Mock reactions
        with patch.object(self.handler.client, 'reactions_add') as mock_add:
            with patch.object(self.handler.client, 'reactions_remove') as mock_remove:
                mock_say = MagicMock()
                
                self.handler._process_message(
                    'C12345', 
                    '1234567890.000001', 
                    'U12345', 
                    'test message', 
                    mock_say
                )
                
                # Verify error reaction
                mock_add.assert_any_call(
                    channel='C12345',
                    timestamp='1234567890.000001',
                    name='x'
                )
                
                # Verify error message sent
                mock_say.assert_called_once()
                args, kwargs = mock_say.call_args
                self.assertIn('sorry', args[0].lower())
                self.assertEqual(kwargs['thread_ts'], '1234567890.000001')
    
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
    
    def test_bot_responded(self):
        """Test bot response detection."""
        # Set up mock response with bot reply
        self.mock_app.client.conversations_replies.return_value = {
            'messages': [
                {'ts': '1234567890.000001', 'user': 'U12345'},  # Original message
                {'ts': '1234567890.000002', 'bot_id': 'B12345'}  # Bot reply
            ]
        }
        
        result = self.handler._bot_responded('C12345', '1234567890.000001')
        
        # Should detect bot response
        self.assertTrue(result)

if __name__ == '__main__':
    unittest.main()