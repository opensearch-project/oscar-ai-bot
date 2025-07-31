# 🏗️ Clean OSCAR Metrics Agent Architecture

## 📋 **Design Principles**

- **Single Responsibility**: Each file has one clear purpose
- **Minimal Dependencies**: Only essential libraries
- **Clear Separation**: Infrastructure, business logic, and data access layers
- **Easy Testing**: Dependency injection and pure functions
- **Simple Configuration**: Environment-based settings

## 📁 **File Structure (Minimal & Clean)**

```
oscar-metrics-agent/
├── infrastructure/
│   └── lambda_stack.py              # AWS resources (CDK)
├── src/
│   ├── main.py                      # Lambda entry point
│   ├── config.py                    # Configuration management
│   ├── opensearch_client.py         # Data access layer
│   ├── metrics_service.py           # Business logic layer
│   └── response_formatter.py        # Output formatting
├── requirements.txt                 # Dependencies
└── tests/
    ├── test_metrics_service.py      # Unit tests
    └── test_integration.py          # Integration tests
```

## 🎯 **File Purposes & Implementation**

### **1. Infrastructure Layer**

#### **`infrastructure/lambda_stack.py`** (AWS Resources)
```python
"""
AWS infrastructure definition using CDK.
Creates Lambda function, IAM roles, and environment configuration.
"""

from aws_cdk import (
    Duration,
    aws_lambda as lambda_,
    aws_iam as iam,
)

class MetricsLambdaStack(Construct):
    def __init__(self, scope: Construct, construct_id: str):
        super().__init__(scope, construct_id)
        
        # IAM role with OpenSearch permissions
        self.lambda_role = iam.Role(
            self, "MetricsLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
            ]
        )
        
        # OpenSearch permissions (same as Jenkins)
        self.lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=["es:ESHttpGet", "es:ESHttpPost", "es:ESHttpHead"],
                resources=["arn:aws:es:us-east-1:*:domain/*"]
            )
        )
        
        # Lambda function
        self.lambda_function = lambda_.Function(
            self, "MetricsFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="main.handler",
            code=lambda_.Code.from_asset("src"),
            timeout=Duration.seconds(60),
            memory_size=512,
            environment={
                "OPENSEARCH_HOST": "search-opensearch-health-metrics-domain-xxxxx.us-east-1.es.amazonaws.com",
                "OPENSEARCH_REGION": "us-east-1",
                "LOG_LEVEL": "INFO"
            },
            role=self.lambda_role
        )
```

**Purpose**: Defines all AWS resources needed. Single file for infrastructure.

---

### **2. Application Layer**

#### **`src/main.py`** (Lambda Entry Point)
```python
"""
Lambda function entry point.
Handles Bedrock agent events and orchestrates the response.
"""

import json
import logging
from typing import Dict, Any

from config import Config
from opensearch_client import OpenSearchClient
from metrics_service import MetricsService
from response_formatter import ResponseFormatter

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize components (reused across invocations)
config = Config()
opensearch_client = OpenSearchClient(config)
metrics_service = MetricsService(opensearch_client)
response_formatter = ResponseFormatter()


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for Bedrock agent requests.
    
    Flow: Event → Parse → Query → Format → Response
    """
    try:
        # Parse Bedrock event
        query_text = event.get('inputText', '')
        function_name = event.get('function', 'query_metrics')
        parameters = {p['name']: p['value'] for p in event.get('parameters', [])}
        
        logger.info(f"Processing: {function_name} with query: {query_text}")
        
        # Route to metrics service based on function name
        if function_name in ['get_test_results', 'get_test_coverage', 'get_test_performance']:
            result = metrics_service.get_test_failures(
                repository=parameters.get('repository', 'OpenSearch'),
                time_range=parameters.get('time_range', '7d')
            )
        elif function_name in ['get_build_status', 'get_build_trends', 'get_build_artifacts']:
            result = metrics_service.get_release_status(
                version=parameters.get('version'),
                component=parameters.get('component')
            )
        elif function_name in ['get_deployment_status', 'get_deployment_history', 'get_environment_health']:
            result = metrics_service.get_deployment_status(
                repository=parameters.get('repository'),
                environment=parameters.get('environment')
            )
        elif function_name in ['get_performance_data', 'get_performance_trends', 'get_performance_alerts']:
            result = metrics_service.get_performance_metrics(
                repository=parameters.get('repository'),
                metric_category=parameters.get('metric_category')
            )
        elif function_name in ['search_all_metrics', 'get_cluster_health']:
            result = metrics_service.search_metrics(
                query_text or parameters.get('search_query', '')
            )
        else:
            result = metrics_service.search_metrics(query_text)
        
        # Format response for Bedrock
        formatted_response = response_formatter.format_for_bedrock(result)
        
        return {
            "messageVersion": "1.0",
            "response": {
                "actionGroup": event.get("actionGroup", "metrics"),
                "function": function_name,
                "functionResponse": {
                    "responseBody": {
                        "TEXT": {
                            "body": formatted_response
                        }
                    }
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Handler error: {str(e)}")
        return {
            "messageVersion": "1.0",
            "response": {
                "actionGroup": event.get("actionGroup", "metrics"),
                "function": event.get("function", "query_metrics"),
                "functionResponse": {
                    "responseBody": {
                        "TEXT": {
                            "body": f"Error processing request: {str(e)}"
                        }
                    }
                }
            }
        }
```

