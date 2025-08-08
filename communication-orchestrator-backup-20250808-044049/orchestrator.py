#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Communication Orchestrator for OSCAR Agent.

This module provides the main orchestrator functionality for automated
messaging to Slack channels for release management notifications.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from config import communication_config
from message_generator import MessageGenerator

logger = logging.getLogger(__name__)

class CommunicationOrchestrator:
    """Main orchestrator for automated release management communications."""
    
    def __init__(self, slack_client: WebClient, region: str = "us-east-1"):
        """Initialize the communication orchestrator.
        
        Args:
            slack_client: Slack WebClient instance
            region: AWS region for AI services
        """
        self.slack_client = slack_client
        self.message_generator = MessageGenerator(region)
    
    def send_notification(
        self, 
        message_type: str, 
        context: Dict[str, Any], 
        channels: Optional[List[str]] = None,
        custom_template: Optional[str] = None,
        mentions: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Send notification to specified channels.
        
        Args:
            message_type: Type of message to send
            context: Context data for message generation
            channels: Optional list of channels to send to (overrides template default)
            custom_template: Optional custom template to use
            mentions: Optional list of mentions to include
            
        Returns:
            Dictionary with send results
        """
        try:
            # Validate message context
            validation_errors = self.message_generator.validate_message_context(message_type, context)
            if validation_errors:
                return {
                    "success": False,
                    "error": f"Validation failed: {', '.join(validation_errors)}",
                    "sent_channels": []
                }
            
            # Generate message
            message = self.message_generator.generate_message(message_type, context, custom_template)
            
            # Determine target channels
            target_channels = channels or communication_config.get_channels_for_template(message_type)
            if not target_channels:
                return {
                    "success": False,
                    "error": f"No channels configured for message type: {message_type}",
                    "sent_channels": []
                }
            
            # Determine mentions
            template = communication_config.get_template(message_type)
            target_mentions = mentions or (template.mentions if template else [])
            
            # Add mentions to message
            if target_mentions:
                mention_text = " ".join(target_mentions)
                message = f"{mention_text}\n\n{message}"
            
            # Send to each channel
            results = []
            sent_channels = []
            
            for channel in target_channels:
                try:
                    # Validate channel permission
                    if not communication_config.is_channel_allowed_for_template(channel, message_type):
                        logger.warning(f"Channel {channel} not allowed for message type {message_type}")
                        results.append({
                            "channel": channel,
                            "success": False,
                            "error": "Channel not allowed for this message type"
                        })
                        continue
                    
                    # Send message
                    response = self.slack_client.chat_postMessage(
                        channel=channel,
                        text=message,
                        unfurl_links=False,
                        unfurl_media=False
                    )
                    
                    results.append({
                        "channel": channel,
                        "success": True,
                        "message_ts": response["ts"]
                    })
                    sent_channels.append(channel)
                    logger.info(f"Successfully sent {message_type} notification to {channel}")
                    
                except SlackApiError as e:
                    error_msg = f"Slack API error: {e.response['error']}"
                    logger.error(f"Failed to send message to {channel}: {error_msg}")
                    results.append({
                        "channel": channel,
                        "success": False,
                        "error": error_msg
                    })
                except Exception as e:
                    error_msg = f"Unexpected error: {str(e)}"
                    logger.error(f"Failed to send message to {channel}: {error_msg}")
                    results.append({
                        "channel": channel,
                        "success": False,
                        "error": error_msg
                    })
            
            return {
                "success": len(sent_channels) > 0,
                "message": message,
                "sent_channels": sent_channels,
                "results": results
            }
            
        except Exception as e:
            logger.error(f"Error in send_notification: {e}")
            return {
                "success": False,
                "error": str(e),
                "sent_channels": []
            }
    
    def list_available_templates(self) -> Dict[str, Any]:
        """List all available message templates.
        
        Returns:
            Dictionary with template information
        """
        templates = {}
        for name, template in communication_config.message_templates.items():
            templates[name] = {
                "description": template.description,
                "channels": template.channels,
                "mentions": template.mentions,
                "priority": template.priority
            }
        
        return {
            "templates": templates,
            "channel_configs": communication_config.channel_configs
        }
    
    def preview_message(
        self, 
        message_type: str, 
        context: Dict[str, Any], 
        custom_template: Optional[str] = None
    ) -> Dict[str, Any]:
        """Preview a message without sending it.
        
        Args:
            message_type: Type of message to preview
            context: Context data for message generation
            custom_template: Optional custom template to use
            
        Returns:
            Dictionary with preview information
        """
        try:
            # Validate message context
            validation_errors = self.message_generator.validate_message_context(message_type, context)
            if validation_errors:
                return {
                    "success": False,
                    "error": f"Validation failed: {', '.join(validation_errors)}"
                }
            
            # Generate message
            message = self.message_generator.generate_message(message_type, context, custom_template)
            
            # Get template info
            template = communication_config.get_template(message_type)
            
            return {
                "success": True,
                "message": message,
                "target_channels": template.channels if template else [],
                "mentions": template.mentions if template else [],
                "priority": template.priority if template else "normal"
            }
            
        except Exception as e:
            logger.error(f"Error in preview_message: {e}")
            return {
                "success": False,
                "error": str(e)
            }

def parse_communication_command(text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    """Parse a communication command from Slack message text.
    
    Args:
        text: The message text to parse
        
    Returns:
        Tuple of (command_type, parameters) or None if not a communication command
    """
    # Remove mentions and clean text
    clean_text = re.sub(r'<@[A-Z0-9]+>', '', text).strip()
    
    # Check for communication command patterns
    patterns = {
        'send_notification': r'/send[_-]?(notification|alert|message)\s+(\w+)(?:\s+(.+))?',
        'list_templates': r'/list[_-]?(templates|types)',
        'preview_message': r'/preview[_-]?(message|notification)\s+(\w+)(?:\s+(.+))?'
    }
    
    for command_type, pattern in patterns.items():
        match = re.search(pattern, clean_text, re.IGNORECASE)
        if match:
            if command_type == 'list_templates':
                return command_type, {}
            elif command_type in ['send_notification', 'preview_message']:
                message_type = match.group(2)
                context_text = match.group(3) if len(match.groups()) >= 3 else ""
                
                # Parse context from remaining text
                context = parse_context_from_text(context_text)
                
                return command_type, {
                    'message_type': message_type,
                    'context': context
                }
    
    return None

def parse_context_from_text(text: str) -> Dict[str, Any]:
    """Parse context parameters from text.
    
    Args:
        text: Text containing context parameters
        
    Returns:
        Dictionary of parsed context
    """
    context = {}
    
    if not text:
        return context
    
    # Simple key=value parsing
    # Example: "build_name=main-build branch=main severity=high"
    pairs = re.findall(r'(\w+)=([^\s]+)', text)
    for key, value in pairs:
        context[key] = value
    
    # Handle JSON-like input
    if '{' in text and '}' in text:
        try:
            import json
            json_match = re.search(r'\{[^}]+\}', text)
            if json_match:
                json_data = json.loads(json_match.group())
                context.update(json_data)
        except json.JSONDecodeError:
            pass
    
    return context