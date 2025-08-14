#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.

"""
Storage Management for OSCAR Agent.

This module provides storage implementations for session and context data
with support for DynamoDB backend and automatic TTL management.

Classes:
    StorageInterface: Abstract base class for storage implementations
    DynamoDBStorage: DynamoDB implementation with TTL and error handling
"""

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import boto3

from config import config

logger = logging.getLogger(__name__)

class StorageInterface(ABC):
    """Abstract base class for storage implementations.
    
    This interface defines the contract for all storage implementations,
    ensuring consistent behavior for context and session management.
    """
    
    @abstractmethod
    def store_context(self, thread_key: str, context: Dict[str, Any]) -> bool:
        """Store conversation context for a thread.
        
        Args:
            thread_key: Unique identifier for the conversation thread
            context: Dictionary containing conversation context data
            
        Returns:
            True if storage was successful, False otherwise
        """
    
    @abstractmethod
    def get_context(self, thread_key: str) -> Optional[Dict[str, Any]]:
        """
        Get conversation context for a thread.
        
        Args:
            thread_key: Unique identifier for the conversation thread
            
        Returns:
            Dictionary containing conversation context data, or None if not found
        """
        pass
    
    @abstractmethod
    def has_seen_event(self, event_id: str) -> bool:
        """
        Check if an event has been seen before.
        
        Args:
            event_id: Unique identifier for the event
            
        Returns:
            True if the event has been seen before, False otherwise
        """
        pass
    
    @abstractmethod
    def mark_event_seen(self, event_id: str) -> bool:
        """
        Mark an event as seen.
        
        Args:
            event_id: Unique identifier for the event
            
        Returns:
            True if the event was successfully marked as seen, False otherwise
        """
        pass
    
    @abstractmethod
    def get_context_for_query(self, thread_key: str) -> str:
        """
        Get conversation context formatted for prepending to a query.
        
        Args:
            thread_key: Unique identifier for the conversation thread
            
        Returns:
            Formatted context string to prepend to query, empty string if no context
        """
        pass

