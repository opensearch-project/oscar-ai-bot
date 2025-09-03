#!/bin/bash

# Deploy OSCAR Limited Supervisor Agent using AWS CLI with JSON configurations
# Uses JSON files for clean, maintainable configuration

set -e

# Configuration variables
AWS_REGION="us-east-1"

echo "Creating OSCAR Limited Supervisor Agent from JSON configurations..."

# Check if required JSON files exist
for file in oscar-limited-agent-config.json oscar-limited-action-group.json; do
    if [[ ! -f "$file" ]]; then
        echo "Error: Required file $file not found"
        exit 1
    fi
done

# Create the agent using JSON config
echo "Creating agent..."
AGENT_RESPONSE=$(aws bedrock-agent create-agent \
    --region $AWS_REGION \
    --cli-input-json file://oscar-limited-agent-config.json \
    --output json)

# Extract agent ID from response
AGENT_ID=$(echo $AGENT_RESPONSE | jq -r '.agent.agentId')
echo "Created agent with ID: $AGENT_ID"

# Wait for agent to be ready
echo "Waiting for agent to be ready..."
sleep 10

# Create action group using JSON config
echo "Creating action group..."
aws bedrock-agent create-agent-action-group \
    --region $AWS_REGION \
    --agent-id "$AGENT_ID" \
    --agent-version "DRAFT" \
    --cli-input-json file://oscar-limited-action-group.json

echo "Action group created successfully"

# Associate knowledge base if config exists
if [[ -f "oscar-limited-knowledge-base.json" ]]; then
    echo "Associating knowledge base..."
    aws bedrock-agent associate-agent-knowledge-base \
        --region $AWS_REGION \
        --agent-id "$AGENT_ID" \
        --agent-version "DRAFT" \
        --cli-input-json file://oscar-limited-knowledge-base.json
    echo "Knowledge base associated successfully"
fi

# Create collaborators if config exists
if [[ -f "oscar-limited-collaborators.json" ]]; then
    echo "Creating collaborators..."
    
    # Read collaborators array and create each one
    jq -c '.[]' oscar-limited-collaborators.json | while read collaborator; do
        collaborator_name=$(echo $collaborator | jq -r '.collaboratorName')
        echo "Creating collaborator: $collaborator_name"
        
        # Create temporary file for this collaborator
        echo $collaborator > temp_collaborator.json
        
        aws bedrock-agent create-agent-collaborator \
            --region $AWS_REGION \
            --agent-id "$AGENT_ID" \
            --agent-version "DRAFT" \
            --client-token "${collaborator_name}-$(date +%s)" \
            --cli-input-json file://temp_collaborator.json
        
        rm temp_collaborator.json
    done
    
    echo "Collaborators created successfully"
fi

# Prepare the agent (this creates a version)
echo "Preparing agent..."
PREPARE_RESPONSE=$(aws bedrock-agent prepare-agent \
    --region $AWS_REGION \
    --agent-id "$AGENT_ID" \
    --output json)

echo "Agent prepared successfully"

# Create alias
echo "Creating agent alias..."
ALIAS_RESPONSE=$(aws bedrock-agent create-agent-alias \
    --region $AWS_REGION \
    --agent-id "$AGENT_ID" \
    --agent-alias-name "live" \
    --description "Live alias for OSCAR Limited Supervisor Agent" \
    --output json)

ALIAS_ID=$(echo $ALIAS_RESPONSE | jq -r '.agentAlias.agentAliasId')
echo "Created alias with ID: $ALIAS_ID"

echo ""
echo "=== DEPLOYMENT COMPLETE ==="
echo "Agent ID: $AGENT_ID"
echo "Alias ID: $ALIAS_ID"
echo ""
echo "You can now test the agent using:"
echo "aws bedrock-agent-runtime invoke-agent --region $AWS_REGION --agent-id $AGENT_ID --agent-alias-id $ALIAS_ID --session-id test-session --input-text 'Hello, what can you help me with?'"