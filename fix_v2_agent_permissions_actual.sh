#!/bin/bash

set -e

echo "🔐 Fixing V2 Agent Permissions with Actual Agent IDs"
echo "===================================================="

# Actual agent IDs from your deployment
AGENT_FUNCTIONS=(
    "YXSZJ659S7:oscar-test-metrics-agent-new:TestAnalyzer"
    "0NBATJIVCH:oscar-build-metrics-agent-new:BuildAnalyzer"
    "4FCARBPEYB:oscar-release-metrics-agent-new:ReleaseAnalyzer"
    "BIHPD6OLO0:oscar-deployment-metrics-agent-new:DeploymentAnalyzer"
)

echo "⚠️  UPDATE REQUIRED: Replace placeholder IDs with actual agent IDs"
echo ""

# Function to add permission
add_permission() {
    local agent_id=$1
    local function_name=$2
    local agent_name=$3
    
    echo "  Adding permission for $agent_name..."
    echo "    Agent ID: $agent_id"
    echo "    Function: $function_name"
    
    aws lambda add-permission \
        --function-name "$function_name" \
        --statement-id "bedrock-v2-$agent_id-$(date +%s)" \
        --action "lambda:InvokeFunction" \
        --principal "bedrock.amazonaws.com" \
        --source-arn "arn:aws:bedrock:us-east-1:395380602281:agent/$agent_id" \
        --region us-east-1 >/dev/null 2>&1 || echo "    (Permission may already exist)"
    
    echo "    ✅ Permission added"
    echo ""
}

# Add permissions for each agent
for entry in "${AGENT_FUNCTIONS[@]}"; do
    IFS=':' read -ra PARTS <<< "$entry"
    agent_id="${PARTS[0]}"
    function_name="${PARTS[1]}"
    agent_name="${PARTS[2]}"
    
    add_permission "$agent_id" "$function_name" "$agent_name"
done

echo "✅ Permissions updated for available agents!"
echo ""
echo "📋 Next Steps:"
echo "1. Get the actual agent IDs for the remaining agents from AWS Console"
echo "2. Update this script with the real IDs"
echo "3. Run the script again"
echo ""
echo "🔍 To get agent IDs, run:"
echo "aws bedrock-agent list-agents --region us-east-1 --query 'agentSummaries[?contains(agentName, \`v2\`)].{Name:agentName,ID:agentId}' --output table"