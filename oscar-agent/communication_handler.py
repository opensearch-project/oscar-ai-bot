#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""
Communication Handler for OSCAR Supervisor Agent.

This module provides the Lambda function handler for automated message sending
functionality integrated with the OSCAR supervisor agent.
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Channel allow list for message sending
CHANNEL_ALLOW_LIST = ['C096MV7JZ0T', 'C09827S7CEB', 'C091EH1JKCL', 'C088XMSH4DA']

# Initialize clients
slack_token = os.environ.get('SLACK_BOT_TOKEN')
slack_client = WebClient(token=slack_token) if slack_token else None
bedrock_agent_runtime = boto3.client('bedrock-agent-runtime', region_name='us-east-1')

# Hardcoded message templates from the templates directory
MESSAGE_TEMPLATES = {
    "missing_release_notes": {
        "template": "Hi, </br>\n\nThis component is missing release notes at {branch} ref. Please add them on priority in order to meet the entrance criteria for the release. </br>\nPlease check out the [guidelines](https://github.com/opensearch-project/opensearch-plugins/blob/main/RELEASE_NOTES.md) for the release notes. </br>\n\nThank you!",
        "default_channel": "C096MV7JZ0T"
    },
    "criteria_not_met": {
        "template": "Hi @{release_owner}, </br>\n\nThe below {type_of_criteria} criteria for your component has not been met. </br>\nPlease review the issue and address it with high priority. </br>\n\n{criteria}\n\nThanks!",
        "default_channel": "C096MV7JZ0T"
    },
    "documentation_issues": {
        "template": "Hi @{owner}, </br>\n\nAs part of the [entrance criteria](https://github.com/opensearch-project/.github/blob/main/RELEASING.md#entrance-criteria-to-start-release-window), all the documentation pull requests need to be drafted and in technical review. </br>\n**Since there is no pull request linked to this issue, please take one of the following actions:** </br>\n* Create the pull request and [link it](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue) to this issue. </br>\n* If you already have a pull request created, please [link it](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue) to this issue. </br>\n* If this feature is not targeted for the currently labeled release version, please update the issue with the correct release version. </br>\n\nPlease note: Missing documentation can block the release and cause delays in the overall process. </br>\nThank you!",
        "default_channel": "C096MV7JZ0T"
    },
    "missing_code_coverage": {
        "template": "Hi, </br>\n\n{component_name} is not reporting code-coverage for branch [{branch}]({codecov_url}). </br>\nPlease fix the issue by checking your CI workflow responsible for reporting code coverage. See the details on [code coverage reporting](https://github.com/opensearch-project/opensearch-plugins/blob/main/TESTING.md#code-coverage-reporting) </br>\n\nThank you!",
        "default_channel": "C09827S7CEB"
    },
    "release_announcement": {
        "template": "We're excited to announce the release of OpenSearch {release_version}! :tada:! </br>\n\n• Download: https://opensearch.org/downloads.html </br>\n• Release Notes: https://github.com/opensearch-project/opensearch-build/blob/main/release-notes/opensearch-release-notes-{release_version}.md </br>\n• Documentation: https://opensearch.org/docs/latest/about/ </br>\nFor detailed information about what's new, check out our blog post: https://www.opensearch.org/blog/explore-OpenSearch-2-19/ </br>\n\nThanks everyone for the help to release OpenSearch and OpenSearch Dashboards {release_version}. </br>\nComponent repo owners please create a github release based on the tags of {release_version}.0. </br>\n\nHere is the retrospective issue {release_retro_issue_link} for the release. Please feel free to share your valuable feedback to help us make improvements for the upcoming releases.",
        "default_channel": "C096MV7JZ0T"
    }
}

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for communication orchestration functionality.
    
    Args:
        event: Lambda event containing the action group request
        context: Lambda context
        
    Returns:
        Response for the Bedrock agent
    """
    try:
        logger.info(f"Received event: {json.dumps(event, indent=2)}")
        
        # Extract parameters from the event
        action_group = event.get('actionGroup', '')
        api_path = event.get('apiPath', '')
        function_name = event.get('function', '')
        parameters = event.get('parameters', [])
        
        # Convert parameters list to dictionary
        params = {}
        for param in parameters:
            params[param['name']] = param['value']
        
        logger.info(f"Processing action: {action_group}, path: {api_path}, params: {params}")
        
        # Handle the send_automated_message function
        if function_name == 'send_automated_message':
            logger.info(f"Calling handle_send_message with params: {params}")
            return handle_send_message(params)
        else:
            logger.error(f"Unknown function: {function_name}")
            return {
                "messageVersion": "1.0",
                "response": {
                    "actionGroup": "communication-orchestration",
                    "function": function_name or "unknown",
                    "functionResponse": {
                        "responseBody": {
                            "TEXT": {
                                "body": f'❌ Unknown function: {function_name}'
                            }
                        }
                    }
                }
            }
            
    except Exception as e:
        logger.error(f"Error in lambda_handler: {e}", exc_info=True)
        logger.error(f"Full event: {json.dumps(event, indent=2)}")
        return {
            "messageVersion": "1.0",
            "response": {
                "actionGroup": "communication-orchestration",
                "function": "send_automated_message",
                "functionResponse": {
                    "responseBody": {
                        "TEXT": {
                            "body": f'❌ Internal server error: {str(e)}'
                        }
                    }
                }
            }
        }

def handle_send_message(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle the send_message action.
    
    Args:
        params: Parameters from the agent request
        
    Returns:
        Response for the agent
    """
    try:
        # Extract parameters
        query = params.get('query', '')
        message_content = params.get('message_content', '')
        target_channel = params.get('target_channel', '')
        
        logger.info(f"Processing message request: query='{query}', channel='{target_channel}'")
        logger.info(f"Message content provided: {bool(message_content)}")
        
        # Use provided message content (agent should provide complete message)
        if message_content:
            processed_message = message_content
        else:
            logger.error("No message content provided - agent should fill template with metrics")
            return create_error_response('No message content provided. Agent must provide complete message with metrics data.')
        
        # Extract target channel from query if not provided
        if not target_channel:
            target_channel = extract_channel_from_query(query)
            if not target_channel:
                logger.error(f"Failed to extract channel from query: '{query}'")
                return create_error_response(f'Could not determine target channel from query: "{query}". Please specify channel using #channel-name or channel ID.')
        
        # Validate channel is in allow list
        if target_channel not in CHANNEL_ALLOW_LIST:
            return create_error_response(f'Channel {target_channel} is not in the allowed channels list')
        
        # Send message directly to Slack
        if slack_client:
            try:
                logger.info(f"Sending message to channel {target_channel}: {processed_message[:100]}...")
                response = slack_client.chat_postMessage(
                    channel=target_channel,
                    text=processed_message,
                    unfurl_links=False,
                    unfurl_media=False
                )
                logger.info(f"Slack API response: {response.get('ok')}, ts: {response.get('ts')}")
                result = {
                    'success': True,
                    'message': f'✅ Message sent successfully to channel {target_channel}',
                    'channel': target_channel,
                    'timestamp': response.get('ts')
                }
            except SlackApiError as e:
                logger.error(f"Slack API error: {e.response}")
                result = {
                    'success': False,
                    'error': f'❌ Slack API error: {e.response.get("error", str(e))}'
                }
        else:
            logger.error("Slack client not initialized - missing SLACK_BOT_TOKEN")
            result = {
                'success': False,
                'error': '❌ Slack client not initialized - missing SLACK_BOT_TOKEN'
            }
        
        logger.info(f"Message sending completed: {result}")
        if not result.get('success'):
            logger.error(f"Message sending failed for query '{query}': {result.get('error')}")
        
        # Return proper Bedrock agent response format
        if result.get('success'):
            response_body = f"✅ Message sent successfully to channel {target_channel}"
        else:
            response_body = f"❌ {result.get('error', 'Failed to send message')}"
        
        return {
            "messageVersion": "1.0",
            "response": {
                "actionGroup": "communication-orchestration",
                "function": "send_automated_message",
                "functionResponse": {
                    "responseBody": {
                        "TEXT": {
                            "body": response_body
                        }
                    }
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Error in handle_send_message: {e}", exc_info=True)
        logger.error(f"Query was: '{query}'")
        return create_error_response(f'Error processing message: {str(e)}')

def generate_message_with_metrics(message_type: str, query: str) -> str:
    """
    Generate complete message by collecting metrics and filling template.
    
    Args:
        message_type: Type of message to generate
        query: Original user query
        
    Returns:
        Complete message with real data
    """
    try:
        # Get template
        template_info = MESSAGE_TEMPLATES.get(message_type)
        if not template_info:
            return f"Automated notification: {query}"
        
        template = template_info['template']
        
        # Collect metrics based on message type
        if message_type == 'missing_release_notes':
            metrics_data = collect_release_notes_metrics(query)
        else:
            metrics_data = {}
        
        # Fill template with metrics data
        try:
            formatted_message = template.format(**metrics_data)
            return formatted_message
        except KeyError as e:
            logger.warning(f"Missing template variable {e}, using partial formatting")
            # Leave missing variables as placeholders
            import string
            formatter = string.Formatter()
            formatted_parts = []
            for literal_text, field_name, format_spec, conversion in formatter.parse(template):
                formatted_parts.append(literal_text)
                if field_name is not None:
                    if field_name in metrics_data:
                        formatted_parts.append(str(metrics_data[field_name]))
                    else:
                        formatted_parts.append(f'{{{field_name}}}')
            return ''.join(formatted_parts)
            
    except Exception as e:
        logger.error(f"Error generating message with metrics: {e}")
        return f"Automated notification: {query}"

def collect_release_notes_metrics(query: str) -> Dict[str, Any]:
    """
    Collect release notes metrics from the ReleaseReadinessSpecialist agent.
    
    Args:
        query: Original user query
        
    Returns:
        Dictionary with metrics data for template filling
    """
    try:
        # Extract version from query
        version_match = re.search(r'version\s+(\d+\.\d+\.\d+)', query.lower())
        version = version_match.group(1) if version_match else '3.2.0'
        
        # Query the ReleaseReadinessSpecialist for release notes metrics
        metrics_query = f"What are the current release notes metrics for OpenSearch version {version}? Which components are missing release notes?"
        
        logger.info(f"Querying metrics for version {version}")
        
        # For now, return basic data - in production this would call the metrics agent
        # TODO: Implement actual Bedrock agent invocation
        return {
            'branch': version,
            'version': version,
            'release_version': version,
            'component_name': 'OpenSearch components',
            'components_missing': 'Multiple components'
        }
        
    except Exception as e:
        logger.error(f"Error collecting release notes metrics: {e}")
        return {'branch': '3.2.0', 'version': '3.2.0'}

def process_template_message(message_type: str, content: str, params: Dict[str, Any]) -> str:
    """
    Process a message using a predefined template.
    
    Args:
        message_type: Type of message template to use
        content: Base content for the message
        params: Additional parameters for template substitution
        
    Returns:
        Processed message content
    """
    try:
        template_info = MESSAGE_TEMPLATES.get(message_type)
        if not template_info:
            return content
        
        template = template_info['template']
        
        # Extract variables from content and params
        variables = {}
        
        # Extract version/branch from query
        version_match = re.search(r'version\s+(\d+\.\d+\.\d+)', content.lower())
        if version_match:
            version = version_match.group(1)
            variables['branch'] = f'{version}'
            variables['version'] = version
            variables['release_version'] = version
        
        # Add any additional parameters from params
        variables.update(params)
        
        # Format template with variables, handling missing variables gracefully
        try:
            formatted_message = template.format(**variables)
            return formatted_message
        except KeyError as e:
            logger.warning(f"Missing template variable {e}, using partial formatting")
            # Try to format with available variables, leaving missing ones as placeholders
            import string
            formatter = string.Formatter()
            formatted_parts = []
            for literal_text, field_name, format_spec, conversion in formatter.parse(template):
                formatted_parts.append(literal_text)
                if field_name is not None:
                    if field_name in variables:
                        formatted_parts.append(str(variables[field_name]))
                    else:
                        formatted_parts.append(f'{{{field_name}}}')
            return ''.join(formatted_parts)
            
    except Exception as e:
        logger.error(f"Error processing template message: {e}")
        return content

def send_slack_message(channel: str, message: str) -> Dict[str, Any]:
    """Send message to Slack channel."""
    if not slack_client:
        return {'success': False, 'error': 'Slack client not initialized'}
    
    try:
        response = slack_client.chat_postMessage(
            channel=channel,
            text=message,
            unfurl_links=False,
            unfurl_media=False
        )
        return {'success': True, 'message_ts': response['ts']}
    except SlackApiError as e:
        return {'success': False, 'error': f'Slack API error: {e.response["error"]}'}

def extract_channel_from_query(query: str) -> Optional[str]:
    """
    Extract channel from user query.
    
    Args:
        query: User's natural language query
        
    Returns:
        Channel ID if found, None otherwise
    """
    # Channel ID pattern (C followed by 10+ alphanumeric characters)
    channel_id_match = re.search(r'\b(C[A-Z0-9]{10,})\b', query)
    if channel_id_match:
        channel_id = channel_id_match.group(1)
        return channel_id if channel_id in CHANNEL_ALLOW_LIST else None
    
    # Channel reference patterns (#channel-name)
    channel_ref_match = re.search(r'#([a-z0-9-]+)', query.lower())
    if channel_ref_match:
        channel_name = channel_ref_match.group(1)
        # Map common channel names to IDs
        channel_mapping = {
            'opensearch-release-manager': 'C096MV7JZ0T',
            'private-oscar-test': 'C09827S7CEB', 
            'opensearch-3-2-0-release': 'C088XMSH4DA',
            'riley-needs-to-lock-in': 'C091EH1JKCL'
        }
        return channel_mapping.get(channel_name)
    
    # Text-based channel mentions
    query_lower = query.lower()
    if 'riley-needs-to-lock-in' in query_lower:
        return 'C096MV7JZ0T'
    elif '3-2-0' in query_lower or '3.2.0' in query_lower or 'release channel' in query_lower:
        return 'C096MV7JZ0T'
    elif 'build channel' in query_lower:
        return 'C09827S7CEB'
    elif 'test channel' in query_lower:
        return 'C091EH1JKCL'
    elif 'dev channel' in query_lower:
        return 'C088XMSH4DA'
    
    return None

def determine_message_type_from_query(query: str) -> str:
    """
    Determine message type from user query.
    
    Args:
        query: User's natural language query
        
    Returns:
        Message type string
    """
    query_lower = query.lower()
    
    if 'missing release notes' in query_lower or 'release notes' in query_lower:
        return 'missing_release_notes'
    elif 'criteria not met' in query_lower or 'entrance criteria' in query_lower:
        return 'criteria_not_met'
    elif 'documentation' in query_lower and ('missing' in query_lower or 'issue' in query_lower):
        return 'documentation_issues'
    elif 'code coverage' in query_lower or 'coverage' in query_lower:
        return 'missing_code_coverage'
    elif 'release announcement' in query_lower or 'announce release' in query_lower:
        return 'release_announcement'
    else:
        return 'missing_release_notes'  # Default

def create_error_response(error_message: str) -> Dict[str, Any]:
    """
    Create a standardized error response for agent format.
    
    Args:
        error_message: Error message to return
        
    Returns:
        Error response dictionary
    """
    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": "communication-orchestration",
            "function": "send_automated_message",
            "functionResponse": {
                "responseBody": {
                    "TEXT": {
                        "body": f'❌ {error_message}'
                    }
                }
            }
        }
    }