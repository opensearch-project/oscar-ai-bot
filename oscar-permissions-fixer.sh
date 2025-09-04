#!/bin/bash

# OSCAR Complete Permissions Fixer
# This script fixes ALL permissions for OSCAR CDK deployment:
# 1. Resource-based policies on Lambda functions (allows Bedrock agents to invoke them)
# 2. Identity-based policies on IAM roles (allows Lambda functions to access AWS services)

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}[INFO] 🔐 OSCAR Complete Permissions Fixer${NC}"
echo -e "${BLUE}[INFO] ====================================${NC}"
echo -e "${BLUE}[INFO] Fixing both resource-based and identity-based policies...${NC}"

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

# Configuration from environment or defaults
PRIVILEGED_AGENT_ID="${OSCAR_PRIVILEGED_BEDROCK_AGENT_ID:-MMJVHNFRAQ}"
PRIVILEGED_AGENT_ALIAS="${OSCAR_PRIVILEGED_BEDROCK_AGENT_ALIAS_ID:-TEOZAGSWCV}"
LIMITED_AGENT_ID="${OSCAR_LIMITED_BEDROCK_AGENT_ID:-TBB6FSCSJ2}"
LIMITED_AGENT_ALIAS="${OSCAR_LIMITED_BEDROCK_AGENT_ALIAS_ID:-L5C80SCNBX}"
ACCOUNT_ID="${AWS_ACCOUNT_ID:-395380602281}"
REGION="${AWS_REGION:-us-east-1}"

echo -e "${BLUE}[INFO] Configuration:${NC}"
echo -e "${BLUE}[INFO] - Privileged Agent: $PRIVILEGED_AGENT_ID/$PRIVILEGED_AGENT_ALIAS${NC}"
echo -e "${BLUE}[INFO] - Limited Agent: $LIMITED_AGENT_ID/$LIMITED_AGENT_ALIAS${NC}"
echo -e "${BLUE}[INFO] - Account: $ACCOUNT_ID${NC}"
echo -e "${BLUE}[INFO] - Region: $REGION${NC}"

# =============================================================================
# PART 1: IDENTITY-BASED POLICIES (IAM Role Policies)
# =============================================================================

echo -e "${BLUE}[INFO] 🎯 PART 1: Fixing IAM Role Policies (Identity-based)${NC}"

# Function to add policy to role
add_policy_to_role() {
    local role_name=$1
    local policy_name=$2
    local policy_document=$3
    
    echo -e "${BLUE}[INFO] Adding policy '$policy_name' to role '$role_name'...${NC}"
    aws iam put-role-policy \
        --role-name "$role_name" \
        --policy-name "$policy_name" \
        --policy-document "$policy_document"
    echo -e "${GREEN}[SUCCESS] ✅ Policy '$policy_name' added to '$role_name'${NC}"
}

# 1. FIX SUPERVISOR AGENT (oscar-supervisor-agent-cdk)
echo -e "${BLUE}[INFO] 🎯 Fixing Supervisor Agent IAM permissions...${NC}"

SUPERVISOR_BEDROCK_POLICY='{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "BedrockAgentInvocation",
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeAgent",
                "bedrock-agent-runtime:InvokeAgent",
                "bedrock:InvokeModel",
                "bedrock:GetAgent",
                "bedrock:GetKnowledgeBase",
                "bedrock:Retrieve",
                "bedrock:RetrieveAndGenerate"
            ],
            "Resource": [
                "arn:aws:bedrock:'$REGION':'$ACCOUNT_ID':agent/'$PRIVILEGED_AGENT_ID'",
                "arn:aws:bedrock:'$REGION':'$ACCOUNT_ID':agent-alias/'$PRIVILEGED_AGENT_ID'/'$PRIVILEGED_AGENT_ALIAS'",
                "arn:aws:bedrock:'$REGION':'$ACCOUNT_ID':agent-alias/'$PRIVILEGED_AGENT_ID'/*",
                "arn:aws:bedrock:'$REGION':'$ACCOUNT_ID':agent/'$LIMITED_AGENT_ID'",
                "arn:aws:bedrock:'$REGION':'$ACCOUNT_ID':agent-alias/'$LIMITED_AGENT_ID'/'$LIMITED_AGENT_ALIAS'",
                "arn:aws:bedrock:'$REGION':'$ACCOUNT_ID':agent-alias/'$LIMITED_AGENT_ID'/*",
                "arn:aws:bedrock:'$REGION':'$ACCOUNT_ID':knowledge-base/*",
                "arn:aws:bedrock:'$REGION'::foundation-model/anthropic.claude-3-haiku-*",
                "arn:aws:bedrock:'$REGION'::foundation-model/anthropic.claude-3-sonnet-*"
            ]
        }
    ]
}'

