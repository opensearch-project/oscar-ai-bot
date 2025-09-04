#!/bin/bash
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

# Deploy Lambda stack with properly prepared assets
# This script ensures all dependencies are installed before deployment

set -e

echo "🚀 Deploying OSCAR Lambda Stack with Dependencies"
echo "================================================="

# Step 1: Prepare Lambda assets with dependencies
echo "Step 1: Preparing Lambda assets..."
./prepare_lambda_assets.sh

# Step 2: Deploy the Lambda stack (force update)
echo ""
echo "Step 2: Deploying Lambda stack..."
cdk deploy OscarLambdaStack --require-approval never --force

# Step 3: Clean up (optional - comment out if you want to keep assets for debugging)
echo ""
echo "Step 3: Cleaning up temporary assets..."
rm -rf lambda_assets

echo ""
echo "🎉 Lambda stack deployment completed successfully!"
echo ""
echo "📋 Deployed Functions:"
echo "   ✅ oscar-supervisor-agent-cdk (Main OSCAR agent)"
echo "   ✅ oscar-communication-handler-cdk (Bedrock action groups)"
echo "   ✅ oscar-jenkins-agent-cdk (Jenkins integration)"
echo "   ✅ oscar-metrics-agent-cdk (Unified metrics)"
echo ""
echo "🧪 Test the API Gateway:"
echo "curl -X POST https://ggjmr44j4i.execute-api.us-east-1.amazonaws.com/prod/slack/events \\"
echo "  -H \"Content-Type: application/json\" \\"
echo "  -d '{\"type\": \"url_verification\", \"challenge\": \"test_challenge_123\"}'"