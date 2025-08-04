# OSCAR Metrics System - Complete Overview

## 🏗️ **System Architecture**

### High-Level Flow
```
User Query → OSCAR Supervisor Agent (Bedrock) 
    ↓
Bedrock Multi-Agent Collaboration
    ↓
Specialized Collaborator Agents (4 agents)
    ↓
Specialized Lambda Functions (4 functions)
    ↓
OpenSearch Cluster (gradle-check-*, opensearch_release_metrics)
    ↓
Formatted Response → User
```

### Components Overview

#### 1. **Bedrock Agents (5 total)**
- **OSCAR Supervisor Agent** - Main orchestrator with multi-agent collaboration
- **Test Metrics Collaborator** - Specialized for test analysis
- **Build Metrics Collaborator** - Specialized for build analysis  
- **Release Metrics Collaborator** - Specialized for release tracking
- **Deployment Metrics Collaborator** - Specialized for deployment monitoring

#### 2. **Lambda Functions (4 specialized)**
- **oscar-test-metrics-agent** - Test failure analysis and coverage
- **oscar-build-metrics-agent** - Build status and compilation analysis
- **oscar-release-metrics-agent** - Release readiness and version tracking
- **oscar-deployment-metrics-agent** - Deployment monitoring and environment health

#### 3. **Data Sources**
- **gradle-check-*** indices - Test execution data, build information
- **opensearch_release_metrics** index - Release status, component readiness
- **Knowledge Base** - OpenSearch documentation and best practices

## 📊 **Data Model & Query Structure**

### OpenSearch Indices Structure

#### gradle-check-* Indices (Test & Build Data)
```json
{
  "build_start_time": "2024-01-15T10:30:00Z",
  "repository": "core",
  "build_number": "12345",
  "test_class": "org.opensearch.search.SearchServiceTests",
  "test_name": "testSearchTimeout",
  "test_status": "FAILED",
  "pull_request": "PR-1234",
  "build_url": "https://build.ci.opensearch.org/job/...",
  "failure_message": "Timeout waiting for search response"
}
```

#### opensearch_release_metrics Index (Release Data)
```json
{
  "current_date": "2024-01-15",
  "version": "2.11.0",
  "component": "core",
  "repository": "OpenSearch",
  "release_owners": ["owner1", "owner2"],
  "release_issue_exists": true,
  "release_issue": "https://github.com/opensearch-project/OpenSearch/issues/1234"
}
```

### Query Patterns

#### Test Metrics Queries
```javascript
// Get test failures for repository in time range
{
  "query": {
    "bool": {
      "must": [
        {"range": {"build_start_time": {"gte": "now-7d"}}},
        {"term": {"repository.keyword": "core"}},
        {"term": {"test_status.keyword": "FAILED"}}
      ]
    }
  },
  "aggs": {
    "failed_by_class": {
      "terms": {"field": "test_class.keyword", "size": 10}
    }
  }
}
```

#### Release Metrics Queries
```javascript
// Get release status for version/component
{
  "query": {
    "bool": {
      "must": [
        {"match": {"version": "2.11.0"}},
        {"match": {"component": "core"}}
      ]
    }
  },
  "sort": [{"current_date": {"order": "desc"}}]
}
```

## 🔄 **End-to-End Flow Detailed**

### 1. User Query Processing
```
User: "Show me test failures from the last week"
    ↓
OSCAR Supervisor Agent receives query
    ↓
Bedrock analyzes query and determines: test-related
    ↓
Delegates to test_metrics_collaborator
```

### 2. Collaborator Processing
```
test_metrics_collaborator receives delegation
    ↓
Invokes oscar-test-metrics-agent Lambda
    ↓
Lambda function: analyze_test_metrics
```

### 3. Lambda Function Processing
```python
def handler(event, context):
    # Parse Bedrock event
    function_name = event.get('function', 'analyze_test_metrics')
    parameters = extract_parameters(event)
    
    # Route to metrics service
    result = metrics_service.get_test_failures(
        repository=parameters.get('repository', 'OpenSearch'),
        time_range=parameters.get('time_range', '7d'),
        status_filter='fail'
    )
    
    # Format for Bedrock
    formatted_response = response_formatter.format_for_bedrock(result)
    
    return bedrock_response(formatted_response)
```

### 4. Data Access Layer
```python
class MetricsService:
    def get_test_failures(self, repository, time_range, status_filter):
        # Query OpenSearch
        results = self.opensearch_client.query_test_failures(
            repository, time_range, status_filter
        )
        
        # Process and analyze data
        return {
            'type': 'test_metrics',
            'total_failures': results['hits']['total']['value'],
            'top_failing_classes': process_aggregations(results),
            'recent_failures': process_hits(results)
        }
```

