# OSCAR Enhanced Metrics Agents Deployment Guide

## Overview

This guide covers the deployment of enhanced metrics agents with improved query capabilities, natural language processing, and multi-strategy analysis for OpenSearch ecosystem components.

## Agent Configuration Updates

### 1. Integration Test Agent Configuration

```json
{
  "agentName": "oscar-integration-test-agent",
  "description": "Enhanced integration test analysis agent that provides comprehensive failure analysis, RC-based queries, and cross-component testing insights for OpenSearch ecosystem components.",
  "instruction": "You are OSCAR's Integration Test Agent. You analyze integration test results, failures, and success patterns across OpenSearch and OpenSearch-Dashboards components. You can query by RC numbers, build numbers, specific components, platforms, and architectures. You provide detailed failure analysis with test reports, build URLs, and actionable insights for debugging test issues.",
  "actionGroups": [
    {
      "actionGroupName": "IntegrationTestActionGroup",
      "description": "Enhanced integration test failure analysis and component testing insights",
      "actionGroupExecutor": {
        "lambda": "arn:aws:lambda:us-east-1:ACCOUNT:function:oscar-test-metrics-agent-new"
      },
      "functionSchema": {
        "functions": [
          {
            "name": "get_integration_test_metrics",
            "description": "Get comprehensive integration test results with multi-strategy analysis",
            "parameters": {
              "query": {
                "type": "string",
                "description": "Natural language query about integration test failures or status",
                "required": false
              },
              "version": {
                "type": "string",
                "description": "Version number (e.g., 3.2.0)",
                "required": false
              },
              "rc_numbers": {
                "type": "array",
                "description": "List of RC numbers to analyze",
                "required": false
              },
              "build_numbers": {
                "type": "array", 
                "description": "List of build numbers to analyze",
                "required": false
              },
              "components": {
                "type": "array",
                "description": "List of component names (OpenSearch, OpenSearch-Dashboards)",
                "required": false
              },
              "status_filter": {
                "type": "string",
                "description": "Filter by test status (failed, passed)",
                "required": false
              },
              "distribution": {
                "type": "string",
                "description": "Distribution type (tar, rpm, deb, zip)",
                "required": false
              },
              "architecture": {
                "type": "string", 
                "description": "Architecture (x64, arm64)",
                "required": false
              }
            },
            "requireConfirmation": "DISABLED"
          },
          {
            "name": "resolve_components_from_builds",
            "description": "Resolve which components are associated with specific build numbers",
            "parameters": {
              "version": {
                "type": "string",
                "description": "Version number",
                "required": true
              },
              "build_numbers": {
                "type": "array",
                "description": "List of build numbers to resolve",
                "required": true
              }
            },
            "requireConfirmation": "DISABLED"
          },
          {
            "name": "get_rc_build_mapping",
            "description": "Get build numbers for specific RC numbers",
            "parameters": {
              "version": {
                "type": "string",
                "description": "Version number",
                "required": true
              },
              "rc_numbers": {
                "type": "array",
                "description": "List of RC numbers",
                "required": true
              },
              "component": {
                "type": "string",
                "description": "Component name for RC resolution",
                "required": false
              }
            },
            "requireConfirmation": "DISABLED"
          }
        ]
      }
    }
  ]
}
```

### 2. Build Metrics Agent Configuration

```json
{
  "agentName": "oscar-build-metrics-agent", 
  "description": "Enhanced build metrics agent that analyzes distribution build results, component build status, and build pipeline performance across OpenSearch ecosystem.",
  "instruction": "You are OSCAR's Build Metrics Agent. You analyze distribution build results, component build failures, and build pipeline performance. You can query build status by version, build numbers, components, and time ranges. You provide build success rates, failure analysis, and component-specific build insights.",
  "actionGroups": [
    {
      "actionGroupName": "BuildMetricsActionGroup",
      "description": "Enhanced build metrics analysis and distribution build insights",
      "actionGroupExecutor": {
        "lambda": "arn:aws:lambda:us-east-1:ACCOUNT:function:oscar-build-metrics-agent-new"
      },
      "functionSchema": {
        "functions": [
          {
            "name": "get_build_metrics",
            "description": "Get comprehensive build metrics and distribution build analysis",
            "parameters": {
              "query": {
                "type": "string",
                "description": "Natural language query about build status or failures",
                "required": false
              },
              "version": {
                "type": "string",
                "description": "Version number (e.g., 3.2.0)",
                "required": false
              },
              "build_numbers": {
                "type": "array",
                "description": "List of build numbers to analyze",
                "required": false
              },
              "components": {
                "type": "array",
                "description": "List of component names",
                "required": false
              },
              "status_filter": {
                "type": "string",
                "description": "Filter by build status (failed, success)",
                "required": false
              },
              "time_range": {
                "type": "string",
                "description": "Time range for analysis (7d, 30d)",
                "required": false
              }
            },
            "requireConfirmation": "DISABLED"
          }
        ]
      }
    }
  ]
}
```

