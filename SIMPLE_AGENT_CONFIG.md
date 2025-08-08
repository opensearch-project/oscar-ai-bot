# Simple Communication Orchestration - Agent Configuration

## Agent Instructions Update

Add this to your OSCAR supervisor agent instructions:

```
**AUTOMATED MESSAGE SENDING:**

When users request automated message sending (e.g., "send missing release notes message to [channel]"), you MUST follow this workflow:

1. **Route to metrics agent** (e.g., ReleaseReadinessSpecialist) to get current data
2. **Route to knowledge base** to get the appropriate message template
3. **Combine the data** - fill the template with real metrics data
4. **Call send_automated_message** with:
   - message_content: Complete filled message (NOT raw template)
   - target_channel: Target channel name
   - query: Original user query

**CRITICAL:** Always gather real data first, then fill templates, then send complete messages

**CRITICAL: These requests require send_automated_message function:**
- "send missing release notes message to..."
- "send criteria not met notification to..."
- "send documentation issues alert to..."
- "send code coverage notification to..."
- "send release announcement to..."
- Any request containing "send [something] to [channel]"

**Function Call Pattern:**
User: "send missing release notes message to riley-needs-to-lock-in channel for version 3.2.0"

Agent workflow:
1. Call ReleaseReadinessSpecialist: "What are the current release notes metrics for version 3.2.0?"
2. Call Knowledge Base: "Get missing release notes message template"
3. Combine: Fill template with actual component data from metrics
4. Call send_automated_message(
     message_content: "Hi, [Actual component teams]\n\nComponents X, Y, Z are missing release notes for version 3.2.0...",
     target_channel: "riley-needs-to-lock-in",
     query: "original query"
   )

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
    "message_content": {
      "type": "string",
      "description": "Complete message content filled with actual data",
      "required": true
    },
    "target_channel": {
      "type": "string",
      "description": "Target Slack channel ID or name",
      "required": true
    },
    "query": {
      "type": "string",
      "description": "Original user query for logging",
      "required": false
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