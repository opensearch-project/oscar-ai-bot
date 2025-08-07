#!/bin/bash

set -e

echo "🔧 Updating build agent action group with specialized parameters"

# Create the updated function schema for build metrics
cat > build_action_group_schema.json << 'EOF'
{
    "functions": [
        {
            "name": "get_build_metrics",
            "description": "Retrieve comprehensive build performance, CI/CD pipeline metrics, and development workflow efficiency data",
            "parameters": {
                "metric_type": {
                    "type": "string",
                    "description": "Type of build metric: execution, performance, pipeline, workflow, or summary",
                    "required": false
                },
                "time_range": {
                    "type": "string",
                    "description": "Time range: 1d, 7d, 30d, or 90d",
                    "required": false
                },
                "branch_filter": {
                    "type": "string", 
                    "description": "Filter by specific branch or repository name",
                    "required": false
                },
                "build_type": {
                    "type": "string",
                    "description": "Type of build: main, release, feature, or all",
                    "required": false
                },
                "status_filter": {
                    "type": "string",
                    "description": "Filter by build status: success, failed, open, closed, or all",
                    "required": false
                },
                "pipeline_stage": {
                    "type": "string",
                    "description": "Specific pipeline stage: build, test, deploy, or all",
                    "required": false
                }
            },
            "requireConfirmation": "DISABLED"
        },
        {
            "name": "get_metrics",
            "description": "Generic metrics retrieval function for build data",
            "parameters": {
                "metric_type": {
                    "type": "string",
                    "description": "Type of metric: status, execution, performance, or summary",
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

# Get the build agent action group ID first
BUILD_ACTION_GROUP_ID=$(aws bedrock-agent list-agent-action-groups --agent-id 0NBATJIVCH --agent-version DRAFT --region us-east-1 --query 'actionGroupSummaries[0].actionGroupId' --output text)

# Update the action group
aws bedrock-agent update-agent-action-group \
    --agent-id 0NBATJIVCH \
    --agent-version DRAFT \
    --action-group-id $BUILD_ACTION_GROUP_ID \
    --action-group-name "build-metrics-actions-v2" \
    --description "Retrieve and analyze build performance and CI/CD pipeline metrics" \
    --action-group-executor lambda="arn:aws:lambda:us-east-1:395380602281:function:oscar-build-metrics-agent-new" \
    --function-schema file://build_action_group_schema.json \
    --region us-east-1

echo "✅ Build agent action group updated"

# Prepare the agent
echo "🚀 Preparing build agent..."
aws bedrock-agent prepare-agent \
    --agent-id 0NBATJIVCH \
    --region us-east-1

echo "✅ Build agent updated successfully!"

# Cleanup
rm -f build_action_group_schema.json

echo ""
echo "🧪 Test the updated agent:"
echo "aws lambda invoke --function-name oscar-build-metrics-agent-new --payload '{\"actionGroup\": \"MetricsActionGroup\", \"function\": \"get_build_metrics\", \"parameters\": [{\"name\": \"metric_type\", \"value\": \"execution\"}, {\"name\": \"branch_filter\", \"value\": \"opensearch-build\"}]}' --cli-binary-format raw-in-base64-out --region us-east-1 test.json && cat test.json | jq ."