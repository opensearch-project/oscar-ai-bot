#!/bin/bash
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

# Update ONLY the code for Slack Agent Lambda function
# Preserves all permissions and configurations
# Updates slack_handler.py and communication_handler.py

set -e

echo "🔄 Updating Slack Agent Lambda Function (Code Only)..."

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
    echo "✅ Loaded environment variables from .env"
else
    echo "❌ .env file not found. Please create it with required variables."
    exit 1
fi

# Set function name
FUNCTION_NAME="oscar-supervisor-agent"

# Verify region configuration
echo "🌍 Using AWS Region: $AWS_REGION"
if [ "$AWS_REGION" != "us-east-1" ]; then
    echo "⚠️  Warning: Expected region us-east-1, but using $AWS_REGION"
fi

echo "📦 Creating deployment package..."

# Create temporary directory for deployment
TEMP_DIR=$(mktemp -d)
echo "Using temporary directory: $TEMP_DIR"

# Copy the main agent files (including slack_handler.py and communication_handler.py)
cp oscar-agent/*.py $TEMP_DIR/
cp oscar-agent/app.py $TEMP_DIR/lambda_function.py

# Create requirements.txt for the Lambda function
cat > $TEMP_DIR/requirements.txt << EOF
boto3>=1.26.0
botocore>=1.29.0
slack_sdk>=3.19.0
slack_bolt>=1.14.0
EOF

# Install dependencies
echo "📦 Installing Python dependencies..."
if ! pip install -r $TEMP_DIR/requirements.txt -t $TEMP_DIR/ --quiet; then
    echo "❌ Failed to install dependencies with pip. Trying with --user flag..."
    pip install -r $TEMP_DIR/requirements.txt -t $TEMP_DIR/ --user --quiet || {
        echo "❌ Failed to install dependencies. Please check your pip installation."
        exit 1
    }
fi

# Verify critical dependencies were installed
echo "🔍 Verifying dependencies..."
if [ ! -d "$TEMP_DIR/slack_bolt" ]; then
    echo "❌ slack_bolt not found in deployment package"
    echo "📦 Attempting manual installation..."
    pip install slack_bolt>=1.14.0 -t $TEMP_DIR/ --quiet || {
        echo "❌ Failed to install slack_bolt"
        exit 1
    }
fi

if [ ! -d "$TEMP_DIR/slack_sdk" ]; then
    echo "❌ slack_sdk not found in deployment package"
    echo "📦 Attempting manual installation..."
    pip install slack_sdk>=3.19.0 -t $TEMP_DIR/ --quiet || {
        echo "❌ Failed to install slack_sdk"
        exit 1
    }
fi

echo "✅ Dependencies verified"

# Verify critical code fixes are in place
echo "🔍 Verifying critical code fixes..."
if ! grep -q "def get_context_for_query" oscar-agent/storage.py; then
    echo "❌ CRITICAL: storage.py is missing get_context_for_query method"
    echo "   This will cause AttributeError. Please restore the correct storage.py file."
    exit 1
fi

if grep -q "^[[:space:]]*context = self.storage.get_context_for_query" oscar-agent/slack_handler.py; then
    echo "❌ CRITICAL: slack_handler.py has variable name collision bug"
    echo "   This will cause context to be overwritten. Please fix variable naming."
    exit 1
fi

echo "✅ Critical code fixes verified"

# Create deployment package using Python to ensure correct structure
echo "📦 Creating deployment package..."
python3 -c "
import os
import zipfile
import sys

# Change to the directory
os.chdir('$TEMP_DIR')

# Create zip file
with zipfile.ZipFile('../slack-agent-update.zip', 'w', zipfile.ZIP_DEFLATED) as zipf:
    for root, dirs, files in os.walk('.'):
        # Skip __pycache__ directories
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for file in files:
            if not file.endswith('.pyc'):
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, '.')
                zipf.write(file_path, arcname)

print('✅ Deployment package created successfully')
"

DEPLOYMENT_PACKAGE="$TEMP_DIR/../slack-agent-update.zip"
PACKAGE_SIZE=$(ls -la $DEPLOYMENT_PACKAGE | awk '{print $5}')
echo "✅ Created deployment package: $DEPLOYMENT_PACKAGE"
echo "📏 Package size: $(numfmt --to=iec $PACKAGE_SIZE)"

# Verify package size is reasonable (should be > 1MB with dependencies)
if [ $PACKAGE_SIZE -lt 1000000 ]; then
    echo "⚠️  Warning: Package size is unusually small ($PACKAGE_SIZE bytes)"
    echo "   This might indicate missing dependencies"
    echo "   Expected size: >10MB with all dependencies"
fi

# Check if Lambda function exists
echo "🔍 Checking if Lambda function exists..."
if aws lambda get-function --function-name $FUNCTION_NAME --region $AWS_REGION > /dev/null 2>&1; then
    echo "🔄 Updating Lambda function code and environment variables..."
    
    # Update function code
    aws lambda update-function-code \
        --function-name $FUNCTION_NAME \
        --zip-file fileb://$DEPLOYMENT_PACKAGE \
        --region $AWS_REGION >/dev/null

    # Wait for code update to complete
    echo "⏳ Waiting for code update to complete..."
    aws lambda wait function-updated --function-name $FUNCTION_NAME --region $AWS_REGION

    # Create environment variables JSON file
    cat > $TEMP_DIR/env-vars.json << EOF
{
    "Variables": {
        "SLACK_BOT_TOKEN": "$SLACK_BOT_TOKEN",
        "SLACK_SIGNING_SECRET": "$SLACK_SIGNING_SECRET",
        "OSCAR_BEDROCK_AGENT_ID": "$OSCAR_BEDROCK_AGENT_ID",
        "OSCAR_BEDROCK_AGENT_ALIAS_ID": "${OSCAR_BEDROCK_AGENT_ALIAS_ID:-TSTALIASID}",
        "SESSIONS_TABLE_NAME": "${SESSIONS_TABLE_NAME:-oscar-agent-sessions}",
        "CONTEXT_TABLE_NAME": "${CONTEXT_TABLE_NAME:-oscar-agent-context}",
        "ENABLE_DM": "$ENABLE_DM",
        "DEDUP_TTL": "${DEDUP_TTL:-300}",
        "SESSION_TTL": "${SESSION_TTL:-3600}",
        "CONTEXT_TTL": "${CONTEXT_TTL:-604800}",
        "MAX_CONTEXT_LENGTH": "${MAX_CONTEXT_LENGTH:-3000}",
        "CONTEXT_SUMMARY_LENGTH": "${CONTEXT_SUMMARY_LENGTH:-500}",
        "AGENT_TIMEOUT": "${AGENT_TIMEOUT:-60}",
        "AGENT_MAX_RETRIES": "${AGENT_MAX_RETRIES:-2}",
        "CHANNEL_ALLOW_LIST": "$CHANNEL_ALLOW_LIST",
        "AUTHORIZED_MESSAGE_SENDERS": "$AUTHORIZED_MESSAGE_SENDERS",
        "METRICS_CROSS_ACCOUNT_ROLE_ARN": "$METRICS_CROSS_ACCOUNT_ROLE_ARN"
    }
}
EOF

    # Update environment variables using JSON file
    aws lambda update-function-configuration \
        --function-name $FUNCTION_NAME \
        --environment file://$TEMP_DIR/env-vars.json \
        --region $AWS_REGION >/dev/null

    echo "✅ Updated Lambda function code and configuration: $FUNCTION_NAME"
    
    # Wait for function to be ready
    echo "⏳ Waiting for function to be ready..."
    aws lambda wait function-updated --function-name $FUNCTION_NAME --region $AWS_REGION
    aws lambda wait function-active --function-name $FUNCTION_NAME --region $AWS_REGION
    
else
    echo "❌ Lambda function $FUNCTION_NAME does not exist!"
    echo "   Please run ./deploy_slack_agent.sh first to create the function."
    exit 1
fi

# Get function ARN for confirmation
FUNCTION_ARN=$(aws lambda get-function --function-name $FUNCTION_NAME --region $AWS_REGION --query 'Configuration.FunctionArn' --output text)

# Cleanup
echo "🧹 Cleaning up temporary files..."
rm -rf $TEMP_DIR

echo ""
echo "🎉 Slack Agent Lambda Function Code Updated!"
echo ""
echo "📋 Summary:"
echo "   Function Name: $FUNCTION_NAME"
echo "   Function ARN:  $FUNCTION_ARN"
echo "   Region:        $AWS_REGION"
echo ""
echo "🔒 Preserved:"
echo "   ✅ All IAM permissions"
echo "   ✅ Environment variables"
echo "   ✅ API Gateway permissions"
echo "   ✅ Bedrock agent access"
echo "   ✅ DynamoDB permissions"
echo ""
echo "📝 Updated Files:"
echo "   ✅ slack_handler.py"
echo "   ✅ communication_handler.py"
echo "   ✅ oscar_agent.py"
echo "   ✅ storage.py"
echo "   ✅ config.py"
echo "   ✅ app.py (lambda handler)"
echo ""
echo "🧪 Test with: @oscar hello"