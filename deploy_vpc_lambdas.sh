#!/bin/bash
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

# Robust VPC Lambda Deployment Script for OSCAR Metrics Agents
# Deploys Lambda functions within VPC for secure OpenSearch connectivity

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 OSCAR Metrics VPC Lambda Deployment${NC}"
echo "=================================================="

# Load environment variables
load_environment() {
    if [ -f ".env" ]; then
        echo -e "${GREEN}✅ Loading environment from .env file${NC}"
        while IFS= read -r line; do
            [[ $line =~ ^[[:space:]]*# ]] && continue
            [[ -z $line ]] && continue
            export "$line"
        done < .env
        
        # Set defaults
        export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-$AWS_REGION}"
        export OPENSEARCH_REGION="${OPENSEARCH_REGION:-$AWS_REGION}"
        export OPENSEARCH_SERVICE="${OPENSEARCH_SERVICE:-es}"
        export LOG_LEVEL="${LOG_LEVEL:-INFO}"
        export REQUEST_TIMEOUT="${REQUEST_TIMEOUT:-30}"
        export MAX_RESULTS="${MAX_RESULTS:-50}"
        export MOCK_MODE="${MOCK_MODE:-false}"
    else
        echo -e "${RED}❌ .env file not found${NC}"
        exit 1
    fi
}

# Validate environment
validate_environment() {
    echo -e "${YELLOW}🔍 Validating environment...${NC}"
    
    local missing_vars=()
    local required_vars=(
        "AWS_REGION"
        "VPC_ID"
        "SUBNET_IDS"
        "SECURITY_GROUP_ID"
        "OPENSEARCH_HOST"
        "OPENSEARCH_DOMAIN_ARN"
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
    
    # Validate VPC and subnets exist
    echo "   Validating VPC: $VPC_ID"
    if ! aws ec2 describe-vpcs --vpc-ids "$VPC_ID" --region "$AWS_REGION" >/dev/null 2>&1; then
        echo -e "${RED}❌ VPC $VPC_ID not found or not accessible${NC}"
        exit 1
    fi
    
    # Validate subnets
    IFS=',' read -ra SUBNET_ARRAY <<< "$SUBNET_IDS"
    echo "   Validating ${#SUBNET_ARRAY[@]} subnets..."
    for subnet in "${SUBNET_ARRAY[@]}"; do
        if ! aws ec2 describe-subnets --subnet-ids "$subnet" --region "$AWS_REGION" >/dev/null 2>&1; then
            echo -e "${RED}❌ Subnet $subnet not found or not accessible${NC}"
            exit 1
        fi
    done
    
    # Validate security group
    echo "   Validating security group: $SECURITY_GROUP_ID"
    if ! aws ec2 describe-security-groups --group-ids "$SECURITY_GROUP_ID" --region "$AWS_REGION" >/dev/null 2>&1; then
        echo -e "${RED}❌ Security group $SECURITY_GROUP_ID not found or not accessible${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✅ Environment validation passed${NC}"
}

# Show configuration
show_configuration() {
    echo ""
    echo -e "${BLUE}🔧 Deployment Configuration:${NC}"
    echo "   AWS Region: $AWS_REGION"
    echo "   VPC ID: $VPC_ID"
    echo "   Subnets: $SUBNET_IDS"
    echo "   Security Group: $SECURITY_GROUP_ID"
    echo "   OpenSearch Host: $OPENSEARCH_HOST"
    echo "   Mock Mode: $MOCK_MODE"
    echo ""
}

# Create deployment package
create_deployment_package() {
    echo -e "${YELLOW}📦 Creating deployment package...${NC}"
    
    # Clean up any existing package
    rm -rf lambda-package lambda-package.zip
    mkdir lambda-package
    
    # Install dependencies
    echo "   Installing Python dependencies..."
    pip install -r metrics/requirements.txt -t lambda-package/ --quiet --no-warn-script-location
    
    # Copy source code
    echo "   Copying source code..."
    cp metrics/*.py lambda-package/
    
    # Clean up unnecessary files to reduce package size
    find lambda-package -name "*.pyc" -delete 2>/dev/null || true
    find lambda-package -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    find lambda-package -name "*.dist-info" -type d -exec rm -rf {} + 2>/dev/null || true
    find lambda-package -name "tests" -type d -exec rm -rf {} + 2>/dev/null || true
    find lambda-package -name "test" -type d -exec rm -rf {} + 2>/dev/null || true
    
    # Create zip package
    echo "   Creating deployment package..."
    cd lambda-package
    zip -r ../lambda-package.zip . -q
    cd ..
    
    # Clean up temporary directory
    rm -rf lambda-package
    
    local package_size=$(du -h lambda-package.zip | cut -f1)
    echo -e "${GREEN}   ✅ Deployment package created (${package_size})${NC}"
}

# Setup IAM role with proper permissions
setup_iam_role() {
    local role_name="oscar-metrics-lambda-role"
    
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
    
    aws iam attach-role-policy \
        --role-name "$role_name" \
        --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole" \
        --region "$AWS_REGION"
    
    # Create custom policy for OpenSearch access and role assumption
    cat > opensearch-policy.json << EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "es:ESHttpGet",
                "es:ESHttpPost",
                "es:ESHttpPut",
                "es:ESHttpDelete",
                "es:ESHttpHead"
            ],
            "Resource": [
                "$OPENSEARCH_DOMAIN_ARN",
                "$OPENSEARCH_DOMAIN_ARN/*"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "sts:AssumeRole"
            ],
            "Resource": [
                "arn:aws:iam::979020455945:role/OpenSearchOscarAccessRole"
            ]
        }
    ]
}
EOF

    aws iam put-role-policy \
        --role-name "$role_name" \
        --policy-name "OpenSearchVPCAccess" \
        --policy-document file://opensearch-policy.json \
        --region "$AWS_REGION"
    
    # Clean up policy files
    rm -f trust-policy.json opensearch-policy.json
    
    echo -e "${GREEN}   ✅ IAM role created: $ROLE_ARN${NC}"
    
    # Wait for role propagation
    echo "   ⏳ Waiting for IAM role propagation..."
    sleep 15
}

# Create configuration files for Lambda deployment
create_config_files() {
    local agent_type=$1
    
    # Create environment variables JSON (excluding AWS_REGION as it's reserved)
    cat > env-vars.json << EOF
{
    "Variables": {
        "OPENSEARCH_HOST": "$OPENSEARCH_HOST",
        "OPENSEARCH_REGION": "$OPENSEARCH_REGION",
        "OPENSEARCH_SERVICE": "$OPENSEARCH_SERVICE",
        "OPENSEARCH_DOMAIN_ARN": "$OPENSEARCH_DOMAIN_ARN",
        "VPC_ID": "$VPC_ID",
        "SUBNET_IDS": "$SUBNET_IDS",
        "SECURITY_GROUP_ID": "$SECURITY_GROUP_ID",
        "LOG_LEVEL": "$LOG_LEVEL",
        "REQUEST_TIMEOUT": "$REQUEST_TIMEOUT",
        "MAX_RESULTS": "$MAX_RESULTS",
        "MOCK_MODE": "$MOCK_MODE",
        "AGENT_TYPE": "$agent_type",
        "METRICS_ROLE_ARN": "${METRICS_ROLE_ARN:-arn:aws:iam::979020455945:role/OpenSearchOscarAccessRole}"
    }
}
EOF

    # Create VPC configuration JSON with proper subnet array formatting
    local subnet_json=""
    IFS=',' read -ra SUBNET_ARRAY <<< "$SUBNET_IDS"
    for i in "${!SUBNET_ARRAY[@]}"; do
        if [ $i -eq 0 ]; then
            subnet_json="\"${SUBNET_ARRAY[$i]}\""
        else
            subnet_json="$subnet_json, \"${SUBNET_ARRAY[$i]}\""
        fi
    done
    
    cat > vpc-config.json << EOF
{
    "SubnetIds": [$subnet_json],
    "SecurityGroupIds": ["$SECURITY_GROUP_ID"]
}
EOF
}

# Deploy or update a Lambda function
deploy_lambda_function() {
    local function_name=$1
    local agent_type=$2
    
    echo -e "${YELLOW}🚀 Deploying $function_name...${NC}"
    
    # Create configuration files
    create_config_files "$agent_type"
    
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
            --zip-file fileb://lambda-package.zip \
            --region "$AWS_REGION" >/dev/null
        
        # Wait for code update to complete
        aws lambda wait function-updated --function-name "$function_name" --region "$AWS_REGION" 2>/dev/null || true
        
        # Update function configuration
        aws lambda update-function-configuration \
            --function-name "$function_name" \
            --vpc-config file://vpc-config.json \
            --environment file://env-vars.json \
            --timeout 60 \
            --memory-size 256 \
            --region "$AWS_REGION" >/dev/null
        
    else
        echo "   Creating new function..."
        
        aws lambda create-function \
            --function-name "$function_name" \
            --runtime python3.9 \
            --role "$ROLE_ARN" \
            --handler lambda_function.lambda_handler \
            --zip-file fileb://lambda-package.zip \
            --timeout 60 \
            --memory-size 256 \
            --vpc-config file://vpc-config.json \
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
    rm -f env-vars.json vpc-config.json
    
    echo ""
}

# Test Lambda function connectivity
test_lambda_connectivity() {
    local function_name=$1
    
    echo -e "${YELLOW}🧪 Testing $function_name connectivity...${NC}"
    
    # Create test payload
    local test_payload='{"function": "test_connection", "parameters": []}'
    
    # Invoke function and capture result
    if aws lambda invoke \
        --function-name "$function_name" \
        --payload "$test_payload" \
        --region "$AWS_REGION" \
        "test-result-${function_name}.json" >/dev/null 2>&1; then
        
        echo -e "${GREEN}   ✅ $function_name invocation successful${NC}"
        
        # Check if response contains error
        if grep -q '"error"' "test-result-${function_name}.json" 2>/dev/null; then
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
    # Load and validate environment
    load_environment
    validate_environment
    show_configuration
    
    # Create deployment package
    create_deployment_package
    
    # Setup IAM role
    setup_iam_role
    
    # Deploy Lambda functions
    echo -e "${BLUE}🚀 Deploying Lambda Functions${NC}"
    echo "================================"
    
    local lambda_functions=(
        "oscar-test-metrics-agent:test-metrics"
        "oscar-build-metrics-agent:build-metrics"
        "oscar-release-metrics-agent:release-metrics"
        "oscar-deployment-metrics-agent:deployment-metrics"
    )
    
    for func_config in "${lambda_functions[@]}"; do
        IFS=':' read -ra FUNC_PARTS <<< "$func_config"
        local func_name="${FUNC_PARTS[0]}"
        local agent_type="${FUNC_PARTS[1]}"
        
        deploy_lambda_function "$func_name" "$agent_type"
    done
    
    # Test connectivity
    echo -e "${BLUE}🧪 Testing Connectivity${NC}"
    echo "======================="
    
    for func_config in "${lambda_functions[@]}"; do
        IFS=':' read -ra FUNC_PARTS <<< "$func_config"
        local func_name="${FUNC_PARTS[0]}"
        
        test_lambda_connectivity "$func_name"
    done
    
    # Clean up
    rm -f lambda-package.zip env-vars.json vpc-config.json
    
    # Show deployment summary
    echo -e "${GREEN}✅ VPC Lambda Deployment Complete!${NC}"
    echo "=================================="
    echo ""
    echo -e "${BLUE}📋 Deployed Functions:${NC}"
    
    for func_config in "${lambda_functions[@]}"; do
        IFS=':' read -ra FUNC_PARTS <<< "$func_config"
        local func_name="${FUNC_PARTS[0]}"
        
        local arn=$(aws lambda get-function --function-name "$func_name" --query 'Configuration.FunctionArn' --output text --region "$AWS_REGION" 2>/dev/null || echo "Not found")
        echo "   $func_name: $arn"
    done
    
    echo ""
    echo -e "${BLUE}🔗 VPC Configuration:${NC}"
    echo "   VPC ID: $VPC_ID"
    echo "   Subnets: $SUBNET_IDS"
    echo "   Security Group: $SECURITY_GROUP_ID"
    echo "   OpenSearch Host: $OPENSEARCH_HOST"
    
    echo ""
    echo -e "${BLUE}📝 Next Steps:${NC}"
    echo "1. Configure Bedrock agents using the Lambda ARNs above"
    echo "2. Follow MANUAL_AGENT_CONFIGURATION.md for agent setup"
    echo "3. Test end-to-end functionality with Bedrock"
    
    echo ""
    echo -e "${BLUE}🧪 Test Results:${NC}"
    echo "   Check test-result-*.json files for detailed function test results"
    
    echo ""
    echo -e "${BLUE}🗑️  Cleanup:${NC}"
    echo "   If you need to redeploy, run: ./destroy_lambda_functions.sh"
}

# Run main deployment
main