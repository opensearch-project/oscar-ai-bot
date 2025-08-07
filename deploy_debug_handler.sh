#!/bin/bash
# Deploy debug handler temporarily
set -e

echo "🔧 Deploying debug handler"

# Load environment
if [ -f ".env" ]; then
    while IFS= read -r line; do
        [[ $line =~ ^[[:space:]]*# ]] && continue
        [[ -z $line ]] && continue
        export "$line"
    done < .env
fi

# Create minimal package
rm -rf debug-package debug-package.zip
mkdir debug-package
cp debug_handler.py debug-package/lambda_function.py

cd debug-package && zip -r ../debug-package.zip . -q && cd ..
rm -rf debug-package

# Update supervisor function with debug handler
aws lambda update-function-code \
    --function-name oscar-supervisor-agent \
    --zip-file fileb://debug-package.zip \
    --region "$AWS_REGION" >/dev/null

aws lambda wait function-updated --function-name oscar-supervisor-agent --region "$AWS_REGION"

rm -f debug-package.zip

echo "✅ Debug handler deployed"
echo "🧪 Now test the webhook URL in Slack"
echo ""
echo "To restore original handler:"
echo "./update_lambdas.sh"