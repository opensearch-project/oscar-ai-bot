#!/usr/bin/env python3
"""
Slack Text Formatter for OSCAR Agent

This module provides text formatting utilities specifically for Slack messages,
converting markdown-style formatting to Slack's mrkdwn format.
"""

import re
import logging

logger = logging.getLogger(__name__)

def format_for_slack(text: str) -> str:
    """
    Convert standard markdown formatting to Slack mrkdwn format.
    
    Args:
        text: Input text with standard markdown formatting
        
    Returns:
        Text formatted for Slack mrkdwn
    """
    if not text:
        return text
    
    # Convert headers - Slack doesn't support headers, use bold instead
    text = re.sub(r'^# (.+)$', r'*\1*', text, flags=re.MULTILINE)
    text = re.sub(r'^## (.+)$', r'*\1*', text, flags=re.MULTILINE)
    text = re.sub(r'^### (.+)$', r'*\1*', text, flags=re.MULTILINE)
    
    # Convert bold - markdown ** to slack *
    text = re.sub(r'\*\*(.+?)\*\*', r'*\1*', text)
    
    # Convert italic - markdown * to slack _
    text = re.sub(r'(?<!\*)\*([^*]+?)\*(?!\*)', r'_\1_', text)
    
    # Convert code blocks - markdown ``` to slack ```
    # (Already compatible, but ensure proper spacing)
    text = re.sub(r'```(\w+)?\n', r'```\n', text)
    
    # Convert inline code - markdown ` to slack `
    # (Already compatible)
    
    # Convert bullet points - ensure proper Slack formatting
    text = re.sub(r'^- (.+)$', r'• \1', text, flags=re.MULTILINE)
    text = re.sub(r'^  - (.+)$', r'  ◦ \1', text, flags=re.MULTILINE)
    
    # Convert checkmarks and status indicators
    text = re.sub(r'✓', '✅', text)
    text = re.sub(r'✗', '❌', text)
    
    # Ensure proper line breaks for Slack
    # Slack needs double line breaks for paragraph separation
    text = re.sub(r'\n\n+', '\n\n', text)
    
    return text

def lambda_handler(event, context):
    """
    AWS Lambda handler for text formatting action group.
    
    Expected event structure:
    {
        "function": "format_text_for_slack",
        "parameters": [
            {"name": "text", "value": "text to format"},
            {"name": "format_type", "value": "slack_mrkdwn"}  # optional
        ]
    }
    """
    try:
        logger.info(f"Text formatting request: {event}")
        
        function_name = event.get('function', '')
        parameters = event.get('parameters', [])
        
        # Extract parameters
        params = {}
        for param in parameters:
            if isinstance(param, dict) and 'name' in param and 'value' in param:
                params[param['name']] = param['value']
        
        text = params.get('text', '')
        format_type = params.get('format_type', 'slack_mrkdwn')
        
        if function_name == 'format_text_for_slack':
            if format_type == 'slack_mrkdwn':
                formatted_text = format_for_slack(text)
                return {
                    'statusCode': 200,
                    'body': {
                        'formatted_text': formatted_text,
                        'original_length': len(text),
                        'formatted_length': len(formatted_text),
                        'format_type': format_type
                    }
                }
            else:
                return {
                    'statusCode': 400,
                    'body': {'error': f'Unsupported format_type: {format_type}'}
                }
        else:
            return {
                'statusCode': 400,
                'body': {'error': f'Unknown function: {function_name}'}
            }
            
    except Exception as e:
        logger.error(f"Text formatting error: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'body': {'error': str(e)}
        }

# Test function for local development
if __name__ == "__main__":
    test_text = """# Integration Test Status: OpenSearch 3.2.0 RC6

## Summary
**Overall Status: PASS (100%)**
**336/336 components passed** across all platforms

## Platform Coverage
- ✓ Linux (x64, arm64): tar, rpm, deb distributions
- ✓ Windows (x64): zip distribution

## Component Details
- **OpenSearch Core**: All core components passed
- **Security Components**: All security features verified

```bash
# Example command
curl -X GET "localhost:9200"
```

Inline `code` example."""

    formatted = format_for_slack(test_text)
    print("Original:")
    print(test_text)
    print("\nFormatted for Slack:")
    print(formatted)