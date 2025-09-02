# OSCAR CDK Deployment

This directory contains the AWS Cloud Development Kit (CDK) code for deploying the complete OSCAR infrastructure.

## Architecture

The CDK deployment creates a modular, serverless architecture with the following components:

### Core Infrastructure
- **Permissions Stack**: IAM roles and policies with least-privilege access
- **Secrets Stack**: AWS Secrets Manager for secure configuration
- **Storage Stack**: DynamoDB tables for session and context data
- **VPC Stack**: Optional VPC configuration for Lambda functions
- **API Gateway Stack**: HTTP endpoints for Slack integration
- **Knowledge Base Stack**: Bedrock Knowledge Base for document retrieval
- **Lambda Stack**: All Lambda functions for OSCAR operations
- **Agents Stack**: Bedrock agents for AI-powered interactions

## Quick Start

1. **Set up environment variables:**
   ```bash
   export CDK_DEFAULT_ACCOUNT=your-account-id
   export CDK_DEFAULT_REGION=us-east-1
   export ENVIRONMENT=dev
   ```

2. **Deploy complete infrastructure:**
   ```bash
   python scripts/deploy_full_stack.py
   ```

3. **Validate deployment:**
   ```bash
   python scripts/validate_deployment.py
   ```

## Environment Configuration

The deployment uses environment variables from the `.env` file:

### Required Variables
- `CDK_DEFAULT_ACCOUNT`: AWS account ID
- `CDK_DEFAULT_REGION`: AWS region

### Optional Variables
- `ENVIRONMENT`: Deployment environment (dev/staging/prod)
- `SESSIONS_TABLE_NAME`: DynamoDB sessions table name
- `CONTEXT_TABLE_NAME`: DynamoDB context table name
- `VPC_ID`: Existing VPC ID (if using VPC)
- `USE_VPC`: Enable VPC deployment (true/false)

## Stack Dependencies

Stacks are deployed in the following order:
1. **OscarPermissionsStack** - IAM roles and policies
2. **OscarSecretsStack** - Secrets Manager configuration
3. **OscarStorageStack** - DynamoDB tables
4. **OscarVpcStack** - VPC configuration (optional)
5. **OscarApiGatewayStack** - API Gateway endpoints
6. **OscarKnowledgeBaseStack** - Bedrock Knowledge Base
7. **OscarLambdaStack** - Lambda functions
8. **OscarAgentsStack** - Bedrock agents

## Deployment Scripts

- **`scripts/deploy_full_stack.py`**: Deploy all stacks
- **`scripts/deploy_lambda_stack.py`**: Deploy only Lambda stack
- **`scripts/validate_deployment.py`**: Validate deployment
- **`scripts/migrate_env_to_secrets.py`**: Migrate env vars to Secrets Manager

See `scripts/README.md` for detailed script documentation.

## Configuration Files

- **`cdk.json`**: CDK app configuration
- **`.env`**: Environment variables
- **`requirements.txt`**: Python dependencies
- **`agents/configs/`**: Bedrock agent configurations
- **`knowledge_docs/`**: Knowledge base documents

## Troubleshooting

### Common Issues

1. **Missing environment variables**: Ensure `CDK_DEFAULT_ACCOUNT` and `CDK_DEFAULT_REGION` are set
2. **Permission errors**: Verify AWS credentials have necessary permissions
3. **Stack dependencies**: Deploy stacks in the correct order using `deploy_full_stack.py`

### Debugging

```bash
# Verbose deployment
python scripts/deploy_full_stack.py --verbose

# Check specific stack
cdk deploy OscarLambdaStack --debug

# Validate deployment
python scripts/validate_deployment.py --verbose
```

## Clean Up

To remove all deployed resources:

```bash
cdk destroy --all
```

## Support

For deployment issues:
1. Check the logs for detailed error messages
2. Verify prerequisites and dependencies
3. Ensure AWS credentials are properly configured
4. Review the script documentation