### 5. Response Formatting
```python
class ResponseFormatter:
    def format_for_bedrock(self, data):
        if data['type'] == 'test_metrics':
            return f"""🧪 **Test Execution Analysis**
            
**Repository**: {data['repository']}
**Total Failures**: {data['total_failures']}

### Top Failing Test Classes
{format_failing_classes(data['top_failing_classes'])}

### Recent Failures
{format_recent_failures(data['recent_failures'])}
"""
```

### 6. Response Coordination
```
Lambda returns formatted response
    ↓
test_metrics_collaborator receives response
    ↓
Bedrock coordinates with supervisor
    ↓
OSCAR Supervisor Agent synthesizes final response
    ↓
User receives comprehensive analysis
```

## 🎯 **Multi-Agent Coordination Examples**

### Single-Agent Query
```
User: "Show me test failures"
→ Supervisor → test_metrics_collaborator → Test Lambda → Response
```

### Multi-Agent Query
```
User: "Give me comprehensive project status"
→ Supervisor → Multiple collaborators in parallel:
   ├── test_metrics_collaborator → Test Lambda
   ├── build_metrics_collaborator → Build Lambda  
   ├── release_metrics_collaborator → Release Lambda
   └── deployment_metrics_collaborator → Deploy Lambda
→ Bedrock aggregates all responses → Unified response
```

### Knowledge + Metrics Query
```
User: "How do I configure security and what's its current test status?"
→ Supervisor uses both:
   ├── Knowledge Base → Security configuration docs
   └── test_metrics_collaborator → Current security test status
→ Combined response with docs + real-time data
```

## 📁 **Code Structure Overview**

### Core Files
```
multi-agent/src/
├── test_metrics_agent.py      # Test analysis specialist
├── build_metrics_agent.py     # Build status specialist  
├── release_metrics_agent.py   # Release tracking specialist
├── deployment_metrics_agent.py # Deployment monitoring specialist
└── (shared from metrics/src/)
    ├── config.py              # Environment configuration
    ├── opensearch_client.py   # Data access layer
    ├── metrics_service.py     # Business logic
    └── response_formatter.py  # Output formatting
```

### Key Classes

#### MetricsService (Business Logic)
```python
class MetricsService:
    def get_test_failures(self, repository, time_range, analysis_type, build_id, status_filter)
    def get_build_status(self, repository, time_range, analysis_type, build_id, status_filter)  
    def get_release_metrics(self, repository, version, analysis_type, component, time_range)
    def get_deployment_status(self, repository, environment, analysis_type, time_range, version)
    def search_metrics(self, search_query, metric_types, repository, time_range)
    def get_cluster_health(self, cluster_name, health_aspect, include_details, time_range)
```

#### OpenSearchClient (Data Access)
```python
class OpenSearchClient:
    def query_test_failures(self, repository, time_range, status_filter)
    def query_release_status(self, version, component)
    def search_all(self, query_text, metric_types, repository, time_range)
    def get_cluster_health()
    def test_connection()
```

#### ResponseFormatter (Output)
```python
class ResponseFormatter:
    def format_for_bedrock(self, data)
    def _format_test_metrics(self, data)
    def _format_build_metrics(self, data)
    def _format_release_metrics(self, data)
    def _format_deployment_metrics(self, data)
```

## 🔧 **Configuration & Environment**

### Required Environment Variables
```bash
OPENSEARCH_HOST="search-opensearch-health-metrics-domain-xxxxx.us-east-1.es.amazonaws.com"
OPENSEARCH_REGION="us-east-1"
OPENSEARCH_SERVICE="es"
LOG_LEVEL="INFO"
```

### AWS Permissions Required
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "es:ESHttpGet",
        "es:ESHttpPost", 
        "es:ESHttpHead"
      ],
      "Resource": "arn:aws:es:*:*:domain/*"
    }
  ]
}
```

## 🎭 **Mock System for Testing**

For development and testing without OpenSearch connectivity, the system includes:

### Mock Data Sources
- Simulated test failure data
- Mock build status information  
- Fake release metrics
- Simulated deployment data

### Mock Responses
- Realistic response formats
- Proper error handling
- Consistent data structures
- Time-based variations

### Testing Capabilities
- End-to-end flow validation
- Multi-agent coordination testing
- Response formatting verification
- Error scenario simulation

This allows complete system testing without requiring actual OpenSearch cluster access, making development and validation much easier.

## 🚀 **Deployment Strategy**

### Phase 1: Infrastructure
1. Deploy Lambda functions with mock data
2. Configure Bedrock agents
3. Test multi-agent collaboration

### Phase 2: Integration  
1. Configure OpenSearch connectivity
2. Replace mock with real data access
3. Validate against actual metrics

### Phase 3: Production
1. Monitor performance and accuracy
2. Optimize queries and responses
3. Scale based on usage patterns

This approach ensures a solid foundation that can be incrementally enhanced with real data connectivity.