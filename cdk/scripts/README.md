# OSCAR CDK Scripts

This directory contains essential deployment and management scripts for the OSCAR CDK infrastructure.

## Core Deployment Scripts

### `deploy_full_stack.py`
Main deployment script that deploys the complete OSCAR infrastructure.

**Usage:**
```bash
python scripts/deploy_full_stack.py [options]
```

**Options:**
- `--stacks STACK1 STACK2`: Deploy specific stacks only
- `--skip-validation`: Skip prerequisite validation
- `--verbose, -v`: Enable verbose logging

### `deploy_lambda_stack.py`
Focused deployment script for the Lambda stack only.

**Usage:**
```bash
python scripts/deploy_lambda_stack.py [options]
```

**Options:**
- `--skip-dependencies`: Skip dependency stack validation
- `--verbose, -v`: Enable verbose logging

## Configuration Management Scripts

### `migrate_env_to_secrets.py`
Migrates environment variables from `.env` files to AWS Secrets Manager.

**Usage:**
```bash
python scripts/migrate_env_to_secrets.py --env-file .env --secret-name oscar-central-env
```

### `extract_agent_configs.py`
Extracts Bedrock agent configurations from deployed agents.

**Usage:**
```bash
python scripts/extract_agent_configs.py --agent-id AGENT_ID --output-file config.json
```

### `extract_all_agent_configs.py`
Extracts configurations from all deployed OSCAR agents.

**Usage:**
```bash
python scripts/extract_all_agent_configs.py --output-dir configs/
```

### `validate_agent_configs.py`
Validates agent configuration files for correctness and completeness.

**Usage:**
```bash
python scripts/validate_agent_configs.py --config-dir configs/
```

## Knowledge Management Scripts

### `ingest_knowledge_docs.py`
Ingests documentation into the OSCAR Knowledge Base.

**Usage:**
```bash
python scripts/ingest_knowledge_docs.py --docs-dir knowledge_docs/ --knowledge-base-id KB_ID
```

## Validation Scripts

### `validate_deployment.py`
Basic deployment validation script that checks if all components are working.

**Usage:**
```bash
python scripts/validate_deployment.py --region us-east-1 [--verbose]
```

## Environment Variables

Scripts use the following environment variables:
- `CDK_DEFAULT_ACCOUNT` - AWS account ID
- `CDK_DEFAULT_REGION` - AWS region
- `ENVIRONMENT` - Deployment environment (dev/staging/prod)

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

## Dependencies

Install required packages:
```bash
pip install -r requirements.txt
```

## Error Handling

All scripts include error handling and logging. Use the `--verbose` flag for detailed output.