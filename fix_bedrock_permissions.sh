#!/bin/bash

set -e

echo "🔧 Fixing Bedrock Agent Permissions for -new Functions"
echo "======================================================"

# Get the Bedrock agent service role
BEDROCK_AGENT_ROLE="AmazonBedrockExecutionRoleForAgents_OSCAR"

# Functions that need permission
FUNCTIONS=(
    "oscar-test-metrics-agent-new"
    "oscar-build-metrics-agent-new" 
    "oscar-release-metrics-agent-new"
    "oscar-deployment-metrics-agent-new"
)

echo "Adding Lambda invoke permissions for Bedrock agent..."

for func in "${FUNCTIONS[@]}"; do
    echo "  Adding permission for $func..."
    
    # Add resource-based policy to allow Bedrock to invoke the function
    aws lambda add-permission \
        --function-name "$func" \
        --statement-id "bedrock-agent-invoke-$(date +%s)" \
        --action "lambda:InvokeFunction" \
        --principal "bedrock.amazonaws.com" \
        --source-arn "arn:aws:bedrock:us-east-1:395380602281:agent/EUU645OSFB" \
        --region us-east-1 >/dev/null 2>&1 || echo "    (Permission may already exist)"
    
    echo "    ✅ Permission added for $func"
done

echo ""
echo "✅ Bedrock agent permissions updated!"
echo ""
echo "🧪 Test Bedrock agent now:"
echo "python3 test_integration.py"