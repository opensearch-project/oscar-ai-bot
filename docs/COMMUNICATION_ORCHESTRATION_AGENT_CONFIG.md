# OSCAR Communication Orchestration - Agent Configuration Guide

## Overview

This guide provides the complete configuration for adding automated message sending functionality to the OSCAR supervisor agent. This enables release managers to send templated messages to Slack channels using natural language commands.

## Prerequisites

- OSCAR supervisor agent already deployed and functional
- Slack bot with appropriate permissions
- Lambda function for communication handler deployed
- Channel allow list configured

## Agent Configuration Updates

### 1. Update OSCAR Supervisor Agent Instructions

Navigate to: **AWS Console → Amazon Bedrock → Agents → oscar-supervisor-agent → Edit**

**Add the following to the existing agent instructions:**

```
**ENHANCED COMMUNICATION ORCHESTRATION:**

You now have the ability to send automated messages to Slack channels for release management tasks. This functionality is restricted to authorized users only.

**Message Sending Capabilities:**
- Send missing release notes reminders
- Send entrance criteria notifications  
- Send documentation issue alerts
- Send code coverage notifications
- Send release announcements

**Supported Message Types:**
1. **missing_release_notes**: Reminds teams about missing release notes
2. **criteria_not_met**: Notifies about unmet entrance criteria
3. **documentation_issues**: Alerts about missing documentation PRs
4. **missing_code_coverage**: Notifies about code coverage issues
5. **release_announcement**: Announces new releases

**Usage Examples:**
- "Send missing release notes messages to #3-2-0 channel"
- "Send criteria not met notification for component X to #release"
- "Post release announcement for version 2.19.0 to C096MV7JZ0T"

**Channel Specification:**
- Users must specify target channel in their query
- Supported formats: #channel-name, channel ID (C096MV7JZ0T), or descriptive text
- Only allowed channels: C096MV7JZ0T, C09827S7CEB, C091EH1JKCL, C088XMSH4DA

**Authorization:**
- Only authorized release managers can use this functionality
- Unauthorized requests will be denied with appropriate error message

**Processing Flow:**
1. Detect message sending request from user query
2. Verify user authorization (handled by Slack handler)
3. Extract target channel from user query (required)
4. Determine appropriate message template from query content
5. Use knowledge base and metrics data to populate template variables
6. Send formatted message to specified channel
7. Confirm successful delivery to user
```

### 2. Add New Action Group

**Action Group Configuration:**

- **Action Group Name**: `communication-orchestration`
- **Description**: `Automated message sending for release management communications`
- **Action Group Type**: `Define with function details`
- **Lambda Function**: `arn:aws:lambda:us-east-1:YOUR_ACCOUNT:function:oscar-communication-handler`

### 3. Function Schema Configuration

**Function Name**: `send_automated_message`

**Complete JSON Schema:**
```json
{
  "name": "send_automated_message",
  "description": "Send automated messages to Slack channels for release management tasks. Processes natural language requests to generate and send templated messages.",
  "parameters": {
    "query": {
      "type": "string",
      "description": "The user's natural language request for sending a message (e.g., 'send missing release notes message to 3-2-0 channel')",
      "required": true
    },
    "message_type": {
      "type": "string",
      "description": "Type of message to send: missing_release_notes, criteria_not_met, documentation_issues, missing_code_coverage, or release_announcement",
      "required": false
    },
    "target_channel": {
      "type": "string", 
      "description": "Target Slack channel ID (C096MV7JZ0T, C09827S7CEB, C091EH1JKCL, or C088XMSH4DA)",
      "required": false
    },
    "branch": {
      "type": "string",
      "description": "Git branch name for release notes or code coverage messages",
      "required": false
    },
    "component_name": {
      "type": "string",
      "description": "Name of the component for coverage or criteria messages",
      "required": false
    },
    "release_version": {
      "type": "string",
      "description": "Release version for announcements (e.g., '2.19.0')",
      "required": false
    },
    "owner": {
      "type": "string",
      "description": "GitHub username or Slack user ID for notifications",
      "required": false
    }
  },
  "requireConfirmation": "DISABLED"
}
```

### 4. Lambda Function Deployment

**Create the Lambda function:**

```bash
# Create deployment package
cd /path/to/oscar-agent
zip -r communication-handler.zip communication_handler.py

# Deploy Lambda function
aws lambda create-function \
  --function-name oscar-communication-handler \
  --runtime python3.9 \
  --role arn:aws:iam::YOUR_ACCOUNT:role/oscar-lambda-execution-role \
  --handler communication_handler.lambda_handler \
  --zip-file fileb://communication-handler.zip \
  --timeout 30 \
  --memory-size 256 \
  --environment Variables='{
    "SLACK_BOT_TOKEN":"YOUR_SLACK_BOT_TOKEN"
  }'
```

