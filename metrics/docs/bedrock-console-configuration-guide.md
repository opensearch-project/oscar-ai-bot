# Bedrock Console Configuration Guide for OSCAR Agent

## Overview

This guide provides step-by-step instructions for configuring the comprehensive OSCAR Agent in the Amazon Bedrock console. This agent combines both knowledge base operations and metrics analysis capabilities, serving as a unified AI assistant for OpenSearch project management and support.

## Architecture

```
User → OSCAR (Slack Bot) → Query Classification →
                        ├── OSCAR Agent (Bedrock Agent) [unified]
                        │   ├── Knowledge Base Action Group
                        │   └── Metrics Action Groups
                        └── Comprehensive Response
```

## Prerequisites

1. AWS account with Bedrock access enabled
2. Deployed Lambda function for metrics processing
3. Appropriate IAM permissions for Bedrock agent creation
4. OpenSearch cluster with metrics data (gradle-check-*, opensearch_release_metrics)

## Step 1: Create the OSCAR Agent

### Basic Agent Configuration
1. Navigate to Amazon Bedrock console
2. Go to "Agents" section
3. Click "Create Agent"
4. Configure basic settings:
   - **Agent Name**: `oscar-agent`
   - **Description**: `Comprehensive AI assistant for OpenSearch project management, combining knowledge base queries with real-time metrics analysis`
   - **Foundation Model**: `Claude 3.5 Sonnet` (anthropic.claude-3-5-sonnet-20241022-v1:0)
   - **Agent Instructions**: Use the instructions below

### Agent Instructions
```text
You are OSCAR, a comprehensive AI assistant for OpenSearch project management and support. You combine knowledge base queries with real-time metrics analysis to provide complete, actionable responses to users.

## Core Capabilities

### Knowledge Base Operations
- Answer questions about OpenSearch documentation, configuration, and best practices
- Provide guidance on installation, setup, and troubleshooting
- Explain features, APIs, and architectural concepts
- Offer recommendations based on official documentation

### Metrics Data Analysis
- Query test execution results and failure patterns from gradle-check indices
- Analyze build status and release information from opensearch_release_metrics
- Retrieve deployment status and environment health data
- Monitor system performance and operational metrics
- Provide cluster health and operational status

### Data Sources
- **Knowledge Base**: Official OpenSearch documentation, guides, and best practices
- **Test Data**: gradle-check-* indices (test failures, execution times, coverage)
- **Release Data**: opensearch_release_metrics index (versions, components, release status)
- **Performance Data**: Various performance and benchmark indices
- **Cluster Data**: OpenSearch cluster health and operational metrics

### Response Guidelines
- Always determine whether a query requires knowledge base information, metrics data, or both
- For metrics queries: Provide accurate, data-driven insights with specific numbers and trends
- For knowledge queries: Reference official documentation and provide step-by-step guidance
- For combined queries: Integrate both knowledge and metrics to provide comprehensive answers
- Include relevant time ranges and data sources when presenting metrics
- Highlight critical issues that need immediate attention
- Format responses with clear structure and actionable information
- When metrics data is unavailable, clearly state limitations and suggest alternatives

### Available Repositories
core, sql, dashboards, security, ml-commons, k-nn, anomaly-detection, alerting, index-management, job-scheduler, performance-analyzer

### Time Range Formats
Use relative formats: 7d, 30d, 1h, 24h, 1w, 1m

### Key Metrics Categories
- **Test Metrics**: Failures, success rates, execution times, coverage
- **Build Metrics**: Status, duration, artifacts, release readiness
- **Deployment Metrics**: Environment status, deployment success, rollbacks
- **Performance Metrics**: Latency, throughput, resource usage, benchmarks
- **Operational Metrics**: Cluster health, node status, index statistics

### Integration Approach
- Use knowledge base functions for documentation, configuration, and conceptual questions
- Use metrics functions for current status, performance data, and operational insights
- Combine both when users need context (e.g., "How do I configure X and what's its current performance?")
- Always provide complete, helpful responses that address the user's underlying needs

You are helpful, knowledgeable, and focused on providing actionable insights for OpenSearch project success.
```

## Step 2: Create Action Groups (11 Functions Total)

### Action Group 1: Knowledge Base Operations

