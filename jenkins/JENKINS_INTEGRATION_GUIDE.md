# Jenkins Integration for OSCAR

This document provides comprehensive information about the Jenkins integration system for OSCAR.

## 🏗️ Architecture Overview

The Jenkins integration consists of:

1. **Jenkins Lambda Function** (`oscar-jenkins-agent`) - Handles job operations
2. **Jenkins Agent (Bedrock)** - Provides conversational interface with mandatory confirmation workflow
3. **Supervisor Agent** - Routes requests and handles user authorization
4. **Message Processor** - Adds user context to all queries

## 🔐 Security Features

### User Authorization System
- **User Context Propagation**: All queries include `[USER_ID: <user_id>]` prefix
- **Authorization Action Group**: Supervisor agent can check user permissions via `check_user_authorization`
- **Allowlist Based**: Uses `AUTHORIZED_MESSAGE_SENDERS` from environment variables

### Mandatory Confirmation Workflow
- **Two-Phase Process**: Information gathering → User confirmation → Execution
- **Confirmation Parameter**: `trigger_job` requires `confirmed=true` to execute
- **Security by Default**: Jobs cannot execute without explicit confirmation

## 📋 Available Functions

### `get_job_info`
- **Purpose**: Get job details without execution
- **Parameters**: `job_name` (optional, defaults to docker-scan)
- **Usage**: Always call this first to show job details to user

### `trigger_job`
- **Purpose**: Execute Jenkins jobs
- **Parameters**: 
  - `job_name` (required): Name of Jenkins job
  - `confirmed` (required): Must be "true" to execute
  - Job-specific parameters (e.g., `IMAGE_FULL_NAME` for docker-scan)
- **Security**: Blocked unless `confirmed=true`

### `list_jobs`
- **Purpose**: List all available Jenkins jobs
- **Parameters**: None
- **Usage**: When users ask "what jobs are available?"

### `test_connection`
- **Purpose**: Test Jenkins connectivity
- **Parameters**: None
- **Usage**: Only for troubleshooting

## 🔄 Workflow Example

### User Request: "Run docker scan on alpine:3.19"

1. **Message Processor**: Adds user context
   ```
   "[USER_ID: U091B0QH1QD] Run docker scan on alpine:3.19"
   ```

2. **Supervisor Agent**: Routes to jenkins-specialist

3. **Jenkins Agent**: Follows mandatory workflow
   ```
   Step 1: get_job_info(job_name="docker-scan")
   Step 2: Present job details and ask for confirmation
   Step 3: Wait for user to say "yes" or "no"
   Step 4: If "yes": trigger_job(job_name="docker-scan", confirmed="true", IMAGE_FULL_NAME="alpine:3.19")
   ```

4. **Lambda Function**: Validates confirmation and executes job

## 🛠️ Configuration

### Environment Variables
```bash
# Jenkins Configuration
JENKINS_URL=https://build.ci.opensearch.org
JENKINS_API_TOKEN=<username:token>

# Authorization (shared with main OSCAR)
AUTHORIZED_MESSAGE_SENDERS=U091B0QH1QD,W017PN2ADN0,W017VV9TD33
```

### AWS Resources
- **Lambda Function**: `oscar-jenkins-agent`
- **Bedrock Agent**: Jenkins specialist (ID: PN1WKOJ0U7)
- **Action Groups**: jenkins-operations, user-authentication

## 📝 Agent Instructions

### For Bedrock Console (Jenkins Agent)
Copy content from `jenkins/AGENT_INSTRUCTIONS_FOR_BEDROCK_CONSOLE.md` into the Jenkins Agent instructions in AWS Bedrock Console.

Key points:
- **NEVER call `trigger_job` directly**
- **ALWAYS call `get_job_info` first**
- **ALWAYS ask for user confirmation**
- **ONLY set `confirmed=true` after user says "yes"**

## 🚀 Deployment

### Jenkins Lambda
```bash
jenkins/deployment/update_lambda.sh
```

