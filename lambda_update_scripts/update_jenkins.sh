#!/bin/bash
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

# Update Jenkins Lambda function code while preserving permissions
# This is the safe way to update your Jenkins deployment without losing configurations

set -e

# Load environment variables from .env file
if [ -f ".env" ]; then
    echo "📋 Loading environment variables from .env file..."
    set -a  # automatically export all variables
    source .env
    set +a  # stop automatically exporting
else
    echo "⚠️  Warning: .env file not found, using system environment variables"
fi

echo "🔧 Updating Jenkins Lambda Function (Code Only)..."
echo "================================================"

# Set Jenkins function name (with fallback to default)
JENKINS_FUNCTION_NAME=${JENKINS_LAMBDA_FUNCTION_NAME:-oscar-jenkins-agent}

echo ""
echo "📋 Jenkins Update Configuration:"
echo "   Function Name: $JENKINS_FUNCTION_NAME"
echo "   AWS Region: $AWS_REGION"
echo "   Mode: Code update only (preserves all permissions)"
echo ""

# Verify function exists
echo "🔍 Verifying Lambda function exists..."
if ! aws lambda get-function --function-name "$JENKINS_FUNCTION_NAME" --region "$AWS_REGION" > /dev/null 2>&1; then
    echo "❌ Error: Lambda function '$JENKINS_FUNCTION_NAME' does not exist"
    echo "💡 Run the full deployment script first"
    exit 1
fi
echo "✅ Lambda function exists"
echo ""

# Create deployment package
echo "📦 Creating Jenkins deployment package..."
cd jenkins

# Create a temporary directory for the deployment package
TEMP_DIR=$(mktemp -d)
echo "   Using temp directory: $TEMP_DIR"

# Copy all necessary files for the lambda function
echo "   Copying Python files..."
cp *.py "$TEMP_DIR/"

echo "   Copying requirements.txt..."
cp requirements.txt "$TEMP_DIR/"

# Install dependencies
echo "   Installing dependencies..."
pip install -r requirements.txt -t "$TEMP_DIR/" --quiet

# Copy schemas directory (contains action group definitions)
if [ -d "schemas" ]; then
    echo "   Copying schemas directory..."
    cp -r schemas "$TEMP_DIR/"
fi

# Copy any JSON configuration files if they exist
if ls *.json 1> /dev/null 2>&1; then
    echo "   Copying JSON configuration files..."
    cp *.json "$TEMP_DIR/"
fi

echo "   Files copied to deployment package:"
ls -la "$TEMP_DIR/"

# Create the zip file
cd "$TEMP_DIR"
zip -r jenkins-deployment.zip .
echo "✅ Created deployment package"

# Update the Lambda function
echo ""
echo "🚀 Updating Lambda function code..."
aws lambda update-function-code \
    --function-name "$JENKINS_FUNCTION_NAME" \
    --zip-file fileb://jenkins-deployment.zip \
    --region "$AWS_REGION"

if [ $? -eq 0 ]; then
    echo "✅ Jenkins Lambda function updated successfully"
else
    echo "❌ Failed to update Jenkins Lambda function"
    exit 1
fi

# Clean up
cd - > /dev/null
rm -rf "$TEMP_DIR"
echo "🧹 Cleaned up temporary files"

echo ""
echo "🎉 Jenkins Lambda Function Updated!"
echo "=================================="
echo ""
echo "📋 Updated Function:"
echo "   ✅ $JENKINS_FUNCTION_NAME"
echo ""
echo "🔒 Preserved (NOT touched):"
echo "   ✅ IAM roles and permissions"
echo "   ✅ Environment variables"
echo "   ✅ VPC configurations"
echo "   ✅ Bedrock agent permissions"
echo ""
echo "🧪 Test Commands:"
echo "   # Test Jenkins connection"
echo "   aws lambda invoke --function-name $JENKINS_FUNCTION_NAME --payload '{\"function\": \"test_connection\"}' --cli-binary-format raw-in-base64-out --region $AWS_REGION test.json && cat test.json"
echo ""
echo "   # Get job info (safe, no execution)"
echo "   aws lambda invoke --function-name $JENKINS_FUNCTION_NAME --payload '{\"function\": \"get_job_info\", \"parameters\": [{\"name\": \"job_name\", \"value\": \"docker-scan\"}]}' --cli-binary-format raw-in-base64-out --region $AWS_REGION test.json && cat test.json"
echo ""
echo "📖 For troubleshooting, see: jenkins/JENKINS_INTEGRATION_GUIDE.md"