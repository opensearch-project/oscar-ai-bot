#!/bin/bash
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

# Deploy OSCAR Slack Agent Lambda Function
# Handles slack_handler.py and related Slack bot functionality

set -e

echo "🤖 Deploying OSCAR Slack Agent Lambda Function..."

# Load environment variables
if [ -f .env ]; then
    set -a  # automatically export all variables
    source .env
    set +a  # turn off automatic export
    echo "✅ Loaded environment variables from .env"
else
    echo "❌ .env file not found. Please create it with required variables."
    exit 1
fi

# Validate required environment variables
required_vars=("SLACK_BOT_TOKEN" "SLACK_SIGNING_SECRET" "AWS_REGION" "OSCAR_BEDROCK_AGENT_ID")
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "❌ Required environment variable $var is not set"
        exit 1
    fi
done

# Set default values
AWS_REGION=${AWS_REGION:-us-east-1}
FUNCTION_NAME="oscar-supervisor-agent"
LAMBDA_ROLE_NAME="oscar-supervisor-agent-role"

# Verify region configuration
echo "🌍 Using AWS Region: $AWS_REGION"
if [ "$AWS_REGION" != "us-east-1" ]; then
    echo "⚠️  Warning: Expected region us-east-1, but using $AWS_REGION"
fi

echo "📦 Creating deployment package..."

# Create temporary directory for deployment
TEMP_DIR=$(mktemp -d)
echo "Using temporary directory: $TEMP_DIR"

