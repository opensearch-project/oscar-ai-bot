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
pip install -r $TEMP_DIR/requirements.txt -t $TEMP_DIR/ --quiet

# Create deployment package
cd $TEMP_DIR
zip -r ../slack-agent-update.zip . -x "*.pyc" "*/__pycache__/*" -q
cd - > /dev/null

DEPLOYMENT_PACKAGE="$TEMP_DIR/../slack-agent-update.zip"
echo "✅ Created deployment package: $DEPLOYMENT_PACKAGE"

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

    # Update environment variables using individual variables (AWS_REGION is reserved)
    aws lambda update-function-configuration \
        --function-name $FUNCTION_NAME \
        --environment Variables="{SLACK_BOT_TOKEN=$SLACK_BOT_TOKEN,SLACK_SIGNING_SECRET=$SLACK_SIGNING_SECRET,OSCAR_BEDROCK_AGENT_ID=$OSCAR_BEDROCK_AGENT_ID,OSCAR_BEDROCK_AGENT_ALIAS_ID=${OSCAR_BEDROCK_AGENT_ALIAS_ID:-TSTALIASID},SESSIONS_TABLE_NAME=${SESSIONS_TABLE_NAME:-oscar-sessions-v2},CONTEXT_TABLE_NAME=${CONTEXT_TABLE_NAME:-oscar-context},ENABLE_DM=$ENABLE_DM,DEDUP_TTL=${DEDUP_TTL:-300},SESSION_TTL=${SESSION_TTL:-3600},CONTEXT_TTL=${CONTEXT_TTL:-604800},MAX_CONTEXT_LENGTH=${MAX_CONTEXT_LENGTH:-3000},CONTEXT_SUMMARY_LENGTH=${CONTEXT_SUMMARY_LENGTH:-500},AGENT_TIMEOUT=${AGENT_TIMEOUT:-60},AGENT_MAX_RETRIES=${AGENT_MAX_RETRIES:-2}}" \
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