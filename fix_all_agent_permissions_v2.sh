#!/bin/bash

set -e

echo "🔐 Setting Up Permissions for New Agent Configuration v2"
echo "======================================================"

# Agent mappings (update with actual agent IDs after creation)
AGENT_FUNCTIONS=(
    "TEST_AGENT_ID_V2:oscar-test-metrics-agent-new"
    "BUILD_AGENT_ID_V2:oscar-build-metrics-agent-new"
    "RELEASE_AGENT_ID_V2:oscar-release-metrics-agent-new"
    "DEPLOYMENT_AGENT_ID_V2:oscar-deployment-metrics-agent-new"
    "SUPERVISOR_AGENT_ID_V2:oscar-supervisor-agent"
)

echo "⚠️  IMPORTANT: Update this script with actual agent IDs after creation"
echo ""
echo "Replace the following placeholders with actual agent IDs:"
echo "  TEST_AGENT_ID_V2 → Actual test agent ID"
echo "  BUILD_AGENT_ID_V2 → Actual build agent ID"
echo "  RELEASE_AGENT_ID_V2 → Actual release agent ID"
echo "  DEPLOYMENT_AGENT_ID_V2 → Actual deployment agent ID"
echo "  SUPERVISOR_AGENT_ID_V2 → Actual supervisor agent ID"
echo ""

# Function to add permission for an agent to invoke a Lambda function
add_agent_permission() {
    local agent_id=$1
    local function_name=$2
    local description=$3
    
    echo "  Adding permission for $description..."
    echo "    Agent: $agent_id"
    echo "    Function: $function_name"
    
    # Add resource-based policy
    aws lambda add-permission \
        --function-name "$function_name" \
        --statement-id "bedrock-agent-v2-$agent_id-$(date +%s)" \
        --action "lambda:InvokeFunction" \
        --principal "bedrock.amazonaws.com" \
        --source-arn "arn:aws:bedrock:us-east-1:395380602281:agent/$agent_id" \
        --region us-east-1 >/dev/null 2>&1 || echo "    (Permission may already exist)"
    
    echo "    ✅ Permission added"
}

echo "📋 Adding Lambda invoke permissions for all agents..."
echo ""

# Add permissions for each agent
for entry in "${AGENT_FUNCTIONS[@]}"; do
    IFS=':' read -ra PARTS <<< "$entry"
    agent_id="${PARTS[0]}"
    function_name="${PARTS[1]}"
    
    case $agent_id in
        "TEST_AGENT_ID_V2")
            add_agent_permission "$agent_id" "$function_name" "Test Metrics Agent v2"
            ;;
        "BUILD_AGENT_ID_V2")
            add_agent_permission "$agent_id" "$function_name" "Build Metrics Agent v2"
            ;;
        "RELEASE_AGENT_ID_V2")
            add_agent_permission "$agent_id" "$function_name" "Release Metrics Agent v2"
            ;;
        "DEPLOYMENT_AGENT_ID_V2")
            add_agent_permission "$agent_id" "$function_name" "Deployment Metrics Agent v2"
            ;;
        "SUPERVISOR_AGENT_ID_V2")
            add_agent_permission "$agent_id" "$function_name" "Supervisor Agent v2"
            ;;
    esac
    echo ""
done

echo "✅ All permissions configured!"
echo ""
echo "🧪 Next Steps:"
echo "1. Test individual agents with their specific queries"
echo "2. Test supervisor agent routing logic"
echo "3. Verify knowledge base integration"
echo "4. Run comprehensive integration tests"
echo ""
echo "📝 Test Commands:"
echo "# Individual agent test"
echo "aws bedrock-agent-runtime invoke-agent --agent-id TEST_AGENT_ID_V2 --agent-alias-id TESTALIASID --session-id test-session --input-text 'Show test coverage trends'"
echo ""
echo "# Supervisor agent test"
echo "aws bedrock-agent-runtime invoke-agent --agent-id SUPERVISOR_AGENT_ID_V2 --agent-alias-id SUPERVISORALIASID --session-id test-session --input-text 'How do I configure OpenSearch security?'"