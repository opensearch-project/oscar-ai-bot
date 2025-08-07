#!/bin/bash
# Fix Lambda permission for API Gateway
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

echo "🔧 Fixing Lambda permission for API Gateway"
echo "API ID: $api_id"
echo "Account: 395380602281"

# Remove all existing API Gateway permissions
echo "Removing existing permissions..."
aws lambda get-policy --function-name oscar-supervisor-agent --region "$AWS_REGION" --query 'Policy' --output text 2>/dev/null | \
jq -r '.Statement[] | select(.Principal.Service == "apigateway.amazonaws.com") | .Sid' 2>/dev/null | \
while read sid; do
    if [ -n "$sid" ]; then
        aws lambda remove-permission \
            --function-name oscar-supervisor-agent \
            --statement-id "$sid" \
            --region "$AWS_REGION" >/dev/null 2>&1 || true
        echo "  Removed permission: $sid"
    fi
done

# Add new permission
echo "Adding new permission..."
aws lambda add-permission \
    --function-name oscar-supervisor-agent \
    --statement-id "apigateway-invoke-$(date +%s)" \
    --action lambda:InvokeFunction \
    --principal apigateway.amazonaws.com \
    --source-arn "arn:aws:execute-api:$AWS_REGION:395380602281:$api_id/*/*" \
    --region "$AWS_REGION" >/dev/null

echo "✅ Lambda permission fixed"
echo "🧪 Test webhook now"