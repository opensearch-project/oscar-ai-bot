#!/bin/bash

# Test OSCAR Limited Supervisor Agent

set -e

# Configuration variables
AWS_REGION="us-east-1"

# Prompt for agent details
read -p "Enter Agent ID: " AGENT_ID
read -p "Enter Alias ID: " ALIAS_ID

echo "Testing OSCAR Limited Supervisor Agent..."
echo "Agent ID: $AGENT_ID"
echo "Alias ID: $ALIAS_ID"

# Test basic functionality
echo ""
echo "=== Test 1: Basic greeting ==="
aws bedrock-agent-runtime invoke-agent \
    --region $AWS_REGION \
    --agent-id "$AGENT_ID" \
    --agent-alias-id "$ALIAS_ID" \
    --session-id "test-session-$(date +%s)" \
    --input-text "Hello, what can you help me with?" \
    --output json | jq -r '.completion'

echo ""
echo "=== Test 2: Documentation query ==="
aws bedrock-agent-runtime invoke-agent \
    --region $AWS_REGION \
    --agent-id "$AGENT_ID" \
    --agent-alias-id "$ALIAS_ID" \
    --session-id "test-session-$(date +%s)" \
    --input-text "How do I install OpenSearch?" \
    --output json | jq -r '.completion'

echo ""
echo "=== Test 3: Limitation test (communication) ==="
aws bedrock-agent-runtime invoke-agent \
    --region $AWS_REGION \
    --agent-id "$AGENT_ID" \
    --agent-alias-id "$ALIAS_ID" \
    --session-id "test-session-$(date +%s)" \
    --input-text "Send a message to the release channel" \
    --output json | jq -r '.completion'

echo ""
echo "=== Test 4: Limitation test (Jenkins) ==="
aws bedrock-agent-runtime invoke-agent \
    --region $AWS_REGION \
    --agent-id "$AGENT_ID" \
    --agent-alias-id "$ALIAS_ID" \
    --session-id "test-session-$(date +%s)" \
    --input-text "Run a Jenkins build job" \
    --output json | jq -r '.completion'

echo ""
echo "=== TESTING COMPLETE ==="