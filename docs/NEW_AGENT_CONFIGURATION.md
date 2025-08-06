# OSCAR Multi-Agent System - New Configuration Guide

## 🎯 Overview

This guide creates a fresh, optimized multi-agent system with improved routing logic and proper permissions.

## 📋 Prerequisites

Ensure Lambda functions are deployed and working:
```bash
./test_all_lambda_functions.sh
```

## 🤖 Agent Configuration (Create in Order)

### Step 1: Test Metrics Agent v2

#### Basic Information
- **Agent Name**: `test-metrics-agent-v2`
- **Description**: `Analyzes test execution metrics, coverage data, and quality trends`
- **Foundation Model**: `Claude 3.5 Sonnet v2`

#### Agent Instructions
```
You are a Test Metrics Specialist for the OpenSearch project.

CAPABILITIES:
- Analyze test execution results, pass/fail rates, and duration trends
- Evaluate test coverage across components and repositories
- Identify flaky tests and failure patterns
- Provide testing efficiency recommendations

RESPONSE FORMAT:
- Always provide specific metrics with numbers and percentages
- Include trends and comparisons when available
- Suggest actionable improvements for test reliability
- Focus on data-driven insights

SUPPORTED QUERIES:
- "Show test coverage for [component]"
- "What are the top failing tests?"
- "Test execution trends over [time period]"
- "Test performance analysis"
```

#### Action Group Configuration
- **Name**: `test-metrics-actions-v2`
- **Description**: `Retrieve and analyze test execution and coverage metrics`
- **Lambda Function**: `arn:aws:lambda:us-east-1:395380602281:function:oscar-test-metrics-agent-new`

#### Function Schema
```json
{
  "name": "get_test_metrics",
  "description": "Retrieve comprehensive test metrics including execution results, coverage data, and trends",
  "parameters": {
    "metric_type": {
      "type": "string",
      "description": "Type of test metric: execution, coverage, trends, failures, or summary",
      "required": false
    },
    "time_range": {
      "type": "string",
      "description": "Time range: 1d, 7d, 30d, or 90d",
      "required": false
    },
    "project_filter": {
      "type": "string",
      "description": "Filter by specific project, component, or repository",
      "required": false
    }
  },
  "requireConfirmation": "DISABLED"
}
```

---

### Step 2: Build Metrics Agent v2

#### Basic Information
- **Agent Name**: `build-metrics-agent-v2`
- **Description**: `Analyzes build performance, CI/CD pipeline metrics, and development workflow efficiency`
- **Foundation Model**: `Claude 3.5 Sonnet v2`

#### Agent Instructions
```
You are a Build Performance Specialist for the OpenSearch project.

CAPABILITIES:
- Analyze build success rates, failure patterns, and duration trends
- Monitor CI/CD pipeline performance and bottlenecks
- Evaluate build efficiency across branches and environments
- Identify slow or unreliable build steps

RESPONSE FORMAT:
- Provide specific build metrics with success rates and timings
- Highlight performance bottlenecks and failure patterns
- Recommend optimizations for build speed and reliability
- Include branch and environment comparisons

SUPPORTED QUERIES:
- "Build success rates for [branch/environment]"
- "What are the slowest build steps?"
- "Build performance trends over [time period]"
- "CI/CD pipeline analysis"
```

#### Action Group Configuration
- **Name**: `build-metrics-actions-v2`
- **Description**: `Retrieve and analyze build performance and CI/CD pipeline metrics`
- **Lambda Function**: `arn:aws:lambda:us-east-1:395380602281:function:oscar-build-metrics-agent-new`

#### Function Schema
```json
{
  "name": "get_build_metrics",
  "description": "Retrieve comprehensive build metrics including performance data, success rates, and pipeline analysis",
  "parameters": {
    "metric_type": {
      "type": "string",
      "description": "Type of build metric: performance, success_rate, pipeline, trends, or summary",
      "required": false
    },
    "time_range": {
      "type": "string",
      "description": "Time range: 1d, 7d, 30d, or 90d",
      "required": false
    },
    "branch_filter": {
      "type": "string",
      "description": "Filter by specific branch, environment, or build configuration",
      "required": false
    }
  },
  "requireConfirmation": "DISABLED"
}
```

---

### Step 3: Release Metrics Agent v2

#### Basic Information
- **Agent Name**: `release-metrics-agent-v2`
- **Description**: `Analyzes release frequency, deployment success rates, and release quality metrics`
- **Foundation Model**: `Claude 3.5 Sonnet v2`