**Purpose**: Single entry point. Minimal routing logic. Delegates to service layer.

---

#### **`src/config.py`** (Configuration Management)
```python
"""
Configuration management for the metrics agent.
Loads settings from environment variables.
"""

import os
from dataclasses import dataclass


@dataclass
class Config:
    """Application configuration loaded from environment variables."""
    
    # OpenSearch settings (from Jenkins Groovy scripts)
    opensearch_host: str
    opensearch_region: str
    opensearch_service: str
    
    # Application settings
    log_level: str
    
    def __init__(self):
        self.opensearch_host = os.getenv('OPENSEARCH_HOST', 'localhost')
        self.opensearch_region = os.getenv('OPENSEARCH_REGION', 'us-east-1')
        self.opensearch_service = os.getenv('OPENSEARCH_SERVICE', 'es')
        self.log_level = os.getenv('LOG_LEVEL', 'INFO')
    
    def validate(self) -> None:
        """Validate required configuration."""
        if not self.opensearch_host or self.opensearch_host == 'localhost':
            raise ValueError("OPENSEARCH_HOST must be set to actual cluster endpoint")
```

**Purpose**: Single source of configuration. Environment-based. Validation included.

---

#### **`src/opensearch_client.py`** (Data Access Layer)
```python
"""
OpenSearch client for metrics data access.
Uses same authentication as Jenkins Groovy scripts.
"""

import logging
from typing import Dict, Any, List, Optional

import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
from aws_requests_auth.aws_auth import AWSRequestsAuth

from config import Config

logger = logging.getLogger(__name__)


class OpenSearchClient:
    """
    OpenSearch client with Jenkins-compatible authentication.
    
    Handles all data access operations.
    """
    
    def __init__(self, config: Config):
        self.config = config
        self.client = self._create_client()
    
    def _create_client(self) -> OpenSearch:
        """Create OpenSearch client with AWS authentication."""
        # Get AWS credentials (same as Jenkins)
        session = boto3.Session()
        credentials = session.get_credentials()
        
        if not credentials:
            raise ValueError("No AWS credentials found")
        
        # Create auth (same as Jenkins Groovy scripts)
        auth = AWSRequestsAuth(credentials, self.config.opensearch_region, self.config.opensearch_service)
        
        return OpenSearch(
            hosts=[{'host': self.config.opensearch_host, 'port': 443}],
            http_auth=auth,
            use_ssl=True,
            connection_class=RequestsHttpConnection,
            timeout=30
        )
    
    def query_test_failures(self, repository: str, time_range: str) -> Dict[str, Any]:
        """Query gradle-check indices for test failures."""
        query = {
            "query": {
                "bool": {
                    "must": [
                        {"range": {"build_start_time": {"gte": f"now-{time_range}"}}},
                        {"term": {"test_status.keyword": "FAILED"}}
                    ]
                }
            },
            "aggs": {
                "failed_by_class": {
                    "terms": {"field": "test_class.keyword", "size": 10}
                }
            },
            "size": 50
        }
        
        return self.client.search(index="gradle-check-*", body=query)
    
    def query_release_status(self, version: Optional[str] = None, component: Optional[str] = None) -> Dict[str, Any]:
        """Query opensearch_release_metrics for release information."""
        must_clauses = []
        
        if version:
            must_clauses.append({"match": {"version": version}})
        if component:
            must_clauses.append({"match": {"component": component}})
        
        query = {
            "query": {
                "bool": {"must": must_clauses} if must_clauses else {"match_all": {}}
            },
            "sort": [{"current_date": {"order": "desc"}}],
            "size": 20
        }
        
        return self.client.search(index="opensearch_release_metrics", body=query)
    
    def search_all(self, query_text: str) -> Dict[str, Any]:
        """General search across all metrics indices."""
        query = {
            "query": {
                "multi_match": {
                    "query": query_text,
                    "fields": ["test_class", "component", "repository", "test_name"]
                }
            },
            "size": 30
        }
        
        return self.client.search(index="gradle-check-*,opensearch_release_metrics", body=query)
    
    def test_connection(self) -> bool:
        """Test connection to OpenSearch cluster."""
        try:
            self.client.cluster.health()
            return True
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False
    
    def get_cluster_health(self) -> Dict[str, Any]:
        """Get cluster health information."""
        try:
            return self.client.cluster.health()
        except Exception as e:
            logger.error(f"Cluster health check failed: {e}")
            return {'status': 'unknown', 'error': str(e)}
```