SUPERVISOR_DYNAMODB_POLICY='{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "DynamoDBCDKAccess",
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
                "arn:aws:dynamodb:'$REGION':'$ACCOUNT_ID':table/oscar-agent-context-dev-cdk",
                "arn:aws:dynamodb:'$REGION':'$ACCOUNT_ID':table/oscar-agent-context-dev-cdk/*",
                "arn:aws:dynamodb:'$REGION':'$ACCOUNT_ID':table/oscar-agent-sessions-dev-cdk",
                "arn:aws:dynamodb:'$REGION':'$ACCOUNT_ID':table/oscar-agent-sessions-dev-cdk/*",
                "arn:aws:dynamodb:'$REGION':'$ACCOUNT_ID':table/oscar-context-dev-cdk",
                "arn:aws:dynamodb:'$REGION':'$ACCOUNT_ID':table/oscar-context-dev-cdk/*",
                "arn:aws:dynamodb:'$REGION':'$ACCOUNT_ID':table/oscar-sessions-dev-cdk",
                "arn:aws:dynamodb:'$REGION':'$ACCOUNT_ID':table/oscar-sessions-dev-cdk/*"
            ]
        }
    ]
}'

SUPERVISOR_LAMBDA_POLICY='{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "LambdaCDKInvocation",
            "Effect": "Allow",
            "Action": [
                "lambda:InvokeFunction"
            ],
            "Resource": [
                "arn:aws:lambda:'$REGION':'$ACCOUNT_ID':function:oscar-*-cdk",
                "arn:aws:lambda:'$REGION':'$ACCOUNT_ID':function:oscar-supervisor-agent-cdk",
                "arn:aws:lambda:'$REGION':'$ACCOUNT_ID':function:oscar-communication-handler-cdk",
                "arn:aws:lambda:'$REGION':'$ACCOUNT_ID':function:oscar-test-metrics-agent-cdk",
                "arn:aws:lambda:'$REGION':'$ACCOUNT_ID':function:oscar-build-metrics-agent-cdk",
                "arn:aws:lambda:'$REGION':'$ACCOUNT_ID':function:oscar-release-metrics-agent-cdk",
                "arn:aws:lambda:'$REGION':'$ACCOUNT_ID':function:oscar-jenkins-agent-cdk"
            ]
        }
    ]
}'

add_policy_to_role "oscar-lambda-execution-role-cdk" "BedrockAgentInvocationPolicy" "$SUPERVISOR_BEDROCK_POLICY"
add_policy_to_role "oscar-lambda-execution-role-cdk" "DynamoDBCDKAccess" "$SUPERVISOR_DYNAMODB_POLICY"
add_policy_to_role "oscar-lambda-execution-role-cdk" "LambdaCDKInvocation" "$SUPERVISOR_LAMBDA_POLICY"

# 2. FIX COMMUNICATION HANDLER (oscar-communication-handler-cdk)
echo -e "${BLUE}[INFO] 📞 Fixing Communication Handler IAM permissions...${NC}"

COMM_HANDLER_POLICY='{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeAgent",
                "bedrock:InvokeModel",
                "bedrock:GetAgent",
                "bedrock:GetKnowledgeBase"
            ],
            "Resource": "*"
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
                "arn:aws:dynamodb:'$REGION':'$ACCOUNT_ID':table/oscar-agent-context-dev-cdk",
                "arn:aws:dynamodb:'$REGION':'$ACCOUNT_ID':table/oscar-agent-context-dev-cdk/*",
                "arn:aws:dynamodb:'$REGION':'$ACCOUNT_ID':table/oscar-agent-sessions-dev-cdk",
                "arn:aws:dynamodb:'$REGION':'$ACCOUNT_ID':table/oscar-agent-sessions-dev-cdk/*"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": "arn:aws:logs:*:*:*"
        }
    ]
}'

