#!/bin/bash

# Jenkins Agent Deployment Script
# Deploys the Jenkins Lambda function with proper configuration

set -e

echo "🚀 Starting Jenkins Agent deployment..."

# Configuration
AWS_REGION="us-east-1"
AWS_ACCOUNT_ID="395380602281"
FUNCTION_NAME="oscar-jenkins-agent"
ROLE_NAME="oscar-jenkins-lambda-role"
SECRET_ARN="arn:aws:secretsmanager:us-east-1:395380602281:secret:jenkins-api-token-WQZEc6"

echo "📋 Configuration:"
echo "  AWS Region: $AWS_REGION"
echo "  AWS Account: $AWS_ACCOUNT_ID"
echo "  Function Name: $FUNCTION_NAME"
echo "  Role Name: $ROLE_NAME"

# Navigate to jenkins directory
cd "$(dirname "$0")/.."

# Create deployment package
echo "📦 Creating deployment package..."
TEMP_DIR=$(mktemp -d)
echo "📁 Using temporary directory: $TEMP_DIR"

# Copy all Python files for modular deployment
cp *.py "$TEMP_DIR/"
cp requirements.txt "$TEMP_DIR/"

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt -t "$TEMP_DIR/" --quiet

# Create ZIP package
echo "🗜️  Creating ZIP package..."
cd "$TEMP_DIR"
zip -r ../jenkins-agent-deployment.zip . > /dev/null
cd - > /dev/null

# Move the ZIP to deployment directory
mv "$TEMP_DIR/../jenkins-agent-deployment.zip" deployment/jenkins-agent-deployment.zip

# Clean up temporary directory
rm -rf "$TEMP_DIR"

# Create or update IAM role
echo "🔐 Setting up IAM role..."
if ! aws iam get-role --role-name "$ROLE_NAME" --region "$AWS_REGION" > /dev/null 2>&1; then
    echo "🆕 Creating IAM role..."
    
    # Create trust policy
    cat > deployment/trust-policy.json << 'EOF'
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
    
    # Create role
    aws iam create-role \
        --role-name "$ROLE_NAME" \
        --assume-role-policy-document file://deployment/trust-policy.json \
        --region "$AWS_REGION" > /dev/null
    
    # Attach basic execution policy
    aws iam attach-role-policy \
        --role-name "$ROLE_NAME" \
        --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole" \
        --region "$AWS_REGION"
    
    # Create and attach Secrets Manager policy
    cat > deployment/secrets-policy.json << EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "secretsmanager:GetSecretValue"
            ],
            "Resource": [
                "$SECRET_ARN"
            ]
        }
    ]
}
EOF
    
    aws iam put-role-policy \
        --role-name "$ROLE_NAME" \
        --policy-name "SecretsManagerAccess" \
        --policy-document file://deployment/secrets-policy.json \
        --region "$AWS_REGION"
    
    # Clean up policy files
    rm deployment/trust-policy.json deployment/secrets-policy.json
    
    echo "✅ IAM role created"
    
    # Wait for role to be available
    echo "⏳ Waiting for IAM role to be available..."
    sleep 10
else
    echo "✅ IAM role already exists"
fi

# Get role ARN
ROLE_ARN=$(aws iam get-role --role-name "$ROLE_NAME" --query 'Role.Arn' --output text --region "$AWS_REGION")

# Check if function exists and delete if it does (for clean deployment)
echo "🔍 Checking if Lambda function exists..."
if aws lambda get-function --function-name "$FUNCTION_NAME" --region "$AWS_REGION" > /dev/null 2>&1; then
    echo "🗑️  Deleting existing function for clean deployment..."
    aws lambda delete-function --function-name "$FUNCTION_NAME" --region "$AWS_REGION"
    sleep 5
fi

echo "🆕 Creating Lambda function..."

# Create function
aws lambda create-function \
    --function-name "$FUNCTION_NAME" \
    --runtime python3.12 \
    --role "$ROLE_ARN" \
    --handler lambda_function.lambda_handler \
    --zip-file fileb://deployment/jenkins-agent-deployment.zip \
    --timeout 180 \
    --memory-size 512 \
    --environment Variables="{JENKINS_URL=https://ci-staging.opensearch.org,JENKINS_SECRET_NAME=jenkins-api-token,LOG_LEVEL=INFO}" \
    --region "$AWS_REGION" > /dev/null

echo "✅ Lambda function created successfully"

# Clean up deployment package
rm deployment/jenkins-agent-deployment.zip

# Get function info
echo "📋 Function details:"
aws lambda get-function --function-name "$FUNCTION_NAME" --region "$AWS_REGION" --query '{
    FunctionName: Configuration.FunctionName,
    FunctionArn: Configuration.FunctionArn,
    Runtime: Configuration.Runtime,
    Handler: Configuration.Handler,
    MemorySize: Configuration.MemorySize,
    Timeout: Configuration.Timeout,
    LastModified: Configuration.LastModified
}' --output table

echo ""
echo "🎉 Jenkins Agent deployment completed successfully!"
echo ""
echo "📝 Next steps:"
echo "1. Test the deployment: python deployment/test_deployment.py"
echo "2. Configure Bedrock agent with function definitions from schemas/jenkins_action_group.json"
echo "3. Set up agent collaboration as documented in docs/AGENT_CONFIGURATION.md"
echo ""
echo "🔧 Available functions:"
echo "  • docker_scan: Trigger Docker security scans"
echo "  • trigger_job: Trigger any supported Jenkins job"
echo "  • test_connection: Test Jenkins connectivity"
echo "  • get_job_info: Get job information and parameters"
echo "  • list_jobs: List all available jobs"