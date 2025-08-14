# Cross-Channel Context Preservation Fix

## Problem Description

When a user requests OSCAR to send a message to a different channel (e.g., "Send missing release notes message to #private-oscar-test"), the following flow occurs:

1. User makes request in Channel A
2. OSCAR responds with confirmation in Channel A (context preserved)
3. User approves, message gets sent to Channel B via communication handler
4. **ISSUE**: When users respond in threads in Channel B, OSCAR has no context about the original message

This breaks the conversation flow because the bot becomes "agnostic" to the message context in the target channel.

## Root Cause

The communication handler (`communication_handler.py`) sends messages to target channels but doesn't store context for the new channel/thread combination. The context storage only happens in the original channel where the request was made.

## Solution Implementation

### 1. Enhanced Communication Handler

**File**: `oscar-agent/communication_handler.py`

Added context storage functionality:

```python
# Added imports
import time

# Added DynamoDB initialization
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
context_table_name = os.environ.get('CONTEXT_TABLE_NAME', 'oscar-agent-context')
context_table = dynamodb.Table(context_table_name)
context_ttl = 7 * 24 * 60 * 60  # 7 days in seconds

# Added context storage function
def store_cross_channel_context(channel: str, message_ts: str, original_query: str, sent_message: str) -> None:
    """Store context for a message sent to a different channel to enable follow-up conversations."""
    try:
        thread_key = f"{channel}_{message_ts}"
        
        context = {
            "session_id": None,  # New conversation thread
            "history": [
                {
                    "query": "[Automated message - original request details redacted for privacy]",
                    "response": sent_message,
                    "timestamp": int(time.time())
                }
            ]
        }
        
        # Store with TTL
        expiration = int(time.time()) + context_ttl
        item = {
            'thread_key': thread_key,
            'context': context,
            'ttl': expiration,
            'updated_at': int(time.time())
        }
        
        context_table.put_item(Item=item)
        logger.info(f"Stored cross-channel context for thread {thread_key} in channel {channel}")
        
    except Exception as e:
        logger.error(f"Error storing cross-channel context for {channel}_{message_ts}: {e}", exc_info=True)
```

**Modified message sending logic**:

```python
# After successful message send
if response.get('ok') and response.get('ts'):
    store_cross_channel_context(target_channel, response.get('ts'), query, processed_message)
```

### 2. Updated Deployment Script

**File**: `deploy_communication_handler.sh`

Added:
- `CONTEXT_TABLE_NAME` environment variable
- DynamoDB permissions in IAM policy
- Access to both `oscar-agent-context` and `oscar-agent-sessions` tables

### 3. Test Coverage

**File**: `test_cross_channel_context.py`

Comprehensive test suite covering:
- Cross-channel context storage and retrieval
- Communication handler integration
- Follow-up conversation scenarios
- Context formatting for queries

## How It Works

### Before Fix
```
Channel A: User -> "Send message to Channel B"
Channel A: OSCAR -> "Message sent to Channel B" ✅ (has context)
Channel B: OSCAR -> "Missing release notes message..." ❌ (no context stored)
Channel B: User -> "What version is this for?" ❌ (OSCAR has no context)
```

### After Fix
```
Channel A: User -> "Send message to Channel B"
Channel A: OSCAR -> "Message sent to Channel B" ✅ (has context)
Channel B: OSCAR -> "Missing release notes message..." ✅ (context stored)
Channel B: User -> "What version is this for?" ✅ (OSCAR has context)
```

## Context Structure

The stored context includes:
- **thread_key**: `{channel_id}_{message_timestamp}`
- **session_id**: `None` (new conversation)
- **history**: Array with original request and sent message
- **ttl**: 7-day expiration for cleanup

Example context:
```json
{
  "session_id": null,
  "history": [
    {
      "query": "[Automated message - original request details redacted for privacy]",
      "response": "Hi, this component is missing release notes at 3.2.0 ref...",
      "timestamp": 1703123456
    }
  ]
}
```

## Privacy & Security

The implementation includes important privacy protections:

- **Query Redaction**: Original user queries are redacted in cross-channel contexts to prevent sensitive information leakage
- **User Privacy**: People in the target channel cannot see who made the original request or the exact wording used
- **Secure Context**: Only the bot's response message is preserved for context, not the triggering request details

## Benefits

1. **Seamless Conversations**: Users can respond to bot messages in any channel and maintain context
2. **Better User Experience**: No need to re-explain context when following up
3. **Consistent Behavior**: Same context preservation mechanism across all channels
4. **Automatic Cleanup**: TTL ensures old contexts don't accumulate indefinitely
5. **Privacy Protection**: Original requests are redacted to protect user privacy and sensitive information

## Testing

Run the test suite:
```bash
python test_cross_channel_context.py
```

## Deployment

1. Deploy updated communication handler:
   ```bash
   ./deploy_communication_handler.sh
   ```

2. Verify DynamoDB permissions are correctly set

3. Test with a cross-channel message request

## Future Enhancements

- Consider linking cross-channel contexts to original session IDs
- Add metrics for cross-channel conversation success rates
- Implement context inheritance for complex multi-channel workflows