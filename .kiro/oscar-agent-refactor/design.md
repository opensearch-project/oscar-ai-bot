# Design Document

## Overview

This document outlines the comprehensive design for refactoring the OSCAR system from a direct LLM implementation to a Bedrock Agent-based architecture. The refactoring will be implemented in two phases:

**Phase 1: Knowledge Base Agent Integration** - Replace the current Bedrock knowledge base implementation with a unified Bedrock agent that handles knowledge base queries through action groups.

**Phase 2: Metrics Integration** - Extend the agent with metrics capabilities, potentially using multiple specialized agents for different metrics domains.

The design maintains backward compatibility with existing Slack bot functionality while providing enhanced capabilities through the agent architecture.

## Architecture

### Current Architecture (Before Refactoring)

```
Slack Event → Lambda → SlackHandler → BedrockKnowledgeBase → Knowledge Base
                                   → QueryClassifier → BedrockAgentClient (metrics)
```

### Target Architecture (Phase 1)

```
Slack Event → Lambda → SlackHandler → OSCAR Agent (Bedrock) → Knowledge Base Action Group
```

### Target Architecture (Phase 2)

```
Slack Event → Lambda → SlackHandler → Agent Router → OSCAR Knowledge Agent → Knowledge Base Action Group
                                                  → OSCAR Metrics Agent → Test Metrics Action Group
                                                                        → Build Metrics Action Group
                                                                        → Performance Metrics Action Group
                                                  → OSCAR Build Agent → Build-specific Action Groups
                                                  → OSCAR Test Agent → Test-specific Action Groups
```

## Components and Interfaces

### 1. Agent Configuration (Bedrock Console)

#### Phase 1: Knowledge Base Only Agent

**Agent Basic Configuration:**
- **Agent Name**: `oscar-knowledge-agent`
- **Description**: `AI assistant for OpenSearch documentation and knowledge base queries`
- **Foundation Model**: `Claude 3.5 Sonnet` (anthropic.claude-3-5-sonnet-20241022-v1:0)
- **Agent Instructions**:

```text
You are OSCAR, an AI assistant for OpenSearch project management and support. You specialize in providing accurate information from the OpenSearch documentation and knowledge base.

## Core Capabilities

### Knowledge Base Operations
- Answer questions about OpenSearch documentation, configuration, and best practices
- Provide guidance on installation, setup, and troubleshooting
- Explain features, APIs, and architectural concepts
- Offer recommendations based on official documentation

### Response Guidelines
- Always reference official documentation when providing answers
- Provide step-by-step guidance when appropriate
- Include relevant code examples and configuration snippets
- If information is not available in the knowledge base, clearly state this limitation
- Format responses with clear structure and actionable information
- Use markdown formatting for better readability

### Available Topics
- OpenSearch core functionality and APIs
- Security configuration and best practices
- Cluster management and operations
- Plugin development and usage
- Performance optimization
- Troubleshooting common issues

You are helpful, knowledgeable, and focused on providing accurate information from the OpenSearch knowledge base.
```

**Action Group Configuration:**

1. **Action Group Name**: `knowledge_base_operations`
2. **Description**: `Query OpenSearch documentation and knowledge base for guidance and information`
3. **Action Group Type**: **Return control to user**
4. **Action Group Schema**: **Define with function details**

**Function Definition:**

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

#### Phase 2: Extended Metrics Agent Configuration

**Updated Agent Instructions:**

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

**Additional Action Groups for Phase 2:**

1. **test_build_metrics** - Test execution results, build status, and compilation analysis
2. **deployment_performance_metrics** - Deployment status, environment health, and system performance analysis
3. **general_search_health** - Cross-domain search, cluster health, and comprehensive metrics analysis
4. **comprehensive_analysis** - Combined knowledge base and metrics analysis for comprehensive responses

### 2. Code Architecture Refactoring

#### Current Code Structure Analysis

