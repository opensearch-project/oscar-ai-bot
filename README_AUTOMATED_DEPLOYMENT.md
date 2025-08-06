# OSCAR - Complete Automated Deployment

OSCAR is an AI-powered Slack bot that provides intelligent assistance for OpenSearch project management, metrics analysis, and documentation queries. This version includes complete automated deployment that handles all infrastructure setup.

## Features

- **Bedrock Agent Integration**: Uses Amazon Bedrock agents for intelligent query processing
- **Metrics Analysis**: Real-time access to test, build, release, and deployment metrics
- **Knowledge Base Access**: Provides accurate information from OpenSearch documentation
- **Slack Integration**: Responds to mentions and maintains conversation context
- **Serverless Architecture**: Built on AWS Lambda with DynamoDB for scalability
- **Automated Deployment**: One-command deployment of all infrastructure

## Quick Start

### Prerequisites

- AWS Account with appropriate permissions
- Slack workspace with app creation capabilities
- AWS CLI configured with credentials
- Python 3.12+ installed

### 1. Setup

```bash
git clone <repository-url>
cd OSCAR
```

### 2. Configure Environment

Create your `.env` file:

```bash
# Required Configuration
AWS_REGION=us-east-1
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_SIGNING_SECRET=your-signing-secret-here
OSCAR_BEDROCK_AGENT_ID=your-bedrock-agent-id
OSCAR_BEDROCK_AGENT_ALIAS_ID=your-bedrock-agent-alias-id

# Optional Configuration (with defaults)
SESSIONS_TABLE_NAME=oscar-sessions-v2
CONTEXT_TABLE_NAME=oscar-context
ENABLE_DM=false
DEDUP_TTL=300
SESSION_TTL=3600
CONTEXT_TTL=604800
MAX_CONTEXT_LENGTH=3000
CONTEXT_SUMMARY_LENGTH=500
AGENT_TIMEOUT=60
AGENT_MAX_RETRIES=2

# Metrics Configuration (for OpenSearch connectivity)
OPENSEARCH_HOST=your-opensearch-host
OPENSEARCH_REGION=us-east-1
OPENSEARCH_SERVICE=es
OPENSEARCH_DOMAIN_ARN=your-domain-arn
METRICS_ROLE_ARN=your-cross-account-role-arn
VPC_ID=your-vpc-id
SUBNET_IDS=subnet-1,subnet-2,subnet-3
SECURITY_GROUP_ID=your-security-group-id
LAMBDA_EXECUTION_ROLE_ARN=your-lambda-role-arn
```

### 3. Deploy Everything

```bash
# One command to deploy all infrastructure
./deploy_oscar_all.sh
```

This single command will:
- ✅ Deploy all 4 metrics Lambda functions with Bedrock permissions
- ✅ Create DynamoDB tables for session and context storage
- ✅ Deploy the supervisor Lambda function with proper IAM roles
- ✅ Create API Gateway with Slack webhook endpoint
- ✅ Configure all necessary permissions and integrations

### 4. Configure Slack App

After deployment, you'll get a webhook URL. Configure your Slack app:

1. Go to https://api.slack.com/apps
2. Select your OSCAR app (or create a new one)
3. Go to **Event Subscriptions**
4. Set **Request URL** to the webhook URL from deployment output
5. Subscribe to bot events: `app_mention`, `message.im` (if DM enabled)
6. Save changes and reinstall app to workspace

### 5. Test OSCAR

```bash
# In any Slack channel where OSCAR is invited:
@oscar hello
@oscar What is OpenSearch?
@oscar Show me test metrics for the last 7 days
@oscar What are the current build success rates?
```

## Architecture

The automated deployment creates:

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Slack App     │───▶│   API Gateway    │───▶│ Supervisor      │
│                 │    │  /slack/events   │    │ Lambda          │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                                         │
                                                         ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   DynamoDB      │◀───│  Bedrock Agent   │◀───│ Metrics Lambda  │
│ Sessions/Context│    │   Integration    │    │ Functions (4)   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## Components Deployed

### Lambda Functions
- **oscar-supervisor-agent**: Main Slack bot handler with Bedrock integration
- **oscar-test-metrics-agent-new**: Test metrics analysis
- **oscar-build-metrics-agent-new**: Build metrics analysis  
- **oscar-release-metrics-agent-new**: Release metrics analysis
- **oscar-deployment-metrics-agent-new**: Deployment metrics analysis

