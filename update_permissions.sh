#!/bin/bash
# Update IAM Permissions (Additive Only)
set -e

echo "🔐 Updating IAM Permissions"

# Load environment
if [ -f ".env" ]; then
    while IFS= read -r line; do
        [[ $line =~ ^[[:space:]]*# ]] && continue
        [[ -z $line ]] && continue
        export "$line"
    done < .env
fi

# Add Bedrock permissions to metrics agents
echo "📦 Adding Bedrock permissions to metrics agents..."
AGENT_PERMISSIONS=(
    "YXSZJ659S7:oscar-test-metrics-agent-new"
    "0NBATJIVCH:oscar-build-metrics-agent-new"
    "4FCARBPEYB:oscar-release-metrics-agent-new"
    "BIHPD6OLO0:oscar-deployment-metrics-agent-new"
)

for entry in "${AGENT_PERMISSIONS[@]}"; do
    IFS=':' read -ra PARTS <<< "$entry"
    agent_id="${PARTS[0]}"
    function_name="${PARTS[1]}"
    
    aws lambda add-permission \
        --function-name "$function_name" \
        --statement-id "bedrock-v2-$agent_id-$(date +%s)" \
        --action "lambda:InvokeFunction" \
        --principal "bedrock.amazonaws.com" \
        --source-arn "arn:aws:bedrock:$AWS_REGION:395380602281:agent/$agent_id" \
        --region "$AWS_REGION" >/dev/null 2>&1 || echo "  Permission exists for $function_name"
done

# Add API Gateway permission to supervisor
echo "🌐 Adding API Gateway permission to supervisor..."
api_id=$(aws apigateway get-rest-apis --region "$AWS_REGION" --query "items[?name=='oscar-slack-webhook'].id" --output text)

if [ -n "$api_id" ] && [ "$api_id" != "None" ]; then
    aws lambda add-permission \
        --function-name oscar-supervisor-agent \
        --statement-id "apigateway-invoke-$(date +%s)" \
        --action lambda:InvokeFunction \
        --principal apigateway.amazonaws.com \
        --source-arn "arn:aws:execute-api:$AWS_REGION:*:$api_id/*/*" \
        --region "$AWS_REGION" >/dev/null 2>&1 || echo "  API Gateway permission exists"
fi

# Ensure supervisor has required IAM policies
echo "🔑 Checking supervisor IAM role..."
role_name="oscar-supervisor-lambda-role"

if aws iam get-role --role-name "$role_name" >/dev/null 2>&1; then
    # Add DynamoDB policy if missing
    cat > dynamodb-policy.json << EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "dynamodb:GetItem",
                "dynamodb:PutItem",
                "dynamodb:UpdateItem",
                "dynamodb:DeleteItem",
                "dynamodb:Query"
            ],
            "Resource": [
                "arn:aws:dynamodb:$AWS_REGION:*:table/${SESSIONS_TABLE_NAME:-oscar-sessions-v2}",
                "arn:aws:dynamodb:$AWS_REGION:*:table/${CONTEXT_TABLE_NAME:-oscar-context}"
            ]
        }
    ]
}
EOF

    aws iam put-role-policy \
        --role-name "$role_name" \
        --policy-name "DynamoDBAccess" \
        --policy-document file://dynamodb-policy.json >/dev/null 2>&1 || echo "  DynamoDB policy exists"
    
    # Add Bedrock policy if missing
    cat > bedrock-policy.json << EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeAgent",
                "bedrock-agent-runtime:InvokeAgent"
            ],
            "Resource": "*"
        }
    ]
}
EOF

    aws iam put-role-policy \
        --role-name "$role_name" \
        --policy-name "BedrockAccess" \
        --policy-document file://bedrock-policy.json >/dev/null 2>&1 || echo "  Bedrock policy exists"
    
    rm -f dynamodb-policy.json bedrock-policy.json
    echo "  ✅ Supervisor IAM role updated"
else
    echo "  ⚠️  Supervisor IAM role not found - run deploy_infrastructure.sh first"
fi

echo "✅ Permissions updated"