The current codebase has two main implementations:
1. **slack-bot/** - Original implementation with BedrockKnowledgeBase and QueryClassifier
2. **oscar-agent/** - Newer implementation with unified BedrockOSCARAgent

#### Refactoring Strategy

**Phase 1 Changes:**

1. **Consolidate to oscar-agent structure** - Use oscar-agent/ as the primary codebase
2. **Remove query classification logic** - Let the agent handle routing internally
3. **Simplify agent interface** - Single agent call instead of knowledge base + metrics routing
4. **Update CDK configuration** - Point to oscar-agent code and add agent permissions

**Phase 2 Changes:**

1. **Add metrics Lambda function** - Separate Lambda for metrics action groups
2. **Implement multi-agent coordination** - Router to determine which agent to use
3. **Add metrics data access layer** - OpenSearch client for metrics queries

#### Detailed Component Design

##### 1. Agent Interface Layer

**File: `oscar-agent/oscar_agent.py`**

```python
class OSCARAgentInterface(ABC):
    """Abstract base class for OSCAR agent implementations."""
    
    @abstractmethod
    def query(self, query: str, session_id: Optional[str] = None, 
              context_summary: Optional[str] = None) -> Tuple[str, Optional[str]]:
        """Query the OSCAR agent with automatic routing."""
        pass

class BedrockOSCARAgent(OSCARAgentInterface):
    """Unified Bedrock agent implementation."""
    
    def __init__(self, region: Optional[str] = None):
        self.region = region or config.region
        self.client = boto3.client('bedrock-agent-runtime', region_name=self.region)
        self.agent_id = config.oscar_bedrock_agent_id
        self.agent_alias_id = config.oscar_bedrock_agent_alias_id
    
    def query(self, query: str, session_id: Optional[str] = None, 
              context_summary: Optional[str] = None) -> Tuple[str, Optional[str]]:
        """Query the unified agent - no client-side routing needed."""
        # Direct agent invocation - let agent handle routing
        return self._invoke_agent(query, session_id, context_summary)
```

##### 2. Slack Handler Simplification

**File: `oscar-agent/slack_handler.py`**

Key changes:
- Remove query classification logic
- Simplify to single agent call
- Maintain same user experience

```python
def _process_message(self, channel: str, thread_ts: str, user_id: str, 
                    text: str, say: Callable, message_ts: str = None) -> None:
    """Process message with simplified agent call."""
    
    # Extract query
    query = self._extract_query(text)
    
    # Get context
    context = self.storage.get_context(thread_key)
    context_summary = context.get("summary") if context else None
    session_id = context.get("session_id") if context else None
    
    # Single agent call - no routing logic needed
    response, new_session_id = self.oscar_agent.query(
        query, 
        session_id=session_id,
        context_summary=context_summary
    )
    
    # Send response and update context
    say(text=response, thread_ts=thread_ts)
    self._update_context(thread_key, query, response, session_id, new_session_id)
```

##### 3. Configuration Updates

**File: `oscar-agent/config.py`**

```python
class Config:
    def __init__(self, validate_required: bool = True):
        # Phase 1: Single agent configuration
        self.oscar_bedrock_agent_id = os.environ.get('OSCAR_BEDROCK_AGENT_ID')
        self.oscar_bedrock_agent_alias_id = os.environ.get('OSCAR_BEDROCK_AGENT_ALIAS_ID')
        
        # Phase 2: Multi-agent configuration
        self.oscar_knowledge_agent_id = os.environ.get('OSCAR_KNOWLEDGE_AGENT_ID')
        self.oscar_knowledge_agent_alias_id = os.environ.get('OSCAR_KNOWLEDGE_AGENT_ALIAS_ID')
        self.oscar_metrics_agent_id = os.environ.get('OSCAR_METRICS_AGENT_ID')
        self.oscar_metrics_agent_alias_id = os.environ.get('OSCAR_METRICS_AGENT_ALIAS_ID')
        self.oscar_build_agent_id = os.environ.get('OSCAR_BUILD_AGENT_ID')
        self.oscar_build_agent_alias_id = os.environ.get('OSCAR_BUILD_AGENT_ALIAS_ID')
        self.oscar_test_agent_id = os.environ.get('OSCAR_TEST_AGENT_ID')
        self.oscar_test_agent_alias_id = os.environ.get('OSCAR_TEST_AGENT_ALIAS_ID')
        
        # Agent routing configuration
        self.enable_multi_agent = os.environ.get('ENABLE_MULTI_AGENT', 'false').lower() == 'true'
        self.default_agent = os.environ.get('DEFAULT_AGENT', 'knowledge')
```

### 3. Metrics Integration Architecture (Phase 2)

#### Multi-Agent Strategy

Due to Bedrock's 10 function limit per agent, we'll use specialized agents:

1. **OSCAR Knowledge Agent** - Documentation and knowledge base queries
2. **OSCAR Metrics Agent** - General metrics queries and cross-domain analysis
3. **OSCAR Build Agent** - Build-specific metrics and analysis
4. **OSCAR Test Agent** - Test-specific metrics and analysis

#### Agent Router Implementation

**File: `oscar-agent/agent_router.py`**

```python
class AgentRouter:
    """Routes queries to appropriate specialized agents."""
    
    def __init__(self):
        self.knowledge_agent = BedrockOSCARAgent(
            config.oscar_knowledge_agent_id,
            config.oscar_knowledge_agent_alias_id
        )
        self.metrics_agent = BedrockOSCARAgent(
            config.oscar_metrics_agent_id,
            config.oscar_metrics_agent_alias_id
        )
        self.build_agent = BedrockOSCARAgent(
            config.oscar_build_agent_id,
            config.oscar_build_agent_alias_id
        )
        self.test_agent = BedrockOSCARAgent(
            config.oscar_test_agent_id,
            config.oscar_test_agent_alias_id
        )
        self.classifier = QueryClassifier()
    
    def route_query(self, query: str, session_id: Optional[str] = None, 
                   context_summary: Optional[str] = None) -> Tuple[str, Optional[str]]:
        """Route query to appropriate agent."""
        
        # Classify query type
        query_type = self.classifier.classify_query(query)
        
        # Route to appropriate agent
        if query_type == 'knowledge':
            return self.knowledge_agent.query(query, session_id, context_summary)
        elif query_type == 'build':
            return self.build_agent.query(query, session_id, context_summary)
        elif query_type == 'test':
            return self.test_agent.query(query, session_id, context_summary)
        elif query_type == 'metrics':
            return self.metrics_agent.query(query, session_id, context_summary)
        else:
            # Default to knowledge agent
            return self.knowledge_agent.query(query, session_id, context_summary)
```

#### Metrics Lambda Function

**File: `metrics-lambda/main.py`**

```python
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler for metrics action groups."""
    
    try:
        # Parse Bedrock agent event
        function_name = event.get('function')
        parameters = {p['name']: p['value'] for p in event.get('parameters', [])}
        
        # Route to appropriate metrics service
        if function_name.startswith('get_test_'):
            result = metrics_service.get_test_metrics(**parameters)
        elif function_name.startswith('get_build_'):
            result = metrics_service.get_build_metrics(**parameters)
        elif function_name.startswith('get_deployment_'):
            result = metrics_service.get_deployment_metrics(**parameters)
        elif function_name.startswith('get_performance_'):
            result = metrics_service.get_performance_metrics(**parameters)
        else:
            result = metrics_service.search_all_metrics(**parameters)
        
        # Format response for Bedrock
        formatted_response = response_formatter.format_for_bedrock(result)
        
        return {
            "messageVersion": "1.0",
            "response": {
                "actionGroup": event.get("actionGroup"),
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
        return error_response(str(e))
```

#### Query Classification Enhancement

**File: `oscar-agent/query_classifier.py`**

```python
class QueryClassifier:
    """Enhanced query classifier for multi-agent routing."""
    
    KNOWLEDGE_KEYWORDS = [
        'how to', 'configure', 'setup', 'install', 'explain', 'documentation',
        'guide', 'tutorial', 'best practice', 'recommend', 'what is', 'why'
    ]
    
    BUILD_KEYWORDS = [
        'build', 'compilation', 'artifact', 'release', 'version', 'deploy'
    ]
    
    TEST_KEYWORDS = [
        'test', 'testing', 'failure', 'coverage', 'junit', 'gradle'
    ]
    
    METRICS_KEYWORDS = [
        'performance', 'latency', 'throughput', 'metrics', 'status', 'health'
    ]
    
    def classify_query(self, query: str) -> str:
        """Classify query into knowledge, build, test, or metrics category."""
        
        query_lower = query.lower()
        
        # Score each category
        knowledge_score = sum(1 for kw in self.KNOWLEDGE_KEYWORDS if kw in query_lower)
        build_score = sum(1 for kw in self.BUILD_KEYWORDS if kw in query_lower)
        test_score = sum(1 for kw in self.TEST_KEYWORDS if kw in query_lower)
        metrics_score = sum(1 for kw in self.METRICS_KEYWORDS if kw in query_lower)
        
        # Return category with highest score
        scores = {
            'knowledge': knowledge_score,
            'build': build_score,
            'test': test_score,
            'metrics': metrics_score
        }
        
        return max(scores, key=scores.get) if max(scores.values()) > 0 else 'knowledge'
```

## Data Models

### Agent Configuration Model

```python
@dataclass
class AgentConfig:
    """Configuration for a Bedrock agent."""
    agent_id: str
    agent_alias_id: str
    region: str
    timeout: int = 60
    max_retries: int = 2

@dataclass
class MultiAgentConfig:
    """Configuration for multi-agent setup."""
    knowledge_agent: AgentConfig
    metrics_agent: Optional[AgentConfig] = None
    build_agent: Optional[AgentConfig] = None
    test_agent: Optional[AgentConfig] = None
    enable_routing: bool = False
    default_agent: str = 'knowledge'
```

### Query Context Model

```python
@dataclass
class QueryContext:
    """Context for agent queries."""
    query: str
    session_id: Optional[str] = None
    context_summary: Optional[str] = None
    user_id: Optional[str] = None
    channel_id: Optional[str] = None
    thread_ts: Optional[str] = None
    query_type: Optional[str] = None
    
@dataclass
class AgentResponse:
    """Response from agent query."""
    text: str
    session_id: Optional[str] = None
    agent_used: str = 'unknown'
    processing_time: float = 0.0
    error: Optional[str] = None
```

### Metrics Data Models

```python
@dataclass
class TestMetrics:
    """Test execution metrics."""
    repository: str
    total_tests: int
    passed_tests: int
    failed_tests: int
    skipped_tests: int
    execution_time: float
    coverage_percentage: Optional[float] = None
    
@dataclass
class BuildMetrics:
    """Build execution metrics."""
    repository: str
    build_id: str
    status: str
    duration: float
    artifacts: List[str]
    version: Optional[str] = None
    
@dataclass
class DeploymentMetrics:
    """Deployment status metrics."""
    repository: str
    environment: str
    status: str
    version: str
    deployment_time: datetime
    rollback_available: bool
```

## Error Handling

### Agent Error Handling Strategy

1. **Connection Errors** - Retry with exponential backoff
2. **Session Expiry** - Fall back to context-enhanced queries
3. **Agent Unavailable** - Route to alternative agent or provide graceful degradation
4. **Timeout Errors** - Provide partial response with timeout indication
5. **Permission Errors** - Log and provide user-friendly error message

### Error Response Format

```python
class AgentErrorHandler:
    """Handles agent-specific errors."""
    
    def handle_agent_error(self, error: Exception, query: str) -> str:
        """Convert agent errors to user-friendly messages."""
        
        if isinstance(error, ClientError):
            if error.response['Error']['Code'] == 'AccessDeniedException':
                return "I don't have permission to access that information. Please contact your administrator."
            elif error.response['Error']['Code'] == 'ThrottlingException':
                return "I'm currently experiencing high load. Please try again in a moment."
            elif error.response['Error']['Code'] == 'ValidationException':
                return "There was an issue with your query format. Please try rephrasing your question."
        
        elif isinstance(error, TimeoutError):
            return "Your query is taking longer than expected. I'm still working on it, but you may want to try a more specific question."
        
        else:
            logger.error(f"Unexpected agent error: {error}", exc_info=True)
            return "I encountered an unexpected error. Please try again or contact support if this continues."
```

## Testing Strategy

### Unit Testing

1. **Agent Interface Tests** - Mock Bedrock agent responses
2. **Query Classification Tests** - Validate routing logic
3. **Context Management Tests** - Verify session handling
4. **Error Handling Tests** - Test all error scenarios

### Integration Testing

1. **End-to-End Agent Tests** - Real agent invocations with test queries
2. **Slack Integration Tests** - Mock Slack events and validate responses
3. **Multi-Agent Coordination Tests** - Verify agent routing works correctly
4. **Performance Tests** - Validate response times and throughput

### Test Implementation

```python
class TestOSCARAgent:
    """Test suite for OSCAR agent integration."""
    
    @pytest.fixture
    def mock_agent_response(self):
        """Mock successful agent response."""
        return {
            'completion': [
                {'chunk': {'bytes': b'Test response from agent'}}
            ],
            'sessionId': 'test-session-123'
        }
    
    def test_knowledge_query(self, mock_bedrock_client, mock_agent_response):
        """Test knowledge base query routing."""
        mock_bedrock_client.invoke_agent.return_value = mock_agent_response
        
        agent = BedrockOSCARAgent()
        response, session_id = agent.query("How do I configure OpenSearch security?")
        
        assert "Test response from agent" in response
        assert session_id == "test-session-123"
        mock_bedrock_client.invoke_agent.assert_called_once()
    
    def test_metrics_query_routing(self, mock_agent_router):
        """Test metrics query routing to appropriate agent."""
        router = AgentRouter()
        
        # Test build query routing
        response, _ = router.route_query("What's the latest build status?")
        mock_agent_router.build_agent.query.assert_called_once()
        
        # Test test query routing
        response, _ = router.route_query("Show me test failures from last week")
        mock_agent_router.test_agent.query.assert_called_once()
```

### Performance Testing

```python
class TestAgentPerformance:
    """Performance tests for agent responses."""
    
    def test_response_time_requirements(self):
        """Verify agent responses meet time requirements."""
        agent = BedrockOSCARAgent()
        
        start_time = time.time()
        response, _ = agent.query("Test query")
        end_time = time.time()
        
        assert end_time - start_time < 10.0  # 10 second requirement
    
    def test_concurrent_queries(self):
        """Test agent handles concurrent queries."""
        agent = BedrockOSCARAgent()
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(agent.query, f"Test query {i}")
                for i in range(10)
            ]
            
            results = [future.result() for future in futures]
            assert len(results) == 10
            assert all(response for response, _ in results)
```

## Migration Strategy

### Phase 1 Migration Steps

1. **Prepare New Agent Configuration**
   - Create knowledge base agent in Bedrock console
   - Configure action group with knowledge base function
   - Test agent with sample queries

2. **Update Codebase**
   - Copy oscar-agent structure as primary implementation
   - Remove query classification logic
   - Update configuration to use single agent
   - Update CDK to deploy oscar-agent code

3. **Deploy and Test**
   - Deploy updated Lambda function
   - Test with existing Slack bot functionality
   - Verify backward compatibility

4. **Cleanup**
   - Remove old slack-bot implementation
   - Update documentation
   - Archive legacy code

### Phase 2 Migration Steps

1. **Create Specialized Agents**
   - Build agent with build-specific action groups
   - Test agent with test-specific action groups
   - Metrics agent with general metrics action groups

2. **Implement Metrics Lambda**
   - Deploy metrics Lambda function
   - Configure action groups to use metrics Lambda
   - Test metrics data access

3. **Add Agent Router**
   - Implement query classification
   - Add multi-agent coordination
   - Test agent routing logic

4. **Gradual Rollout**
   - Enable multi-agent for specific channels
   - Monitor performance and accuracy
   - Full rollout after validation

### Rollback Strategy

1. **Configuration Rollback** - Revert environment variables to previous agent IDs
2. **Code Rollback** - Deploy previous Lambda version
3. **Agent Rollback** - Revert to previous agent configuration in Bedrock console
4. **Data Integrity** - Ensure session data remains compatible across versions

This design provides a comprehensive roadmap for refactoring OSCAR to use Bedrock agents while maintaining functionality and enabling future metrics integration.