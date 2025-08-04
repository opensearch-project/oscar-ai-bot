#!/bin/bash
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0
#
# The OpenSearch Contributors require contributions made to
# this file be licensed under the Apache-2.0 license or a
# compatible open source license.

# OSCAR Agent Deployment Script
# 
# This script provides a complete deployment pipeline for the OSCAR agent
# implementation, including dependency management, testing, and CDK deployment.
#
# Usage: ./deploy_oscar_agent.sh
# Prerequisites: AWS credentials configured, CDK installed

set -e

# Color codes for output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

log_info "Starting OSCAR Agent deployment..."

# Load environment variables from .env file
load_environment() {
    if [ -f ".env" ]; then
        log_info "Loading environment variables from .env file..."
        export OSCAR_BEDROCK_AGENT_ID=$(grep "^OSCAR_BEDROCK_AGENT_ID=" .env | cut -d '=' -f2)
        export OSCAR_BEDROCK_AGENT_ALIAS_ID=$(grep "^OSCAR_BEDROCK_AGENT_ALIAS_ID=" .env | cut -d '=' -f2)
        export AWS_REGION=$(grep "^AWS_REGION=" .env | cut -d '=' -f2)
        export AWS_ACCOUNT_ID=$(grep "^AWS_ACCOUNT_ID=" .env | cut -d '=' -f2)
        export SLACK_BOT_TOKEN=$(grep "^SLACK_BOT_TOKEN=" .env | cut -d '=' -f2)
        export SLACK_SIGNING_SECRET=$(grep "^SLACK_SIGNING_SECRET=" .env | cut -d '=' -f2)
    else
        log_error ".env file not found"
        exit 1
    fi
}

load_environment

# Validate required environment variables
validate_environment() {
    local missing_vars=()
    
    [ -z "$OSCAR_BEDROCK_AGENT_ID" ] && missing_vars+=("OSCAR_BEDROCK_AGENT_ID")
    [ -z "$OSCAR_BEDROCK_AGENT_ALIAS_ID" ] && missing_vars+=("OSCAR_BEDROCK_AGENT_ALIAS_ID")
    [ -z "$AWS_REGION" ] && missing_vars+=("AWS_REGION")
    [ -z "$AWS_ACCOUNT_ID" ] && missing_vars+=("AWS_ACCOUNT_ID")
    [ -z "$SLACK_BOT_TOKEN" ] && missing_vars+=("SLACK_BOT_TOKEN")
    [ -z "$SLACK_SIGNING_SECRET" ] && missing_vars+=("SLACK_SIGNING_SECRET")
    
    if [ ${#missing_vars[@]} -ne 0 ]; then
        log_error "Missing required environment variables:"
        for var in "${missing_vars[@]}"; do
            log_error "  - $var"
        done
        exit 1
    fi
    
    log_success "Environment validation passed"
    log_info "Agent configuration:"
    log_info "  Agent ID: $OSCAR_BEDROCK_AGENT_ID"
    log_info "  Agent Alias ID: $OSCAR_BEDROCK_AGENT_ALIAS_ID"
    log_info "  Region: $AWS_REGION"
    log_info "  Account: $AWS_ACCOUNT_ID"
}

validate_environment

# Create deployment package with dependencies
create_deployment_package() {
    log_info "Creating deployment package with dependencies..."
    ./build_deployment.sh
    log_success "Deployment package ready"
}

create_deployment_package

# Deploy using CDK
deploy_cdk_stack() {
    log_info "Deploying CDK stack..."
    cd cdk
    
    # Setup CDK environment
    if [ ! -d ".venv" ]; then
        log_info "Installing CDK dependencies..."
        python -m venv .venv
        source .venv/bin/activate
        pip install -r requirements.txt --quiet
    else
        source .venv/bin/activate
    fi
    
    # Set CDK environment variables
    export CDK_DEFAULT_REGION=$AWS_REGION
    export CDK_DEFAULT_ACCOUNT=$AWS_ACCOUNT_ID
    
    log_info "CDK Configuration:"
    log_info "  Account: $CDK_DEFAULT_ACCOUNT"
    log_info "  Region: $CDK_DEFAULT_REGION"
    
    # Bootstrap CDK environment
    log_info "Bootstrapping CDK environment..."
    if ! cdk bootstrap --quiet; then
        log_error "CDK bootstrap failed"
        exit 1
    fi
    log_success "CDK bootstrap completed"
    
    # Deploy the stack
    log_info "Deploying OSCAR Agent stack..."
    if cdk deploy --require-approval never --quiet; then
        log_success "OSCAR Agent deployment completed successfully!"
        
        echo ""
        log_info "📋 Deployment Summary:"
        log_info "  Agent ID: $OSCAR_BEDROCK_AGENT_ID"
        log_info "  Agent Alias: $OSCAR_BEDROCK_AGENT_ALIAS_ID"
        log_info "  Region: $AWS_REGION"
        log_info "  Account: $AWS_ACCOUNT_ID"
        echo ""
        log_info "🔗 Next steps:"
        log_info "1. Test the Slack bot by mentioning it in a channel"
        log_info "2. Check CloudWatch logs if needed"
        log_info "3. Monitor agent performance in Bedrock console"
        echo ""
        log_success "🎉 Your OSCAR agent is ready to use!"
    else
        log_error "Deployment failed"
        log_error "Check the error messages above and verify:"
        log_error "1. AWS credentials are configured correctly"
        log_error "2. You have necessary permissions for CDK deployment"
        log_error "3. Agent ID and alias are correct"
        log_error "4. Agent is in 'Prepared' or 'Published' state"
        exit 1
    fi
    
    cd ..
}

deploy_cdk_stack