# OSCAR CDK Configuration Management Utilities

This directory contains utilities for managing configuration and agent definitions for the OSCAR CDK automation system.

## Overview

The configuration management utilities provide a standardized way to:
- Load configuration from multiple sources (.env files, environment variables, AWS Secrets Manager)
- Build and validate Bedrock agent configurations from JSON files
- Manage agent configuration templates and deployment artifacts

## Utilities

### ConfigLoader (`config_loader.py`)

Handles loading configuration from various sources with fallback priority:
1. AWS Secrets Manager (if specified)
2. Environment variables
3. .env files
4. Default values

**Key Features:**
- Load environment variables from .env files
- Access AWS Secrets Manager with proper error handling
- Merge configuration from multiple sources
- Validate required configuration keys

**Usage:**
```python
from utils.config_loader import ConfigLoader

# Initialize loader
config_loader = ConfigLoader(region="us-east-1")

# Load from .env file
env_config = config_loader.load_env_file(".env")

# Get specific config value with fallback
value = config_loader.get_config_value("AWS_REGION", default="us-east-1")

# Load merged configuration
merged_config = config_loader.load_merged_config(".env", secret_name="oscar-central-env")

# Validate required keys
config_loader.validate_required_config(merged_config, ["AWS_REGION", "SLACK_BOT_TOKEN"])
```

### AgentConfigBuilder (`agent_config_builder.py`)

Manages Bedrock agent configurations with support for:
- Loading agent configurations from JSON files
- Validating configuration completeness
- Creating template configurations
- Converting configurations for CDK deployment

**Key Features:**
- Type-safe configuration objects with dataclasses
- Comprehensive validation of agent configurations
- Support for action groups, knowledge bases, and collaborators
- Template generation for new agents

**Usage:**
```python
from utils.agent_config_builder import AgentConfigBuilder, FoundationModel

# Initialize builder
builder = AgentConfigBuilder("agents/configs")

# Load existing configuration
agent_config = builder.load_agent_config("privileged_agent_template")

# Validate configuration
builder.validate_agent_config(agent_config)

# Create new template
template = builder.create_template_config(
    "my-agent", 
    FoundationModel.CLAUDE_3_5_SONNET.value
)

# Save configuration
builder.save_agent_config(template, "my_agent_config")

# List all configurations
configs = builder.list_agent_configs()
```

## Directory Structure

```
cdk/
├── agents/
│   └── configs/           # Agent configuration JSON files
│       ├── privileged_agent_template.json
│       └── limited_agent_template.json
├── knowledge_docs/        # Documentation for Knowledge Base ingestion
├── scripts/              # Deployment and utility scripts
└── utils/                # Configuration management utilities
    ├── __init__.py
    ├── config_loader.py
    ├── agent_config_builder.py
    ├── test_config_utilities.py
    └── README.md
```

## Configuration Files

### Agent Configuration Format

Agent configurations are stored as JSON files in `agents/configs/` with the following structure:

```json
{
  "agent_name": "oscar-privileged-agent",
  "description": "Agent description",
  "instructions": "System instructions for the agent",
  "foundation_model": "anthropic.claude-3-5-sonnet-20241022-v2:0",
  "agent_id": "EXISTING_AGENT_ID",
  "primary_alias_id": "EXISTING_ALIAS_ID",
  "action_groups": [
    {
      "name": "action-group-name",
      "description": "Action group description",
      "lambda_function_arn": "arn:aws:lambda:region:account:function:name",
      "api_schema": { /* OpenAPI schema */ },
      "action_group_state": "ENABLED"
    }
  ],
  "knowledge_bases": [
    {
      "knowledge_base_id": "KNOWLEDGE_BASE_ID",
      "knowledge_base_state": "ENABLED",
      "retrieval_configuration": {
        "vectorSearchConfiguration": {
          "numberOfResults": 10,
          "overrideSearchType": "HYBRID"
        }
      }
    }
  ],
  "tags": {
    "Environment": "Production",
    "Project": "OSCAR"
  }
}
```

### Supported Foundation Models

- `anthropic.claude-3-5-sonnet-20241022-v2:0` (Claude 3.5 Sonnet)
- `anthropic.claude-3-5-haiku-20241022-v1:0` (Claude 3.5 Haiku)
- `anthropic.claude-3-sonnet-20240229-v1:0` (Claude 3 Sonnet)
- `anthropic.claude-3-haiku-20240307-v1:0` (Claude 3 Haiku)

## Testing

Run the test suite to verify utilities are working correctly:

```bash
cd cdk
python utils/test_config_utilities.py
```

The test suite validates:
- Configuration loading from .env files
- Environment variable merging
- Agent configuration loading and validation
- Template creation and persistence
- Configuration file listing

## Requirements

The utilities require the following Python packages:
- `boto3` - AWS SDK for Secrets Manager access
- `botocore` - AWS core library for error handling

These dependencies are included in the main CDK requirements.txt file.

## Security Considerations

- Secrets Manager access requires appropriate IAM permissions
- Configuration files may contain sensitive information and should be handled securely
- Agent configurations include ARNs and IDs that should be validated before deployment
- Environment variables are loaded from multiple sources with proper precedence handling