### 3. Release Metrics Agent Configuration

```json
{
  "agentName": "oscar-release-metrics-agent",
  "description": "Enhanced release readiness agent that analyzes release metrics, component readiness, and release pipeline status for OpenSearch ecosystem releases.",
  "instruction": "You are OSCAR's Release Metrics Agent. You analyze release readiness, component release status, and release pipeline health. You can assess release readiness scores, identify blocking components, and provide release owner information. You help determine if components are ready for release based on release issues, notes, version increments, and branch status.",
  "actionGroups": [
    {
      "actionGroupName": "ReleaseMetricsActionGroup", 
      "description": "Enhanced release readiness analysis and component release insights",
      "actionGroupExecutor": {
        "lambda": "arn:aws:lambda:us-east-1:ACCOUNT:function:oscar-release-metrics-agent-new"
      },
      "functionSchema": {
        "functions": [
          {
            "name": "get_release_metrics",
            "description": "Get comprehensive release readiness metrics and component analysis",
            "parameters": {
              "query": {
                "type": "string",
                "description": "Natural language query about release readiness or status",
                "required": false
              },
              "version": {
                "type": "string", 
                "description": "Version number (e.g., 3.2.0)",
                "required": false
              },
              "components": {
                "type": "array",
                "description": "List of component names",
                "required": false
              },
              "time_range": {
                "type": "string",
                "description": "Time range for analysis (7d, 30d)",
                "required": false
              }
            },
            "requireConfirmation": "DISABLED"
          }
        ]
      }
    }
  ]
}
```

## Supervisor Agent Collaborator Updates

### Integration Test Specialist
```json
{
  "collaboratorName": "IntegrationTestSpecialist",
  "description": "Expert in integration test analysis, failure debugging, and cross-component testing insights",
  "instruction": "You specialize in integration test failures, RC-based analysis, and component testing patterns. You can analyze test failures across different platforms, architectures, and distributions. You provide detailed failure analysis with test reports and build URLs for debugging."
}
```

### Build Metrics Specialist
```json
{
  "collaboratorName": "BuildMetricsSpecialist", 
  "description": "Expert in build pipeline analysis, distribution builds, and component build status",
  "instruction": "You specialize in build metrics, distribution build analysis, and build pipeline performance. You can analyze build failures, success rates, and component-specific build issues across different versions and time ranges."
}
```

### Release Readiness Specialist
```json
{
  "collaboratorName": "ReleaseReadinessSpecialist",
  "description": "Expert in release readiness assessment, component release status, and release pipeline health",
  "instruction": "You specialize in release readiness analysis, component release status, and release blocking issues. You can assess release readiness scores, identify components that need attention, and provide release owner information for coordination."
}
```

---

## Enhanced Configuration Best Practices

### Function Schema Requirements
- **Required Fields**: All parameters must include `"required": true/false`
- **Confirmation**: All functions must include `"requireConfirmation": "DISABLED"`
- **Parameter Types**: Use proper JSON schema types (string, array, object)
- **Descriptions**: Provide clear, actionable parameter descriptions

### Agent Instructions Format
- **Role Definition**: Start with clear agent identity
- **Capabilities**: List specific analysis capabilities
- **Query Handling**: Explain how different query types are processed
- **Response Guidelines**: Define output format and quality standards

### Collaborator Configuration
- **Naming Convention**: Use descriptive, role-based names
- **Instruction Clarity**: Provide specific collaboration scenarios
- **Capability Mapping**: Clearly define when to use each collaborator pipeline health",
  "instruction": "You specialize in release readiness analysis, component release status, and release blocking issues. You can assess release readiness scores, identify components that need attention, and provide release owner information for coordination."
}
```

## Deployment Instructions

### 1. Environment Variables Update

Set the appropriate agent type for each Lambda function:

```bash
# Integration Test Agent
AGENT_TYPE=integration-test

# Build Metrics Agent  
AGENT_TYPE=build-metrics

