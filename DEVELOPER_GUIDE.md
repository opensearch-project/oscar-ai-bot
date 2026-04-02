# Developer Guide

This project contains the AWS CDK infrastructure code for OSCAR (OpenSearch Conversational AI Release Assistant).

## 🏗️ Infrastructure Components

The CDK deploys:
- **Lambda Functions**: All OSCAR agent implementations
- **DynamoDB Table**: Session and context management
- **IAM Roles & Policies**: Security and permissions
- **API Gateway**: Slack integration endpoint
- **Secrets Manager**: Centralized configuration
- **Bedrock Agents**: Main as well as collaborator bedrock agents. 

## 📋 CDK Stacks

| Stack | Purpose | Resources |
|-------|---------|-----------|
| `OscarPermissionsStack` | IAM roles and policies | Bedrock agent role, Lambda execution roles (base, Jenkins, metrics), API Gateway role |
| `OscarSecretsStack` | Configuration management | Central secret (`oscar-central-env-{env}`) with all environment variables |
| `OscarStorageStack` | Data persistence | DynamoDB table for session/context/deduplication with TTL and monitoring |
| `OscarVpcStack` | Networking | VPC, security groups, VPC endpoints (S3, DynamoDB, Secrets Manager) |
| `OscarKnowledgeBaseStack` | Bedrock Knowledge Base | S3 bucket, OpenSearch Serverless collection, document sync Lambda |
| `OscarLambdaStack` | Compute functions | Supervisor agent, Jenkins agent, metrics agent (VPC-enabled) |
| `OscarApiGatewayStack` | Slack integration | REST API (`POST /slack/events`) with Lambda proxy integration |
| `OscarAgentsStack` | Bedrock Agents | Supervisor agents (privileged & limited), collaborator agents (Jenkins, Build, Test, Release) |

_Please note: Stacks have dependencies on each other and needs to be deployed in a specific order. Check app.py for more details_
## 🔨 Build Tools

### Pyenv