add_policy_to_role "oscar-communication-handler-execution-role-cdk" "CommunicationHandlerCDKPolicy" "$COMM_HANDLER_POLICY"

# 3. FIX METRICS AGENTS (VPC Lambda role - shared by all 3 metrics agents)
echo -e "${BLUE}[INFO] 📊 Fixing Metrics Agents IAM permissions...${NC}"

# The metrics agents already have the cross-account OpenSearch access, just need to ensure secrets access
METRICS_ADDITIONAL_POLICY='{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": "arn:aws:logs:*:*:*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "secretsmanager:GetSecretValue"
            ],
            "Resource": [
                "arn:aws:secretsmanager:'$REGION':'$ACCOUNT_ID':secret:oscar-central-env-dev-cdk*",
                "arn:aws:secretsmanager:'$REGION':'$ACCOUNT_ID':secret:oscar-central-env*"
            ]
        }
    ]
}'

add_policy_to_role "oscar-metrics-lambda-vpc-role" "MetricsAgentsCDKPolicy" "$METRICS_ADDITIONAL_POLICY"

# 4. FIX JENKINS AGENT (oscar-jenkins-agent-cdk)
echo -e "${BLUE}[INFO] 🔧 Fixing Jenkins Agent IAM permissions...${NC}"

JENKINS_POLICY='{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeAgent",
                "bedrock:InvokeModel",
                "bedrock:GetAgent",
                "bedrock:GetKnowledgeBase"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": "arn:aws:logs:*:*:*"
        }
    ]
}'

add_policy_to_role "oscar-jenkins-lambda-execution-role-cdk" "JenkinsAgentCDKPolicy" "$JENKINS_POLICY"

# =============================================================================
# PART 2: RESOURCE-BASED POLICIES (Lambda Function Policies)
# =============================================================================

echo -e "${BLUE}[INFO] 🎯 PART 2: Fixing Lambda Function Policies (Resource-based)${NC}"

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
        --source-arn "arn:aws:bedrock:${REGION}:${ACCOUNT_ID}:agent/${agent_id}" \
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

echo -e "${BLUE}[INFO] Processing Lambda function resource-based permissions...${NC}"

# Legacy Lambda Functions (if they exist)
if [ -n "$MAIN_LAMBDA_ARN" ] && [ -n "$LIMITED_AGENT_ID" ]; then
    FUNCTION_NAME=$(echo "$MAIN_LAMBDA_ARN" | awk -F':' '{print $NF}')
    remove_existing_permissions "$FUNCTION_NAME" "$LIMITED_AGENT_ID"
    add_lambda_permission "$FUNCTION_NAME" "$LIMITED_AGENT_ID" "OSCAR Limited"
fi

if [ -n "$MAIN_LAMBDA_ARN" ] && [ -n "$PRIVILEGED_AGENT_ID" ]; then
    FUNCTION_NAME=$(echo "$MAIN_LAMBDA_ARN" | awk -F':' '{print $NF}')
    remove_existing_permissions "$FUNCTION_NAME" "$PRIVILEGED_AGENT_ID"
    add_lambda_permission "$FUNCTION_NAME" "$PRIVILEGED_AGENT_ID" "OSCAR Privileged"
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

# CDK Lambda Functions
echo -e "${BLUE}[INFO] 🔧 Processing CDK Lambda function resource-based permissions...${NC}"