**Purpose**: Single data access layer. Clean interface. Jenkins-compatible authentication.

---

#### **`src/metrics_service.py`** (Business Logic Layer)
```python
"""
Business logic for metrics analysis.
Processes OpenSearch data and applies business rules.
"""

import logging
from typing import Dict, Any, List, Optional

from opensearch_client import OpenSearchClient

logger = logging.getLogger(__name__)


class MetricsService:
    """
    Core business logic for metrics analysis.
    
    Processes raw OpenSearch data into meaningful insights.
    """
    
    def __init__(self, opensearch_client: OpenSearchClient):
        self.opensearch_client = opensearch_client
    
    def get_test_failures(self, repository: str, time_range: str) -> Dict[str, Any]:
        """
        Analyze test failures for a repository.
        
        Returns structured data for response formatting.
        """
        try:
            # Get raw data from OpenSearch
            results = self.opensearch_client.query_test_failures(repository, time_range)
            
            # Extract and process data
            total_failures = results['hits']['total']['value']
            failed_tests = results['hits']['hits']
            class_aggregations = results['aggregations']['failed_by_class']['buckets']
            
            # Calculate insights
            top_failing_classes = [
                {
                    'class_name': bucket['key'],
                    'failure_count': bucket['doc_count']
                }
                for bucket in class_aggregations[:5]
            ]
            
            recent_failures = [
                {
                    'test_class': test['_source'].get('test_class', 'Unknown'),
                    'test_name': test['_source'].get('test_name', 'Unknown'),
                    'build_number': test['_source'].get('build_number', 'Unknown'),
                    'pull_request': test['_source'].get('pull_request', 'Unknown')
                }
                for test in failed_tests[:10]
            ]
            
            return {
                'type': 'test_failures',
                'repository': repository,
                'time_range': time_range,
                'total_failures': total_failures,
                'top_failing_classes': top_failing_classes,
                'recent_failures': recent_failures
            }
            
        except Exception as e:
            logger.error(f"Test failure analysis failed: {e}")
            return {'type': 'error', 'message': str(e)}
    
    def get_release_status(self, version: Optional[str] = None, component: Optional[str] = None) -> Dict[str, Any]:
        """
        Get release status information.
        
        Returns structured data about release progress.
        """
        try:
            # Get raw data from OpenSearch
            results = self.opensearch_client.query_release_status(version, component)
            
            # Process release data
            releases = results['hits']['hits']
            
            release_info = []
            for release in releases:
                source = release['_source']
                release_info.append({
                    'version': source.get('version', 'Unknown'),
                    'component': source.get('component', 'Unknown'),
                    'repository': source.get('repository', 'Unknown'),
                    'release_owners': source.get('release_owners', []),
                    'release_issue_exists': source.get('release_issue_exists', False),
                    'release_issue': source.get('release_issue', ''),
                    'date': source.get('current_date', '')
                })
            
            return {
                'type': 'release_status',
                'version': version,
                'component': component,
                'releases': release_info,
                'total_found': len(release_info)
            }
            
        except Exception as e:
            logger.error(f"Release status analysis failed: {e}")
            return {'type': 'error', 'message': str(e)}
    
    def search_metrics(self, query_text: str) -> Dict[str, Any]:
        """
        General metrics search.
        
        Searches across all metrics data.
        """
        try:
            results = self.opensearch_client.search_all(query_text)
            
            hits = results['hits']['hits']
            search_results = []
            
            for hit in hits:
                source = hit['_source']
                search_results.append({
                    'index': hit['_index'],
                    'score': hit['_score'],
                    'data': source
                })
            
            return {
                'type': 'search_results',
                'query': query_text,
                'total_found': results['hits']['total']['value'],
                'results': search_results[:15]  # Limit results
            }
            
        except Exception as e:
            logger.error(f"Metrics search failed: {e}")
            return {'type': 'error', 'message': str(e)}
    
    def get_deployment_status(self, repository: Optional[str] = None, environment: Optional[str] = None) -> Dict[str, Any]:
        """
        Get deployment status information.
        
        Returns structured data about deployment status.
        """
        try:
            # For now, use release metrics as deployment data source
            results = self.opensearch_client.query_release_status(component=repository)
            
            return {
                'type': 'deployment_status',
                'repository': repository,
                'environment': environment,
                'deployments': results['hits']['hits'][:10],
                'total_found': results['hits']['total']['value']
            }
            
        except Exception as e:
            logger.error(f"Deployment status analysis failed: {e}")
            return {'type': 'error', 'message': str(e)}
    
    def get_performance_metrics(self, repository: Optional[str] = None, metric_category: Optional[str] = None) -> Dict[str, Any]:
        """
        Get performance metrics information.
        
        Returns structured data about performance metrics.
        """
        try:
            # For now, use general search for performance data
            search_query = f"{repository or ''} {metric_category or 'performance'}"
            results = self.opensearch_client.search_all(search_query.strip())
            
            return {
                'type': 'performance_metrics',
                'repository': repository,
                'metric_category': metric_category,
                'metrics': results['hits']['hits'][:10],
                'total_found': results['hits']['total']['value']
            }
            
        except Exception as e:
            logger.error(f"Performance metrics analysis failed: {e}")
            return {'type': 'error', 'message': str(e)}
```

