# OSCAR - OpenSearch Conversational Automation for Release

OSCAR is an AI-powered Slack bot that provides intelligent assistance for OpenSearch project management and documentation queries. Built with Amazon Bedrock agents, it delivers accurate, contextual responses from the official OpenSearch knowledge base.

## Features

- **Bedrock Agent Integration**: Uses Amazon Bedrock agents for intelligent query processing
- **Knowledge Base Access**: Provides accurate information from OpenSearch documentation
- **Slack Integration**: Responds to mentions and maintains conversation context
- **Serverless Architecture**: Built on AWS Lambda with DynamoDB for scalability
- **Context Preservation**: Maintains conversation history across threaded discussions

## Architecture

OSCAR uses a modern serverless architecture:

- **AWS Lambda**: Processes Slack events and coordinates agent interactions
- **Amazon Bedrock Agent**: Handles intelligent query processing with knowledge base integration
- **DynamoDB**: Stores conversation context and session management
- **API Gateway**: Manages Slack webhook requests
- **CloudWatch**: Provides comprehensive logging and monitoring

## Quick Start

### Prerequisites

- AWS Account with Bedrock and Lambda permissions
- Slack workspace with app creation capabilities
- Python 3.12+ and AWS CDK v2 installed
- AWS CLI configured with appropriate credentials

### 1. Setup

```bash
git clone <repository-url>
cd OSCAR
```

### 2. Configure Environment

Create and configure your `.env` file:

```bash
# Slack Configuration
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_SIGNING_SECRET=your-signing-secret

# AWS Configuration
AWS_REGION=us-west-2
AWS_ACCOUNT_ID=your-account-id

# OSCAR Agent Configuration
OSCAR_BEDROCK_AGENT_ID=your-agent-id
OSCAR_BEDROCK_AGENT_ALIAS_ID=your-agent-alias-id
```

### 3. Deploy

```bash
./deploy_oscar_agent.sh
```

### 4. Configure Slack App

1. Create a Slack app at https://api.slack.com/apps
2. Set Event Subscriptions URL to your API Gateway endpoint
3. Subscribe to `app_mention` events
4. Install the app to your workspace

## Usage

### Basic Queries

```
@oscar What is OpenSearch?
@oscar How do I configure OpenSearch security?
@oscar What are the indexing best practices?
```

### Threaded Conversations

OSCAR maintains context in threads:

```
@oscar How do I install OpenSearch?
  └─ Follow up: What about Docker installation?
  └─ Follow up: How do I configure it for production?
```

## Project Structure

```
OSCAR/
├── oscar-agent/           # Main agent implementation
│   ├── app.py            # Lambda handler
│   ├── oscar_agent.py    # Bedrock agent interface
│   ├── slack_handler.py  # Slack event processing
│   ├── storage.py        # DynamoDB storage layer
│   └── config.py         # Configuration management
├── cdk/                  # Infrastructure as code
│   └── stacks/           # CDK stack definitions
├── .kiro/                # Kiro IDE configuration
└── deploy_oscar_agent.sh # Deployment script
```

## Configuration

### Required Environment Variables

| Variable | Description |
|----------|-------------|
| `OSCAR_BEDROCK_AGENT_ID` | Your Bedrock agent ID |
| `OSCAR_BEDROCK_AGENT_ALIAS_ID` | Your Bedrock agent alias ID |
| `SLACK_BOT_TOKEN` | Slack bot token (xoxb-...) |
| `SLACK_SIGNING_SECRET` | Slack app signing secret |
| `AWS_REGION` | AWS deployment region |
| `AWS_ACCOUNT_ID` | Your AWS account ID |

### Optional Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SESSIONS_TABLE_NAME` | oscar-sessions-v2 | DynamoDB sessions table |
| `CONTEXT_TABLE_NAME` | oscar-context | DynamoDB context table |
| `ENABLE_DM` | false | Enable direct message support |

## Monitoring

### CloudWatch Logs

Monitor at: `/aws/lambda/oscar-slack-bot`

### Key Metrics

- Response times and error rates
- Agent invocation success/failure
- DynamoDB read/write operations
- Slack event processing metrics

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| Bot not responding | Check CloudWatch logs for errors |
| Permission denied | Verify Bedrock agent permissions |
| Slack verification failed | Check signing secret configuration |
| Agent not found | Verify agent ID and alias are correct |

### Debug Steps

1. Check CloudWatch logs: `/aws/lambda/oscar-slack-bot`
2. Verify agent status in Bedrock console
3. Test agent directly in Bedrock console
4. Validate Slack app configuration

## Development

### Local Testing

The deployment script includes validation and testing:

```bash
# Test configuration
python oscar-agent/test_agent.py

# Deploy with validation
./deploy_oscar_agent.sh
```

### Code Style

- Python 3.12+ with type hints
- Comprehensive error handling
- Structured logging
- Clean architecture principles

## License

Licensed under the Apache 2.0 License. See [LICENSE](LICENSE) for details.

## Support

- Create issues in the GitHub repository
- Check CloudWatch logs for debugging: `/aws/lambda/oscar-slack-bot`
- Review the `.kiro/oscar-agent-refactor/` documentation for detailed design information