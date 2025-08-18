#!/bin/bash
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

# Monitor OSCAR agent performance by checking recent CloudWatch logs

set -e

echo "🔍 OSCAR Agent Performance Monitor"
echo "=================================="

# Load environment variables
if [ -f .env ]; then
    set -a
    source .env
    set +a
else
    echo "❌ .env file not found"
    exit 1
fi

echo "📊 Checking recent performance metrics..."
echo ""

# Get recent log events from the last hour
START_TIME=$(python3 -c "import time; print(int((time.time() - 3600) * 1000))")

echo "🕐 Analyzing logs from the last hour..."
echo ""

# Check supervisor agent performance
echo "📈 Supervisor Agent Performance:"
aws logs filter-log-events \
    --log-group-name "/aws/lambda/oscar-supervisor-agent" \
    --region $AWS_REGION \
    --start-time $START_TIME \
    --filter-pattern "\"OSCAR agent query completed\"" \
    --query 'events[*].message' \
    --output text | grep -o "completed in [0-9.]* seconds" | tail -10

echo ""

# Check communication handler performance
echo "📈 Communication Handler Performance:"
aws logs filter-log-events \
    --log-group-name "/aws/lambda/oscar-communication-handler" \
    --region $AWS_REGION \
    --start-time $START_TIME \
    --filter-pattern "\"Processing\"" \
    --query 'events[*].message' \
    --output text | head -5

echo ""

# Check for timeout errors
echo "⚠️  Recent Timeout/Error Patterns:"
aws logs filter-log-events \
    --log-group-name "/aws/lambda/oscar-supervisor-agent" \
    --region $AWS_REGION \
    --start-time $START_TIME \
    --filter-pattern "\"Task timed out\" OR \"high load\" OR \"timeout\"" \
    --query 'events[*].message' \
    --output text | head -5

echo ""

# Check current Lambda configurations
echo "⚙️  Current Lambda Configurations:"
echo "Supervisor Agent:"
aws lambda get-function-configuration \
    --function-name oscar-supervisor-agent \
    --region $AWS_REGION \
    --query '{Timeout:Timeout,MemorySize:MemorySize,Runtime:Runtime}'

echo ""
echo "Communication Handler:"
aws lambda get-function-configuration \
    --function-name oscar-communication-handler \
    --region $AWS_REGION \
    --query '{Timeout:Timeout,MemorySize:MemorySize,Runtime:Runtime}'

echo ""
echo "✅ Performance monitoring complete!"
echo ""
echo "💡 Tips for better performance:"
echo "   - Keep queries specific and focused"
echo "   - Avoid complex multi-step message requests"
echo "   - Use direct channel mentions (#channel-name)"
echo "   - Monitor for 'high load' messages indicating timeout issues"