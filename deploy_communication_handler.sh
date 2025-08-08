#!/bin/bash
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

# Deploy OSCAR Communication Handler Lambda Function

set -e

echo "🚀 Deploying OSCAR Communication Handler Lambda Function..."

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
    echo "✅ Loaded environment variables from .env"
else
    echo "❌ .env file not found. Please create it with required variables."
    exit 1
fi

# Validate required environment variables
required_vars=("SLACK_BOT_TOKEN" "AWS_REGION")
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "❌ Required environment variable $var is not set"
        exit 1
    fi
done

# Set default values
AWS_REGION=${AWS_REGION:-us-east-1}
FUNCTION_NAME="oscar-communication-handler"
LAMBDA_ROLE_NAME="oscar-communication-handler-role"

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

# Install dependencies if requirements exist
if [ -f $TEMP_DIR/requirements.txt ]; then
    echo "📦 Installing Python dependencies..."
    pip install -r $TEMP_DIR/requirements.txt -t $TEMP_DIR/
fi

# Create deployment package
cd $TEMP_DIR
zip -r ../communication-handler.zip . -x "*.pyc" "*/__pycache__/*"
cd - > /dev/null

DEPLOYMENT_PACKAGE="$TEMP_DIR/../communication-handler.zip"
echo "✅ Created deployment package: $DEPLOYMENT_PACKAGE"

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

    # Create and attach custom policy for Bedrock access
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
        --policy-name "CommunicationHandlerPolicy" \
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
        --runtime python3.9 \
        --handler lambda_function.lambda_handler \
        --timeout 30 \
        --memory-size 256 \
        --environment Variables="{SLACK_BOT_TOKEN=$SLACK_BOT_TOKEN}" \
        --region $AWS_REGION

    echo "✅ Updated Lambda function: $FUNCTION_NAME"
else
    echo "🆕 Creating new Lambda function..."
    
    aws lambda create-function \
        --function-name $FUNCTION_NAME \
        --runtime python3.9 \
        --role $ROLE_ARN \
        --handler lambda_function.lambda_handler \
        --zip-file fileb://$DEPLOYMENT_PACKAGE \
        --timeout 30 \
        --memory-size 256 \
        --environment Variables="{SLACK_BOT_TOKEN=$SLACK_BOT_TOKEN}" \
        --region $AWS_REGION

    echo "✅ Created Lambda function: $FUNCTION_NAME"
fi

# Get function ARN
FUNCTION_ARN=$(aws lambda get-function --function-name $FUNCTION_NAME --region $AWS_REGION --query 'Configuration.FunctionArn' --output text)
echo "📋 Lambda function ARN: $FUNCTION_ARN"

# Add permission for Bedrock to invoke the Lambda function
echo "🔐 Adding Bedrock invoke permission..."
aws lambda add-permission \
    --function-name $FUNCTION_NAME \
    --statement-id "bedrock-invoke-permission" \
    --action lambda:InvokeFunction \
    --principal bedrock.amazonaws.com \
    --region $AWS_REGION \
    2>/dev/null || echo "⚠️  Permission may already exist"

# Test the function
echo "🧪 Testing Lambda function..."
cat > $TEMP_DIR/test-event.json << 'EOF'
{
  "actionGroup": "communication-orchestration",
  "apiPath": "/send_automated_message",
  "httpMethod": "POST",
  "parameters": [
    {
      "name": "query",
      "value": "send missing release notes message to riley-needs-to-lock-in channel"
    }
  ]
}
EOF

echo "📤 Invoking test..."
aws lambda invoke \
    --function-name $FUNCTION_NAME \
    --payload file://$TEMP_DIR/test-event.json \
    --region $AWS_REGION \
    $TEMP_DIR/response.json

echo "📥 Test response:"
cat $TEMP_DIR/response.json | jq '.' 2>/dev/null || cat $TEMP_DIR/response.json

# Cleanup
echo "🧹 Cleaning up temporary files..."
rm -rf $TEMP_DIR

echo ""
echo "🎉 Communication Handler Lambda Function Deployment Complete!"
echo ""
echo "📋 Summary:"
echo "   Function Name: $FUNCTION_NAME"
echo "   Function ARN:  $FUNCTION_ARN"
echo "   IAM Role:      $ROLE_ARN"
echo "   Region:        $AWS_REGION"
echo ""
echo "📝 Next Steps:"
echo "   1. Update OSCAR supervisor agent with new action group"
echo "   2. Configure function schema in Bedrock console"
echo "   3. Test with authorized Slack users"
echo "   4. Monitor CloudWatch logs for any issues"
echo ""
echo "📖 For detailed configuration instructions, see:"
echo "   docs/COMMUNICATION_ORCHESTRATION_AGENT_CONFIG.md"