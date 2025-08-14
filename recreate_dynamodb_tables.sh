#!/bin/bash
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

# Recreate DynamoDB tables with proper settings for OSCAR Agent

set -e

echo "🗄️ Recreating DynamoDB Tables for OSCAR Agent..."

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
    echo "✅ Loaded environment variables from .env"
else
    echo "❌ .env file not found. Please create it with required variables."
    exit 1
fi

# Set default values
AWS_REGION=${AWS_REGION:-us-east-1}
CONTEXT_TABLE_NAME=${CONTEXT_TABLE_NAME:-oscar-agent-context}
SESSIONS_TABLE_NAME=${SESSIONS_TABLE_NAME:-oscar-agent-sessions}

echo "🌍 Using AWS Region: $AWS_REGION"
echo "📊 Context Table: $CONTEXT_TABLE_NAME"
echo "📊 Sessions Table: $SESSIONS_TABLE_NAME"

# Function to delete table if it exists
delete_table_if_exists() {
    local table_name=$1
    echo "🔍 Checking if table $table_name exists..."
    
    if aws dynamodb describe-table --table-name $table_name --region $AWS_REGION > /dev/null 2>&1; then
        echo "🗑️ Deleting existing table: $table_name"
        aws dynamodb delete-table --table-name $table_name --region $AWS_REGION
        
        echo "⏳ Waiting for table $table_name to be deleted..."
        aws dynamodb wait table-not-exists --table-name $table_name --region $AWS_REGION
        echo "✅ Table $table_name deleted successfully"
    else
        echo "ℹ️ Table $table_name does not exist, skipping deletion"
    fi
}

# Function to create table
create_table() {
    local table_name=$1
    local key_name=$2
    local key_type=$3
    
    echo "🆕 Creating table: $table_name"
    
    aws dynamodb create-table \
        --table-name $table_name \
        --attribute-definitions \
            AttributeName=$key_name,AttributeType=$key_type \
        --key-schema \
            AttributeName=$key_name,KeyType=HASH \
        --billing-mode PAY_PER_REQUEST \
        --region $AWS_REGION
    
    echo "⏳ Waiting for table $table_name to be active..."
    aws dynamodb wait table-exists --table-name $table_name --region $AWS_REGION
    
    # Enable TTL
    echo "🕐 Enabling TTL for table $table_name..."
    aws dynamodb update-time-to-live \
        --table-name $table_name \
        --time-to-live-specification \
            Enabled=true,AttributeName=ttl \
        --region $AWS_REGION
    
    echo "✅ Table $table_name created successfully with TTL enabled"
}

# Delete and recreate context table
echo ""
echo "=" * 50
echo "📊 CONTEXT TABLE"
echo "=" * 50
delete_table_if_exists $CONTEXT_TABLE_NAME
create_table $CONTEXT_TABLE_NAME "thread_key" "S"

# Delete and recreate sessions table
echo ""
echo "=" * 50
echo "📊 SESSIONS TABLE"
echo "=" * 50
delete_table_if_exists $SESSIONS_TABLE_NAME
create_table $SESSIONS_TABLE_NAME "event_id" "S"

# Verify tables
echo ""
echo "=" * 50
echo "🔍 VERIFICATION"
echo "=" * 50

echo "📊 Verifying context table..."
aws dynamodb describe-table --table-name $CONTEXT_TABLE_NAME --region $AWS_REGION --query 'Table.[TableName,TableStatus,BillingModeSummary.BillingMode]' --output table

echo "📊 Verifying sessions table..."
aws dynamodb describe-table --table-name $SESSIONS_TABLE_NAME --region $AWS_REGION --query 'Table.[TableName,TableStatus,BillingModeSummary.BillingMode]' --output table

# Check TTL settings
echo "🕐 Checking TTL settings for context table..."
aws dynamodb describe-time-to-live --table-name $CONTEXT_TABLE_NAME --region $AWS_REGION --query 'TimeToLiveDescription.[TimeToLiveStatus,AttributeName]' --output table

echo "🕐 Checking TTL settings for sessions table..."
aws dynamodb describe-time-to-live --table-name $SESSIONS_TABLE_NAME --region $AWS_REGION --query 'TimeToLiveDescription.[TimeToLiveStatus,AttributeName]' --output table

echo ""
echo "🎉 DynamoDB Tables Recreation Complete!"
echo ""
echo "📋 Summary:"
echo "   Context Table:  $CONTEXT_TABLE_NAME (✅ Active with TTL)"
echo "   Sessions Table: $SESSIONS_TABLE_NAME (✅ Active with TTL)"
echo "   Region:         $AWS_REGION"
echo "   Billing Mode:   PAY_PER_REQUEST"
echo ""
echo "📝 Next Steps:"
echo "   1. Deploy updated Lambda functions with enhanced logging"
echo "   2. Test context storage with new logging"
echo "   3. Monitor CloudWatch logs for detailed context operations"
echo ""
echo "🧪 Test Commands:"
echo "   # Test basic functionality"
echo "   python3 test_context_storage_comprehensive.py"
echo ""
echo "   # Check logs after testing"
echo "   aws logs get-log-events --log-group-name '/aws/lambda/oscar-supervisor-agent' --log-stream-name \$(aws logs describe-log-streams --log-group-name '/aws/lambda/oscar-supervisor-agent' --order-by LastEventTime --descending --max-items 1 --query 'logStreams[0].logStreamName' --output text) --region $AWS_REGION"