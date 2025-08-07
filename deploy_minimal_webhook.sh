#!/bin/bash
# Deploy minimal webhook handler
set -e

echo "🔧 Deploying minimal webhook handler"

# Load environment
if [ -f ".env" ]; then
    while IFS= read -r line; do
        [[ $line =~ ^[[:space:]]*# ]] && continue
        [[ -z $line ]] && continue
        export "$line"
    done < .env
fi

# Create minimal package
rm -rf minimal-package minimal-package.zip
mkdir minimal-package
cp oscar-agent/webhook_handler.py minimal-package/lambda_function.py

cd minimal-package && zip -r ../minimal-package.zip . -q && cd ..
rm -rf minimal-package

# Update supervisor function code and handler
aws lambda update-function-code \
    --function-name oscar-supervisor-agent \
    --zip-file fileb://minimal-package.zip \
    --region "$AWS_REGION" >/dev/null

aws lambda wait function-updated --function-name oscar-supervisor-agent --region "$AWS_REGION"

# Update handler to point to lambda_function.lambda_handler
aws lambda update-function-configuration \
    --function-name oscar-supervisor-agent \
    --handler lambda_function.lambda_handler \
    --region "$AWS_REGION" >/dev/null

aws lambda wait function-updated --function-name oscar-supervisor-agent --region "$AWS_REGION"

rm -f minimal-package.zip

echo "✅ Minimal webhook handler deployed"
echo "🧪 Test webhook URL now"
echo ""
echo "To restore full handler:"
echo "./update_lambdas.sh"