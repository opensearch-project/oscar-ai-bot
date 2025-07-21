# OSCAR Slack Bot

A Slack bot for OpenSearch Conversational Automation for Release, powered by AWS Lambda and Amazon Bedrock.

## Architecture

This Slack bot uses a two-phase processing approach to prevent duplicate responses:

1. **Immediate Acknowledgment**: When a Slack event is received, the Lambda function immediately acknowledges it with a 200 OK response within Slack's 3-second timeout window.

2. **Asynchronous Processing**: After acknowledging the event, the Lambda function invokes itself asynchronously to process the event and generate a response.

This approach prevents Slack from retrying events (which can lead to duplicate responses) while still allowing for longer processing times when querying the knowledge base.

## Deployment

### Prerequisites

- AWS CLI configured with appropriate permissions
- Python 3.9 installed
- AWS CDK installed (`npm install -g aws-cdk`)

### Environment Variables

Set the following environment variables before deploying:

```bash
export SLACK_BOT_TOKEN=xoxb-your-token
export SLACK_SIGNING_SECRET=your-signing-secret
export KNOWLEDGE_BASE_ID=your-knowledge-base-id
export MODEL_ARN=your-model-arn
export ENABLE_DM=true  # Set to 'false' to disable direct messages
```

### Deploy

```bash
./deploy_cdk.sh --enable-dm
```

Note: The `--enable-dm` flag is optional. If you don't want to enable direct messages, simply run:

```bash
./deploy_cdk.sh
```

### Update Slack App Configuration

After deployment, update your Slack App configuration:

1. Go to the Slack API website (https://api.slack.com/apps)
2. Select your app
3. Under "Event Subscriptions", set the Request URL to the API Gateway endpoint provided in the deployment output
4. Subscribe to the bot events: `app_mention` and `message.im` (if DMs are enabled)

## How It Works

1. Slack sends an event to the API Gateway endpoint
2. The Lambda function immediately acknowledges the event with a 200 OK response
3. The Lambda function invokes itself asynchronously to process the event
4. The asynchronous Lambda function processes the event, queries the knowledge base, and sends a response to Slack

This approach ensures that:
- Slack receives an immediate acknowledgment, preventing retries
- The bot can take as long as needed to process the event and generate a response
- No duplicate responses are sent, even if multiple Lambda instances are invoked

## Troubleshooting

### Duplicate Responses

If you're still seeing duplicate responses:

1. Check the CloudWatch logs for the Lambda function to see if multiple instances are being invoked
2. Ensure that the Lambda function has permission to invoke itself asynchronously
3. Verify that the Slack app is not configured to retry events

### No Responses

If the bot is not responding:

1. Check the CloudWatch logs for errors
2. Verify that the Lambda function has permission to send messages to Slack
3. Ensure that the bot has been invited to the channel and has the necessary permissions