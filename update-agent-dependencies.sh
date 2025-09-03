#!/bin/bash

# Update Agent Dependencies Script
# Updates existing agents when Lambda functions or collaborators change

set -e

# Configuration
AWS_REGION="us-east-1"
CONFIG_FILE="deployment-config.json"
AGENT_IDS_FILE="deployed-agent-ids.json"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Get agent ID from tracking file
get_agent_id() {
    local agent_type=$1
    jq -r --arg type "$agent_type" '.[$type].agent_id // empty' "$AGENT_IDS_FILE"
}

# Check if Lambda function exists
check_lambda_exists() {
    local function_name=$1
    aws lambda get-function --region "$AWS_REGION" --function-name "$function_name" >/dev/null 2>&1
}

# Update Lambda ARN in action group
update_action_group_lambda() {
    local agent_id=$1
    local action_group_id=$2
    local new_lambda_arn=$3
    local action_group_name=$4
    
    log_info "Updating Lambda ARN for action group: $action_group_name"
    
    # Get current action group configuration
    local current_config=$(aws bedrock-agent get-agent-action-group \
        --region "$AWS_REGION" \
        --agent-id "$agent_id" \
        --agent-version "DRAFT" \
        --action-group-id "$action_group_id" \
        --output json)
    
    # Extract current configuration and update Lambda ARN
    echo "$current_config" | jq --arg arn "$new_lambda_arn" \
        '.agentActionGroup | {
            actionGroupName: .actionGroupName,
            description: .description,
            actionGroupState: .actionGroupState,
            actionGroupExecutor: {
                lambda: {
                    lambdaArn: $arn
                }
            },
            functionSchema: .functionSchema
        }' > "temp_update_action_group.json"
    
    # Update the action group
    aws bedrock-agent update-agent-action-group \
        --region "$AWS_REGION" \
        --agent-id "$agent_id" \
        --agent-version "DRAFT" \
        --action-group-id "$action_group_id" \
        --cli-input-json "file://temp_update_action_group.json"
    
    rm "temp_update_action_group.json"
    log_success "Updated Lambda ARN for action group: $action_group_name"
}

# Update collaborator agent ID
update_collaborator() {
    local agent_id=$1
    local collaborator_id=$2
    local new_collaborator_agent_id=$3
    local collaborator_name=$4
    
    log_info "Updating collaborator: $collaborator_name"
    
    # Get current collaborator configuration
    local current_config=$(aws bedrock-agent get-agent-collaborator \
        --region "$AWS_REGION" \
        --agent-id "$agent_id" \
        --agent-version "DRAFT" \
        --collaborator-id "$collaborator_id" \
        --output json)
    
    # Extract current configuration and update agent ID
    echo "$current_config" | jq --arg new_id "$new_collaborator_agent_id" \
        '.agentCollaborator | {
            collaboratorName: .collaboratorName,
            collaborationInstruction: .collaborationInstruction,
            agentDescriptor: {
                agentId: $new_id,
                agentVersion: .agentDescriptor.agentVersion
            },
            relayConversationHistory: .relayConversationHistory
        }' > "temp_update_collaborator.json"
    
    # Update the collaborator
    aws bedrock-agent update-agent-collaborator \
        --region "$AWS_REGION" \
        --agent-id "$agent_id" \
        --agent-version "DRAFT" \
        --collaborator-id "$collaborator_id" \
        --cli-input-json "file://temp_update_collaborator.json"
    
    rm "temp_update_collaborator.json"
    log_success "Updated collaborator: $collaborator_name"
}

