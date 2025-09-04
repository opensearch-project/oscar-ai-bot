#!/bin/bash
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

# Deploy all OSCAR CDK stacks in the correct order
# This script ensures proper dependency management and asset preparation

set -e

echo "🚀 Deploying All OSCAR CDK Stacks"
echo "=================================="

# Step 1: Prepare Lambda assets with dependencies
echo "Step 1: Preparing Lambda assets..."
./prepare_lambda_assets.sh

# Step 2: Deploy all stacks in dependency order
echo ""
echo "Step 2: Deploying all stacks..."
echo "   📦 Deploying Secrets Stack..."
cdk deploy OscarSecretsStack --require-approval never

echo "   🔐 Deploying Permissions Stack..."
cdk deploy OscarPermissionsStack --require-approval never

echo "   ⚡ Deploying Lambda Stack..."
cdk deploy OscarLambdaStack --require-approval never

echo "   🌐 Deploying API Gateway Stack..."
cdk deploy OscarApiGatewayStack --require-approval never

# Step 3: Clean up temporary assets
echo ""
echo "Step 3: Cleaning up temporary assets..."
rm -rf lambda_assets

echo ""
echo "🎉 All OSCAR stacks deployed successfully!"
echo ""
echo "📋 Deployed Stacks:"
echo "   ✅ OscarSecretsStack (Environment secrets)"
echo "   ✅ OscarPermissionsStack (IAM roles and policies)"
echo "   ✅ OscarLambdaStack (Lambda functions)"
echo "   ✅ OscarApiGatewayStack (API Gateway)"
echo ""
echo "📋 Deployed Functions:"
echo "   ✅ oscar-supervisor-agent-cdk (Main OSCAR agent)"
echo "   ✅ oscar-communication-handler-cdk (Bedrock action groups)"
echo "   ✅ oscar-jenkins-agent-cdk (Jenkins integration)"
echo "   ✅ oscar-metrics-agent-cdk (Unified metrics)"
echo ""
echo "🧪 Test the API Gateway:"
echo "curl -X POST \$(aws cloudformation describe-stacks --stack-name OscarApiGatewayStack --query 'Stacks[0].Outputs[?OutputKey==\`SlackEventsUrl\`].OutputValue' --output text) \\"
echo "  -H \"Content-Type: application/json\" \\"
echo "  -d '{\"type\": \"url_verification\", \"challenge\": \"test_challenge_123\"}'"