class DynamoDBStorage(StorageInterface):
    """DynamoDB implementation with automatic TTL and error handling.
    
    This implementation provides robust storage for conversation context and
    session data with features:
    - Automatic TTL management for data cleanup
    - Context size limiting to prevent oversized items
    - Comprehensive error handling and logging
    - Event deduplication support
    """
    
    def __init__(self, region: Optional[str] = None) -> None:
        """Initialize DynamoDB storage with configuration.
        
        Args:
            region: AWS region for DynamoDB service, defaults to config value
        """
        self.region = region or config.region
        self.dynamodb = boto3.resource('dynamodb', region_name=self.region)
        self.sessions_table = self.dynamodb.Table(config.sessions_table_name)
        self.context_table = self.dynamodb.Table(config.context_table_name)
        self.dedup_ttl = config.dedup_ttl
        self.context_ttl = config.context_ttl
    
    def store_context(self, thread_key: str, context: Dict[str, Any]) -> bool:
        """
        Store conversation context in DynamoDB.
        
        Args:
            thread_key: Unique identifier for the conversation thread
            context: Dictionary containing conversation context data
            
        Returns:
            True if storage was successful, False otherwise
        """
        try:
            # Validate context structure
            if not isinstance(context, dict):
                logger.error(f"Invalid context type for {thread_key}: {type(context)}")
                return False
            
            # Ensure required fields exist
            if "history" not in context:
                context["history"] = []
            if "session_id" not in context:
                context["session_id"] = None
            
            # Store with TTL
            expiration = int(time.time()) + self.context_ttl
            item = {
                'thread_key': thread_key,
                'context': context,
                'ttl': expiration,
                'updated_at': int(time.time())
            }
            
            self.context_table.put_item(Item=item)
            logger.info(f"Stored context for thread {thread_key} (history: {len(context.get('history', []))} entries, session: {context.get('session_id')})")
            return True
            
        except Exception as e:
            logger.error(f"Error storing context for {thread_key}: {e}", exc_info=True)
            return False
    
    def get_context(self, thread_key: str) -> Optional[Dict[str, Any]]:
        """
        Get conversation context from DynamoDB.
        
        Args:
            thread_key: Unique identifier for the conversation thread
            
        Returns:
            Dictionary containing conversation context data, or None if not found
        """
        try:
            response = self.context_table.get_item(
                Key={'thread_key': thread_key}
            )
            
            if 'Item' in response:
                context = response['Item'].get('context')
                if context:
                    # Validate context structure
                    if not isinstance(context, dict):
                        logger.warning(f"Invalid context structure for {thread_key}, returning None")
                        return None
                    
                    # Ensure required fields exist
                    if "history" not in context:
                        context["history"] = []
                    if "session_id" not in context:
                        context["session_id"] = None
                    
                    history_count = len(context.get("history", []))
                    session_id = context.get("session_id")
                    logger.info(f"Retrieved context for thread {thread_key} (history: {history_count} entries, session: {session_id})")
                    return context
                else:
                    logger.warning(f"Context field missing for thread {thread_key}")
                    return None
            
            logger.info(f"No context found for thread {thread_key}")
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving context for {thread_key}: {e}", exc_info=True)
            return None
    
    def has_seen_event(self, event_id: str) -> bool:
        """
        Check if an event has been seen before in DynamoDB.
        
        Args:
            event_id: Unique identifier for the event
            
        Returns:
            True if the event has been seen before, False otherwise
        """
        try:
            response = self.sessions_table.get_item(
                Key={'event_id': event_id}
            )
            
            if 'Item' in response:
                # Check if the item has expired (TTL might not have been processed yet)
                if 'ttl' in response['Item']:
                    ttl = response['Item']['ttl']
                    current_time = int(time.time())
                    if ttl < current_time:
                        logger.info(f"Event {event_id} found but TTL expired, treating as new")
                        return False
                
                logger.info(f"Event {event_id} has been seen before")
                return True
            
            logger.info(f"Event {event_id} has not been seen before")
            return False
        except Exception as e:
            logger.error(f"Error checking event: {e}")
            return False
    
    def mark_event_seen(self, event_id: str) -> bool:
        """
        Mark an event as seen in DynamoDB.
        
        Args:
            event_id: Unique identifier for the event
            
        Returns:
            True if the event was successfully marked as seen, False otherwise
        """
        try:
            # Store event with TTL
            expiration = int(time.time()) + self.dedup_ttl
            current_time = int(time.time())
            
            self.sessions_table.put_item(
                Item={
                    'event_id': event_id,
                    'timestamp': current_time,
                    'ttl': expiration
                }
            )
            logger.info(f"Marked event {event_id} as seen")
            return True
        except Exception as e:
            logger.error(f"Error marking event: {e}")
            return False
    
    def get_context_for_query(self, thread_key: str) -> str:
        """
        Get conversation context formatted for prepending to a query.
        
        Args:
            thread_key: Unique identifier for the conversation thread
            
        Returns:
            Formatted context string to prepend to query, empty string if no context
        """
        try:
            context = self.get_context(thread_key)
            if not context or not context.get("history"):
                return ""
            
            # Format all conversation history for context
            context_lines = [""]
            
            for entry in context["history"]:
                query = entry.get("query", "")
                response = entry.get("response", "")
                
                context_lines.append(f"User: {query}")
                context_lines.append(f"Assistant: {response}")
                context_lines.append("")  # Empty line for readability
                        
            formatted_context = "\n".join(context_lines)
            logger.info(f"Generated context for query (thread {thread_key}): {len(formatted_context)} characters")
            return formatted_context
            
        except Exception as e:
            logger.error(f"Error generating context for query (thread {thread_key}): {e}", exc_info=True)
            return ""

def get_storage(storage_type: str = 'dynamodb', region: Optional[str] = None) -> StorageInterface:
    """
    Get storage implementation based on type.
    
    Args:
        storage_type: Type of storage to create (currently only 'dynamodb' is supported)
        region: AWS region for DynamoDB service, defaults to config value if None
        
    Returns:
        An implementation of StorageInterface
    """
    return DynamoDBStorage(region)