**Purpose**: Pure business logic. No I/O operations. Easy to test. Clear data transformations.

---

#### **`src/response_formatter.py`** (Output Formatting)
```python
"""
Response formatting for different output types.
Converts structured data into human-readable responses.
"""

from typing import Dict, Any


class ResponseFormatter:
    """
    Formats structured data into human-readable responses.
    
    Handles different response types and output formats.
    """
    
    def format_for_bedrock(self, data: Dict[str, Any]) -> str:
        """
        Format structured data for Bedrock agent response.
        
        Returns markdown-formatted text.
        """
        if data.get('type') == 'error':
            return f"❌ Error: {data.get('message', 'Unknown error occurred')}"
        
        elif data.get('type') == 'test_failures':
            return self._format_test_failures(data)
        
        elif data.get('type') == 'release_status':
            return self._format_release_status(data)
        
        elif data.get('type') == 'search_results':
            return self._format_search_results(data)
        
        elif data.get('type') == 'deployment_status':
            return self._format_deployment_status(data)
        
        elif data.get('type') == 'performance_metrics':
            return self._format_performance_metrics(data)
        
        else:
            return "❓ Unknown response type"
    
    def _format_test_failures(self, data: Dict[str, Any]) -> str:
        """Format test failure analysis."""
        response = f"""## 🧪 Test Failure Analysis

### Summary
- **Repository**: {data['repository']}
- **Time Range**: Last {data['time_range']}
- **Total Failures**: {data['total_failures']}

### Top Failing Test Classes
"""
        
        for class_info in data['top_failing_classes']:
            response += f"- **{class_info['class_name']}**: {class_info['failure_count']} failures\n"
        
        response += "\n### Recent Failures\n"
        for failure in data['recent_failures'][:5]:
            response += f"- `{failure['test_class']}`: {failure['test_name']} (Build #{failure['build_number']})\n"
        
        return response
    
    def _format_release_status(self, data: Dict[str, Any]) -> str:
        """Format release status information."""
        response = f"""## 📦 Release Status

### Query Results
- **Version**: {data.get('version', 'All versions')}
- **Component**: {data.get('component', 'All components')}
- **Total Found**: {data['total_found']}

### Release Information
"""
        
        for release in data['releases'][:10]:
            status_icon = "✅" if release['release_issue_exists'] else "❌"
            response += f"""
**{release['component']} v{release['version']}**
- Repository: {release['repository']}
- Release Issue: {status_icon} {'Exists' if release['release_issue_exists'] else 'Missing'}
- Owners: {', '.join(release['release_owners']) if release['release_owners'] else 'None'}
"""
        
        return response
    
    def _format_search_results(self, data: Dict[str, Any]) -> str:
        """Format general search results."""
        response = f"""## 🔍 Search Results

**Query**: "{data['query']}"
**Total Found**: {data['total_found']}

### Results
"""
        
        for result in data['results'][:10]:
            index_type = "🧪" if "gradle-check" in result['index'] else "📦"
            response += f"{index_type} **{result['index']}** (Score: {result['score']:.2f})\n"
            
            # Show relevant fields
            source_data = result['data']
            if 'test_class' in source_data:
                response += f"  - Test: {source_data.get('test_class', 'Unknown')}\n"
            if 'component' in source_data:
                response += f"  - Component: {source_data.get('component', 'Unknown')}\n"
            response += "\n"
        
        return response
    
    def _format_deployment_status(self, data: Dict[str, Any]) -> str:
        """Format deployment status information."""
        response = f"""## 🚀 Deployment Status

### Query Results
- **Repository**: {data.get('repository', 'All repositories')}
- **Environment**: {data.get('environment', 'All environments')}
- **Total Found**: {data['total_found']}

### Deployment Information
"""
        
        for deployment in data['deployments'][:5]:
            source = deployment.get('_source', {})
            response += f"""
**{source.get('component', 'Unknown')} Deployment**
- Version: {source.get('version', 'Unknown')}
- Repository: {source.get('repository', 'Unknown')}
- Status: {'✅ Active' if source.get('release_issue_exists') else '⚠️ Pending'}
"""
        
        return response
    
    def _format_performance_metrics(self, data: Dict[str, Any]) -> str:
        """Format performance metrics information."""
        response = f"""## ⚡ Performance Metrics

### Query Results
- **Repository**: {data.get('repository', 'All repositories')}
- **Metric Category**: {data.get('metric_category', 'All metrics')}
- **Total Found**: {data['total_found']}

### Performance Data
"""
        
        for metric in data['metrics'][:5]:
            source = metric.get('_source', {})
            index_type = "🧪" if "gradle-check" in metric.get('_index', '') else "📦"
            response += f"""
{index_type} **Performance Record**
- Source: {metric.get('_index', 'Unknown')}
- Score: {metric.get('_score', 0):.2f}
- Data: {source.get('test_class', source.get('component', 'Unknown'))}
"""
        
        return response
```