### OSCAR Agent (includes supervisor)
```bash
deployment_scripts/deploy_oscar_agent.sh
```

## 🧪 Testing

### Direct Lambda Testing
```bash
# Test get_job_info
aws lambda invoke --function-name oscar-jenkins-agent \
  --payload '{"function":"get_job_info","parameters":[{"name":"job_name","value":"docker-scan"}]}' \
  response.json

# Test trigger_job (should fail without confirmation)
aws lambda invoke --function-name oscar-jenkins-agent \
  --payload '{"function":"trigger_job","parameters":[{"name":"job_name","value":"docker-scan"},{"name":"IMAGE_FULL_NAME","value":"alpine:3.19"}]}' \
  response.json

# Test trigger_job (should work with confirmation)
aws lambda invoke --function-name oscar-jenkins-agent \
  --payload '{"function":"trigger_job","parameters":[{"name":"job_name","value":"docker-scan"},{"name":"IMAGE_FULL_NAME","value":"alpine:3.19"},{"name":"confirmed","value":"true"}]}' \
  response.json
```

### End-to-End Testing
1. Send message in Slack: "Run docker scan on alpine:3.19"
2. Verify agent asks for confirmation
3. Reply "yes" and verify job executes
4. Reply "no" and verify job is cancelled

## 🔍 Troubleshooting

### Common Issues

1. **"Access denied" errors**
   - Check user is in `AUTHORIZED_MESSAGE_SENDERS`
   - Verify supervisor agent has user-authentication action group

2. **"Confirmation parameter" errors**
   - Ensure Jenkins agent instructions are updated in Bedrock console
   - Check agent is calling `get_job_info` first

3. **"HTTP 401 Unauthorized" errors**
   - Verify `JENKINS_API_TOKEN` is correct
   - Check token format is `username:token`

### Log Monitoring
```bash
# Jenkins Lambda logs
aws logs tail /aws/lambda/oscar-jenkins-agent --follow

# Supervisor Agent logs  
aws logs tail /aws/lambda/oscar-supervisor-agent --follow
```

## 📊 Supported Jobs

### docker-scan
- **Description**: Triggers Docker security scan
- **Parameters**: `IMAGE_FULL_NAME` (required)
- **Example**: `IMAGE_FULL_NAME=alpine:3.19`

### Pipeline central-release-promotion
- **Description**: Promotes release candidates to final release
- **Parameters**: 
  - `RELEASE_VERSION` (required): Version to promote (e.g., "2.11.0")
  - `OPENSEARCH_RC_BUILD_NUMBER` (required): OpenSearch RC build number
  - `OPENSEARCH_DASHBOARDS_RC_BUILD_NUMBER` (required): Dashboards RC build number

## 🔒 Security Best Practices

1. **Always use confirmation workflow** - Never bypass the two-phase process
2. **Validate user authorization** - Check allowlist before sensitive operations
3. **Monitor job executions** - Review logs for unauthorized attempts
4. **Rotate API tokens** - Update Jenkins tokens regularly
5. **Limit permissions** - Use least-privilege principle for Jenkins service account

## 📚 File Structure

```
jenkins/
├── lambda_function.py              # Main Lambda handler
├── jenkins_client.py               # Jenkins API client
├── job_definitions.py              # Job registry and validation
├── config.py                       # Configuration management
├── requirements.txt                # Python dependencies
├── schemas/
│   └── jenkins_action_group.json   # Bedrock action group schema
├── deployment/
│   └── update_lambda.sh            # Deployment script
└── AGENT_INSTRUCTIONS_FOR_BEDROCK_CONSOLE.md  # Agent instructions

oscar-agent/
├── app.py                          # Main OSCAR agent with auth handler
├── slack_handler/
│   └── message_processor.py        # Adds user context to queries
└── schemas/
    └── user_authentication_action_group.json  # Auth action group schema
```

This integration provides a secure, user-friendly way to execute Jenkins jobs through conversational AI while maintaining proper authorization and confirmation workflows.