#!/bin/bash
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

# Complete OSCAR Deployment and Testing Script
# Deploys all components, tests functionality, and provides integration instructions

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Complete OSCAR Deployment and Testing${NC}"
echo "=============================================="

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

echo ""

# Step 1: Deploy VPC Lambda Functions
echo -e "${YELLOW}📦 Step 1: Deploying VPC Lambda Functions${NC}"
echo "=============================================="
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
echo "=============================================="
if [ -f "./deploy_oscar_supervisor.sh" ]; then
    ./deploy_oscar_supervisor.sh
    echo -e "${GREEN}✅ OSCAR Supervisor Agent deployed${NC}"
else
    echo -e "${RED}❌ deploy_oscar_supervisor.sh not found${NC}"
    exit 1
fi

echo ""

# Step 3: Comprehensive Testing
echo -e "${YELLOW}🧪 Step 3: Comprehensive Testing${NC}"
echo "=================================="

# Test supervisor function
echo "Testing supervisor function..."
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
    cat test-supervisor.json 2>/dev/null || echo "No response file"
fi

# Test metrics functions
echo "Testing metrics functions..."
metrics_functions=("oscar-test-metrics-agent" "oscar-build-metrics-agent" "oscar-release-metrics-agent" "oscar-deployment-metrics-agent")

for func in "${metrics_functions[@]}"; do
    echo "   Testing $func..."
    aws lambda invoke \
        --function-name "$func" \
        --payload '{"test": "connectivity"}' \
        --cli-binary-format raw-in-base64-out \
        --region "$AWS_REGION" \
        "test-${func}.json" >/dev/null 2>&1
    
    if grep -q '"mock_mode": true' "test-${func}.json" 2>/dev/null; then
        echo -e "${GREEN}   ✅ $func working (mock mode)${NC}"
    elif grep -q '"response"' "test-${func}.json" 2>/dev/null; then
        echo -e "${GREEN}   ✅ $func working${NC}"
    else
        echo -e "${RED}   ❌ $func test failed${NC}"
        cat "test-${func}.json" 2>/dev/null || echo "No response file"
    fi
done

# Clean up test files
rm -f test-*.json

echo ""

# Step 4: Get Function ARNs
echo -e "${YELLOW}📋 Step 4: Deployment Summary${NC}"
echo "============================="

SUPERVISOR_ARN=$(aws lambda get-function --function-name oscar-supervisor-agent --region "$AWS_REGION" --query 'Configuration.FunctionArn' --output text)
echo -e "${BLUE}Supervisor Agent:${NC}"
echo "   oscar-supervisor-agent: $SUPERVISOR_ARN"

echo ""
echo -e "${BLUE}Metrics Agent Functions:${NC}"
for agent in test build release deployment; do
    AGENT_ARN=$(aws lambda get-function --function-name "oscar-${agent}-metrics-agent" --region "$AWS_REGION" --query 'Configuration.FunctionArn' --output text 2>/dev/null || echo "Not found")
    echo "   oscar-${agent}-metrics-agent: $AGENT_ARN"
done

echo ""

# Step 5: Configuration Status
echo -e "${YELLOW}🔧 Step 5: Configuration Status${NC}"
echo "==============================="
echo -e "${BLUE}Environment Configuration:${NC}"
echo "   AWS Region: $AWS_REGION"
echo "   OSCAR Agent ID: $OSCAR_BEDROCK_AGENT_ID"
echo "   OSCAR Agent Alias: $OSCAR_BEDROCK_AGENT_ALIAS_ID"
echo "   Sessions Table: $SESSIONS_TABLE_NAME"
echo "   Context Table: $CONTEXT_TABLE_NAME"
echo "   VPC ID: $VPC_ID"
echo "   Security Group: $SECURITY_GROUP_ID"

echo ""

