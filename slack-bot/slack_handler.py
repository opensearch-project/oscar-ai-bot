"""
Slack event handler module for OSCAR.

This module provides the SlackHandler class for handling Slack events.
"""

import logging
import time
import re
from slack_sdk.errors import SlackApiError

from .config import config
from .storage import get_storage
from .bedrock import get_knowledge_base

# Configure logging
logger = logging.getLogger(__name__)

class SlackHandler:
    """Handler for Slack events."""
    
    def __init__(self, app, storage, knowledge_base):
        """Initialize Slack handler with app, storage, and knowledge base."""
        self.app = app
        self.storage = storage
        self.knowledge_base = knowledge_base
        self.client = app.client
    
    def register_handlers(self):
        """Register event handlers with the Slack app."""
        # Register app_mention handler
        self.app.event("app_mention")(self.handle_app_mention)
        
        # Register message handler for DMs if enabled
        if config.enable_dm:
            self.app.message()(self.handle_message)
        
        logger.info("Registered Slack event handlers")
    
    def handle_app_mention(self, event, say):
        """Handle app_mention events."""
        # Extract message details
        channel = event.get("channel")
        thread_ts = event.get("thread_ts") or event.get("ts")
        user_id = event.get("user")
        text = event.get("text")
        
        # Check if this is a duplicate event
        if self._is_duplicate_event(event):
            logger.info(f"Ignoring duplicate event: {event.get('event_ts')}")
            return
        
        # Process the message
        self._process_message(channel, thread_ts, user_id, text, say)
    
    def handle_message(self, message, say):
        """Handle direct message events."""
        # Only process DM messages
        channel_type = message.get("channel_type")
        if channel_type != "im":
            return
        
        # Extract message details
        channel = message.get("channel")
        thread_ts = message.get("thread_ts") or message.get("ts")
        user_id = message.get("user")
        text = message.get("text")
        
        # Check if this is a duplicate event
        if self._is_duplicate_event(message):
            logger.info(f"Ignoring duplicate event: {message.get('event_ts')}")
            return
        
        # Process the message
        self._process_message(channel, thread_ts, user_id, text, say)
    
    def _process_message(self, channel, thread_ts, user_id, text, say):
        """Process a message and generate a response."""
        # Add thinking reaction
        try:
            self.client.reactions_add(
                channel=channel,
                timestamp=thread_ts,
                name="thinking_face"
            )
        except SlackApiError as e:
            logger.warning(f"Error adding thinking reaction: {e}")
        
        # Generate thread key based on channel type
        # For public channels (C), use channel and thread_ts
        # For DMs (D), include user_id to maintain separate contexts
        if channel.startswith("C"):
            thread_key = f"{channel}_{thread_ts}"
        else:
            thread_key = f"{channel}_{thread_ts}_{user_id}"
        
        try:
            # Get context from storage
            context = self.storage.get_context(thread_key)
            context_summary = context.get("summary") if context else None
            session_id = context.get("session_id") if context else None
            
            # Extract query from text (remove mentions)
            query = re.sub(r'<@[A-Z0-9]+>', '', text).strip()
            
            # Query knowledge base
            start_time = time.time()
            response, new_session_id = self.knowledge_base.query(
                query, 
                session_id=session_id,
                context_summary=context_summary
            )
            end_time = time.time()
            
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
            
            # Log performance
            logger.info(f"Query processed in {end_time - start_time:.2f} seconds")
            
            # Remove thinking reaction and add done reaction
            try:
                self.client.reactions_remove(
                    channel=channel,
                    timestamp=thread_ts,
                    name="thinking_face"
                )
                self.client.reactions_add(
                    channel=channel,
                    timestamp=thread_ts,
                    name="white_check_mark"
                )
            except SlackApiError as e:
                logger.warning(f"Error updating reactions: {e}")
                
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            
            # Remove thinking reaction and add error reaction
            try:
                self.client.reactions_remove(
                    channel=channel,
                    timestamp=thread_ts,
                    name="thinking_face"
                )
                self.client.reactions_add(
                    channel=channel,
                    timestamp=thread_ts,
                    name="x"
                )
            except SlackApiError as reaction_error:
                logger.warning(f"Error updating reactions: {reaction_error}")
            
            # Send error message
            say(text="Sorry, I encountered an error while processing your request. Please try again later.", 
                thread_ts=thread_ts)
    
    def _is_duplicate_event(self, event):
        """Check if this is a duplicate event."""
        event_id = event.get("event_ts") or event.get("ts")
        if not event_id:
            return False
        
        # Check if we've seen this event before
        if self.storage.has_seen_event(event_id):
            return True
        
        # Mark this event as seen
        self.storage.mark_event_seen(event_id)
        return False
    
    def _bot_responded(self, channel, thread_ts):
        """Check if the bot has already responded in this thread."""
        try:
            # Get replies in thread
            response = self.client.conversations_replies(
                channel=channel,
                ts=thread_ts
            )
            
            # Check if any messages are from the bot
            bot_id = self.client.auth_test()["bot_id"]
            for message in response.get("messages", []):
                if message.get("bot_id") == bot_id:
                    return True
            
            return False
        except Exception as e:
            logger.error(f"Error checking if bot responded: {e}")
            return False