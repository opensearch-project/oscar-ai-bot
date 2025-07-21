# OSCAR - OpenSearch Conversational Automation for Releases

OSCAR is an AI-powered assistant for OpenSearch release management, leveraging Amazon Bedrock for knowledge base integration and Slack for user interaction.

## Components

- **Slack Bot**: AI-powered Slack bot with thread-based context and knowledge base integration
- **CDK Infrastructure**: Modular AWS CDK stacks for deploying the required infrastructure
- **Knowledge Base**: Amazon Bedrock knowledge base with OpenSearch documentation

## Features

- **Thread-Based Context**: Maintains conversation context within Slack threads
- **Knowledge Base Integration**: Uses Amazon Bedrock to query OpenSearch documentation
- **Emoji Reactions**: Provides visual feedback on message processing status
- **Deduplication**: Prevents duplicate responses to the same message
<!-- - **Throttling**: Rate limits requests to prevent overuse -->
- **Toggleable DM Support**: Enable or disable direct message functionality

## Deployment Options

OSCAR can be deployed using either AWS CDK or Serverless Framework:

### CDK Deployment

```bash
# Deploy using settings from .env file
./deploy_cdk.sh

# Deploy with DM functionality explicitly enabled
./deploy_cdk.sh --enable-dm

# Update just the Lambda function
./deploy_lambda.sh
```

### Serverless Framework Deployment

```bash
# Deploy with Serverless Framework
./deploy_serverless.sh

# Deploy with DM functionality enabled
./deploy_serverless.sh --enable-dm
```

## Environment Variables

Create a `.env` file in the root directory with the following variables:

### Required Variables

| Variable | Description |
|----------|-------------|
| `SLACK_BOT_TOKEN` | Slack bot token |
| `SLACK_SIGNING_SECRET` | Slack signing secret |
| `KNOWLEDGE_BASE_ID` | Bedrock knowledge base ID |
| `MODEL_ARN` | Bedrock model ARN |

### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AWS_REGION` | AWS region | us-east-1 |
| `SESSIONS_TABLE_NAME` | DynamoDB sessions table name | oscar-sessions-v2 |
| `CONTEXT_TABLE_NAME` | DynamoDB context table name | oscar-context |
| `DEDUP_TTL` | Deduplication TTL in seconds | 300 (5 minutes) |
| `SESSION_TTL` | Session TTL in seconds | 3600 (1 hour) |
| `CONTEXT_TTL` | Context TTL in seconds | 604800 (7 days) |
| `MAX_CONTEXT_LENGTH` | Maximum context length | 3000 |
| `CONTEXT_SUMMARY_LENGTH` | Context summary length | 500 |
| `ENABLE_DM` | Enable direct messages | false |
| `PROMPT_TEMPLATE` | Custom prompt template | Default template |
<!-- | `THROTTLE_REQUESTS_PER_MINUTE` | Maximum requests per minute per user | 5 |
| `THROTTLE_WINDOW_SECONDS` | Throttling window in seconds | 60 | -->

## Usage

### Channel Mentions

Mention the bot in any channel:
```
@oscar What's the status of OpenSearch 2.11?
```

Reply in thread to maintain context:
```
@oscar What about security issues?
```

### Direct Messages (if enabled)

Send a direct message to the bot:
```
What's new in the latest release?
```

## Development

For detailed information about the Slack bot implementation, see the [slack-bot README](slack-bot/README.md).

### Running Tests

```bash
cd slack-bot
chmod +x tests/run_tests.sh
./tests/run_tests.sh
```

## Project Structure

```
├── cdk/                    # CDK infrastructure code
│   ├── stacks/             # CDK stack definitions
│   └── app.py              # CDK app entry point
├── slack-bot/              # Slack bot implementation
│   ├── tests/              # Unit tests
│   ├── app.py              # Lambda handler
│   ├── bedrock.py          # Bedrock integration
│   ├── config.py           # Configuration management
│   ├── slack_handler.py    # Slack event handling
│   ├── storage.py          # DynamoDB storage
├── deploy_cdk.sh           # CDK deployment script
├── deploy_lambda.sh        # Lambda update script
├── deploy_serverless.sh    # Serverless Framework deployment script
└── serverless.yml          # Serverless Framework configuration
```

## License

This project is licensed under the Apache License 2.0.