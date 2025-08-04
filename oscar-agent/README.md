# OSCAR Agent Implementation

This directory contains the Bedrock agent-based implementation of OSCAR (OpenSearch Conversational Automation for Release).

## Overview

The OSCAR agent implementation uses Amazon Bedrock agents for intelligent query processing, providing:

- **Unified Agent Interface**: Single agent handles all query routing through action groups
- **Enhanced Context Management**: Maintains conversation flow and session handling
- **Comprehensive Error Handling**: User-friendly error messages with automatic retry logic
- **Extensible Architecture**: Ready for Phase 2 metrics integration

## Architecture

```
Slack Event → Lambda → SlackHandler → OSCAR Agent (Bedrock) → Knowledge Base Action Group
```

## Files

| File | Purpose |
|------|---------|
| `app.py` | Main Lambda handler for Slack events |
| `config.py` | Configuration management with environment variable handling |
| `oscar_agent.py` | Bedrock agent interface and implementation |
| `slack_handler.py` | Slack event processing with reaction management |
| `storage.py` | DynamoDB storage interface for context management |
| `test_agent.py` | Agent functionality testing script |
| `requirements.txt` | Python dependencies |

## Configuration

### Required Environment Variables

```bash
# Agent Configuration
OSCAR_BEDROCK_AGENT_ID=your-agent-id
OSCAR_BEDROCK_AGENT_ALIAS_ID=your-agent-alias-id

# Slack Configuration
SLACK_BOT_TOKEN=xoxb-your-token
SLACK_SIGNING_SECRET=your-signing-secret

# AWS Configuration
AWS_REGION=us-west-2
AWS_ACCOUNT_ID=your-account-id
```

### Optional Configuration

```bash
# DynamoDB Tables
SESSIONS_TABLE_NAME=oscar-sessions-v2      # Default: oscar-sessions-v2
CONTEXT_TABLE_NAME=oscar-context           # Default: oscar-context

# TTL Settings (in seconds)
DEDUP_TTL=300                             # Default: 300 (5 minutes)
SESSION_TTL=3600                          # Default: 3600 (1 hour)
CONTEXT_TTL=604800                        # Default: 604800 (7 days)

# Context Management
MAX_CONTEXT_LENGTH=3000                   # Default: 3000 characters
CONTEXT_SUMMARY_LENGTH=500                # Default: 500 characters

# Agent Settings
AGENT_TIMEOUT=60                          # Default: 60 seconds
AGENT_MAX_RETRIES=2                       # Default: 2 retries

# Feature Flags
ENABLE_DM=false                           # Default: false (enable direct messages)
```

## Testing

Test the agent configuration locally:

```bash
python test_agent.py
```

This validates:
- ✅ Agent configuration is correct
- ✅ Agent can be reached and responds to queries
- ✅ All required environment variables are set
- ✅ Bedrock permissions are working

## Deployment

Deploy using the root-level deployment script:

```bash
cd ..
./deploy_oscar_agent.sh
```

The deployment script:
1. Validates configuration
2. Creates deployment package with dependencies
3. Deploys CDK infrastructure
4. Configures permissions

## Key Components

### BedrockOSCARAgent Class

**Features:**
- **Automatic Session Management**: Generates session IDs and maintains context
- **Retry Logic**: Exponential backoff for transient errors
- **Fallback Handling**: Context-enhanced queries when sessions expire
- **Error Translation**: Converts AWS errors to user-friendly messages

**Methods:**
- `query(query, session_id, context_summary)` - Main query interface
- `_invoke_agent(query, session_id)` - Direct agent invocation
- `_retry_with_backoff(func, *args)` - Retry mechanism
- `_handle_agent_error(error, query)` - Error handling

### SlackHandler Class

**Features:**
- **Event Processing**: Handles app_mention and direct message events
- **Reaction Management**: Visual feedback (🤔 → ✅) during processing
- **Context Preservation**: Maintains conversation history in threads
- **Async Processing**: Immediate acknowledgment with background processing