**Required IAM Permissions for Lambda Role:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream", 
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeAgent",
        "bedrock:InvokeModel"
      ],
      "Resource": "*"
    }
  ]
}
```

### 5. Update Slack Handler Authorization

**File**: `oscar-agent/slack_handler.py`

**Update the authorized users list with actual Slack member IDs:**

```python
# Replace with actual Slack user IDs of authorized release managers
AUTHORIZED_MESSAGE_SENDERS = [
    'U091B0QH1QD',  # Release Manager 1
    'W017VPMPKH7',  # Release Manager 2  
    'W017PN2ADN0',  # Release Manager 3
    'W017VV9TD33',  # Release Manager 4
]
```

**To get Slack user IDs:**
1. Go to Slack workspace
2. Click on user profile
3. Click "More" → "Copy member ID"
4. Replace the placeholder IDs above

### 6. Channel Configuration

**Current allowed channels:**
- `C096MV7JZ0T` - Primary release channel (3.2.0)
- `C09827S7CEB` - Build/CI channel  
- `C091EH1JKCL` - Test/QA channel
- `C088XMSH4DA` - General development channel

**To add more channels:**
1. Update `channel_allow_list` in `slack_handler.py`
2. Update `CHANNEL_ALLOW_LIST` in `communication_handler.py`
3. Redeploy both components

### 7. Message Templates

**Available templates (hardcoded from templates directory):**

1. **missing_release_notes**: Reminds about missing release notes
2. **criteria_not_met**: Notifies about unmet entrance criteria
3. **documentation_issues**: Alerts about missing documentation
4. **missing_code_coverage**: Notifies about code coverage issues
5. **release_announcement**: Announces new releases

**Template variables are automatically extracted from:**
- User query content
- Metrics data (when available)
- Knowledge base information
- Explicit parameters

## Testing the Configuration

### 1. Test Authorization

**Authorized user test:**
```
@OSCAR send missing release notes message to the 3-2-0 release channel
```

**Expected**: Message processed and sent

**Unauthorized user test:**
```
@OSCAR send missing release notes message to the 3-2-0 release channel  
```

**Expected**: "❌ You are not authorized to use automated message sending functionality."

### 2. Test Message Types

**Missing release notes:**
```
@OSCAR send missing release notes reminder for branch main to release channel
```

**Criteria not met:**
```
@OSCAR send criteria not met notification for component opensearch-security
```

**Documentation issues:**
```
@OSCAR send documentation issues alert for owner @username
```

**Code coverage:**
```
@OSCAR send code coverage notification for component opensearch-dashboards branch main
```

**Release announcement:**
```
@OSCAR announce release of version 2.19.0
```

### 3. Test Channel Extraction

**Channel ID format:**
```
@OSCAR send message to channel C096MV7JZ0T about missing release notes
```

**Channel reference format:**
```
@OSCAR send missing release notes message to #3-2-0
@OSCAR send code coverage alert to #build
```

**Descriptive format:**
```
@OSCAR send missing release notes message to release channel
@OSCAR send code coverage alert to build channel
```

## Troubleshooting

### Common Issues

1. **"Channel not in allow list" error**
   - Verify channel ID is correct
   - Update allow lists in both handler files
   - Redeploy Lambda function

2. **"Not authorized" error**
   - Verify user ID is in AUTHORIZED_MESSAGE_SENDERS
   - Check Slack member ID format (starts with U or W)
   - Redeploy Slack handler

3. **Template formatting issues**
   - Check template variables in communication_handler.py
   - Verify variable extraction logic
   - Test with explicit parameters

4. **Lambda function errors**
   - Check CloudWatch logs for detailed errors
   - Verify IAM permissions
   - Test Lambda function independently

### Monitoring

**CloudWatch Logs:**
- `/aws/lambda/oscar-communication-handler`
- `/aws/lambda/oscar-slack-bot`

**Key metrics to monitor:**
- Message send success rate
- Authorization failures
- Template processing errors
- Channel routing accuracy

## Security Considerations

1. **User Authorization**: Only 4 specific users can send messages
2. **Channel Restrictions**: Messages limited to pre-approved channels
3. **Template Safety**: All templates are hardcoded, no user-provided templates
4. **Rate Limiting**: Slack API rate limits apply automatically
5. **Audit Trail**: All actions logged in CloudWatch

## Deployment Checklist

- [ ] Update supervisor agent instructions
- [ ] Add communication-orchestration action group
- [ ] Configure function schema
- [ ] Deploy Lambda function with correct permissions
- [ ] Update authorized users list with real Slack IDs
- [ ] Test with authorized user
- [ ] Test with unauthorized user  
- [ ] Verify all message types work
- [ ] Confirm channel routing
- [ ] Monitor CloudWatch logs
- [ ] Document any customizations

## Future Enhancements

1. **Dynamic Templates**: Load templates from S3 or database
2. **Advanced Routing**: More sophisticated channel selection logic
3. **Scheduling**: Schedule messages for future delivery
4. **Approval Workflow**: Require approval before sending certain messages
5. **Analytics**: Track message effectiveness and engagement
6. **Integration**: Connect with GitHub issues and PRs for automated updates