#!/bin/bash
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

# Enhanced OSCAR Supervisor Agent Deployment Script
# Deploys the supervisor agent with knowledge base + metrics coordination

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Enhanced OSCAR Supervisor Agent Deployment${NC}"
echo "=================================================="

# Load environment variables
if [ -f ".env" ]; then
    echo -e "${GREEN}✅ Loading environment from .env file${NC}"
    while IFS= read -r line; do
        [[ $line =~ ^[[:space:]]*# ]] && continue
        [[ -z $line ]] && continue
        export "$line"
    done < .env
else
    echo -e "${RED}❌ .env file not found${NC}"
    exit 1
fi

# Validate required environment variables
validate_environment() {
    echo -e "${YELLOW}🔍 Validating environment...${NC}"
    
    local missing_vars=()
    local required_vars=(
        "AWS_REGION"
        "SLACK_BOT_TOKEN"
        "SLACK_SIGNING_SECRET"
        "OSCAR_BEDROCK_AGENT_ID"
        "OSCAR_BEDROCK_AGENT_ALIAS_ID"
        "SESSIONS_TABLE_NAME"
        "CONTEXT_TABLE_NAME"
    )
    
    for var in "${required_vars[@]}"; do
        if [ -z "${!var}" ]; then
            missing_vars+=("$var")
        fi
    done
    
    if [ ${#missing_vars[@]} -ne 0 ]; then
        echo -e "${RED}❌ Missing required environment variables:${NC}"
        printf '   %s\n' "${missing_vars[@]}"
        echo ""
        echo "Please ensure your .env file contains all required variables."
        exit 1
    fi
    
    echo -e "${GREEN}✅ Environment validation passed${NC}"
}

# Show configuration
show_configuration() {
    echo ""
    echo -e "${BLUE}🔧 Deployment Configuration:${NC}"
    echo "   AWS Region: $AWS_REGION"
    echo "   OSCAR Agent ID: $OSCAR_BEDROCK_AGENT_ID"
    echo "   OSCAR Agent Alias: $OSCAR_BEDROCK_AGENT_ALIAS_ID"
    echo "   Sessions Table: $SESSIONS_TABLE_NAME"
    echo "   Context Table: $CONTEXT_TABLE_NAME"
    echo "   Enable DM: ${ENABLE_DM:-false}"
    echo ""
}

# Create deployment package
create_deployment_package() {
    echo -e "${YELLOW}📦 Creating deployment package...${NC}"
    
    # Clean up any existing package
    rm -rf supervisor-package supervisor-package.zip
    mkdir supervisor-package
    
    # Install dependencies
    echo "   Installing Python dependencies..."
    pip install -r oscar-agent/requirements.txt -t supervisor-package/ --quiet --no-warn-script-location
    
    # Copy source code
    echo "   Copying source code..."
    cp oscar-agent/*.py supervisor-package/
    
    # Clean up unnecessary files to reduce package size
    find supervisor-package -name "*.pyc" -delete 2>/dev/null || true
    find supervisor-package -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    find supervisor-package -name "*.dist-info" -type d -exec rm -rf {} + 2>/dev/null || true
    find supervisor-package -name "tests" -type d -exec rm -rf {} + 2>/dev/null || true
    find supervisor-package -name "test" -type d -exec rm -rf {} + 2>/dev/null || true
    
    # Create zip package
    echo "   Creating deployment package..."
    cd supervisor-package
    zip -r ../supervisor-package.zip . -q
    cd ..
    
    # Clean up temporary directory
    rm -rf supervisor-package
    
    local package_size=$(du -h supervisor-package.zip | cut -f1)
    echo -e "${GREEN}   ✅ Deployment package created (${package_size})${NC}"
}

# Setup IAM role
setup_iam_role() {
    local role_name="oscar-supervisor-lambda-role"
    
    echo -e "${YELLOW}🔑 Setting up IAM role...${NC}"
    
    # Check if role exists
    if aws iam get-role --role-name "$role_name" --region "$AWS_REGION" >/dev/null 2>&1; then
        ROLE_ARN=$(aws iam get-role --role-name "$role_name" --query 'Role.Arn' --output text --region "$AWS_REGION")
        echo "   Using existing IAM role: $ROLE_ARN"
        return
    fi
    
    echo "   Creating new IAM role: $role_name"
    
    # Create trust policy for Lambda
    cat > trust-policy.json << 'EOF'
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Service": "lambda.amazonaws.com"
            },
            "Action": "sts:AssumeRole"
        }
    ]
}
EOF

    # Create IAM role
    ROLE_ARN=$(aws iam create-role \
        --role-name "$role_name" \
        --assume-role-policy-document file://trust-policy.json \
        --query 'Role.Arn' \
        --output text \
        --region "$AWS_REGION")
    
    # Attach AWS managed policies for Lambda execution
    aws iam attach-role-policy \
        --role-name "$role_name" \
        --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole" \
        --region "$AWS_REGION"
    
    # Create custom policy for OSCAR supervisor functionality
    cat > oscar-supervisor-policy.json << EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeAgent",
                "bedrock:GetAgent",
                "bedrock:GetKnowledgeBase",
                "bedrock:Retrieve",
                "bedrock:RetrieveAndGenerate"
            ],
            "Resource": [
                "arn:aws:bedrock:$AWS_REGION:*:agent/$OSCAR_BEDROCK_AGENT_ID",
                "arn:aws:bedrock:$AWS_REGION:*:agent-alias/$OSCAR_BEDROCK_AGENT_ID/$OSCAR_BEDROCK_AGENT_ALIAS_ID",
                "arn:aws:bedrock:$AWS_REGION:*:knowledge-base/*"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "dynamodb:GetItem",
                "dynamodb:PutItem",
                "dynamodb:UpdateItem",
                "dynamodb:DeleteItem",
                "dynamodb:Query",
                "dynamodb:Scan"
            ],
            "Resource": [
                "arn:aws:dynamodb:$AWS_REGION:*:table/$SESSIONS_TABLE_NAME",
                "arn:aws:dynamodb:$AWS_REGION:*:table/$CONTEXT_TABLE_NAME"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "lambda:InvokeFunction"
            ],
            "Resource": [
                "arn:aws:lambda:$AWS_REGION:*:function:oscar-*-metrics-agent",
                "arn:aws:lambda:$AWS_REGION:*:function:oscar-supervisor-agent"
            ]
        }
    ]
}
EOF

    aws iam put-role-policy \
        --role-name "$role_name" \
        --policy-name "OSCARSupervisorAccess" \
        --policy-document file://oscar-supervisor-policy.json \
        --region "$AWS_REGION"
    
    # Clean up policy files
    rm -f trust-policy.json oscar-supervisor-policy.json
    
    echo -e "${GREEN}   ✅ IAM role created: $ROLE_ARN${NC}"
    
    # Wait for role propagation
    echo "   ⏳ Waiting for IAM role propagation..."
    sleep 15
}

# Deploy supervisor Lambda function
deploy_supervisor_function() {
    local function_name="oscar-supervisor-agent"
    
    echo -e "${YELLOW}🚀 Deploying $function_name...${NC}"
    
    # Create environment variables JSON
    cat > env-vars.json << EOF
{
    "Variables": {
        "OSCAR_BEDROCK_AGENT_ID": "$OSCAR_BEDROCK_AGENT_ID",
        "OSCAR_BEDROCK_AGENT_ALIAS_ID": "$OSCAR_BEDROCK_AGENT_ALIAS_ID",
        "SESSIONS_TABLE_NAME": "$SESSIONS_TABLE_NAME",
        "CONTEXT_TABLE_NAME": "$CONTEXT_TABLE_NAME",
        "SLACK_BOT_TOKEN": "$SLACK_BOT_TOKEN",
        "SLACK_SIGNING_SECRET": "$SLACK_SIGNING_SECRET",
        "DEDUP_TTL": "${DEDUP_TTL:-300}",
        "SESSION_TTL": "${SESSION_TTL:-3600}",
        "CONTEXT_TTL": "${CONTEXT_TTL:-604800}",
        "MAX_CONTEXT_LENGTH": "${MAX_CONTEXT_LENGTH:-3000}",
        "CONTEXT_SUMMARY_LENGTH": "${CONTEXT_SUMMARY_LENGTH:-500}",
        "ENABLE_DM": "${ENABLE_DM:-false}",
        "AGENT_TIMEOUT": "${AGENT_TIMEOUT:-60}",
        "AGENT_MAX_RETRIES": "${AGENT_MAX_RETRIES:-2}"
    }
}
EOF
    
    # Check if function exists
    local function_exists=false
    if aws lambda get-function --function-name "$function_name" --region "$AWS_REGION" >/dev/null 2>&1; then
        function_exists=true
    fi
    
    if [ "$function_exists" = true ]; then
        echo "   Updating existing function..."
        
        # Wait for any pending updates to complete
        echo "   Waiting for function to be ready..."
        aws lambda wait function-updated --function-name "$function_name" --region "$AWS_REGION" 2>/dev/null || true
        
        # Update function code first
        aws lambda update-function-code \
            --function-name "$function_name" \
            --zip-file fileb://supervisor-package.zip \
            --region "$AWS_REGION" >/dev/null
        
        # Wait for code update to complete
        aws lambda wait function-updated --function-name "$function_name" --region "$AWS_REGION" 2>/dev/null || true
        
        # Update function configuration
        aws lambda update-function-configuration \
            --function-name "$function_name" \
            --environment file://env-vars.json \
            --timeout 60 \
            --memory-size 512 \
            --region "$AWS_REGION" >/dev/null
        
    else
        echo "   Creating new function..."
        
        aws lambda create-function \
            --function-name "$function_name" \
            --runtime python3.9 \
            --role "$ROLE_ARN" \
            --handler app.lambda_handler \
            --zip-file fileb://supervisor-package.zip \
            --timeout 60 \
            --memory-size 512 \
            --environment file://env-vars.json \
            --region "$AWS_REGION" >/dev/null
    fi
    
    # Wait for final update to complete
    aws lambda wait function-updated --function-name "$function_name" --region "$AWS_REGION" 2>/dev/null || true
    
    # Get function ARN
    local function_arn
    function_arn=$(aws lambda get-function --function-name "$function_name" --query 'Configuration.FunctionArn' --output text --region "$AWS_REGION")
    
    echo -e "${GREEN}   ✅ $function_name deployed successfully${NC}"
    echo "   ARN: $function_arn"
    
    # Clean up config files
    rm -f env-vars.json
    
    # Store ARN for summary
    SUPERVISOR_FUNCTION_ARN="$function_arn"
    
    echo ""
}

# Test supervisor function
test_supervisor_function() {
    local function_name="oscar-supervisor-agent"
    
    echo -e "${YELLOW}🧪 Testing $function_name...${NC}"
    
    # Create test payload
    local test_payload='{"test": "supervisor-connectivity"}'
    
    # Invoke function and capture result
    if aws lambda invoke \
        --function-name "$function_name" \
        --payload "$test_payload" \
        --region "$AWS_REGION" \
        "test-result-supervisor.json" >/dev/null 2>&1; then
        
        echo -e "${GREEN}   ✅ $function_name invocation successful${NC}"
        
        # Check if response contains error
        if grep -q '"error"' "test-result-supervisor.json" 2>/dev/null; then
            echo -e "${YELLOW}   ⚠️  Function returned an error (check logs for details)${NC}"
        else
            echo -e "${GREEN}   ✅ Function executed without errors${NC}"
        fi
    else
        echo -e "${RED}   ❌ $function_name invocation failed${NC}"
    fi
    
    echo ""
}

# Main deployment process
main() {
    # Validate and show configuration
    validate_environment
    show_configuration
    
    # Create deployment package
    create_deployment_package
    
    # Setup IAM role
    setup_iam_role
    
    # Deploy supervisor function
    deploy_supervisor_function
    
    # Test function
    test_supervisor_function
    
    # Clean up
    rm -f supervisor-package.zip env-vars.json
    
    # Show deployment summary
    echo -e "${GREEN}✅ Enhanced OSCAR Supervisor Deployment Complete!${NC}"
    echo "=================================================="
    echo ""
    echo -e "${BLUE}📋 Deployed Function:${NC}"
    echo "   oscar-supervisor-agent: $SUPERVISOR_FUNCTION_ARN"
    
    echo ""
    echo -e "${BLUE}🔗 Configuration:${NC}"
    echo "   OSCAR Agent ID: $OSCAR_BEDROCK_AGENT_ID"
    echo "   OSCAR Agent Alias: $OSCAR_BEDROCK_AGENT_ALIAS_ID"
    echo "   Sessions Table: $SESSIONS_TABLE_NAME"
    echo "   Context Table: $CONTEXT_TABLE_NAME"
    
    echo ""
    echo -e "${BLUE}📝 Next Steps:${NC}"
    echo "1. Configure your OSCAR Bedrock agent with this Lambda ARN"
    echo "2. Set up API Gateway for Slack webhook integration"
    echo "3. Configure Slack app with the API Gateway endpoint"
    echo "4. Test end-to-end functionality"
    
    echo ""
    echo -e "${BLUE}🧪 Test Results:${NC}"
    echo "   Check test-result-supervisor.json for detailed function test results"
    
    echo ""
    echo -e "${BLUE}📚 Documentation:${NC}"
    echo "   See MANUAL_AGENT_CONFIGURATION.md for Bedrock agent setup"
}

# Run main deployment
main