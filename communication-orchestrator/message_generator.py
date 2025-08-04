#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Message Generator for Communication Orchestrator.

This module handles AI-powered message generation and template processing
for automated release management notifications.
"""

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

from config import communication_config, MessageTemplate

logger = logging.getLogger(__name__)

class MessageGenerator:
    """Generates contextual messages using AI and templates."""
    
    def __init__(self, region: str = "us-east-1"):
        """Initialize the message generator.
        
        Args:
            region: AWS region for Bedrock service
        """
        self.region = region
        self.bedrock_client = boto3.client('bedrock-runtime', region_name=region)
        self.model_id = "anthropic.claude-3-5-haiku-20241022-v1:0"
    
    def generate_message(
        self, 
        message_type: str, 
        context: Dict[str, Any], 
        custom_template: Optional[str] = None
    ) -> str:
        """Generate a message using template and AI enhancement.
        
        Args:
            message_type: Type of message to generate
            context: Context data for message generation
            custom_template: Optional custom template to use instead of default
            
        Returns:
            Generated message text
            
        Raises:
            ValueError: If message type is not found
        """
        # Get template
        if custom_template:
            template_text = custom_template
        else:
            template = communication_config.get_template(message_type)
            if not template:
                raise ValueError(f"Unknown message type: {message_type}")
            template_text = template.template
        
        # First, try simple template substitution
        try:
            message = self._apply_template_substitution(template_text, context)
            
            # If AI enhancement is requested or template has placeholders that couldn't be filled
            if context.get('use_ai_enhancement', True) and self._has_unfilled_placeholders(message):
                message = self._enhance_with_ai(message, message_type, context)
            
            return message
            
        except Exception as e:
            logger.error(f"Error generating message: {e}")
            # Fallback to basic template
            return self._generate_fallback_message(message_type, context)
    
    def _apply_template_substitution(self, template: str, context: Dict[str, Any]) -> str:
        """Apply template variable substitution.
        
        Args:
            template: Template string with {variable} placeholders
            context: Context data for substitution
            
        Returns:
            Template with variables substituted
        """
        # Add timestamp if not provided
        if 'timestamp' not in context:
            context['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        
        # Handle special formatting for lists
        formatted_context = context.copy()
        
        # Format task lists
        if 'tasks' in context and isinstance(context['tasks'], list):
            formatted_context['task_list'] = '\n'.join([f"- {task}" for task in context['tasks']])
        
        # Format failed tests
        if 'failed_tests' in context and isinstance(context['failed_tests'], list):
            formatted_context['failed_tests'] = '\n'.join([f"- {test}" for test in context['failed_tests']])
        
        # Format CVE IDs
        if 'cve_ids' in context and isinstance(context['cve_ids'], list):
            formatted_context['cve_ids'] = ', '.join(context['cve_ids'])
        
        try:
            return template.format(**formatted_context)
        except KeyError as e:
            logger.warning(f"Missing template variable: {e}")
            return template
    
    def _has_unfilled_placeholders(self, message: str) -> bool:
        """Check if message still has unfilled placeholders.
        
        Args:
            message: Message to check
            
        Returns:
            True if unfilled placeholders exist
        """
        return bool(re.search(r'\{[^}]+\}', message))
    
    def _enhance_with_ai(self, message: str, message_type: str, context: Dict[str, Any]) -> str:
        """Enhance message using AI.
        
        Args:
            message: Base message to enhance
            message_type: Type of message
            context: Additional context for AI
            
        Returns:
            AI-enhanced message
        """
        try:
            prompt = self._create_enhancement_prompt(message, message_type, context)
            
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1000,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.3
            }
            
            response = self.bedrock_client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(request_body)
            )
            
            response_body = json.loads(response['body'].read())
            enhanced_message = response_body['content'][0]['text'].strip()
            
            logger.info(f"Successfully enhanced message using AI for type: {message_type}")
            return enhanced_message
            
        except Exception as e:
            logger.error(f"Error enhancing message with AI: {e}")
            return message  # Return original message if AI enhancement fails
    
    def _create_enhancement_prompt(self, message: str, message_type: str, context: Dict[str, Any]) -> str:
        """Create prompt for AI message enhancement.
        
        Args:
            message: Base message
            message_type: Type of message
            context: Additional context
            
        Returns:
            Enhancement prompt
        """
        return f"""You are helping to improve an automated notification message for a software release management team.

Message Type: {message_type}
Current Message:
{message}

Additional Context:
{json.dumps(context, indent=2)}

Please improve this message by:
1. Making it more professional and clear
2. Adding relevant technical details if missing
3. Ensuring the tone is appropriate for the urgency level
4. Keeping it concise but informative
5. Maintaining any existing formatting and structure

Return only the improved message, no explanations or additional text."""
    
    def _generate_fallback_message(self, message_type: str, context: Dict[str, Any]) -> str:
        """Generate a basic fallback message.
        
        Args:
            message_type: Type of message
            context: Context data
            
        Returns:
            Basic fallback message
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        
        fallback_messages = {
            "build_failure": f"🚨 Build Failure Alert - {timestamp}\n\nA build has failed and requires attention. Please check the build system for details.",
            "cve_check_failure": f"🔒 Security Alert - {timestamp}\n\nCVE security check has failed. Please review security vulnerabilities immediately.",
            "release_reminder": f"📅 Release Reminder - {timestamp}\n\nUpcoming release tasks require attention. Please check the release schedule.",
            "deployment_status": f"🚀 Deployment Update - {timestamp}\n\nDeployment status update available. Please check deployment systems.",
            "test_failure": f"🧪 Test Failure Alert - {timestamp}\n\nCritical tests have failed. Please investigate and resolve."
        }
        
        return fallback_messages.get(message_type, f"📢 Notification - {timestamp}\n\nAutomated notification from release management system.")
    
    def validate_message_context(self, message_type: str, context: Dict[str, Any]) -> List[str]:
        """Validate that context has required fields for message type.
        
        Args:
            message_type: Type of message to validate
            context: Context to validate
            
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        # Define required fields for each message type
        required_fields = {
            "build_failure": ["build_name", "branch"],
            "cve_check_failure": ["component", "severity"],
            "release_reminder": ["release_version"],
            "deployment_status": ["environment", "status", "version"],
            "test_failure": ["test_suite", "failed_count"]
        }
        
        required = required_fields.get(message_type, [])
        
        for field in required:
            if field not in context or not context[field]:
                errors.append(f"Missing required field: {field}")
        
        return errors