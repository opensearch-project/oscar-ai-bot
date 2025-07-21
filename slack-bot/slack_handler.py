#!/usr/bin/env python
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.

"""
Slack event handler module for OSCAR.

This module provides the SlackHandler class for handling Slack events.
"""

import logging
import time
import re
from typing import Dict, Any, Optional, Callable
from slack_bolt import App
from slack_sdk.errors import SlackApiError

from config import config
from storage import StorageInterface
from bedrock import KnowledgeBaseInterface

# Configure logging
logger = logging.getLogger(__name__)

class SlackHandler:
    """Handler for Slack events."""
    
    def __init__(self, app: App, storage: StorageInterface, knowledge_base: KnowledgeBaseInterface) -> None:
        """
        Initialize Slack handler with app, storage, and knowledge base.
        
        Args:
            app: Slack Bolt app instance
            storage: Storage implementation for persisting conversation context
            knowledge_base: Knowledge base implementation for answering queries
        """
        self.app = app
        self.storage = storage
        self.knowledge_base = knowledge_base
        self.client = app.client
    
    def register_handlers(self) -> App:
        """
        Register event handlers with the Slack app.
        
        Returns:
            The Slack Bolt app instance with handlers registered
        """
        # Register app_mention handler
        self.app.event("app_mention")(self.handle_app_mention)
        
        # Register message handler for DMs if enabled
        if config.enable_dm:
            self.app.message()(self.handle_message)
        
        logger.info("Registered Slack event handlers")
        return self.app
    
    def handle_app_mention(self, event: Dict[str, Any], say: Callable) -> None:
        """
        Handle app_mention events.
        
        Args:
            event: Slack event data
            say: Function to send a message to the channel
        """
        # Extract message details
        channel = event.get("channel")
        thread_ts = event.get("thread_ts") or event.get("ts")
        user_id = event.get("user")
        text = event.get("text")
        event_ts = event.get("ts")  # Use ts for the specific message, not thread_ts
        
        logger.info(f"Processing app_mention event: channel={channel}, ts={event_ts}, thread_ts={thread_ts}")
        
        # Process the message
        self._process_message(channel, thread_ts, user_id, text, say, message_ts=event_ts)
    
    def handle_message(self, message: Dict[str, Any], say: Callable) -> None:
        """
        Handle direct message events.
        
        Args:
            message: Slack message data
            say: Function to send a message to the channel
        """
        # Only process DM messages
        channel_type = message.get("channel_type")
        if channel_type != "im":
            return
        
        # Extract message details
        channel = message.get("channel")
        thread_ts = message.get("thread_ts") or message.get("ts")
        user_id = message.get("user")
        text = message.get("text")
        event_ts = message.get("ts")  # Use ts for the specific message
        
        logger.info(f"Processing DM message event: channel={channel}, ts={event_ts}, thread_ts={thread_ts}")
        
        # Process the message
        self._process_message(channel, thread_ts, user_id, text, say, message_ts=event_ts)
    
    def _is_duplicate_event(self, event: Dict[str, Any]) -> bool:
        """
        Check if this is a duplicate event using event timestamp.
        
        Args:
            event: Slack event data
            
        Returns:
            True if the event is a duplicate, False otherwise
        """
        # Get primary event identifier
        event_id = event.get("event_ts") or event.get("ts")
        if not event_id:
            logger.warning("Event has no timestamp identifier, cannot deduplicate")
            return False
        
        # Check if we've seen this event before
        if self.storage.has_seen_event(event_id):
            logger.info(f"Detected duplicate event: {event_id}")
            return True
        
        # Mark event as seen
        self.storage.mark_event_seen(event_id)
        logger.info(f"New event marked as seen: {event_id}")
        return False
    
    def _check_bot_already_responded(self, channel: str, thread_ts: str) -> bool:
        """
        Check if the bot has already responded in the thread.
        
        Args:
            channel: Slack channel ID
            thread_ts: Thread timestamp
            
        Returns:
            True if the bot has already responded, False otherwise
        """
        try:
            # Get bot user ID
            bot_info = self.client.auth_test()
            bot_user_id = bot_info["user_id"]
            
            # Get replies in the thread
            response = self.client.conversations_replies(
                channel=channel,
                ts=thread_ts
            )
            
            # Check if any messages in the thread are from the bot
            if response and response.get('messages'):
                for message in response.get('messages', []):
                    # Skip the first message (the original message)
                    if message.get('ts') == thread_ts:
                        continue
                        
                    # Check if this message is from the bot
                    if message.get('user') == bot_user_id:
                        logger.info(f"Found existing bot response in thread {thread_ts}")
                        return True
            
            return False
        except Exception as e:
            logger.error(f"Error checking for bot responses: {e}")
            # If there's an error, assume no response to be safe
            return False
    
    def _process_message(self, channel: str, thread_ts: str, user_id: str, 
                        text: str, say: Callable, message_ts: str = None) -> None:
        """
        Process a message and generate a response.
        
        Args:
            channel: Slack channel ID
            thread_ts: Thread timestamp for threading replies
            user_id: User ID of the message sender
            text: Message text
            say: Function to send a message to the channel
            message_ts: Timestamp of the specific message to react to (may differ from thread_ts)
        """
        # Use message_ts if provided, otherwise fall back to thread_ts
        # This ensures we react to the specific message, not just the thread parent
        reaction_ts = message_ts if message_ts else thread_ts
        
        # Generate thread key for context storage
        thread_key = f"{channel}_{thread_ts}"
        
        logger.info(f"Processing message in channel {channel}, thread {thread_ts}, from user {user_id}")
        
        # Add thinking reaction to the specific message
        try:
            self.client.reactions_add(
                channel=channel,
                timestamp=reaction_ts,
                name="thinking_face"
            )
            logger.info(f"Added thinking_face reaction to message {reaction_ts}")
        except SlackApiError as e:
            logger.warning(f"Error adding thinking reaction: {e}")
        
        try:
            # Extract query from text (remove mentions)
            query = re.sub(r'<@[A-Z0-9]+>', '', text).strip()
            logger.info(f"Extracted query: {query}")
            
            # Get context from storage
            context = self.storage.get_context(thread_key)
            context_summary = context.get("summary") if context else None
            session_id = context.get("session_id") if context else None
            
            # Query knowledge base
            start_time = time.time()
            response, new_session_id = self.knowledge_base.query(
                query, 
                session_id=session_id,
                context_summary=context_summary
            )
            end_time = time.time()
            logger.info(f"Knowledge base query completed in {end_time - start_time:.2f} seconds")
            
            # Update context with new session ID and append to history
            if not context:
                context = {
                    "session_id": new_session_id,
                    "history": [],
                    "summary": ""
                }
            
            # Update session ID if it changed
            if new_session_id and new_session_id != session_id:
                context["session_id"] = new_session_id
            
            # Append to history
            context["history"].append({
                "query": query,
                "response": response,
                "timestamp": int(time.time())
            })
            
            # Generate summary (simple for now, just the last few exchanges)
            history_text = ""
            for entry in context["history"][-3:]:  # Last 3 exchanges
                history_text += f"User: {entry['query']}\nAssistant: {entry['response']}\n\n"
            context["summary"] = history_text[:config.context_summary_length]
            
            # Store updated context
            self.storage.store_context(thread_key, context)
            
            # Send response
            say(text=response, thread_ts=thread_ts)
            logger.info(f"Successfully sent response to thread {thread_ts}")
            
            # Log performance
            logger.info(f"Query processed in {end_time - start_time:.2f} seconds")
            
            # Remove thinking reaction and add done reaction to the specific message
            try:
                self.client.reactions_remove(
                    channel=channel,
                    timestamp=reaction_ts,
                    name="thinking_face"
                )
                self.client.reactions_add(
                    channel=channel,
                    timestamp=reaction_ts,
                    name="white_check_mark"
                )
                logger.info(f"Added white_check_mark reaction to message {reaction_ts}")
            except SlackApiError as e:
                logger.warning(f"Error updating reactions: {e}")
                
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            
            # Remove thinking reaction and add error reaction to the specific message
            try:
                self.client.reactions_remove(
                    channel=channel,
                    timestamp=reaction_ts,
                    name="thinking_face"
                )
                self.client.reactions_add(
                    channel=channel,
                    timestamp=reaction_ts,
                    name="x"
                )
            except SlackApiError as reaction_error:
                logger.warning(f"Error updating reactions: {reaction_error}")
            
            # Send error message
            try:
                say(text="Sorry, I encountered an error while processing your request. Please try again later.", 
                    thread_ts=thread_ts)
            except Exception as say_error:
                logger.error(f"Error sending error message: {say_error}", exc_info=True)