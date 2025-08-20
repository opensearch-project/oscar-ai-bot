#!/bin/bash
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

# Deploy metrics Lambda functions with proper permissions and dependencies
# FULL DEPLOYMENT - Creates functions, roles, and permissions

set -e

echo "🚀 Deploying metrics Lambda functions..."

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

# Verify region configuration
echo "🌍 Using AWS Region: $AWS_REGION"

# Use the correct VPC role ARN
ROLE_ARN="${LAMBDA_EXECUTION_ROLE_ARN:-arn:aws:iam::395380602281:role/oscar-metrics-lambda-vpc-role}"
echo "Using IAM role: $ROLE_ARN"

# Create deployment package
echo "📦 Creating deployment package..."
rm -rf metrics-package metrics-package.zip
mkdir metrics-package

# Create comprehensive requirements.txt for metrics
cat > metrics-package/requirements.txt << EOF
# Core AWS dependencies
boto3>=1.34.0
botocore>=1.34.0

# HTTP and networking
requests>=2.31.0
urllib3>=2.0.0
python-dotenv>=1.0.0

# Additional dependencies for metrics functionality
certifi>=2023.7.22
charset-normalizer>=3.0.0
idna>=3.0.0
python-dateutil>=2.8.0
jmespath>=1.0.0
s3transfer>=0.6.0
six>=1.16.0
EOF

# Install dependencies with upgrade flag
echo "📦 Installing Python dependencies..."
if ! pip install -r metrics-package/requirements.txt -t metrics-package/ --upgrade --quiet; then
    echo "❌ Failed to install dependencies with pip. Trying alternative approach..."
    # Try installing each dependency individually
    while IFS= read -r line; do
        if [[ $line =~ ^[a-zA-Z] ]]; then
            echo "  Installing: $line"
            pip install "$line" -t metrics-package/ --upgrade --quiet || {
                echo "❌ Failed to install $line"
                exit 1
            }
        fi
    done < metrics-package/requirements.txt
fi

# Verify critical dependencies
echo "🔍 Verifying dependencies..."
CRITICAL_DEPS=("boto3" "botocore" "requests")
for dep in "${CRITICAL_DEPS[@]}"; do
    if [ ! -d "metrics-package/$dep" ] && [ ! -d "metrics-package/${dep//_/-}" ]; then
        echo "❌ Missing dependency: $dep"
        pip install "$dep" -t metrics-package/ --upgrade --quiet || {
            echo "❌ Failed to install $dep"
            exit 1
        }
    fi
done

echo "✅ Dependencies verified"

