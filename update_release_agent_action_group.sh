#!/bin/bash

set -e

echo "🔧 Updating release agent action group with specialized parameters"

# Create the updated function schema for release metrics
cat > release_action_group_schema.json << 'EOF'
{
    "functions": [
        {
            "name": "get_release_metrics",
            "description": "Retrieve comprehensive release frequency, deployment success rates, and release quality metrics with readiness analysis",
            "parameters": {
                "metric_type": {
                    "type": "string",
                    "description": "Type of release metric: frequency, success_rate, quality, readiness, rollbacks, or summary",
                    "required": false
                },
                "time_range": {
                    "type": "string",
                    "description": "Time range: 1d, 7d, 30d, or 90d",
                    "required": false
                },
                "environment_filter": {
                    "type": "string", 
                    "description": "Filter by deployment environment or repository name",
                    "required": false
                },
                "release_state": {
                    "type": "string",
                    "description": "Filter by release state: open, closed, or all",
                    "required": false
                },
                "version_filter": {
                    "type": "string",
                    "description": "Filter by specific version pattern (e.g., 3.2.0, 2.x)",
                    "required": false
                },
                "readiness_threshold": {
                    "type": "string",
                    "description": "Minimum readiness score: high, medium, low, or all",
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
                    "description": "Type of metric: status, execution, readiness, or summary",
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

# Update the action group (we know the ID is ITCRWPHYJU from earlier)
aws bedrock-agent update-agent-action-group \
    --agent-id 4FCARBPEYB \
    --agent-version DRAFT \
    --action-group-id ITCRWPHYJU \
    --action-group-name "release-metrics-actions-v2" \
    --description "Retrieve and analyze release frequency, deployment success rates, and release quality metrics" \
    --action-group-executor lambda="arn:aws:lambda:us-east-1:395380602281:function:oscar-release-metrics-agent-new" \
    --function-schema file://release_action_group_schema.json \
    --region us-east-1

echo "✅ Release agent action group updated"

# Prepare the agent
echo "🚀 Preparing release agent..."
aws bedrock-agent prepare-agent \
    --agent-id 4FCARBPEYB \
    --region us-east-1

echo "✅ Release agent updated successfully!"

# Cleanup
rm -f release_action_group_schema.json

echo ""
echo "🧪 Test the updated agent:"
echo "aws lambda invoke --function-name oscar-release-metrics-agent-new --payload '{\"actionGroup\": \"MetricsActionGroup\", \"function\": \"get_release_metrics\", \"parameters\": [{\"name\": \"metric_type\", \"value\": \"readiness\"}, {\"name\": \"release_state\", \"value\": \"open\"}]}' --cli-binary-format raw-in-base64-out --region us-east-1 test.json && cat test.json | jq ."