### Infrastructure
- **API Gateway**: REST API with `/slack/events` endpoint
- **DynamoDB Tables**: Session storage and conversation context
- **IAM Roles**: Proper permissions for all Lambda functions
- **Bedrock Permissions**: Agent access to Lambda functions

## Usage Examples

### General Queries
```
@oscar What is OpenSearch?
@oscar How do I configure security?
@oscar What are the best practices for indexing?
```

### Metrics Queries
```
@oscar Show me test coverage for the last 7 days
@oscar What are the current build success rates?
@oscar Tell me about release readiness for production
@oscar Show deployment metrics for the OpenSearch service
```

### Contextual Conversations
```
@oscar What are the test trends?
  └─ Can you explain those results in more detail?
  └─ What should we focus on improving?
```

## Monitoring

### CloudWatch Logs
- `/aws/lambda/oscar-supervisor-agent`
- `/aws/lambda/oscar-test-metrics-agent-new`
- `/aws/lambda/oscar-build-metrics-agent-new`
- `/aws/lambda/oscar-release-metrics-agent-new`
- `/aws/lambda/oscar-deployment-metrics-agent-new`

### Key Metrics
- Response times and error rates
- Agent invocation success/failure
- DynamoDB read/write operations
- API Gateway request volume

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| Bot not responding | Check CloudWatch logs for errors |
| Permission denied | Verify Bedrock agent permissions |
| Slack verification failed | Check signing secret configuration |
| Metrics not working | Verify OpenSearch connectivity and VPC settings |

### Debug Commands

```bash
# Test supervisor function
aws lambda invoke --function-name oscar-supervisor-agent \
  --payload '{"test": "connectivity"}' \
  --cli-binary-format raw-in-base64-out \
  --region us-east-1 test.json && cat test.json

# Test metrics function
aws lambda invoke --function-name oscar-test-metrics-agent-new \
  --payload '{"function": "test_basic"}' \
  --cli-binary-format raw-in-base64-out \
  --region us-east-1 test.json && cat test.json

# Check API Gateway
curl -X POST https://your-api-id.execute-api.us-east-1.amazonaws.com/prod/slack/events \
  -H "Content-Type: application/json" \
  -d '{"type": "url_verification", "challenge": "test"}'
```

## Manual Deployment (Alternative)

If you prefer manual control, you can run individual components:

```bash
# Deploy only metrics agents
./deploy_metrics.sh

# Deploy only supervisor
./deploy_oscar_supervisor.sh

# Follow manual Slack setup guide
cat SLACK_DEPLOYMENT_GUIDE.md
```

## Development

### Project Structure
```
OSCAR/
├── oscar-agent/              # Main agent implementation
│   ├── app.py               # Lambda handler
│   ├── oscar_agent.py       # Bedrock agent interface
│   ├── slack_handler.py     # Slack event processing
│   ├── storage.py           # DynamoDB storage layer
│   └── config.py            # Configuration management
├── metrics/                 # Metrics Lambda functions
│   └── lambda_function.py   # Metrics processing
├── deploy_oscar_all.sh      # Complete automated deployment
├── deploy_oscar_complete_automated.sh  # Detailed deployment script
└── .env                     # Environment configuration
```

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AWS_REGION` | Yes | - | AWS deployment region |
| `SLACK_BOT_TOKEN` | Yes | - | Slack bot token (xoxb-...) |
| `SLACK_SIGNING_SECRET` | Yes | - | Slack app signing secret |
| `OSCAR_BEDROCK_AGENT_ID` | Yes | - | Bedrock agent ID |
| `OSCAR_BEDROCK_AGENT_ALIAS_ID` | Yes | - | Bedrock agent alias ID |
| `SESSIONS_TABLE_NAME` | No | oscar-sessions-v2 | DynamoDB sessions table |
| `CONTEXT_TABLE_NAME` | No | oscar-context | DynamoDB context table |
| `ENABLE_DM` | No | false | Enable direct message support |

## Security

- All Lambda functions use least-privilege IAM roles
- DynamoDB tables use AWS managed encryption
- API Gateway uses HTTPS only
- Slack signature verification enabled
- No sensitive data logged to CloudWatch

## License

Licensed under the Apache 2.0 License. See [LICENSE](LICENSE) for details.

## Support

- Check CloudWatch logs: `/aws/lambda/oscar-supervisor-agent`
- Review deployment output for webhook URLs
- Test individual components using the debug commands above
- Create issues in the GitHub repository for bugs or feature requests