# OSCAR Agent Deployment System

This directory contains a comprehensive, dependency-aware deployment system for all OSCAR agents using AWS CLI commands with JSON-based configurations.

## 🏗️ System Overview

The deployment system handles:
- **6 Agent Types**: Jenkins, Build Metrics, Test Metrics, Release Metrics, OSCAR Limited, OSCAR Privileged
- **Dependency Management**: Automatic Lambda ARN updates and collaborator linking
- **Knowledge Base Integration**: Automatic association with OpenSearch documentation
- **Deployment Order**: Ensures dependencies are deployed before dependent agents
- **Update Capabilities**: Scripts to update existing agents when dependencies change

## 📁 Directory Structure

```
├── agent-configs/                    # Agent configuration directories
│   ├── jenkins/                     # Jenkins agent configs
│   ├── build-metrics/               # Build metrics agent configs
│   ├── test-metrics/                # Test metrics agent configs
│   ├── release-metrics/             # Release metrics agent configs
│   ├── oscar-limited/               # OSCAR limited supervisor configs
│   └── oscar-privileged/            # OSCAR privileged supervisor configs
├── deployment-config.json           # Master deployment configuration
├── deploy-all-agents.sh            # Main deployment script
├── update-agent-dependencies.sh    # Update existing agent dependencies
├── update-knowledge-bases.sh       # Update knowledge base associations
├── validate-deployment.sh          # Pre-deployment validation
└── test_oscar_limited_agent.sh     # Testing script
```

## 🚀 Quick Start

### Fresh Account Deployment

1. **Validate deployment readiness**:
   ```bash
   ./validate-deployment.sh
   ```
   This checks:
   - Configuration file syntax
   - IAM roles existence
   - Lambda functions availability
   - Knowledge base accessibility
   - Collaborator placeholder setup

2. **Deploy all agents**:
   ```bash
   ./deploy-all-agents.sh
   ```
   This will:
   - Deploy agents in dependency order
   - Update Lambda ARNs automatically
   - Replace collaborator placeholders with actual agent IDs
   - Link collaborators correctly
   - Associate knowledge bases
   - Create aliases for all agents
   - Save agent IDs for future updates

### Existing Account Updates

1. **Update Dependencies** (when Lambda functions change):
   ```bash
   ./update-agent-dependencies.sh oscar-limited
   ./update-agent-dependencies.sh oscar-privileged
   ```

2. **Update Knowledge Bases**:
```bash
# Update specific agent
./update-knowledge-bases.sh update-agent oscar-limited

# Update all agents with knowledge bases
./update-knowledge-bases.sh update-all

# Update knowledge base ID in configuration
./update-knowledge-bases.sh update-config opensearch-docs NEW_KB_ID
```

## 🔧 Agent Configurations

### Jenkins Agent
- **Name**: `jenkins-agent-cdk-created`
- **Lambda**: `oscar-jenkins-agent-cdk-created`
- **Functions**: `get_job_info`, `list_jobs`, `trigger_job`
- **Purpose**: Jenkins job operations with security confirmation workflow

### Build Metrics Agent
- **Name**: `build-metrics-agent-cdk-created`
- **Lambda**: `oscar-build-metrics-agent-cdk-created`
- **Functions**: `get_build_metrics`, `resolve_components_from_builds`
- **Purpose**: Distribution build analysis and component build performance

### Test Metrics Agent
- **Name**: `integration-test-agent-cdk-created`
- **Lambda**: `oscar-test-metrics-agent-cdk-created`
- **Functions**: `get_integration_test_metrics`, `get_rc_build_mapping`
- **Purpose**: Integration test failure analysis and RC-based queries

### Release Metrics Agent
- **Name**: `release-metrics-agent-cdk-created`
- **Lambda**: `oscar-release-metrics-agent-cdk-created`
- **Functions**: `get_release_metrics`
- **Purpose**: Release readiness analysis and component release status

### OSCAR Limited Supervisor
- **Name**: `oscar-supervisor-agent-limited-cdk-created`
- **Lambda**: `oscar-supervisor-agent-cdk-created`
- **Functions**: `process_oscar_query`
- **Collaborators**: Build, Test, Release Metrics agents
- **Knowledge Base**: OpenSearch documentation
- **Limitations**: No communication or Jenkins features

### OSCAR Privileged Supervisor
- **Name**: `oscar-supervisor-agent-privileged-cdk-created`
- **Lambdas**: 
  - `oscar-supervisor-agent-cdk-created` (routing)
  - `oscar-communication-handler-cdk-created` (messaging)
- **Functions**: `process_oscar_query`, `send_automated_message`
- **Collaborators**: Jenkins, Build, Test, Release Metrics agents
- **Knowledge Base**: OpenSearch documentation
- **Features**: Full communication and Jenkins capabilities

## 🔄 Dependency Management

### Automatic Updates
The system automatically handles:
- **Lambda ARN Updates**: When new Lambda functions are deployed
- **Collaborator Linking**: When dependent agents are created/updated
- **Knowledge Base Association**: When knowledge bases are created/changed

### Deployment Order
```
1. jenkins-agent
2. build-metrics-agent  
3. test-metrics-agent
4. release-metrics-agent
5. oscar-limited-supervisor (depends on metrics agents)
6. oscar-privileged-supervisor (depends on all agents)
```

