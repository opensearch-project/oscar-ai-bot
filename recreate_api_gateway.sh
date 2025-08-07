#!/bin/bash
# Recreate API Gateway from scratch
set -e

echo "🔧 Recreating API Gateway"

# Load environment
if [ -f ".env" ]; then
    while IFS= read -r line; do
        [[ $line =~ ^[[:space:]]*# ]] && continue
        [[ -z $line ]] && continue
        export "$line"
    done < .env
fi

# Delete existing API Gateway
api_id=$(aws apigateway get-rest-apis --region "$AWS_REGION" --query "items[?name=='oscar-slack-webhook'].id" --output text)

if [ -n "$api_id" ] && [ "$api_id" != "None" ]; then
    echo "Deleting existing API Gateway: $api_id"
    aws apigateway delete-rest-api --rest-api-id "$api_id" --region "$AWS_REGION"
    sleep 5
fi

# Get function ARN
function_arn=$(aws lambda get-function --function-name oscar-supervisor-agent --region "$AWS_REGION" --query 'Configuration.FunctionArn' --output text)
echo "Function ARN: $function_arn"

# Create new API Gateway
echo "Creating new API Gateway..."
api_id=$(aws apigateway create-rest-api \
    --name "oscar-slack-webhook" \
    --description "OSCAR Slack webhook" \
    --endpoint-configuration types=REGIONAL \
    --region "$AWS_REGION" \
    --query 'id' \
    --output text)

echo "Created API Gateway: $api_id"

# Get root resource
root_id=$(aws apigateway get-resources \
    --rest-api-id "$api_id" \
    --region "$AWS_REGION" \
    --query 'items[?path==`/`].id' \
    --output text)

# Create /slack resource
slack_id=$(aws apigateway create-resource \
    --rest-api-id "$api_id" \
    --parent-id "$root_id" \
    --path-part "slack" \
    --region "$AWS_REGION" \
    --query 'id' \
    --output text)

# Create /slack/events resource
events_id=$(aws apigateway create-resource \
    --rest-api-id "$api_id" \
    --parent-id "$slack_id" \
    --path-part "events" \
    --region "$AWS_REGION" \
    --query 'id' \
    --output text)

# Create POST method
aws apigateway put-method \
    --rest-api-id "$api_id" \
    --resource-id "$events_id" \
    --http-method POST \
    --authorization-type NONE \
    --region "$AWS_REGION" >/dev/null

# Create Lambda proxy integration
aws apigateway put-integration \
    --rest-api-id "$api_id" \
    --resource-id "$events_id" \
    --http-method POST \
    --type AWS_PROXY \
    --integration-http-method POST \
    --uri "arn:aws:apigateway:$AWS_REGION:lambda:path/2015-03-31/functions/$function_arn/invocations" \
    --region "$AWS_REGION" >/dev/null

# Add Lambda permission
aws lambda add-permission \
    --function-name oscar-supervisor-agent \
    --statement-id "apigateway-invoke-$(date +%s)" \
    --action lambda:InvokeFunction \
    --principal apigateway.amazonaws.com \
    --source-arn "arn:aws:execute-api:$AWS_REGION:*:$api_id/*/*" \
    --region "$AWS_REGION" >/dev/null 2>&1 || echo "Permission may already exist"

# Deploy API
aws apigateway create-deployment \
    --rest-api-id "$api_id" \
    --stage-name prod \
    --region "$AWS_REGION" >/dev/null

webhook_url="https://$api_id.execute-api.$AWS_REGION.amazonaws.com/prod/slack/events"
echo "✅ API Gateway recreated"
echo "🔗 Webhook URL: $webhook_url"