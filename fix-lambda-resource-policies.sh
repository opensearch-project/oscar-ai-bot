#!/bin/bash

# Fix Lambda Resource-Based Policies for Bedrock Agent Invocation
# This script adds resource-based policies to Lambda functions allowing Bedrock agents to invoke them

set -e

echo "[INFO] 🔐 Adding resource-based policies to Lambda functions for Bedrock agent invocation..."
echo "[INFO] ================================================================================"

# Configuration
PRIVILEGED_AGENT_ID="MMJVHNFRAQ"
LIMITED_AGENT_ID="TBB6FSCSJ2"
ACCOUNT_ID="395380602281"
REGION="us-east-1"

echo "[INFO] Privileged Agent: $PRIVILEGED_AGENT_ID"
echo "[INFO] Limited Agent: $LIMITED_AGENT_ID"

# Function to add resource-based policy to Lambda function
add_lambda_permission() {
    local function_name=$1
    local agent_id=$2
    local agent_name=$3
    
    echo "[INFO] Adding permission for ${agent_name} agent (${agent_id}) to invoke ${function_name}"
    
    # Generate a unique statement ID
    local statement_id="bedrock-agent-${agent_id}-$(date +%s)"
    
    # Add the permission
    aws lambda add-permission \
        --function-name "${function_name}" \
        --statement-id "${statement_id}" \
        --action "lambda:InvokeFunction" \
        --principal "bedrock.amazonaws.com" \
        --source-arn "arn:aws:bedrock:${REGION}:${ACCOUNT_ID}:agent/${agent_id}" \
        --output text > /dev/null 2>&1
    
    if [ $? -eq 0 ]; then
        echo "[SUCCESS] ✅ Permission added for ${function_name}"
    else
        # Check if permission already exists
        aws lambda get-policy --function-name "${function_name}" --query 'Policy' --output text 2>/dev/null | grep -q "${agent_id}"
        if [ $? -eq 0 ]; then
            echo "[INFO] ⚠️  Permission already exists for ${function_name}"
        else
            echo "[ERROR] ❌ Failed to add permission for ${function_name}"
            return 1
        fi
    fi
}

# Function to remove existing permissions for cleanup
remove_existing_permissions() {
    local function_name=$1
    local agent_id=$2
    
    echo "[INFO] Checking for existing permissions for agent ${agent_id} on ${function_name}"
    
    # Get current policy and extract statement IDs that match this agent
    local policy=$(aws lambda get-policy --function-name "${function_name}" --query 'Policy' --output text 2>/dev/null || echo "")
    
    if [ -n "$policy" ]; then
        # Extract statement IDs that contain this agent ID
        local statement_ids=$(echo "$policy" | jq -r --arg agent_id "$agent_id" '.Statement[] | select(.Condition.ArnLike."AWS:SourceArn" | contains($agent_id)) | .Sid' 2>/dev/null || echo "")
        
        if [ -n "$statement_ids" ]; then
            echo "$statement_ids" | while read -r sid; do
                if [ -n "$sid" ]; then
                    echo "[INFO] Removing existing permission: ${sid}"
                    aws lambda remove-permission --function-name "${function_name}" --statement-id "${sid}" > /dev/null 2>&1 || true
                fi
            done
        fi
    fi
}

echo "[INFO] Processing Lambda function permissions..."

# 1. Communication Handler Lambda
COMM_HANDLER_FUNCTION="oscar-communication-handler-cdk"
echo "[INFO] 📞 Fixing Communication Handler permissions..."

remove_existing_permissions "$COMM_HANDLER_FUNCTION" "$PRIVILEGED_AGENT_ID"
add_lambda_permission "$COMM_HANDLER_FUNCTION" "$PRIVILEGED_AGENT_ID" "OSCAR Privileged"

remove_existing_permissions "$COMM_HANDLER_FUNCTION" "$LIMITED_AGENT_ID"
add_lambda_permission "$COMM_HANDLER_FUNCTION" "$LIMITED_AGENT_ID" "OSCAR Limited"

# 2. Supervisor Agent Lambda
SUPERVISOR_FUNCTION="oscar-supervisor-agent-cdk"
echo "[INFO] 🎯 Fixing Supervisor Agent permissions..."

remove_existing_permissions "$SUPERVISOR_FUNCTION" "$PRIVILEGED_AGENT_ID"
add_lambda_permission "$SUPERVISOR_FUNCTION" "$PRIVILEGED_AGENT_ID" "OSCAR Privileged"

remove_existing_permissions "$SUPERVISOR_FUNCTION" "$LIMITED_AGENT_ID"
add_lambda_permission "$SUPERVISOR_FUNCTION" "$LIMITED_AGENT_ID" "OSCAR Limited"

# 3. Metrics Agent Lambdas
echo "[INFO] 📊 Fixing Metrics Agent permissions..."

for metrics_function in "oscar-test-metrics-agent-cdk" "oscar-build-metrics-agent-cdk" "oscar-release-metrics-agent-cdk"; do
    echo "[INFO] Processing $metrics_function..."
    
    remove_existing_permissions "$metrics_function" "$PRIVILEGED_AGENT_ID"
    add_lambda_permission "$metrics_function" "$PRIVILEGED_AGENT_ID" "OSCAR Privileged"
    
    remove_existing_permissions "$metrics_function" "$LIMITED_AGENT_ID"
    add_lambda_permission "$metrics_function" "$LIMITED_AGENT_ID" "OSCAR Limited"
done

# 4. Jenkins Agent Lambda
JENKINS_FUNCTION="oscar-jenkins-agent-cdk"
echo "[INFO] 🔧 Fixing Jenkins Agent permissions..."

remove_existing_permissions "$JENKINS_FUNCTION" "$PRIVILEGED_AGENT_ID"
add_lambda_permission "$JENKINS_FUNCTION" "$PRIVILEGED_AGENT_ID" "OSCAR Privileged"

remove_existing_permissions "$JENKINS_FUNCTION" "$LIMITED_AGENT_ID"
add_lambda_permission "$JENKINS_FUNCTION" "$LIMITED_AGENT_ID" "OSCAR Limited"

echo "[SUCCESS] ✅ Lambda function resource-based policies have been updated!"
echo "[INFO] 📋 Summary:"
echo "[INFO] - Communication Handler: Accessible by both OSCAR agents"
echo "[INFO] - Supervisor Agent: Accessible by both OSCAR agents"
echo "[INFO] - All Metrics Agents: Accessible by both OSCAR agents"
echo "[INFO] - Jenkins Agent: Accessible by both OSCAR agents"
echo "[INFO] 🎯 All Bedrock agents can now invoke their respective Lambda functions!"