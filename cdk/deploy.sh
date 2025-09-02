#!/bin/bash

# OSCAR CDK Deployment Script
# This script sets up the environment and deploys all OSCAR infrastructure

set -e  # Exit on any error

echo "🚀 Starting OSCAR CDK Deployment"
echo "=================================="

# Load environment variables from .env file
if [ -f .env ]; then
    echo "📋 Loading environment variables from .env file..."
    set -a  # automatically export all variables
    source .env
    set +a  # stop automatically exporting
else
    echo "❌ Error: .env file not found!"
    exit 1
fi

# Set CDK environment variables
export CDK_DEFAULT_ACCOUNT=$AWS_ACCOUNT_ID
export CDK_DEFAULT_REGION=$AWS_DEFAULT_REGION

echo "🔧 Configuration:"
echo "  Account: $CDK_DEFAULT_ACCOUNT"
echo "  Region: $CDK_DEFAULT_REGION"
echo "  Environment: ${ENVIRONMENT:-dev}"

# Validate required environment variables
if [ -z "$CDK_DEFAULT_ACCOUNT" ]; then
    echo "❌ Error: AWS_ACCOUNT_ID not set in .env file"
    exit 1
fi

if [ -z "$SLACK_BOT_TOKEN" ]; then
    echo "❌ Error: SLACK_BOT_TOKEN not set in .env file"
    exit 1
fi

if [ -z "$SLACK_SIGNING_SECRET" ]; then
    echo "❌ Error: SLACK_SIGNING_SECRET not set in .env file"
    exit 1
fi

echo "✅ Environment validation passed"

# Check if CDK is bootstrapped
echo "🔍 Checking CDK bootstrap status..."
if ! cdk bootstrap --show-template > /dev/null 2>&1; then
    echo "🏗️  Bootstrapping CDK..."
    cdk bootstrap
else
    echo "✅ CDK already bootstrapped"
fi

# Synthesize templates first to catch any errors
echo "🔨 Synthesizing CloudFormation templates..."
cdk synth

# Deploy all stacks
echo "🚀 Deploying all stacks..."
echo "This may take 15-20 minutes..."

cdk deploy --all --require-approval never

echo ""
echo "🎉 Deployment completed successfully!"
echo "=================================="
echo ""
echo "📋 Next steps:"
echo "1. Note the API Gateway URLs from the outputs above"
echo "2. Update your Slack app webhook URLs with the new endpoints"
echo "3. Test the bot functionality"
echo ""
echo "🔗 Key outputs to save:"
echo "  - SlackEventsUrl: Use this for Slack Events API"
echo "  - SlackInteractiveUrl: Use this for Slack Interactive Components"
echo "  - Bedrock Agent IDs: These will be the new agent IDs"
echo ""