# Update agent dependencies
update_agent() {
    local agent_type=$1
    
    log_info "Updating dependencies for $agent_type agent..."
    
    # Get agent ID
    local agent_id=$(get_agent_id "$agent_type")
    if [[ -z "$agent_id" ]]; then
        log_error "Agent $agent_type not found in deployed agents"
        return 1
    fi
    
    log_info "Found $agent_type agent ID: $agent_id"
    
    # Update Lambda ARNs in action groups
    local lambda_function=$(jq -r --arg type "$agent_type" '.agents[$type].lambda_function' "$CONFIG_FILE")
    if [[ "$lambda_function" != "null" ]] && check_lambda_exists "$lambda_function"; then
        local lambda_arn="arn:aws:lambda:$AWS_REGION:395380602281:function:$lambda_function"
        
        # Get action groups for this agent
        local action_groups=$(aws bedrock-agent list-agent-action-groups \
            --region "$AWS_REGION" \
            --agent-id "$agent_id" \
            --agent-version "DRAFT" \
            --output json)
        
        # Update each action group
        echo "$action_groups" | jq -c '.actionGroupSummaries[]' | while read action_group; do
            local action_group_id=$(echo "$action_group" | jq -r '.actionGroupId')
            local action_group_name=$(echo "$action_group" | jq -r '.actionGroupName')
            
            # Skip communication action group for privileged agent (different Lambda)
            if [[ "$action_group_name" == "communication-orchestration" ]]; then
                continue
            fi
            
            update_action_group_lambda "$agent_id" "$action_group_id" "$lambda_arn" "$action_group_name"
        done
    fi
    
    # Update communication Lambda for privileged agent
    if [[ "$agent_type" == "oscar-privileged" ]]; then
        local comm_lambda=$(jq -r --arg type "$agent_type" '.agents[$type].communication_lambda' "$CONFIG_FILE")
        if [[ "$comm_lambda" != "null" ]] && check_lambda_exists "$comm_lambda"; then
            local comm_arn="arn:aws:lambda:$AWS_REGION:395380602281:function:$comm_lambda"
            
            # Find communication action group
            local action_groups=$(aws bedrock-agent list-agent-action-groups \
                --region "$AWS_REGION" \
                --agent-id "$agent_id" \
                --agent-version "DRAFT" \
                --output json)
            
            local comm_action_group_id=$(echo "$action_groups" | jq -r '.actionGroupSummaries[] | select(.actionGroupName == "communication-orchestration") | .actionGroupId')
            
            if [[ -n "$comm_action_group_id" ]]; then
                update_action_group_lambda "$agent_id" "$comm_action_group_id" "$comm_arn" "communication-orchestration"
            fi
        fi
    fi
    
    # Update collaborators
    local collaborators=$(jq -r --arg type "$agent_type" '.agents[$type].collaborators[]?' "$CONFIG_FILE")
    
    if [[ -n "$collaborators" ]]; then
        # Get current collaborators
        local current_collaborators=$(aws bedrock-agent list-agent-collaborators \
            --region "$AWS_REGION" \
            --agent-id "$agent_id" \
            --agent-version "DRAFT" \
            --output json)
        
        for collaborator_type in $collaborators; do
            local new_collaborator_id=$(get_agent_id "$collaborator_type")
            if [[ -n "$new_collaborator_id" ]]; then
                # Find matching collaborator by name pattern
                local collaborator_info=$(echo "$current_collaborators" | jq -r --arg type "$collaborator_type" \
                    '.agentCollaboratorSummaries[] | select(.collaboratorName | test($type; "i")) | {id: .collaboratorId, name: .collaboratorName}')
                
                if [[ -n "$collaborator_info" ]]; then
                    local collaborator_id=$(echo "$collaborator_info" | jq -r '.id')
                    local collaborator_name=$(echo "$collaborator_info" | jq -r '.name')
                    
                    update_collaborator "$agent_id" "$collaborator_id" "$new_collaborator_id" "$collaborator_name"
                fi
            else
                log_warning "Collaborator $collaborator_type not found in deployed agents"
            fi
        done
    fi
    
    # Prepare the agent to apply changes
    log_info "Preparing $agent_type agent to apply changes..."
    aws bedrock-agent prepare-agent \
        --region "$AWS_REGION" \
        --agent-id "$agent_id" \
        --output json >/dev/null
    
    log_success "Successfully updated $agent_type agent dependencies!"
}

# Main function
main() {
    local agent_type=$1
    
    if [[ -z "$agent_type" ]]; then
        echo "Usage: $0 <agent-type>"
        echo "Available agent types:"
        jq -r '.deployment_order[]' "$CONFIG_FILE"
        exit 1
    fi
    
    if [[ ! -f "$AGENT_IDS_FILE" ]]; then
        log_error "Agent IDs file not found: $AGENT_IDS_FILE"
        log_error "Please run deploy-all-agents.sh first"
        exit 1
    fi
    
    log_info "Updating dependencies for $agent_type agent..."
    update_agent "$agent_type"
    log_success "Dependency update completed!"
}

# Run main function
main "$@"