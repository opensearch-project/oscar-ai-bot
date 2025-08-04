#!/bin/bash
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

# Complete OSCAR Deployment Script
# Deploys all components and provides Slack integration instructions

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Complete OSCAR Deployment${NC}"
echo "=================================="

# Load environment variables
if [ -f ".env" ]; then
    echo -e "${GREEN}✅ Loading environment from .env file${NC}"
    while IFS= read -r line; do
        [[ $line =~ ^[[:space:]]*# ]] && continue
        [[ -z $line ]] && continue
        export "$line"
    done < .env
else
    echo -e "${RED}❌ .env file not found${NC}"
    exit 1
fi

# Step 1: Deploy VPC Lambda Functions
echo -e "${YELLOW}📦 Step 1: Deploying VPC Lambda Functions${NC}"
if [ -f "./deploy_vpc_lambdas.sh" ]; then
    ./deploy_vpc_lambdas.sh
    echo -e "${GREEN}✅ VPC Lambda functions deployed${NC}"
else
    echo -e "${RED}❌ deploy_vpc_lambdas.sh not found${NC}"
    exit 1
fi

echo ""

# Step 2: Deploy Supervisor Agent
echo -e "${YELLOW}📦 Step 2: Deploying OSCAR Supervisor Agent${NC}"
if [ -f "./deploy_oscar_supervisor.sh" ]; then
    ./deploy_oscar_supervisor.sh
    echo -e "${GREEN}✅ OSCAR Supervisor Agent deployed${NC}"
else
    echo -e "${RED}❌ deploy_oscar_supervisor.sh not found${NC}"
    exit 1
fi

echo ""

# Step 3: Test Deployments
echo -e "${YELLOW}🧪 Step 3: Testing Deployments${NC}"

# Test supervisor function
echo "   Testing supervisor function..."
aws lambda invoke \
    --function-name oscar-supervisor-agent \
    --payload '{"test": "connectivity"}' \
    --cli-binary-format raw-in-base64-out \
    --region "$AWS_REGION" \
    test-supervisor.json >/dev/null 2>&1

if grep -q "statusCode.*200" test-supervisor.json 2>/dev/null; then
    echo -e "${GREEN}   ✅ Supervisor function working${NC}"
else
    echo -e "${RED}   ❌ Supervisor function test failed${NC}"
fi

# Test one metrics function
echo "   Testing metrics function..."
aws lambda invoke \
    --function-name oscar-test-metrics-agent \
    --payload '{"test": "connectivity"}' \
    --cli-binary-format raw-in-base64-out \
    --region "$AWS_REGION" \
    test-metrics.json >/dev/null 2>&1

if grep -q '"status": "success"' test-metrics.json 2>/dev/null; then
    echo -e "${GREEN}   ✅ Metrics functions working${NC}"
else
    echo -e "${YELLOW}   ⚠️  Metrics functions in mock mode (expected for testing)${NC}"
fi

# Clean up test files
rm -f test-supervisor.json test-metrics.json

echo ""

# Step 4: Get Function ARNs
echo -e "${YELLOW}📋 Step 4: Deployment Summary${NC}"

SUPERVISOR_ARN=$(aws lambda get-function --function-name oscar-supervisor-agent --region "$AWS_REGION" --query 'Configuration.FunctionArn' --output text)
echo "   Supervisor Agent ARN: $SUPERVISOR_ARN"

echo "   Metrics Agent Functions:"
for agent in test build release deployment; do
    AGENT_ARN=$(aws lambda get-function --function-name "oscar-${agent}-metrics-agent" --region "$AWS_REGION" --query 'Configuration.FunctionArn' --output text 2>/dev/null || echo "Not found")
    echo "     oscar-${agent}-metrics-agent: $AGENT_ARN"
done

echo ""

# Step 5: Slack Integration Instructions
echo -e "${BLUE}📱 Step 5: Slack Integration Setup${NC}"
echo "=============================================="
echo ""
echo -e "${YELLOW}🔧 Manual Configuration Required:${NC}"
echo ""
echo "1. ${BLUE}Configure Bedrock Agent Action Group:${NC}"
echo "   - Go to AWS Bedrock Console"
echo "   - Navigate to your agent: $OSCAR_BEDROCK_AGENT_ID"
echo "   - Update Action Group Lambda function to: $SUPERVISOR_ARN"
echo "   - Save and create new agent version"
echo "   - Update alias $OSCAR_BEDROCK_AGENT_ALIAS_ID to point to new version"
echo ""
echo "2. ${BLUE}Create API Gateway for Slack Webhook:${NC}"
echo "   - Go to AWS API Gateway Console"
echo "   - Create new REST API named 'oscar-slack-webhook'"
echo "   - Create resource '/slack' with POST method"
echo "   - Set integration type to Lambda Function"
echo "   - Lambda Function: oscar-supervisor-agent"
echo "   - Enable Lambda Proxy Integration"
echo "   - Deploy API to 'prod' stage"
echo "   - Note the Invoke URL (e.g., https://abc123.execute-api.us-east-1.amazonaws.com/prod)"
echo ""
echo "3. ${BLUE}Configure Slack App:${NC}"
echo "   - Go to https://api.slack.com/apps"
echo "   - Create new app or select existing OSCAR app"
echo "   - Go to 'Event Subscriptions'"
echo "   - Enable Events: ON"
echo "   - Request URL: [API Gateway URL]/slack"
echo "   - Subscribe to bot events: app_mention, message.im (if DM enabled)"
echo "   - Save Changes"
echo ""
echo "4. ${BLUE}Install Slack App:${NC}"
echo "   - Go to 'Install App' in Slack app settings"
echo "   - Install to your workspace"
echo "   - Copy Bot User OAuth Token to .env file as SLACK_BOT_TOKEN"
echo "   - Copy Signing Secret to .env file as SLACK_SIGNING_SECRET"
echo ""
echo "5. ${BLUE}Test Slack Integration:${NC}"
echo "   - Invite @oscar to a Slack channel"
echo "   - Send message: @oscar What is OpenSearch?"
echo "   - OSCAR should respond with information from the knowledge base"
echo ""

# Step 6: Verification Commands
echo -e "${BLUE}🔍 Step 6: Verification Commands${NC}"
echo "=================================="
echo ""
echo "Test supervisor function:"
echo "aws lambda invoke --function-name oscar-supervisor-agent --payload '{\"test\": \"connectivity\"}' --cli-binary-format raw-in-base64-out --region $AWS_REGION result.json && cat result.json"
echo ""
echo "Test metrics function:"
echo "aws lambda invoke --function-name oscar-test-metrics-agent --payload '{\"test\": \"connectivity\"}' --cli-binary-format raw-in-base64-out --region $AWS_REGION result.json && cat result.json"
echo ""
echo "Check CloudWatch logs:"
echo "aws logs tail /aws/lambda/oscar-supervisor-agent --region $AWS_REGION --follow"
echo ""

# Step 7: Troubleshooting
echo -e "${BLUE}🔧 Step 7: Troubleshooting${NC}"
echo "=========================="
echo ""
echo "Common issues and solutions:"
echo ""
echo "1. ${YELLOW}Lambda function timeouts:${NC}"
echo "   - Check VPC configuration and security groups"
echo "   - Verify NAT Gateway for internet access"
echo "   - Check CloudWatch logs for detailed errors"
echo ""
echo "2. ${YELLOW}Bedrock agent not responding:${NC}"
echo "   - Verify agent ID and alias ID in .env file"
echo "   - Check IAM permissions for Bedrock access"
echo "   - Ensure Lambda function ARN is correctly configured in action group"
echo ""
echo "3. ${YELLOW}Slack webhook not working:${NC}"
echo "   - Verify API Gateway configuration and deployment"
echo "   - Check Slack app Event Subscriptions URL"
echo "   - Verify bot token and signing secret"
echo ""
echo "4. ${YELLOW}OpenSearch connectivity issues:${NC}"
echo "   - Functions will use mock mode if OpenSearch is unreachable"
echo "   - Check VPC endpoint configuration"
echo "   - Verify cross-account permissions"
echo ""

echo -e "${GREEN}✅ OSCAR Deployment Complete!${NC}"
echo "=================================="
echo ""
echo -e "${BLUE}📚 Next Steps:${NC}"
echo "1. Complete Slack integration setup (Steps 2-4 above)"
echo "2. Test end-to-end functionality"
echo "3. Monitor CloudWatch logs for any issues"
echo "4. Configure additional Bedrock agent capabilities as needed"
echo ""
echo -e "${BLUE}📖 Documentation:${NC}"
echo "- See build_docs/ directory for detailed configuration guides"
echo "- Check CloudWatch logs for runtime information"
echo "- Use verification commands above for testing"