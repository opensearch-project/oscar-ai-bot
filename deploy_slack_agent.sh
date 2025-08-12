#!/bin/bash
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

# Deploy OSCAR Slack Agent Lambda Function
# Handles slack_handler.py and related Slack bot functionality

set -e

echo "🤖 Deploying OSCAR Slack Agent Lambda Function..."

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
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

echo "📦 Creating deployment package..."

# Create temporary directory for deployment
TEMP_DIR=$(mktemp -d)
echo "Using temporary directory: $TEMP_DIR"

# Copy the main agent files
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
zip -r ../slack-agent.zip . -x "*.pyc" "*/__pycache__/*" -q
cd - > /dev/null

DEPLOYMENT_PACKAGE="$TEMP_DIR/../slack-agent.zip"
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

# Prepare environment variables (AWS_REGION is reserved and automatically set by Lambda)
ENV_VARS="{SLACK_BOT_TOKEN=$SLACK_BOT_TOKEN,SLACK_SIGNING_SECRET=$SLACK_SIGNING_SECRET,OSCAR_BEDROCK_AGENT_ID=$OSCAR_BEDROCK_AGENT_ID,OSCAR_BEDROCK_AGENT_ALIAS_ID=${OSCAR_BEDROCK_AGENT_ALIAS_ID:-TSTALIASID},SESSIONS_TABLE_NAME=${SESSIONS_TABLE_NAME:-oscar-sessions-v2},CONTEXT_TABLE_NAME=${CONTEXT_TABLE_NAME:-oscar-context},ENABLE_DM=$ENABLE_DM,DEDUP_TTL=${DEDUP_TTL:-300},SESSION_TTL=${SESSION_TTL:-3600},CONTEXT_TTL=${CONTEXT_TTL:-604800},MAX_CONTEXT_LENGTH=${MAX_CONTEXT_LENGTH:-3000},CONTEXT_SUMMARY_LENGTH=${CONTEXT_SUMMARY_LENGTH:-500},AGENT_TIMEOUT=${AGENT_TIMEOUT:-60},AGENT_MAX_RETRIES=${AGENT_MAX_RETRIES:-2}}"

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
        --timeout 60 \
        --memory-size 512 \
        --environment Variables="$ENV_VARS" \
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
        --timeout 60 \
        --memory-size 512 \
        --environment Variables="$ENV_VARS" \
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