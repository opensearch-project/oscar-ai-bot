#!/bin/bash

# Deployment Validation Script
# Validates that all components are ready for deployment

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

# Check if Lambda function exists
check_lambda_exists() {
    local function_name=$1
    aws lambda get-function --region "$AWS_REGION" --function-name "$function_name" >/dev/null 2>&1
}

# Check if knowledge base exists
check_knowledge_base_exists() {
    local kb_id=$1
    aws bedrock-agent get-knowledge-base --region "$AWS_REGION" --knowledge-base-id "$kb_id" >/dev/null 2>&1
}

# Check if IAM role exists
check_iam_role_exists() {
    local role_name=$1
    aws iam get-role --role-name "$role_name" >/dev/null 2>&1
}

# Validate configuration files
validate_config_files() {
    log_info "Validating configuration files..."
    
    local errors=0
    
    # Check main config file
    if [[ ! -f "$CONFIG_FILE" ]]; then
        log_error "Main configuration file not found: $CONFIG_FILE"
        ((errors++))
    else
        log_success "Main configuration file found"
    fi
    
    # Check agent configuration directories
    local deployment_order=$(jq -r '.deployment_order[]' "$CONFIG_FILE" 2>/dev/null || echo "")
    
    if [[ -z "$deployment_order" ]]; then
        log_error "Could not read deployment order from $CONFIG_FILE"
        ((errors++))
        return $errors
    fi
    
    for agent_type in $deployment_order; do
        log_info "Checking $agent_type configuration..."
        
        local agent_dir="agent-configs/$agent_type"
        if [[ ! -d "$agent_dir" ]]; then
            log_error "Agent directory not found: $agent_dir"
            ((errors++))
            continue
        fi
        
        # Check required files
        if [[ ! -f "$agent_dir/agent-config.json" ]]; then
            log_error "Agent config not found: $agent_dir/agent-config.json"
            ((errors++))
        fi
        
        # Check action group files
        if [[ ! -f "$agent_dir/action-group.json" ]] && [[ ! -f "$agent_dir/action-groups.json" ]]; then
            log_error "No action group configuration found for $agent_type"
            ((errors++))
        fi
        
        # Validate JSON syntax
        for json_file in "$agent_dir"/*.json; do
            if [[ -f "$json_file" ]]; then
                if ! jq empty "$json_file" 2>/dev/null; then
                    log_error "Invalid JSON syntax in $json_file"
                    ((errors++))
                else
                    log_success "Valid JSON: $(basename "$json_file")"
                fi
            fi
        done
    done
    
    return $errors
}

# Validate Lambda functions
validate_lambda_functions() {
    log_info "Validating Lambda functions..."
    
    local errors=0
    local warnings=0
    
    # Get all Lambda functions from config
    local lambda_functions=$(jq -r '.lambda_functions | keys[]' "$CONFIG_FILE")
    
    for lambda_name in $lambda_functions; do
        if check_lambda_exists "$lambda_name"; then
            log_success "Lambda function exists: $lambda_name"
        else
            log_warning "Lambda function not found: $lambda_name"
            ((warnings++))
        fi
    done
    
    # Check specific agent Lambda mappings
    local deployment_order=$(jq -r '.deployment_order[]' "$CONFIG_FILE")
    
    for agent_type in $deployment_order; do
        local lambda_function=$(jq -r --arg type "$agent_type" '.agents[$type].lambda_function' "$CONFIG_FILE")
        if [[ "$lambda_function" != "null" ]]; then
            if ! check_lambda_exists "$lambda_function"; then
                log_warning "Agent $agent_type references missing Lambda: $lambda_function"
                ((warnings++))
            fi
        fi
        
        # Check communication Lambda for privileged agent
        if [[ "$agent_type" == "oscar-privileged" ]]; then
            local comm_lambda=$(jq -r --arg type "$agent_type" '.agents[$type].communication_lambda' "$CONFIG_FILE")
            if [[ "$comm_lambda" != "null" ]] && ! check_lambda_exists "$comm_lambda"; then
                log_warning "Privileged agent references missing communication Lambda: $comm_lambda"
                ((warnings++))
            fi
        fi
    done
    
    if [[ $warnings -gt 0 ]]; then
        log_warning "Found $warnings Lambda function warnings"
        log_info "Agents can be created but action groups will fail until Lambdas are deployed"
    fi
    
    return $errors
}

# Validate IAM roles
validate_iam_roles() {
    log_info "Validating IAM roles..."
    
    local errors=0
    
    # Extract IAM role from agent configs
    local role_arn=$(jq -r '.agents | to_entries[0].value | .agentResourceRoleArn // empty' "$CONFIG_FILE" 2>/dev/null)
    
    if [[ -z "$role_arn" ]]; then
        # Try to get from agent config file
        local first_agent=$(jq -r '.deployment_order[0]' "$CONFIG_FILE")
        if [[ -f "agent-configs/$first_agent/agent-config.json" ]]; then
            role_arn=$(jq -r '.agentResourceRoleArn' "agent-configs/$first_agent/agent-config.json")
        fi
    fi
    
    if [[ -n "$role_arn" ]] && [[ "$role_arn" != "null" ]]; then
        local role_name=$(echo "$role_arn" | sed 's/.*role\///')
        
        if check_iam_role_exists "$role_name"; then
            log_success "IAM role exists: $role_name"
        else
            log_error "IAM role not found: $role_name"
            log_error "Please create the IAM role before deploying agents"
            ((errors++))
        fi
    else
        log_warning "Could not determine IAM role from configuration"
    fi
    
    return $errors
}

# Validate knowledge bases
validate_knowledge_bases() {
    log_info "Validating knowledge bases..."
    
    local errors=0
    local warnings=0
    
    # Get knowledge bases from config
    local knowledge_bases=$(jq -r '.knowledge_bases | keys[]' "$CONFIG_FILE")
    
    for kb_name in $knowledge_bases; do
        local kb_id=$(jq -r --arg name "$kb_name" '.knowledge_bases[$name].id' "$CONFIG_FILE")
        
        if [[ "$kb_id" != "null" ]]; then
            if check_knowledge_base_exists "$kb_id"; then
                log_success "Knowledge base exists: $kb_name ($kb_id)"
            else
                log_warning "Knowledge base not found: $kb_name ($kb_id)"
                ((warnings++))
            fi
        else
            log_warning "Knowledge base $kb_name has no ID configured"
            ((warnings++))
        fi
    done
    
    if [[ $warnings -gt 0 ]]; then
        log_warning "Found $warnings knowledge base warnings"
        log_info "Agents can be created but knowledge base associations will fail"
    fi
    
    return $errors
}

# Validate collaborator placeholders
validate_collaborator_placeholders() {
    log_info "Validating collaborator configurations..."
    
    local errors=0
    
    # Check for placeholder values in collaborator configs
    for collaborator_file in agent-configs/*/collaborators.json; do
        if [[ -f "$collaborator_file" ]]; then
            local agent_type=$(basename "$(dirname "$collaborator_file")")
            
            # Check for placeholder patterns
            local placeholders=$(jq -r '.[] | select(.agentDescriptor.agentId | startswith("PLACEHOLDER_")) | .agentDescriptor.agentId' "$collaborator_file" 2>/dev/null || echo "")
            
            if [[ -n "$placeholders" ]]; then
                log_success "$agent_type has placeholder collaborator IDs (good for fresh deployment)"
                while IFS= read -r placeholder; do
                    log_info "  - $placeholder"
                done <<< "$placeholders"
            else
                # Check for hardcoded IDs
                local hardcoded=$(jq -r '.[] | select(.agentDescriptor.agentId | test("^[A-Z0-9]{10}$")) | .agentDescriptor.agentId' "$collaborator_file" 2>/dev/null || echo "")
                
                if [[ -n "$hardcoded" ]]; then
                    log_warning "$agent_type has hardcoded collaborator IDs"
                    while IFS= read -r id; do
                        log_warning "  - Hardcoded ID: $id"
                    done <<< "$hardcoded"
                    log_info "  These will be updated during deployment if dependencies exist"
                fi
            fi
        fi
    done
    
    # Check for Lambda ARN placeholders
    log_info "Validating Lambda ARN placeholders..."
    
    for action_file in agent-configs/*/action-group.json agent-configs/*/action-groups.json; do
        if [[ -f "$action_file" ]]; then
            local agent_type=$(basename "$(dirname "$action_file")")
            
            # Check for Lambda ARN placeholders
            local lambda_placeholders=$(jq -r '
                if type == "array" then
                    .[] | select(.actionGroupExecutor.lambda.lambdaArn | startswith("PLACEHOLDER_")) | .actionGroupExecutor.lambda.lambdaArn
                else
                    select(.actionGroupExecutor.lambda.lambdaArn | startswith("PLACEHOLDER_")) | .actionGroupExecutor.lambda.lambdaArn
                end
            ' "$action_file" 2>/dev/null || echo "")
            
            if [[ -n "$lambda_placeholders" ]]; then
                log_success "$agent_type has placeholder Lambda ARNs (good for fresh deployment)"
                while IFS= read -r placeholder; do
                    log_info "  - $placeholder"
                done <<< "$lambda_placeholders"
            fi
        fi
    done
    
    # Check for knowledge base placeholders
    log_info "Validating knowledge base placeholders..."
    
    for kb_file in agent-configs/*/knowledge-base.json; do
        if [[ -f "$kb_file" ]]; then
            local agent_type=$(basename "$(dirname "$kb_file")")
            
            local kb_placeholder=$(jq -r 'select(.knowledgeBaseId == "PLACEHOLDER_KNOWLEDGE_BASE_ID") | .knowledgeBaseId' "$kb_file" 2>/dev/null || echo "")
            
            if [[ -n "$kb_placeholder" ]]; then
                log_success "$agent_type has placeholder knowledge base ID (good for fresh deployment)"
                log_info "  - $kb_placeholder"
            fi
        fi
    done
    
    return $errors
}

# Check deployment readiness
check_deployment_readiness() {
    log_info "Checking deployment readiness..."
    
    local total_errors=0
    local total_warnings=0
    
    # Run all validations
    validate_config_files
    total_errors=$((total_errors + $?))
    
    validate_iam_roles
    total_errors=$((total_errors + $?))
    
    validate_lambda_functions
    # Lambda warnings don't count as errors for deployment readiness
    
    validate_knowledge_bases
    # KB warnings don't count as errors for deployment readiness
    
    validate_collaborator_placeholders
    total_errors=$((total_errors + $?))
    
    echo
    echo "=== DEPLOYMENT READINESS SUMMARY ==="
    
    if [[ $total_errors -eq 0 ]]; then
        log_success "✅ Ready for deployment!"
        log_info "All critical components validated successfully"
        
        if [[ -f "$AGENT_IDS_FILE" ]]; then
            log_info "Existing deployment detected - this will update existing agents"
        else
            log_info "Fresh deployment detected - new agents will be created"
        fi
        
        echo
        log_info "To deploy all agents: ./deploy-all-agents.sh"
        log_info "To deploy specific agent: ./deploy-all-agents.sh (then select agent)"
        
        return 0
    else
        log_error "❌ Not ready for deployment"
        log_error "Found $total_errors critical errors that must be fixed"
        
        echo
        log_info "Common fixes:"
        log_info "1. Create IAM role: oscar-bedrock-agent-execution-role-cdk"
        log_info "2. Deploy Lambda functions using CDK or other method"
        log_info "3. Create knowledge bases if needed"
        log_info "4. Fix JSON syntax errors in configuration files"
        
        return 1
    fi
}

# Main function
main() {
    local command=${1:-"check"}
    
    case "$command" in
        "check"|"validate")
            check_deployment_readiness
            ;;
        "config")
            validate_config_files
            ;;
        "lambda")
            validate_lambda_functions
            ;;
        "iam")
            validate_iam_roles
            ;;
        "kb"|"knowledge-base")
            validate_knowledge_bases
            ;;
        "collaborators")
            validate_collaborator_placeholders
            ;;
        *)
            echo "Usage: $0 [command]"
            echo ""
            echo "Commands:"
            echo "  check, validate    Run full deployment readiness check (default)"
            echo "  config            Validate configuration files only"
            echo "  lambda            Validate Lambda functions only"
            echo "  iam               Validate IAM roles only"
            echo "  kb                Validate knowledge bases only"
            echo "  collaborators     Validate collaborator configurations only"
            echo ""
            echo "Examples:"
            echo "  $0                # Full validation"
            echo "  $0 check          # Full validation"
            echo "  $0 lambda         # Check Lambda functions only"
            exit 1
            ;;
    esac
}

# Run main function
main "$@"