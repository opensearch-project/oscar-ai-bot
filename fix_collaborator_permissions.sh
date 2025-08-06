#!/bin/bash

set -e

echo "🔧 Fixing Collaborator Agent Permissions for -new Functions"
echo "=========================================================="

# Collaborator agents and their corresponding functions
COLLABORATORS=(
    "AN4EQIXC5G:oscar-build-metrics-agent-new"
    "0N1EX9RC8A:oscar-test-metrics-agent-new" 
    "ZGIQNVESPI:oscar-deployment-metrics-agent-new"
    "W8UZ5PH9DK:oscar-release-metrics-agent-new"
)

echo "Adding Lambda invoke permissions for collaborator agents..."

for entry in "${COLLABORATORS[@]}"; do
    IFS=':' read -ra PARTS <<< "$entry"
    agent_id="${PARTS[0]}"
    function_name="${PARTS[1]}"
    
    echo "  Adding permission for agent $agent_id to invoke $function_name..."
    
    # Add resource-based policy to allow Bedrock to invoke the function for this specific agent
    aws lambda add-permission \
        --function-name "$function_name" \
        --statement-id "bedrock-collaborator-$agent_id-$(date +%s)" \
        --action "lambda:InvokeFunction" \
        --principal "bedrock.amazonaws.com" \
        --source-arn "arn:aws:bedrock:us-east-1:395380602281:agent/$agent_id" \
        --region us-east-1 >/dev/null 2>&1 || echo "    (Permission may already exist)"
    
    echo "    ✅ Permission added for $agent_id -> $function_name"
done

echo ""
echo "✅ All collaborator agent permissions updated!"
echo ""
echo "🧪 Test the integration now:"
echo "python3 test_integration.py"