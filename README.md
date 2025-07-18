# OSCAR - OpenSearch Context-Aware Release Assistant

OSCAR is an AI-powered assistant for OpenSearch release management, leveraging Amazon Bedrock for knowledge base integration and Slack for user interaction.

## Components

- **Slack Bot**: AI-powered Slack bot with thread-based context and knowledge base integration
- **CDK Infrastructure**: Modular AWS CDK stacks for deploying the required infrastructure
  - Storage Stack: DynamoDB tables and S3 bucket
  - Lambda Stack: Lambda function and API Gateway
  - Main Stack: Combines all components with Secrets Manager
- **Knowledge Base**: Amazon Bedrock knowledge base with OpenSearch documentation

## Deployment Options

OSCAR can be deployed using either AWS CDK or Serverless Framework:

### CDK Deployment

```bash
# Deploy using settings from .env file (including ENABLE_DM)
./deploy_cdk.sh

# Deploy with DM functionality explicitly enabled (overrides .env setting)
./deploy_cdk.sh --enable-dm

# Update just the Lambda function (respects ENABLE_DM from .env)
./deploy_lambda.sh
```

### Serverless Framework Deployment

```bash
# Deploy with Serverless Framework (DM functionality disabled by default)
./deploy_serverless.sh

# Deploy with DM functionality enabled
./deploy_serverless.sh --enable-dm
```

## Environment Variables

Create a `.env` file in the root directory with the following variables:

```
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token
SLACK_SIGNING_SECRET=your-slack-signing-secret
KNOWLEDGE_BASE_ID=your-bedrock-knowledge-base-id
MODEL_ARN=arn:aws:bedrock:region:account:inference-profile/model-id
```

Optional environment variables:

```
AWS_REGION=us-west-2
SLACK_SECRETS_ARN=arn:aws:secretsmanager:region:account:secret:name
SESSIONS_TABLE_NAME=oscar-sessions
CONTEXT_TABLE_NAME=oscar-context
DEDUP_TTL=300
SESSION_TTL=3600
CONTEXT_TTL=172800
MAX_CONTEXT_LENGTH=3000
CONTEXT_SUMMARY_LENGTH=500
PROMPT_TEMPLATE=custom prompt template
```

### Environment Variable Behavior

- **Required variables** (SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET, KNOWLEDGE_BASE_ID, MODEL_ARN) are used for core functionality
- **Optional variables** provide customization of behavior and settings
- **All environment variables** from the `.env` file are passed to the Lambda function
- Command-line flags (like `--enable-dm`) override the corresponding `.env` settings

When deploying:
1. The script first checks for environment variables in the `.env` file
2. Command-line arguments override the values from the `.env` file
3. Default values are used for any variables not specified


## Features

- **Thread-Based Context**: Maintains conversation context within Slack threads
- **Knowledge Base Integration**: Uses Amazon Bedrock to query OpenSearch documentation
- **Emoji Reactions**: Provides visual feedback on message processing status
- **Deduplication**: Prevents duplicate responses to the same message
- **Toggleable DM Support**: Enable or disable direct message functionality

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

### Local Development

```bash
cd slack-bot
python socket_app.py
```

## Project Structure

```
├── cdk/                    # CDK infrastructure code
│   ├── stacks/             # CDK stack definitions
│   └── app.py              # CDK app entry point
├── slack-bot/              # Slack bot implementation
│   ├── oscar/              # Core functionality modules
│   ├── tests/              # Unit tests
│   ├── app.py              # Lambda handler
│   └── socket_app.py       # Local development app
├── deploy_cdk.sh           # CDK deployment script
├── deploy_lambda.sh        # Lambda update script
├── deploy_serverless.sh    # Serverless Framework deployment script
└── serverless.yml          # Serverless Framework configuration
```

## License

This project is licensed under the Apache License 2.0.