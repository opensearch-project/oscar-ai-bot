#!/bin/bash

# Update Knowledge Base Associations Script
# Updates agents when knowledge bases are created or changed

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

# Check if knowledge base exists
check_knowledge_base_exists() {
    local kb_id=$1
    aws bedrock-agent get-knowledge-base --region "$AWS_REGION" --knowledge-base-id "$kb_id" >/dev/null 2>&1
}

# Update knowledge base association
update_knowledge_base_association() {
    local agent_id=$1
    local kb_id=$2
    local kb_name=$3
    
    log_info "Updating knowledge base association: $kb_name ($kb_id)"
    
    # Check if association already exists
    local existing_associations=$(aws bedrock-agent list-agent-knowledge-bases \
        --region "$AWS_REGION" \
        --agent-id "$agent_id" \
        --agent-version "DRAFT" \
        --output json)
    
    local existing_kb=$(echo "$existing_associations" | jq -r --arg kb_id "$kb_id" \
        '.agentKnowledgeBaseSummaries[] | select(.knowledgeBaseId == $kb_id) | .knowledgeBaseId')
    
    if [[ -n "$existing_kb" ]]; then
        log_info "Knowledge base $kb_name already associated with agent"
        return 0
    fi
    
    # Associate the knowledge base
    aws bedrock-agent associate-agent-knowledge-base \
        --region "$AWS_REGION" \
        --agent-id "$agent_id" \
        --agent-version "DRAFT" \
        --knowledge-base-id "$kb_id" \
        --description "OpenSearch documentation, build commands, guides, release references, best practices, troubleshooting, & feature explanations. Prioritize for static information and how-to questions." \
        --knowledge-base-state "ENABLED"
    
    log_success "Associated knowledge base: $kb_name"
}

# Update agent knowledge bases
update_agent_knowledge_bases() {
    local agent_type=$1
    
    log_info "Updating knowledge bases for $agent_type agent..."
    
    # Get agent ID
    local agent_id=$(get_agent_id "$agent_type")
    if [[ -z "$agent_id" ]]; then
        log_error "Agent $agent_type not found in deployed agents"
        return 1
    fi
    
    log_info "Found $agent_type agent ID: $agent_id"
    
    # Get knowledge base dependencies
    local knowledge_bases=$(jq -r --arg type "$agent_type" '.agents[$type].knowledge_bases[]?' "$CONFIG_FILE")
    
    if [[ -z "$knowledge_bases" ]]; then
        log_info "No knowledge bases configured for $agent_type agent"
        return 0
    fi
    
    for kb_name in $knowledge_bases; do
        local kb_id=$(jq -r --arg name "$kb_name" '.knowledge_bases[$name].id' "$CONFIG_FILE")
        local kb_display_name=$(jq -r --arg name "$kb_name" '.knowledge_bases[$name].name' "$CONFIG_FILE")
        
        if [[ "$kb_id" != "null" ]] && check_knowledge_base_exists "$kb_id"; then
            update_knowledge_base_association "$agent_id" "$kb_id" "$kb_display_name"
        else
            log_warning "Knowledge base $kb_name ($kb_id) not found or not accessible"
        fi
    done
    
    # Prepare the agent to apply changes
    log_info "Preparing $agent_type agent to apply changes..."
    aws bedrock-agent prepare-agent \
        --region "$AWS_REGION" \
        --agent-id "$agent_id" \
        --output json >/dev/null
    
    log_success "Successfully updated knowledge bases for $agent_type agent!"
}

# Update knowledge base ID in configuration
update_knowledge_base_config() {
    local kb_name=$1
    local new_kb_id=$2
    
    log_info "Updating knowledge base ID in configuration: $kb_name -> $new_kb_id"
    
    # Update deployment config
    jq --arg name "$kb_name" --arg id "$new_kb_id" \
       '.knowledge_bases[$name].id = $id' \
       "$CONFIG_FILE" > "${CONFIG_FILE}.tmp" && mv "${CONFIG_FILE}.tmp" "$CONFIG_FILE"
    
    # Update agent configuration files
    for agent_dir in agent-configs/*/; do
        if [[ -f "$agent_dir/knowledge-base.json" ]]; then
            jq --arg id "$new_kb_id" \
               '.knowledgeBaseId = $id' \
               "$agent_dir/knowledge-base.json" > "$agent_dir/knowledge-base.json.tmp" && \
               mv "$agent_dir/knowledge-base.json.tmp" "$agent_dir/knowledge-base.json"
            log_success "Updated knowledge base ID in $(basename "$agent_dir")"
        fi
    done
    
    log_success "Updated knowledge base configuration for $kb_name"
}

# Main function
main() {
    local command=$1
    local param1=$2
    local param2=$3
    
    case "$command" in
        "update-agent")
            if [[ -z "$param1" ]]; then
                echo "Usage: $0 update-agent <agent-type>"
                echo "Available agent types:"
                jq -r '.deployment_order[]' "$CONFIG_FILE"
                exit 1
            fi
            
            if [[ ! -f "$AGENT_IDS_FILE" ]]; then
                log_error "Agent IDs file not found: $AGENT_IDS_FILE"
                log_error "Please run deploy-all-agents.sh first"
                exit 1
            fi
            
            update_agent_knowledge_bases "$param1"
            ;;
        
        "update-config")
            if [[ -z "$param1" ]] || [[ -z "$param2" ]]; then
                echo "Usage: $0 update-config <kb-name> <new-kb-id>"
                echo "Available knowledge bases:"
                jq -r '.knowledge_bases | keys[]' "$CONFIG_FILE"
                exit 1
            fi
            
            update_knowledge_base_config "$param1" "$param2"
            ;;
        
        "update-all")
            if [[ ! -f "$AGENT_IDS_FILE" ]]; then
                log_error "Agent IDs file not found: $AGENT_IDS_FILE"
                log_error "Please run deploy-all-agents.sh first"
                exit 1
            fi
            
            log_info "Updating knowledge bases for all agents..."
            
            # Get agents that use knowledge bases
            local agents_with_kb=$(jq -r '.agents | to_entries[] | select(.value.knowledge_bases | length > 0) | .key' "$CONFIG_FILE")
            
            for agent_type in $agents_with_kb; do
                log_info "=== Updating $agent_type agent ==="
                update_agent_knowledge_bases "$agent_type"
                echo
            done
            
            log_success "Updated knowledge bases for all agents!"
            ;;
        
        *)
            echo "Usage: $0 <command> [parameters]"
            echo ""
            echo "Commands:"
            echo "  update-agent <agent-type>           Update knowledge bases for specific agent"
            echo "  update-config <kb-name> <new-kb-id> Update knowledge base ID in configuration"
            echo "  update-all                          Update knowledge bases for all agents"
            echo ""
            echo "Examples:"
            echo "  $0 update-agent oscar-limited"
            echo "  $0 update-config opensearch-docs NBRUVWHAYY"
            echo "  $0 update-all"
            exit 1
            ;;
    esac
}

# Run main function
main "$@"