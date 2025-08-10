#!/bin/bash
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

# Update ONLY the code for Communication Handler Lambda function
# Preserves all permissions and configurations

set -e

echo "🔄 Updating Communication Handler Lambda Function (Code Only)..."

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
    echo "✅ Loaded environment variables from .env"
else
    echo "❌ .env file not found. Please create it with required variables."
    exit 1
fi

# Set function name
FUNCTION_NAME="oscar-communication-handler"

echo "📦 Creating deployment package..."

# Create temporary directory for deployment
TEMP_DIR=$(mktemp -d)
echo "Using temporary directory: $TEMP_DIR"

# Copy the communication handler
cp oscar-agent/communication_handler.py $TEMP_DIR/lambda_function.py

# Create requirements.txt for the Lambda function
cat > $TEMP_DIR/requirements.txt << EOF
boto3>=1.26.0
botocore>=1.29.0
slack_sdk>=3.19.0
EOF

# Install dependencies
echo "📦 Installing Python dependencies..."
pip install -r $TEMP_DIR/requirements.txt -t $TEMP_DIR/ --quiet

# Create deployment package
cd $TEMP_DIR
zip -r ../communication-handler-update.zip . -x "*.pyc" "*/__pycache__/*" -q
cd - > /dev/null

DEPLOYMENT_PACKAGE="$TEMP_DIR/../communication-handler-update.zip"
echo "✅ Created deployment package: $DEPLOYMENT_PACKAGE"

# Check if Lambda function exists
echo "🔍 Checking if Lambda function exists..."
if aws lambda get-function --function-name $FUNCTION_NAME --region $AWS_REGION > /dev/null 2>&1; then
    echo "🔄 Updating Lambda function code (preserving all configurations)..."
    
    # Update ONLY function code - preserves all permissions, environment variables, and configurations
    aws lambda update-function-code \
        --function-name $FUNCTION_NAME \
        --zip-file fileb://$DEPLOYMENT_PACKAGE \
        --region $AWS_REGION >/dev/null

    echo "✅ Updated Lambda function code: $FUNCTION_NAME"
    
    # Wait for function to be ready
    echo "⏳ Waiting for function to be ready..."
    aws lambda wait function-updated --function-name $FUNCTION_NAME --region $AWS_REGION
    aws lambda wait function-active --function-name $FUNCTION_NAME --region $AWS_REGION
    
else
    echo "❌ Lambda function $FUNCTION_NAME does not exist!"
    echo "   Please run ./deploy_communication_handler.sh first to create the function."
    exit 1
fi

# Get function ARN for confirmation
FUNCTION_ARN=$(aws lambda get-function --function-name $FUNCTION_NAME --region $AWS_REGION --query 'Configuration.FunctionArn' --output text)

# Cleanup
echo "🧹 Cleaning up temporary files..."
rm -rf $TEMP_DIR

echo ""
echo "🎉 Communication Handler Lambda Function Code Updated!"
echo ""
echo "📋 Summary:"
echo "   Function Name: $FUNCTION_NAME"
echo "   Function ARN:  $FUNCTION_ARN"
echo "   Region:        $AWS_REGION"
echo ""
echo "🔒 Preserved:"
echo "   ✅ All IAM permissions"
echo "   ✅ Environment variables"
echo "   ✅ Bedrock agent permissions"
echo "   ✅ All existing configurations"
echo ""
echo "📝 Updated Files:"
echo "   ✅ communication_handler.py"
echo ""
echo "🧪 Test command:"
echo "aws lambda invoke --function-name $FUNCTION_NAME --payload '{\"actionGroup\": \"communication-orchestration\", \"apiPath\": \"/send_automated_message\"}' --cli-binary-format raw-in-base64-out --region $AWS_REGION test.json && cat test.json"