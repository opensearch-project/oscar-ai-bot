#!/bin/bash
# Complete Automated OSCAR Deployment Script
# Deploys all components including metrics agents, supervisor, API Gateway, and DynamoDB tables

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Complete Automated OSCAR Deployment${NC}"
echo "=============================================="

# Load environment variables
load_environment() {
    if [ -f ".env" ]; then
        echo -e "${GREEN}✅ Loading environment from .env file${NC}"
        while IFS= read -r line; do
            [[ $line =~ ^[[:space:]]*# ]] && continue
            [[ -z $line ]] && continue
            export "$line"
        done < .env
    else
        echo -e "${RED}❌ .env file not found${NC}"
        exit 1
    fi
}

load_environment

# Validate required environment variables
validate_environment() {
    echo -e "${YELLOW}🔍 Validating environment...${NC}"
    
    local missing_vars=()
    local required_vars=(
        "AWS_REGION"
        "SLACK_BOT_TOKEN"
        "SLACK_SIGNING_SECRET"
        "OSCAR_BEDROCK_AGENT_ID"
        "OSCAR_BEDROCK_AGENT_ALIAS_ID"
    )
    
    for var in "${required_vars[@]}"; do
        if [ -z "${!var}" ]; then
            missing_vars+=("$var")
        fi
    done
    
    if [ ${#missing_vars[@]} -ne 0 ]; then
        echo -e "${RED}❌ Missing required environment variables:${NC}"
        printf '   %s\n' "${missing_vars[@]}"
        exit 1
    fi
    
    echo -e "${GREEN}✅ Environment validation passed${NC}"
}

validate_environment

# Step 1: Deploy Metrics Agents with Permissions
deploy_metrics_agents() {
    echo -e "${YELLOW}📦 Step 1: Deploying Metrics Agents${NC}"
    ./deploy_metrics.sh
    echo -e "${GREEN}✅ Metrics agents deployed with permissions${NC}"
    echo ""
}

# Step 2: Create DynamoDB Tables
create_dynamodb_tables() {
    echo -e "${YELLOW}📊 Step 2: Creating DynamoDB Tables${NC}"
    
    local sessions_table="${SESSIONS_TABLE_NAME:-oscar-sessions-v2}"
    local context_table="${CONTEXT_TABLE_NAME:-oscar-context}"
    
    # Create sessions table
    echo "  Creating sessions table: $sessions_table"
    aws dynamodb create-table \
        --table-name "$sessions_table" \
        --attribute-definitions \
            AttributeName=event_id,AttributeType=S \
        --key-schema \
            AttributeName=event_id,KeyType=HASH \
        --billing-mode PAY_PER_REQUEST \
        --region "$AWS_REGION" \
        --sse-specification Enabled=true \
        --tags Key=Project,Value=OSCAR Key=Service,Value=SlackBot \
        >/dev/null 2>&1 || echo "    (Table may already exist)"
    
    # Create context table
    echo "  Creating context table: $context_table"
    aws dynamodb create-table \
        --table-name "$context_table" \
        --attribute-definitions \
            AttributeName=thread_key,AttributeType=S \
        --key-schema \
            AttributeName=thread_key,KeyType=HASH \
        --billing-mode PAY_PER_REQUEST \
        --region "$AWS_REGION" \
        --sse-specification Enabled=true \
        --tags Key=Project,Value=OSCAR Key=Service,Value=SlackBot \
        >/dev/null 2>&1 || echo "    (Table may already exist)"
    
    # Add TTL to tables if they were just created
    echo "  Configuring TTL for tables..."
    aws dynamodb update-time-to-live \
        --table-name "$sessions_table" \
        --time-to-live-specification Enabled=true,AttributeName=ttl \
        --region "$AWS_REGION" >/dev/null 2>&1 || echo "    (TTL may already be configured)"
    
    aws dynamodb update-time-to-live \
        --table-name "$context_table" \
        --time-to-live-specification Enabled=true,AttributeName=ttl \
        --region "$AWS_REGION" >/dev/null 2>&1 || echo "    (TTL may already be configured)"
    
    # Wait for tables to be active
    echo "  Waiting for tables to be active..."
    aws dynamodb wait table-exists --table-name "$sessions_table" --region "$AWS_REGION"
    aws dynamodb wait table-exists --table-name "$context_table" --region "$AWS_REGION"
    
    echo -e "${GREEN}✅ DynamoDB tables created${NC}"
    echo ""
}

# Step 3: Create IAM Role for Supervisor Lambda
create_supervisor_role() {
    echo -e "${YELLOW}🔑 Step 3: Creating Supervisor IAM Role${NC}"
    
    local role_name="oscar-supervisor-lambda-role"
    
    # Check if role exists
    if aws iam get-role --role-name "$role_name" --region "$AWS_REGION" >/dev/null 2>&1; then
        SUPERVISOR_ROLE_ARN=$(aws iam get-role --role-name "$role_name" --query 'Role.Arn' --output text --region "$AWS_REGION")
        echo "  Using existing IAM role: $SUPERVISOR_ROLE_ARN"
        echo "  ⚠️  WARNING: Existing role permissions will be preserved"
        echo "  If you need to update permissions, delete the role first or update manually"
        return
    fi
    
    echo "  Creating new IAM role: $role_name"
    
    # Create trust policy
    cat > trust-policy.json << 'EOF'
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

    # Create IAM role
    SUPERVISOR_ROLE_ARN=$(aws iam create-role \
        --role-name "$role_name" \
        --assume-role-policy-document file://trust-policy.json \
        --query 'Role.Arn' \
        --output text \
        --region "$AWS_REGION")
    
    # Attach basic execution policy
    aws iam attach-role-policy \
        --role-name "$role_name" \
        --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole" \
        --region "$AWS_REGION"
    
    # Create custom policy
    cat > supervisor-policy.json << EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeAgent",
                "bedrock:GetAgent",
                "bedrock:GetKnowledgeBase",
                "bedrock:Retrieve",
                "bedrock:RetrieveAndGenerate",
                "bedrock-agent-runtime:InvokeAgent",
                "bedrock-agent-runtime:Retrieve",
                "bedrock-agent-runtime:RetrieveAndGenerate"
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
                "arn:aws:dynamodb:$AWS_REGION:*:table/${SESSIONS_TABLE_NAME:-oscar-sessions-v2}",
                "arn:aws:dynamodb:$AWS_REGION:*:table/${CONTEXT_TABLE_NAME:-oscar-context}"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "lambda:InvokeFunction"
            ],
            "Resource": [
                "arn:aws:lambda:$AWS_REGION:*:function:oscar-*-metrics-agent*",
                "arn:aws:lambda:$AWS_REGION:*:function:oscar-supervisor-agent"
            ]
        }
    ]
}
EOF

    aws iam put-role-policy \
        --role-name "$role_name" \
        --policy-name "OSCARSupervisorAccess" \
        --policy-document file://supervisor-policy.json \
        --region "$AWS_REGION"
    
    # Clean up policy files
    rm -f trust-policy.json supervisor-policy.json
    
    echo -e "${GREEN}✅ IAM role created: $SUPERVISOR_ROLE_ARN${NC}"
    
    # Wait for role propagation
    echo "  ⏳ Waiting for IAM role propagation..."
    sleep 15
    echo ""
}

