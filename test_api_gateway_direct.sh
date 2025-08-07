#!/bin/bash
# Test API Gateway with proper event structure
set -e

# Load environment
if [ -f ".env" ]; then
    while IFS= read -r line; do
        [[ $line =~ ^[[:space:]]*# ]] && continue
        [[ -z $line ]] && continue
        export "$line"
    done < .env
fi

echo "🧪 Testing Lambda with API Gateway event structure"

# Create proper API Gateway event structure
cat > api-gateway-event.json << 'EOF'
{
    "httpMethod": "POST",
    "path": "/slack/events",
    "headers": {
        "Content-Type": "application/json"
    },
    "body": "{\"type\": \"url_verification\", \"challenge\": \"test123\"}"
}
EOF

aws lambda invoke --function-name oscar-supervisor-agent \
    --payload file://api-gateway-event.json \
    --cli-binary-format raw-in-base64-out \
    --region "$AWS_REGION" api-gateway-test.json

echo "Lambda response with API Gateway event:"
cat api-gateway-test.json

rm -f api-gateway-event.json api-gateway-test.json