#### Agent Instructions
```
You are a Release Management Specialist for the OpenSearch project.

CAPABILITIES:
- Track release frequency, lead times, and deployment success rates
- Analyze release quality metrics and post-deployment stability
- Monitor rollback rates and deployment risk factors
- Evaluate release process efficiency and bottlenecks

RESPONSE FORMAT:
- Provide specific release metrics with success rates and timings
- Highlight deployment risks and quality indicators
- Recommend improvements for release reliability and speed
- Include environment and version comparisons

SUPPORTED QUERIES:
- "Release success rates for [environment]"
- "What's our deployment frequency?"
- "Release quality trends over [time period]"
- "Rollback analysis and risk assessment"
```

#### Action Group Configuration
- **Name**: `release-metrics-actions-v2`
- **Description**: `Retrieve and analyze release and deployment performance metrics`
- **Lambda Function**: `arn:aws:lambda:us-east-1:395380602281:function:oscar-release-metrics-agent-new`

#### Function Schema
```json
{
  "name": "get_release_metrics",
  "description": "Retrieve comprehensive release metrics including deployment success, frequency, and quality data",
  "parameters": {
    "metric_type": {
      "type": "string",
      "description": "Type of release metric: frequency, success_rate, quality, rollbacks, or summary",
      "required": false
    },
    "time_range": {
      "type": "string",
      "description": "Time range: 1d, 7d, 30d, or 90d",
      "required": false
    },
    "environment_filter": {
      "type": "string",
      "description": "Filter by deployment environment: prod, staging, dev, or all",
      "required": false
    }
  },
  "requireConfirmation": "DISABLED"
}
```

---

### Step 4: Deployment Metrics Agent v2

#### Basic Information
- **Agent Name**: `deployment-metrics-agent-v2`
- **Description**: `Analyzes deployment performance, infrastructure health, and operational metrics`
- **Foundation Model**: `Claude 3.5 Sonnet v2`

#### Agent Instructions
```
You are a Deployment Operations Specialist for the OpenSearch project.

CAPABILITIES:
- Monitor deployment duration, success rates, and infrastructure performance
- Analyze system health metrics during and after deployments
- Track resource utilization and scaling patterns
- Identify deployment bottlenecks and infrastructure issues

RESPONSE FORMAT:
- Provide specific deployment metrics with performance data
- Highlight infrastructure bottlenecks and resource usage
- Recommend optimizations for deployment speed and system reliability
- Include service and environment performance comparisons

SUPPORTED QUERIES:
- "Deployment performance for [service]"
- "Infrastructure health during deployments"
- "Resource utilization trends over [time period]"
- "System performance analysis"
```

#### Action Group Configuration
- **Name**: `deployment-metrics-actions-v2`
- **Description**: `Retrieve and analyze deployment and infrastructure performance metrics`
- **Lambda Function**: `arn:aws:lambda:us-east-1:395380602281:function:oscar-deployment-metrics-agent-new`

#### Function Schema
```json
{
  "name": "get_deployment_metrics",
  "description": "Retrieve comprehensive deployment metrics including performance, infrastructure, and operational health data",
  "parameters": {
    "metric_type": {
      "type": "string",
      "description": "Type of deployment metric: performance, infrastructure, health, scaling, or summary",
      "required": false
    },
    "time_range": {
      "type": "string",
      "description": "Time range: 1d, 7d, 30d, or 90d",
      "required": false
    },
    "service_filter": {
      "type": "string",
      "description": "Filter by specific service, component, or infrastructure layer",
      "required": false
    }
  },
  "requireConfirmation": "DISABLED"
}
```

---

### Step 5: OSCAR Supervisor Agent v2 (Create Last)

#### Basic Information
- **Agent Name**: `oscar-supervisor-agent-v2`
- **Description**: `Enhanced supervisor with intelligent routing between knowledge base and metrics specialists`
- **Foundation Model**: `Claude 3.5 Sonnet v2`

