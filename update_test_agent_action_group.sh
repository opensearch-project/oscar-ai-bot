#!/bin/bash

set -e

echo "🔧 Updating test agent action group with specialized parameters"

# Create the updated function schema for test metrics
cat > test_action_group_schema.json << 'EOF'
{
    "functions": [
        {
            "name": "get_test_metrics",
            "description": "Retrieve comprehensive test execution metrics, coverage data, and quality trends for OpenSearch projects",
            "parameters": {
                "metric_type": {
                    "type": "string",
                    "description": "Type of test metric: execution, coverage, quality, trends, or summary",
                    "required": false
                },
                "time_range": {
                    "type": "string",
                    "description": "Time range: 1d, 7d, 30d, or 90d",
                    "required": false
                },
                "project_filter": {
                    "type": "string", 
                    "description": "Filter by specific project/repository name",
                    "required": false
                },
                "test_type": {
                    "type": "string",
                    "description": "Type of test: functional, unit, integration, or all",
                    "required": false
                },
                "status_filter": {
                    "type": "string",
                    "description": "Filter by test status: passed, failed, open, closed, or all",
                    "required": false
                }
            },
            "requireConfirmation": "DISABLED"
        },
        {
            "name": "get_metrics",
            "description": "Generic metrics retrieval function for test data",
            "parameters": {
                "metric_type": {
                    "type": "string",
                    "description": "Type of metric: status, execution, coverage, or summary",
                    "required": false
                },
                "time_range": {
                    "type": "string",
                    "description": "Time range: 1d, 7d, 30d, or 90d", 
                    "required": false
                }
            },
            "requireConfirmation": "DISABLED"
        }
    ]
}
EOF

# Update the action group
aws bedrock-agent update-agent-action-group \
    --agent-id YXSZJ659S7 \
    --agent-version DRAFT \
    --action-group-id MC9YVIJJJR \
    --action-group-name "test-metrics-actions-v2" \
    --description "Retrieve and analyze test execution metrics, coverage data, and quality trends" \
    --action-group-executor lambda="arn:aws:lambda:us-east-1:395380602281:function:oscar-test-metrics-agent-new" \
    --function-schema file://test_action_group_schema.json \
    --region us-east-1

echo "✅ Test agent action group updated"

# Prepare the agent
echo "🚀 Preparing test agent..."
aws bedrock-agent prepare-agent \
    --agent-id YXSZJ659S7 \
    --region us-east-1

echo "✅ Test agent updated successfully!"

# Cleanup
rm -f test_action_group_schema.json

echo ""
echo "🧪 Test the updated agent:"
echo "aws lambda invoke --function-name oscar-test-metrics-agent-new --payload '{\"actionGroup\": \"MetricsActionGroup\", \"function\": \"get_test_metrics\", \"parameters\": [{\"name\": \"metric_type\", \"value\": \"execution\"}, {\"name\": \"project_filter\", \"value\": \"opensearch-build\"}]}' --cli-binary-format raw-in-base64-out --region us-east-1 test.json && cat test.json | jq ."