# Copy source code
cp metrics/*.py metrics-package/

# Remove requirements.txt from package (not needed in Lambda)
rm -f metrics-package/requirements.txt

# Create zip
cd metrics-package && zip -r ../metrics-package.zip . -q && cd ..
rm -rf metrics-package

# Create VPC configuration
IFS=',' read -ra SUBNET_ARRAY <<< "$SUBNET_IDS"
subnet_json=""
for i in "${!SUBNET_ARRAY[@]}"; do
    if [ $i -eq 0 ]; then
        subnet_json="\"${SUBNET_ARRAY[$i]}\""
    else
        subnet_json="$subnet_json, \"${SUBNET_ARRAY[$i]}\""
    fi
done

cat > vpc-config.json << EOF
{
    "SubnetIds": [$subnet_json],
    "SecurityGroupIds": ["$SECURITY_GROUP_ID"]
}
EOF

# Deploy all agent functions
AGENT_FUNCTIONS=(
    "oscar-test-metrics-agent-new:test-metrics"
    "oscar-build-metrics-agent-new:build-metrics"
    "oscar-release-metrics-agent-new:release-metrics"
    "oscar-deployment-metrics-agent-new:deployment-metrics"
)

for func_config in "${AGENT_FUNCTIONS[@]}"; do
    IFS=':' read -ra FUNC_PARTS <<< "$func_config"
    FUNCTION_NAME="${FUNC_PARTS[0]}"
    AGENT_TYPE="${FUNC_PARTS[1]}"
    
    echo "🚀 Deploying $FUNCTION_NAME ($AGENT_TYPE)..."
    
    # Create minimal environment variables (config now comes from Secrets Manager)
    cat > env-vars.json << EOF
{
    "Variables": {
        "AGENT_TYPE": "$AGENT_TYPE"
    }
}
EOF
    
    # Check if function exists
    if aws lambda get-function --function-name "$FUNCTION_NAME" --region "$AWS_REGION" > /dev/null 2>&1; then
        echo "📝 Updating existing function..."
        # Update function code
        aws lambda update-function-code \
            --function-name "$FUNCTION_NAME" \
            --zip-file fileb://metrics-package.zip \
            --region "$AWS_REGION" >/dev/null
        
        # Wait for update to complete
        aws lambda wait function-updated --function-name "$FUNCTION_NAME" --region "$AWS_REGION"
        
        # Update configuration
        aws lambda update-function-configuration \
            --function-name "$FUNCTION_NAME" \
            --environment file://env-vars.json \
            --region "$AWS_REGION" >/dev/null
    else
        echo "🆕 Creating new function..."
        # Create new function
        aws lambda create-function \
            --function-name "$FUNCTION_NAME" \
            --runtime python3.12 \
            --role "$ROLE_ARN" \
            --handler lambda_function.lambda_handler \
            --zip-file fileb://metrics-package.zip \
            --timeout ${METRICS_TIMEOUT:-150} \
            --memory-size ${METRICS_MEMORY_SIZE:-512} \
            --vpc-config file://vpc-config.json \
            --environment file://env-vars.json \
            --region "$AWS_REGION" >/dev/null
    fi
    
    echo "✅ $FUNCTION_NAME deployed"
    
    # Wait for function to be ready
    aws lambda wait function-active --function-name "$FUNCTION_NAME" --region "$AWS_REGION"
done

echo "✅ All functions deployed successfully"

# Add Bedrock agent permissions
echo ""
echo "🔐 Adding Bedrock agent permissions..."

# Actual agent IDs from your deployment
AGENT_PERMISSIONS=(
    "YXSZJ659S7:oscar-test-metrics-agent-new:TestAnalyzer"
    "0NBATJIVCH:oscar-build-metrics-agent-new:BuildAnalyzer"
    "4FCARBPEYB:oscar-release-metrics-agent-new:ReleaseAnalyzer"
    "BIHPD6OLO0:oscar-deployment-metrics-agent-new:DeploymentAnalyzer"
)

# Function to add permission
add_permission() {
    local agent_id=$1
    local function_name=$2
    local agent_name=$3
    
    echo "  Adding permission for $agent_name..."
    
    aws lambda add-permission \
        --function-name "$function_name" \
        --statement-id "bedrock-v2-$agent_id-$(date +%s)" \
        --action "lambda:InvokeFunction" \
        --principal "bedrock.amazonaws.com" \
        --source-arn "arn:aws:bedrock:$AWS_REGION:395380602281:agent/$agent_id" \
        --region "$AWS_REGION" >/dev/null 2>&1 || echo "    (Permission may already exist)"
    
    echo "    ✅ Permission added"
}

# Add permissions for each agent
for entry in "${AGENT_PERMISSIONS[@]}"; do
    IFS=':' read -ra PARTS <<< "$entry"
    agent_id="${PARTS[0]}"
    function_name="${PARTS[1]}"
    agent_name="${PARTS[2]}"
    
    add_permission "$agent_id" "$function_name" "$agent_name"
done

echo "✅ Bedrock permissions configured"

# Cleanup
rm -f metrics-package.zip env-vars.json vpc-config.json

echo ""
echo "🎉 Metrics Lambda Functions Deployment Complete!"
echo ""
echo "📋 Deployed Functions:"
for func_config in "${AGENT_FUNCTIONS[@]}"; do
    IFS=':' read -ra FUNC_PARTS <<< "$func_config"
    echo "   ✅ ${FUNC_PARTS[0]} (${FUNC_PARTS[1]})"
done
echo ""
echo "🧪 Test command:"
echo "aws lambda invoke --function-name oscar-build-metrics-agent-new --payload '{\"function\": \"test_basic\"}' --cli-binary-format raw-in-base64-out --region $AWS_REGION test.json && cat test.json | jq ."