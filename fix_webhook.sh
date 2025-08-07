#!/bin/bash
# Fix webhook URL issue
set -e

echo "🔧 Fixing webhook URL issue"

# Load environment
if [ -f ".env" ]; then
    while IFS= read -r line; do
        [[ $line =~ ^[[:space:]]*# ]] && continue
        [[ -z $line ]] && continue
        export "$line"
    done < .env
fi

# 1. Update Lambda function first
echo "📦 Updating supervisor Lambda..."
./update_lambdas.sh

# 2. Ensure API Gateway is properly configured
echo "🌐 Checking API Gateway..."
api_id=$(aws apigateway get-rest-apis --region "$AWS_REGION" --query "items[?name=='oscar-slack-webhook'].id" --output text)

if [ -z "$api_id" ] || [ "$api_id" = "None" ]; then
    echo "  Creating API Gateway..."
    ./deploy_infrastructure.sh
else
    echo "  API Gateway exists: $api_id"
    
    # Redeploy to ensure latest changes
    echo "  Redeploying API..."
    aws apigateway create-deployment \
        --rest-api-id "$api_id" \
        --stage-name prod \
        --region "$AWS_REGION" >/dev/null
fi

# 3. Update permissions
echo "🔐 Updating permissions..."
./update_permissions.sh

# 4. Test webhook
echo "🧪 Testing webhook..."
./test_webhook.sh

echo "✅ Webhook fix complete"