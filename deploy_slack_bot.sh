#!/bin/bash

# Deploy the Slack bot using Serverless Framework

echo "Deploying OSCAR Slack Bot..."

# Check if required environment variables are set
if [ -z "$SLACK_BOT_TOKEN" ]; then
    echo "Error: SLACK_BOT_TOKEN environment variable is not set"
    exit 1
fi

if [ -z "$SLACK_SIGNING_SECRET" ]; then
    echo "Error: SLACK_SIGNING_SECRET environment variable is not set"
    exit 1
fi

if [ -z "$KNOWLEDGE_BASE_ID" ]; then
    echo "Error: KNOWLEDGE_BASE_ID environment variable is not set"
    exit 1
fi

# Deploy using Serverless Framework
echo "Running serverless deploy..."
serverless deploy

# Get the API Gateway endpoint
ENDPOINT=$(serverless info --verbose | grep -o 'https://[^[:space:]]*/slack/events')

if [ -n "$ENDPOINT" ]; then
    echo ""
    echo "Deployment successful!"
    echo ""
    echo "API Gateway endpoint: $ENDPOINT"
    echo ""
    echo "Next steps:"
    echo "1. Go to your Slack App configuration at https://api.slack.com/apps"
    echo "2. Under 'Event Subscriptions', set the Request URL to: $ENDPOINT"
    echo "3. Subscribe to the bot events: app_mention and message.im (if DMs are enabled)"
    echo ""
else
    echo "Deployment may have failed or endpoint not found in output"
    echo "Check the logs for more information"
fi