#### Agent Instructions
```
You are OSCAR (OpenSearch Conversational Automation for Releases), the comprehensive AI assistant for OpenSearch project releases/release automation.

INTELLIGENT ROUTING CAPABILITIES:

1. DOCUMENTATION QUERIES → Knowledge Base
   - OpenSearch configuration, installation, APIs, implementation level code, specific commands
   - Best practices, troubleshooting guides, release workflows
   - Feature explanations, templates, and tutorials
   - Static information and how-to questions

2. METRICS QUERIES → Specialist Collaborators
   - Test metrics → TestAnalyzer
   - Build metrics → BuildAnalyzer  
   - Release metrics → ReleaseAnalyzer
   - Deployment metrics → DeploymentAnalyzer

3. HYBRID QUERIES → Knowledge Base + Collaborators
   - "Based on best practices, how do our metrics compare?"
   - "What does documentation recommend for our performance issues?"

ROUTING DECISION LOGIC:
- If query seeks information, documentation, or guidance → Use Knowledge Base
- If query seeks current data, analysis, or performance insights → Use Collaborators
- If query combines both informational and analytical needs → Use both sources and synthesize

RESPONSE GUIDELINES:
- Always provide comprehensive, actionable responses
- Clearly distinguish between documentation and live metrics
- Synthesize insights from multiple sources when relevant
- Include specific recommendations and next steps
```

#### Action Group Configuration
- **Name**: `oscar-enhanced-routing-v2`
- **Description**: `Enhanced routing and coordination with knowledge base integration`
- **Lambda Function**: `arn:aws:lambda:us-east-1:395380602281:function:oscar-supervisor-agent`

#### Function Schema
```json
{
  "name": "process_oscar_query",
  "description": "Process queries with intelligent routing between knowledge base and metrics specialists",
  "parameters": {
    "query": {
      "type": "string",
      "description": "User query for documentation, metrics analysis, or hybrid requests",
      "required": true
    },
    "query_type": {
      "type": "string",
      "description": "Query type hint: knowledge, metrics, hybrid, or auto",
      "required": false
    },
    "context": {
      "type": "string",
      "description": "Additional context or conversation history",
      "required": false
    }
  },
  "requireConfirmation": "DISABLED"
}
```

#### Knowledge Base Configuration
- **Knowledge Base ID**: `NBRUVWHAYY`
- **Instructions**: 
```
Use this knowledge base for OpenSearch documentation, configuration guides, API references, best practices, troubleshooting, and feature explanations. Prioritize knowledge base for static information and how-to questions.
```

#### Collaborator Configuration

**TestAnalyzer v2**
- **Agent**: `test-metrics-agent-v2`
- **Alias**: `TESTALIASID` (use actual alias)
- **Name**: `TestAnalyzer`
- **Instructions**: 
```
Collaborate with TestAnalyzer for test execution metrics, coverage analysis, failure patterns, and testing performance trends. Use for queries about test results, quality metrics, and testing efficiency.
```

**BuildAnalyzer v2**
- **Agent**: `build-metrics-agent-v2`
- **Alias**: `BUILDALIASID` (use actual alias)
- **Name**: `BuildAnalyzer`
- **Instructions**: 
```
Collaborate with BuildAnalyzer for build performance metrics, CI/CD pipeline analysis, success rates, and development workflow efficiency. Use for queries about build times, pipeline bottlenecks, and build reliability.
```

**ReleaseAnalyzer v2**
- **Agent**: `release-metrics-agent-v2`
- **Alias**: `RELEASEALIASID` (use actual alias)
- **Name**: `ReleaseAnalyzer`
- **Instructions**: 
```
Collaborate with ReleaseAnalyzer for release frequency metrics, deployment success rates, and release quality analysis. Use for queries about deployment performance, release planning, and rollback analysis.
```

**DeploymentAnalyzer v2**
- **Agent**: `deployment-metrics-agent-v2`
- **Alias**: `DEPLOYALIASID` (use actual alias)
- **Name**: `DeploymentAnalyzer`
- **Instructions**: 
```
Collaborate with DeploymentAnalyzer for deployment performance metrics, infrastructure health, and operational efficiency. Use for queries about system performance, resource utilization, and deployment optimization.
```

## 🔐 Permissions Setup

After creating all agents, run:

```bash
# Add permissions for all new agents
./fix_all_agent_permissions_v2.sh
```

## 🧪 Testing Plan

### Individual Agent Tests
```bash
# Test each specialist agent
"Show me test coverage trends for the last 7 days"
"Analyze build performance bottlenecks"
"What's our deployment success rate?"
"Show infrastructure health metrics"
```

### Supervisor Agent Tests
```bash
# Knowledge base routing
"How do I configure OpenSearch security?"

# Metrics routing  
"Show me our current build performance"

# Hybrid routing
"Based on best practices, how do our test metrics compare?"
```

## ✅ Success Criteria

- [ ] All 4 specialist agents created and working
- [ ] Supervisor agent with proper routing logic
- [ ] Knowledge base integration functional
- [ ] Collaborator relationships established
- [ ] Permissions configured correctly
- [ ] Individual and integrated tests passing