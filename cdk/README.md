# OSCAR CDK Deployment

This directory contains the AWS Cloud Development Kit (CDK) code for deploying the OSCAR Slack bot infrastructure.

## Architecture

The CDK deployment creates a modular, serverless architecture for the OSCAR Slack bot with the following components:

### Storage Resources
- **DynamoDB Tables**:
  - `oscar-sessions`: Stores active Bedrock sessions with 1-hour TTL
  - `oscar-context`: Stores conversation context with configurable TTL (default 48 hours)
- **S3 Bucket**: Stores documentation for the knowledge base

### Serverless Compute
- **Lambda Function**: Processes Slack events and interacts with the knowledge base
- **API Gateway**: HTTP endpoint for receiving Slack events

### Security
- **Secrets Manager**: Securely stores Slack credentials
- **IAM Roles**: Provides least-privilege permissions for all components

## Stack Organization

The CDK code is organized into modular stacks for better maintainability:

- **OscarSlackBotStack** (`oscar_slack_bot_stack.py`): Main stack that combines all components
- **OscarStorageStack** (`storage_stack.py`): DynamoDB tables and S3 bucket for data storage
- **OscarLambdaStack** (`lambda_stack.py`): Lambda function and API Gateway for request processing

## Prerequisites

1. **AWS Account** with appropriate permissions
2. **AWS CLI** installed and configured
3. **Node.js and npm** installed (for CDK)
4. **Python 3.9+** installed
5. **Slack Workspace** where you have permissions to create apps

## Environment Variables

The deployment uses the following environment variables, which can be set in a `.env` file in the root directory:

### Required Variables
- `KNOWLEDGE_BASE_ID`: ID of your Amazon Bedrock knowledge base
- `MODEL_ARN`: ARN of the Bedrock model to use (e.g., Claude)
- `SLACK_BOT_TOKEN`: Bot token from your Slack app
- `SLACK_SIGNING_SECRET`: Signing secret from your Slack app

### Optional Variables
- `SESSIONS_TABLE_NAME`: Name of the DynamoDB table for sessions (default: "oscar-sessions")
- `CONTEXT_TABLE_NAME`: Name of the DynamoDB table for context (default: "oscar-context")
- `DEDUP_TTL`: Time-to-live for deduplication records in seconds (default: 300)
- `SESSION_TTL`: Time-to-live for session records in seconds (default: 3600)
- `CONTEXT_TTL`: Time-to-live for context records in seconds (default: 172800)
- `MAX_CONTEXT_LENGTH`: Maximum length of context summary (default: 3000)
- `CONTEXT_SUMMARY_LENGTH`: Length of context summary for each interaction (default: 500)
- `PROMPT_TEMPLATE`: Custom prompt template for the Bedrock model

## Deployment Instructions

### Option 1: Using the Deployment Script

The easiest way to deploy is using the provided script:

```bash
# From the root directory
./deploy_cdk.sh
```

This script will:
1. Load environment variables from `.env`
2. Run tests to ensure everything is working correctly
3. Bootstrap the CDK environment if needed
4. Deploy all required AWS resources
5. Update the Lambda function with the full code
6. Configure Secrets Manager with your Slack credentials

### Option 2: Manual Deployment

If you prefer to deploy manually:

```bash
# Install dependencies
cd cdk
pip install -r requirements.txt

# Bootstrap CDK (if not already done)
cdk bootstrap aws://ACCOUNT-NUMBER/REGION

# Deploy the stack
cdk deploy
```

### Command Line Options

The `deploy_cdk.sh` script supports the following options:

- `-a, --account ACCOUNT_ID`: AWS Account ID (default: extracted from .env)
- `-r, --region REGION`: AWS Region (default: extracted from .env)
- `--enable-dm`: Enable direct message functionality (overrides .env setting)
- `-h, --help`: Show help message

## Configuration

### Slack App Configuration

After deployment, you'll need to configure your Slack app:

1. Go to your Slack App configuration at https://api.slack.com/apps
2. Select your OSCAR app
3. Go to "Event Subscriptions"
4. Toggle "Enable Events" to On
5. Enter the webhook URL from the deployment output as the Request URL
6. Under "Subscribe to bot events", add:
   - `app_mention`
   - `message.im` (if DM functionality is enabled)
7. Click "Save Changes"

### Environment Variable Behavior

- Values in the `.env` file are used as defaults
- Command-line flags (like `--enable-dm`) override the corresponding `.env` settings
- Default values are used for any variables not specified

## Customization

### Lambda Function

You can customize the Lambda function by modifying `lambda_stack.py`:

- **Memory**: Change `memory_size` (default: 512 MB)
- **Timeout**: Adjust `timeout` (default: 30 seconds)
- **Environment Variables**: Add or modify variables in `_get_lambda_environment_variables()`

### Storage

You can customize the storage resources by modifying `storage_stack.py`:

- **Table Names**: Change the table names
- **Billing Mode**: Switch between PAY_PER_REQUEST and PROVISIONED
- **S3 Configuration**: Add lifecycle rules, encryption, etc.

### API Gateway

You can customize the API Gateway by modifying the `api` resource in `lambda_stack.py`:

- **Throttling**: Add rate limiting (the reason an intermediate API gateway is so useful)
- **Authorization**: Add API key or other authorization methods
- **CORS**: Configure cross-origin resource sharing

## Troubleshooting

### Common Issues

1. **Deployment Fails with Region Error**:
   - Ensure you're specifying the correct region with `-r` flag
   - Check that AWS CLI is configured correctly

2. **Lambda Function Errors**:
   - Check CloudWatch Logs for detailed error messages
   - Verify that all environment variables are set correctly
   - Ensure Secrets Manager contains valid Slack credentials

3. **Slack Integration Issues**:
   - Verify the webhook URL is correctly configured in Slack
   - Check that all required scopes are added to the Slack app
   - Ensure the bot is invited to the channel

4. **Knowledge Base Issues**:
   - Verify that the KNOWLEDGE_BASE_ID environment variable is set correctly
   - Check that the knowledge base exists and is active

### Debugging

To debug deployment issues:

```bash
# Get detailed logs during deployment
cdk deploy --debug

# Check the status of the stack
aws cloudformation describe-stacks --stack-name OscarSlackBotStack

# Check Lambda logs
aws logs filter-log-events --log-group-name /aws/lambda/oscar-slack-bot
```

## Clean Up

To remove all deployed resources:

```bash
# Using CDK
cd cdk
cdk destroy

# Or using the AWS CLI
aws cloudformation delete-stack --stack-name OscarSlackBotStack
```

## Development

### Adding New Resources

To add new AWS resources to the stack:

1. Decide which stack the resource belongs to (storage, lambda, or main)
2. Add the resource definition to the appropriate file
3. Update any dependencies or references in other stacks
4. Deploy the changes with `cdk deploy`

### Testing Changes

Before deploying changes, you can synthesize the CloudFormation template to check for errors:

```bash
cd cdk
cdk synth
```

This will generate a CloudFormation template in the `cdk.out` directory that you can review.