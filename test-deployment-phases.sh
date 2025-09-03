#!/bin/bash

# Test Deployment Phases Script
# Simulates the deployment process to show how placeholders are replaced

set -e

# Configuration
CONFIG_FILE="deployment-config.json"

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

# Simulate Lambda ARN updates
simulate_lambda_updates() {
    log_info "=== PHASE 1: Simulating Lambda ARN Updates ==="
    
    # Create backup copies
    for agent_dir in agent-configs/*/; do
        if [[ -f "$agent_dir/action-group.json" ]]; then
            cp "$agent_dir/action-group.json" "$agent_dir/action-group.json.backup"
        fi
        if [[ -f "$agent_dir/action-groups.json" ]]; then
            cp "$agent_dir/action-groups.json" "$agent_dir/action-groups.json.backup"
        fi
    done
    
    # Simulate Lambda ARN replacements
    local lambda_mappings=(
        "PLACEHOLDER_JENKINS_LAMBDA_ARN:arn:aws:lambda:us-east-1:395380602281:function:oscar-jenkins-agent-cdk"
        "PLACEHOLDER_BUILD_METRICS_LAMBDA_ARN:arn:aws:lambda:us-east-1:395380602281:function:oscar-build-metrics-agent-cdk"
        "PLACEHOLDER_TEST_METRICS_LAMBDA_ARN:arn:aws:lambda:us-east-1:395380602281:function:oscar-test-metrics-agent-cdk"
        "PLACEHOLDER_RELEASE_METRICS_LAMBDA_ARN:arn:aws:lambda:us-east-1:395380602281:function:oscar-release-metrics-agent-cdk"
        "PLACEHOLDER_SUPERVISOR_LAMBDA_ARN:arn:aws:lambda:us-east-1:395380602281:function:oscar-supervisor-agent-cdk"
        "PLACEHOLDER_COMMUNICATION_LAMBDA_ARN:arn:aws:lambda:us-east-1:395380602281:function:oscar-communication-handler-cdk"
    )
    
    for mapping in "${lambda_mappings[@]}"; do
        local placeholder="${mapping%%:*}"
        local arn="${mapping#*:}"
        
        log_info "Replacing $placeholder with $arn"
        
        # Update all action group files
        for action_file in agent-configs/*/action-group.json agent-configs/*/action-groups.json; do
            if [[ -f "$action_file" ]]; then
                if grep -q "$placeholder" "$action_file" 2>/dev/null; then
                    sed -i.tmp "s|$placeholder|$arn|g" "$action_file"
                    rm -f "$action_file.tmp"
                    log_success "Updated $(basename "$(dirname "$action_file")"): $placeholder → $arn"
                fi
            fi
        done
    done
}

# Simulate knowledge base updates
simulate_kb_updates() {
    log_info "=== PHASE 2: Simulating Knowledge Base ID Updates ==="
    
    # Create backup copies
    for kb_file in agent-configs/*/knowledge-base.json; do
        if [[ -f "$kb_file" ]]; then
            cp "$kb_file" "$kb_file.backup"
        fi
    done
    
    local kb_id="NBRUVWHAYY"
    log_info "Replacing PLACEHOLDER_KNOWLEDGE_BASE_ID with $kb_id"
    
    for kb_file in agent-configs/*/knowledge-base.json; do
        if [[ -f "$kb_file" ]]; then
            if grep -q "PLACEHOLDER_KNOWLEDGE_BASE_ID" "$kb_file" 2>/dev/null; then
                sed -i.tmp "s|PLACEHOLDER_KNOWLEDGE_BASE_ID|$kb_id|g" "$kb_file"
                rm -f "$kb_file.tmp"
                log_success "Updated $(basename "$(dirname "$kb_file")"): PLACEHOLDER_KNOWLEDGE_BASE_ID → $kb_id"
            fi
        fi
    done
}

# Simulate collaborator updates
simulate_collaborator_updates() {
    log_info "=== PHASE 3: Simulating Collaborator ID Updates ==="
    
    # Create backup copies
    for collab_file in agent-configs/*/collaborators.json; do
        if [[ -f "$collab_file" ]]; then
            cp "$collab_file" "$collab_file.backup"
        fi
    done
    
    # Simulate agent creation order and ID assignment
    local agent_mappings=(
        "PLACEHOLDER_JENKINS_AGENT_ID:JENKINS123456"
        "PLACEHOLDER_BUILD_METRICS_AGENT_ID:BUILD123456"
        "PLACEHOLDER_TEST_METRICS_AGENT_ID:TEST1234567"
        "PLACEHOLDER_RELEASE_METRICS_AGENT_ID:RELEASE1234"
    )
    
    for mapping in "${agent_mappings[@]}"; do
        local placeholder="${mapping%%:*}"
        local agent_id="${mapping#*:}"
        
        log_info "Simulating agent creation: $placeholder → $agent_id"
        
        # Update collaborator files
        for collab_file in agent-configs/*/collaborators.json; do
            if [[ -f "$collab_file" ]]; then
                if grep -q "$placeholder" "$collab_file" 2>/dev/null; then
                    sed -i.tmp "s|$placeholder|$agent_id|g" "$collab_file"
                    rm -f "$collab_file.tmp"
                    log_success "Updated $(basename "$(dirname "$collab_file")"): $placeholder → $agent_id"
                fi
            fi
        done
    done
}

# Show final configuration
show_final_config() {
    log_info "=== FINAL CONFIGURATION PREVIEW ==="
    
    echo
    echo "Lambda ARNs in action groups:"
    for action_file in agent-configs/*/action-group.json agent-configs/*/action-groups.json; do
        if [[ -f "$action_file" ]]; then
            local agent_type=$(basename "$(dirname "$action_file")")
            local arns=$(jq -r '
                if type == "array" then
                    .[] | .actionGroupExecutor.lambda.lambdaArn
                else
                    .actionGroupExecutor.lambda.lambdaArn
                end
            ' "$action_file" 2>/dev/null | grep -v "null" || echo "")
            
            if [[ -n "$arns" ]]; then
                echo "  $agent_type:"
                while IFS= read -r arn; do
                    echo "    - $arn"
                done <<< "$arns"
            fi
        fi
    done
    
    echo
    echo "Knowledge Base IDs:"
    for kb_file in agent-configs/*/knowledge-base.json; do
        if [[ -f "$kb_file" ]]; then
            local agent_type=$(basename "$(dirname "$kb_file")")
            local kb_id=$(jq -r '.knowledgeBaseId' "$kb_file" 2>/dev/null)
            echo "  $agent_type: $kb_id"
        fi
    done
    
    echo
    echo "Collaborator Agent IDs:"
    for collab_file in agent-configs/*/collaborators.json; do
        if [[ -f "$collab_file" ]]; then
            local agent_type=$(basename "$(dirname "$collab_file")")
            echo "  $agent_type:"
            jq -r '.[] | "    - \(.collaboratorName): \(.agentDescriptor.agentId)"' "$collab_file" 2>/dev/null
        fi
    done
}

# Restore original files
restore_files() {
    log_info "=== Restoring Original Configuration Files ==="
    
    for backup_file in agent-configs/*/*.backup; do
        if [[ -f "$backup_file" ]]; then
            original_file="${backup_file%.backup}"
            mv "$backup_file" "$original_file"
            log_success "Restored $(basename "$original_file")"
        fi
    done
}

# Main function
main() {
    local command=${1:-"test"}
    
    case "$command" in
        "test")
            log_info "Testing deployment phases with placeholder replacement..."
            echo
            
            simulate_lambda_updates
            echo
            
            simulate_kb_updates
            echo
            
            simulate_collaborator_updates
            echo
            
            show_final_config
            echo
            
            read -p "Press Enter to restore original files..."
            restore_files
            
            log_success "Test completed! Original files restored."
            ;;
        
        "show")
            show_final_config
            ;;
        
        *)
            echo "Usage: $0 [test|show]"
            echo ""
            echo "Commands:"
            echo "  test    Run full deployment simulation (default)"
            echo "  show    Show current configuration state"
            exit 1
            ;;
    esac
}

# Run main function
main "$@"