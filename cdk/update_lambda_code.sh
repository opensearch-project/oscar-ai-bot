#!/bin/bash
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

# Update Lambda function code using pre-built assets
# This ensures the Lambda functions get the latest code with dependencies

set -e

echo "🔄 Updating Lambda function code with dependencies..."

# Prepare assets first
./prepare_lambda_assets.sh

# Function to update Lambda code
update_lambda_code() {
    local function_name=$1
    local asset_dir=$2
    
    echo "📦 Updating $function_name..."
    
    # Create ZIP file
    cd "lambda_assets/$asset_dir"
    zip -r "../../${function_name}-update.zip" . -q
    cd ../..
    
    # Update Lambda function code
    aws lambda update-function-code \
        --function-name "$function_name" \
        --zip-file "fileb://${function_name}-update.zip" \
        --region us-east-1
    
    # Wait for update to complete
    aws lambda wait function-updated --function-name "$function_name" --region us-east-1
    
    # Clean up ZIP file
    rm -f "${function_name}-update.zip"
    
    echo "✅ $function_name updated successfully"
}

# Update all Lambda functions
update_lambda_code "oscar-supervisor-agent-cdk" "oscar-agent"
update_lambda_code "oscar-communication-handler-cdk" "oscar-agent"
update_lambda_code "oscar-jenkins-agent-cdk" "jenkins"
update_lambda_code "oscar-metrics-agent-cdk" "metrics"

# Clean up assets
rm -rf lambda_assets

echo ""
echo "🎉 All Lambda functions updated with dependencies!"
echo ""
echo "🧪 Test the API Gateway:"
echo "curl -X POST https://ggjmr44j4i.execute-api.us-east-1.amazonaws.com/prod/slack/events \\"
echo "  -H \"Content-Type: application/json\" \\"
echo "  -d '{\"type\": \"url_verification\", \"challenge\": \"test_challenge_123\"}'"