#### Basic Configuration
1. Click "Add Action Group"
2. **Action Group Name**: `knowledge_base_operations`
3. **Description**: `Query OpenSearch documentation and knowledge base for guidance and information`
4. **Action Group Type**: Select **Return control to user**
5. **Action Group Schema**: Select **Define with function details**
6. Use **JSON Editor** and paste the function definition below

#### Function 1: query_knowledge_base

```json
{
  "name": "query_knowledge_base",
  "description": "Query the OpenSearch knowledge base for documentation, configuration guidance, best practices, and conceptual information",
  "parameters": {
    "query": {
      "description": "The user's question or search query for the knowledge base",
      "required": "True",
      "type": "String"
    },
    "context": {
      "description": "Additional context or previous conversation history to help with the query",
      "required": "False",
      "type": "String"
    }
  },
  "requireConfirmation": "DISABLED"
}
```

### Action Group 2: Test and Build Metrics

#### Basic Configuration
1. Click "Add Action Group"
2. **Action Group Name**: `test_build_metrics`
3. **Description**: `Test execution results, build status, and compilation analysis`
4. **Lambda Function**: Select your deployed metrics Lambda function
5. **Action Group Schema**: Select **Define with function details**
6. Use **JSON Editor** and paste the function definitions below

#### Function 2: get_test_metrics

```json
{
  "name": "get_test_metrics",
  "description": "Analyze test execution results, failures, coverage, and performance data",
  "parameters": {
    "repository": {
      "description": "Repository name (core, sql, dashboards, security, ml-commons, k-nn, anomaly-detection)",
      "required": "False",
      "type": "String"
    },
    "analysis_type": {
      "description": "Type of test analysis (results, coverage, performance, all)",
      "required": "False",
      "type": "String"
    },
    "time_range": {
      "description": "Time range for analysis (e.g., 7d, 30d, 1h)",
      "required": "False",
      "type": "String"
    },
    "build_id": {
      "description": "Specific build ID to analyze",
      "required": "False",
      "type": "String"
    },
    "status_filter": {
      "description": "Filter by test status (pass, fail, skip, error, all)",
      "required": "False",
      "type": "String"
    }
  },
  "requireConfirmation": "DISABLED"
}
```

#### Function 3: get_build_metrics

```json
{
  "name": "get_build_metrics",
  "description": "Retrieve build status, trends, artifacts, and compilation information",
  "parameters": {
    "repository": {
      "description": "Repository name (core, sql, dashboards, security, ml-commons, k-nn, anomaly-detection)",
      "required": "False",
      "type": "String"
    },
    "analysis_type": {
      "description": "Type of build analysis (status, trends, artifacts, all)",
      "required": "False",
      "type": "String"
    },
    "time_range": {
      "description": "Time range for analysis (e.g., 7d, 30d, 1h)",
      "required": "False",
      "type": "String"
    },
    "build_id": {
      "description": "Specific build ID or version number",
      "required": "False",
      "type": "String"
    },
    "status_filter": {
      "description": "Filter by build status (success, failed, in_progress, cancelled, all)",
      "required": "False",
      "type": "String"
    }
  },
  "requireConfirmation": "DISABLED"
}
```

### Action Group 3: Deployment and Performance Metrics

#### Basic Configuration
1. Click "Add Action Group"
2. **Action Group Name**: `deployment_performance_metrics`
3. **Description**: `Deployment status, environment health, and system performance analysis`
4. **Lambda Function**: Select your deployed metrics Lambda function
5. **Action Group Schema**: Select **Define with function details**

#### Function 4: get_deployment_metrics

```json
{
  "name": "get_deployment_metrics",
  "description": "Retrieve deployment status, history, environment health, and rollback information",
  "parameters": {
    "repository": {
      "description": "Repository name (core, sql, dashboards, security, ml-commons, k-nn, anomaly-detection)",
      "required": "False",
      "type": "String"
    },
    "environment": {
      "description": "Target environment (development, staging, production, all)",
      "required": "False",
      "type": "String"
    },
    "analysis_type": {
      "description": "Type of deployment analysis (status, history, health, all)",
      "required": "False",
      "type": "String"
    },
    "time_range": {
      "description": "Time range for deployment analysis (e.g., 7d, 30d, 1h)",
      "required": "False",
      "type": "String"
    },
    "version": {
      "description": "Specific version to check",
      "required": "False",
      "type": "String"
    }
  },
  "requireConfirmation": "DISABLED"
}
```

#### Function 5: get_performance_metrics

