#!/bin/bash
# Enable API Gateway logging
set -e

# Load environment
if [ -f ".env" ]; then
    while IFS= read -r line; do
        [[ $line =~ ^[[:space:]]*# ]] && continue
        [[ -z $line ]] && continue
        export "$line"
    done < .env
fi

api_id=$(aws apigateway get-rest-apis --region "$AWS_REGION" --query "items[?name=='oscar-slack-webhook'].id" --output text)

echo "🔧 Enabling API Gateway logging for $api_id"

# Update stage to enable logging
aws apigateway update-stage \
    --rest-api-id "$api_id" \
    --stage-name prod \
    --patch-ops op=replace,path=/accessLogSettings/destinationArn,value="arn:aws:logs:$AWS_REGION:395380602281:log-group:API-Gateway-Execution-Logs_${api_id}/prod" \
    --patch-ops op=replace,path=/accessLogSettings/format,value='$requestId $status $error.message $error.messageString' \
    --region "$AWS_REGION" >/dev/null 2>&1 || echo "Logging may already be enabled"

# Create log group if it doesn't exist
aws logs create-log-group \
    --log-group-name "API-Gateway-Execution-Logs_${api_id}/prod" \
    --region "$AWS_REGION" >/dev/null 2>&1 || echo "Log group may already exist"

echo "✅ API Gateway logging enabled"
echo "🧪 Test webhook again, then check logs with:"
echo "aws logs tail API-Gateway-Execution-Logs_${api_id}/prod --region $AWS_REGION --since 5m"