# OSCAR Deployment Scripts Guide

## Overview

This guide explains the complete deployment script setup for OSCAR, ensuring efficient and safe deployments.

## 📋 Available Scripts

### 🚀 Full Deployment Scripts (Create everything)
- **`deploy_all.sh`** - Master deployment script for all resources
- **`deploy_metrics.sh`** - Deploy all 4 metrics Lambda functions
- **`deploy_communication_handler.sh`** - Deploy communication handler Lambda
- **`deploy_slack_agent.sh`** - Deploy Slack agent Lambda (slack_handler.py, etc.)

### 🔄 Update Scripts (Code only, preserves permissions)
- **`update_all.sh`** - Update all Lambda function code
- **`update_metrics.sh`** - Update only metrics Lambda functions code
- **`update_communication_handler.sh`** - Update only communication handler code
- **`update_slack_agent.sh`** - Update only Slack agent code (slack_handler.py, communication_handler.py)

## 🎯 Usage Scenarios

### First Time Deployment
```bash
# Deploy everything from scratch
./deploy_all.sh
```

### Code Updates (Recommended)
```bash
# Update all function code while preserving permissions
./update_all.sh

# Or update specific components
./update_metrics.sh
./update_slack_agent.sh
./update_communication_handler.sh
```

### Specific Component Deployment
```bash
# Deploy only metrics functions
./deploy_metrics.sh

# Deploy only Slack agent
./deploy_slack_agent.sh
```

## 🔒 What Gets Preserved in Updates

The update scripts are designed to **NEVER** touch:
- ✅ IAM roles and permissions
- ✅ Environment variables
- ✅ VPC configurations
- ✅ API Gateway permissions
- ✅ Bedrock agent permissions
- ✅ DynamoDB permissions
- ✅ Security group settings

## 📦 What Each Script Handles

### `deploy_all.sh`
- CDK infrastructure deployment
- All 4 metrics Lambda functions
- Communication handler Lambda
- Slack agent Lambda
- Complete setup from scratch

### `deploy_metrics.sh`
- **Functions**: oscar-test-metrics-agent-new, oscar-build-metrics-agent-new, oscar-release-metrics-agent-new, oscar-deployment-metrics-agent-new
- **Creates**: IAM roles, VPC configurations, Bedrock permissions
- **Files**: metrics/lambda_function.py

### `deploy_slack_agent.sh`
- **Function**: oscar-slack-agent
- **Creates**: IAM role with DynamoDB and Bedrock permissions
- **Files**: slack_handler.py, communication_handler.py, oscar_agent.py, storage.py, config.py, app.py

### `deploy_communication_handler.sh`
- **Function**: oscar-communication-handler
- **Creates**: IAM role with Bedrock permissions
- **Files**: communication_handler.py

### Update Scripts
- **Only update**: Function code (zip file)
- **Preserve**: All configurations and permissions
- **Safe**: No risk of losing permissions

## 🧪 Testing Commands

After deployment/updates:

```bash
# Test Slack agent
@oscar hello

# Test metrics functions
aws lambda invoke --function-name oscar-build-metrics-agent-new \
  --payload '{"function": "get_build_metrics"}' \
  --cli-binary-format raw-in-base64-out \
  --region us-east-1 test.json && cat test.json | jq .

# Test communication handler
aws lambda invoke --function-name oscar-communication-handler \
  --payload '{"actionGroup": "communication-orchestration", "apiPath": "/send_automated_message"}' \
  --cli-binary-format raw-in-base64-out \
  --region us-east-1 test.json && cat test.json
```

## 🔧 Prerequisites

Ensure your `.env` file contains:
```bash
# Required
AWS_REGION=us-east-1
SLACK_BOT_TOKEN=xoxb-your-token
SLACK_SIGNING_SECRET=your-secret
OSCAR_BEDROCK_AGENT_ID=your-agent-id

# For metrics
OPENSEARCH_HOST=your-host
VPC_ID=your-vpc
SUBNET_IDS=subnet-1,subnet-2
SECURITY_GROUP_ID=your-sg
LAMBDA_EXECUTION_ROLE_ARN=your-role-arn
```

## 🚨 Important Notes

1. **Always use update scripts for code changes** - They preserve your permissions
2. **Full deployment scripts recreate everything** - Use only for initial setup or major changes
3. **Test after updates** - Use the provided test commands
4. **Monitor CloudWatch logs** - Check for any issues after deployment

## 📁 File Mapping

| Script | Primary Files Updated |
|--------|----------------------|
| `update_slack_agent.sh` | slack_handler.py, communication_handler.py, oscar_agent.py, storage.py, config.py |
| `update_metrics.sh` | metrics/lambda_function.py |
| `update_communication_handler.sh` | communication_handler.py |

This setup ensures you can safely update your code without losing any AWS permissions or configurations!