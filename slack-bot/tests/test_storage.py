"""
Tests for the storage module.
"""

import unittest
import time
from unittest.mock import patch, MagicMock
from slack_bot.storage import InMemoryStorage, DynamoDBStorage, StorageInterface

class TestInMemoryStorage(unittest.TestCase):
    """Test cases for the InMemoryStorage class."""
    
    def setUp(self):
        """Set up test environment."""
        self.storage = InMemoryStorage()
    
    def test_store_and_get_context(self):
        """Test storing and retrieving context."""
        # Create test context
        context = {
            'session_id': 'test-session',
            'history': [{'query': 'test query', 'response': 'test response'}],
            'summary': 'test summary'
        }
        
        # Store context
        result = self.storage.store_context('thread-1', context)
        self.assertTrue(result)
        
        # Retrieve context
        retrieved = self.storage.get_context('thread-1')
        self.assertEqual(retrieved, context)
        
        # Non-existent thread should return None
        self.assertIsNone(self.storage.get_context('thread-2'))
    
    def test_has_seen_event_and_mark_event_seen(self):
        """Test event deduplication."""
        # Initially event should not be seen
        self.assertFalse(self.storage.has_seen_event('event-1'))
        
        # Mark event as seen
        self.storage.mark_event_seen('event-1')
        
        # Now event should be seen
        self.assertTrue(self.storage.has_seen_event('event-1'))
        
        # Different event should not be seen
        self.assertFalse(self.storage.has_seen_event('event-2'))
    
    def test_context_expiration(self):
        """Test context expiration."""
        # Store context with short TTL
        self.storage.context_ttl = 1  # 1 second
        context = {'test': 'data'}
        self.storage.store_context('thread-exp', context)
        
        # Should be available immediately
        self.assertEqual(self.storage.get_context('thread-exp'), context)
        
        # Wait for expiration
        time.sleep(1.1)
        
        # Should be expired now
        self.assertIsNone(self.storage.get_context('thread-exp'))

class TestDynamoDBStorage(unittest.TestCase):
    """Test cases for the DynamoDBStorage class."""
    
    @patch('boto3.resource')
    def setUp(self, mock_boto_resource):
        """Set up test environment with mocked DynamoDB."""
        # Set up mock DynamoDB tables
        self.mock_sessions_table = MagicMock()
        self.mock_context_table = MagicMock()
        
        # Set up mock DynamoDB resource
        mock_dynamodb = MagicMock()
        mock_boto_resource.return_value = mock_dynamodb
        mock_dynamodb.Table.side_effect = [self.mock_sessions_table, self.mock_context_table]
        
        # Create storage instance with mocked config
        with patch('slack_bot.storage.config') as mock_config:
            mock_config.sessions_table_name = 'test-sessions'
            mock_config.context_table_name = 'test-context'
            mock_config.dedup_ttl = 300
            mock_config.context_ttl = 172800
            mock_config.max_context_length = 3000
            self.storage = DynamoDBStorage(region='us-west-2')
    
    def test_store_context(self):
        """Test storing context in DynamoDB."""
        # Set up mock
        self.mock_context_table.put_item.return_value = {}
        
        # Create test context
        context = {
            'session_id': 'test-session',
            'history': [{'query': 'test query', 'response': 'test response'}],
            'summary': 'test summary'
        }
        
        # Store context
        result = self.storage.store_context('thread-1', context)
        
        # Verify result
        self.assertTrue(result)
        
        # Verify put_item was called correctly
        self.mock_context_table.put_item.assert_called_once()
        args, kwargs = self.mock_context_table.put_item.call_args
        self.assertEqual(kwargs['Item']['thread_key'], 'thread-1')
        self.assertEqual(kwargs['Item']['context'], context)
        self.assertIn('ttl', kwargs['Item'])
    
    def test_get_context(self):
        """Test retrieving context from DynamoDB."""
        # Set up mock
        context = {
            'session_id': 'test-session',
            'history': [{'query': 'test query', 'response': 'test response'}],
            'summary': 'test summary'
        }
        self.mock_context_table.get_item.return_value = {
            'Item': {
                'thread_key': 'thread-1',
                'context': context
            }
        }
        
        # Retrieve context
        retrieved = self.storage.get_context('thread-1')
        
        # Verify result
        self.assertEqual(retrieved, context)
        
        # Verify get_item was called correctly
        self.mock_context_table.get_item.assert_called_once_with(
            Key={'thread_key': 'thread-1'}
        )
    
    def test_has_seen_event(self):
        """Test checking if event has been seen."""
        # Set up mock for seen event
        self.mock_sessions_table.get_item.return_value = {'Item': {'event_id': 'event-1'}}
        
        # Check if event has been seen
        result = self.storage.has_seen_event('event-1')
        
        # Verify result
        self.assertTrue(result)
        
        # Verify get_item was called correctly
        self.mock_sessions_table.get_item.assert_called_once_with(
            Key={'event_id': 'event-1'}
        )
        
        # Set up mock for unseen event
        self.mock_sessions_table.get_item.return_value = {}
        
        # Check if event has been seen
        result = self.storage.has_seen_event('event-2')
        
        # Verify result
        self.assertFalse(result)
    
    def test_mark_event_seen(self):
        """Test marking event as seen."""
        # Set up mock
        self.mock_sessions_table.put_item.return_value = {}
        
        # Mark event as seen
        result = self.storage.mark_event_seen('event-1')
        
        # Verify result
        self.assertTrue(result)
        
        # Verify put_item was called correctly
        self.mock_sessions_table.put_item.assert_called_once()
        args, kwargs = self.mock_sessions_table.put_item.call_args
        self.assertEqual(kwargs['Item']['event_id'], 'event-1')
        self.assertIn('timestamp', kwargs['Item'])
        self.assertIn('ttl', kwargs['Item'])
    
    def test_context_truncation(self):
        """Test context truncation when exceeding max length."""
        # Set up mock
        self.mock_context_table.put_item.return_value = {}
        
        # Create large context
        large_history = []
        for i in range(100):
            large_history.append({
                'query': f'query {i}' * 50,
                'response': f'response {i}' * 50,
                'timestamp': int(time.time())
            })
        
        large_context = {
            'session_id': 'test-session',
            'history': large_history,
            'summary': 'test summary'
        }
        
        # Store context
        with patch('slack_bot.storage.config') as mock_config:
            mock_config.max_context_length = 1000  # Small max length to force truncation
            self.storage.store_context('thread-large', large_context)
        
        # Verify put_item was called
        self.mock_context_table.put_item.assert_called_once()
        
        # Get the context that was stored
        args, kwargs = self.mock_context_table.put_item.call_args
        stored_context = kwargs['Item']['context']
        
        # Verify history was truncated
        self.assertLess(len(stored_context['history']), len(large_history))

if __name__ == '__main__':
    unittest.main()