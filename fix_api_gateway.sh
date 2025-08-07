#!/bin/bash
# Fix API Gateway integration
set -e

echo "🔧 Fixing API Gateway integration"

# Load environment
if [ -f ".env" ]; then
    while IFS= read -r line; do
        [[ $line =~ ^[[:space:]]*# ]] && continue
        [[ -z $line ]] && continue
        export "$line"
    done < .env
fi

# Get API Gateway details
api_id=$(aws apigateway get-rest-apis --region "$AWS_REGION" --query "items[?name=='oscar-slack-webhook'].id" --output text)

if [ -z "$api_id" ] || [ "$api_id" = "None" ]; then
    echo "❌ API Gateway not found"
    exit 1
fi

echo "API Gateway ID: $api_id"

# Get resources
resources=$(aws apigateway get-resources --rest-api-id "$api_id" --region "$AWS_REGION")
events_id=$(echo "$resources" | jq -r '.items[] | select(.pathPart == "events") | .id')

if [ -z "$events_id" ] || [ "$events_id" = "null" ]; then
    echo "❌ /slack/events resource not found"
    exit 1
fi

echo "Events resource ID: $events_id"

# Get function ARN
function_arn=$(aws lambda get-function --function-name oscar-supervisor-agent --region "$AWS_REGION" --query 'Configuration.FunctionArn' --output text)
echo "Function ARN: $function_arn"

# Delete existing method and integration
echo "Removing existing method..."
aws apigateway delete-method \
    --rest-api-id "$api_id" \
    --resource-id "$events_id" \
    --http-method ANY \
    --region "$AWS_REGION" >/dev/null 2>&1 || true

# Create POST method (not ANY)
echo "Creating POST method..."
aws apigateway put-method \
    --rest-api-id "$api_id" \
    --resource-id "$events_id" \
    --http-method POST \
    --authorization-type NONE \
    --region "$AWS_REGION" >/dev/null

# Create proper Lambda proxy integration
echo "Creating Lambda proxy integration..."
aws apigateway put-integration \
    --rest-api-id "$api_id" \
    --resource-id "$events_id" \
    --http-method POST \
    --type AWS_PROXY \
    --integration-http-method POST \
    --uri "arn:aws:apigateway:$AWS_REGION:lambda:path/2015-03-31/functions/$function_arn/invocations" \
    --region "$AWS_REGION" >/dev/null

# Deploy API
echo "Deploying API..."
aws apigateway create-deployment \
    --rest-api-id "$api_id" \
    --stage-name prod \
    --region "$AWS_REGION" >/dev/null

echo "✅ API Gateway fixed"
echo "🧪 Test webhook now"