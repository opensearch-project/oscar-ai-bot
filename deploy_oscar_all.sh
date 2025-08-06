#!/bin/bash
# Ultimate OSCAR Deployment Script
# One command to deploy everything

set -e

echo "🚀 OSCAR Complete Deployment"
echo "============================"
echo ""
echo "This script will deploy:"
echo "  ✅ Metrics Lambda functions with Bedrock permissions"
echo "  ✅ Supervisor Lambda function"
echo "  ✅ DynamoDB tables for session/context storage"
echo "  ✅ API Gateway with Slack webhook endpoint"
echo "  ✅ All necessary IAM roles and permissions"
echo ""

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "❌ .env file not found!"
    echo ""
    echo "Please create a .env file with the following variables:"
    echo "  AWS_REGION=us-east-1"
    echo "  SLACK_BOT_TOKEN=xoxb-your-token"
    echo "  SLACK_SIGNING_SECRET=your-secret"
    echo "  OSCAR_BEDROCK_AGENT_ID=your-agent-id"
    echo "  OSCAR_BEDROCK_AGENT_ALIAS_ID=your-alias-id"
    echo ""
    exit 1
fi

# Confirm deployment
read -p "Continue with deployment? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Deployment cancelled."
    exit 0
fi

echo ""
echo "Starting automated deployment..."
echo ""

# Run the complete automated deployment
./deploy_oscar_complete_automated.sh

echo ""
echo "🎉 Deployment complete!"
echo ""
echo "Next steps:"
echo "1. Configure your Slack app with the webhook URL shown above"
echo "2. Test OSCAR by mentioning it in a Slack channel"
echo "3. Monitor CloudWatch logs if needed"