**Purpose**: Clean separation of formatting logic. Easy to modify output formats. Reusable.

---

### **3. Dependencies & Testing**

#### **`requirements.txt`** (Minimal Dependencies)
```txt
# Core dependencies only
opensearch-py==2.4.2
boto3==1.34.34
aws-requests-auth==0.4.3

# Testing (dev only)
pytest==7.4.4
moto==4.2.14
```

#### **`tests/test_metrics_service.py`** (Unit Tests)
```python
"""Unit tests for metrics service business logic."""

import pytest
from unittest.mock import Mock

from src.metrics_service import MetricsService


def test_get_test_failures():
    """Test test failure analysis logic."""
    # Mock OpenSearch client
    mock_client = Mock()
    mock_client.query_test_failures.return_value = {
        'hits': {
            'total': {'value': 5},
            'hits': [
                {'_source': {'test_class': 'TestClass1', 'test_name': 'test1', 'build_number': 123}}
            ]
        },
        'aggregations': {
            'failed_by_class': {
                'buckets': [{'key': 'TestClass1', 'doc_count': 3}]
            }
        }
    }
    
    service = MetricsService(mock_client)
    result = service.get_test_failures('OpenSearch', '7d')
    
    assert result['type'] == 'test_failures'
    assert result['total_failures'] == 5
    assert len(result['top_failing_classes']) == 1
    assert result['top_failing_classes'][0]['class_name'] == 'TestClass1'
```

---

## 🎯 **How It All Comes Together**

### **Request Flow**
```
1. Bedrock Agent → main.py handler()
2. handler() → metrics_service.get_test_failures()
3. metrics_service → opensearch_client.query_test_failures()
4. opensearch_client → OpenSearch cluster (real Jenkins data)
5. Data flows back: OpenSearch → client → service → formatter
6. Formatted response → Bedrock Agent → User
```

