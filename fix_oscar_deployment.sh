#!/bin/bash
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

# OSCAR Emergency Fix Script
# Use this if OSCAR stops working and you need to apply all critical fixes

set -e

echo "🚨 OSCAR Emergency Fix Script"
echo "This script applies all critical fixes that were discovered during debugging"
echo ""

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

# Verify critical environment variables
echo "🔍 Verifying critical environment variables..."
if [ "$CONTEXT_TABLE_NAME" != "oscar-agent-context" ]; then
    echo "❌ CONTEXT_TABLE_NAME must be 'oscar-agent-context', found: $CONTEXT_TABLE_NAME"
    echo "   Please update your .env file"
    exit 1
fi

if [ "$SESSIONS_TABLE_NAME" != "oscar-agent-sessions" ]; then
    echo "❌ SESSIONS_TABLE_NAME must be 'oscar-agent-sessions', found: $SESSIONS_TABLE_NAME"
    echo "   Please update your .env file"
    exit 1
fi

echo "✅ Environment variables are correct"

# Check if DynamoDB tables exist
echo "🔍 Checking DynamoDB tables..."
if ! aws dynamodb describe-table --table-name oscar-agent-context --region $AWS_REGION > /dev/null 2>&1; then
    echo "❌ Table oscar-agent-context does not exist"
    echo "   Running table setup..."
    python setup_dynamodb_tables.py
fi

if ! aws dynamodb describe-table --table-name oscar-agent-sessions --region $AWS_REGION > /dev/null 2>&1; then
    echo "❌ Table oscar-agent-sessions does not exist"
    echo "   Running table setup..."
    python setup_dynamodb_tables.py
fi

echo "✅ DynamoDB tables verified"

# Fix IAM permissions
echo "🔧 Fixing IAM permissions..."
cat > /tmp/dynamodb-policy.json << EOF
{
    "Version": "2012-10-17",
    "Statement": [
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
                "arn:aws:dynamodb:us-east-1:*:table/oscar-agent-sessions",
                "arn:aws:dynamodb:us-east-1:*:table/oscar-agent-context"
            ]
        }
    ]
}
EOF

aws iam put-role-policy --role-name oscar-supervisor-lambda-role --policy-name DynamoDBAccess --policy-document file:///tmp/dynamodb-policy.json --region $AWS_REGION
rm /tmp/dynamodb-policy.json
echo "✅ IAM permissions updated"

# Verify critical files have required methods
echo "🔍 Verifying critical code fixes..."
if ! grep -q "def get_context_for_query" oscar-agent/storage.py; then
    echo "❌ storage.py is missing get_context_for_query method"
    echo "   This is a critical bug - please restore the correct storage.py file"
    exit 1
fi

if grep -q "context = self.storage.get_context_for_query" oscar-agent/slack_handler.py; then
    echo "❌ slack_handler.py has variable name collision bug"
    echo "   This is a critical bug - please fix the variable naming"
    exit 1
fi

echo "✅ Critical code fixes verified"

# Deploy with manual method to ensure it works
echo "🚀 Deploying OSCAR with emergency method..."

# Create deployment directory
TEMP_DIR=$(mktemp -d)
echo "Using temporary directory: $TEMP_DIR"

# Copy files
cp oscar-agent/*.py $TEMP_DIR/
cp oscar-agent/app.py $TEMP_DIR/lambda_function.py

# Install dependencies
echo "📦 Installing dependencies..."
pip install boto3>=1.26.0 botocore>=1.29.0 slack_sdk>=3.19.0 slack_bolt>=1.14.0 -t $TEMP_DIR/ --quiet --upgrade

# Create deployment package with Python (ensures correct structure)
echo "📦 Creating deployment package..."
python3 -c "
import os
import zipfile

os.chdir('$TEMP_DIR')
with zipfile.ZipFile('../oscar-emergency-deploy.zip', 'w', zipfile.ZIP_DEFLATED) as zipf:
    for root, dirs, files in os.walk('.'):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for file in files:
            if not file.endswith('.pyc'):
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, '.')
                zipf.write(file_path, arcname)
"

# Deploy to Lambda
echo "🚀 Deploying to Lambda..."
aws lambda update-function-code --function-name oscar-supervisor-agent --zip-file fileb://$TEMP_DIR/../oscar-emergency-deploy.zip --region $AWS_REGION > /dev/null

# Wait for deployment to complete
echo "⏳ Waiting for deployment to complete..."
aws lambda wait function-updated --function-name oscar-supervisor-agent --region $AWS_REGION

# Cleanup
rm -rf $TEMP_DIR $TEMP_DIR/../oscar-emergency-deploy.zip

echo ""
echo "🎉 OSCAR Emergency Fix Complete!"
echo ""
echo "✅ Applied fixes:"
echo "   - Fixed DynamoDB table names and permissions"
echo "   - Deployed code with correct structure"
echo "   - Verified critical bug fixes are in place"
echo ""
echo "🧪 Test OSCAR now with: @oscar hello"
echo ""
echo "📋 If issues persist, check:"
echo "   - CloudWatch logs: aws logs describe-log-streams --log-group-name '/aws/lambda/oscar-supervisor-agent' --order-by LastEventTime --descending --max-items 1 --region us-east-1"
echo "   - Run debug script: python debug_context_preservation.py"
echo ""