# Copy the main agent files
cp oscar-agent/*.py $TEMP_DIR/
cp oscar-agent/app.py $TEMP_DIR/lambda_function.py

# Copy the entire slack_handler package directory
if [ -d "oscar-agent/slack_handler" ]; then
    echo "📁 Copying slack_handler package..."
    cp -r oscar-agent/slack_handler $TEMP_DIR/
    echo "✅ Copied slack_handler package structure"
else
    echo "❌ slack_handler directory not found!"
    exit 1
fi

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

# Create deployment package
cd $TEMP_DIR
zip -r ../slack-agent.zip . -x "*.pyc" "*/__pycache__/*" -q
cd - > /dev/null

DEPLOYMENT_PACKAGE="$TEMP_DIR/../slack-agent.zip"
PACKAGE_SIZE=$(ls -la $DEPLOYMENT_PACKAGE | awk '{print $5}')
echo "✅ Created deployment package: $DEPLOYMENT_PACKAGE"
echo "📏 Package size: $(numfmt --to=iec $PACKAGE_SIZE)"

# Verify package size is reasonable (should be > 1MB with dependencies)
if [ $PACKAGE_SIZE -lt 1000000 ]; then
    echo "⚠️  Warning: Package size is unusually small ($PACKAGE_SIZE bytes)"
    echo "   This might indicate missing dependencies"
    echo "   Expected size: >10MB with all dependencies"
fi

# Check if IAM role exists, create if not
echo "🔐 Checking IAM role..."
if ! aws iam get-role --role-name $LAMBDA_ROLE_NAME --region $AWS_REGION > /dev/null 2>&1; then
    echo "Creating IAM role: $LAMBDA_ROLE_NAME"
    
    # Create trust policy
    cat > $TEMP_DIR/trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

    # Create the role
    aws iam create-role \
        --role-name $LAMBDA_ROLE_NAME \
        --assume-role-policy-document file://$TEMP_DIR/trust-policy.json \
        --region $AWS_REGION

    # Attach basic Lambda execution policy
    aws iam attach-role-policy \
        --role-name $LAMBDA_ROLE_NAME \
        --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole \
        --region $AWS_REGION

    # Create and attach custom policy for Bedrock and DynamoDB access
    cat > $TEMP_DIR/lambda-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeAgent",
        "bedrock:InvokeModel",
        "bedrock:GetAgent",
        "bedrock:GetKnowledgeBase"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
        "dynamodb:Scan"
      ],
      "Resource": [
        "arn:aws:dynamodb:${AWS_REGION}:*:table/oscar-sessions*",
        "arn:aws:dynamodb:${AWS_REGION}:*:table/oscar-context*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    }
  ]
}
EOF

    aws iam put-role-policy \
        --role-name $LAMBDA_ROLE_NAME \
        --policy-name "SlackAgentPolicy" \
        --policy-document file://$TEMP_DIR/lambda-policy.json \
        --region $AWS_REGION

    echo "✅ Created IAM role: $LAMBDA_ROLE_NAME"
    
    # Wait for role to be available
    echo "⏳ Waiting for IAM role to be available..."
    sleep 10
else
    echo "✅ IAM role already exists: $LAMBDA_ROLE_NAME"
fi

# Get role ARN
ROLE_ARN=$(aws iam get-role --role-name $LAMBDA_ROLE_NAME --region $AWS_REGION --query 'Role.Arn' --output text)
echo "📋 Using IAM role: $ROLE_ARN"

# Create environment variables JSON file
cat > $TEMP_DIR/env-vars.json << EOF
{
    "Variables": {
        "SLACK_BOT_TOKEN": "$SLACK_BOT_TOKEN",
        "SLACK_SIGNING_SECRET": "$SLACK_SIGNING_SECRET",
        "OSCAR_BEDROCK_AGENT_ID": "$OSCAR_BEDROCK_AGENT_ID",
        "OSCAR_BEDROCK_AGENT_ALIAS_ID": "${OSCAR_BEDROCK_AGENT_ALIAS_ID:-TSTALIASID}",
        "SESSIONS_TABLE_NAME": "${SESSIONS_TABLE_NAME:-oscar-sessions-v2}",
        "CONTEXT_TABLE_NAME": "${CONTEXT_TABLE_NAME:-oscar-context}",
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

# Check if Lambda function exists
echo "🔍 Checking if Lambda function exists..."
if aws lambda get-function --function-name $FUNCTION_NAME --region $AWS_REGION > /dev/null 2>&1; then
    echo "📝 Updating existing Lambda function..."
    
    # Update function code
    aws lambda update-function-code \
        --function-name $FUNCTION_NAME \
        --zip-file fileb://$DEPLOYMENT_PACKAGE \
        --region $AWS_REGION

    # Update function configuration
    aws lambda update-function-configuration \
        --function-name $FUNCTION_NAME \
        --runtime python3.12 \
        --handler lambda_function.lambda_handler \
        --timeout 60 \
        --memory-size 512 \
        --environment file://$TEMP_DIR/env-vars.json \
        --region $AWS_REGION

    echo "✅ Updated Lambda function: $FUNCTION_NAME"
else
    echo "🆕 Creating new Lambda function..."
    
    aws lambda create-function \
        --function-name $FUNCTION_NAME \
        --runtime python3.12 \
        --role $ROLE_ARN \
        --handler lambda_function.lambda_handler \
        --zip-file fileb://$DEPLOYMENT_PACKAGE \
        --timeout 60 \
        --memory-size 512 \
        --environment file://$TEMP_DIR/env-vars.json \
        --region $AWS_REGION

    echo "✅ Created Lambda function: $FUNCTION_NAME"
fi

# Get function ARN
FUNCTION_ARN=$(aws lambda get-function --function-name $FUNCTION_NAME --region $AWS_REGION --query 'Configuration.FunctionArn' --output text)
echo "📋 Lambda function ARN: $FUNCTION_ARN"

# Add permission for API Gateway to invoke the Lambda function
echo "🔐 Adding API Gateway invoke permission..."
aws lambda add-permission \
    --function-name $FUNCTION_NAME \
    --statement-id "api-gateway-invoke-permission" \
    --action lambda:InvokeFunction \
    --principal apigateway.amazonaws.com \
    --region $AWS_REGION \
    2>/dev/null || echo "⚠️  Permission may already exist"

# Cleanup
echo "🧹 Cleaning up temporary files..."
rm -rf $TEMP_DIR

echo ""
echo "🎉 Slack Agent Lambda Function Deployment Complete!"
echo ""
echo "📋 Summary:"
echo "   Function Name: $FUNCTION_NAME"
echo "   Function ARN:  $FUNCTION_ARN"
echo "   IAM Role:      $ROLE_ARN"
echo "   Region:        $AWS_REGION"
echo ""
echo "📝 Next Steps:"
echo "   1. Configure API Gateway to trigger this function"
echo "   2. Set up Slack webhook URL"
echo "   3. Test with @oscar hello"
echo "   4. Monitor CloudWatch logs for any issues"