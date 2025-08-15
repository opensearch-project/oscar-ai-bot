#!/bin/bash
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

# Deploy OSCAR Main Agent Lambda Function
# FULL DEPLOYMENT - Creates function, role, and permissions

set -e

echo "🚀 Deploying OSCAR Main Agent Lambda Function..."

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
    echo "✅ Loaded environment variables from .env"
else
    echo "❌ .env file not found. Please create it with required variables."
    exit 1
fi

# Validate required environment variables
required_vars=("SLACK_BOT_TOKEN" "SLACK_SIGNING_SECRET" "OSCAR_BEDROCK_AGENT_ID" "AWS_REGION")
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "❌ Required environment variable $var is not set"
        exit 1
    fi
done

# Set default values
AWS_REGION=${AWS_REGION:-us-east-1}
FUNCTION_NAME="oscar-supervisor-agent"
LAMBDA_ROLE_NAME="oscar-supervisor-lambda-role"

# Verify region configuration
echo "🌍 Using AWS Region: $AWS_REGION"
if [ "$AWS_REGION" != "us-east-1" ]; then
    echo "⚠️  Warning: Expected region us-east-1, but using $AWS_REGION"
fi

echo "📦 Creating deployment package..."

# Create temporary directory for deployment
TEMP_DIR=$(mktemp -d)
echo "Using temporary directory: $TEMP_DIR"