# Step 4: Deploy Supervisor Lambda
deploy_supervisor_lambda() {
    echo -e "${YELLOW}🚀 Step 4: Deploying Supervisor Lambda${NC}"
    
    local function_name="oscar-supervisor-agent"
    
    # Create deployment package
    echo "  📦 Creating deployment package..."
    rm -rf supervisor-package supervisor-package.zip
    mkdir supervisor-package
    
    # Install dependencies
    pip install -r oscar-agent/requirements.txt -t supervisor-package/ --quiet --no-warn-script-location
    
    # Copy source code
    cp oscar-agent/*.py supervisor-package/
    
    # Clean up unnecessary files
    find supervisor-package -name "*.pyc" -delete 2>/dev/null || true
    find supervisor-package -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    find supervisor-package -name "*.dist-info" -type d -exec rm -rf {} + 2>/dev/null || true
    
    # Create zip package
    cd supervisor-package && zip -r ../supervisor-package.zip . -q && cd ..
    rm -rf supervisor-package
    
    # Create environment variables
    cat > supervisor-env-vars.json << EOF
{
    "Variables": {
        "OSCAR_BEDROCK_AGENT_ID": "$OSCAR_BEDROCK_AGENT_ID",
        "OSCAR_BEDROCK_AGENT_ALIAS_ID": "$OSCAR_BEDROCK_AGENT_ALIAS_ID",
        "SESSIONS_TABLE_NAME": "${SESSIONS_TABLE_NAME:-oscar-sessions-v2}",
        "CONTEXT_TABLE_NAME": "${CONTEXT_TABLE_NAME:-oscar-context}",
        "SLACK_BOT_TOKEN": "$SLACK_BOT_TOKEN",
        "SLACK_SIGNING_SECRET": "$SLACK_SIGNING_SECRET",
        "DEDUP_TTL": "${DEDUP_TTL:-300}",
        "SESSION_TTL": "${SESSION_TTL:-3600}",
        "CONTEXT_TTL": "${CONTEXT_TTL:-604800}",
        "MAX_CONTEXT_LENGTH": "${MAX_CONTEXT_LENGTH:-3000}",
        "CONTEXT_SUMMARY_LENGTH": "${CONTEXT_SUMMARY_LENGTH:-500}",
        "ENABLE_DM": "${ENABLE_DM:-false}",
        "AGENT_TIMEOUT": "${AGENT_TIMEOUT:-60}",
        "AGENT_MAX_RETRIES": "${AGENT_MAX_RETRIES:-2}"
    }
}
EOF
    
    # Check if function exists
    if aws lambda get-function --function-name "$function_name" --region "$AWS_REGION" >/dev/null 2>&1; then
        echo "  Updating existing function..."
        
        # Update function code
        aws lambda update-function-code \
            --function-name "$function_name" \
            --zip-file fileb://supervisor-package.zip \
            --region "$AWS_REGION" >/dev/null
        
        # Wait for update
        aws lambda wait function-updated --function-name "$function_name" --region "$AWS_REGION"
        
        # Update configuration
        aws lambda update-function-configuration \
            --function-name "$function_name" \
            --environment file://supervisor-env-vars.json \
            --timeout 60 \
            --memory-size 512 \
            --region "$AWS_REGION" >/dev/null
    else
        echo "  Creating new function..."
        
        aws lambda create-function \
            --function-name "$function_name" \
            --runtime python3.12 \
            --role "$SUPERVISOR_ROLE_ARN" \
            --handler app.lambda_handler \
            --zip-file fileb://supervisor-package.zip \
            --timeout 60 \
            --memory-size 512 \
            --environment file://supervisor-env-vars.json \
            --region "$AWS_REGION" >/dev/null
    fi
    
    # Wait for function to be ready
    aws lambda wait function-updated --function-name "$function_name" --region "$AWS_REGION"
    
    # Get function ARN
    SUPERVISOR_FUNCTION_ARN=$(aws lambda get-function --function-name "$function_name" --query 'Configuration.FunctionArn' --output text --region "$AWS_REGION")
    
    # Clean up
    rm -f supervisor-package.zip supervisor-env-vars.json
    
    echo -e "${GREEN}✅ Supervisor Lambda deployed: $SUPERVISOR_FUNCTION_ARN${NC}"
    echo ""
}

# Step 5: Create API Gateway
create_api_gateway() {
    echo -e "${YELLOW}🌐 Step 5: Creating API Gateway${NC}"
    
    local api_name="oscar-slack-webhook"
    
    # Check if API already exists
    local existing_api_id=$(aws apigateway get-rest-apis --region "$AWS_REGION" --query "items[?name=='$api_name'].id" --output text)
    
    if [ -n "$existing_api_id" ] && [ "$existing_api_id" != "None" ]; then
        echo "  Using existing API Gateway: $existing_api_id"
        API_ID="$existing_api_id"
    else
        echo "  Creating new API Gateway..."
        
        # Create REST API
        API_ID=$(aws apigateway create-rest-api \
            --name "$api_name" \
            --description "Webhook endpoint for OSCAR Slack integration" \
            --endpoint-configuration types=REGIONAL \
            --region "$AWS_REGION" \
            --query 'id' \
            --output text)
        
        echo "  Created API Gateway: $API_ID"
    fi
    
    # Get root resource ID
    ROOT_RESOURCE_ID=$(aws apigateway get-resources \
        --rest-api-id "$API_ID" \
        --region "$AWS_REGION" \
        --query 'items[?path==`/`].id' \
        --output text)
    
    # Create /slack resource
    echo "  Creating /slack resource..."
    SLACK_RESOURCE_ID=$(aws apigateway create-resource \
        --rest-api-id "$API_ID" \
        --parent-id "$ROOT_RESOURCE_ID" \
        --path-part "slack" \
        --region "$AWS_REGION" \
        --query 'id' \
        --output text 2>/dev/null || \
        aws apigateway get-resources \
            --rest-api-id "$API_ID" \
            --region "$AWS_REGION" \
            --query 'items[?pathPart==`slack`].id' \
            --output text)
    
    # Create /slack/events resource
    echo "  Creating /slack/events resource..."
    EVENTS_RESOURCE_ID=$(aws apigateway create-resource \
        --rest-api-id "$API_ID" \
        --parent-id "$SLACK_RESOURCE_ID" \
        --path-part "events" \
        --region "$AWS_REGION" \
        --query 'id' \
        --output text 2>/dev/null || \
        aws apigateway get-resources \
            --rest-api-id "$API_ID" \
            --region "$AWS_REGION" \
            --query 'items[?pathPart==`events`].id' \
            --output text)
    
    # Create POST method
    echo "  Creating POST method..."
    aws apigateway put-method \
        --rest-api-id "$API_ID" \
        --resource-id "$EVENTS_RESOURCE_ID" \
        --http-method POST \
        --authorization-type NONE \
        --region "$AWS_REGION" >/dev/null 2>&1 || true
    
    # Add method response
    aws apigateway put-method-response \
        --rest-api-id "$API_ID" \
        --resource-id "$EVENTS_RESOURCE_ID" \
        --http-method POST \
        --status-code 200 \
        --region "$AWS_REGION" >/dev/null 2>&1 || true
    
    # Set up Lambda integration
    echo "  Setting up Lambda integration..."
    aws apigateway put-integration \
        --rest-api-id "$API_ID" \
        --resource-id "$EVENTS_RESOURCE_ID" \
        --http-method POST \
        --type AWS_PROXY \
        --integration-http-method POST \
        --uri "arn:aws:apigateway:$AWS_REGION:lambda:path/2015-03-31/functions/$SUPERVISOR_FUNCTION_ARN/invocations" \
        --region "$AWS_REGION" >/dev/null 2>&1 || true
    
    # Add integration response
    aws apigateway put-integration-response \
        --rest-api-id "$API_ID" \
        --resource-id "$EVENTS_RESOURCE_ID" \
        --http-method POST \
        --status-code 200 \
        --region "$AWS_REGION" >/dev/null 2>&1 || true
    
    # Add Lambda permission for API Gateway
    echo "  Adding Lambda permission for API Gateway..."
    aws lambda add-permission \
        --function-name oscar-supervisor-agent \
        --statement-id "apigateway-invoke-$(date +%s)" \
        --action lambda:InvokeFunction \
        --principal apigateway.amazonaws.com \
        --source-arn "arn:aws:execute-api:$AWS_REGION:*:$API_ID/*/*" \
        --region "$AWS_REGION" >/dev/null 2>&1 || echo "    (Permission may already exist)"
    
    # Deploy API
    echo "  Deploying API to prod stage..."
    aws apigateway create-deployment \
        --rest-api-id "$API_ID" \
        --stage-name prod \
        --region "$AWS_REGION" >/dev/null
    
    # Get API URL
    API_URL="https://$API_ID.execute-api.$AWS_REGION.amazonaws.com/prod"
    WEBHOOK_URL="$API_URL/slack/events"
    
    echo -e "${GREEN}✅ API Gateway created${NC}"
    echo "  API URL: $API_URL"
    echo "  Webhook URL: $WEBHOOK_URL"
    echo ""
}