Use pyenv to manage multiple versions of Python. This can be installed with [pyenv-installer](https://github.com/pyenv/pyenv-installer) on Linux and MacOS, and [pyenv-win](https://github.com/pyenv-win/pyenv-win#installation) on Windows.

```
curl -L https://github.com/pyenv/pyenv-installer/raw/master/bin/pyenv-installer | bash
```

### Python 3.12

Python projects in this repository use Python 3.12. See the [Python Beginners Guide](https://wiki.python.org/moin/BeginnersGuide) if you have never worked with the language.
```bash
$ python --version
Python 3.12.12
```

If you are using pyenv.

```
$ pyenv install 3.12.12
$ pyenv global 3.12.12
```

### Pipenv
This project uses [pipenv](https://pipenv.pypa.io/en/latest/), which is typically installed with `pip install --user pipenv` or use whatever fits your local OS. Pipenv automatically creates and manages a virtualenv for your projects, as well as adds/removes packages from your `Pipfile` as you install/uninstall packages. It also generates the ever-important `Pipfile.lock`, which is used to produce deterministic builds.

```bash
$ pipenv --version
pipenv, version 2026.0.3
```
### Install Dependencies

```bash
$ pipenv install
To activate this project's virtualenv, run pipenv shell.
Alternatively, run a command inside the virtualenv with pipenv run.
Installing dependencies from Pipfile.lock (6657ff)...
```

### Docker

This project uses [`PythonFunction`](https://docs.aws.amazon.com/cdk/api/v2/python/aws_cdk.aws_lambda_python_alpha/PythonFunction.html) to deploy Lambda functions. `PythonFunction` builds Lambda packages inside a Docker container to ensure dependencies are compiled for the Lambda runtime environment. **Docker must be running** before executing `cdk synth` or `cdk deploy`.

```bash
# Verify Docker is running
docker info
```

## ⚙️ Configuration

### Slack App Configuration

1. Go to https://api.slack.com/apps
2. Select **Event Subscriptions** → Set Request URL to your API Gateway endpoint
3. Subscribe to bot events (`message.channels`, `app_mention`)
4. Install app to workspace
5. Go to **OAuth and Permissions**
   - Get Bot OAuth Token (store in Secrets Manager as `SLACK_BOT_TOKEN`)
   - Set Bot Token Scopes: `app_mentions:read`, `channels:history`, `channels:read`, `chat:write`, `commands`, `im:history`, `im:read`, `im:write`, `reactions:write`
6. `@bot_name` in a channel to add the bot

Configuration is split into two categories:

### Secrets Manager (Sensitive Values)

Sensitive values are stored in AWS Secrets Manager in **JSON format** — never in `.env` or Lambda environment variables.

After deploying `OscarSecretsStack`, populate the central secret:

```bash
aws secretsmanager put-secret-value \
  --secret-id oscar-central-env-dev \
  --secret-string '{
    "SLACK_BOT_TOKEN": "xoxb-your-bot-token",
    "SLACK_SIGNING_SECRET": "your-signing-secret",
    "DM_AUTHORIZED_USERS": "U12345678,U87654321",
    "FULLY_AUTHORIZED_USERS": "U12345678",
    "CHANNEL_ALLOW_LIST": "C12345678,C87654321"
  }'
```

| Key | Description |
|-----|-------------|
| `SLACK_BOT_TOKEN` | Bot OAuth token from Slack app settings |
| `SLACK_SIGNING_SECRET` | Signing secret for verifying Slack webhooks |
| `DM_AUTHORIZED_USERS` | Comma-separated Slack user IDs allowed to DM the bot |
| `FULLY_AUTHORIZED_USERS` | Comma-separated user IDs with full access (Jenkins, communication) |
| `CHANNEL_ALLOW_LIST` | Comma-separated channel IDs the bot responds in |

Agent-specific secrets (e.g., Jenkins API token) are documented in each agent's README.

### Non-Sensitive Configuration (`.env`)

Non-sensitive config is set via `.env` file (loaded by CDK at deploy time). All values have sensible defaults — override only what you need.

```bash
cp .env.example .env
```

See `.env.example` for the full list of configurable values with defaults.

## 🔧 Key Files

| File | Purpose                                                     |
|------|-------------------------------------------------------------|
| `app.py` | CDK application entry point                                 |
| `.env` | Non-sensitive config (loaded by CDK at deploy time)         |
| `.env.example` | Reference for all configurable values                       |
| `stacks/` | CDK stack definitions                                       |
| `agents/` | Agents per functionality (one per collaborator agent)       |
| `lambda/` | Core Lambda source code (supervisor, communication handler) |

## 🧪 Testing

```bash
# Run all tests
pipenv run python -m pytest

# Run a specific test area
pipenv run python -m pytest tests/stacks/
pipenv run python -m pytest tests/agents/
pipenv run python -m pytest tests/lambda/

# Run with coverage
pipenv run coverage run -m pytest
pipenv run coverage report --show-missing
```

Tests are organized to mirror the source tree.

Key conventions:
- CDK tests use `Template.from_stack()` with `resource_count_is()` and `has_resource_properties()`
- Lambda tests mock the `config` module at `sys.modules` level to prevent AWS calls during import
- DynamoDB/Secrets Manager/SSM tests use `moto` (`@mock_aws`)
- Every test imports and calls real production code — no reimplementing logic in tests

## 🎨 Code Style

This project uses [flake8](https://flake8.pycqa.org/) for linting and [isort](https://pycqa.github.io/isort/) for import sorting. Configuration is in `.flake8`.

```bash
# Lint the entire project
pipenv run flake8 .

# Sort imports
pipenv run isort .

# Check imports without modifying
pipenv run isort --check-only .
```

Key style rules (see `.flake8`):
- Ignored: `E722` (bare except — intentional in VPC fallback logic), `E501` (line length — no limit enforced)
- Excluded: `cdk.out`, `venv`, `tests`

## 🔍 Type Checking

This project uses [mypy](https://mypy.readthedocs.io/) for static type checking. Configuration is in `mypy.ini`.

```bash
# Type check the project
pipenv run mypy .
```

Key mypy settings (see `mypy.ini`):
- `ignore_missing_imports = true` — CDK and Slack libraries don't ship stubs
- `explicit_package_bases = true` — required due to hyphenated directory names in `lambda/`
- `exclude` — skips `cdk.out`, `venv`, `tests`, and `lambda`

When adding new code, use type annotations:
```python
from typing import Any, Dict, List, Optional

def my_function(agents: Optional[List] = None) -> Dict[str, Any]:
    ...
```

## 🚀 Deployment

**In order to deploy all the stacks**:
```bash
# From project root
pipenv run cdk deploy "*"

```
**Deploy each stack individually**:
```bash
pipenv run cdk deploy <stack_name>
```

## 🧹 Cleanup

**Remove all resources**:
```bash
pipenv run cdk destroy --all
```

**Note**: Some resources like S3 buckets may need manual cleanup if they contain data.

**Useful Commands**:
```bash
cdk ls                    # List all stacks
cdk diff                  # Show changes
cdk synth                 # Generate CloudFormation
cdk doctor                # Check CDK setup
```
