# OSCAR Slack Bot - Remaining Changes

This document outlines the remaining changes needed for the OSCAR Slack Bot PR based on the review of the current codebase and the PR changes document.

## 1. Error Handling Improvements

### Replace stacktrace/detailed error descriptions with user-friendly messages

**File**: `bedrock.py`

```python
def query(self, query: str, session_id: Optional[str] = None, 
          context_summary: Optional[str] = None) -> Tuple[str, Optional[str]]:
    # ... existing code ...
    
    try:
        # Try with query decomposition first
        response = self.client.retrieve_and_generate(**request)
        logger.info("Query with decomposition succeeded")
        return response['output']['text'], response.get('sessionId')
    except Exception as e:
        logger.warning(f"Error with query decomposition: {e}")
        
        # If query decomposition fails, try without it
        logger.info("Retrying without query decomposition...")
        try:
            # ... existing fallback code ...
        except Exception as fallback_error:
            logger.error(f"Fallback also failed: {fallback_error}")
            # Return user-friendly error message instead of raising the exception
            return "I'm sorry, I couldn't retrieve the information you requested. There might be an issue with the knowledge base or the query format.", None
```

### Add emoji indicator for timeout situations

**File**: `slack_handler.py`

```python
def _process_message(self, channel: str, thread_ts: str, user_id: str, 
                    text: str, say: Callable, message_ts: str = None) -> None:
    # ... existing code ...
    
    # Add thinking reaction to the specific message
    self._manage_reactions(channel, reaction_ts, add_reaction="thinking_face")
    
    # Set timeout threshold (60 seconds)
    timeout_threshold = 60
    start_time = time.time()
    
    try:
        # Extract query from text (remove mentions)
        query = self._extract_query(text)
        logger.info(f"Extracted query: {query}")
        
        # Get context from storage
        context = self.storage.get_context(thread_key)
        context_summary = context.get("summary") if context else None
        session_id = context.get("session_id") if context else None
        
        # Query knowledge base
        kb_start_time = time.time()
        response, new_session_id = self.knowledge_base.query(
            query, 
            session_id=session_id,
            context_summary=context_summary
        )
        kb_end_time = time.time()
        
        # Check if we're approaching timeout
        elapsed_time = kb_end_time - start_time
        if elapsed_time > timeout_threshold * 0.8:  # 80% of timeout threshold
            # Add timer emoji to indicate slow response
            self._manage_reactions(channel, reaction_ts, add_reaction="timer_clock")
            
        # ... rest of the existing code ...
        
        # Update reactions based on processing time
        if elapsed_time > timeout_threshold:
            self._manage_reactions(
                channel, 
                reaction_ts, 
                add_reaction="white_check_mark", 
                remove_reaction=["thinking_face", "timer_clock"]
            )
        else:
            self._manage_reactions(
                channel, 
                reaction_ts, 
                add_reaction="white_check_mark", 
                remove_reaction="thinking_face"
            )
            
    except Exception as e:
        # ... existing error handling ...
```

## 2. Throttling Implementation

**File**: `lambda_stack.py`

Add throttling configuration to the API Gateway:

```python
# Create API Gateway with throttling
self.api = apigateway.RestApi(
    self, "OscarSlackBotApi",
    deploy_options=apigateway.StageOptions(
        throttling_rate_limit=5,  # 5 requests per second
        throttling_burst_limit=10  # 10 concurrent requests
    )
)

# Add Lambda integration
slack_events_integration = apigateway.LambdaIntegration(
    self.lambda_function,
    proxy=True
)

# Add Slack events endpoint
slack_events = self.api.root.add_resource("slack").add_resource("events")
slack_events.add_method("POST", slack_events_integration)
```

## 3. Code Organization

### Move mock implementations to test files

1. Remove `MockKnowledgeBase` from `bedrock.py` and move it to `tests/test_bedrock.py`

### Extract common utilities

Create a new file `utils.py` for common utilities:

```python
#!/usr/bin/env python
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.

"""
Utility functions for OSCAR.

This module provides common utility functions used across the OSCAR application.
"""

import logging
import time
import re
from typing import Dict, Any, Optional, List

# Configure logging
logger = logging.getLogger(__name__)

def extract_query(text: str) -> str:
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

def generate_thread_key(channel: str, thread_ts: str) -> str:
    """
    Generate a unique key for a thread.
    
    Args:
        channel: The Slack channel ID
        thread_ts: The thread timestamp
        
    Returns:
        A unique key for the thread
    """
    return f"{channel}_{thread_ts}"
```

Then update `slack_handler.py` to use these utilities.

## 4. Bedrock Module Improvements

### Simplify conditional logic in `bedrock.py`

```python
def _create_request(self, query: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Create a request for the Bedrock knowledge base.
    
    Args:
        query: The user's query
        session_id: Optional session ID for maintaining conversation context
        
    Returns:
        A dictionary containing the request parameters
    """
    # Check if we're using an inference profile ARN
    is_inference_profile = "inference-profile" in self.model_arn
    
    # Prepare base request structure
    request = {
        'input': {'text': query},
        'retrieveAndGenerateConfiguration': {
            'type': 'KNOWLEDGE_BASE',
            'knowledgeBaseConfiguration': {
                'knowledgeBaseId': self.knowledge_base_id,
                'modelArn': self.model_arn,
                'generationConfiguration': {
                    'promptTemplate': {
                        'textPromptTemplate': self.prompt_template
                    }
                }
            }
        }
    }
    
    # Add query decomposition configuration for non-inference profiles
    if not is_inference_profile:
        request['retrieveAndGenerateConfiguration']['knowledgeBaseConfiguration']['orchestrationConfiguration'] = {
            'queryTransformationConfiguration': {
                'type': 'QUERY_DECOMPOSITION'
            }
        }
    
    # Add session ID if available
    if session_id:
        request['sessionId'] = session_id
    
    return request
```