```json
{
  "name": "get_performance_metrics",
  "description": "Retrieve system performance data, trends, alerts, and resource usage metrics",
  "parameters": {
    "repository": {
      "description": "Repository name (core, sql, dashboards, security, ml-commons, k-nn, anomaly-detection)",
      "required": "False",
      "type": "String"
    },
    "environment": {
      "description": "Target environment (development, staging, production)",
      "required": "False",
      "type": "String"
    },
    "analysis_type": {
      "description": "Type of performance analysis (data, trends, alerts, all)",
      "required": "False",
      "type": "String"
    },
    "metric_category": {
      "description": "Category of performance metric (latency, throughput, memory, cpu, disk, all)",
      "required": "False",
      "type": "String"
    },
    "time_range": {
      "description": "Time range for metrics (e.g., 24h, 7d, 1h)",
      "required": "False",
      "type": "String"
    }
  },
  "requireConfirmation": "DISABLED"
}
```

### Action Group 4: General Search and Health

#### Basic Configuration
1. Click "Add Action Group"
2. **Action Group Name**: `general_search_health`
3. **Description**: `Cross-domain search, cluster health, and comprehensive metrics analysis`
4. **Lambda Function**: Select your deployed metrics Lambda function
5. **Action Group Schema**: Select **Define with function details**

#### Function 6: search_all_metrics

```json
{
  "name": "search_all_metrics",
  "description": "Perform unified search across all metrics types and data sources",
  "parameters": {
    "search_query": {
      "description": "Search query text for metrics data",
      "required": "True",
      "type": "String"
    },
    "metric_types": {
      "description": "Types of metrics to search (test, build, deployment, performance, all)",
      "required": "False",
      "type": "String"
    },
    "repository": {
      "description": "Repository name filter (core, sql, dashboards, security, ml-commons, k-nn, anomaly-detection)",
      "required": "False",
      "type": "String"
    },
    "time_range": {
      "description": "Time range for search (e.g., 7d, 30d, 1h)",
      "required": "False",
      "type": "String"
    }
  },
  "requireConfirmation": "DISABLED"
}
```

#### Function 7: get_cluster_health

```json
{
  "name": "get_cluster_health",
  "description": "Retrieve comprehensive OpenSearch cluster operational status and health metrics",
  "parameters": {
    "cluster_name": {
      "description": "Specific cluster to check",
      "required": "False",
      "type": "String"
    },
    "health_aspect": {
      "description": "Aspect of cluster health to check (overall, indices, nodes, shards, all)",
      "required": "False",
      "type": "String"
    },
    "include_details": {
      "description": "Include detailed health information and recommendations (true, false)",
      "required": "False",
      "type": "String"
    },
    "time_range": {
      "description": "Time range for health trend analysis (e.g., 24h, 7d, 1h)",
      "required": "False",
      "type": "String"
    }
  },
  "requireConfirmation": "DISABLED"
}
```

### Action Group 5: Comprehensive Analysis

#### Basic Configuration
1. Click "Add Action Group"
2. **Action Group Name**: `comprehensive_analysis`
3. **Description**: `Combined knowledge base and metrics analysis for comprehensive responses`
4. **Action Group Type**: Select **Return control to user**
5. **Action Group Schema**: Select **Define with function details**

#### Function 8: get_comprehensive_analysis

```json
{
  "name": "get_comprehensive_analysis",
  "description": "Provide comprehensive analysis combining knowledge base information with current metrics data and advanced aggregation capabilities",
  "parameters": {
    "topic": {
      "description": "The main topic, component, or complex analysis query to analyze (e.g., security, performance, specific feature)",
      "required": "True",
      "type": "String"
    },
    "analysis_type": {
      "description": "Type of comprehensive analysis (status, troubleshooting, optimization, overview, trends, comparisons, correlations)",
      "required": "False",
      "type": "String"
    },
    "time_range": {
      "description": "Time range for metrics analysis (e.g., 7d, 30d, 1h)",
      "required": "False",
      "type": "String"
    },
    "repository": {
      "description": "Specific repository to focus on if applicable",
      "required": "False",
      "type": "String"
    },
    "data_sources": {
      "description": "Data sources to include (auto, all, tests, builds, performance, releases)",
      "required": "False",
      "type": "String"
    },
    "aggregation_type": {
      "description": "Type of aggregation (summary, trends, comparisons, correlations)",
      "required": "False",
      "type": "String"
    }
  },
  "requireConfirmation": "DISABLED"
}
```

