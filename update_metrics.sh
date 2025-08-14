#!/bin/bash
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

# Update ONLY the code for metrics Lambda functions
# Preserves all permissions and configurations

set -e

echo "🔄 Updating Metrics Lambda Functions (Code Only)..."

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
    echo "✅ Loaded environment variables from .env"
else
    echo "❌ .env file not found. Please create it with required variables."
    exit 1
fi

# Verify region configuration
echo "🌍 Using AWS Region: $AWS_REGION"
if [ "$AWS_REGION" != "us-east-1" ]; then
    echo "⚠️  Warning: Expected region us-east-1, but using $AWS_REGION"
fi

# Create deployment package
echo "📦 Creating deployment package..."
rm -rf update-package update-package.zip
mkdir update-package

# Install dependencies (only boto3 and requests)
pip install boto3 requests -t update-package/ --quiet

# Copy source code
cp metrics/*.py update-package/

# Create zip
cd update-package && zip -r ../update-package.zip . -q && cd ..
rm -rf update-package

# Update all agent functions (CODE ONLY)
AGENT_FUNCTIONS=(
    "oscar-test-metrics-agent-new"
    "oscar-build-metrics-agent-new"
    "oscar-release-metrics-agent-new"
    "oscar-deployment-metrics-agent-new"
)

for FUNCTION_NAME in "${AGENT_FUNCTIONS[@]}"; do
    echo "🔄 Updating code for $FUNCTION_NAME..."
    
    # Update ONLY function code - preserves all permissions and configurations
    aws lambda update-function-code \
        --function-name "$FUNCTION_NAME" \
        --zip-file fileb://update-package.zip \
        --region "$AWS_REGION" >/dev/null
    
    echo "✅ $FUNCTION_NAME code updated"
    
    # Wait for function to be ready
    aws lambda wait function-updated --function-name "$FUNCTION_NAME" --region "$AWS_REGION"
done

echo "⏳ Waiting for all functions to be ready..."
for FUNCTION_NAME in "${AGENT_FUNCTIONS[@]}"; do
    aws lambda wait function-active --function-name "$FUNCTION_NAME" --region "$AWS_REGION"
done

# Cleanup
rm -f update-package.zip

echo ""
echo "✅ All metrics functions updated successfully!"
echo ""
echo "📋 Updated Functions:"
for FUNCTION_NAME in "${AGENT_FUNCTIONS[@]}"; do
    echo "   ✅ $FUNCTION_NAME"
done
echo ""
echo "🔒 Preserved:"
echo "   ✅ All IAM permissions"
echo "   ✅ Environment variables"
echo "   ✅ VPC configurations"
echo "   ✅ Bedrock agent permissions"
echo ""
echo "🧪 Test command:"
echo "aws lambda invoke --function-name oscar-build-metrics-agent-new --payload '{\"function\": \"get_build_metrics\"}' --cli-binary-format raw-in-base64-out --region $AWS_REGION test.json && cat test.json | jq ."