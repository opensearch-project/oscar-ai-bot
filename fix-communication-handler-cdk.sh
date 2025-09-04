#!/bin/bash

# Fix Communication Handler CDK Lambda Function
# This script updates the communication handler Lambda with the correct flattened structure

set -e

echo "[INFO] 🔧 Fixing Communication Handler CDK Lambda Function..."
echo "[INFO] ================================================================="

# Configuration
FUNCTION_NAME="oscar-communication-handler-cdk"
REGION="us-east-1"

echo "[INFO] Function Name: $FUNCTION_NAME"

# Create temporary directory for deployment
TEMP_DIR=$(mktemp -d)
echo "[INFO] Using temporary directory: $TEMP_DIR"

# Copy the lambda entry point to root (rename to lambda_function.py)
cp oscar-agent/communication_handler/lambda_handler.py $TEMP_DIR/lambda_function.py

# Copy ONLY essential communication handler files directly to root (flatten structure)
echo "[INFO] 📁 Flattening essential communication_handler files to root directory..."

cp oscar-agent/communication_handler/message_handler.py $TEMP_DIR/
cp oscar-agent/communication_handler/message_formatter.py $TEMP_DIR/
cp oscar-agent/communication_handler/slack_client.py $TEMP_DIR/
cp oscar-agent/communication_handler/response_builder.py $TEMP_DIR/
cp oscar-agent/communication_handler/channel_utils.py $TEMP_DIR/

# Copy context_storage.py (unified storage)
cp oscar-agent/context_storage.py $TEMP_DIR/

# Copy config.py (required dependency)
cp oscar-agent/config.py $TEMP_DIR/

echo "[INFO] ✅ Flattened essential files to root"

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

# Install dependencies
echo "[INFO] 📦 Installing Python dependencies..."
pip install -r $TEMP_DIR/requirements.txt -t $TEMP_DIR/ --upgrade --quiet

# Verify critical dependencies
echo "[INFO] 🔍 Verifying dependencies..."
CRITICAL_DEPS=("slack_sdk" "boto3" "botocore" "requests")
for dep in "${CRITICAL_DEPS[@]}"; do
    if [ ! -d "$TEMP_DIR/$dep" ] && [ ! -d "$TEMP_DIR/${dep//_/-}" ]; then
        echo "[ERROR] ❌ Missing dependency: $dep"
        pip install "$dep" -t $TEMP_DIR/ --upgrade --quiet || {
            echo "[ERROR] ❌ Failed to install $dep"
            exit 1
        }
    fi
done

echo "[SUCCESS] ✅ Dependencies verified"

# Clean up any conflicting directories
rm -rf $TEMP_DIR/storage/ 2>/dev/null || true
rm -rf $TEMP_DIR/communication_handler/ 2>/dev/null || true
rm -rf $TEMP_DIR/communication/ 2>/dev/null || true

# Verify critical files exist in flattened structure
CRITICAL_FILES=("lambda_function.py" "config.py" "message_handler.py" "message_formatter.py" "slack_client.py" "response_builder.py" "channel_utils.py" "context_storage.py")
for file in "${CRITICAL_FILES[@]}"; do
    if [ ! -f "$TEMP_DIR/$file" ]; then
        echo "[ERROR] ❌ Missing critical file: $file"
        exit 1
    fi
done
echo "[SUCCESS] ✅ All critical files present in flattened structure"

# Create deployment package
cd $TEMP_DIR
zip -r ../communication-handler-cdk-fix.zip . -x "*.pyc" "*/__pycache__/*" -q
cd - > /dev/null

DEPLOYMENT_PACKAGE="$TEMP_DIR/../communication-handler-cdk-fix.zip"
echo "[SUCCESS] ✅ Created deployment package: $DEPLOYMENT_PACKAGE"

# Check if Lambda function exists
echo "[INFO] 🔍 Checking if Lambda function exists..."
if aws lambda get-function --function-name $FUNCTION_NAME --region $REGION > /dev/null 2>&1; then
    echo "[INFO] 🔄 Updating Lambda function code..."
    
    # Update function code (this replaces ALL code in the lambda)
    aws lambda update-function-code \
        --function-name $FUNCTION_NAME \
        --zip-file fileb://$DEPLOYMENT_PACKAGE \
        --region $REGION >/dev/null
    
    # Wait for code update to complete
    echo "[INFO] ⏳ Waiting for code update to complete..."
    aws lambda wait function-updated --function-name $FUNCTION_NAME --region $REGION
    
    echo "[SUCCESS] ✅ Updated Lambda function code: $FUNCTION_NAME"
    
    # Wait for function to be ready
    echo "[INFO] ⏳ Waiting for function to be ready..."
    aws lambda wait function-updated --function-name $FUNCTION_NAME --region $REGION
    aws lambda wait function-active --function-name $FUNCTION_NAME --region $REGION
    
else
    echo "[ERROR] ❌ Lambda function $FUNCTION_NAME does not exist!"
    exit 1
fi

# Get function ARN for confirmation
FUNCTION_ARN=$(aws lambda get-function --function-name $FUNCTION_NAME --region $REGION --query 'Configuration.FunctionArn' --output text)

# Cleanup
echo "[INFO] 🧹 Cleaning up temporary files..."
rm -rf $TEMP_DIR

echo ""
echo "[SUCCESS] 🎉 Communication Handler CDK Lambda Function Fixed!"
echo ""
echo "[INFO] 📋 Summary:"
echo "   Function Name: $FUNCTION_NAME"
echo "   Function ARN:  $FUNCTION_ARN"
echo "   Region:        $REGION"
echo ""
echo "[INFO] 📝 Updated Files (Flattened Structure):"
echo "   ✅ lambda_function.py (entry point)"
echo "   ✅ message_handler.py"
echo "   ✅ message_formatter.py"
echo "   ✅ slack_client.py"
echo "   ✅ response_builder.py"
echo "   ✅ channel_utils.py"
echo "   ✅ context_storage.py (unified storage)"
echo "   ✅ config.py"
echo ""
echo "[INFO] 🧪 Test the communication handler now!"