#!/bin/bash

# Update Secrets Manager secret with complete .env file content
# This script reads the .env file and updates the Secrets Manager secret with all values

set -e

# Configuration
AWS_REGION="us-east-1"
CDK_DIR="cdk"
ENV_FILE="$CDK_DIR/.env"
ENVIRONMENT="${ENVIRONMENT:-dev}"
SECRET_NAME="oscar-central-env-${ENVIRONMENT}-cdk"

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

# Convert .env file to JSON format for Secrets Manager
convert_env_to_json() {
    local env_file=$1
    local json_output=""
    
    log_info "Converting .env file to JSON format..."
    
    # Read .env file and convert to JSON
    while IFS='=' read -r key value || [[ -n "$key" ]]; do
        # Skip empty lines and comments
        [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue
        
        # Remove leading/trailing whitespace
        key=$(echo "$key" | xargs)
        value=$(echo "$value" | xargs)
        
        # Skip if key is empty
        [[ -z "$key" ]] && continue
        
        # Remove quotes from value if present
        value=$(echo "$value" | sed 's/^["'\'']\|["'\'']$//g')
        
        # Escape special characters for JSON
        value=$(echo "$value" | sed 's/\\/\\\\/g; s/"/\\"/g')
        
        # Add to JSON (with comma if not first entry)
        if [[ -n "$json_output" ]]; then
            json_output="${json_output},"
        fi
        json_output="${json_output}\"${key}\":\"${value}\""
        
        log_info "Added: $key"
    done < "$env_file"
    
    # Wrap in JSON object
    echo "{${json_output}}"
}

# Update Secrets Manager secret
update_secret() {
    local secret_name=$1
    local secret_value=$2
    
    log_info "Updating Secrets Manager secret: $secret_name"
    
    # Update the secret value
    aws secretsmanager update-secret \
        --region "$AWS_REGION" \
        --secret-id "$secret_name" \
        --secret-string "$secret_value" \
        --description "OSCAR central environment variables (updated $(date))" \
        > /dev/null
    
    log_success "Secret updated successfully!"
}

# Create secret if it doesn't exist
create_secret_if_needed() {
    local secret_name=$1
    
    log_info "Checking if secret exists: $secret_name"
    
    if aws secretsmanager describe-secret \
        --region "$AWS_REGION" \
        --secret-id "$secret_name" \
        > /dev/null 2>&1; then
        log_success "Secret exists and is accessible"
        return 0
    else
        log_warning "Secret does not exist: $secret_name"
        log_info "Creating secret: $secret_name"
        
        if aws secretsmanager create-secret \
            --region "$AWS_REGION" \
            --name "$secret_name" \
            --description "OSCAR central environment variables" \
            > /dev/null 2>&1; then
            log_success "Created secret: $secret_name"
            return 0
        else
            log_error "Failed to create secret: $secret_name"
            return 1
        fi
    fi
}

# Main function
main() {
    log_info "🔐 Updating Secrets Manager with complete .env content..."
    log_info "======================================================="
    
    # Check if .env file exists
    if [[ ! -f "$ENV_FILE" ]]; then
        log_error ".env file not found: $ENV_FILE"
        exit 1
    fi
    
    # Create secret if needed
    if ! create_secret_if_needed "$SECRET_NAME"; then
        exit 1
    fi
    
    # Convert .env to JSON
    log_info "Reading .env file: $ENV_FILE"
    local json_content=$(convert_env_to_json "$ENV_FILE")
    
    if [[ -z "$json_content" || "$json_content" == "{}" ]]; then
        log_error "Failed to convert .env file to JSON or file is empty"
        exit 1
    fi
    
    log_info "Generated JSON with $(echo "$json_content" | jq -r 'keys | length') environment variables"
    
    # Update the secret
    update_secret "$SECRET_NAME" "$json_content"
    
    # Verify the update
    log_info "Verifying secret update..."
    local stored_keys=$(aws secretsmanager get-secret-value \
        --region "$AWS_REGION" \
        --secret-id "$SECRET_NAME" \
        --query "SecretString" \
        --output text | jq -r 'keys | length')
    
    log_success "✅ Secret updated successfully with $stored_keys environment variables!"
    log_info "📁 Source file: $ENV_FILE"
    log_info "🔐 Secret name: $SECRET_NAME"
    log_info "🌍 Region: $AWS_REGION"
}

# Run main function
main "$@"