#!/bin/bash
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

# OSCAR Complete Deployment Script
# Deploys all infrastructure and Lambda functions

set -e

echo "🚀 OSCAR Complete Deployment Starting..."
echo "========================================"

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
    echo "✅ Loaded environment variables from .env"
else
    echo "❌ .env file not found. Please create it with required variables."
    exit 1
fi

# Validate required environment variables
required_vars=("SLACK_BOT_TOKEN" "AWS_REGION" "OSCAR_BEDROCK_AGENT_ID")
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "❌ Required environment variable $var is not set"
        exit 1
    fi
done

echo ""
echo "📋 Deployment Configuration:"
echo "   AWS Region: $AWS_REGION"
echo "   Bedrock Agent ID: $OSCAR_BEDROCK_AGENT_ID"
echo ""

# Step 1: Deploy CDK Infrastructure
echo "🏗️  Step 1: Deploying CDK Infrastructure..."
echo "============================================"
cd cdk
npm install --silent 2>/dev/null || echo "NPM packages already installed"
cdk bootstrap --region $AWS_REGION 2>/dev/null || echo "CDK already bootstrapped"
cdk deploy --require-approval never --region $AWS_REGION
cd ..
echo "✅ CDK Infrastructure deployed"

# Step 2: Deploy Metrics Lambda Functions
echo ""
echo "📊 Step 2: Deploying Metrics Lambda Functions..."
echo "==============================================="
./deploy_metrics.sh
echo "✅ Metrics Lambda functions deployed"

# Step 3: Deploy Communication Handler
echo ""
echo "💬 Step 3: Deploying Communication Handler..."
echo "============================================"
./deploy_communication_handler.sh
echo "✅ Communication Handler deployed"

# Step 4: Deploy Slack Agent (Main Bot)
echo ""
echo "🤖 Step 4: Deploying Slack Agent..."
echo "=================================="
./deploy_slack_agent.sh
echo "✅ Slack Agent deployed"

echo ""
echo "🎉 OSCAR Complete Deployment Finished!"
echo "====================================="
echo ""
echo "📋 Deployment Summary:"
echo "   ✅ CDK Infrastructure"
echo "   ✅ Metrics Lambda Functions (4)"
echo "   ✅ Communication Handler"
echo "   ✅ Slack Agent"
echo ""
echo "📝 Next Steps:"
echo "   1. Configure Slack webhook URL in your Slack app"
echo "   2. Test OSCAR with: @oscar hello"
echo "   3. Monitor CloudWatch logs for any issues"
echo ""
echo "🔗 Useful Commands:"
echo "   Update only code: ./update_all.sh"
echo "   Update metrics: ./update_metrics.sh"
echo "   Update slack agent: ./update_slack_agent.sh"