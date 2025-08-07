#!/bin/bash

set -e

echo "🔧 Updating deployment agent action group with specialized parameters"

# Create the updated function schema for deployment metrics
cat > deployment_action_group_schema.json << 'EOF'
{
    "functions": [
        {
            "name": "get_deployment_metrics",
            "description": "Retrieve comprehensive deployment performance, infrastructure health, and operational efficiency metrics",
            "parameters": {
                "metric_type": {
                    "type": "string",
                    "description": "Type of deployment metric: performance, health, infrastructure, operational, or summary",
                    "required": false
                },
                "time_range": {
                    "type": "string",
                    "description": "Time range: 1d, 7d, 30d, or 90d",
                    "required": false
                },
                "service_filter": {
                    "type": "string", 
                    "description": "Filter by specific service or component name",
                    "required": false
                },
                "environment": {
                    "type": "string",
                    "description": "Deployment environment: production, staging, development, or all",
                    "required": false
                },
                "health_status": {
                    "type": "string",
                    "description": "Filter by health status: healthy, degraded, critical, or all",
                    "required": false
                },
                "deployment_type": {
                    "type": "string",
                    "description": "Type of deployment: core, plugin, dashboard, or all",
                    "required": false
                }
            },
            "requireConfirmation": "DISABLED"
        },
        {
            "name": "get_metrics",
            "description": "Generic metrics retrieval function for deployment data",
            "parameters": {
                "metric_type": {
                    "type": "string",
                    "description": "Type of metric: status, execution, health, or summary",
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

# Get the deployment agent action group ID first
DEPLOYMENT_ACTION_GROUP_ID=$(aws bedrock-agent list-agent-action-groups --agent-id BIHPD6OLO0 --agent-version DRAFT --region us-east-1 --query 'actionGroupSummaries[0].actionGroupId' --output text)

# Update the action group
aws bedrock-agent update-agent-action-group \
    --agent-id BIHPD6OLO0 \
    --agent-version DRAFT \
    --action-group-id $DEPLOYMENT_ACTION_GROUP_ID \
    --action-group-name "deployment-metrics-actions-v2" \
    --description "Retrieve and analyze deployment performance, infrastructure health, and operational metrics" \
    --action-group-executor lambda="arn:aws:lambda:us-east-1:395380602281:function:oscar-deployment-metrics-agent-new" \
    --function-schema file://deployment_action_group_schema.json \
    --region us-east-1

echo "✅ Deployment agent action group updated"

# Prepare the agent
echo "🚀 Preparing deployment agent..."
aws bedrock-agent prepare-agent \
    --agent-id BIHPD6OLO0 \
    --region us-east-1

echo "✅ Deployment agent updated successfully!"

# Cleanup
rm -f deployment_action_group_schema.json

echo ""
echo "🧪 Test the updated agent:"
echo "aws lambda invoke --function-name oscar-deployment-metrics-agent-new --payload '{\"actionGroup\": \"MetricsActionGroup\", \"function\": \"get_deployment_metrics\", \"parameters\": [{\"name\": \"metric_type\", \"value\": \"health\"}, {\"name\": \"service_filter\", \"value\": \"OpenSearch\"}]}' --cli-binary-format raw-in-base64-out --region us-east-1 test.json && cat test.json | jq ."