![oscar-banner](oscar-banner.png)

# OSCAR - AI-Powered Operations Assistant

OSCAR is a serverless multi-agent conversational AI assistant that brings intelligent automation to Slack workspaces. Built on AWS Bedrock and Lambda, it provides conversational interfaces for complex operations like Jenkins job management, system monitoring, and team collaboration.

## Features

### Conversational AI
- **Natural Language Processing**: Understand complex requests in plain English
- **Context Awareness**: Maintains conversation history and context across interactions
- **Multi-Agent Architecture**: Specialized agents for different domains (Jenkins, monitoring, etc.)

### Operations Automation
- **Jenkins Integration**: Secure job execution with mandatory confirmation workflows
- **System Monitoring**: Real-time metrics and performance tracking
- **User Authorization**: Role-based access control with audit trails

### Developer Experience
- **Slack Native**: Seamless integration with existing Slack workflows
- **Serverless Architecture**: Auto-scaling AWS Lambda functions
- **Infrastructure as Code**: CDK-based deployment and management

## Use Cases

- **DevOps Teams**: Execute Jenkins jobs, monitor deployments, manage releases
- **Engineering Teams**: Automate routine tasks, get system status, troubleshoot issues
- **Operations Teams**: Monitor metrics, manage infrastructure, coordinate responses

## Architecture

OSCAR uses a modular, event-driven architecture:

```
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐
│    Slack    │───▶│   Gateway    │───▶│  Supervisor     │
│   Events    │    │   Lambda     │    │    Agent        │
└─────────────┘    └──────────────┘    └─────────────────┘
                                                │
                   ┌────────────────────────────┼────────────────────────────┐
                   │                            │                            │
            ┌──────▼──────┐              ┌──────▼──────┐              ┌──────▼──────┐
            │   Jenkins   │              │  Metrics    │              │   Future    │
            │  Specialist │              │  Specialist │              │ Specialists │
            └─────────────┘              └─────────────┘              └─────────────┘
```

## Project Structure

```
oscar-ai-bot/
├── app.py                       # CDK application entry point
├── stacks/                      # CDK stack definitions
│   ├── permissions_stack.py        # IAM roles and policies
│   ├── secrets_stack.py            # Secrets Manager configuration
│   ├── storage_stack.py            # DynamoDB tables
│   ├── vpc_stack.py                # VPC and networking
│   ├── knowledge_base_stack.py     # Bedrock Knowledge Base
│   ├── lambda_stack.py             # Lambda functions
│   ├── api_gateway_stack.py        # REST API for Slack
│   └── bedrock_agents_stack.py     # Bedrock agents (supervisor + collaborators)
├── lambda/                         # Lambda function source code
│   ├── oscar-agent/                # Main Slack bot handler
│   ├── oscar-communication-handler/ # Bedrock action group for messaging
│   └── knowledge-base/             # Upload and sync docs
├── agents/                         # Collaborator agent modules
│   ├── base_agent.py               # Abstract agent interface
│   ├── jenkins/                    # Jenkins job operations
│   └── metrics/                    # Build, test, and release metrics
│       └── lambda/                 # Metrics Lambda code
├── tests/                       # Test suite (see Testing section)
├── utils/                       # Shared utilities
├── Pipfile                      # Python dependencies (pipenv)
└── Pipfile.lock                 # Locked dependency versions
```

## Developer Guide

Please refer to [DEVELOPER_GUIDE.md](./DEVELOPER_GUIDE.md) on how to start developing and deploy OSCAR.

## Key Components

### Supervisor Agent
- Routes requests to specialized agents
- Handles user authorization and context
- Manages conversation flow and error handling

### Jenkins Integration
- Secure job execution with confirmation workflows
- Dynamic job discovery and parameter validation
- Real-time progress monitoring with workflow URLs

### Metrics System
- Build, integration test, and release readiness metrics from OpenSearch
- Deduplication and filtering of test results across platforms and architectures
- Summary generation for release decision-making

### Infrastructure
- CDK-based AWS resource management
- DynamoDB for conversation storage
- Lambda functions with proper IAM roles

## Security

- **User Authorization**: Allowlist-based access control
- **Confirmation Workflows**: Mandatory approval for sensitive operations
- **Audit Trails**: Complete logging of all operations
- **Secrets Management**: AWS Secrets Manager integration
- **Least Privilege**: Minimal IAM permissions per component

OSCAR transforms complex operations into simple conversations, making powerful automation accessible to every team member.