#### Function 9: get_dashboard_summary

```json
{
  "name": "get_dashboard_summary",
  "description": "Generate a comprehensive dashboard summary combining project status, metrics, and recommendations with enhanced aggregation",
  "parameters": {
    "time_range": {
      "description": "Time range for dashboard data (e.g., 24h, 7d, 30d)",
      "required": "False",
      "type": "String"
    },
    "focus_areas": {
      "description": "Specific areas to focus on (tests, builds, performance, security, all)",
      "required": "False",
      "type": "String"
    },
    "repository_filter": {
      "description": "Filter dashboard to specific repositories",
      "required": "False",
      "type": "String"
    },
    "aggregation_type": {
      "description": "Type of aggregation for dashboard insights (summary, trends, comparisons)",
      "required": "False",
      "type": "String"
    }
  },
  "requireConfirmation": "DISABLED"
}
```

#### Function 10: get_troubleshooting_guide

```json
{
  "name": "get_troubleshooting_guide",
  "description": "Provide troubleshooting guidance combining documentation with current system status",
  "parameters": {
    "issue_description": {
      "description": "Description of the issue or problem to troubleshoot",
      "required": "True",
      "type": "String"
    },
    "component": {
      "description": "Specific OpenSearch component or feature related to the issue",
      "required": "False",
      "type": "String"
    },
    "error_message": {
      "description": "Specific error message if available",
      "required": "False",
      "type": "String"
    },
    "environment": {
      "description": "Environment where the issue occurs (development, staging, production)",
      "required": "False",
      "type": "String"
    }
  },
  "requireConfirmation": "DISABLED"
}
```

## Step 3: Testing and Validation

### Test Queries

#### Knowledge Base Function Testing
1. **query_knowledge_base**: "How do I configure OpenSearch security?"
2. **query_knowledge_base**: "What are the best practices for indexing?"
3. **query_knowledge_base**: "Explain OpenSearch cluster architecture"

#### Metrics Function Testing
4. **get_test_metrics**: "Show me test failures from the last week"
5. **get_build_metrics**: "What's the build status for the SQL repository?"
6. **get_deployment_metrics**: "How are deployments performing in production?"
7. **get_performance_metrics**: "What's the search latency trend this week?"
8. **search_all_metrics**: "Find any issues with the core repository"
9. **get_cluster_health**: "What's the current cluster health status?"

#### Comprehensive Analysis Function Testing
10. **get_comprehensive_analysis**: "Analyze the security plugin's current status and configuration"
11. **get_comprehensive_analysis** (with aggregation): "Compare test performance across all repositories this month with trend analysis"
12. **get_dashboard_summary**: "Give me a complete project overview for the last 7 days"
13. **get_troubleshooting_guide**: "Help me troubleshoot slow search performance"

#### Natural Language Testing (Mixed Queries)
1. "How do I configure security and what's its current test status?"
2. "Show me build artifacts for version 2.11.0 and explain the release process"
3. "Check deployment history and provide deployment best practices"
4. "Get performance alerts and explain how to optimize search performance"
5. "Search for memory-related issues and provide memory tuning guidance"
6. "How healthy is our cluster and what are the monitoring best practices?"

### Validation Checklist
- [ ] Agent is created with correct name and model
- [ ] All 5 action groups are created and enabled
- [ ] Knowledge base action group is configured as "Return control to user"
- [ ] Metrics action groups are connected to Lambda function
- [ ] Function schemas are correctly defined with proper parameters
- [ ] Agent instructions cover both knowledge base and metrics capabilities
- [ ] IAM permissions allow Lambda to access OpenSearch
- [ ] Knowledge base integration is properly configured
- [ ] Test queries return expected results from both knowledge base and metrics
- [ ] Comprehensive analysis functions work correctly

## Next Steps

After completing the Bedrock console configuration:

1. **Deploy Metrics Lambda Function**: Use the provided CDK stack
2. **Configure Knowledge Base Integration**: Ensure the knowledge base is properly linked
3. **Test Agent Functions**: Validate that each action group works correctly
4. **Update OSCAR Slack Bot**: Configure the bot to use the new unified agent
5. **Monitor Performance**: Set up logging and monitoring for agent interactions

This configuration provides a comprehensive OSCAR agent that combines knowledge base queries with real-time metrics analysis, offering users complete OpenSearch project support in a single interface.