# Step 6: Slack Integration Instructions
echo -e "${BLUE}📱 Step 6: Slack Integration Setup${NC}"
echo "===================================="
echo ""
echo -e "${YELLOW}🔧 Required Manual Steps:${NC}"
echo ""
echo "1. ${BLUE}Configure Bedrock Agent Action Group:${NC}"
echo "   - Go to AWS Bedrock Console"
echo "   - Navigate to your agent: $OSCAR_BEDROCK_AGENT_ID"
echo "   - Update Action Group Lambda function to:"
echo "     $SUPERVISOR_ARN"
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
echo "   - Note the Invoke URL"
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
echo "   - Redeploy supervisor: ./deploy_oscar_supervisor.sh"
echo ""
echo "5. ${BLUE}Test Slack Integration:${NC}"
echo "   - Invite @oscar to a Slack channel"
echo "   - Send message: @oscar What is OpenSearch?"
echo "   - OSCAR should respond with information from the knowledge base"
echo ""

# Step 7: Verification Commands
echo -e "${BLUE}🔍 Step 7: Verification Commands${NC}"
echo "================================="
echo ""
echo "Test supervisor function:"
echo "aws lambda invoke --function-name oscar-supervisor-agent \\"
echo "  --payload '{\"test\": \"connectivity\"}' \\"
echo "  --cli-binary-format raw-in-base64-out \\"
echo "  --region $AWS_REGION result.json && cat result.json"
echo ""
echo "Test metrics function:"
echo "aws lambda invoke --function-name oscar-test-metrics-agent \\"
echo "  --payload '{\"test\": \"connectivity\"}' \\"
echo "  --cli-binary-format raw-in-base64-out \\"
echo "  --region $AWS_REGION result.json && cat result.json"
echo ""
echo "Check CloudWatch logs:"
echo "aws logs tail /aws/lambda/oscar-supervisor-agent --region $AWS_REGION --follow"
echo ""

# Step 8: Documentation References
echo -e "${BLUE}📚 Step 8: Documentation${NC}"
echo "========================="
echo ""
echo "Detailed guides available in build_docs/:"
echo "   - SLACK_INTEGRATION_GUIDE.md - Complete Slack setup"
echo "   - MANUAL_AGENT_CONFIGURATION.md - Bedrock agent configuration"
echo "   - METRICS_SYSTEM_OVERVIEW.md - System architecture"
echo ""

# Step 9: Troubleshooting
echo -e "${BLUE}🔧 Step 9: Common Issues & Solutions${NC}"
echo "===================================="
echo ""
echo "1. ${YELLOW}Lambda function timeouts:${NC}"
echo "   - Metrics functions use mock mode to avoid VPC connectivity delays"
echo "   - Check VPC configuration and security groups for real data access"
echo "   - Verify NAT Gateway for internet access"
echo ""
echo "2. ${YELLOW}Bedrock agent not responding:${NC}"
echo "   - Verify agent ID and alias ID in .env file"
echo "   - Check IAM permissions for Bedrock access"
echo "   - Ensure Lambda function ARN is correctly configured in action group"
echo ""
echo "3. ${YELLOW}Slack webhook not working:${NC}"
echo "   - Verify API Gateway configuration and deployment"
echo "   - Check Slack app Event Subscriptions URL"
echo "   - Verify bot token and signing secret in .env"
echo ""
echo "4. ${YELLOW}OpenSearch connectivity:${NC}"
echo "   - Functions currently use mock mode for testing"
echo "   - To enable real data, update metrics/lambda_function.py"
echo "   - Ensure VPC endpoint and security groups are configured"
echo ""

echo -e "${GREEN}✅ OSCAR Complete Deployment Finished!${NC}"
echo "========================================"
echo ""
echo -e "${BLUE}🎉 Next Steps:${NC}"
echo "1. Complete Slack integration setup (Steps above)"
echo "2. Test end-to-end functionality"
echo "3. Monitor CloudWatch logs for any issues"
echo "4. Configure additional Bedrock agent capabilities as needed"
echo ""
echo -e "${BLUE}📞 Support:${NC}"
echo "- Check build_docs/ for detailed guides"
echo "- Monitor CloudWatch logs for runtime issues"
echo "- Use verification commands above for testing"
echo ""
echo -e "${BLUE}🚀 OSCAR is ready for Slack integration!${NC}"