## 5. Documentation Updates

### Update README.md

```markdown
# OpenSearch Conversational Automation for Releases (OSCAR) Slack Bot

A Slack bot for OpenSearch release management, powered by AWS Lambda and Amazon Bedrock.

## Architecture

This Slack bot uses a two-phase processing approach to prevent duplicate responses:

1. **Immediate Acknowledgment**: When a Slack event is received, the Lambda function immediately acknowledges it with a 200 OK response within Slack's 3-second timeout window.

2. **Asynchronous Processing**: After acknowledging the event, the Lambda function invokes itself asynchronously to process the event and generate a response.

### Components

- **Slack Bot**: AI-powered Slack bot with thread-based context and knowledge base integration
- **AWS Lambda**: Serverless function for processing Slack events
- **Amazon Bedrock**: AI service for natural language understanding and generation
- **DynamoDB**: NoSQL database for storing conversation context and session data
  - Sessions Table: Stores active Bedrock sessions (1-hour TTL)
  - Context Table: Stores conversation context (7-day TTL)
- **API Gateway**: HTTP endpoint for receiving Slack events
- **S3**: Storage for knowledge base documents

## Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `SLACK_BOT_TOKEN` | Slack bot token | Yes | - |
| `SLACK_SIGNING_SECRET` | Slack signing secret | Yes | - |
| `KNOWLEDGE_BASE_ID` | Bedrock knowledge base ID | Yes | - |
| `MODEL_ARN` | Bedrock model ARN | No | Claude 3.5 Haiku |
| `AWS_REGION` | AWS region | No | us-east-1 |
| `SESSIONS_TABLE_NAME` | DynamoDB sessions table name | No | oscar-sessions-v2 |
| `CONTEXT_TABLE_NAME` | DynamoDB context table name | No | oscar-context |
| `DEDUP_TTL` | Deduplication TTL in seconds | No | 300 (5 minutes) |
| `SESSION_TTL` | Session TTL in seconds | No | 3600 (1 hour) |
| `CONTEXT_TTL` | Context TTL in seconds | No | 604800 (7 days) |
| `MAX_CONTEXT_LENGTH` | Maximum context length | No | 3000 |
| `CONTEXT_SUMMARY_LENGTH` | Context summary length | No | 500 |
| `ENABLE_DM` | Enable direct messages | No | false |
| `PROMPT_TEMPLATE` | Custom prompt template | No | Default template |

## Features

- **Thread-Based Context**: Maintains conversation context within Slack threads
- **Knowledge Base Integration**: Uses Amazon Bedrock to query OpenSearch documentation
- **Emoji Reactions**: Provides visual feedback on message processing status
- **Deduplication**: Prevents duplicate responses to the same message
- **Toggleable DM Support**: Enable or disable direct message functionality

## Project Structure

```
slack-bot/
├── app.py                # Lambda handler
├── bedrock.py            # Bedrock integration
├── config.py             # Configuration management
├── slack_handler.py      # Slack event handling
├── storage.py            # DynamoDB storage
├── utils.py              # Common utilities
├── requirements.txt      # Python dependencies
└── tests/                # Unit tests
    ├── run_tests.sh      # Test runner script
    └── ...               # Test files
```

## Deployment

See the main [README.md](../README.md) for deployment instructions.
```

## 6. Documentation Enhancement

Add OSCAR documentation to the knowledge base to enable the bot to answer questions about OSCAR itself. This involves:

1. Creating documentation files about OSCAR's features, architecture, and usage
2. Adding these files to the S3 bucket used by the Bedrock knowledge base
3. Reindexing the knowledge base to include the new documentation

## 7. Additional Improvements

### Add TODO comment about deduplication solution

**File**: `app.py`

```python
def get_event_id(event: Dict[str, Any]) -> str:
    """
    Generate a unique ID for a Slack event.
    
    Args:
        event: The event dict from API Gateway
        
    Returns:
        A unique ID for the event
    """
    # TODO: Consider a more robust deduplication solution that resets TTL on updates
    # The current TTL setup starts the countdown when a key is first created
    # Future improvement could include resetting the timer when the key is updated
    
    # Extract event body
    body = None
    if event.get('body'):
        body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
    
    # If this is a Slack event, use the event ID
    if body and body.get('event'):
        slack_event = body.get('event')
        event_ts = slack_event.get('event_ts') or slack_event.get('ts')
        channel = slack_event.get('channel')
        
        if event_ts and channel:
            return f"slack_event_{channel}_{event_ts}"
    
    # ... rest of the existing code ...
```

### Add note about prompt templates

**File**: `config.py`

```python
# Default prompt template
# TODO: Consider allowing users to select default prompts through JSON or YAML configuration
self.prompt_template = os.environ.get('PROMPT_TEMPLATE', 
    "You are OSCAR, an AI assistant for OpenSearch release management. " +
    # ... rest of the template ...
)
```