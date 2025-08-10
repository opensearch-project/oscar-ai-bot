#!/bin/bash
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

# Update ALL Lambda function code while preserving permissions
# This is the safe way to update your deployment without losing configurations

set -e

echo "🔄 Updating All OSCAR Lambda Functions (Code Only)..."
echo "===================================================="

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
    echo "✅ Loaded environment variables from .env"
else
    echo "❌ .env file not found. Please create it with required variables."
    exit 1
fi

echo ""
echo "📋 Update Configuration:"
echo "   AWS Region: $AWS_REGION"
echo "   Mode: Code updates only (preserves all permissions)"
echo ""

# Step 1: Update Metrics Lambda Functions
echo "📊 Step 1: Updating Metrics Lambda Functions..."
echo "=============================================="
./update_metrics.sh
echo "✅ Metrics functions updated"

# Step 2: Update Communication Handler
echo ""
echo "💬 Step 2: Updating Communication Handler..."
echo "==========================================="
./update_communication_handler.sh
echo "✅ Communication Handler updated"

# Step 3: Update Slack Agent
echo ""
echo "🤖 Step 3: Updating Slack Agent..."
echo "================================="
./update_slack_agent.sh
echo "✅ Slack Agent updated"

echo ""
echo "🎉 All OSCAR Lambda Functions Updated!"
echo "====================================="
echo ""
echo "📋 Updated Functions:"
echo "   ✅ oscar-test-metrics-agent-new"
echo "   ✅ oscar-build-metrics-agent-new"
echo "   ✅ oscar-release-metrics-agent-new"
echo "   ✅ oscar-deployment-metrics-agent-new"
echo "   ✅ oscar-communication-handler"
echo "   ✅ oscar-supervisor-agent"
echo ""
echo "🔒 Preserved (NOT touched):"
echo "   ✅ All IAM roles and permissions"
echo "   ✅ Environment variables"
echo "   ✅ VPC configurations"
echo "   ✅ API Gateway permissions"
echo "   ✅ Bedrock agent permissions"
echo "   ✅ DynamoDB permissions"
echo ""
echo "🧪 Test Commands:"
echo "   @oscar hello"
echo "   @oscar show me test metrics"
echo "   aws lambda invoke --function-name oscar-supervisor-agent --payload '{\"test\": \"connectivity\"}' --region $AWS_REGION test.json"