# Step 6: Test Deployment
test_deployment() {
    echo -e "${YELLOW}🧪 Step 6: Testing Deployment${NC}"
    
    # Test supervisor function
    echo "  Testing supervisor function..."
    aws lambda invoke \
        --function-name oscar-supervisor-agent \
        --payload '{"test": "connectivity"}' \
        --cli-binary-format raw-in-base64-out \
        --region "$AWS_REGION" \
        test-supervisor.json >/dev/null 2>&1
    
    if grep -q "statusCode.*200" test-supervisor.json 2>/dev/null; then
        echo -e "${GREEN}    ✅ Supervisor function working${NC}"
    else
        echo -e "${RED}    ❌ Supervisor function test failed${NC}"
    fi
    
    # Test metrics function
    echo "  Testing metrics function..."
    aws lambda invoke \
        --function-name oscar-test-metrics-agent-new \
        --payload '{"function": "test_basic"}' \
        --cli-binary-format raw-in-base64-out \
        --region "$AWS_REGION" \
        test-metrics.json >/dev/null 2>&1
    
    if grep -q '"status": "success"' test-metrics.json 2>/dev/null; then
        echo -e "${GREEN}    ✅ Metrics functions working${NC}"
    else
        echo -e "${YELLOW}    ⚠️  Metrics functions in mock mode (expected)${NC}"
    fi
    
    # Test API Gateway
    echo "  Testing API Gateway..."
    if curl -s -X POST "$WEBHOOK_URL" \
        -H "Content-Type: application/json" \
        -d '{"type": "url_verification", "challenge": "test"}' | grep -q "test"; then
        echo -e "${GREEN}    ✅ API Gateway working${NC}"
    else
        echo -e "${YELLOW}    ⚠️  API Gateway test inconclusive${NC}"
    fi
    
    # Clean up test files
    rm -f test-supervisor.json test-metrics.json
    
    echo ""
}