### Configuration Files
Each agent has:
- **`agent-config.json`**: Main agent configuration (name, model, instructions)
- **`action-group.json`** or **`action-groups.json`**: Function schemas and Lambda ARNs
- **`knowledge-base.json`**: Knowledge base associations (if applicable)
- **`collaborators.json`**: Collaborator configurations (if applicable)

## 📊 Tracking and State Management

### Agent IDs File
The system maintains `deployed-agent-ids.json` with:
```json
{
  "jenkins": {
    "agent_id": "PN1WKOJ0U7",
    "alias_id": "MPGKGSVQZO"
  },
  "oscar-limited": {
    "agent_id": "DKGVSQJG3D", 
    "alias_id": "QMKM8LNJKC"
  }
}
```

### Master Configuration
`deployment-config.json` defines:
- Agent dependencies and deployment order
- Lambda function mappings
- Knowledge base configurations
- Collaborator relationships

## 🧪 Testing and Validation

### Pre-Deployment Validation
```bash
./validate-deployment.sh
```
Validates:
- Configuration file syntax and structure
- IAM role existence (`oscar-bedrock-agent-execution-role-cdk`)
- Lambda function availability
- Knowledge base accessibility
- Collaborator placeholder configuration

### Component-Specific Validation
```bash
./validate-deployment.sh lambda      # Check Lambda functions only
./validate-deployment.sh iam         # Check IAM roles only
./validate-deployment.sh kb          # Check knowledge bases only
./validate-deployment.sh config      # Check configuration files only
```

### Test Individual Agent
```bash
./test_oscar_limited_agent.sh
# Enter agent ID and alias ID when prompted
```

### Agent Testing Validation
The test script validates:
1. Basic agent functionality
2. Knowledge base integration
3. Limitation responses (for limited agent)
4. Function schema correctness

## 🔧 Advanced Usage

### Redeploy Specific Agent
```bash
# The script will prompt for confirmation if agent exists
./deploy-all-agents.sh
# Choose 'y' when asked about redeploying existing agents
```

### Update Only Lambda ARNs
```bash
./update-agent-dependencies.sh oscar-privileged
```

### Add New Knowledge Base
1. Update `deployment-config.json`:
```json
"knowledge_bases": {
  "new-kb": {
    "id": "NEW_KB_ID",
    "name": "New Knowledge Base"
  }
}
```

2. Update agent configuration:
```json
"knowledge_bases": ["opensearch-docs", "new-kb"]
```

3. Run update:
```bash
./update-knowledge-bases.sh update-all
```

## 🏗️ Fresh Account Deployment Requirements

### Prerequisites
Before deploying to a fresh AWS account, ensure:

1. **IAM Role**: Create `oscar-bedrock-agent-execution-role-cdk` with:
   - Bedrock agent permissions
   - Lambda invoke permissions
   - Knowledge base access permissions

2. **Lambda Functions**: Deploy all required Lambda functions:
   - `oscar-jenkins-agent-cdk`
   - `oscar-build-metrics-agent-cdk`
   - `oscar-test-metrics-agent-cdk`
   - `oscar-release-metrics-agent-cdk`
   - `oscar-supervisor-agent-cdk`
   - `oscar-communication-handler-cdk`

3. **Knowledge Bases**: Create OpenSearch documentation knowledge base
   - Update `deployment-config.json` with correct knowledge base ID

### Collaborator Placeholder System
The system uses placeholder values for fresh deployments:
- `PLACEHOLDER_JENKINS_AGENT_ID`
- `PLACEHOLDER_BUILD_METRICS_AGENT_ID`
- `PLACEHOLDER_TEST_METRICS_AGENT_ID`
- `PLACEHOLDER_RELEASE_METRICS_AGENT_ID`

These are automatically replaced with actual agent IDs during deployment.

### Deployment Behavior
- **Fresh Account**: Creates new agents with placeholder replacement
- **Existing Account**: Updates existing agents and maintains relationships
- **Mixed State**: Handles partial deployments gracefully

## 🚨 Important Notes

### Security Features
- **Jenkins Agent**: Requires explicit user confirmation for all job executions
- **Communication**: Privileged agent requires confirmation for message sending
- **Limited Agent**: Explicitly blocks communication and Jenkins features

### Lambda Function Naming
All Lambda functions must follow the pattern: `*-cdk` suffix for proper identification and updates.

### Error Handling
- Scripts validate Lambda function existence before updates
- Dependency checks ensure proper deployment order
- Rollback capabilities through agent ID tracking

### Best Practices
1. Always run `deploy-all-agents.sh` for initial deployment
2. Use update scripts for incremental changes
3. Test agents after updates
4. Keep `deployed-agent-ids.json` backed up
5. Review configurations before deployment

## 📝 Troubleshooting

### Common Issues
1. **Lambda not found**: Ensure Lambda functions are deployed with correct names
2. **Permission errors**: Verify IAM roles have proper Bedrock permissions
3. **Dependency errors**: Check deployment order in `deployment-config.json`
4. **Knowledge base errors**: Verify knowledge base IDs are correct

### Recovery
If deployment fails:
1. Check `deployed-agent-ids.json` for partial deployments
2. Use update scripts to fix specific issues
3. Redeploy individual agents if needed
4. Clean up failed agents manually if necessary