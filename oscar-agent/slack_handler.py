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
import threading
import queue
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import slack_bolt
from slack_bolt import App
from slack_sdk.errors import SlackApiError

from config import config
from oscar_agent import OSCARAgentInterface
from storage import StorageInterface

logger = logging.getLogger(__name__)
channel_allow_list = ['C096MV7JZ0T', 'C09827S7CEB', 'C091EH1JKCL', 'C088XMSH4DA']

# Authorized users for automated message sending functionality --> Rishabh, Sayali, Prudhvi, Divyam, Peter, Saurabh (Not in order with respect to the below)
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
        
        # Thread pool for better scaling (50-100 concurrent users)
        self.executor = ThreadPoolExecutor(max_workers=50, thread_name_prefix="oscar-agent")
        
        # Track active queries for rate limiting
        self.active_queries = {}
        self.monitor_lock = threading.Lock()
        
 
    
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
        
        # Register slash command handlers for message orchestration
        self.app.command("/oscar-announce")(self.handle_announce_command)
        self.app.command("/oscar-assign-owner")(self.handle_assign_owner_command)
        self.app.command("/oscar-request-owner")(self.handle_request_owner_command)
        self.app.command("/oscar-rc-details")(self.handle_rc_details_command)
        self.app.command("/oscar-missing-notes")(self.handle_missing_notes_command)
        
        logger.info("Registered Slack event handlers and slash commands for OSCAR agent")
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
    
    def _attempt_bedrock_cancellation(self, session_id: str) -> None:
        """
        Attempt to cancel a Bedrock agent session.
        Note: This may not immediately stop the agent but can help with resource cleanup.
        """
        if not session_id:
            return
            
        try:
            # There's no direct "cancel" API for Bedrock agents, but we can try:
            # 1. End the session (if the agent supports it)
            # 2. Log the cancellation attempt for monitoring
            logger.warning(f"Attempting to cancel Bedrock session: {session_id}")
            
            # Note: Bedrock agents don't have a direct cancellation API
            # The session will eventually timeout on AWS side
            # This is mainly for logging and future enhancement
            
        except Exception as e:
            logger.error(f"Failed to cancel Bedrock session {session_id}: {e}")
    

    def _query_agent_with_timeout(self, query: str, session_id: str, context_summary: str, 
                                 channel: str, reaction_ts: str, start_time: float,
                                 hourglass_threshold: float, timeout_threshold: float,
                                 say: Callable, thread_ts: str, user_id: str) -> tuple:
        """
        Query the agent with timeout monitoring using simple threading with limits.
        """
        
        # Simple system overload protection
        query_id = f"{channel}_{thread_ts}_{int(start_time)}"
        
        with self.monitor_lock:
            if len(self.active_queries) >= 50:
                self._manage_reactions(channel, reaction_ts, add_reaction="x", remove_reaction="thinking_face")
                say(text="🚫 System is currently overloaded. Please try again in a few minutes.", thread_ts=thread_ts)
                return None, None
            
            # Register query for timeout tracking only
            self.active_queries[query_id] = {
                'start_time': start_time,
                'user_id': user_id,
                'cancelled': False
            }
        
        result_queue = queue.Queue()
        hourglass_added = False
        
        def agent_worker():
            try:
                # Check if cancelled before starting
                with self.monitor_lock:
                    if self.active_queries.get(query_id, {}).get('cancelled'):
                        result_queue.put(("cancelled", "Query was cancelled", None))
                        return
                
                # Test delay for timeout verification (remove in production)
                import os
                if os.getenv('OSCAR_TEST_TIMEOUT') == 'true':
                    logger.warning(f"TEST MODE: Adding 60s delay to test timeout for query {query_id}")
                    time.sleep(60)  # This will trigger timeout
                
                response, new_session_id = self.oscar_agent.query(
                    query, session_id=session_id, context_summary=context_summary
                )
                result_queue.put(("success", response, new_session_id))
            except Exception as e:
                result_queue.put(("error", str(e), None))
        
        # Start agent in background thread
        thread = threading.Thread(target=agent_worker, daemon=True)
        thread.start()
        
        # Monitor every 10 seconds for better timing accuracy
        while thread.is_alive():
            try:
                # Wait 10 seconds for result
                status, response, new_session_id = result_queue.get(timeout=10)
                
                # Clean up on success
                with self.monitor_lock:
                    self.active_queries.pop(query_id, None)
                
                if status == "success":
                    return response, new_session_id
                elif status == "cancelled":
                    logger.warning(f"Query {query_id} was cancelled")
                    return None, None
                else:
                    raise Exception(response)
                    
            except queue.Empty:
                # Check elapsed time
                elapsed = time.time() - start_time
                logger.info(f"TIMEOUT CHECK: Query {query_id} still running after {elapsed:.2f}s (hourglass_added={hourglass_added})")
                
                # Add hourglass at 30s
                if elapsed >= hourglass_threshold and not hourglass_added:
                    logger.warning(f"ADDING HOURGLASS: After {elapsed:.2f}s for query {query_id}")
                    try:
                        self._manage_reactions(channel, reaction_ts, add_reaction="hourglass_flowing_sand")
                        hourglass_added = True
                        logger.warning(f"HOURGLASS ADDED SUCCESSFULLY for {query_id}")
                    except Exception as e:
                        logger.error(f"FAILED TO ADD HOURGLASS: {e}")
                
                # Timeout at 50s
                if elapsed >= timeout_threshold:
                    logger.error(f"TIMEOUT TRIGGERED: Query {query_id} timed out after {elapsed:.2f}s")
                    
                    # Force thread termination attempt (though this won't stop Bedrock)
                    logger.warning(f"Thread still alive: {thread.is_alive()}, attempting cleanup")
                    
                    # Mark as cancelled and attempt to stop Bedrock session
                    with self.monitor_lock:
                        query_info = self.active_queries.get(query_id)
                        if query_info:
                            query_info['cancelled'] = True
                            # Attempt to cancel Bedrock session if possible
                            self._attempt_bedrock_cancellation(query_info.get('session_id'))
                        self.active_queries.pop(query_id, None)
                    
                    try:
                        self._manage_reactions(channel, reaction_ts, add_reaction="x", 
                                             remove_reaction=["thinking_face", "hourglass_flowing_sand"])
                        say(text="⏱️ Your request took too long and timed out. Please try a simpler question.", 
                            thread_ts=thread_ts)
                        logger.warning(f"TIMEOUT HANDLED SUCCESSFULLY for {query_id}")
                    except Exception as e:
                        logger.error(f"FAILED TO HANDLE TIMEOUT: {e}")
                    
                    # Break out of monitoring loop and return None
                    return None, None
        
        # Get final result if thread finished normally
        try:
            if not result_queue.empty():
                status, response, new_session_id = result_queue.get_nowait()
                
                # Clean up
                with self.monitor_lock:
                    self.active_queries.pop(query_id, None)
                
                if status == "success":
                    return response, new_session_id
                elif status == "cancelled":
                    return None, None
                else:
                    raise Exception(response)
        except queue.Empty:
            pass
        
        # Clean up
        with self.monitor_lock:
            self.active_queries.pop(query_id, None)
        
        # Thread finished but no result - this shouldn't happen
        logger.error(f"Agent thread finished without result for query {query_id}")
        return None, None
    
    def _process_message(self, channel: str, thread_ts: str, user_id: str, 
                        text: str, say: Callable, message_ts: str = None, slash_command: str = None) -> None:
        """
        Process a message and generate a response using the OSCAR agent.
        
        Args:
            channel: Slack channel ID
            thread_ts: Thread timestamp for threading replies
            user_id: User ID of the message sender
            text: Message text (for slash commands, this is the channel parameter)
            say: Function to send a message to the channel
            message_ts: Timestamp of the specific message to react to (may differ from thread_ts)
            slash_command: Type of slash command if this is a slash command invocation
        """
        # Use message_ts if provided, otherwise fall back to thread_ts
        # This ensures we react to the specific message, not just the thread parent
        reaction_ts = message_ts if message_ts else thread_ts
        
        # Generate thread key for context storage
        thread_key = f"{channel}_{thread_ts}"
        
        logger.info(f"Processing message in channel {channel}, thread {thread_ts}, from user {user_id}")
        
        # Add thinking reaction to the specific message
        self._manage_reactions(channel, reaction_ts, add_reaction="thinking_face")
        
        # Set timeout thresholds 
        hourglass_threshold = 45  # seconds
        timeout_threshold = 120    # seconds
        start_time = time.time()
        
        try:
            # Extract or generate query based on source
            if slash_command:
                # For slash commands, generate query from template
                query_template = self.AGENT_QUERIES.get(slash_command)
                if not query_template:
                    self._manage_reactions(channel, reaction_ts, add_reaction="x", remove_reaction="thinking_face")
                    say(text="❌ Unknown slash command type", thread_ts=thread_ts)
                    return
                # text contains "channel version", split them
                params = text.split()
                if len(params) >= 2:
                    channel_param = params[0]
                    version_param = params[1]
                    query = query_template.format(channel=channel_param, version=version_param)
                else:
                    query = query_template.format(channel=text, version="latest")
                logger.info(f"Generated slash command query: {query}")
            else:
                # For regular messages, extract query from text (remove mentions)
                query = self._extract_query(text)
                logger.info(f"Extracted query: {query}")
            
            # Check for automated message sending requests (skip for slash commands as they're pre-authorized)
            if not slash_command and self._is_message_sending_request(query):
                if not self._is_user_authorized_for_messaging(user_id):
                    logger.warning(f"Unauthorized message sending attempt by user {user_id}")
                    self._manage_reactions(channel, reaction_ts, add_reaction="x", remove_reaction="thinking_face")
                    say(text="❌ You are not authorized to use automated message sending functionality. If this was erroneous, try a prompt without keywords like 'message', 'notification', or 'ping'.", thread_ts=thread_ts)
                    return
                
                logger.info(f"Processing automated message sending request from authorized user {user_id}")
                # Continue with normal agent processing - agent will handle message sending via action group
            
            # Get context from storage
            context = self.storage.get_context(thread_key)
            context_summary = context.get("summary") if context else None
            session_id = context.get("session_id") if context else None
            
            # Query OSCAR agent with timeout monitoring
            response, new_session_id = self._query_agent_with_timeout(
                query, session_id, context_summary, channel, reaction_ts, 
                start_time, hourglass_threshold, timeout_threshold, say, thread_ts, user_id
            )
            
            # If timeout occurred, response will be None
            if response is None:
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
            
            # Add success reaction and remove processing reactions
            self._manage_reactions(
                channel, 
                reaction_ts, 
                add_reaction="white_check_mark", 
                remove_reaction=["thinking_face", "hourglass_flowing_sand"]
            )
                
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            
            # Update reactions: remove processing reactions, add x
            self._manage_reactions(
                channel, 
                reaction_ts, 
                add_reaction="x", 
                remove_reaction=["thinking_face", "hourglass_flowing_sand"]
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
            'message', 'release notes message', 'ping people', 'ping'
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
    
    # Predefined agent queries for direct invocation
    AGENT_QUERIES = {
        "announce": "Send a release announcement message to channel {channel} using the release-announcement template for version {version}. Ensure the template is filled out correctly.",
        "assign_owner": "Send a release owner assignment message to channel {channel} using the release-owner-assignment template for version {version}. Make sure to ping any relevant people and ensure the template is filled out correctly.",
        "request_owner": "Send a request for release owner message to channel {channel} using the request-release-owner template for version {version}. Make sure to ping any relevant people and ensure the template is filled out correctly.",
        "rc_details": "Send RC details message to channel {channel} using the rc-details template for version {version} release candidate. Ensure the template is filled out correctly and fully.",
        "missing_notes": "Send a missing release notes message to channel {channel} using the missing-release-notes template for version {version}. Ensure all relevant maintainers are pinged and the template is filled out correctly."
    }
    
    def handle_announce_command(self, ack, command, say):
        """Handle /announce slash command."""
        self._handle_slash_command(ack, command, say, "announce")
    
    def handle_assign_owner_command(self, ack, command, say):
        """Handle /assign-owner slash command."""
        self._handle_slash_command(ack, command, say, "assign_owner")
    
    def handle_request_owner_command(self, ack, command, say):
        """Handle /request-owner slash command."""
        self._handle_slash_command(ack, command, say, "request_owner")
    
    def handle_rc_details_command(self, ack, command, say):
        """Handle /rc-details slash command."""
        self._handle_slash_command(ack, command, say, "rc_details")
    
    def handle_missing_notes_command(self, ack, command, say):
        """Handle /missing-notes slash command."""
        self._handle_slash_command(ack, command, say, "missing_notes")
    
    def _handle_slash_command(self, ack, command, say, slash_command_type: str):
        """Handle slash commands by delegating to _process_message."""
        ack()
        
        user_id = command.get('user_id')
        params = command.get('text', '').strip().split()
        
        # Check authorization
        if not self._is_user_authorized_for_messaging(user_id):
            say(text="❌ You are not authorized to use OSCAR slash commands.", response_type="ephemeral")
            return
        
        # Require channel and version parameters
        if len(params) != 2:
            say(text=f"❌ Usage: `/{slash_command_type.replace('_', '-')} <channel_id_or_name> <version>`", response_type="ephemeral")
            return
        
        channel_param = params[0]
        version_param = params[1]
        
        # Create synthetic parameters and delegate to _process_message
        channel_id = command.get('channel_id')
        thread_ts = str(int(time.time()))
        
        # Pass both channel and version as combined parameters
        combined_params = f"{channel_param} {version_param}"
        
        # Delegate to _process_message with slash_command parameter
        self._process_message(channel_id, thread_ts, user_id, combined_params, say, thread_ts, slash_command_type)