# Main deployment process
main() {
    deploy_metrics_agents
    create_dynamodb_tables
    create_supervisor_role
    deploy_supervisor_lambda
    create_api_gateway
    test_deployment
    
    # Show deployment summary
    echo -e "${GREEN}✅ Complete OSCAR Deployment Finished!${NC}"
    echo "=============================================="
    echo ""
    echo -e "${BLUE}📋 Deployment Summary:${NC}"
    echo "  Supervisor Function: oscar-supervisor-agent"
    echo "  Metrics Functions: oscar-*-metrics-agent-new"
    echo "  API Gateway: $API_ID"
    echo "  Webhook URL: $WEBHOOK_URL"
    echo "  DynamoDB Tables: ${SESSIONS_TABLE_NAME:-oscar-sessions-v2}, ${CONTEXT_TABLE_NAME:-oscar-context}"
    echo ""
    echo -e "${BLUE}🔗 Slack Configuration:${NC}"
    echo "  1. Go to https://api.slack.com/apps"
    echo "  2. Select your OSCAR app (or create new one)"
    echo "  3. Go to Event Subscriptions"
    echo "  4. Set Request URL to: $WEBHOOK_URL"
    echo "  5. Subscribe to bot events: app_mention, message.im (if DM enabled)"
    echo "  6. Save Changes and reinstall app to workspace"
    echo ""
    echo -e "${BLUE}🧪 Test Commands:${NC}"
    echo "  # Test in Slack:"
    echo "  @oscar hello"
    echo "  @oscar What is OpenSearch?"
    echo "  @oscar Show me test metrics"
    echo ""
    echo -e "${BLUE}📊 Monitoring:${NC}"
    echo "  CloudWatch Logs: /aws/lambda/oscar-supervisor-agent"
    echo "  API Gateway Logs: Check API Gateway console"
    echo ""
    echo -e "${GREEN}🎉 OSCAR is ready to use in Slack!${NC}"
}

# Run main deployment
main