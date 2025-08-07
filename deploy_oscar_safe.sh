#!/bin/bash
# Safe OSCAR Deployment - Preserves existing resources
set -e

echo "🛡️ Safe OSCAR Deployment"
echo "========================"
echo ""
echo "This script will:"
echo "  ✅ Deploy metrics agents (preserves existing permissions)"
echo "  ✅ Create missing DynamoDB tables only"
echo "  ✅ Deploy supervisor (updates code, preserves IAM role)"
echo "  ✅ Create API Gateway if missing"
echo "  ✅ Provide webhook URL for Slack configuration"
echo ""

# Load environment
if [ -f ".env" ]; then
    while IFS= read -r line; do
        [[ $line =~ ^[[:space:]]*# ]] && continue
        [[ -z $line ]] && continue
        export "$line"
    done < .env
else
    echo "❌ .env file not found"
    exit 1
fi

# Step 1: Deploy metrics (your existing script handles permissions safely)
echo "📦 Step 1: Deploying Metrics Agents"
./deploy_metrics.sh
echo ""

# Step 2: Check/Create DynamoDB tables
echo "📊 Step 2: Checking DynamoDB Tables"
sessions_table="${SESSIONS_TABLE_NAME:-oscar-sessions-v2}"
context_table="${CONTEXT_TABLE_NAME:-oscar-context}"

# Only create if doesn't exist
if ! aws dynamodb describe-table --table-name "$sessions_table" --region "$AWS_REGION" >/dev/null 2>&1; then
    echo "  Creating sessions table: $sessions_table"
    aws dynamodb create-table \
        --table-name "$sessions_table" \
        --attribute-definitions AttributeName=event_id,AttributeType=S \
        --key-schema AttributeName=event_id,KeyType=HASH \
        --billing-mode PAY_PER_REQUEST \
        --region "$AWS_REGION" \
        --sse-specification Enabled=true >/dev/null
    aws dynamodb wait table-exists --table-name "$sessions_table" --region "$AWS_REGION"
    aws dynamodb update-time-to-live \
        --table-name "$sessions_table" \
        --time-to-live-specification Enabled=true,AttributeName=ttl \
        --region "$AWS_REGION" >/dev/null
else
    echo "  ✅ Sessions table exists: $sessions_table"
fi

if ! aws dynamodb describe-table --table-name "$context_table" --region "$AWS_REGION" >/dev/null 2>&1; then
    echo "  Creating context table: $context_table"
    aws dynamodb create-table \
        --table-name "$context_table" \
        --attribute-definitions AttributeName=thread_key,AttributeType=S \
        --key-schema AttributeName=thread_key,KeyType=HASH \
        --billing-mode PAY_PER_REQUEST \
        --region "$AWS_REGION" \
        --sse-specification Enabled=true >/dev/null
    aws dynamodb wait table-exists --table-name "$context_table" --region "$AWS_REGION"
    aws dynamodb update-time-to-live \
        --table-name "$context_table" \
        --time-to-live-specification Enabled=true,AttributeName=ttl \
        --region "$AWS_REGION" >/dev/null
else
    echo "  ✅ Context table exists: $context_table"
fi
echo ""

# Step 3: Deploy supervisor (preserves existing IAM role)
echo "🚀 Step 3: Deploying Supervisor"
./deploy_oscar_supervisor.sh
echo ""

# Step 4: Check/Create API Gateway
echo "🌐 Step 4: Checking API Gateway"
api_name="oscar-slack-webhook"
existing_api_id=$(aws apigateway get-rest-apis --region "$AWS_REGION" --query "items[?name=='$api_name'].id" --output text)

if [ -n "$existing_api_id" ] && [ "$existing_api_id" != "None" ]; then
    echo "  ✅ API Gateway exists: $existing_api_id"
    API_ID="$existing_api_id"
else
    echo "  Creating API Gateway..."
    # Run the API Gateway creation from the main script
    source deploy_oscar_complete_automated.sh
    create_api_gateway
fi

# Get webhook URL
API_URL="https://$API_ID.execute-api.$AWS_REGION.amazonaws.com/prod"
WEBHOOK_URL="$API_URL/slack/events"

echo ""
echo "✅ Safe Deployment Complete!"
echo "============================"
echo ""
echo "📋 Summary:"
echo "  Webhook URL: $WEBHOOK_URL"
echo "  Sessions Table: $sessions_table"
echo "  Context Table: $context_table"
echo ""
echo "🔗 Slack Configuration:"
echo "  Set Event Subscriptions URL to: $WEBHOOK_URL"
echo ""
echo "🧪 Test with: @oscar hello"