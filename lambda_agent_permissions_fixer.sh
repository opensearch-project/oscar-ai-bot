#!/bin/bash

# Lambda Agent Permissions Fixer
# This script adds resource-based policies to Lambda functions allowing their respective Bedrock agents to invoke them

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}[INFO] 🔐 Fixing Lambda function permissions for Bedrock agent invocation${NC}"
echo -e "${BLUE}[INFO] ================================================================${NC}"

# Load environment variables from .env file
if [ -f "cdk/.env" ]; then
    echo -e "${BLUE}[INFO] Loading environment variables from cdk/.env${NC}"
    # Use a safer method to load environment variables, avoiding complex JSON values
    while IFS='=' read -r key value; do
        # Skip comments and empty lines
        [[ $key =~ ^#.*$ ]] && continue
        [[ -z $key ]] && continue
        # Only export simple key=value pairs (avoid complex JSON)
        if [[ $value != *"{"* && $value != *"}"* ]]; then
            export "$key=$value"
        fi
    done < cdk/.env
else
    echo -e "${RED}[ERROR] cdk/.env file not found!${NC}"
    exit 1
fi

# Function to add resource-based policy to Lambda function
add_lambda_permission() {
    local function_name=$1
    local agent_id=$2
    local agent_name=$3
    
    echo -e "${BLUE}[INFO] Adding permission for ${agent_name} agent (${agent_id}) to invoke ${function_name}${NC}"
    
    # Generate a unique statement ID
    local statement_id="bedrock-v2-${agent_id}-$(date +%s)"
    
    # Add the permission
    aws lambda add-permission \
        --function-name "${function_name}" \
        --statement-id "${statement_id}" \
        --action "lambda:InvokeFunction" \
        --principal "bedrock.amazonaws.com" \
        --source-arn "arn:aws:bedrock:${AWS_REGION}:${AWS_ACCOUNT_ID}:agent/${agent_id}" \
        --output text > /dev/null 2>&1
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}[SUCCESS] ✅ Permission added for ${function_name}${NC}"
    else
        # Check if permission already exists
        aws lambda get-policy --function-name "${function_name}" --query 'Policy' --output text 2>/dev/null | grep -q "${agent_id}"
        if [ $? -eq 0 ]; then
            echo -e "${YELLOW}[INFO] ⚠️  Permission already exists for ${function_name}${NC}"
        else
            echo -e "${RED}[ERROR] ❌ Failed to add permission for ${function_name}${NC}"
            return 1
        fi
    fi
}

# Function to remove existing permissions for an agent (cleanup)
remove_existing_permissions() {
    local function_name=$1
    local agent_id=$2
    
    echo -e "${BLUE}[INFO] Checking for existing permissions for agent ${agent_id} on ${function_name}${NC}"
    
    # Get current policy and extract statement IDs that match this agent
    local policy=$(aws lambda get-policy --function-name "${function_name}" --query 'Policy' --output text 2>/dev/null || echo "")
    
    if [ -n "$policy" ]; then
        # Extract statement IDs that contain this agent ID
        local statement_ids=$(echo "$policy" | jq -r --arg agent_id "$agent_id" '.Statement[] | select(.Condition.ArnLike."AWS:SourceArn" | contains($agent_id)) | .Sid' 2>/dev/null || echo "")
        
        if [ -n "$statement_ids" ]; then
            echo "$statement_ids" | while read -r sid; do
                if [ -n "$sid" ]; then
                    echo -e "${YELLOW}[INFO] Removing existing permission: ${sid}${NC}"
                    aws lambda remove-permission --function-name "${function_name}" --statement-id "${sid}" > /dev/null 2>&1 || true
                fi
            done
        fi
    fi
}

echo -e "${BLUE}[INFO] Processing Lambda function permissions...${NC}"

# Supervisor Agent Lambda (Main)
if [ -n "$MAIN_LAMBDA_ARN" ] && [ -n "$OSCAR_LIMITED_BEDROCK_AGENT_ID" ]; then
    FUNCTION_NAME=$(echo "$MAIN_LAMBDA_ARN" | awk -F':' '{print $NF}')
    remove_existing_permissions "$FUNCTION_NAME" "$OSCAR_LIMITED_BEDROCK_AGENT_ID"
    add_lambda_permission "$FUNCTION_NAME" "$OSCAR_LIMITED_BEDROCK_AGENT_ID" "OSCAR Limited"
fi

if [ -n "$MAIN_LAMBDA_ARN" ] && [ -n "$OSCAR_PRIVILEGED_BEDROCK_AGENT_ID" ]; then
    FUNCTION_NAME=$(echo "$MAIN_LAMBDA_ARN" | awk -F':' '{print $NF}')
    remove_existing_permissions "$FUNCTION_NAME" "$OSCAR_PRIVILEGED_BEDROCK_AGENT_ID"
    add_lambda_permission "$FUNCTION_NAME" "$OSCAR_PRIVILEGED_BEDROCK_AGENT_ID" "OSCAR Privileged"
fi

# Jenkins Agent Lambda
if [ -n "$JENKINS_LAMBDA_ARN" ] && [ -n "$JENKINS_AGENT_ID" ]; then
    FUNCTION_NAME=$(echo "$JENKINS_LAMBDA_ARN" | awk -F':' '{print $NF}')
    remove_existing_permissions "$FUNCTION_NAME" "$JENKINS_AGENT_ID"
    add_lambda_permission "$FUNCTION_NAME" "$JENKINS_AGENT_ID" "Jenkins"
fi

# Build Metrics Agent Lambda
if [ -n "$BUILD_METRICS_LAMBDA_ARN" ] && [ -n "$BUILD_METRICS_AGENT_ID" ]; then
    FUNCTION_NAME=$(echo "$BUILD_METRICS_LAMBDA_ARN" | awk -F':' '{print $NF}')
    remove_existing_permissions "$FUNCTION_NAME" "$BUILD_METRICS_AGENT_ID"
    add_lambda_permission "$FUNCTION_NAME" "$BUILD_METRICS_AGENT_ID" "Build Metrics"
fi

# Test Metrics Agent Lambda
if [ -n "$TEST_METRICS_LAMBDA_ARN" ] && [ -n "$TEST_METRICS_AGENT_ID" ]; then
    FUNCTION_NAME=$(echo "$TEST_METRICS_LAMBDA_ARN" | awk -F':' '{print $NF}')
    remove_existing_permissions "$FUNCTION_NAME" "$TEST_METRICS_AGENT_ID"
    add_lambda_permission "$FUNCTION_NAME" "$TEST_METRICS_AGENT_ID" "Test Metrics"
fi

# Release Metrics Agent Lambda
if [ -n "$RELEASE_METRICS_LAMBDA_ARN" ] && [ -n "$RELEASE_METRICS_AGENT_ID" ]; then
    FUNCTION_NAME=$(echo "$RELEASE_METRICS_LAMBDA_ARN" | awk -F':' '{print $NF}')
    remove_existing_permissions "$FUNCTION_NAME" "$RELEASE_METRICS_AGENT_ID"
    add_lambda_permission "$FUNCTION_NAME" "$RELEASE_METRICS_AGENT_ID" "Release Metrics"
fi

# CDK Lambda Functions (for CDK deployment)
echo -e "${BLUE}[INFO] 🔧 Processing CDK Lambda function permissions...${NC}"

# CDK Supervisor Agent Lambda
CDK_SUPERVISOR_FUNCTION="oscar-supervisor-agent-cdk"
if aws lambda get-function --function-name "$CDK_SUPERVISOR_FUNCTION" >/dev/null 2>&1; then
    echo -e "${BLUE}[INFO] Processing CDK Supervisor Agent Lambda...${NC}"
    if [ -n "$OSCAR_LIMITED_BEDROCK_AGENT_ID" ]; then
        remove_existing_permissions "$CDK_SUPERVISOR_FUNCTION" "$OSCAR_LIMITED_BEDROCK_AGENT_ID"
        add_lambda_permission "$CDK_SUPERVISOR_FUNCTION" "$OSCAR_LIMITED_BEDROCK_AGENT_ID" "OSCAR Limited"
    fi
    if [ -n "$OSCAR_PRIVILEGED_BEDROCK_AGENT_ID" ]; then
        remove_existing_permissions "$CDK_SUPERVISOR_FUNCTION" "$OSCAR_PRIVILEGED_BEDROCK_AGENT_ID"
        add_lambda_permission "$CDK_SUPERVISOR_FUNCTION" "$OSCAR_PRIVILEGED_BEDROCK_AGENT_ID" "OSCAR Privileged"
    fi
fi

# CDK Communication Handler Lambda
CDK_COMM_HANDLER_FUNCTION="oscar-communication-handler-cdk"
if aws lambda get-function --function-name "$CDK_COMM_HANDLER_FUNCTION" >/dev/null 2>&1; then
    echo -e "${BLUE}[INFO] Processing CDK Communication Handler Lambda...${NC}"
    if [ -n "$OSCAR_LIMITED_BEDROCK_AGENT_ID" ]; then
        remove_existing_permissions "$CDK_COMM_HANDLER_FUNCTION" "$OSCAR_LIMITED_BEDROCK_AGENT_ID"
        add_lambda_permission "$CDK_COMM_HANDLER_FUNCTION" "$OSCAR_LIMITED_BEDROCK_AGENT_ID" "OSCAR Limited"
    fi
    if [ -n "$OSCAR_PRIVILEGED_BEDROCK_AGENT_ID" ]; then
        remove_existing_permissions "$CDK_COMM_HANDLER_FUNCTION" "$OSCAR_PRIVILEGED_BEDROCK_AGENT_ID"
        add_lambda_permission "$CDK_COMM_HANDLER_FUNCTION" "$OSCAR_PRIVILEGED_BEDROCK_AGENT_ID" "OSCAR Privileged"
    fi
fi

# CDK Metrics Agent Lambdas
for cdk_metrics_function in "oscar-test-metrics-agent-cdk" "oscar-build-metrics-agent-cdk" "oscar-release-metrics-agent-cdk"; do
    if aws lambda get-function --function-name "$cdk_metrics_function" >/dev/null 2>&1; then
        echo -e "${BLUE}[INFO] Processing CDK Metrics Lambda: $cdk_metrics_function${NC}"
        if [ -n "$OSCAR_LIMITED_BEDROCK_AGENT_ID" ]; then
            remove_existing_permissions "$cdk_metrics_function" "$OSCAR_LIMITED_BEDROCK_AGENT_ID"
            add_lambda_permission "$cdk_metrics_function" "$OSCAR_LIMITED_BEDROCK_AGENT_ID" "OSCAR Limited"
        fi
        if [ -n "$OSCAR_PRIVILEGED_BEDROCK_AGENT_ID" ]; then
            remove_existing_permissions "$cdk_metrics_function" "$OSCAR_PRIVILEGED_BEDROCK_AGENT_ID"
            add_lambda_permission "$cdk_metrics_function" "$OSCAR_PRIVILEGED_BEDROCK_AGENT_ID" "OSCAR Privileged"
        fi
    fi
done

# CDK Jenkins Agent Lambda
CDK_JENKINS_FUNCTION="oscar-jenkins-agent-cdk"
if aws lambda get-function --function-name "$CDK_JENKINS_FUNCTION" >/dev/null 2>&1; then
    echo -e "${BLUE}[INFO] Processing CDK Jenkins Agent Lambda...${NC}"
    if [ -n "$OSCAR_LIMITED_BEDROCK_AGENT_ID" ]; then
        remove_existing_permissions "$CDK_JENKINS_FUNCTION" "$OSCAR_LIMITED_BEDROCK_AGENT_ID"
        add_lambda_permission "$CDK_JENKINS_FUNCTION" "$OSCAR_LIMITED_BEDROCK_AGENT_ID" "OSCAR Limited"
    fi
    if [ -n "$OSCAR_PRIVILEGED_BEDROCK_AGENT_ID" ]; then
        remove_existing_permissions "$CDK_JENKINS_FUNCTION" "$OSCAR_PRIVILEGED_BEDROCK_AGENT_ID"
        add_lambda_permission "$CDK_JENKINS_FUNCTION" "$OSCAR_PRIVILEGED_BEDROCK_AGENT_ID" "OSCAR Privileged"
    fi
fi

echo -e "${GREEN}[SUCCESS] ✅ Lambda function permissions have been updated!${NC}"
echo -e "${BLUE}[INFO] 📋 Summary:${NC}"
echo -e "${BLUE}[INFO] - Main Lambda: Accessible by OSCAR Limited & Privileged agents${NC}"
echo -e "${BLUE}[INFO] - Jenkins Lambda: Accessible by Jenkins agent${NC}"
echo -e "${BLUE}[INFO] - Build Metrics Lambda: Accessible by Build Metrics agent${NC}"
echo -e "${BLUE}[INFO] - Test Metrics Lambda: Accessible by Test Metrics agent${NC}"
echo -e "${BLUE}[INFO] - Release Metrics Lambda: Accessible by Release Metrics agent${NC}"
echo -e "${BLUE}[INFO] - CDK Supervisor Lambda: Accessible by both OSCAR agents${NC}"
echo -e "${BLUE}[INFO] - CDK Communication Handler: Accessible by both OSCAR agents${NC}"
echo -e "${BLUE}[INFO] - CDK Metrics Lambdas: Accessible by both OSCAR agents${NC}"
echo -e "${BLUE}[INFO] - CDK Jenkins Lambda: Accessible by both OSCAR agents${NC}"
echo -e "${BLUE}[INFO] 🎯 All Bedrock agents can now invoke their respective Lambda functions!${NC}"