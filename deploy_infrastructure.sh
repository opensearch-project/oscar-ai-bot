#!/bin/bash
# Deploy Infrastructure Resources (DynamoDB, API Gateway)
set -e

echo "🏗️ Deploying Infrastructure"

# Load environment
if [ -f ".env" ]; then
    while IFS= read -r line; do
        [[ $line =~ ^[[:space:]]*# ]] && continue
        [[ -z $line ]] && continue
        export "$line"
    done < .env
fi

# Create DynamoDB tables
echo "📊 Creating DynamoDB tables..."
sessions_table="${SESSIONS_TABLE_NAME:-oscar-sessions-v2}"
context_table="${CONTEXT_TABLE_NAME:-oscar-context}"

for table in "$sessions_table" "$context_table"; do
    if ! aws dynamodb describe-table --table-name "$table" --region "$AWS_REGION" >/dev/null 2>&1; then
        echo "  Creating $table..."
        if [ "$table" = "$sessions_table" ]; then
            key_attr="event_id"
        else
            key_attr="thread_key"
        fi
        
        aws dynamodb create-table \
            --table-name "$table" \
            --attribute-definitions AttributeName=$key_attr,AttributeType=S \
            --key-schema AttributeName=$key_attr,KeyType=HASH \
            --billing-mode PAY_PER_REQUEST \
            --region "$AWS_REGION" \
            --sse-specification Enabled=true >/dev/null
        
        aws dynamodb wait table-exists --table-name "$table" --region "$AWS_REGION"
        
        aws dynamodb update-time-to-live \
            --table-name "$table" \
            --time-to-live-specification Enabled=true,AttributeName=ttl \
            --region "$AWS_REGION" >/dev/null
    else
        echo "  ✅ $table exists"
    fi
done

# Create API Gateway
echo "🌐 Creating API Gateway..."
api_name="oscar-slack-webhook"
existing_api_id=$(aws apigateway get-rest-apis --region "$AWS_REGION" --query "items[?name=='$api_name'].id" --output text)

if [ -n "$existing_api_id" ] && [ "$existing_api_id" != "None" ]; then
    echo "  ✅ API Gateway exists: $existing_api_id"
    API_ID="$existing_api_id"
else
    echo "  Creating API Gateway..."
    
    # Get supervisor function ARN first
    FUNCTION_ARN=$(aws lambda get-function \
        --function-name oscar-supervisor-agent \
        --region "$AWS_REGION" \
        --query 'Configuration.FunctionArn' \
        --output text)
    
    # Create REST API
    API_ID=$(aws apigateway create-rest-api \
        --name "$api_name" \
        --description "OSCAR Slack webhook" \
        --endpoint-configuration types=REGIONAL \
        --region "$AWS_REGION" \
        --query 'id' \
        --output text)
    
    # Get root resource
    ROOT_ID=$(aws apigateway get-resources \
        --rest-api-id "$API_ID" \
        --region "$AWS_REGION" \
        --query 'items[?path==`/`].id' \
        --output text)
    
    # Create /slack resource
    SLACK_ID=$(aws apigateway create-resource \
        --rest-api-id "$API_ID" \
        --parent-id "$ROOT_ID" \
        --path-part "slack" \
        --region "$AWS_REGION" \
        --query 'id' \
        --output text)
    
    # Create /slack/events resource
    EVENTS_ID=$(aws apigateway create-resource \
        --rest-api-id "$API_ID" \
        --parent-id "$SLACK_ID" \
        --path-part "events" \
        --region "$AWS_REGION" \
        --query 'id' \
        --output text)
    
    # Create ANY method (like CDK LambdaRestApi does)
    aws apigateway put-method \
        --rest-api-id "$API_ID" \
        --resource-id "$EVENTS_ID" \
        --http-method ANY \
        --authorization-type NONE \
        --region "$AWS_REGION" >/dev/null
    
    # Create Lambda proxy integration
    aws apigateway put-integration \
        --rest-api-id "$API_ID" \
        --resource-id "$EVENTS_ID" \
        --http-method ANY \
        --type AWS_PROXY \
        --integration-http-method POST \
        --uri "arn:aws:apigateway:$AWS_REGION:lambda:path/2015-03-31/functions/$FUNCTION_ARN/invocations" \
        --region "$AWS_REGION" >/dev/null
    
    # Add Lambda permission for API Gateway
    aws lambda add-permission \
        --function-name oscar-supervisor-agent \
        --statement-id "apigateway-invoke-$(date +%s)" \
        --action lambda:InvokeFunction \
        --principal apigateway.amazonaws.com \
        --source-arn "arn:aws:execute-api:$AWS_REGION:*:$API_ID/*/*" \
        --region "$AWS_REGION" >/dev/null 2>&1 || echo "    (Permission may already exist)"
    
    # Deploy API
    aws apigateway create-deployment \
        --rest-api-id "$API_ID" \
        --stage-name prod \
        --region "$AWS_REGION" >/dev/null
    
    echo "  Created API Gateway: $API_ID"
fi

# Output webhook URL
WEBHOOK_URL="https://$API_ID.execute-api.$AWS_REGION.amazonaws.com/prod/slack/events"
echo ""
echo "✅ Infrastructure deployed"
echo "📋 Webhook URL: $WEBHOOK_URL"
echo ""
echo "🔗 Configure in Slack:"
echo "  Event Subscriptions → Request URL: $WEBHOOK_URL"