# Release Metrics Agent
AGENT_TYPE=release-metrics
```

### 2. Lambda Function Deployment

Deploy the updated lambda function to all three agents:

```bash
# Package the lambda function
zip -r lambda_function.zip lambda_function.py

# Deploy to Integration Test Agent
aws lambda update-function-code \
  --function-name oscar-test-metrics-agent-new \
  --zip-file fileb://lambda_function.zip

# Deploy to Build Metrics Agent
aws lambda update-function-code \
  --function-name oscar-build-metrics-agent-new \
  --zip-file fileb://lambda_function.zip

# Deploy to Release Metrics Agent
aws lambda update-function-code \
  --function-name oscar-release-metrics-agent-new \
  --zip-file fileb://lambda_function.zip
```

### 3. Bedrock Agent Configuration

#### Step-by-Step Agent Setup

**For each agent (Integration Test, Build, Release):**

1. **Navigate to AWS Bedrock Console**
   - Go to Amazon Bedrock → Agents → Create Agent

2. **Basic Information**
   - Use agent names and descriptions from configurations above
   - Select Foundation Model: `Claude 3.5 Sonnet v2`

3. **Agent Instructions**
   - Copy the complete instruction text from each agent configuration
   - Ensure instructions match the agent's specialized focus

4. **Action Groups Configuration**
   - Create new action group with name from configuration
   - Select "Define with function details"
   - Enter Lambda function ARN for the specific agent
   - Copy the complete JSON function schema from configurations above
   - **Critical**: Ensure all parameters include `"required": true/false`
   - **Critical**: Ensure function includes `"requireConfirmation": "DISABLED"`

5. **Save and Prepare Agent**
   - Save the agent configuration
   - Click "Prepare" to deploy the agent
   - Wait for preparation to complete

### 4. Supervisor Agent Collaborator Updates

**In the OSCAR Supervisor Agent:**

1. **Navigate to Collaborators Section**
   - Go to existing OSCAR supervisor agent
   - Select "Collaborators" tab

2. **Add/Update Collaborators**
   - Add each specialized agent as a collaborator
   - Use collaborator names and instructions from configurations above
   - Enable conversation history sharing for all collaborators

3. **Prepare Updated Supervisor**
   - Save collaborator configurations
   - Click "Prepare" to update the supervisor agent

### 5. Verification and Testing

#### Individual Agent Testing

**Integration Test Agent:**
```
Which components failed RC 1 for version 3.2.0?
Show me integration test failures for build numbers 11323 and 8585
What OpenSearch-Dashboards tests failed on ARM64?
```

**Build Metrics Agent:**
```
Show me build status for version 3.2.0
Which components had build failures in the last 7 days?
What's the build success rate for OpenSearch components?
```

**Release Metrics Agent:**
```
What's the release readiness for version 3.2.0?
Which components are blocking the release?
Show me release owners for OpenSearch components
```

#### Multi-Agent Collaboration Testing

**Through OSCAR Supervisor:**
```
@OSCAR Provide a comprehensive analysis of integration test failures and their impact on release readiness for version 3.2.0
@OSCAR Which components have both build failures and integration test issues?
@OSCAR Generate an executive summary of our development pipeline health
```

### 6. Validation Checklist

**Lambda Functions:**
- [ ] All three Lambda functions deployed successfully
- [ ] Environment variables set correctly for each agent
- [ ] Functions can connect to OpenSearch indices
- [ ] Basic connectivity tests pass

**Bedrock Agents:**
- [ ] All three specialized agents created and prepared
- [ ] Action groups configured with correct Lambda ARNs
- [ ] Function schemas include required fields and requireConfirmation
- [ ] Agent instructions match specialized capabilities

**Supervisor Agent:**
- [ ] Collaborators added for all three specialized agents
- [ ] Collaborator instructions define clear usage scenarios
- [ ] Conversation history sharing enabled
- [ ] Supervisor agent prepared with updated configuration

**End-to-End Testing:**
- [ ] Individual agents respond to direct queries
- [ ] Supervisor agent can coordinate with collaborators
- [ ] Natural language parsing works correctly
- [ ] Cross-agent functionality works (RC resolution, component mapping)
- [ ] Complex multi-parameter queries return expected results

**Performance Validation:**
- [ ] Query response times are acceptable (< 30 seconds)
- [ ] OpenSearch queries return proper data structure
- [ ] Error handling works for invalid parameters
- [ ] Agent collaboration doesn't cause timeouts

## Enhanced Capabilities

The updated system provides:

### **Query Intelligence**
- **10x Query Flexibility**: From basic status to complex multi-parameter queries
- **Natural Language Processing**: Handles both vague ("What's broken?") and specific queries
- **Multi-Strategy Analysis**: RC-based, build-based, component-based approaches
- **Cross-Repository Intelligence**: Automatic component resolution from build numbers

### **Advanced Analysis**
- **RC-to-Build Mapping**: Automatic resolution of RC numbers to build numbers
- **Component Cross-Reference**: Resolve components from build numbers across indices
- **OpenSearch-Dashboards Handling**: Special regex patterns for dashboard components
- **Platform/Architecture Filtering**: Support for ARM64, Windows, different distributions

### **Performance Optimization**
- **Query Deduplication**: Collapse queries to avoid duplicate components
- **Proper Field Selection**: Optimized `_source` filtering for faster responses
- **Smart Sorting**: Chronological ordering with `build_start_time` descending
- **Result Pagination**: Configurable result limits (default 100)

### **Integration Features**
- **Detailed Failure Context**: Test reports, build URLs, debugging links
- **Success Rate Calculations**: Automatic computation of pass/fail ratios
- **Release Readiness Scoring**: Multi-criteria assessment for release preparation
- **Cross-Agent Coordination**: Seamless collaboration between specialized agents

---

## Troubleshooting Guide

### **Lambda Function Issues**

**Symptoms**: Function timeouts, connection errors, permission denied

**Solutions**:
```bash
# Check CloudWatch logs
aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/oscar"

