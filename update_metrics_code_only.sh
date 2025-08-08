#!/bin/bash

set -e

echo "🔄 Updating Metrics Lambda Code (Preserving Permissions)"
echo "========================================================"

# Load environment
if [ -f ".env" ]; then
    while IFS= read -r line; do
        [[ $line =~ ^[[:space:]]*# ]] && continue
        [[ -z $line ]] && continue
        export "$line"
    done < .env
fi

# Create deployment package
echo "📦 Creating deployment package..."
rm -rf new-package new-package.zip
mkdir new-package

# Install dependencies
pip install boto3 requests -t new-package/ --quiet

# Copy source code
cp metrics/*.py new-package/

# Create zip
cd new-package && zip -r ../new-package.zip . -q && cd ..
rm -rf new-package

# Update functions (preserving permissions and connections)
AGENT_FUNCTIONS=(
    "oscar-test-metrics-agent-new"
    "oscar-build-metrics-agent-new"
    "oscar-release-metrics-agent-new"
)

for FUNCTION_NAME in "${AGENT_FUNCTIONS[@]}"; do
    echo "🔄 Updating $FUNCTION_NAME code..."
    
    # Update function code only
    aws lambda update-function-code \
        --function-name "$FUNCTION_NAME" \
        --zip-file fileb://new-package.zip \
        --region "$AWS_REGION" >/dev/null
    
    echo "✅ $FUNCTION_NAME code updated"
    
    # Wait for update to complete
    aws lambda wait function-updated --function-name "$FUNCTION_NAME" --region "$AWS_REGION"
done

echo "✅ All function code updated (permissions preserved)"

# Cleanup
rm -f new-package.zip

echo ""
echo "🧪 Test the new response format:"
echo "aws lambda invoke --function-name oscar-test-metrics-agent-new --payload '{\"parameters\": [{\"name\": \"metric_type\", \"value\": \"execution\"}]}' --cli-binary-format raw-in-base64-out --region $AWS_REGION test.json && cat test.json | jq ."