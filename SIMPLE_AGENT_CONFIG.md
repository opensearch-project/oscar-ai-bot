# Simple Communication Orchestration - Agent Configuration

## Agent Instructions Update

Add this to your OSCAR supervisor agent instructions:

```
**AUTOMATED MESSAGE SENDING:**

When users request automated message sending (e.g., "send missing release notes message to [channel]"), you MUST:

1. IMMEDIATELY call the send_automated_message function with the complete user query
2. DO NOT attempt to generate message content yourself
3. DO NOT respond with explanatory text before calling the function
4. Let the function handle all message generation and channel posting

**CRITICAL: These requests require send_automated_message function:**
- "send missing release notes message to..."
- "send criteria not met notification to..."
- "send documentation issues alert to..."
- "send code coverage notification to..."
- "send release announcement to..."
- Any request containing "send [something] to [channel]"

**Function Call Pattern:**
User: "send missing release notes message to riley-needs-to-lock-in channel for version 3.2.0"
Agent: [IMMEDIATELY call send_automated_message with full query]

**DO NOT:**
- Generate message content in your response
- Explain what you're going to do before calling the function
- Process the request locally
```

## Action Group Configuration

**Action Group Name:** `communication-orchestration`
**Description:** `Send automated release management messages to Slack channels for authorized users`
**Lambda Function:** `arn:aws:lambda:us-east-1:YOUR_ACCOUNT:function:oscar-communication-handler`

## Function Schema

```json
{
  "name": "send_automated_message",
  "description": "Send automated messages to Slack channels",
  "parameters": {
    "query": {
      "type": "string",
      "description": "Complete user query with channel and message details",
      "required": true
    }
  },
  "requireConfirmation": "DISABLED"
}
```

## Deploy and Test

1. Deploy Lambda: `./deploy_communication_handler.sh`
2. Update agent with above configuration
3. Test: `@OSCAR send missing release notes message to #3-2-0 for version 3.2.0`

The agent will:
1. Detect message sending request
2. Call send_automated_message function (NOT generate content itself)
3. Function extracts channel, determines type, generates content
4. Function sends message directly to target channel
5. Function returns confirmation to user