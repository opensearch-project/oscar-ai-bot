#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.

"""
Slack Event Handler for OSCAR Agent.

This module provides comprehensive Slack event handling with agent integration,
including message processing, reaction management, and context preservation.

Classes:
    SlackHandler: Main handler for Slack events with agent integration
"""

import logging
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from slack_bolt import App
from slack_sdk.errors import SlackApiError

from config import config
from oscar_agent import OSCARAgentInterface
from storage import StorageInterface

logger = logging.getLogger(__name__)
channel_allow_list = ['C096MV7JZ0T', 'C09827S7CEB', 'C091EH1JKCL', 'C088XMSH4DA']

# Authorized users for automated message sending functionality --> Rishabh, Sayali, Prudhvi, Divyam, Peter, Saurabh
AUTHORIZED_MESSAGE_SENDERS = ['U091B0QH1QD', 'W017PN2ADN0', 'W017VV9TD33', 'W017VPMPKH7', 'W017PKU06CC', 'U032Q5N0HTM']

class SlackHandler:
    """Comprehensive Slack event handler with OSCAR agent integration.
    
    This class manages all Slack interactions including:
    - Event registration and processing
    - Message parsing and query extraction
    - Agent invocation and response handling
    - Reaction management for user feedback
    - Context preservation across conversations
    """
    
    def __init__(
        self, 
        app: App, 
        storage: StorageInterface, 
        oscar_agent: OSCARAgentInterface
    ) -> None:
        """Initialize Slack handler with required dependencies.
        
        Args:
            app: Slack Bolt app instance
            storage: Storage implementation for conversation context
            oscar_agent: OSCAR agent implementation for query processing
        """
        self.app = app
        self.storage = storage
        self.oscar_agent = oscar_agent
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
        
        logger.info("Registered Slack event handlers for OSCAR agent")
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
        if channel not in channel_allow_list:
            logger.info(f"Channel {channel} not in allow list, ignoring event")
            return
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
    
    def _extract_query(self, text: str) -> str:
        """
        Extract the query from the message text by removing mentions.
        
        Args:
            text: The raw message text
            
        Returns:
            The cleaned query text
        """
        # Remove mentions (e.g., <@U12345>)
        query = re.sub(r'<@[A-Z0-9]+>', '', text).strip()
        return query
    
    def _update_context(self, thread_key: str, query: str, response: str, 
                       session_id: Optional[str], new_session_id: Optional[str]) -> Dict[str, Any]:
        """
        Update the conversation context with the new query and response.
        
        Args:
            thread_key: The unique key for the thread
            query: The user's query
            response: The agent's response
            session_id: The current session ID
            new_session_id: The new session ID from the agent
            
        Returns:
            The updated context
        """
        # Get existing context or create a new one
        context = self.storage.get_context(thread_key)
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
        
        return context
    
    def _manage_reactions(self, channel: str, timestamp: str, add_reaction: Optional[str] = None, 
                         remove_reaction: Optional[Union[str, List[str]]] = None) -> None:
        """
        Add or remove reactions from a message.
        
        Args:
            channel: The Slack channel ID
            timestamp: The message timestamp
            add_reaction: The reaction to add (optional)
            remove_reaction: The reaction(s) to remove (optional, can be a string or list of strings)
        """
        try:
            # Remove reaction(s) if specified
            if remove_reaction:
                # Handle both single reaction and list of reactions
                reactions_to_remove = [remove_reaction] if isinstance(remove_reaction, str) else remove_reaction
                
                for reaction in reactions_to_remove:
                    try:
                        self.client.reactions_remove(
                            channel=channel,
                            timestamp=timestamp,
                            name=reaction
                        )
                        logger.info(f"Removed {reaction} reaction from message {timestamp}")
                    except SlackApiError as e:
                        # Ignore errors for reactions that don't exist
                        if "no_reaction" in str(e):
                            logger.debug(f"Reaction {reaction} not found on message {timestamp}")
                        else:
                            logger.warning(f"Error removing reaction {reaction}: {e}")
            
            # Add reaction if specified
            if add_reaction:
                try:
                    self.client.reactions_add(
                        channel=channel,
                        timestamp=timestamp,
                        name=add_reaction
                    )
                    logger.info(f"Added {add_reaction} reaction to message {timestamp}")
                except SlackApiError as e:
                    # Ignore errors for reactions that already exist
                    if "already_reacted" in str(e):
                        logger.debug(f"Reaction {add_reaction} already exists on message {timestamp}")
                    else:
                        logger.warning(f"Error adding reaction {add_reaction}: {e}")
        except Exception as e:
            logger.warning(f"Error managing reactions: {e}")
    
    def _process_message(self, channel: str, thread_ts: str, user_id: str, 
                        text: str, say: Callable, message_ts: str = None) -> None:
        """
        Process a message and generate a response using the OSCAR agent.
        
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
        self._manage_reactions(channel, reaction_ts, add_reaction="thinking_face")
        
        # Set timeout threshold (60 seconds)
        timeout_threshold = 60
        start_time = time.time()
        
        try:
            # Extract query from text (remove mentions)
            query = self._extract_query(text)
            logger.info(f"Extracted query: {query}")
            
            # Check for automated message sending requests
            if self._is_message_sending_request(query):
                if not self._is_user_authorized_for_messaging(user_id):
                    logger.warning(f"Unauthorized message sending attempt by user {user_id}")
                    self._manage_reactions(channel, reaction_ts, add_reaction="x", remove_reaction="thinking_face")
                    say(text="❌ You are not authorized to use automated message sending functionality.", thread_ts=thread_ts)
                    return
                
                logger.info(f"Processing automated message sending request from authorized user {user_id}")
                # Continue with normal agent processing - agent will handle message sending via action group
            
            # Get context from storage
            context = self.storage.get_context(thread_key)
            context_summary = context.get("summary") if context else None
            session_id = context.get("session_id") if context else None
            
            # Check if we're approaching timeout before querying agent
            current_time = time.time()
            if current_time - start_time > timeout_threshold * 0.3:  # 30% of timeout threshold
                # Add hourglass emoji to indicate potential slow response
                self._manage_reactions(channel, reaction_ts, add_reaction="hourglass_flowing_sand")
            
            # Query OSCAR agent with timeout handling
            agent_start_time = time.time()
            
            # Check if we've already exceeded timeout before starting agent query
            if agent_start_time - start_time > timeout_threshold:
                logger.warning(f"Timeout exceeded before agent query: {agent_start_time - start_time:.2f}s")
                self._manage_reactions(channel, reaction_ts, add_reaction="stopwatch", remove_reaction=["thinking_face", "hourglass_flowing_sand"])
                say(text="⏱️ Your query is taking longer than expected and has timed out. Please try a simpler question or try again later.", thread_ts=thread_ts)
                return
            
            response, new_session_id = self.oscar_agent.query(
                query, 
                session_id=session_id,
                context_summary=context_summary
            )
            agent_end_time = time.time()
            logger.info(f"OSCAR agent query completed in {agent_end_time - agent_start_time:.2f} seconds")
            
            # Check if agent query exceeded timeout
            if agent_end_time - start_time > timeout_threshold:
                logger.warning(f"Agent query exceeded timeout: {agent_end_time - start_time:.2f}s")
                self._manage_reactions(channel, reaction_ts, add_reaction="stopwatch", remove_reaction=["thinking_face", "hourglass_flowing_sand"])
                say(text="⏱️ Your query took longer than expected to complete. The response may be incomplete. Please try a simpler question.", thread_ts=thread_ts)
                return
            
            # Validate response - handle None, empty, or whitespace-only responses
            if response is None:
                logger.warning(f"OSCAR agent returned None response for query: {query}")
                response = "I'm having trouble generating a response right now. Please try again."
            elif not response or response.strip() == "":
                logger.warning(f"OSCAR agent returned empty response for query: {query}")
                response = "I'm having trouble generating a response right now. Please try again."
            else:
                # Ensure response is a string
                response = str(response).strip()
            
            # Update context with new query and response
            self._update_context(thread_key, query, response, session_id, new_session_id)
            
            # Send response
            say(text=response, thread_ts=thread_ts)
            logger.info(f"Successfully sent response to thread {thread_ts}")
            
            # Log performance
            end_time = time.time()
            total_elapsed = end_time - start_time
            logger.info(f"Query processed in {total_elapsed:.2f} seconds")
            
            # Update reactions based on processing time
            reactions_to_remove = ["thinking_face", "hourglass_flowing_sand"]
            if total_elapsed > timeout_threshold:
                # Keep stopwatch reaction if it was a slow response
                logger.info(f"Response took longer than timeout threshold: {total_elapsed:.2f}s > {timeout_threshold}s")
            else:
                # Remove stopwatch if it was added
                reactions_to_remove.append("stopwatch")
                
            # Add success reaction and remove processing reactions
            self._manage_reactions(
                channel, 
                reaction_ts, 
                add_reaction="white_check_mark", 
                remove_reaction=reactions_to_remove
            )
                
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            
            # Update reactions: remove processing reactions, add x
            self._manage_reactions(
                channel, 
                reaction_ts, 
                add_reaction="x", 
                remove_reaction=["thinking_face", "hourglass_flowing_sand", "stopwatch"]
            )
            
            # Send user-friendly error message based on error type
            try:
                error_str = str(e).lower()
                if 'throttl' in error_str or 'rate' in error_str:
                    error_message = "I'm currently experiencing high load. Please wait a moment and try again."
                elif 'timeout' in error_str:
                    error_message = "Your request is taking longer than expected. Please try a simpler question."
                elif 'nonetype' in error_str:
                    error_message = "I'm having trouble generating a response. Please try rephrasing your question."
                else:
                    error_message = "Sorry, I encountered an error while processing your request. Please try again later."
                
                # Ensure error_message is not None
                if error_message is None or error_message.strip() == "":
                    error_message = "An unexpected error occurred. Please try again."
                    
                say(text=error_message, thread_ts=thread_ts)
            except Exception as say_error:
                logger.error(f"Error sending error message: {say_error}", exc_info=True)
                # Last resort - try to send a basic message
                try:
                    say(text="Error occurred. Please try again.", thread_ts=thread_ts)
                except:
                    logger.error("Failed to send any error message to Slack")
    
    def _is_message_sending_request(self, query: str) -> bool:
        """Check if the query is requesting automated message sending.
        
        Args:
            query: The user's query
            
        Returns:
            True if this is a message sending request
        """
        query_lower = query.lower()
        message_keywords = [
            'send message', 'send notification', 'send alert', 'post message',
            'notify channel', 'send to channel', 'message channel',
            'missing release notes', 'release notes message', 'ping people'
        ]
        
        return any(keyword in query_lower for keyword in message_keywords)
    
    def _is_user_authorized_for_messaging(self, user_id: str) -> bool:
        """Check if user is authorized for automated message sending.
        
        Args:
            user_id: Slack user ID
            
        Returns:
            True if user is authorized
        """
        return user_id in AUTHORIZED_MESSAGE_SENDERS
    
    def send_slack_message(self, channel: str, message: str) -> Dict[str, Any]:
        """Send a message to a Slack channel.
        
        This method is called by the supervisor agent's action group function.
        
        Args:
            channel: Target Slack channel ID or name
            message: Message content to send
            
        Returns:
            Dictionary with send result
        """
        try:
            # Validate channel is in allow list
            if channel not in channel_allow_list:
                return {
                    "success": False,
                    "error": f"Channel {channel} not in allow list"
                }
            
            # Send message
            response = self.client.chat_postMessage(
                channel=channel,
                text=message,
                unfurl_links=False,
                unfurl_media=False
            )
            
            logger.info(f"Successfully sent automated message to channel {channel}")
            return {
                "success": True,
                "channel": channel,
                "message_ts": response["ts"]
            }
            
        except SlackApiError as e:
            error_msg = f"Slack API error: {e.response['error']}"
            logger.error(f"Failed to send message to {channel}: {error_msg}")
            return {
                "success": False,
                "error": error_msg
            }
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"Failed to send message to {channel}: {error_msg}")
            return {
                "success": False,
                "error": error_msg
            }