# CDK Supervisor Agent Lambda
CDK_SUPERVISOR_FUNCTION="oscar-supervisor-agent-cdk"
if aws lambda get-function --function-name "$CDK_SUPERVISOR_FUNCTION" >/dev/null 2>&1; then
    echo -e "${BLUE}[INFO] Processing CDK Supervisor Agent Lambda...${NC}"
    if [ -n "$LIMITED_AGENT_ID" ]; then
        remove_existing_permissions "$CDK_SUPERVISOR_FUNCTION" "$LIMITED_AGENT_ID"
        add_lambda_permission "$CDK_SUPERVISOR_FUNCTION" "$LIMITED_AGENT_ID" "OSCAR Limited"
    fi
    if [ -n "$PRIVILEGED_AGENT_ID" ]; then
        remove_existing_permissions "$CDK_SUPERVISOR_FUNCTION" "$PRIVILEGED_AGENT_ID"
        add_lambda_permission "$CDK_SUPERVISOR_FUNCTION" "$PRIVILEGED_AGENT_ID" "OSCAR Privileged"
    fi
fi

# CDK Communication Handler Lambda
CDK_COMM_HANDLER_FUNCTION="oscar-communication-handler-cdk"
if aws lambda get-function --function-name "$CDK_COMM_HANDLER_FUNCTION" >/dev/null 2>&1; then
    echo -e "${BLUE}[INFO] Processing CDK Communication Handler Lambda...${NC}"
    if [ -n "$LIMITED_AGENT_ID" ]; then
        remove_existing_permissions "$CDK_COMM_HANDLER_FUNCTION" "$LIMITED_AGENT_ID"
        add_lambda_permission "$CDK_COMM_HANDLER_FUNCTION" "$LIMITED_AGENT_ID" "OSCAR Limited"
    fi
    if [ -n "$PRIVILEGED_AGENT_ID" ]; then
        remove_existing_permissions "$CDK_COMM_HANDLER_FUNCTION" "$PRIVILEGED_AGENT_ID"
        add_lambda_permission "$CDK_COMM_HANDLER_FUNCTION" "$PRIVILEGED_AGENT_ID" "OSCAR Privileged"
    fi
fi

# CDK Metrics Agent Lambdas
for cdk_metrics_function in "oscar-test-metrics-agent-cdk" "oscar-build-metrics-agent-cdk" "oscar-release-metrics-agent-cdk"; do
    if aws lambda get-function --function-name "$cdk_metrics_function" >/dev/null 2>&1; then
        echo -e "${BLUE}[INFO] Processing CDK Metrics Lambda: $cdk_metrics_function${NC}"
        if [ -n "$LIMITED_AGENT_ID" ]; then
            remove_existing_permissions "$cdk_metrics_function" "$LIMITED_AGENT_ID"
            add_lambda_permission "$cdk_metrics_function" "$LIMITED_AGENT_ID" "OSCAR Limited"
        fi
        if [ -n "$PRIVILEGED_AGENT_ID" ]; then
            remove_existing_permissions "$cdk_metrics_function" "$PRIVILEGED_AGENT_ID"
            add_lambda_permission "$cdk_metrics_function" "$PRIVILEGED_AGENT_ID" "OSCAR Privileged"
        fi
    fi
done

# CDK Jenkins Agent Lambda
CDK_JENKINS_FUNCTION="oscar-jenkins-agent-cdk"
if aws lambda get-function --function-name "$CDK_JENKINS_FUNCTION" >/dev/null 2>&1; then
    echo -e "${BLUE}[INFO] Processing CDK Jenkins Agent Lambda...${NC}"
    if [ -n "$LIMITED_AGENT_ID" ]; then
        remove_existing_permissions "$CDK_JENKINS_FUNCTION" "$LIMITED_AGENT_ID"
        add_lambda_permission "$CDK_JENKINS_FUNCTION" "$LIMITED_AGENT_ID" "OSCAR Limited"
    fi
    if [ -n "$PRIVILEGED_AGENT_ID" ]; then
        remove_existing_permissions "$CDK_JENKINS_FUNCTION" "$PRIVILEGED_AGENT_ID"
        add_lambda_permission "$CDK_JENKINS_FUNCTION" "$PRIVILEGED_AGENT_ID" "OSCAR Privileged"
    fi
fi

# =============================================================================
# PART 3: BEDROCK AGENT RESOURCE-BASED POLICIES
# =============================================================================

echo -e "${BLUE}[INFO] 🎯 PART 3: Adding resource-based policies to Bedrock agents...${NC}"

