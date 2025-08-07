#!/bin/bash
# Check API Gateway integration
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
resources=$(aws apigateway get-resources --rest-api-id "$api_id" --region "$AWS_REGION")
events_id=$(echo "$resources" | jq -r '.items[] | select(.pathPart == "events") | .id')

echo "🔍 Checking API Gateway integration"
echo "API ID: $api_id"
echo "Events resource ID: $events_id"

# Check integration
aws apigateway get-integration \
    --rest-api-id "$api_id" \
    --resource-id "$events_id" \
    --http-method POST \
    --region "$AWS_REGION" \
    --query '{Type: type, IntegrationHttpMethod: httpMethod, Uri: uri}' \
    --output table