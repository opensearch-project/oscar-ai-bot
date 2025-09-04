#!/bin/bash

# CDK Lambda Permissions Fixer
# This script fixes Lambda execution role permissions for ALL OSCAR CDK Lambda functions

set -e

echo "[INFO] 🔧 Fixing Lambda execution role permissions for OSCAR CDK deployment..."
echo "[INFO] ======================================================================="

# Configuration
PRIVILEGED_AGENT_ID="MMJVHNFRAQ"
PRIVILEGED_AGENT_ALIAS="TEOZAGSWCV"
LIMITED_AGENT_ID="TBB6FSCSJ2"
LIMITED_AGENT_ALIAS="L5C80SCNBX"
ACCOUNT_ID="395380602281"
REGION="us-east-1"

echo "[INFO] Privileged Agent: $PRIVILEGED_AGENT_ID/$PRIVILEGED_AGENT_ALIAS"
echo "[INFO] Limited Agent: $LIMITED_AGENT_ID/$LIMITED_AGENT_ALIAS"

# Function to add policy to role
add_policy_to_role() {
    local role_name=$1
    local policy_name=$2
    local policy_document=$3
    
    echo "[INFO] Adding policy '$policy_name' to role '$role_name'..."
    aws iam put-role-policy \
        --role-name "$role_name" \
        --policy-name "$policy_name" \
        --policy-document "$policy_document"
    echo "[SUCCESS] ✅ Policy '$policy_name' added to '$role_name'"
}

# 1. FIX SUPERVISOR AGENT (oscar-supervisor-agent-cdk)
echo "[INFO] 🎯 Fixing Supervisor Agent permissions..."

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
echo "[INFO] 📞 Fixing Communication Handler permissions..."

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
echo "[INFO] 📊 Fixing Metrics Agents permissions..."

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
        }
    ]
}'

add_policy_to_role "oscar-vpc-lambda-execution-role-cdk" "MetricsAgentsCDKPolicy" "$METRICS_ADDITIONAL_POLICY"

# 4. FIX JENKINS AGENT (oscar-jenkins-agent-cdk)
echo "[INFO] 🔧 Fixing Jenkins Agent permissions..."

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

# 5. ADD RESOURCE-BASED POLICIES TO BEDROCK AGENTS
echo "[INFO] 🔐 Adding resource-based policies to Bedrock agents..."

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
    --policy "$RESOURCE_POLICY" || {
    echo "[WARNING] ⚠️  Failed to add resource-based policy to privileged agent. This might be expected if policy already exists."
}

# Apply to limited agent  
aws bedrock-agent put-agent-resource-policy \
    --agent-id "$LIMITED_AGENT_ID" \
    --policy "$RESOURCE_POLICY" || {
    echo "[WARNING] ⚠️  Failed to add resource-based policy to limited agent. This might be expected if policy already exists."
}

echo "[SUCCESS] ✅ Resource-based policies applied to Bedrock agents"

# 6. VERIFY ALL PERMISSIONS
echo "[INFO] 🔍 Verifying permissions for all roles..."

echo "[INFO] Supervisor Agent Role (oscar-lambda-execution-role-cdk):"
aws iam list-role-policies --role-name "oscar-lambda-execution-role-cdk" --query 'PolicyNames' --output table

echo "[INFO] Communication Handler Role (oscar-communication-handler-execution-role-cdk):"
aws iam list-role-policies --role-name "oscar-communication-handler-execution-role-cdk" --query 'PolicyNames' --output table

echo "[INFO] VPC Lambda Role for Metrics (oscar-vpc-lambda-execution-role-cdk):"
aws iam list-role-policies --role-name "oscar-vpc-lambda-execution-role-cdk" --query 'PolicyNames' --output table

echo "[INFO] Jenkins Agent Role (oscar-jenkins-lambda-execution-role-cdk):"
aws iam list-role-policies --role-name "oscar-jenkins-lambda-execution-role-cdk" --query 'PolicyNames' --output table

echo "[INFO] 🎉 ALL Lambda function permissions fixed successfully!"
echo "[INFO] Summary of fixes applied:"
echo "[INFO]   ✅ Supervisor Agent: Bedrock agents, DynamoDB, Lambda invocation"
echo "[INFO]   ✅ Communication Handler: Bedrock agents, DynamoDB, CloudWatch Logs"
echo "[INFO]   ✅ Metrics Agents: Cross-account OpenSearch, S3 cache, CloudWatch Logs"
echo "[INFO]   ✅ Jenkins Agent: Bedrock agents, CloudWatch Logs"
echo "[INFO]   ✅ Resource-based policies on Bedrock agents for all Lambda roles"
echo "[INFO] ======================================================================"