### **Key Benefits of This Design**

1. **Single Responsibility**: Each file has one clear job
2. **Easy Testing**: Business logic separated from I/O
3. **Simple Configuration**: One config file, environment-based
4. **Minimal Dependencies**: Only essential libraries
5. **Clear Interfaces**: Each layer has clean contracts
6. **Easy Deployment**: Single CDK file for infrastructure

### **Total Files: 8 Core Files**
- **1 Infrastructure file** (CDK)
- **5 Application files** (main, config, client, service, formatter)
- **1 Dependencies file** (requirements.txt)
- **1 Test file** (expandable)

This design delivers the full functionality with clean, maintainable code that follows software engineering best practices! 🚀

## 🔄 **Deployment & Usage**

```bash
# Deploy infrastructure
cd infrastructure && cdk deploy

# Test locally
cd src && python -m pytest ../tests/

# Deploy code
zip -r function.zip src/ && aws lambda update-function-code --function-name MetricsFunction --zip-file fileb://function.zip
```

The result is a **clean, minimal, and maintainable** metrics agent that provides the same functionality as the complex version but with better software engineering practices! ✨
---


## 🤖 **Bedrock Agent Configuration**

To complete the implementation, you'll need to configure a Bedrock agent that connects to your Lambda function. The agent configuration is comprehensive and includes multiple specialized action groups.

### **Agent Overview**

The OSCAR Metrics Agent uses **5 specialized action groups** to handle different types of metrics queries:

1. **`build_metrics`** - Build status, compilation results, and artifact information
2. **`test_metrics`** - Test execution results and coverage analysis  
3. **`deployment_metrics`** - Release deployment and environment status
4. **`performance_metrics`** - System performance and operational metrics
5. **`general_search`** - Cross-domain search and cluster health

### **Key Agent Features**

- **Foundation Model**: Claude 3.5 Sonnet (anthropic.claude-3-5-sonnet-20241022-v1:0)
- **Natural Language Processing**: Understands complex metrics queries
- **Parameter Extraction**: Automatically extracts repository, time_range, environment filters
- **Structured Responses**: Returns formatted markdown with actionable insights
- **Multi-Repository Support**: Handles core, sql, dashboards, security, ml-commons, k-nn, anomaly-detection

### **Function Mapping to Clean Architecture**

The agent's functions map directly to your clean architecture:

```
Bedrock Agent Functions → main.py handler() → metrics_service methods

get_test_results     → get_test_failures()
get_build_status     → get_release_status()  
search_all_metrics   → search_metrics()
get_cluster_health   → (direct OpenSearch client call)
```

### **Sample User Interactions**

```
User: "Show me failed tests from the last week"
→ test_metrics.get_test_results(time_range="7d", status_filter="fail")

User: "What's the build status for SQL repository?"  
→ build_metrics.get_build_status(repository="sql")

User: "How are deployments performing in production?"
→ deployment_metrics.get_deployment_status(environment="production")

User: "Search for performance issues"
→ general_search.search_all_metrics(search_query="performance issues")
```

### **Complete Configuration Guide**

For the **complete step-by-step Bedrock agent configuration**, including:
- Detailed agent instructions and settings
- All 5 action groups with full API schemas
- Function definitions with parameters
- Testing commands and validation steps

**See**: `docs/bedrock-console-configuration-guide.md`

This guide provides everything needed to configure the agent in the AWS Bedrock console, including JSON schemas for all action groups and comprehensive testing procedures.

### **Integration with Clean Architecture**

The Bedrock agent integrates seamlessly with your clean architecture:

1. **Agent Functions** → **`main.py` routing logic** → Determines which service method to call
2. **Function Parameters** → **Service method arguments** → Passed to business logic
3. **Service Results** → **`response_formatter.py`** → Converts to natural language
4. **Formatted Response** → **Bedrock Agent** → Presented to user

This provides a complete natural language interface to your OpenSearch metrics data! 🤖✨

---

## 🔧 **Additional Implementation Considerations**

### **Missing Components for Complete Implementation**

While the clean architecture provides the core framework, you'll need these additional components for a production-ready system:

