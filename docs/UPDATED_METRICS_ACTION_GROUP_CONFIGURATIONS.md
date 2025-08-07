# Updated Metrics Agent Action Group Configurations

## 🔍 Discovery Summary

Based on analysis of the OpenSearch cluster, we found:
- **Single Index**: `opensearch_release_metrics` (117,848 documents)
- **Rich Data Structure**: Contains comprehensive release tracking data with fields for issues, PRs, release states, versions, components, and repositories
- **Data Categories**: Build-related (2,946 docs), Test-related (2,967 docs), Release data (all docs), No deployment-specific data

## 📋 Updated Action Group Function Schemas

### 1. Test Metrics Agent Action Group

**Action Group Name**: `test-metrics-actions-v2`
**Lambda Function**: `oscar-test-metrics-agent-new`

```json
{
    "functions": [
        {
            "name": "get_test_metrics",
            "description": "Retrieve test execution metrics from functional test repositories and test-related components",
            "parameters": {
                "metric_type": {
                    "type": "string",
                    "description": "Type of test metric: execution, coverage, quality, trends, or summary",
                    "required": false
                },
                "time_range": {
                    "type": "string",
                    "description": "Time range: 1d, 7d, 30d, or 90d",
                    "required": false
                },
                "project_filter": {
                    "type": "string", 
                    "description": "Filter by specific project/repository (e.g., opensearch-dashboards-functional-test)",
                    "required": false
                },
                "test_type": {
                    "type": "string",
                    "description": "Type of test: functional, unit, integration, or all",
                    "required": false
                },
                "status_filter": {
                    "type": "string",
                    "description": "Filter by test status: passed, failed, open, closed, or all",
                    "required": false
                }
            },
            "requireConfirmation": "DISABLED"
        },
        {
            "name": "get_metrics",
            "description": "Generic metrics retrieval function for test data",
            "parameters": {
                "metric_type": {
                    "type": "string",
                    "description": "Type of metric: status, execution, coverage, or summary",
                    "required": false
                },
                "time_range": {
                    "type": "string",
                    "description": "Time range: 1d, 7d, 30d, or 90d", 
                    "required": false
                }
            },
            "requireConfirmation": "DISABLED"
        }
    ]
}
```

### 2. Build Metrics Agent Action Group

**Action Group Name**: `build-metrics-actions-v2`
**Lambda Function**: `oscar-build-metrics-agent-new`

```json
{
    "functions": [
        {
            "name": "get_build_metrics",
            "description": "Retrieve build performance metrics from opensearch-build and related repositories",
            "parameters": {
                "metric_type": {
                    "type": "string",
                    "description": "Type of build metric: execution, performance, pipeline, workflow, or summary",
                    "required": false
                },
                "time_range": {
                    "type": "string",
                    "description": "Time range: 1d, 7d, 30d, or 90d",
                    "required": false
                },
                "branch_filter": {
                    "type": "string", 
                    "description": "Filter by specific branch or repository (e.g., opensearch-build, documentation-website)",
                    "required": false
                },
                "build_type": {
                    "type": "string",
                    "description": "Type of build: main, release, feature, or all",
                    "required": false
                },
                "status_filter": {
                    "type": "string",
                    "description": "Filter by build status: success, failed, open, closed, or all",
                    "required": false
                },
                "pipeline_stage": {
                    "type": "string",
                    "description": "Specific pipeline stage: build, test, deploy, or all",
                    "required": false
                }
            },
            "requireConfirmation": "DISABLED"
        },
        {
            "name": "get_metrics",
            "description": "Generic metrics retrieval function for build data",
            "parameters": {
                "metric_type": {
                    "type": "string",
                    "description": "Type of metric: status, execution, performance, or summary",
                    "required": false
                },
                "time_range": {
                    "type": "string",
                    "description": "Time range: 1d, 7d, 30d, or 90d", 
                    "required": false
                }
            },
            "requireConfirmation": "DISABLED"
        }
    ]
}
```

### 3. Release Metrics Agent Action Group

**Action Group Name**: `release-metrics-actions-v2`
**Lambda Function**: `oscar-release-metrics-agent-new`