**Methods:**
- `handle_app_mention(event, say)` - Process @mentions
- `handle_message(message, say)` - Process direct messages
- `_process_message(...)` - Core message processing logic
- `_manage_reactions(...)` - Slack reaction management

### DynamoDBStorage Class

**Features:**
- **Context Storage**: Persistent conversation context with TTL
- **Event Deduplication**: Prevents duplicate message processing
- **Automatic Cleanup**: TTL-based cleanup of old data
- **Error Resilience**: Graceful handling of storage failures

**Methods:**
- `store_context(thread_key, context)` - Store conversation context
- `get_context(thread_key)` - Retrieve conversation context
- `has_seen_event(event_id)` - Check for duplicate events
- `mark_event_seen(event_id)` - Mark event as processed

## Error Handling

### Error Types and Responses

| AWS Error | User Message |
|-----------|--------------|
| `AccessDeniedException` | "I don't have permission to access that information. Please contact your administrator." |
| `ThrottlingException` | "I'm currently experiencing high load. Please try again in a moment." |
| `ValidationException` | "There was an issue with your query format. Please try rephrasing your question." |
| `ResourceNotFoundException` | "The agent or knowledge base is not available. Please contact your administrator." |
| `TimeoutError` | "Your query is taking longer than expected. Please try a more specific question or try again later." |

### Retry Strategy

- **Max Retries**: 2 (configurable via `AGENT_MAX_RETRIES`)
- **Backoff**: Exponential with jitter
- **Retryable Errors**: `ThrottlingException`, `ServiceUnavailableException`, `InternalServerException`
- **Non-Retryable**: `AccessDeniedException`, `ValidationException`

## Monitoring

### CloudWatch Logs

Monitor at: `/aws/lambda/oscar-slack-bot`

**Key Log Messages:**
- `Querying OSCAR agent with: ...` - Query initiation
- `Agent response received, length: X characters` - Successful response
- `All query attempts failed: ...` - Error conditions
- `Query processed in X.XX seconds` - Performance metrics

### Slack Visual Feedback

- 🤔 **Thinking**: Processing query
- ⏰ **Timer**: Query taking longer than expected
- ✅ **Success**: Query completed successfully
- ❌ **Error**: Query failed

## Phase 2 Preparation

The implementation includes configuration for future multi-agent support:

```bash
# Multi-Agent Configuration (Phase 2)
OSCAR_KNOWLEDGE_AGENT_ID=knowledge-agent-id
OSCAR_METRICS_AGENT_ID=metrics-agent-id
OSCAR_BUILD_AGENT_ID=build-agent-id
OSCAR_TEST_AGENT_ID=test-agent-id
ENABLE_MULTI_AGENT=false
DEFAULT_AGENT=knowledge
```

## Dependencies

### Core Dependencies
- **slack-bolt** (≥1.18.0) - Slack integration framework
- **boto3** (≥1.34.0) - AWS SDK for Python
- **botocore** (≥1.34.0) - AWS core library
- **requests** (≥2.31.0) - HTTP library

### Development Dependencies
- **pytest** (≥7.4.0) - Testing framework
- **pytest-mock** (≥3.11.0) - Mocking for tests
- **moto** (≥4.2.0) - AWS service mocking

## Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| "Permission denied" error | Lambda role lacks Bedrock permissions | Run `python ../fix_all_permissions.py` |
| Bot not responding | Agent not configured properly | Check agent status in Bedrock console |
| Session errors | Session ID issues | Sessions auto-regenerate, should resolve automatically |
| Timeout errors | Knowledge base slow response | Check knowledge base synchronization status |

### Debug Commands

```bash
# Test agent locally
python test_agent.py

# Check permissions
python ../debug_permissions.py

# Fix permissions
python ../fix_all_permissions.py

# Test full functionality
python ../test_full_functionality.py
```