# Test basic connectivity
aws lambda invoke --function-name oscar-test-metrics-agent-new \
  --payload '{"function":"test_basic"}' response.json

# Verify environment variables
aws lambda get-function-configuration --function-name oscar-test-metrics-agent-new
```

### **OpenSearch Query Issues**

**Symptoms**: Empty results, field not found errors, index not found

**Solutions**:
- **Verify Index Names**: Ensure `opensearch-integration-test-results`, `opensearch-distribution-build-results`, `opensearch_release_metrics` exist
- **Check Field Names**: Validate `component_build_result`, `distribution_build_number`, `rc_number` fields
- **Version Format**: Use exact format like "3.2.0" (not "v3.2.0" or "3.2")
- **Component Names**: Use exact case: "OpenSearch", "OpenSearch-Dashboards"

### **Bedrock Agent Configuration Issues**

**Symptoms**: Function not found, parameter validation errors, agent preparation failures

**Solutions**:
- **Action Group Configuration**: Ensure Lambda ARN is correct and accessible
- **Function Schema**: Verify all parameters include `"required": true/false`
- **Confirmation Setting**: Ensure `"requireConfirmation": "DISABLED"` is present
- **Permissions**: Check Lambda resource policy allows Bedrock invocation

### **Agent Collaboration Issues**

**Symptoms**: Supervisor can't reach collaborators, timeout errors, incomplete responses

**Solutions**:
- **Collaborator Names**: Ensure names match exactly between supervisor and agent configurations
- **Agent Aliases**: Use correct alias (typically "TSTALIASID" for test)
- **Conversation History**: Enable sharing for all collaborators
- **Preparation Status**: Ensure all agents are in "Prepared" state

### **Query Performance Issues**

**Symptoms**: Slow responses, timeouts, incomplete results

**Solutions**:
- **Query Optimization**: Use specific version and component filters
- **Result Limiting**: Reduce query size for initial testing
- **Index Health**: Check OpenSearch cluster status
- **Network Connectivity**: Verify VPC endpoint configuration

---

## Support Resources

### **Debugging Tools**
- **CloudWatch Logs**: `/aws/lambda/oscar-*-agent-new` log groups
- **Bedrock Test Console**: Test individual agents and functions
- **OpenSearch Dashboards**: Query validation and index exploration
- **AWS X-Ray**: Distributed tracing for complex queries

### **Monitoring Dashboards**
- **Lambda Metrics**: Duration, errors, throttles
- **Bedrock Agent Metrics**: Invocations, success rates
- **OpenSearch Metrics**: Query performance, index health

### **Configuration Validation**
```bash
# Validate Lambda deployment
./validate_lambda_deployment.sh

# Test OpenSearch connectivity
./test_opensearch_connectivity.sh

# Verify Bedrock agent configuration
./validate_bedrock_agents.sh
```

**Estimated Total Deployment Time**: ~90 minutes
- Lambda deployment: 15 minutes
- Agent configuration: 60 minutes (20 minutes per agent)
- Testing and validation: 15 minutes