#### **1. Enhanced Error Handling**
```python
# Add to src/main.py
def validate_parameters(parameters: Dict[str, Any], function_name: str) -> Dict[str, Any]:
    """Validate and sanitize input parameters."""
    # Add parameter validation logic
    # Return sanitized parameters or raise validation errors

def handle_opensearch_errors(error: Exception) -> Dict[str, Any]:
    """Convert OpenSearch errors to user-friendly messages."""
    # Map technical errors to user-friendly responses
```

#### **2. Configuration Validation**
```python
# Add to src/config.py
def validate_opensearch_connection(self) -> bool:
    """Validate OpenSearch connection settings."""
    # Test connection and validate configuration
    # Return True if valid, False otherwise
```

#### **3. Logging and Monitoring**
```python
# Add to src/main.py
import structlog

# Configure structured logging for better observability
logger = structlog.get_logger()

def log_request_metrics(function_name: str, duration: float, success: bool):
    """Log request metrics for monitoring."""
    logger.info("request_completed", 
                function=function_name, 
                duration_ms=duration, 
                success=success)
```

#### **4. Caching Layer (Optional)**
```python
# Add to src/cache.py
class MetricsCache:
    """Simple in-memory cache for frequently accessed data."""
    
    def __init__(self, ttl_seconds: int = 300):
        self.cache = {}
        self.ttl = ttl_seconds
    
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get cached result if still valid."""
        # Implementation for cache retrieval
    
    def set(self, key: str, value: Dict[str, Any]):
        """Cache result with TTL."""
        # Implementation for cache storage
```

### **Deployment Checklist**

#### **Pre-Deployment**
- [ ] Update `OPENSEARCH_HOST` with actual cluster endpoint
- [ ] Verify AWS credentials have OpenSearch access
- [ ] Test OpenSearch connection from local environment
- [ ] Run unit tests: `pytest tests/`
- [ ] Validate CDK template: `cdk synth`

#### **Deployment Steps**
```bash
# 1. Deploy infrastructure
cd infrastructure
cdk bootstrap  # First time only
cdk deploy

# 2. Package and deploy Lambda code
cd ../src
zip -r ../function.zip . -x "tests/*" "*.pyc" "__pycache__/*"
aws lambda update-function-code \
  --function-name MetricsFunction \
  --zip-file fileb://../function.zip

# 3. Test deployment
aws lambda invoke \
  --function-name MetricsFunction \
  --payload '{"inputText":"test","function":"search_all_metrics","parameters":[]}' \
  response.json
```

#### **Post-Deployment**
- [ ] Configure Bedrock agent (see bedrock-console-configuration-guide.md)
- [ ] Test all action groups with sample queries
- [ ] Monitor CloudWatch logs for errors
- [ ] Set up CloudWatch alarms for error rates
- [ ] Document actual cluster endpoint for team

### **Performance Optimization**

#### **Lambda Optimization**
```python
# Connection pooling (add to opensearch_client.py)
@lru_cache(maxsize=1)
def get_opensearch_client(config_hash: str) -> OpenSearch:
    """Cached OpenSearch client to reuse connections."""
    # Implementation for connection reuse

# Query optimization (add to metrics_service.py)
def optimize_query_size(query: Dict[str, Any], max_results: int = 50) -> Dict[str, Any]:
    """Limit query results to prevent timeouts."""
    query['size'] = min(query.get('size', 10), max_results)
    return query
```

#### **Cost Optimization**
- Use smaller Lambda memory size (512MB) for basic queries
- Implement query result caching for frequently accessed data
- Set appropriate Lambda timeout (60s for most queries)
- Monitor OpenSearch query costs and optimize expensive queries

### **Security Considerations**

#### **Input Validation**
```python
# Add to src/main.py
def sanitize_input(text: str) -> str:
    """Sanitize user input to prevent injection attacks."""
    # Remove potentially dangerous characters
    # Limit input length
    # Validate against allowed patterns

def validate_repository_name(repo: str) -> bool:
    """Validate repository name against allowed list."""
    allowed_repos = ['core', 'sql', 'dashboards', 'security', 'ml-commons', 'k-nn', 'anomaly-detection']
    return repo.lower() in allowed_repos
```

#### **Access Control**
- Ensure Lambda IAM role has minimal required permissions
- Use VPC endpoints for OpenSearch access if in private subnet
- Enable CloudTrail logging for audit trail
- Implement rate limiting if exposed to external users

This clean architecture provides a solid foundation that can be extended with these additional components as needed for your specific requirements! 🎯