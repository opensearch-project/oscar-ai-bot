# Communication Orchestrator Integration Guide

This document provides guidance on integrating the Communication Orchestrator with the OSCAR supervisor agent and any required configuration updates.

## Overview

The Communication Orchestrator has been designed to integrate seamlessly with the existing OSCAR agent infrastructure. It leverages the same Slack client, AWS credentials, and configuration management system.

## Integration Points

### 1. OSCAR Agent Integration

The Communication Orchestrator is integrated into the OSCAR agent through the `SlackHandler` class:

- **File Modified**: `oscar-agent/slack_handler.py`
- **Integration Method**: Command parsing and routing
- **Dependencies**: Uses existing Slack client and AWS Bedrock access

### 2. Command Processing Flow

```
User Message → SlackHandler → Command Parser → Communication Orchestrator → Slack Response
```

1. User sends message with communication command (e.g., `/send_notification`)
2. `SlackHandler` detects communication command pattern
3. Command is routed to `CommunicationOrchestrator`
4. Message is generated using AI and templates
5. Message is sent to configured channels
6. Results are reported back to user

### 3. No Supervisor Agent Changes Required

The Communication Orchestrator works with the existing supervisor agent without requiring changes to:

- Bedrock agent configuration
- Knowledge base setup
- Lambda function configuration
- IAM permissions (uses existing Bedrock and Slack permissions)

## Configuration Requirements

### Environment Variables

The Communication Orchestrator uses existing environment variables:

```bash
# Required (already configured for OSCAR)
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
AWS_REGION=us-east-1

# Optional (for AI enhancement)
# Uses existing Bedrock permissions
```

### Slack Permissions

Ensure the OSCAR bot has the following Slack permissions:

- `chat:write` - Send messages to channels
- `chat:write.public` - Send messages to public channels
- `channels:read` - Read channel information
- `groups:read` - Read private channel information (if needed)

### AWS Permissions

The Communication Orchestrator requires the same AWS permissions as the existing OSCAR agent:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeModel"
            ],
            "Resource": [
                "arn:aws:bedrock:*::foundation-model/anthropic.claude-3-5-haiku-20241022-v1:0"
            ]
        }
    ]
}
```

## Deployment Steps

### 1. Update Lambda Function

Include the `communication-orchestrator` directory in your Lambda deployment package:

```bash
# If using CDK or similar deployment tool
# Add communication-orchestrator/ to your Lambda function source

# If deploying manually
zip -r oscar-agent.zip oscar-agent/ communication-orchestrator/
```

### 2. Test Integration

After deployment, test the integration:

```
@oscar /list_templates
```

Expected response: List of available message templates

### 3. Validate Permissions

Test sending a notification:

```
@oscar /preview_message build_failure build_name=test-build branch=main
```

Expected response: Preview of generated message

## Channel Configuration

### Default Channels

The system comes pre-configured with these channels:

- `#release-engineering` - Primary release notifications
- `#security-alerts` - Security-related alerts
- `#dev-alerts` - Development team alerts
- `#qa-alerts` - Quality assurance alerts
- `#deployments` - Deployment status updates
- `#release-coordination` - Release planning
- `#dev-team` - General development notifications

### Customizing Channels

To modify channel configurations:

1. Edit `communication-orchestrator/config.py`
2. Update the `channel_configs` dictionary
3. Redeploy the Lambda function

Example:
```python
self.channel_configs = {
    "#your-custom-channel": {
        "description": "Custom notifications",
        "allowed_message_types": ["build_failure", "deployment_status"],
        "default_mention": "@here"
    }
}
```

## Message Templates

### Available Templates

1. **build_failure** - Build failure notifications
2. **cve_check_failure** - Security vulnerability alerts
3. **release_reminder** - Release task reminders
4. **deployment_status** - Deployment updates
5. **test_failure** - Test failure alerts

### Adding Custom Templates

To add new message templates:

1. Edit `communication-orchestrator/config.py`
2. Add new `MessageTemplate` to `message_templates` dictionary
3. Update channel permissions as needed
4. Redeploy

Example:
```python
"custom_alert": MessageTemplate(
    name="custom_alert",
    description="Custom alert for special cases",
    template="🔔 **Custom Alert** 🔔\n\n{message}\n\nTime: {timestamp}",
    channels=["#custom-channel"],
    mentions=["@here"],
    priority="normal"
)
```

## Troubleshooting

### Common Issues

1. **Import Errors**
   - Ensure `communication-orchestrator` directory is included in Lambda package
   - Check Python path configuration

2. **Permission Errors**
   - Verify Slack bot has `chat:write` permissions
   - Check AWS Bedrock permissions for AI enhancement

3. **Channel Not Found**
   - Ensure channels exist in Slack workspace
   - Verify bot is added to target channels

4. **Template Errors**
   - Check template syntax in `config.py`
   - Validate required context fields

### Logging

Enable debug logging to troubleshoot issues:

```python
import logging
logging.getLogger('communication_orchestrator').setLevel(logging.DEBUG)
```

## Security Considerations

### Channel Access Control

- Only configured channels can receive specific message types
- Channel permissions are enforced at the template level
- Validation prevents unauthorized channel access

### Message Content

- All messages go through validation
- Required context fields are enforced
- AI enhancement can be disabled if needed

### Audit Trail

- All communication commands are logged
- Message sending results are tracked
- Failed attempts are recorded

## Performance Considerations

### AI Enhancement

- AI enhancement adds ~2-3 seconds to message generation
- Can be disabled by setting `use_ai_enhancement: false` in context
- Fallback templates ensure reliability

### Rate Limiting

- Slack API rate limits apply (1 message per second per channel)
- Bulk sends are handled sequentially
- Error handling prevents cascading failures

## Future Enhancements

### Planned Features

1. **Scheduled Messages** - Send messages at specific times
2. **Approval Workflows** - Require approval before sending
3. **Custom Templates** - Create templates via Slack interface
4. **Analytics Dashboard** - Track message effectiveness
5. **CI/CD Integration** - Trigger from build systems

### Extension Points

The system is designed for easy extension:

- Add new message types in `config.py`
- Extend AI prompts in `message_generator.py`
- Add new command types in `orchestrator.py`
- Integrate with external systems via webhooks

## Support

For issues or questions:

1. Check the logs in CloudWatch (Lambda function logs)
2. Review the test output: `python communication-orchestrator/test_orchestrator.py`
3. Validate configuration with deployment script: `./deploy_communication_orchestrator.sh`
4. Refer to the detailed README: `communication-orchestrator/README.md`