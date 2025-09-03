#!/bin/bash

# Complete OSCAR Deployment Script
# Deploys infrastructure in the correct order and integrates all components

set -e

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

log_info "🚀 Starting Complete OSCAR Deployment"
log_info "====================================="

# Step 1: Deploy CDK Infrastructure Stacks (excluding agents and secrets)
log_info "📦 Step 1: Deploying CDK Infrastructure Stacks"
log_info "This includes: Permissions, Storage, Lambda, API Gateway"
log_info "Note: Secrets Manager will be deployed LAST after all agents are created"

cd cdk

# Load environment variables
if [ -f .env ]; then
    log_info "Loading environment variables from .env file..."
    set -a
    source .env
    set +a
else
    log_error ".env file not found in cdk directory!"
    exit 1
fi

# Set CDK environment variables
export CDK_DEFAULT_ACCOUNT=$AWS_ACCOUNT_ID
export CDK_DEFAULT_REGION=$AWS_DEFAULT_REGION

log_info "Deploying CDK stacks in correct order..."

# Deploy in dependency order (Secrets Manager will be deployed LAST)
log_info "Deploying Permissions stack..."
cdk deploy OscarPermissionsStack --require-approval never

log_info "Deploying Storage stack..."
cdk deploy OscarStorageStack --require-approval never

log_info "Deploying Lambda stack..."
cdk deploy OscarLambdaStack --require-approval never

log_info "Deploying API Gateway stack..."
cdk deploy OscarApiGatewayStack --require-approval never

log_success "✅ CDK Infrastructure stacks deployed successfully!"

cd ..

# Step 2: Update Lambda ARNs in agent configurations
log_info "📝 Step 2: Updating Lambda ARNs in agent configurations"
./update-lambda-arns.sh

log_success "✅ Lambda ARNs updated in agent configurations"

# Step 3: Deploy agents using our proven manual deployment logic
log_info "🤖 Step 3: Deploying Bedrock Agents"
log_info "Using proven manual deployment logic with proper wait times and collaborator handling"

./deploy-all-agents.sh

log_success "✅ All agents deployed successfully with proper collaborator relationships!"

# Step 4: Deploy Secrets Manager with all resource IDs (LAST)
log_info "🔐 Step 4: Deploying Secrets Manager with all resource IDs"
log_info "This is deployed LAST because it needs all agent IDs and resource ARNs"

cd cdk
log_info "Deploying Secrets Manager stack with complete resource inventory..."
cdk deploy OscarSecretsStack --require-approval never

log_success "✅ Secrets Manager deployed with all resource IDs!"

cd ..

# Step 5: Final verification
log_info "🔍 Step 5: Final Integration Verification"

log_info "Verifying deployed resources..."

# Check agents
log_info "Checking deployed agents..."
aws bedrock-agent list-agents --query "agentSummaries[?contains(agentName, 'oscar') || contains(agentName, 'jenkins') || contains(agentName, 'metrics')].{Name:agentName,ID:agentId,Status:agentStatus}" --output table

# Check Lambda functions
log_info "Checking deployed Lambda functions..."
aws lambda list-functions --query "Functions[?contains(FunctionName, 'oscar')].{Name:FunctionName,Runtime:Runtime,State:State}" --output table

log_success "🎉 Complete OSCAR Deployment Finished Successfully!"
log_success "=============================================="

log_info "📋 Deployment Summary:"
log_info "✅ CDK Infrastructure: Permissions, Secrets, Storage, Lambda, API Gateway"
log_info "✅ Bedrock Agents: All agents with proper collaborator relationships"
log_info "✅ Lambda Integration: All action groups connected to Lambda functions"
log_info "✅ Environment Variables: .env file updated with all resource IDs"
log_info "✅ Secrets Manager: All resource IDs stored securely"

log_info "🧪 Next Steps:"
log_info "1. Test individual agents in AWS Bedrock console"
log_info "2. Test supervisor agents with collaborator routing"
log_info "3. Test Jenkins operations and metrics queries"
log_info "4. Verify end-to-end functionality"

log_info "📁 Key Files Updated:"
log_info "- cdk/.env: Contains all deployed resource IDs"
log_info "- deployed-agent-ids.json: Contains agent and alias IDs"
log_info "- Agent configurations: Updated with actual Lambda ARNs"