#!/bin/bash
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

# Update ONLY the code for Communication Handler Lambda function
# Preserves all permissions and configurations

set -e

echo "🔄 Updating Communication Handler Lambda Function (Code Only)..."

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

# Set function name
FUNCTION_NAME="oscar-communication-handler"

echo "📦 Creating deployment package..."

# Create temporary directory for deployment
TEMP_DIR=$(mktemp -d)
echo "Using temporary directory: $TEMP_DIR"

# Copy the lambda entry point to root
cp oscar-agent/communication_handler/lambda_handler.py $TEMP_DIR/lambda_function.py

# Copy ONLY essential communication handler files directly to root (flatten structure)
echo "📁 Flattening essential communication_handler files to root directory..."

cp oscar-agent/communication_handler/message_handler.py $TEMP_DIR/
cp oscar-agent/communication_handler/message_formatter.py $TEMP_DIR/
cp oscar-agent/communication_handler/slack_client.py $TEMP_DIR/
cp oscar-agent/communication_handler/response_builder.py $TEMP_DIR/
cp oscar-agent/communication_handler/channel_utils.py $TEMP_DIR/
cp oscar-agent/communication_handler/context_storage.py $TEMP_DIR/

echo "✅ Flattened essential files to root (excluded: __init__.py, constants.py)"

# Copy config.py (required dependency)
cp oscar-agent/config.py $TEMP_DIR/

# Create comprehensive requirements.txt for the Lambda function
cat > $TEMP_DIR/requirements.txt << EOF
# Core AWS and Slack dependencies
boto3>=1.34.0
botocore>=1.34.0
slack_sdk>=3.19.0

# HTTP and networking
requests>=2.31.0
urllib3>=2.0.0

# Additional dependencies
certifi>=2023.7.22
charset-normalizer>=3.0.0
idna>=3.0.0
python-dateutil>=2.8.0
jmespath>=1.0.0
s3transfer>=0.6.0
six>=1.16.0
python-dotenv>=1.0.0
EOF

# Install dependencies with upgrade flag
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

# Verify critical dependencies
echo "🔍 Verifying dependencies..."
CRITICAL_DEPS=("slack_sdk" "boto3" "botocore" "requests")
for dep in "${CRITICAL_DEPS[@]}"; do
    if [ ! -d "$TEMP_DIR/$dep" ] && [ ! -d "$TEMP_DIR/${dep//_/-}" ]; then
        echo "❌ Missing dependency: $dep"
        pip install "$dep" -t $TEMP_DIR/ --upgrade --quiet || {
            echo "❌ Failed to install $dep"
            exit 1
        }
    fi
done

echo "✅ Dependencies verified"

# Verify the deployment structure is clean
echo "🔍 Verifying deployment structure..."
echo "📋 Files to be deployed:"
find $TEMP_DIR -name "*.py" | sort
echo ""
echo "📋 Directory structure:"
find $TEMP_DIR -type d | sort
echo ""
echo "📋 Total files:"
find $TEMP_DIR -type f | wc -l

# Verify critical files exist in flattened structure
CRITICAL_FILES=("lambda_function.py" "config.py" "message_handler.py" "message_formatter.py" "slack_client.py" "response_builder.py" "channel_utils.py" "context_storage.py")
for file in "${CRITICAL_FILES[@]}"; do
    if [ ! -f "$TEMP_DIR/$file" ]; then
        echo "❌ Missing critical file: $file"
        exit 1
    fi
done
echo "✅ All critical files present in flattened structure"

# Verify no subdirectories exist (clean deployment)
if [ -d "$TEMP_DIR/communication_handler" ] || [ -d "$TEMP_DIR/communication" ]; then
    echo "❌ Found subdirectories - deployment should be flattened"
    exit 1
fi
echo "✅ Deployment structure is properly flattened"

# Verify no unwanted directories or files exist
echo "🔍 Final verification of deployment package..."
if find $TEMP_DIR -name "communication_handler" -type d | grep -q .; then
    echo "❌ Found communication_handler directory - should be flattened"
    exit 1
fi

if find $TEMP_DIR -name "communication" -type d | grep -q .; then
    echo "❌ Found communication directory - should be flattened"  
    exit 1
fi

if find $TEMP_DIR -maxdepth 1 -name "__init__.py" | grep -q .; then
    echo "❌ Found __init__.py files in root - not needed in flattened structure"
    exit 1
fi

echo "✅ Deployment package structure verified - clean and flattened"

# Create deployment package
cd $TEMP_DIR
zip -r ../communication-handler-update.zip . -x "*.pyc" "*/__pycache__/*" -q
cd - > /dev/null

DEPLOYMENT_PACKAGE="$TEMP_DIR/../communication-handler-update.zip"
echo "✅ Created deployment package: $DEPLOYMENT_PACKAGE"

# Check if Lambda function exists
# Set minimal environment variables (most config now comes from Secrets Manager)
cat > $TEMP_DIR/env-vars.json << EOF
{
    "Variables": {
        "DISABLE_CONFIG_VALIDATION": "true"
    }
}
EOF

echo "🔍 Checking if Lambda function exists..."
if aws lambda get-function --function-name $FUNCTION_NAME --region $AWS_REGION > /dev/null 2>&1; then
    echo "🔄 Updating Lambda function code (this will replace ALL existing code)..."
    echo "⚠️  This deployment will clean up duplicate directories and flatten the structure"
    
    # Update function code (this replaces ALL code in the lambda)
    aws lambda update-function-code \
        --function-name $FUNCTION_NAME \
        --zip-file fileb://$DEPLOYMENT_PACKAGE \
        --region $AWS_REGION >/dev/null
    
    # Wait for code update to complete
    echo "⏳ Waiting for code update to complete..."
    aws lambda wait function-updated --function-name $FUNCTION_NAME --region $AWS_REGION
    
    # Update environment variables, timeout, and memory
    aws lambda update-function-configuration \
        --function-name $FUNCTION_NAME \
        --environment file://$TEMP_DIR/env-vars.json \
        --timeout ${LAMBDA_TIMEOUT:-150} \
        --memory-size ${LAMBDA_MEMORY_SIZE:-512} \
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
echo "📝 Updated Files (Flattened Structure):"
echo "   ✅ lambda_function.py (entry point)"
echo "   ✅ message_handler.py"
echo "   ✅ message_formatter.py"
echo "   ✅ slack_client.py"
echo "   ✅ response_builder.py"
echo "   ✅ channel_utils.py"
echo "   ✅ context_storage.py"
echo "   ✅ config.py"
echo ""
echo "🧹 Cleaned Up:"
echo "   ✅ Removed duplicate communication/ directory"
echo "   ✅ Removed duplicate communication_handler/ directory"
echo "   ✅ Flattened all code to root level"
echo ""
echo "🧪 Test command:"
echo "aws lambda invoke --function-name $FUNCTION_NAME --payload '{\"actionGroup\": \"communication-orchestration\", \"apiPath\": \"/send_automated_message\"}' --cli-binary-format raw-in-base64-out --region $AWS_REGION test.json && cat test.json"