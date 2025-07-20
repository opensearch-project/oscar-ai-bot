"""
Storage module for OSCAR.

This module provides storage implementations for session and context data.
"""

import time
import logging
import boto3
from abc import ABC, abstractmethod
from .config import config

# Configure logging
logger = logging.getLogger(__name__)

class StorageInterface(ABC):
    """Abstract base class for storage implementations."""
    
    @abstractmethod
    def store_context(self, thread_key, context):
        """Store conversation context for a thread."""
        pass
    
    @abstractmethod
    def get_context(self, thread_key):
        """Get conversation context for a thread."""
        pass
    
    @abstractmethod
    def has_seen_event(self, event_id):
        """Check if an event has been seen before."""
        pass
    
    @abstractmethod
    def mark_event_seen(self, event_id):
        """Mark an event as seen."""
        pass

class DynamoDBStorage(StorageInterface):
    """DynamoDB implementation of storage interface."""
    
    def __init__(self, region=None):
        """Initialize DynamoDB storage."""
        self.region = region or config.region
        self.dynamodb = boto3.resource('dynamodb', region_name=self.region)
        self.sessions_table = self.dynamodb.Table(config.sessions_table_name)
        self.context_table = self.dynamodb.Table(config.context_table_name)
        self.dedup_ttl = config.dedup_ttl
        self.context_ttl = config.context_ttl
    
    def store_context(self, thread_key, context):
        """Store conversation context in DynamoDB."""
        try:
            # Ensure context size is within limits
            if len(str(context)) > config.max_context_length:
                logger.warning(f"Context for {thread_key} exceeds max length, truncating history")
                # Keep only the most recent history entries
                while len(str(context)) > config.max_context_length and len(context.get("history", [])) > 1:
                    context["history"].pop(0)
            
            # Store with TTL
            expiration = int(time.time()) + self.context_ttl
            self.context_table.put_item(
                Item={
                    'thread_key': thread_key,
                    'context': context,
                    'ttl': expiration
                }
            )
            logger.info(f"Stored context for thread {thread_key}")
            return True
        except Exception as e:
            logger.error(f"Error storing context: {e}")
            return False
    
    def get_context(self, thread_key):
        """Get conversation context from DynamoDB."""
        try:
            response = self.context_table.get_item(
                Key={'thread_key': thread_key}
            )
            if 'Item' in response:
                logger.info(f"Retrieved context for thread {thread_key}")
                return response['Item'].get('context')
            logger.info(f"No context found for thread {thread_key}")
            return None
        except Exception as e:
            logger.error(f"Error retrieving context: {e}")
            return None
    
    def has_seen_event(self, event_id):
        """Check if an event has been seen before."""
        try:
            response = self.sessions_table.get_item(
                Key={'event_id': event_id}
            )
            return 'Item' in response
        except Exception as e:
            logger.error(f"Error checking event: {e}")
            return False
    
    def mark_event_seen(self, event_id):
        """Mark an event as seen in DynamoDB."""
        try:
            # Store with TTL
            expiration = int(time.time()) + self.dedup_ttl
            self.sessions_table.put_item(
                Item={
                    'event_id': event_id,
                    'timestamp': int(time.time()),
                    'ttl': expiration
                }
            )
            return True
        except Exception as e:
            logger.error(f"Error marking event: {e}")
            return False

class InMemoryStorage(StorageInterface):
    """In-memory implementation of storage interface for testing."""
    
    def __init__(self):
        """Initialize in-memory storage."""
        self.contexts = {}
        self.seen_events = {}
        self.dedup_ttl = config.dedup_ttl
        self.context_ttl = config.context_ttl
    
    def store_context(self, thread_key, context):
        """Store conversation context in memory."""
        self.contexts[thread_key] = {
            'context': context,
            'expiration': int(time.time()) + self.context_ttl
        }
        return True
    
    def get_context(self, thread_key):
        """Get conversation context from memory."""
        if thread_key in self.contexts:
            # Check if expired
            if self.contexts[thread_key]['expiration'] < int(time.time()):
                del self.contexts[thread_key]
                return None
            return self.contexts[thread_key]['context']
        return None
    
    def has_seen_event(self, event_id):
        """Check if an event has been seen before."""
        if event_id in self.seen_events:
            # Check if expired
            if self.seen_events[event_id] < int(time.time()):
                del self.seen_events[event_id]
                return False
            return True
        return False
    
    def mark_event_seen(self, event_id):
        """Mark an event as seen in memory."""
        self.seen_events[event_id] = int(time.time()) + self.dedup_ttl
        return True

# Factory function to create the appropriate storage implementation
def get_storage(storage_type='dynamodb', region=None):
    """Get storage implementation based on type."""
    if storage_type == 'memory':
        return InMemoryStorage()
    return DynamoDBStorage(region)