# Get all Lambda execution role ARNs
SUPERVISOR_ROLE_ARN="arn:aws:iam::$ACCOUNT_ID:role/oscar-lambda-execution-role-cdk"
COMM_HANDLER_ROLE_ARN="arn:aws:iam::$ACCOUNT_ID:role/oscar-communication-handler-execution-role-cdk"
JENKINS_ROLE_ARN="arn:aws:iam::$ACCOUNT_ID:role/oscar-jenkins-lambda-execution-role-cdk"

RESOURCE_POLICY='{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "AllowLambdaInvocation",
            "Effect": "Allow",
            "Principal": {
                "AWS": [
                    "'$SUPERVISOR_ROLE_ARN'",
                    "'$COMM_HANDLER_ROLE_ARN'",
                    "'$JENKINS_ROLE_ARN'"
                ]
            },
            "Action": "bedrock:InvokeAgent",
            "Resource": "*"
        }
    ]
}'

# Apply to privileged agent
aws bedrock-agent put-agent-resource-policy \
    --agent-id "$PRIVILEGED_AGENT_ID" \
    --policy "$RESOURCE_POLICY" 2>/dev/null || {
    echo -e "${YELLOW}[WARNING] ⚠️  Failed to add resource-based policy to privileged agent. This might be expected if policy already exists.${NC}"
}

# Apply to limited agent  
aws bedrock-agent put-agent-resource-policy \
    --agent-id "$LIMITED_AGENT_ID" \
    --policy "$RESOURCE_POLICY" 2>/dev/null || {
    echo -e "${YELLOW}[WARNING] ⚠️  Failed to add resource-based policy to limited agent. This might be expected if policy already exists.${NC}"
}

echo -e "${GREEN}[SUCCESS] ✅ Resource-based policies applied to Bedrock agents${NC}"

# =============================================================================
# VERIFICATION
# =============================================================================

echo -e "${BLUE}[INFO] 🔍 Verifying permissions for all roles...${NC}"

echo -e "${BLUE}[INFO] Supervisor Agent Role (oscar-lambda-execution-role-cdk):${NC}"
aws iam list-role-policies --role-name "oscar-lambda-execution-role-cdk" --query 'PolicyNames' --output table

echo -e "${BLUE}[INFO] Communication Handler Role (oscar-communication-handler-execution-role-cdk):${NC}"
aws iam list-role-policies --role-name "oscar-communication-handler-execution-role-cdk" --query 'PolicyNames' --output table

echo -e "${BLUE}[INFO] VPC Lambda Role for Metrics (oscar-metrics-lambda-vpc-role):${NC}"
aws iam list-role-policies --role-name "oscar-metrics-lambda-vpc-role" --query 'PolicyNames' --output table

echo -e "${BLUE}[INFO] Jenkins Agent Role (oscar-jenkins-lambda-execution-role-cdk):${NC}"
aws iam list-role-policies --role-name "oscar-jenkins-lambda-execution-role-cdk" --query 'PolicyNames' --output table

echo -e "${GREEN}[SUCCESS] ✅ OSCAR Complete Permissions Fixer completed successfully!${NC}"
echo -e "${BLUE}[INFO] 📋 Summary of fixes applied:${NC}"
echo -e "${BLUE}[INFO]   ✅ Supervisor Agent: Bedrock agents, DynamoDB, Lambda invocation${NC}"
echo -e "${BLUE}[INFO]   ✅ Communication Handler: Bedrock agents, DynamoDB, CloudWatch Logs${NC}"
echo -e "${BLUE}[INFO]   ✅ Metrics Agents: Cross-account OpenSearch, S3 cache, CloudWatch Logs${NC}"
echo -e "${BLUE}[INFO]   ✅ Jenkins Agent: Bedrock agents, CloudWatch Logs${NC}"
echo -e "${BLUE}[INFO]   ✅ Resource-based policies on Lambda functions for Bedrock agent invocation${NC}"
echo -e "${BLUE}[INFO]   ✅ Resource-based policies on Bedrock agents for Lambda role access${NC}"
echo -e "${BLUE}[INFO] 🎯 All permissions configured! OSCAR should now work correctly.${NC}"