```json
{
    "functions": [
        {
            "name": "get_release_metrics",
            "description": "Retrieve release readiness metrics including release state, issues, PRs, and version tracking",
            "parameters": {
                "metric_type": {
                    "type": "string",
                    "description": "Type of release metric: frequency, success_rate, quality, readiness, rollbacks, or summary",
                    "required": false
                },
                "time_range": {
                    "type": "string",
                    "description": "Time range: 1d, 7d, 30d, or 90d",
                    "required": false
                },
                "environment_filter": {
                    "type": "string", 
                    "description": "Filter by repository name (mapped from environment since no environment field exists)",
                    "required": false
                },
                "release_state": {
                    "type": "string",
                    "description": "Filter by release state: open, closed, or all",
                    "required": false
                },
                "version_filter": {
                    "type": "string",
                    "description": "Filter by specific version pattern (e.g., 3.2.0, 3.1.0, 2.x)",
                    "required": false
                },
                "readiness_threshold": {
                    "type": "string",
                    "description": "Minimum readiness score based on release indicators: high, medium, low, or all",
                    "required": false
                }
            },
            "requireConfirmation": "DISABLED"
        },
        {
            "name": "get_metrics",
            "description": "Generic metrics retrieval function for release data",
            "parameters": {
                "metric_type": {
                    "type": "string",
                    "description": "Type of metric: status, execution, readiness, or summary",
                    "required": false
                },
                "time_range": {
                    "type": "string",
                    "description": "Time range: 1d, 7d, 30d, or 90d", 
                    "required": false
                }
            },
            "requireConfirmation": "DISABLED"
        }
    ]
}
```

### 4. Deployment Metrics Agent Action Group

**Action Group Name**: `deployment-metrics-actions-v2`
**Lambda Function**: `oscar-deployment-metrics-agent-new`

```json
{
    "functions": [
        {
            "name": "get_deployment_metrics",
            "description": "Retrieve deployment metrics focusing on core services and successfully released components",
            "parameters": {
                "metric_type": {
                    "type": "string",
                    "description": "Type of deployment metric: performance, health, infrastructure, operational, or summary",
                    "required": false
                },
                "time_range": {
                    "type": "string",
                    "description": "Time range: 1d, 7d, 30d, or 90d",
                    "required": false
                },
                "service_filter": {
                    "type": "string", 
                    "description": "Filter by core service component (e.g., OpenSearch, OpenSearch-Dashboards, security, alerting)",
                    "required": false
                },
                "environment": {
                    "type": "string",
                    "description": "Deployment environment context (mapped to repository filtering)",
                    "required": false
                },
                "health_status": {
                    "type": "string",
                    "description": "Filter by health status based on release state: healthy (closed), degraded (open), or all",
                    "required": false
                },
                "deployment_type": {
                    "type": "string",
                    "description": "Type of deployment: core, plugin, dashboard, or all",
                    "required": false
                }
            },
            "requireConfirmation": "DISABLED"
        },
        {
            "name": "get_metrics",
            "description": "Generic metrics retrieval function for deployment data",
            "parameters": {
                "metric_type": {
                    "type": "string",
                    "description": "Type of metric: status, execution, health, or summary",
                    "required": false
                },
                "time_range": {
                    "type": "string",
                    "description": "Time range: 1d, 7d, 30d, or 90d", 
                    "required": false
                }
            },
            "requireConfirmation": "DISABLED"
        }
    ]
}
```

## 🔧 Implementation Notes

### Key Changes Made:
1. **Added `get_metrics` function** to all agents (required for Bedrock orchestration)
2. **Specialized parameters** based on actual data structure discovered
3. **Realistic filtering options** that match available fields in the index
4. **Consistent parameter naming** across all agents
5. **7-parameter limit compliance** - restored all parameters with increased limit

### Data Structure Alignment:
- **Test Agent**: Focuses on `*test*` repositories and functional test data
- **Build Agent**: Targets `opensearch-build`, `documentation-website`, `project-website`
- **Release Agent**: Uses release readiness indicators (`release_state`, `release_branch`, `release_issue_exists`, etc.)
- **Deployment Agent**: Focuses on core services that would be deployed (`OpenSearch`, `OpenSearch-Dashboards`, etc.)

### Parameter Mapping:
- `environment_filter` → Repository filtering (since no environment field exists)
- `health_status` → Based on `release_state` (closed=healthy, open=degraded)
- `readiness_threshold` → Calculated from multiple release indicators

## 📝 Mentor Message

**Subject**: OpenSearch Index Discovery and Metrics Implementation

Hi [Mentor],

Quick update on the metrics system investigation:

**Issue with Mapping Discovery**: I was unable to run the standard OpenSearch mapping commands (`GET /_cat/indices`, `GET /index/_mapping`) due to insufficient permissions. The cross-account role `OpenSearchOscarAccessRole` lacks `indices:monitor/settings/get` and `indices:a`dmin/mappings/get` permissions.

**Workaround**: Used search queries and aggregations to discover the data structure. Found that all metrics data exists in a single index: `opensearch_release_metrics` (117K+ documents).

**Key Finding**: This index contains comprehensive release tracking data with fields for issues, PRs, release states, versions, and components - essentially serving as a unified metrics repository rather than separate indices for different metric types.

**Solution**: Implemented specialized query logic for each agent type (test, build, release, deployment) that filters the same index using different criteria based on repository patterns and component types discovered in the data.

The system is now working with proper data separation at the query level rather than index level.

Best,
[Your name]