#!/bin/bash
# Test webhook URL
set -e

# Load environment
if [ -f ".env" ]; then
    while IFS= read -r line; do
        [[ $line =~ ^[[:space:]]*# ]] && continue
        [[ -z $line ]] && continue
        export "$line"
    done < .env
fi

# Get API Gateway URL
api_id=$(aws apigateway get-rest-apis --region "$AWS_REGION" --query "items[?name=='oscar-slack-webhook'].id" --output text)

if [ -z "$api_id" ] || [ "$api_id" = "None" ]; then
    echo "❌ API Gateway not found"
    exit 1
fi

WEBHOOK_URL="https://$api_id.execute-api.$AWS_REGION.amazonaws.com/prod/slack/events"
echo "🧪 Testing webhook: $WEBHOOK_URL"

# Test URL verification
echo "Testing URL verification..."
echo "Request: POST $WEBHOOK_URL"
echo "Body: {\"type\": \"url_verification\", \"challenge\": \"test123\"}"
echo ""

response=$(curl -s -w "\nHTTP_CODE:%{http_code}" -X POST "$WEBHOOK_URL" \
    -H "Content-Type: application/json" \
    -d '{"type": "url_verification", "challenge": "test123"}')

echo "Full response:"
echo "$response"
echo ""

if echo "$response" | grep -q "test123"; then
    echo "✅ Webhook working correctly"
else
    echo "❌ Webhook not working"
    echo "Expected: challenge value 'test123'"
    
    # Test if Lambda function exists and is working
    echo ""
    echo "Testing Lambda function directly..."
    aws lambda invoke --function-name oscar-supervisor-agent \
        --payload '{"body": "{\"type\": \"url_verification\", \"challenge\": \"test123\"}"}' \
        --cli-binary-format raw-in-base64-out \
        --region "$AWS_REGION" lambda-test.json
    
    echo "Lambda response:"
    cat lambda-test.json
    rm -f lambda-test.json
fi