# Copy all OSCAR agent files
cp oscar-agent/*.py $TEMP_DIR/
cp oscar-agent/app.py $TEMP_DIR/lambda_function.py

# Create comprehensive requirements.txt for the Lambda function
cat > $TEMP_DIR/requirements.txt << EOF
# Core AWS and Slack dependencies
boto3>=1.34.0
botocore>=1.34.0
slack_sdk>=3.19.0
slack_bolt>=1.18.0

# HTTP and networking
requests>=2.31.0
urllib3>=2.0.0

# Additional dependencies for enhanced functionality
opensearch-py==2.4.2
aws-requests-auth==0.4.3

# Ensure we have all transitive dependencies
certifi>=2023.7.22
charset-normalizer>=3.0.0
idna>=3.0.0
python-dateutil>=2.8.0
jmespath>=1.0.0
s3transfer>=0.6.0
six>=1.16.0
EOF

# Install dependencies with upgrade flag to ensure latest compatible versions
echo "📦 Installing Python dependencies..."
if ! pip install -r $TEMP_DIR/requirements.txt -t $TEMP_DIR/ --upgrade --quiet; then
    echo "❌ Failed to install dependencies with pip. Trying alternative approach..."
    # Try installing each dependency individually
    while IFS= read -r line; do
        if [[ $line =~ ^[a-zA-Z] ]]; then
            echo "  Installing: $line"
            pip install "$line" -t $TEMP_DIR/ --upgrade --quiet || {
                echo "❌ Failed to install $line"
                exit 1
            }
        fi
    done < $TEMP_DIR/requirements.txt
fi

# Verify critical dependencies were installed
echo "🔍 Verifying dependencies..."
CRITICAL_DEPS=("slack_bolt" "slack_sdk" "boto3" "botocore" "requests" "opensearchpy")
MISSING_DEPS=()

for dep in "${CRITICAL_DEPS[@]}"; do
    if [ ! -d "$TEMP_DIR/$dep" ] && [ ! -d "$TEMP_DIR/${dep//_/-}" ]; then
        MISSING_DEPS+=("$dep")
    fi
done

if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    echo "❌ Missing dependencies: ${MISSING_DEPS[*]}"
    echo "📦 Attempting manual installation..."
    
    for dep in "${MISSING_DEPS[@]}"; do
        case $dep in
            "slack_bolt")
                pip install slack_bolt>=1.18.0 -t $TEMP_DIR/ --upgrade --quiet || {
                    echo "❌ Failed to install slack_bolt"
                    exit 1
                }
                ;;
            "slack_sdk")
                pip install slack_sdk>=3.19.0 -t $TEMP_DIR/ --upgrade --quiet || {
                    echo "❌ Failed to install slack_sdk"
                    exit 1
                }
                ;;
            "opensearchpy")
                pip install opensearch-py==2.4.2 -t $TEMP_DIR/ --upgrade --quiet || {
                    echo "❌ Failed to install opensearch-py"
                    exit 1
                }
                ;;
            *)
                pip install "$dep" -t $TEMP_DIR/ --upgrade --quiet || {
                    echo "❌ Failed to install $dep"
                    exit 1
                }
                ;;
        esac
    done
fi

echo "✅ Dependencies verified"

# List installed packages for debugging
echo "📋 Installed packages:"
ls -la $TEMP_DIR/ | grep "^d" | awk '{print $9}' | grep -E "^(slack|boto|requests|opensearch|urllib3|certifi)" | head -10

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
with zipfile.ZipFile('../oscar-agent-deploy.zip', 'w', zipfile.ZIP_DEFLATED) as zipf:
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

DEPLOYMENT_PACKAGE="$TEMP_DIR/../oscar-agent-deploy.zip"
PACKAGE_SIZE=$(ls -la $DEPLOYMENT_PACKAGE | awk '{print $5}')
echo "✅ Created deployment package: $DEPLOYMENT_PACKAGE"
echo "📏 Package size: $(numfmt --to=iec $PACKAGE_SIZE)"

# Verify package size is reasonable (should be > 10MB with dependencies)
if [ $PACKAGE_SIZE -lt 10000000 ]; then
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
        "dynamodb:PutItem",
        "dynamodb:GetItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
        "dynamodb:Scan"
      ],
      "Resource": [
        "arn:aws:dynamodb:*:*:table/oscar-agent-context",
        "arn:aws:dynamodb:*:*:table/oscar-agent-sessions"
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
        --policy-name "OSCARAgentPolicy" \
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

# Check if Lambda function exists
echo "🔍 Checking if Lambda function exists..."
if aws lambda get-function --function-name $FUNCTION_NAME --region $AWS_REGION > /dev/null 2>&1; then
    echo "📝 Updating existing Lambda function..."
    
    # Update function code
    aws lambda update-function-code \
        --function-name $FUNCTION_NAME \
        --zip-file fileb://$DEPLOYMENT_PACKAGE \
        --region $AWS_REGION >/dev/null

    # Wait for code update to complete
    echo "⏳ Waiting for code update to complete..."
    aws lambda wait function-updated --function-name $FUNCTION_NAME --region $AWS_REGION

    # Update function configuration
    aws lambda update-function-configuration \
        --function-name $FUNCTION_NAME \
        --runtime python3.12 \
        --handler lambda_function.lambda_handler \
        --timeout 150 \
        --memory-size 512 \
        --environment file://$TEMP_DIR/env-vars.json \
        --region $AWS_REGION >/dev/null

    echo "✅ Updated Lambda function: $FUNCTION_NAME"
else
    echo "🆕 Creating new Lambda function..."
    
    aws lambda create-function \
        --function-name $FUNCTION_NAME \
        --runtime python3.12 \
        --role $ROLE_ARN \
        --handler lambda_function.lambda_handler \
        --zip-file fileb://$DEPLOYMENT_PACKAGE \
        --timeout 150 \
        --memory-size 512 \
        --environment file://$TEMP_DIR/env-vars.json \
        --region $AWS_REGION >/dev/null

    echo "✅ Created Lambda function: $FUNCTION_NAME"
fi

# Get function ARN
FUNCTION_ARN=$(aws lambda get-function --function-name $FUNCTION_NAME --region $AWS_REGION --query 'Configuration.FunctionArn' --output text)
echo "📋 Lambda function ARN: $FUNCTION_ARN"

# Wait for function to be ready
echo "⏳ Waiting for function to be ready..."
aws lambda wait function-updated --function-name $FUNCTION_NAME --region $AWS_REGION
aws lambda wait function-active --function-name $FUNCTION_NAME --region $AWS_REGION

# Test the function
echo "🧪 Testing Lambda function..."
cat > $TEMP_DIR/test-event.json << 'EOF'
{
  "test": "connectivity"
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
echo "🎉 OSCAR Main Agent Lambda Function Deployment Complete!"
echo ""
echo "📋 Summary:"
echo "   Function Name: $FUNCTION_NAME"
echo "   Function ARN:  $FUNCTION_ARN"
echo "   IAM Role:      $ROLE_ARN"
echo "   Region:        $AWS_REGION"
echo ""
echo "📝 Next Steps:"
echo "   1. Setup DynamoDB tables: python setup_dynamodb_tables.py"
echo "   2. Configure API Gateway for Slack webhook"
echo "   3. Update Slack app with webhook URL"
echo "   4. Test with: @oscar hello"
echo ""
echo "🧪 Test with: @oscar hello"