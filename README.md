# OSCAR - OpenSearch Conversational Automation for Release

OSCAR is an AI-powered assistant designed to help with OpenSearch project management, documentation queries, and release coordination through Slack integration.

## Features

- **Slack Integration**: Interact with OSCAR through Slack mentions and direct messages
- **Knowledge Base**: Access OpenSearch documentation and best practices  
- **Metrics Analysis**: Get insights on test failures, build performance, and release status
- **Multi-Agent Architecture**: Specialized agents for different domains with VPC deployment

## Quick Start

1. **Environment Setup**:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

2. **Complete Deployment**:
   ```bash
   ./deploy_oscar_complete.sh
   ```

3. **Follow Slack Integration Instructions**: The deployment script provides detailed steps

## Project Structure

```
oscar-agent/              # Core OSCAR supervisor agent
├── app.py               # Lambda handler for Slack integration
├── oscar_agent.py       # Enhanced Bedrock agent interface
├── slack_handler.py     # Slack event processing
├── storage.py           # DynamoDB session/context management
├── config.py            # Configuration management
└── requirements.txt     # Python dependencies

metrics/                 # VPC-deployed metrics agents
├── lambda_function.py   # Metrics Lambda handler
├── opensearch_client.py # OpenSearch VPC connectivity
├── metrics_service.py   # Metrics data processing
├── config.py           # Metrics configuration
└── requirements.txt    # Python dependencies

build_docs/             # Documentation and guides
├── MANUAL_AGENT_CONFIGURATION.md
├── METRICS_SYSTEM_OVERVIEW.md
└── ...

cdk/                    # Infrastructure as Code (optional)
old_codebase/          # Reference implementation
```

## Architecture

OSCAR uses an enhanced multi-agent architecture:

### Core Components

- **Supervisor Agent** (`oscar-supervisor-agent`): Main Slack interface with knowledge base integration
- **VPC Metrics Agents**: Specialized Lambda functions deployed in VPC for OpenSearch access
  - `oscar-test-metrics-agent`: Test failure analysis
  - `oscar-build-metrics-agent`: Build performance metrics  
  - `oscar-release-metrics-agent`: Release status tracking
  - `oscar-deployment-metrics-agent`: Deployment health monitoring

### Key Features

- **VPC Deployment**: Metrics agents deployed in VPC for secure OpenSearch access
- **Session Management**: DynamoDB-based conversation context preservation
- **Mock Mode**: Fallback mode for testing without OpenSearch connectivity
- **Enhanced Error Handling**: Comprehensive retry logic and user-friendly error messages

## Configuration

Key environment variables in `.env`:

```bash
# Slack Configuration
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_SIGNING_SECRET=your-signing-secret

# Bedrock Agent Configuration  
OSCAR_BEDROCK_AGENT_ID=your-agent-id
OSCAR_BEDROCK_AGENT_ALIAS_ID=your-alias-id

# DynamoDB Tables
SESSIONS_TABLE_NAME=oscar-sessions
CONTEXT_TABLE_NAME=oscar-context

# VPC Configuration (for metrics agents)
VPC_ID=vpc-xxxxxxxxx
SUBNET_IDS=subnet-xxx,subnet-yyy,subnet-zzz
SECURITY_GROUP_ID=sg-xxxxxxxxx

# OpenSearch Configuration
OPENSEARCH_HOST=your-opensearch-endpoint
OPENSEARCH_VPC_ENDPOINT_ID=vpce-xxxxxxxxx
```

## Deployment

### Prerequisites

- AWS CLI configured with appropriate permissions
- Python 3.9+
- Access to AWS Bedrock, Lambda, DynamoDB, VPC services

### Complete Deployment

```bash
# Deploy all components
./deploy_oscar_complete.sh
```

This script will:
1. Deploy VPC Lambda functions for metrics
2. Deploy supervisor agent for Slack integration
3. Test all deployments
4. Provide detailed Slack integration instructions

### Individual Component Deployment

```bash
# Deploy only VPC metrics agents
./deploy_vpc_lambdas.sh

# Deploy only supervisor agent
./deploy_oscar_supervisor.sh
```

## Slack Integration Setup

After deployment, complete these manual steps:

### 1. Configure Bedrock Agent
- Update action group Lambda function to use `oscar-supervisor-agent` ARN
- Create new agent version and update alias

### 2. Create API Gateway
- Create REST API for Slack webhook
- Configure `/slack` POST endpoint
- Point to `oscar-supervisor-agent` Lambda function
- Deploy to production stage

### 3. Configure Slack App
- Set Event Subscriptions URL to API Gateway endpoint
- Subscribe to `app_mention` and `message.im` events
- Install app to workspace

### 4. Test Integration
```bash
# In Slack channel
@oscar What is OpenSearch?
```

## Usage Examples

### Knowledge Base Queries
- `@oscar What is OpenSearch?`
- `@oscar How do I configure security?`
- `@oscar Explain OpenSearch architecture`

### Metrics Queries  
- `@oscar Show me current test failures`
- `@oscar What are the build metrics for last week?`
- `@oscar Release status for version 2.x`
- `@oscar Deployment health summary`

## Monitoring and Troubleshooting

### CloudWatch Logs
```bash
# Monitor supervisor agent
aws logs tail /aws/lambda/oscar-supervisor-agent --follow

# Monitor metrics agents
aws logs tail /aws/lambda/oscar-test-metrics-agent --follow
```

### Test Functions
```bash
# Test supervisor
aws lambda invoke --function-name oscar-supervisor-agent \
  --payload '{"test": "connectivity"}' \
  --cli-binary-format raw-in-base64-out result.json

# Test metrics agent
aws lambda invoke --function-name oscar-test-metrics-agent \
  --payload '{"test": "connectivity"}' \
  --cli-binary-format raw-in-base64-out result.json
```

### Common Issues

1. **Metrics agents timeout**: Functions use mock mode if OpenSearch unreachable
2. **Slack webhook failures**: Check API Gateway configuration and deployment
3. **Bedrock agent errors**: Verify agent ID, alias, and Lambda ARN configuration
4. **VPC connectivity**: Ensure proper security groups and NAT Gateway setup

## Development

### Local Testing
```bash
cd oscar-agent
pip install -r requirements.txt
python -m pytest tests/
```

### Adding New Metrics
1. Extend `metrics_service.py` with new query methods
2. Update routing in `lambda_function.py`
3. Add mock data for testing
4. Deploy with `./deploy_vpc_lambdas.sh`

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes and add tests  
4. Submit a pull request

## License

This project is licensed under the Apache 2.0 License - see the LICENSE file for details.