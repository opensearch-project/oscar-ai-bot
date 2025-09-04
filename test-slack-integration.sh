#!/bin/bash

# Test Slack Integration Script
set -e

echo "🔍 Testing Slack Integration..."

# Update secrets manager with current .env
echo "📝 Updating Secrets Manager..."
./update-secret-with-env.sh

# Test API Gateway endpoint
echo "🌐 Testing API Gateway endpoint..."
API_URL=$(grep "API_GATEWAY_URL" cdk/.env | cut -d'=' -f2)
SLACK_EVENTS_URL="${API_URL}/slack/events"

echo "Testing URL: $SLACK_EVENTS_URL"

# Test with a simple GET request
curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" "$SLACK_EVENTS_URL" || echo "❌ API Gateway not responding"

# Check recent Lambda logs
echo "📋 Checking recent Lambda logs..."
aws logs filter-log-events \
    --log-group-name "/aws/lambda/oscar-supervisor-agent-cdk" \
    --start-time $(($(date +%s) - 300))000 \
    --query 'events[-5:].message' \
    --output text

echo "✅ Test complete!"