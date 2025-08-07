#!/bin/bash

set -e

echo "🔧 Adding missing get_metrics function to release agent action group"

# Create the updated function schema with both functions
cat > release_action_group_schema.json << 'EOF'
{
    "functions": [
        {
            "name": "get_release_metrics",
            "description": "Retrieve comprehensive release metrics including deployment success, frequency, and quality data",
            "parameters": {
                "time_range": {
                    "type": "string",
                    "description": "Time range: 1d, 7d, 30d, or 90d",
                    "required": false
                },
                "environment_filter": {
                    "type": "string", 
                    "description": "Filter by deployment environment: prod, staging, dev, or all",
                    "required": false
                },
                "metric_type": {
                    "type": "string",
                    "description": "Type of release metric: frequency, success_rate, quality, rollbacks, or summary", 
                    "required": false
                }
            },
            "requireConfirmation": "DISABLED"
        },
        {
            "name": "get_metrics",
            "description": "Generic metrics retrieval function for release data",
            "parameters": {
                "metric_type": {
                    "type": "string",
                    "description": "Type of metric: status, execution, frequency, or summary",
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
    --agent-id 4FCARBPEYB \
    --agent-version DRAFT \
    --action-group-id ITCRWPHYJU \
    --action-group-name "release-metrics-actions-v2" \
    --description "Retrieve and analyze release and deployment performance metrics" \
    --action-group-executor lambda="arn:aws:lambda:us-east-1:395380602281:function:oscar-release-metrics-agent-new" \
    --function-schema file://release_action_group_schema.json \
    --region us-east-1

echo "✅ Action group updated with get_metrics function"

# Prepare and deploy the agent
echo "🚀 Preparing agent..."
aws bedrock-agent prepare-agent \
    --agent-id 4FCARBPEYB \
    --region us-east-1

echo "✅ Release agent fixed! The get_metrics function is now available."

# Cleanup
rm -f release_action_group_schema.json

echo ""
echo "🧪 Test the fix:"
echo "aws lambda invoke --function-name oscar-release-metrics-agent-new --payload '{\"actionGroup\": \"MetricsActionGroup\", \"function\": \"get_metrics\", \"parameters\": [{\"name\": \"metric_type\", \"value\": \"status\"}]}' --cli-binary-format raw-in-base64-out --region us-east-1 test.json && cat test.json | jq ."